"""Offline tests for the WP2c evidence-linking pipeline.

The tests are deliberate about the four failure modes the mission cares most about:

  (a) a **company-match-only** link (same company, different technology track, or
      same track but a different company) must NOT be accepted as support;
  (b) an **out-of-window** evidence item must NOT be accepted;
  (c) a candidate with **no independent evidence** must produce
      ``NO_INDEPENDENT_SUPPORT`` and must NOT be silently dropped from the output;
  (d) no output field may carry a development/intent conclusion, and the verdict
      vocabulary must be closed.

No network, no 76 MB warehouse: a tiny SQLite fixture with the same columns as the
read-only evidence warehouse is created in ``tmp_path``.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "experiments" / "innovation_signals_observatory" / "evidence" / "link_evidence.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("evidence_link_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


LE = _load_module()

EP_PFA = "ep_pfa"
CARDIAC_RHYTHM = "cardiac_rhythm"


# --------------------------------------------------------------------- fixtures
def _classified(track_id: str, function_class: str = "CORE_R&D") -> dict[str, Any]:
    return {
        "classifier_source": "medradar.recruitment.taxonomy.classify_rules",
        "classifier_arm": "rules_A",
        "rules_version": "test_rules_version",
        "function_map_version": "test_map_version",
        "function_map_fingerprint": "0" * 64,
        "taxonomy_regime": {"version": "test"},
        "function_class": function_class,
        "function_decision_basis": "title_phrases",
        "function_rule_strength": "MODERATE",
        "confidence_statement": "rule-derived, not a probability",
        "track_id": track_id,
        "track_status": "MAPPED",
        "track_reason": "stub",
        "track_candidate": None,
        "function_spans": [{"field": "job_title", "quote": function_class, "rule": "stub", "target": function_class, "context": ""}],
        "track_spans": [],
        "unclassified_reason": None,
    }


def _stub_classifier(job: Mapping[str, Any]) -> dict[str, Any]:
    title = str(job.get("job_title") or "")
    if "PFA" in title.upper() or "EP" in title.upper():
        return _classified(EP_PFA)
    return _classified(CARDIAC_RHYTHM)


def _posting(posting_id: str, title: str, first_seen: str = "2026-11-04T12:50:44+00:00") -> dict[str, Any]:
    return {
        "posting_id": posting_id,
        "company_key": "medtronic",
        "job_title": title,
        "job_description": "stub description",
        "job_location": "Somewhere",
        "source_url": f"https://example.invalid/{posting_id}",
        "source_posted_at": "2026-11-03",
        "source_posted_quality": "SOURCE_DATE",
        "first_seen_at": first_seen,
    }


def _event(
    event_id: str,
    *,
    kind: str = "510k",
    company_key: str | None = "medtronic",
    track_id: str | None = EP_PFA,
    event_date: str = "2026-05-01",
    as_of: str = "2026-10-30",
    url: str = "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K123456",
    title: str = "Medtronic 510(k)：PFA catheter",
    summary: str = "PFA",
    payload: str = '{"k_number": "K123456"}',
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "source": "openfda_device_510k" if kind == "510k" else f"openfda_device_{kind}",
        "kind": kind,
        "event_date": event_date,
        "as_of": as_of,
        "company_key": company_key,
        "track_id": track_id,
        "product_code": "XXX",
        "title": title,
        "summary": summary,
        "url": url,
        "payload": payload,
        "fetched_at": "2026-10-30T17:00:00Z",
    }


def _make_cell(le, postings: list[dict[str, Any]], focus, tracks) -> dict[str, Any]:
    aggregate = le.build_cells(postings, _stub_classifier, tracks, focus)
    assert aggregate["cells"], "fixture postings should produce at least one cell"
    return aggregate["cells"][0]


def _evaluate(le, cell, rows, focus, tracks, db_tracks, ctgov=None):
    ctgov = ctgov or {"status": "NOT_QUERIED", "by_track": {}, "requests": []}
    cell["evidence"] = le.evaluate_cell_evidence(cell, rows, tracks, focus, db_tracks, ctgov, None)
    le.assign_verdict(cell)
    return cell


@pytest.fixture(scope="module")
def config():
    return LE.load_tracks(), LE.load_focus_companies()


# ---------------------------------------------------------------- the four tests
def test_company_match_only_is_not_accepted_as_support(config):
    """(a) Same company but a different track, and same track but a different company."""
    tracks, focus = config
    db_tracks = [{"id": t} for t in tracks]
    postings = [_posting("p1", "Senior PFA R&D Engineer"), _posting("p2", "Principal PFA Scientist")]
    cell = _make_cell(LE, postings, focus, tracks)

    rows = [
        # same company, DIFFERENT track -> R2 must fail
        _event("e-wrong-track", company_key="medtronic", track_id=CARDIAC_RHYTHM),
        # same track, DIFFERENT company -> R1 must fail
        _event("e-wrong-company", company_key="abbott", track_id=EP_PFA),
    ]
    cell = _evaluate(LE, cell, rows, focus, tracks, db_tracks)

    assert cell["is_candidate"] is True
    assert cell["evidence"]["linked"] == [], "company-match-only may never be treated as support"
    assert cell["verdict"] == "NO_INDEPENDENT_SUPPORT"
    failed = cell["evidence"]["failed_rule_counts"]
    assert failed.get("R1_SAME_ENTITY", 0) >= 1
    assert failed.get("R2_SAME_TRACK", 0) >= 1
    # the different-track record must be visible as a rejection, not silently dropped
    rejected_ids = {item["record_id"] for item in cell["evidence"]["rejected"]}
    assert "e-wrong-track" in rejected_ids


def test_out_of_window_evidence_is_not_accepted(config):
    """(b) In-window is [anchor-24m, anchor]; a 2020 record is outside it."""
    tracks, focus = config
    db_tracks = [{"id": t} for t in tracks]
    postings = [_posting("p1", "Senior PFA R&D Engineer"), _posting("p2", "Principal PFA Scientist")]
    cell = _make_cell(LE, postings, focus, tracks)

    rows = [_event("e-old", event_date="2020-01-01")]
    cell = _evaluate(LE, cell, rows, focus, tracks, db_tracks)

    assert cell["evidence"]["linked"] == []
    assert cell["verdict"] == "NO_INDEPENDENT_SUPPORT"
    assert cell["verdict_reason"]["code"] == "EVIDENCE_OUTSIDE_TIME_WINDOW"
    assert cell["evidence"]["failed_rule_counts"].get("R3_TIME_WINDOW") == 1
    assert cell["hiring_window"]["window_start"] == "2024-11-04"


def test_missing_independent_evidence_yields_no_support_not_dropped(config):
    """(c) A candidate with no same-track evidence stays in the output as NO_INDEPENDENT_SUPPORT."""
    tracks, focus = config
    db_tracks = [{"id": t} for t in tracks]
    postings = [_posting("p1", "Senior PFA R&D Engineer"), _posting("p2", "Principal PFA Scientist")]
    cell = _make_cell(LE, postings, focus, tracks)

    rows = [_event("e-other-track", track_id=CARDIAC_RHYTHM)]
    cell = _evaluate(LE, cell, rows, focus, tracks, db_tracks)

    assert cell["verdict"] == "NO_INDEPENDENT_SUPPORT"
    assert cell["verdict_reason"]["code"] == "NO_EVIDENCE_ROWS_IN_TRACK"
    assert "evidence" in cell, "the cell must not be dropped when evidence is absent"
    assert cell["evidence"]["status"] == "EVALUATED"


def test_valid_in_window_evidence_is_independently_supported(config):
    """Positive control: all four rules pass -> INDEPENDENTLY_SUPPORTED with an identifier."""
    tracks, focus = config
    db_tracks = [{"id": t} for t in tracks]
    postings = [_posting("p1", "Senior PFA R&D Engineer"), _posting("p2", "Principal PFA Scientist")]
    cell = _make_cell(LE, postings, focus, tracks)

    rows = [_event("e-ok", event_date="2026-05-01", payload='{"k_number": "K123456"}')]
    cell = _evaluate(LE, cell, rows, focus, tracks, db_tracks)

    assert cell["verdict"] == "INDEPENDENTLY_SUPPORTED"
    assert cell["evidence"]["linked"], "a passing item must be recorded as linked"
    linked = cell["evidence"]["linked"][0]
    assert linked["identifier"] == "K123456"
    assert linked["rules"] == {
        "R1_SAME_ENTITY": True,
        "R2_SAME_TRACK": True,
        "R3_TIME_WINDOW": True,
        "R4_RESOLVABLE_IDENTIFIER": True,
    }


def test_missing_identifier_is_not_linkable(config):
    """R4: a record without a resolvable FDA/NCT id cannot support a candidate."""
    tracks, focus = config
    db_tracks = [{"id": t} for t in tracks]
    postings = [_posting("p1", "Senior PFA R&D Engineer"), _posting("p2", "Principal PFA Scientist")]
    cell = _make_cell(LE, postings, focus, tracks)

    rows = [
        _event(
            "e-no-id",
            url="https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm",
            title="Medtronic 510(k)：device",
            summary="no identifier here",
            payload="{}",
        )
    ]
    cell = _evaluate(LE, cell, rows, focus, tracks, db_tracks)

    assert cell["evidence"]["linked"] == []
    assert cell["verdict"] == "NO_INDEPENDENT_SUPPORT"
    assert cell["evidence"]["failed_rule_counts"].get("R4_RESOLVABLE_IDENTIFIER") == 1


def test_recall_only_is_contrary_context_not_contradicted(config):
    """A recall is post-market context, not a contradiction of an R&D direction."""
    tracks, focus = config
    db_tracks = [{"id": t} for t in tracks]
    postings = [_posting("p1", "Senior PFA R&D Engineer"), _posting("p2", "Principal PFA Scientist")]
    cell = _make_cell(LE, postings, focus, tracks)

    rows = [
        _event(
            "e-recall",
            kind="device_recall",
            url="https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRES/res.cfm?id=95278",
            title="Medtronic 召回：PFA catheter",
            summary="recall",
            payload='{"product_res_number": "Z-1234-2026", "res_event_number": "95278"}',
        )
    ]
    cell = _evaluate(LE, cell, rows, focus, tracks, db_tracks)

    assert cell["verdict"] == "NO_INDEPENDENT_SUPPORT"
    assert cell["verdict_reason"]["code"] == "ONLY_CONTRARY_CONTEXT_EVIDENCE"
    assert len(cell["evidence"]["contrary_context"]) == 1
    assert cell["verdict"] != "CONTRADICTED", "a recall is not a cessation signal"


def test_below_candidate_threshold_gets_unknown_not_a_verdict(config):
    tracks, focus = config
    db_tracks = [{"id": t} for t in tracks]
    cell = _make_cell(LE, [_posting("p1", "Senior PFA R&D Engineer")], focus, tracks)
    cell = _evaluate(LE, cell, [], focus, tracks, db_tracks)

    assert cell["is_candidate"] is False
    assert cell["hiring_signal_verdict"] == "UNKNOWN"
    assert cell["verdict"] == "UNKNOWN"
    assert cell["verdict_reason"]["code"] == "BELOW_CANDIDATE_THRESHOLD"


def test_payload_truncation_falls_back_to_url_identifier(config):
    """The dev warehouse truncates payloads; an id near the payload start must still resolve."""
    row = _event("e-truncated", payload='{"k_number": "K999999", "applicant": "MEDTRONIC", "decision_dat')
    payload, payload_ok = LE.safe_payload(row["payload"])
    assert payload_ok is False
    identifier, source, granularity = LE.resolve_identifier(row, payload, payload_ok)
    assert identifier == "K999999"
    assert source == "raw_payload_regex"
    assert granularity == "510k"

    # If the truncated payload carries no id either, the url column is the last fallback.
    row = _event("e-truncated-2", payload='{"applicant": "MEDTRONIC", "decision_dat')
    payload, payload_ok = LE.safe_payload(row["payload"])
    identifier, source, granularity = LE.resolve_identifier(row, payload, payload_ok)
    assert identifier == "K123456"
    assert source == "url_or_title_regex"


# -------------------------------------------------------- pipeline-level checks
def _build_fixture_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE events (
            event_id TEXT PRIMARY KEY, source TEXT, kind TEXT, event_date TEXT, as_of TEXT,
            company_key TEXT, applicant_raw TEXT, country TEXT, track_id TEXT, product_code TEXT,
            title TEXT, summary TEXT, url TEXT, payload TEXT, fetched_at TEXT
        );
        CREATE TABLE tracks (
            id TEXT PRIMARY KEY, name_zh TEXT, name_en TEXT, category TEXT, keywords TEXT, updated_at TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO tracks (id, name_zh, name_en, category, keywords) VALUES (?,?,?,?,?)",
        (EP_PFA, "电生理与脉冲场消融", "Electrophysiology / PFA", "cardiovascular", "[]"),
    )
    conn.execute(
        "INSERT INTO tracks (id, name_zh, name_en, category, keywords) VALUES (?,?,?,?,?)",
        (CARDIAC_RHYTHM, "心脏节律", "Cardiac Rhythm", "cardiovascular", "[]"),
    )
    rows = [
        _event("e-ok", event_date="2026-05-01"),
        _event("e-old", event_date="2020-01-01"),
    ]
    conn.executemany(
        "INSERT INTO events VALUES (:event_id, :source, :kind, :event_date, :as_of, :company_key, "
        ":applicant_raw, NULL, :track_id, :product_code, :title, :summary, :url, :payload, :fetched_at)",
        [dict(row, applicant_raw="MEDTRONIC") for row in rows],
    )
    conn.commit()
    conn.close()


def _write_jobs_fixture(path: Path, postings: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in postings) + "\n", encoding="utf-8")


def test_pipeline_output_vocabulary_is_closed_and_conclusion_free(tmp_path):
    """(d) Closed vocabulary; no verdict field may claim a development conclusion."""
    jobs = tmp_path / "jobs.jsonl"
    _write_jobs_fixture(
        jobs,
        [
            _posting("p1", "Senior PFA R&D Engineer"),
            _posting("p2", "Principal PFA Scientist"),
            _posting("p3", "Reliability Engineer"),
        ],
    )
    db = tmp_path / "fixture.sqlite"
    _build_fixture_db(db)
    out_json = tmp_path / "evidence_linking.json"
    out_md = tmp_path / "evidence_linking.md"

    artifact = LE.run(
        jobs_path=jobs,
        evidence_db=db,
        results_dir=tmp_path,
        ctgov_cache=tmp_path / "no_ctgov_cache",
        out_json=out_json,
        out_md=out_md,
        classify=_stub_classifier,
        generated_at="2026-11-04T21:00:00+00:00",
    )
    assert out_json.exists() and out_md.exists()
    payload = json.loads(out_json.read_text(encoding="utf-8"))

    # vocabulary is closed in both fields
    assert set(payload["verdict_vocabulary"]) == set(LE.VERDICTS)
    for cell in payload["cells"]:
        assert cell["verdict"] in LE.VERDICTS
        assert cell["hiring_signal_verdict"] in LE.HIRING_SIGNAL_VERDICTS
        for field in ("verdict", "hiring_signal_verdict"):
            assert cell[field] is not None
        text = " | ".join(
            str(part)
            for part in (
                cell["verdict_reason"].get("code"),
                cell["verdict_reason"].get("detail_zh"),
                cell["verdict_reason"].get("detail_en"),
                (cell.get("escalation") or {}).get("reason_zh"),
            )
            if part
        )
        for pattern in LE.CONCLUSION_FORBIDDEN_PATTERNS:
            assert not pattern.search(text), f"forbidden conclusion language: {pattern.pattern} in {text!r}"

    # the candidate cell with in-window evidence is supported; the out-of-window row is not used
    pfa = next(cell for cell in payload["cells"] if cell["track_id"] == EP_PFA)
    assert pfa["is_candidate"] is True
    assert pfa["verdict"] == "INDEPENDENTLY_SUPPORTED"
    linked_ids = {item["record_id"] for item in pfa["evidence"]["linked"]}
    assert "e-ok" in linked_ids
    assert "e-old" not in linked_ids

    # every candidate appears in the output; nothing is silently dropped
    assert payload["summary"]["n_cells"] == len(payload["cells"])
    assert payload["summary"]["n_candidates"] >= 1
    md = out_md.read_text(encoding="utf-8")
    assert "逐 track 计数" in md

    # the meaning of INDEPENDENTLY_SUPPORTED is stated, not inferred
    assert "NECESSARY-BUT-WEAK" in payload["verdict_definitions"]["INDEPENDENTLY_SUPPORTED"]
    assert set(payload["direction_novelty_vocabulary"]) == set(LE.DIRECTION_NOVELTY_VOCABULARY)
    assert any("必要但很弱" in note for note in payload["limitations"])
    for cell in payload["cells"]:
        assert "direction_novelty" in cell
        assert cell["direction_novelty"]["direction_novelty"] in LE.DIRECTION_NOVELTY_VOCABULARY


def test_ctgov_rules_use_exact_entity_and_verbatim_track_keyword(config):
    tracks, focus = config
    db_tracks = [{"id": t} for t in tracks]
    postings = [_posting("p1", "Senior PFA R&D Engineer"), _posting("p2", "Principal PFA Scientist")]
    cell = _make_cell(LE, postings, focus, tracks)
    window = LE._cell_window(cell)
    track = tracks[EP_PFA]

    good = {
        "nct_id": "NCT07298473",
        "brief_title": "Conquer-AF Redo Ablation Using the Sphere-9 Catheter and Affera Ablation System",
        "overall_status": "RECRUITING",
        "start_date": "2026-04-08",
        "study_first_post_date": "2025-12-23",
        "lead_sponsor": "Medtronic Cardiac Ablation Solutions",
        "conditions": ["Atrial Fibrillation"],
        "interventions": ["Pulsed Field Ablation"],
        "brief_summary": "Pulsed field ablation for persistent AF.",
    }
    item = LE.evaluate_ctgov_item(good, cell, track, focus, window)
    assert item["linkable"] is True
    assert item["identifier"] == "NCT07298473"
    assert item["entity_alias_hits"]

    wrong_sponsor = dict(good, lead_sponsor="University Medical Centre Ljubljana")
    item = LE.evaluate_ctgov_item(wrong_sponsor, cell, track, focus, window)
    assert item["rules"]["R1_SAME_ENTITY"] is False
    assert item["linkable"] is False

    wrong_track = dict(
        good,
        brief_title="A pacemaker study",
        conditions=["Bradycardia"],
        interventions=["Defibrillator"],
        brief_summary="A pacemaker study.",
    )
    item = LE.evaluate_ctgov_item(wrong_track, cell, track, focus, window)
    assert item["rules"]["R2_SAME_TRACK"] is False


def test_evidence_db_is_opened_read_only(tmp_path):
    db = tmp_path / "fixture.sqlite"
    _build_fixture_db(db)
    conn = LE.open_evidence_db(db)
    try:
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("INSERT INTO tracks (id) VALUES ('x')")
    finally:
        conn.close()


# ------------------------------------------------- direction novelty (Lead review)
def _novelty(rows: list[dict[str, Any]], coverage_start: str = "2024-10-01") -> dict[str, Any]:
    cell = {"first_seen_min": "2026-11-04T12:50:44+00:00"}
    window = LE._cell_window(cell)
    return LE.derive_direction_novelty(rows, window, LE.parse_date(coverage_start))


def _date_rows(dates: list[str]) -> list[dict[str, Any]]:
    return [_event(f"nov-{index}", event_date=value) for index, value in enumerate(dates)]


def test_direction_novelty_new_candidate_when_baseline_empty():
    profile = _novelty(_date_rows(["2026-06-01", "2026-08-01"]))
    assert profile["direction_novelty"] == "NEW_DIRECTION_CANDIDATE"
    assert profile["n_events_before_recent_window"] == 0
    assert profile["n_events_recent_window"] == 2
    # the claim is only "new relative to observed coverage", never "new to the company"
    assert "可见基线" in profile["reason_zh"]


def test_direction_novelty_established_when_history_is_continuous():
    dates = [f"{year}-{month:02d}-15" for year in (2024, 2025, 2026) for month in range(1, 13)]
    dates = [value for value in dates if "2024-10-01" <= value <= "2026-10-31"]
    profile = _novelty(_date_rows(dates))
    assert profile["direction_novelty"] == "ESTABLISHED_DIRECTION"
    assert profile["n_events_before_recent_window"] > 0
    assert profile["event_counts_by_kind"]


def test_direction_novelty_sparse_monthly_grid_but_multi_year_span_is_established():
    """A sparse filing rate must not mislabel a real product line as 'recent'."""
    sparse = ["2024-11-01", "2025-02-01", "2025-05-01", "2025-08-01", "2025-11-15", "2026-02-01", "2026-05-01"]
    profile = _novelty(_date_rows(sparse))
    assert profile["distinct_months_with_events"] < 12  # not a filing every month
    assert profile["direction_novelty"] == "ESTABLISHED_DIRECTION"


def test_direction_novelty_recent_when_span_short():
    profile = _novelty(_date_rows(["2024-12-01", "2025-03-01", "2026-08-01"]))
    assert profile["direction_novelty"] == "RECENT_ACTIVITY"


def test_direction_novelty_no_baseline_when_source_truncates():
    profile = _novelty(_date_rows(["2026-07-01"]), coverage_start="2026-06-01")
    assert profile["direction_novelty"] == "NO_BASELINE_DATA"
    assert profile["baseline_window_months_observed"] < LE.NOVELTY_MIN_BASELINE_MONTHS


def test_human_review_requires_reviewable_novelty(config):
    """A long-established track with >=3 postings must NOT flood the review queue."""
    tracks, focus = config
    db_tracks = [{"id": t} for t in tracks]
    postings = [_posting("p1", "PFA R&D Engineer"), _posting("p2", "PFA Scientist"), _posting("p3", "PFA Engineer")]
    established_dates = [f"{year}-{month:02d}-15" for year in (2024, 2025, 2026) for month in range(1, 13)]
    established_dates = [value for value in established_dates if "2024-10-01" <= value <= "2026-10-31"]

    established_rows = [_event(f"est-{i}", event_date=value) for i, value in enumerate(established_dates)]
    cell = _make_cell(LE, postings, focus, tracks)
    cell = _evaluate(LE, cell, established_rows, focus, tracks, db_tracks)
    cell["direction_novelty"] = LE.derive_direction_novelty(
        established_rows, cell["hiring_window"], LE.parse_date("2024-10-01")
    )
    cell = LE.assign_verdict(cell)
    assert cell["verdict"] == "INDEPENDENTLY_SUPPORTED"
    assert cell["n_distinct_posting_ids"] >= 3
    assert cell["direction_novelty"]["direction_novelty"] == "ESTABLISHED_DIRECTION"
    assert cell["escalation"]["human_review_recommended"] is False

    new_rows = [_event("new-1", event_date="2026-06-01")]
    cell = _make_cell(LE, postings, focus, tracks)
    cell = _evaluate(LE, cell, new_rows, focus, tracks, db_tracks)
    cell["direction_novelty"] = LE.derive_direction_novelty(
        new_rows, cell["hiring_window"], LE.parse_date("2024-10-01")
    )
    cell = LE.assign_verdict(cell)
    assert cell["direction_novelty"]["direction_novelty"] == "NEW_DIRECTION_CANDIDATE"
    assert cell["escalation"]["human_review_recommended"] is True


def test_evidence_specificity_separates_admin_from_device_evidence(config):
    base = dict(_event("spec-1"))
    payload_process = '{"pma_number": "P100010", "supplement_reason": "Process Change - Manufacturer/Sterilizer/Packager/Supplier"}'
    payload_design = '{"pma_number": "P100010", "supplement_reason": "Change Design/Components/Specifications/Material"}'
    process = LE.evaluate_db_item(dict(base, kind="pma", payload=payload_process), {"company_key": "medtronic", "track_id": EP_PFA, "track_in_config_taxonomy": True}, {"window_start": "2024-11-04", "window_end": "2026-11-04"}, {"medtronic": {}})
    design = LE.evaluate_db_item(dict(base, kind="pma", payload=payload_design), {"company_key": "medtronic", "track_id": EP_PFA, "track_in_config_taxonomy": True}, {"window_start": "2024-11-04", "window_end": "2026-11-04"}, {"medtronic": {}})
    clearance = LE.evaluate_db_item(dict(base, kind="510k", payload='{"k_number": "K123456"}'), {"company_key": "medtronic", "track_id": EP_PFA, "track_in_config_taxonomy": True}, {"window_start": "2024-11-04", "window_end": "2026-11-04"}, {"medtronic": {}})
    assert process["evidence_specificity"] == "LOW_MANUFACTURING_PROCESS_CHANGE"
    assert design["evidence_specificity"] == "MEDIUM_DESIGN_CHANGE"
    assert clearance["evidence_specificity"] == "HIGH_DEVICE_CLEARANCE"
