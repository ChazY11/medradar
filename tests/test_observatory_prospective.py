"""Synthetic tier: frozen Prospective Observation Registry (no network, no real data).

Every entry created here is an explicit synthetic fixture (``synthetic=True`` and
``合成测试`` in its label/note) so nothing in this file can be mistaken for a real
prospective observation.  The ledger and the registry both live under
``tmp_path`` via ``MEDRADAR_OBSERVATORY_DB`` / ``MEDRADAR_PROSPECTIVE_DIR``; the
real ``data/`` directory is never written.

What is proven here:

* ``freeze()`` is write-once: an identical re-freeze is an idempotent duplicate,
  a different protocol under the same id is refused;
* later ledger writes (a new observation and a new version of a frozen input)
  cannot change the frozen bytes, the frozen content hash, or the recorded
  point-in-time inputs; ``verify_frozen()`` still passes;
* tampering with the frozen file is detected and blocks evaluation;
* an evaluation before ``window_end`` is refused as ``NOT_DUE`` (nothing written);
* an evaluation after ``window_end`` counts only observations first seen inside
  the declared window, reports the ledger counts at the computation moment, and
  never counts records discovered after the window;
* synthetic entries are labelled 合成测试 and are never presented as evidence;
* the HTTP shapes of ``/api/lab/prospective`` and
  ``/api/lab/prospective/{entry_id}``, including the honest empty state, and
  that ``/api/lab`` + ``/api/lab/{study_id}`` still respond.
"""

from __future__ import annotations

import json
import types
from datetime import datetime, timedelta, timezone

import pytest

from medradar.observatory import prospective as registry_module
from medradar.observatory.ledger import ObservationLedger
from medradar.observatory.records import (
    ENTITY_MAPPED,
    TRACK_MAPPED,
    MappingResult,
    RawRecord,
    utc_now_iso,
)

MAPPING_VERSION = "obs-mapping-v1"
COLLECTOR_VERSION = "test-collector/1.0"
SYNTHETIC_LABEL = "合成测试：前瞻观察登记器机制演示"
SYNTHETIC_NOTE = "合成测试：仅用于验证冻结/评估机制，不代表任何真实世界事件或真实前瞻结果。"
ENTRY_ID = "test-prospective-demo-001"


# --------------------------------------------------------------------- helpers
def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _record(record_id: str, *, source: str = "sec_edgar", revision: int = 1) -> RawRecord:
    return RawRecord(
        source=source,
        source_record_id=record_id,
        record_type="sec_8k",
        title=f"8-K｜Item 8.01（合成测试记录 {record_id} v{revision}）",
        url=f"https://www.sec.gov/Archives/edgar/data/test/{record_id}",
        event_at="2025-01-05",
        event_at_precision="date",
        published_at="2025-01-05T21:00:00+00:00",
        published_at_precision="datetime",
        payload={"accession_number": record_id, "form": "8-K", "revision": revision},
    )


def _mapping(
    entity_id: str = "medtronic", track_id: str = "cardiac_rhythm"
) -> MappingResult:
    return MappingResult(
        entity_id=entity_id,
        entity_status=ENTITY_MAPPED,
        entity_method="sec_cik_exact",
        track_id=track_id,
        track_status=TRACK_MAPPED,
        track_method="product_code",
    )


def _spec(entry_id: str, timeline: types.SimpleNamespace, **overrides):
    spec = {
        "entry_id": entry_id,
        "label_zh": SYNTHETIC_LABEL,
        "hypothesis_zh": "若某企业出现 8-K Item 8.01 修订披露，下一季度会出现可观察的后续披露。",
        "target_event_definition_zh": "SEC 8-K/8-K-A 披露中 Item 8.01 或其他事件条款出现。",
        "baseline_zh": "冻结时 MedRadar 已观察到的该范围披露条数。",
        "evaluation_criteria_zh": "窗口内出现 1 条及以上新观察的候选证据即记为“观察到候选事件”。",
        "window_start": _iso(timeline.window_start),
        "window_end": _iso(timeline.window_end),
        "freeze_at": _iso(timeline.freeze_at),
        "scope": {"source": "sec_edgar"},
        "synthetic": True,
        "note_zh": SYNTHETIC_NOTE,
    }
    spec.update(overrides)
    return spec


@pytest.fixture
def timeline() -> types.SimpleNamespace:
    now = _now()
    return types.SimpleNamespace(
        now=now,
        freeze_at=now - timedelta(days=90),
        window_start=now - timedelta(days=80),
        window_end=now - timedelta(days=50),
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    ledger_path = tmp_path / "observatory.sqlite"
    registry_dir = tmp_path / "prospective"
    monkeypatch.setenv("MEDRADAR_OBSERVATORY_DB", str(ledger_path))
    monkeypatch.setenv("MEDRADAR_PROSPECTIVE_DIR", str(registry_dir))
    ledger = ObservationLedger(ledger_path)
    registry = registry_module.ProspectiveRegistry(registry_dir)
    try:
        yield types.SimpleNamespace(
            ledger=ledger,
            registry=registry,
            registry_dir=registry_dir,
            ledger_path=ledger_path,
            entries_dir=registry_dir / "entries",
        )
    finally:
        ledger.close()


def _observe(env, record_id: str, seen_at: str, *, revision: int = 1, source: str = "sec_edgar",
             mapping: MappingResult | None = None, run_id: str) -> str:
    outcome = env.ledger.record_observation(
        _record(record_id, source=source, revision=revision),
        mapping or _mapping(),
        run_id=run_id,
        collector_version=COLLECTOR_VERSION,
        mapping_version=MAPPING_VERSION,
        seen_at=seen_at,
    )
    return outcome.observation_id


def _evaluation_files(env) -> list[str]:
    if not env.entries_dir.is_dir():
        return []
    return sorted(path.name for path in env.entries_dir.glob("*.evaluation.*.json"))


def _freeze_lifecycle(env, timeline) -> tuple[dict, str]:
    """Freeze the standard synthetic entry after one input observation exists."""
    input_id = _observe(
        env,
        "0001-25-000001",
        _iso(timeline.freeze_at - timedelta(days=5)),
        run_id="run-input",
    )
    spec = _spec(ENTRY_ID, timeline)
    frozen = env.registry.freeze(spec, ledger=env.ledger)
    assert frozen["result"] == "created"
    return frozen, input_id


# ------------------------------------------------------- freeze is write-once
def test_freeze_is_write_once_and_frozen_bytes_survive_later_ledger_writes(env, timeline):
    frozen, input_id = _freeze_lifecycle(env, timeline)
    frozen_path = env.registry.entry_path(ENTRY_ID)
    frozen_bytes = frozen_path.read_bytes()
    frozen_hash = frozen["content_sha256"]
    frozen_evidence = frozen["evidence"]
    assert frozen_evidence["count"] == 1
    assert frozen_evidence["as_of"] == _iso(timeline.freeze_at)
    assert frozen_evidence["items"][0]["observation_id"] == input_id
    assert frozen_evidence["items"][0]["payload_hash"]
    assert frozen_evidence["items"][0]["version_id"]

    # identical protocol re-freeze is idempotent and does not rewrite the file
    duplicate = env.registry.freeze(_spec(ENTRY_ID, timeline), ledger=env.ledger)
    assert duplicate["result"] == "duplicate"
    assert frozen_path.read_bytes() == frozen_bytes

    # later ledger writes: a brand-new observation AND a new version of the input
    new_id = _observe(
        env,
        "0001-25-000002",
        _iso(timeline.freeze_at + timedelta(days=3)),
        run_id="run-new",
    )
    updated_input_id = _observe(
        env,
        "0001-25-000001",
        _iso(timeline.freeze_at + timedelta(days=4)),
        revision=2,
        run_id="run-update",
    )
    assert updated_input_id == input_id
    assert env.ledger.observation_row(input_id)["version_count"] == 2
    assert env.ledger.observation_row(new_id)["first_seen_at"] == _iso(
        timeline.freeze_at + timedelta(days=3)
    )

    # the frozen file is byte-identical and still verifies
    assert frozen_path.read_bytes() == frozen_bytes
    verification = env.registry.verify_frozen(ENTRY_ID)
    assert verification["ok"] is True
    assert verification["content_sha256"] == frozen_hash
    assert verification["recomputed_sha256"] == frozen_hash
    assert verification["evidence_sha256_ok"] is True

    # the recorded point-in-time inputs are unchanged: even the ledger's own
    # snapshot(freeze_at) now excludes both later writes
    reread = json.loads(frozen_path.read_text(encoding="utf-8"))
    assert reread["evidence"] == frozen_evidence
    snapshot_after = env.ledger.snapshot(_iso(timeline.freeze_at))
    assert {item["observation_id"] for item in snapshot_after["items"]} == {input_id}
    assert {item["observation_id"] for item in reread["evidence"]["items"]} == {input_id}

    # and the identity re-freeze still returns the original document
    duplicate_after = env.registry.freeze(_spec(ENTRY_ID, timeline), ledger=env.ledger)
    assert duplicate_after["result"] == "duplicate"
    assert duplicate_after["content_sha256"] == frozen_hash
    assert frozen_path.read_bytes() == frozen_bytes


def test_conflicting_second_freeze_is_rejected(env, timeline):
    frozen, _input_id = _freeze_lifecycle(env, timeline)
    frozen_path = env.registry.entry_path(ENTRY_ID)
    frozen_bytes = frozen_path.read_bytes()

    conflicting = _spec(ENTRY_ID, timeline, hypothesis_zh="被改写后的另一个假设")
    with pytest.raises(registry_module.FrozenDocumentConflict) as excinfo:
        env.registry.freeze(conflicting, ledger=env.ledger)
    assert "只写一次" in str(excinfo.value) or "不可改写" in str(excinfo.value)

    # a narrower window is also a different protocol -> refused
    changed_window = _spec(
        ENTRY_ID, timeline, window_end=_iso(timeline.window_end - timedelta(days=1))
    )
    with pytest.raises(registry_module.FrozenDocumentConflict):
        env.registry.freeze(changed_window, ledger=env.ledger)

    assert frozen_path.read_bytes() == frozen_bytes
    assert env.registry.get_entry(ENTRY_ID)["content_sha256"] == frozen["content_sha256"]


def test_verify_frozen_detects_tampering_and_refuses_evaluation(env, timeline):
    frozen, _input_id = _freeze_lifecycle(env, timeline)
    frozen_path = env.registry.entry_path(ENTRY_ID)

    document = json.loads(frozen_path.read_text(encoding="utf-8"))
    document["hypothesis_zh"] = "被人为改写的假设"
    frozen_path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    verification = env.registry.verify_frozen(ENTRY_ID)
    assert verification["ok"] is False
    assert verification["content_sha256"] == frozen["content_sha256"]
    assert verification["recomputed_sha256"] != frozen["content_sha256"]
    assert "改写" in verification["reason_zh"]

    # evaluation refuses to compute on a rewritten frozen body...
    result = env.registry.evaluate_against_ledger(
        ENTRY_ID, env.ledger, now=_iso(timeline.window_end + timedelta(days=1))
    )
    assert result["status"] == "TAMPERED"
    assert result["evaluated"] is False
    assert _evaluation_files(env) == []

    # ...and a re-freeze cannot "repair" (or overwrite) the document either
    with pytest.raises(registry_module.FrozenDocumentConflict):
        env.registry.freeze(_spec(ENTRY_ID, timeline), ledger=env.ledger)


# ------------------------------------------------------------ evaluation gates
def test_evaluation_before_window_end_is_refused_as_not_due(env, timeline):
    _frozen, _input_id = _freeze_lifecycle(env, timeline)
    before_window_end = _iso(timeline.window_end - timedelta(days=1))

    result = env.registry.evaluate_against_ledger(
        ENTRY_ID, env.ledger, now=before_window_end
    )
    assert result["status"] == "NOT_DUE"
    assert result["evaluated"] is False
    assert result["computed_at"] is None
    assert result["recorded_at"] is None
    assert result["window_end"] == _iso(timeline.window_end)
    assert result["reason_zh"] and "尚未结束" in result["reason_zh"]
    assert result["ledger_counts"]["observations"] == 1
    assert _evaluation_files(env) == []
    assert env.registry.get_entry(ENTRY_ID)["evaluation_count"] == 0

    # a premature result can never be appended by hand either
    with pytest.raises(registry_module.EntryValidationError):
        env.registry.append_evaluation(
            ENTRY_ID, {"status": "MATURED", "computed_at": before_window_end}
        )
    with pytest.raises(registry_module.EntryValidationError):
        env.registry.append_evaluation(
            ENTRY_ID, {"status": "NOT_DUE", "computed_at": _iso(timeline.now)}
        )
    assert _evaluation_files(env) == []


def test_evaluation_counts_only_outcomes_discovered_inside_window(env, timeline):
    freeze_at = _iso(timeline.freeze_at)
    window_start = _iso(timeline.window_start)
    window_end = _iso(timeline.window_end)

    input_id = _observe(
        env, "0001-25-000010", _iso(timeline.freeze_at - timedelta(days=5)), run_id="run-input"
    )
    env.registry.freeze(_spec(ENTRY_ID, timeline), ledger=env.ledger)

    # discovered after the freeze but BEFORE the declared window opens
    pre_window_id = _observe(
        env,
        "0001-25-000011",
        _iso(timeline.freeze_at + timedelta(days=5)),
        run_id="run-pre-window",
    )
    # discovered inside the declared window
    inside_one = _observe(
        env, "0001-25-000012", _iso(timeline.window_start + timedelta(days=5)), run_id="run-in-1"
    )
    inside_two = _observe(
        env, "0001-25-000013", _iso(timeline.window_end - timedelta(days=1)), run_id="run-in-2"
    )
    # a new version of the frozen input discovered inside the window
    _observe(
        env,
        "0001-25-000010",
        _iso(timeline.window_start + timedelta(days=20)),
        revision=2,
        run_id="run-update",
    )
    # discovered AFTER the window closes: must never be counted as an outcome
    after_window_id = _observe(
        env,
        "0001-25-000014",
        _iso(timeline.window_end + timedelta(days=5)),
        run_id="run-after-window",
    )

    evaluated_at = _iso(timeline.window_end + timedelta(days=10))
    result = env.registry.evaluate_against_ledger(ENTRY_ID, env.ledger, now=evaluated_at)

    assert result["status"] == "MATURED"
    assert result["evaluation_seq"] == 1
    assert result["computed_at"] == evaluated_at
    assert result["recorded_at"]  # real wall clock of the append
    assert result["inputs"]["count"] == 1
    assert result["inputs"]["observation_ids"] == [input_id]

    outcome_ids = {item["observation_id"] for item in result["outcomes"]["items"]}
    assert outcome_ids == {inside_one, inside_two}
    assert after_window_id not in outcome_ids
    assert pre_window_id not in outcome_ids
    assert result["outcomes"]["count"] == 2
    assert result["outcomes"]["new_version_count"] == 1
    assert result["outcomes"]["classification"] == "CANDIDATE_EVIDENCE_ONLY"
    assert result["outcomes"]["human_classification_required"] is True
    assert result["pre_window_discoveries"]["count"] == 1

    # the computation moment and the ledger counts at that moment are stated
    assert result["ledger"]["snapshot_as_of"] == evaluated_at
    counts_now = env.ledger.counts()
    assert result["ledger"]["counts"]["observations"] == counts_now["observations"] == 5
    assert result["ledger"]["counts"]["versions"] == counts_now["versions"] == 6
    assert result["ledger"]["window_end_snapshot_as_of"] == window_end
    assert result["window_start"] == window_start
    assert result["freeze_at"] == freeze_at

    # the appendix is on disk and the effective status is derived, not written back
    assert _evaluation_files(env) == [f"{ENTRY_ID}.evaluation.1.json"]
    entry = env.registry.get_entry(ENTRY_ID)
    assert entry["status"] == "MATURED"
    assert entry["evaluation_count"] == 1
    assert entry["frozen_status"] == "EXPERIMENTAL"
    frozen_bytes = env.registry.entry_path(ENTRY_ID).read_bytes()
    assert entry["frozen_verified"] is True

    # a later re-evaluation appends sequence 2 and preserves the first appendix
    later = env.registry.evaluate_against_ledger(
        ENTRY_ID, env.ledger, now=_iso(timeline.window_end + timedelta(days=11))
    )
    assert later["evaluation_seq"] == 2
    assert later["supersedes"] == 1
    assert _evaluation_files(env) == [
        f"{ENTRY_ID}.evaluation.1.json",
        f"{ENTRY_ID}.evaluation.2.json",
    ]
    assert env.registry.entry_path(ENTRY_ID).read_bytes() == frozen_bytes


# --------------------------------------------------------------- scope + states
def test_retraction_appends_status_file_without_touching_frozen_document(env, timeline):
    frozen, _input_id = _freeze_lifecycle(env, timeline)
    frozen_path = env.registry.entry_path(ENTRY_ID)
    frozen_bytes = frozen_path.read_bytes()

    # derived statuses can never be appended by hand; a reason is mandatory
    for status in ("ACTIVE", "DUE", "MATURED"):
        with pytest.raises(registry_module.EntryValidationError):
            env.registry.append_status(ENTRY_ID, status, reason_zh="不应允许派生状态")
    with pytest.raises(registry_module.EntryValidationError):
        env.registry.append_status(ENTRY_ID, "RETRACTED", reason_zh="")
    assert not list(env.entries_dir.glob("*.status.*.json"))

    retraction = env.registry.append_status(
        ENTRY_ID,
        "RETRACTED",
        reason_zh="研究者在观察到数据问题后撤回该假设。",
    )
    assert retraction["status"] == "RETRACTED"
    assert retraction["status_seq"] == 1
    assert retraction["frozen_content_sha256"] == frozen["content_sha256"]

    # the frozen body is untouched; the retraction is a new immutable appendix
    assert frozen_path.read_bytes() == frozen_bytes
    assert env.registry.verify_frozen(ENTRY_ID)["ok"] is True
    entry = env.registry.get_entry(ENTRY_ID)
    assert entry["status"] == "RETRACTED"
    assert entry["frozen_status"] == "EXPERIMENTAL"
    assert entry["retracted"] is True
    assert "数据问题" in entry["retraction_reason_zh"]
    assert sorted(path.name for path in env.entries_dir.glob("*.status.*.json")) == [
        f"{ENTRY_ID}.status.1.json"
    ]

    from medradar.product import prospective as product_prospective

    row = product_prospective.overview()["entries"][0]
    assert row["status"] == "RETRACTED"
    assert row["retracted"] is True


def test_freeze_scope_filters_source_entity_and_track(env):
    now = _now()
    seen_at = _iso(now - timedelta(days=10))

    _observe(env, "scope-a", seen_at, run_id="run-scope")
    _observe(env, "scope-b", seen_at, run_id="run-scope")
    _observe(env, "scope-c", seen_at, mapping=MappingResult(), run_id="run-scope")
    _observe(env, "scope-d", seen_at, source="ctgov", run_id="run-scope")

    # freezes happen AFTER the observations: the ledger's mapping rows are stamped
    # with the real wall clock, and the registry compares at second granularity.
    freeze_at = utc_now_iso()
    window_end = _iso(now + timedelta(days=10))

    common = {
        "label_zh": SYNTHETIC_LABEL,
        "hypothesis_zh": "范围过滤测试",
        "target_event_definition_zh": "测试事件",
        "baseline_zh": "测试基线",
        "evaluation_criteria_zh": "测试判据",
        "window_start": freeze_at,
        "window_end": window_end,
        "freeze_at": freeze_at,
        "synthetic": True,
        "note_zh": SYNTHETIC_NOTE,
    }
    everything = env.registry.freeze({"entry_id": "scope-all", **common}, ledger=env.ledger)
    entity_scoped = env.registry.freeze(
        {
            "entry_id": "scope-entity",
            **common,
            "scope": {"source": "sec_edgar", "entity_id": "medtronic"},
        },
        ledger=env.ledger,
    )
    track_scoped = env.registry.freeze(
        {"entry_id": "scope-track", **common, "scope": {"track_id": "cardiac_rhythm"}},
        ledger=env.ledger,
    )

    assert everything["evidence"]["count"] == 4
    assert {
        item["source_record_id"] for item in entity_scoped["evidence"]["items"]
    } == {"scope-a", "scope-b"}
    assert {
        item["source_record_id"] for item in track_scoped["evidence"]["items"]
    } == {"scope-a", "scope-b", "scope-d"}

    # freeze_at == window_start -> the window is open -> ACTIVE (derived status)
    assert env.registry.get_entry("scope-all")["status"] == "ACTIVE"

    # a window that has not opened yet keeps the honest default EXPERIMENTAL
    future = env.registry.freeze(
        {
            "entry_id": "scope-future",
            **common,
            "window_start": _iso(now + timedelta(days=1)),
            "window_end": _iso(now + timedelta(days=11)),
        },
        ledger=env.ledger,
    )
    assert future["status"] == "EXPERIMENTAL"
    assert env.registry.get_entry("scope-future")["status"] == "EXPERIMENTAL"

    # a window that already ended without an evaluation is DUE
    due = env.registry.freeze(
        {
            "entry_id": "scope-due",
            **common,
            "freeze_at": _iso(now - timedelta(days=40)),
            "window_start": _iso(now - timedelta(days=30)),
            "window_end": _iso(now - timedelta(days=10)),
        },
        ledger=env.ledger,
    )
    assert due["window_end"] == _iso(now - timedelta(days=10))
    assert env.registry.get_entry("scope-due")["status"] == "DUE"


# -------------------------------------------------------------------- synthetic
def test_synthetic_entry_is_labelled_and_not_surfaced_as_evidence(env, timeline):
    frozen, _input_id = _freeze_lifecycle(env, timeline)
    assert frozen["synthetic"] is True
    assert registry_module.SYNTHETIC_MARKER in frozen["label_zh"]
    assert registry_module.SYNTHETIC_MARKER in frozen["note_zh"]

    entry = env.registry.get_entry(ENTRY_ID)
    assert entry["synthetic"] is True
    assert registry_module.SYNTHETIC_MARKER in entry["label_zh"]

    # the product view keeps it labelled synthetic and never calls it evidence
    from medradar.product import prospective as product_prospective

    overview = product_prospective.overview()
    assert overview["empty"] is False
    assert overview["registry"]["synthetic_count"] == 1
    assert overview["registry"]["real_entry_count"] == 0
    assert overview["validation"]["validated"] is False
    assert overview["validation"]["calibrated"] is False
    row = overview["entries"][0]
    assert row["synthetic"] is True
    assert row["evidence_status"] == "SYNTHETIC"
    assert registry_module.SYNTHETIC_MARKER in row["synthetic_badge_zh"]
    assert registry_module.SYNTHETIC_MARKER in row["label_zh"]

    # an evaluation of a synthetic entry carries the marker in its honesty block
    result = env.registry.evaluate_against_ledger(
        ENTRY_ID, env.ledger, now=_iso(timeline.window_end + timedelta(days=1))
    )
    assert result["synthetic"] is True
    assert any(registry_module.SYNTHETIC_MARKER in item for item in result["honesty_zh"])

    # a synthetic entry without the marker is refused outright
    with pytest.raises(registry_module.EntryValidationError):
        env.registry.freeze(
            _spec(
                "test-unlabelled-001",
                timeline,
                label_zh="看起来像真实研究的假设",
                note_zh="没有合成测试标记",
            ),
            ledger=env.ledger,
        )


# -------------------------------------------------------------------------- API
def test_lab_prospective_api_shapes_and_existing_routes(env, timeline):
    pytest.importorskip("fastapi", reason="install the product extra: pip install -e .[web]")
    pytest.importorskip("httpx", reason="install the dev extra for TestClient")
    from fastapi.testclient import TestClient

    from medradar.web.app import app

    client = TestClient(app)

    # ---- honest empty state (registry dir does not exist yet)
    empty = client.get("/api/lab/prospective")
    assert empty.status_code == 200
    empty_payload = empty.json()
    assert empty_payload["empty"] is True
    assert empty_payload["entries"] == []
    assert empty_payload["registry"]["entry_count"] == 0
    assert empty_payload["registry"]["exists"] is False
    assert empty_payload["registry"]["path"]
    assert empty_payload["validation"]["validated"] is False
    assert empty_payload["empty_zh"]
    assert client.get("/api/lab/prospective/does-not-exist").status_code == 404

    # ---- freeze one synthetic entry, then read both shapes
    _frozen, input_id = _freeze_lifecycle(env, timeline)
    _observe(
        env,
        "0001-25-000020",
        _iso(timeline.window_start + timedelta(days=5)),
        run_id="run-api-outcome",
    )
    evaluated = env.registry.evaluate_against_ledger(
        ENTRY_ID, env.ledger, now=_iso(timeline.window_end + timedelta(days=1))
    )
    assert evaluated["status"] == "MATURED"

    listing = client.get("/api/lab/prospective")
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["empty"] is False
    assert payload["registry"]["entry_count"] == 1
    assert payload["registry"]["status_counts"]["MATURED"] == 1
    assert payload["registry"]["synthetic_count"] == 1
    assert payload["registry"]["matured_count"] == 1
    row = payload["entries"][0]
    assert row["entry_id"] == ENTRY_ID
    assert row["status"] == "MATURED"
    assert row["status_label_zh"]
    assert row["synthetic"] is True
    assert row["evidence_status"] == "SYNTHETIC"
    assert row["frozen_evidence_count"] == 1
    assert row["frozen_evidence_as_of"] == _iso(timeline.freeze_at)
    assert row["evaluation_count"] == 1
    assert row["evaluation_history"][0]["outcomes_count"] == 1
    assert row["latest_evaluation"]["snapshot_as_of"] == _iso(
        timeline.window_end + timedelta(days=1)
    )
    assert row["frozen_verified"] is True

    detail = client.get(f"/api/lab/prospective/{ENTRY_ID}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["entry"]["entry_id"] == ENTRY_ID
    assert detail_payload["entry"]["synthetic"] is True
    assert detail_payload["entry"]["evidence"]["count"] == 1
    assert detail_payload["entry"]["evidence"]["items"][0]["observation_id"] == input_id
    assert detail_payload["verification"]["ok"] is True
    assert detail_payload["evaluation_count"] == 1
    assert detail_payload["evaluations"][0]["outcomes"]["count"] == 1
    assert detail_payload["validation"]["validated"] is False
    assert detail_payload["honesty_zh"]

    # ---- existing Research Lab endpoints keep working
    lab = client.get("/api/lab")
    assert lab.status_code == 200
    lab_payload = lab.json()
    assert lab_payload["studies"]
    assert "prospective" in lab_payload
    summary = lab_payload["prospective"]
    assert summary["entry_count"] == 1
    assert summary["synthetic_count"] == 1
    assert summary["matured_count"] == 1
    assert summary["status_counts"]["MATURED"] == 1
    assert summary["registry_path"]
    assert summary["notice_zh"]

    study_detail = client.get("/api/lab/C43-hist-v1")
    assert study_detail.status_code == 200
    assert study_detail.json()["id"] == "C43-hist-v1"
    assert client.get("/api/lab/nope").status_code == 404
