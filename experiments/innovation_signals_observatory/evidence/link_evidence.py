"""Cross-source evidence linking for the recruitment lane (Phase 4 · WP2c).

What this module does
---------------------
It takes the T0 job-posting snapshot, classifies every posting into the mission's
job-function vocabulary and the **existing** device technology tracks
(``config/tracks_device.json``) using the deterministic A-arm classifier
(``medradar.recruitment.taxonomy.classify_rules``), aggregates postings into
``(company × track)`` cells, and then asks one question per cell:

    *Is there independent evidence, from a source that is not the job posting,
    that satisfies the four pre-declared linking rules in PROTOCOL.md §6?*

It answers with a verdict from the closed vocabulary in PROTOCOL.md §5 and records
**why** each candidate evidence item was accepted or rejected. It never upgrades a
hiring observation into a statement about strategy, intent or an R&D programme.

The four pre-declared linking rules (this round's operationalisation of §6)
----------------------------------------------------------------------------
R1 ``SAME_ENTITY`` — the independent record's ``company_key`` equals the posting
   cell's focus-company key, and that key is a member of
   ``config/universe_v1.json["focus_companies"]``. Exact string equality only; no
   fuzzy, substring or alias matching is performed here (the upstream resolution
   already happened in the evidence warehouse and is not re-derived).
R2 ``SAME_TRACK`` — the independent record's ``track_id`` equals the cell's track
   id, and the track is one of the pre-existing ``config/tracks_device.json``
   tracks. No new track is invented.
R3 ``TIME_WINDOW`` — the independent record's ``event_date`` lies in
   ``[anchor − HIRE_EVIDENCE_MAX_LOOKBACK_MONTHS, anchor]``, where ``anchor`` is
   the earliest ``first_seen_at`` (our wall clock) of the cell's postings, and its
   ``as_of`` (when the warehouse knew the record) is not later than the anchor.
   The window constant is declared once, below, and printed into the artifact.
R4 ``RESOLVABLE_IDENTIFIER`` — the linked record carries a resolvable external
   identifier: an FDA ``K``/``P`` number or recall number for the warehouse rows,
   an ``NCT`` number for ClinicalTrials.gov records. If no identifier can be
   recovered, the item is *not* linkable.

A candidate is ``INDEPENDENTLY_SUPPORTED`` only when at least one item passes all
four rules **and** the item is of a supporting kind (a regulatory authorisation or
a registered clinical trial). A device *recall* in the same track is recorded as
**contrary context** but is explicitly *not* treated as support or as proof of the
opposite: post-market trouble is not evidence that a company is or is not doing
R&D. ``CONTRADICTED`` therefore requires a pre-declared cessation/withdrawal
signal, which the current warehouse contains none of — that is recorded, not
papered over.

Verdict vocabulary (closed; PROTOCOL.md §5)
-------------------------------------------
``CANDIDATE_TECHNICAL_HIRING_SIGNAL`` · ``INDEPENDENTLY_SUPPORTED`` ·
``NO_INDEPENDENT_SUPPORT`` · ``CONTRADICTED`` · ``UNKNOWN``

Two fields use it, and this is deliberate:

* ``hiring_signal_verdict`` — stage 1, hiring only: a cell with ≥
  ``MIN_DISTINCT_POSTINGS_FOR_CANDIDATE`` distinct posting ids and ≥1 R&D-class
  posting is ``CANDIDATE_TECHNICAL_HIRING_SIGNAL``; otherwise ``UNKNOWN``.
* ``verdict`` — stage 2, the evidence judgement for a candidate. For cells below
  the candidate threshold no verdict is issued (``UNKNOWN``), because "there is
  independent evidence about this track" is not a statement about a hiring signal
  that does not exist.

``CONTRADICTED`` is reachable in code (``_is_contradiction``) but cannot fire on
this snapshot because no FDA event kind carries a cessation/withdrawal signal; that
is recorded in ``limitations``.

Usage
-----
    python experiments/innovation_signals_observatory/evidence/link_evidence.py

Reads (auto-selected):
  * ``.../results/2026-11-04/jobs_medtronic.jsonl`` if it has ≥500 postings
    (authoritative), else ``.../preliminary/jobs_medtronic_preliminary40.jsonl``;
  * the read-only evidence warehouse ``D:\\DEPPSKK\\medradar\\data\\dev_device.sqlite``
    (opened with ``mode=ro`` and ``PRAGMA query_only=1``);
  * optional pre-fetched ClinicalTrials.gov JSON under
    ``.../results/2026-11-04/_httpcache_evidence/ctgov/``. No live network call is
    made by this module; the fetcher is a separate, bounded script.

Writes (only inside this work package's write scope):
  * ``.../results/2026-11-04/evidence_linking.json`` (machine-checkable);
  * ``.../results/2026-11-04/evidence_linking.md`` (short human summary).

Determinism: no wall-clock value is used except the artifact ``generated_at`` and
the snapshot's own recorded ``first_seen_at`` / ``fetched_at``; all ordering is by
explicit sort keys. Re-running against the same inputs reproduces the verdicts.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

# --------------------------------------------------------------------- versions
PIPELINE_VERSION = "evidence_linking/1.0.0"
SCHEMA_VERSION = "evidence-linking-v1"

#: Path anchors. ``parents[3]`` = repository root this file lives in.
REPO_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_DIR = REPO_ROOT / "experiments" / "innovation_signals_observatory"
RESULTS_DIR = EXPERIMENT_DIR / "results" / "2026-11-04"
CONFIG_DIR = REPO_ROOT / "config"
DEFAULT_EVIDENCE_DB = Path(r"D:\DEPPSKK\medradar\data\dev_device.sqlite")
DEFAULT_CTGOV_CACHE = RESULTS_DIR / "_httpcache_evidence" / "ctgov"

# --------------------------------------------------- pre-declared rule constants
#: PROTOCOL.md §6.3: independent evidence may not predate the hiring observation
#: by more than this many months. Declared here, printed into the artifact, and
#: never adjusted per cell.
HIRE_EVIDENCE_MAX_LOOKBACK_MONTHS = 24
#: Forward-only evidence: an independent record may not be *later* than the hiring
#: observation it is supposed to support (no look-ahead).
HIRE_EVIDENCE_MAX_LEAD_DAYS = 0
#: PROTOCOL.md §5: a CANDIDATE signal needs multiple independent posting ids.
MIN_DISTINCT_POSTINGS_FOR_CANDIDATE = 2
#: Lead's escalation floor: fewer distinct posting ids than this is not worth a
#: human review even if it technically clears the candidate threshold.
MIN_DISTINCT_POSTINGS_FOR_HUMAN_REVIEW = 3

#: The mission's function vocabulary (must not be extended here).
FUNCTION_CLASSES = (
    "CORE_R&D",
    "CLINICAL_R&D",
    "PRODUCT_ENGINEERING",
    "ALGORITHM_SOFTWARE",
    "HARDWARE_SYSTEMS",
    "MANUFACTURING_PROCESS",
    "QUALITY_REGULATORY",
    "SALES_ADMIN_OTHER",
    "UNCLASSIFIED",
)
#: Classes that describe technology creation, used for the candidate gate. The
#: classifier's own gate says a QUALITY_REGULATORY / MANUFACTURING_PROCESS posting
#: carries the product area it supports, not an R&D direction, so those two are
#: technical but not R&D and do not by themselves make a technical-hiring signal.
RD_FUNCTIONS = (
    "CORE_R&D",
    "CLINICAL_R&D",
    "PRODUCT_ENGINEERING",
    "ALGORITHM_SOFTWARE",
    "HARDWARE_SYSTEMS",
)
TECHNICAL_FUNCTIONS = RD_FUNCTIONS + ("MANUFACTURING_PROCESS", "QUALITY_REGULATORY")
NON_TECHNICAL_FUNCTIONS = ("SALES_ADMIN_OTHER", "UNCLASSIFIED")

#: Closed verdict vocabulary (PROTOCOL.md §5). Nothing outside this tuple may be
#: written into a ``verdict`` / ``hiring_signal_verdict`` field.
VERDICTS = (
    "CANDIDATE_TECHNICAL_HIRING_SIGNAL",
    "INDEPENDENTLY_SUPPORTED",
    "NO_INDEPENDENT_SUPPORT",
    "CONTRADICTED",
    "UNKNOWN",
)
HIRING_SIGNAL_VERDICTS = ("CANDIDATE_TECHNICAL_HIRING_SIGNAL", "UNKNOWN")

#: Per-cell record caps keep the artifact small (<3 MB) while total counts remain exact.
MAX_LINKED_ITEMS_PER_CELL = 8
MAX_CONTEXT_ITEMS_PER_CELL = 5
MAX_REJECTED_ITEMS_PER_CELL = 12
#: A track with at least this many company events inside the 24-month window is a
#: high-volume line of business for the firm; one more approval there is routine
#: activity, not a discriminating signal. Used only for interpretation, never to
#: change a verdict.
ROUTINE_VOLUME_THRESHOLD_EVENTS_IN_WINDOW = 20
#: Specificity classes for a linked independent-evidence item. Only used to
#: interpret an INDEPENDENTLY_SUPPORTED verdict; the verdict itself follows the
#: four pre-declared rules.
SPECIFICITY_HIGH = "HIGH_DEVICE_CLEARANCE_OR_TRIAL"
SPECIFICITY_MEDIUM = "MEDIUM_DESIGN_OR_POSTAPPROVAL_CHANGE"
SPECIFICITY_LOW = "LOW_ADMINISTRATIVE_SUPPLEMENT"
SPECIFICITY_CONTEXT = "POST_MARKET_CONTEXT"
SPECIFICITY_UNKNOWN = "UNKNOWN_SPECIFICITY"
HIGH_SPECIFICITY_CLASSES = (
    "HIGH_DEVICE_CLEARANCE",
    "HIGH_CLINICAL_TRIAL",
)
MEDIUM_SPECIFICITY_CLASSES = (
    "MEDIUM_DESIGN_CHANGE",
    "MEDIUM_POSTAPPROVAL_STUDY",
)
HIGH_SPECIFICITY_EVIDENCE = (
    "HIGH_DEVICE_CLEARANCE",
    "HIGH_CLINICAL_TRIAL",
)

#: Direction-novelty vocabulary. This is the field that carries the scientific
#: claim; ``INDEPENDENTLY_SUPPORTED`` alone only says "the company is active in this
#: track", which is trivial for a large incumbent.
DIRECTION_NOVELTY_VOCABULARY = (
    "NEW_DIRECTION_CANDIDATE",
    "RECENT_ACTIVITY",
    "ESTABLISHED_DIRECTION",
    "NO_BASELINE_DATA",
)
#: The recent window within which "new" activity must appear.
NOVELTY_RECENT_MONTHS = 12
#: Minimum observed baseline (months of evidence-source coverage before the recent
#: window) required before a novelty call is made at all.
NOVELTY_MIN_BASELINE_MONTHS = 6
#: A track is ESTABLISHED when activity spans at least this many months **and** has
#: at least this many events in the observed coverage **and** is present in both the
#: baseline and the recent window. "Continuous multi-year presence" is measured by
#: span + event count, not by requiring a filing in every calendar month: FDA filing
#: rates are sparse, so a monthly-grid rule would mislabel real product lines as
#: "recent" (observed on the 994-posting snapshot: 11 vs 12 months for a track whose
#: activity actually spans 24 months).
NOVELTY_ESTABLISHED_MIN_SPAN_MONTHS = 18
NOVELTY_ESTABLISHED_MIN_EVENTS = 6

#: Evidence roles. Only ``SUPPORTING_*`` can make a candidate
#: ``INDEPENDENTLY_SUPPORTED``; ``CONTRARY_CONTEXT_POST_MARKET`` is recorded and
#: interpreted explicitly as *not* a contradiction.
SUPPORTING_ROLES = (
    "SUPPORTING_REGULATORY_AUTHORISATION",
    "SUPPORTING_CLINICAL_TRIAL",
    "SUPPORTING_PUBLICATION",
)
CONTRARY_CONTEXT_ROLE = "CONTRARY_CONTEXT_POST_MARKET"

#: Presentation-only zh labels for the five mandated companies (a label, not a
#: roster; identity always comes from config/universe_v1.json focus_companies).
COMPANY_DISPLAY_ZH = {
    "medtronic": "美敦力",
    "ge_healthcare": "GE 医疗",
    "philips": "飞利浦",
    "draeger": "德尔格",
    "mindray": "迈瑞",
}

#: The four pre-declared rules, recorded verbatim in the artifact.
LINKING_RULES = (
    {
        "id": "R1_SAME_ENTITY",
        "text_zh": "独立证据的企业键必须与岗位所属重点企业键完全相等，且该键属于 config/universe_v1.json 的 focus_companies；不做模糊匹配。",
        "text_en": "Independent record's company_key must equal the posting cell's focus-company key exactly; that key must be in config/universe_v1.json focus_companies. No fuzzy matching.",
    },
    {
        "id": "R2_SAME_TRACK",
        "text_zh": "独立证据的 track_id 必须等于岗位单元的 track_id，且该 track 是 config/tracks_device.json 中既有的 track；不新造分类。",
        "text_en": "Independent record's track_id must equal the cell's track id, and the track must be one of the pre-existing config/tracks_device.json tracks. No new taxonomy.",
    },
    {
        "id": "R3_TIME_WINDOW",
        "text_zh": f"独立证据的事件日期必须落在 [最早岗位观察日 − {HIRE_EVIDENCE_MAX_LOOKBACK_MONTHS} 个月, 最早岗位观察日] 内，且其 as_of 不得晚于该观察日。窗口常量写死在代码中。",
        "text_en": f"Independent record's event_date must lie in [earliest posting first_seen_at − {HIRE_EVIDENCE_MAX_LOOKBACK_MONTHS} months, earliest posting first_seen_at], and its as_of must not postdate that anchor. The window is a code constant.",
    },
    {
        "id": "R4_RESOLVABLE_IDENTIFIER",
        "text_zh": "被关联的每条证据都必须带有可回查的外部标识（FDA K 号 / P 号 / 召回编号，或 NCT 号）。无法取得标识的条目不得计入支持。",
        "text_en": "Every linked item must carry a resolvable external identifier (FDA K number / P number / recall number, or NCT number). Items without one are not counted as support.",
    },
)

#: Assertions that must never appear inside a verdict-bearing field. Some of these
#: phrases are legitimate in a *negated* disclaimer outside the machine fields, so
#: the guard is applied to verdict fields only (see ``_assert_no_conclusion``).
CONCLUSION_FORBIDDEN_PATTERNS = (
    re.compile(r"\bis developing\b", re.I),
    re.compile(r"\bare developing\b", re.I),
    re.compile(r"\bhas begun developing\b", re.I),
    re.compile(r"\bis pivoting\b", re.I),
    re.compile(r"\bstrategy shift\b", re.I),
    re.compile(r"\bR&D programme\b", re.I),
    re.compile(r"\bresearch programme\b", re.I),
    re.compile(r"\bproves that\b", re.I),
    re.compile(r"\bconfirms that\b", re.I),
)

# --------------------------------------------------------------------- helpers
def utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path, *, limit: int | None = None) -> str:
    h = hashlib.sha256()
    remaining = limit
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1 << 20)
            if not chunk:
                break
            if remaining is not None:
                if remaining <= 0:
                    break
                chunk = chunk[:remaining]
                remaining -= len(chunk)
            h.update(chunk)
    return h.hexdigest()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def month_span(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def _truncate(text: Any, limit: int) -> str:
    value = "" if text is None else str(text)
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8")
    return len(text.encode("utf-8"))


# ----------------------------------------------------------------- config load
def load_tracks(config_dir: Path = CONFIG_DIR) -> dict[str, dict[str, Any]]:
    doc = _read_json(config_dir / "tracks_device.json")
    return {
        str(track["id"]): {
            "track_id": str(track["id"]),
            "name_zh": track.get("name_zh"),
            "name_en": track.get("name_en"),
            "domain": track.get("domain"),
            "domain_zh": track.get("domain_zh"),
            "category": track.get("category"),
            "keywords": [str(k) for k in (track.get("keywords") or [])],
            "frontier_keywords": [str(k) for k in (track.get("frontier_keywords") or [])],
        }
        for track in doc.get("tracks", [])
    }


def load_focus_companies(config_dir: Path = CONFIG_DIR) -> dict[str, dict[str, Any]]:
    doc = _read_json(config_dir / "universe_v1.json")
    focus = doc.get("focus_companies") or {}
    return {
        str(key): {
            "company_key": str(key),
            "display_name": value.get("display_name"),
            "display_name_zh": COMPANY_DISPLAY_ZH.get(str(key)),
            "aliases": [str(a) for a in (value.get("aliases") or [])],
            "canonical_entity_key": value.get("canonical_entity_key"),
            "roster_status": value.get("roster_status"),
        }
        for key, value in focus.items()
    }


# ------------------------------------------------------------- classification
def make_taxonomy_classifier() -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Return the A-arm classifier bound to ``medradar.recruitment.taxonomy``.

    This function is the **single swap point**: if the classifier module ever
    changes its interface, only this adapter changes. The pipeline never contains
    a competing rule set.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from medradar.recruitment import taxonomy  # local import: keeps --help cheap

    def classify(job: Mapping[str, Any]) -> dict[str, Any]:
        raw = taxonomy.classify_rules(job)
        confidence = raw.get("confidence_basis") or {}
        function_evidence = raw.get("function_evidence") or {}
        track_evidence = raw.get("track_evidence") or {}
        function_spans = [
            {
                "field": span.get("field"),
                "quote": span.get("quote") or span.get("text"),
                "rule": span.get("rule"),
                "target": span.get("target"),
                "context": span.get("context"),
            }
            for span in (function_evidence.get("spans") or [])
        ]
        track_spans = [
            {
                "field": span.get("field"),
                "quote": span.get("quote") or span.get("text"),
                "rule": span.get("rule"),
                "target": span.get("target"),
                "keyword": span.get("keyword"),
                "keyword_kind": span.get("keyword_kind"),
                "context": span.get("context"),
            }
            for span in (track_evidence.get("spans") or [])
        ]
        return {
            "classifier_source": "medradar.recruitment.taxonomy.classify_rules",
            "classifier_arm": raw.get("arm"),
            "rules_version": raw.get("rules_version"),
            "function_map_version": raw.get("function_map_version"),
            "function_map_fingerprint": raw.get("function_map_fingerprint"),
            "taxonomy_regime": raw.get("taxonomy"),
            "function_class": raw.get("function_class"),
            "function_decision_basis": function_evidence.get("decision_basis"),
            "function_rule_strength": (confidence.get("function") or {}).get("rule_strength"),
            "confidence_statement": confidence.get("statement"),
            "track_id": raw.get("track_id"),
            "track_status": track_evidence.get("track_status"),
            "track_reason": track_evidence.get("reason"),
            "track_candidate": track_evidence.get("candidate"),
            "function_spans": function_spans,
            "track_spans": track_spans,
            "unclassified_reason": raw.get("unclassified_reason"),
        }

    return classify


def _classifier_meta(
    classify: Callable[[Mapping[str, Any]], dict[str, Any]], postings: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Record honestly which classifier produced the labels."""
    versions: dict[str, Any] = {}
    status = "RULES_UNAVAILABLE_FALLBACK"
    try:
        if classify is not None:
            sample = classify(postings[0]) if postings else {}
            versions = {
                "arm": sample.get("classifier_arm"),
                "rules_version": sample.get("rules_version"),
                "function_map_version": sample.get("function_map_version"),
                "function_map_fingerprint": sample.get("function_map_fingerprint"),
                "taxonomy": sample.get("taxonomy_regime"),
                "classifier_source": sample.get("classifier_source"),
            }
            if sample.get("classifier_source", "").startswith("medradar."):
                status = f"RULES_ARM_A_{sample.get('rules_version')}"
    except Exception as exc:  # pragma: no cover - defensive only
        versions = {"error": f"{type(exc).__name__}: {exc}"}
    return {"classifier_status": status, **versions}


# ------------------------------------------------------------------- snapshot
def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def resolve_snapshot(results_dir: Path = RESULTS_DIR) -> dict[str, Any]:
    """Pick the authoritative snapshot when it exists; else the preliminary 40."""
    authoritative = results_dir / "jobs_medtronic.jsonl"
    collection = results_dir / "collection_medtronic.json"
    preliminary = results_dir / "preliminary" / "jobs_medtronic_preliminary40.jsonl"
    prelim_report = results_dir / "preliminary" / "collection_medtronic_preliminary40.json"
    report: dict[str, Any] | None = None
    if collection.exists():
        try:
            report = _read_json(collection)
        except json.JSONDecodeError:
            report = None
    n_auth = count_lines(authoritative)
    n_prelim = count_lines(preliminary)
    n_report = None
    if report:
        n_report = (report.get("availability") or {}).get("n")
    if n_auth >= 500 and (n_report is None or n_report >= 500):
        return {
            "path": authoritative,
            "role": "AUTHORITATIVE",
            "n_lines": n_auth,
            "collection_report": report,
            "selection_note": "authoritative snapshot (>=500 postings and collection report n>=500)",
        }
    if n_auth >= 100 and n_auth > n_prelim:
        # The collector's declared posting ceiling may be below 500; a fuller file is
        # still authoritative for this round, and the artifact says it is partial.
        return {
            "path": authoritative,
            "role": "AUTHORITATIVE_PARTIAL",
            "n_lines": n_auth,
            "collection_report": report,
            "selection_note": (
                f"authoritative file has {n_auth} postings (< the 500-posting confirmation floor); "
                "used because it is strictly larger than the preliminary copy"
            ),
        }
    if preliminary.exists():
        prelim = _read_json(prelim_report) if prelim_report.exists() else None
        return {
            "path": preliminary,
            "role": "PRELIMINARY_40",
            "n_lines": count_lines(preliminary),
            "collection_report": prelim,
            "authoritative_lines_seen": n_auth,
            "selection_note": (
                "preliminary bounded snapshot; the authoritative file is used automatically once "
                "jobs_medtronic.jsonl has >=500 postings and collection_medtronic.json reports n>=500"
            ),
        }
    raise FileNotFoundError(f"no job snapshot found under {results_dir}")


def load_jobs(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def dedupe_postings(
    postings: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop offset-pagination duplicate rows; the count of lines is not the population.

    The Workday listing can return the same posting twice if the result set shifts
    mid-run. A posting id is the source-stable identity, so two rows with the same
    id are one posting. The dropped rows are recorded, not silently discarded.
    """
    seen: dict[str, int] = {}
    unique: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for posting in postings:
        posting_id = str(posting.get("posting_id") or "")
        if not posting_id:
            unique.append(dict(posting))
            continue
        if posting_id in seen:
            duplicates.append(
                {
                    "posting_id": posting_id,
                    "job_title": posting.get("job_title"),
                    "first_seen_at": posting.get("first_seen_at"),
                    "source_url": posting.get("source_url"),
                    "reason": "same posting_id returned more than once in the snapshot",
                }
            )
            continue
        seen[posting_id] = len(unique)
        unique.append(dict(posting))
    return unique, duplicates


# --------------------------------------------------------------- cell building
def _posting_summary(posting: Mapping[str, Any], classified: Mapping[str, Any]) -> dict[str, Any]:
    track_quotes: list[dict[str, Any]] = []
    seen_quotes: set[tuple[Any, Any, Any]] = set()
    for span in (classified.get("track_spans") or []):
        if str(span.get("target")) != str(classified.get("track_id")):
            continue  # audit evidence for other candidate tracks is not this track's quote
        key = (span.get("field"), span.get("quote"), span.get("keyword"))
        if key in seen_quotes:
            continue
        seen_quotes.add(key)
        track_quotes.append(
            {
                "field": span.get("field"),
                "quote": _truncate(span.get("quote"), 160),
                "keyword": span.get("keyword"),
                "kind": span.get("keyword_kind"),
            }
        )
        if len(track_quotes) >= 4:
            break
    function_quotes: list[dict[str, Any]] = []
    for span in (classified.get("function_spans") or [])[:2]:
        function_quotes.append({"field": span.get("field"), "quote": _truncate(span.get("quote"), 120)})
    return {
        "posting_id": posting.get("posting_id"),
        "job_title": posting.get("job_title"),
        "job_location": posting.get("job_location"),
        "function_class": classified.get("function_class"),
        "function_decision_basis": classified.get("function_decision_basis"),
        "function_rule_strength": classified.get("function_rule_strength"),
        "track_status": classified.get("track_status"),
        "track_reason": classified.get("track_reason"),
        "track_quotes": track_quotes,
        "function_quotes": function_quotes,
        "source_posted_at": posting.get("source_posted_at"),
        "source_posted_quality": posting.get("source_posted_quality"),
        "first_seen_at": posting.get("first_seen_at"),
        "source_url": posting.get("source_url"),
    }


def build_cells(
    postings: Sequence[Mapping[str, Any]],
    classify: Callable[[Mapping[str, Any]], dict[str, Any]],
    tracks: Mapping[str, Mapping[str, Any]],
    focus: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate postings into (company × track) cells. Pure and deterministic."""
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    function_counts: Counter[str] = Counter()
    track_status_counts: Counter[str] = Counter()
    unclassified: list[dict[str, Any]] = []
    labels: list[tuple[Mapping[str, Any], dict[str, Any]]] = []

    for posting in postings:
        classified = classify(posting)
        labels.append((posting, classified))
        function_class = classified.get("function_class")
        function_counts[str(function_class)] += 1
        track_status = classified.get("track_status")
        track_status_counts[str(track_status)] += 1
        company_key = str(posting.get("company_key"))
        track_id = classified.get("track_id")
        if not track_id:
            candidate = classified.get("track_candidate") or {}
            unclassified.append(
                {
                    "posting_id": posting.get("posting_id"),
                    "job_title": posting.get("job_title"),
                    "function_class": function_class,
                    "track_status": track_status,
                    "track_status_reason": classified.get("track_reason"),
                    "ambient_track_candidate": candidate.get("track_id") if isinstance(candidate, Mapping) else None,
                    "first_seen_at": posting.get("first_seen_at"),
                    "source_url": posting.get("source_url"),
                }
            )
            continue
        key = (company_key, str(track_id))
        cell = cells.get(key)
        if cell is None:
            track = tracks.get(str(track_id), {})
            company = focus.get(company_key, {})
            cell = {
                "company_key": company_key,
                "company_display": company.get("display_name"),
                "company_display_zh": company.get("display_name_zh"),
                "company_in_focus_universe": company_key in focus,
                "track_id": str(track_id),
                "track_name_zh": track.get("name_zh"),
                "track_name_en": track.get("name_en"),
                "track_domain": track.get("domain"),
                "track_in_config_taxonomy": str(track_id) in tracks,
                "postings": [],
            }
            cells[key] = cell
        cell["postings"].append(_posting_summary(posting, classified))

    out: list[dict[str, Any]] = []
    for (company_key, track_id) in sorted(cells):
        cell = cells[(company_key, track_id)]
        postings_in_cell = cell["postings"]
        distinct_ids = sorted({str(p.get("posting_id")) for p in postings_in_cell if p.get("posting_id")})
        first_seen = sorted(
            p["first_seen_at"] for p in postings_in_cell if p.get("first_seen_at")
        )
        source_posted = sorted(
            p["source_posted_at"] for p in postings_in_cell if p.get("source_posted_at")
        )
        function_hist = Counter(str(p.get("function_class")) for p in postings_in_cell)
        n_rd = sum(1 for p in postings_in_cell if p.get("function_class") in RD_FUNCTIONS)
        n_technical = sum(1 for p in postings_in_cell if p.get("function_class") in TECHNICAL_FUNCTIONS)
        n_title_track_hits = sum(
            1
            for p in postings_in_cell
            if any(q.get("field") == "job_title" for q in (p.get("track_quotes") or []))
        )
        cell.update(
            {
                "n_postings": len(postings_in_cell),
                "n_distinct_posting_ids": len(distinct_ids),
                "distinct_posting_ids": distinct_ids,
                "function_classes": dict(sorted(function_hist.items())),
                "n_rd_postings": n_rd,
                "n_technical_postings": n_technical,
                # Track evidence quality: a title keyword hit names the occupation/track;
                # a description-only hit may be incidental prose ("artificial intelligence"
                # in a privacy policy paragraph). This rate is reported, never corrected away.
                "track_evidence_quality": {
                    "n_title_keyword_hits": n_title_track_hits,
                    "n_description_only": len(postings_in_cell) - n_title_track_hits,
                    "description_only_rate": round(
                        (len(postings_in_cell) - n_title_track_hits) / len(postings_in_cell), 4
                    )
                    if postings_in_cell
                    else 0.0,
                },
                "first_seen_min": first_seen[0] if first_seen else None,
                "first_seen_max": first_seen[-1] if first_seen else None,
                "source_posted_min": source_posted[0] if source_posted else None,
                "source_posted_max": source_posted[-1] if source_posted else None,
            }
        )
        # candidate gate (single declared rule, recorded with its arithmetic)
        is_candidate = (
            len(distinct_ids) >= MIN_DISTINCT_POSTINGS_FOR_CANDIDATE and n_rd >= 1
        )
        cell["is_candidate"] = is_candidate
        cell["candidate_rule"] = {
            "min_distinct_posting_ids": MIN_DISTINCT_POSTINGS_FOR_CANDIDATE,
            "distinct_posting_ids": len(distinct_ids),
            "rd_postings_required": 1,
            "rd_postings": n_rd,
            "passed": is_candidate,
        }
        cell["human_review_recommended"] = bool(
            is_candidate and len(distinct_ids) >= MIN_DISTINCT_POSTINGS_FOR_HUMAN_REVIEW
        )
        cell["human_review_threshold_distinct_posting_ids"] = MIN_DISTINCT_POSTINGS_FOR_HUMAN_REVIEW
        out.append(cell)

    out.sort(key=lambda c: (-c["n_distinct_posting_ids"], c["track_id"], c["company_key"]))
    posting_rows = [
        {
            "posting_id": posting.get("posting_id"),
            "company_key": posting.get("company_key"),
            "job_title": posting.get("job_title"),
            "function_class": classified.get("function_class"),
            "track_id": classified.get("track_id"),
            "track_status": classified.get("track_status"),
            "first_seen_at": posting.get("first_seen_at"),
            "source_posted_at": posting.get("source_posted_at"),
        }
        for posting, classified in labels
    ]
    return {
        "cells": out,
        "posting_labels": posting_rows,
        "unclassified_postings": unclassified,
        "function_class_counts": dict(sorted(function_counts.items())),
        "track_status_counts": dict(sorted(track_status_counts.items())),
    }


# ---------------------------------------------------------------- evidence DB
EVENT_COLUMNS = (
    "event_id",
    "source",
    "kind",
    "event_date",
    "as_of",
    "company_key",
    "track_id",
    "product_code",
    "title",
    "summary",
    "url",
    "payload",
    "fetched_at",
)

_ID_PATTERNS = {
    "510k": re.compile(r"\bK\d{6}\b"),
    "pma": re.compile(r"\bP\d{6}\b"),
    "device_recall": re.compile(r"\bZ-\d{4}-\d{3,4}\b"),
}
_RECALL_RES_RE = re.compile(r"[?&]id=(\d{4,})")


def open_evidence_db(path: Path) -> sqlite3.Connection:
    """Open the evidence warehouse strictly read-only.

    ``mode=ro`` prevents file writes at the SQLite layer; ``PRAGMA query_only=1``
    makes an accidental write fail loudly as well.
    """
    if not path.exists():
        raise FileNotFoundError(f"evidence DB not found: {path}")
    uri = "file:" + str(path).replace("\\", "/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = 1")
    return conn


def safe_payload(raw: Any) -> tuple[dict[str, Any] | None, bool]:
    if raw is None:
        return None, True
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, False
    return (parsed if isinstance(parsed, dict) else None), True


def resolve_identifier(
    row: Mapping[str, Any], payload: Mapping[str, Any] | None, payload_ok: bool
) -> tuple[str | None, str, str | None]:
    """Return ``(identifier, source, granularity)`` for one evidence row.

    Payload first (structured field), then a verbatim regex over url/title/summary.
    The dev warehouse truncates many payloads at ~4 KB, so the URL fallback is
    load-bearing; ``probe`` reports how often it was needed.
    """
    kind = str(row.get("kind") or "")
    if payload_ok and payload:
        if kind == "510k" and payload.get("k_number"):
            return str(payload["k_number"]), "payload.k_number", "510k"
        if kind == "pma" and payload.get("pma_number"):
            number = str(payload["pma_number"])
            supplement = payload.get("supplement_number")
            if supplement:
                return f"{number}/{supplement}", "payload.pma_number+supplement_number", "pma_supplement"
            return number, "payload.pma_number", "pma"
        if kind == "device_recall":
            if payload.get("product_res_number"):
                return str(payload["product_res_number"]), "payload.product_res_number", "recall"
            if payload.get("res_event_number"):
                return f"RES-{payload['res_event_number']}", "payload.res_event_number", "recall_event"
    blob = " ".join(str(row.get(field) or "") for field in ("url", "title", "summary"))
    # A truncated payload (the dev warehouse truncates at ~4 KB) can still carry the
    # identifier near its start; regex the raw text before falling back to url fields.
    raw_payload = str(row.get("payload") or "")
    sources = [("raw_payload_regex", raw_payload), ("url_or_title_regex", blob)]
    for source_name, text in sources:
        if not text:
            continue
        pattern = _ID_PATTERNS.get(kind)
        if pattern is not None:
            match = pattern.search(text)
            if match:
                return match.group(0), source_name, {"510k": "510k", "pma": "pma", "device_recall": "recall"}[kind]
        if kind == "device_recall":
            match = _RECALL_RES_RE.search(str(row.get("url") or ""))
            if match and source_name == "url_or_title_regex":
                return f"RES-{match.group(1)}", "url_recall_id_regex", "recall_event"
    return None, "unresolved", None


def support_role_for_kind(kind: str) -> str | None:
    if kind in ("510k", "pma"):
        return "SUPPORTING_REGULATORY_AUTHORISATION"
    if kind == "device_recall":
        return CONTRARY_CONTEXT_ROLE
    return None


def _is_contradiction(kind: str, payload: Mapping[str, Any] | None) -> bool:
    """Pre-declared contradiction gate.

    A contradiction would be independent evidence that the company *ceased or
    withdrew* the technology direction. No FDA event kind in this snapshot carries
    that signal: a recall is post-market trouble, not cessation. Should a payload
    ever carry an explicit withdrawal/deletion decision, this returns True; on the
    current snapshot it cannot fire, and the artifact says so.
    """
    if payload:
        decision = str(payload.get("decision_code") or "").upper()
        if decision in {"WITHDRAWN", "WDRAWN", "DELETED", "WITHDRAWAL"}:
            return True
        supplement_reason = str(payload.get("supplement_reason") or "").lower()
        if "withdraw" in supplement_reason:
            return True
    return False


def probe_evidence_db(conn: sqlite3.Connection, path: Path) -> dict[str, Any]:
    """Measure the warehouse instead of trusting its description."""
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
    ]
    n_events = int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
    min_date, max_date, min_as_of, max_as_of = conn.execute(
        "SELECT MIN(event_date), MAX(event_date), MIN(as_of), MAX(as_of) FROM events"
    ).fetchone()
    by_source = {
        f"{row[0]}|{row[1]}": int(row[2])
        for row in conn.execute(
            "SELECT source, kind, COUNT(*) FROM events GROUP BY source, kind ORDER BY source, kind"
        )
    }
    focus_counts = {
        row[0]: int(row[1])
        for row in conn.execute(
            "SELECT company_key, COUNT(*) FROM events WHERE company_key IS NOT NULL GROUP BY company_key"
        )
    }
    focus_company_tracks: dict[str, dict[str, Any]] = {}
    for company_key in ("medtronic", "ge_healthcare", "philips", "draeger", "mindray"):
        track_rows = conn.execute(
            "SELECT track_id, COUNT(*) FROM events "
            "WHERE company_key = ? AND track_id IS NOT NULL GROUP BY track_id",
            (company_key,),
        ).fetchall()
        focus_company_tracks[company_key] = {
            "n_events_with_track": sum(int(row[1]) for row in track_rows),
            "n_tracks_with_events": len(track_rows),
            "tracks": {row[0]: int(row[1]) for row in track_rows},
        }
    db_tracks = [
        {"id": row[0], "name_zh": row[1], "name_en": row[2], "category": row[3]}
        for row in conn.execute("SELECT id, name_zh, name_en, category FROM tracks ORDER BY id")
    ]
    payload_bad: Counter[str] = Counter()
    id_resolvable: Counter[str] = Counter()
    id_sources: Counter[str] = Counter()
    n_by_kind: Counter[str] = Counter()
    for row in conn.execute("SELECT kind, url, title, summary, payload FROM events"):
        kind = str(row["kind"])
        n_by_kind[kind] += 1
        payload, payload_ok = safe_payload(row["payload"])
        if not payload_ok:
            payload_bad[kind] += 1
        identifier, source, _ = resolve_identifier(dict(row), payload, payload_ok)
        if identifier:
            id_resolvable[kind] += 1
            id_sources[source] += 1
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "tables": tables,
        "n_events": n_events,
        "measured_event_date_min": min_date,
        "measured_event_date_max": max_date,
        "measured_as_of_min": min_as_of,
        "measured_as_of_max": max_as_of,
        "by_source_kind": by_source,
        "focus_company_event_counts": focus_counts,
        "focus_company_tracks": focus_company_tracks,
        "db_tracks": db_tracks,
        "payload_parse_failures_by_kind": dict(sorted(payload_bad.items())),
        "payload_parse_failures_total": int(sum(payload_bad.values())),
        "identifier_resolvable_by_kind": dict(sorted(id_resolvable.items())),
        "identifier_resolved_from": dict(sorted(id_sources.items())),
        "events_by_kind": dict(sorted(n_by_kind.items())),
        "access_mode": "sqlite3 URI mode=ro + PRAGMA query_only=1 (read-only; no writes to data/)",
        "qa_note": (
            "The task brief described this warehouse as 2016-11..2026-10; the measured window is "
            "reported above and is short (a recent-window dev DB). Payloads are truncated at about "
            "4 KB for a large fraction of rows, so identifier extraction falls back to the url/title "
            "columns. Both facts are measured, not assumed."
        ),
    }


def fetch_company_events(
    conn: sqlite3.Connection, company_key: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sql = (
        f"SELECT {', '.join(EVENT_COLUMNS)} FROM events "
        "WHERE company_key = ? ORDER BY event_date, event_id"
    )
    rows = [dict(row) for row in conn.execute(sql, (company_key,))]
    return rows, {"id": f"company_events:{company_key}", "source": "dev_device.sqlite", "sql": sql,
                  "params": [company_key], "row_count": len(rows)}


def _pma_supplement_reason(
    row: Mapping[str, Any], payload: Mapping[str, Any] | None, payload_ok: bool
) -> str | None:
    if payload_ok and payload and payload.get("supplement_reason"):
        return str(payload["supplement_reason"])
    raw = str(row.get("payload") or "")
    match = re.search(r'"supplement_reason"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    if match:
        try:
            return json.loads('"' + match.group(1) + '"')
        except json.JSONDecodeError:
            return match.group(1)
    return None


def evidence_specificity(kind: str, supplement_reason: str | None) -> str:
    """Classify how specific a linked independent-evidence item is.

    This does **not** change the four-rule verdict; it stops a routine
    manufacturing-site PMA supplement from being read as evidence of a technology
    direction. FDA PMA supplements are dominated by process/location changes.
    """
    if kind == "510k":
        return "HIGH_DEVICE_CLEARANCE"
    if kind == "device_recall":
        return SPECIFICITY_CONTEXT
    if kind == "pma":
        reason = (supplement_reason or "").lower()
        if any(token in reason for token in ("change design", "components", "specifications", "material")):
            return "MEDIUM_DESIGN_CHANGE"
        if "postapproval study" in reason or reason.endswith(" pas"):
            return "MEDIUM_POSTAPPROVAL_STUDY"
        if "process change" in reason:
            return "LOW_MANUFACTURING_PROCESS_CHANGE"
        if "location change" in reason:
            return "LOW_FACILITY_LOCATION_CHANGE"
        if "labeling change" in reason:
            return "LOW_LABELING_CHANGE"
        return SPECIFICITY_UNKNOWN
    return SPECIFICITY_UNKNOWN


def evaluate_db_item(
    row: Mapping[str, Any],
    cell: Mapping[str, Any],
    window: Mapping[str, Any],
    focus: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate the four pre-declared rules for one warehouse record."""
    payload, payload_ok = safe_payload(row.get("payload"))
    identifier, identifier_source, identifier_granularity = resolve_identifier(row, payload, payload_ok)
    supplement_reason = _pma_supplement_reason(row, payload, payload_ok)
    specificity = evidence_specificity(str(row.get("kind") or ""), supplement_reason)
    company_match = (
        str(row.get("company_key")) == cell["company_key"]
        and str(cell["company_key"]) in focus
    )
    track_match = (
        str(row.get("track_id")) == cell["track_id"]
        and bool(cell.get("track_in_config_taxonomy"))
    )
    event_date = parse_date(row.get("event_date"))
    as_of = parse_date(row.get("as_of"))
    window_start = parse_date(window["window_start"])
    window_end = parse_date(window["window_end"])
    in_window = bool(event_date and window_start and window_end and window_start <= event_date <= window_end)
    point_in_time = bool(as_of and window_end and as_of <= window_end)
    time_ok = in_window and point_in_time
    identifier_ok = identifier is not None
    rules = {
        "R1_SAME_ENTITY": company_match,
        "R2_SAME_TRACK": track_match,
        "R3_TIME_WINDOW": time_ok,
        "R4_RESOLVABLE_IDENTIFIER": identifier_ok,
    }
    failed = [rule_id for rule_id, passed in rules.items() if not passed]
    support_role = support_role_for_kind(str(row.get("kind")))
    contradiction = _is_contradiction(str(row.get("kind")), payload)
    return {
        "source": "dev_device.sqlite",
        "record_id": row.get("event_id"),
        "kind": row.get("kind"),
        "event_date": row.get("event_date"),
        "as_of": row.get("as_of"),
        "company_key": row.get("company_key"),
        "track_id": row.get("track_id"),
        "product_code": row.get("product_code"),
        "title": _truncate(row.get("title"), 180),
        "url": row.get("url"),
        "identifier": identifier,
        "identifier_source": identifier_source,
        "identifier_granularity": identifier_granularity,
        "payload_parse_ok": payload_ok,
        "pma_supplement_reason": supplement_reason,
        "evidence_specificity": specificity,
        "rules": rules,
        "failed_rules": failed,
        "linkable": all(rules.values()),
        "support_role": support_role,
        "is_contradiction": contradiction,
        "in_window": in_window,
        "point_in_time_ok": point_in_time,
    }


def derive_direction_novelty(
    same_track_rows: Sequence[Mapping[str, Any]],
    window: Mapping[str, Any],
    source_coverage_start: date | None,
) -> dict[str, Any]:
    """Derive the direction-novelty field from the temporal profile of the evidence.

    The scientific question is not "does the company have activity in this track"
    (a large incumbent does, in most tracks) but "is the observed hiring pointing at
    a direction that is new or recently active". That can only be judged against a
    baseline, so the baseline is declared here and its **observed coverage** is
    reported: if the evidence source cannot see far enough back, the honest answer
    is ``NO_BASELINE_DATA``, not "new".

    Everything below is computed from the same company × track rows that were used
    for the rule evaluation; nothing is asserted without the counts.
    """
    anchor = parse_date(window.get("window_end"))
    dates = sorted(d for d in (parse_date(row.get("event_date")) for row in same_track_rows) if d)
    months_with_events = sorted({(d.year, d.month) for d in dates})
    profile: dict[str, Any] = {
        "vocabulary": list(DIRECTION_NOVELTY_VOCABULARY),
        "anchor_date": anchor.isoformat() if anchor else None,
        "source_coverage_start": source_coverage_start.isoformat() if source_coverage_start else None,
        "n_events_in_track_total": len(dates),
        "first_event_date": dates[0].isoformat() if dates else None,
        "last_event_date": dates[-1].isoformat() if dates else None,
        "distinct_months_with_events": len(months_with_events),
        "event_counts_by_kind": dict(
            sorted(Counter(str(row.get("kind")) for row in same_track_rows).items())
        ),
        "n_events_in_hiring_window_24m": sum(
            1 for d in dates if anchor and parse_date(window.get("window_start")) and parse_date(window["window_start"]) <= d <= anchor
        ),
        "recent_window_months": NOVELTY_RECENT_MONTHS,
        "min_baseline_months_required": NOVELTY_MIN_BASELINE_MONTHS,
        "established_min_span_months": NOVELTY_ESTABLISHED_MIN_SPAN_MONTHS,
        "established_min_events": NOVELTY_ESTABLISHED_MIN_EVENTS,
        "baseline_window": None,
        "baseline_window_months_observed": 0.0,
        "n_events_before_recent_window": 0,
        "n_events_recent_window": 0,
        "recent_activity_absent": False,
        "direction_novelty": "NO_BASELINE_DATA",
        "reason_zh": "",
    }
    if anchor is None:
        profile["reason_zh"] = "缺少招聘观察锚点日期，无法计算方向新颖度。"
        return profile
    recent_start = add_months(anchor, -NOVELTY_RECENT_MONTHS)
    coverage_start = source_coverage_start or (dates[0] if dates else None)
    if coverage_start is None:
        profile["reason_zh"] = "证据来源没有任何可用日期，无法计算方向新颖度。"
        return profile
    baseline_start = max(coverage_start, add_months(anchor, -60))
    baseline_end = recent_start
    observed_months = max(0.0, (baseline_end - baseline_start).days / 30.44)
    n_baseline = sum(1 for d in dates if baseline_start <= d < baseline_end)
    n_recent = sum(1 for d in dates if recent_start <= d <= anchor)
    profile.update(
        {
            "recent_window_start": recent_start.isoformat(),
            "baseline_window": [baseline_start.isoformat(), (baseline_end).isoformat()],
            "baseline_window_months_observed": round(observed_months, 1),
            "n_events_before_recent_window": n_baseline,
            "n_events_recent_window": n_recent,
            "recent_activity_absent": n_recent == 0,
        }
    )
    if observed_months < NOVELTY_MIN_BASELINE_MONTHS:
        profile["direction_novelty"] = "NO_BASELINE_DATA"
        profile["reason_zh"] = (
            f"来源只能看到 {observed_months:.1f} 个月的基线（要求 ≥ {NOVELTY_MIN_BASELINE_MONTHS}），"
            "无法区分「新方向」与「早已存在但来源看不到」。"
        )
    elif n_baseline == 0 and n_recent == 0:
        profile["direction_novelty"] = "NO_BASELINE_DATA"
        profile["reason_zh"] = "该 track 在证据来源可见期内没有任何记录，无法谈方向新颖度。"
    elif n_baseline == 0 and n_recent > 0:
        profile["direction_novelty"] = "NEW_DIRECTION_CANDIDATE"
        profile["reason_zh"] = (
            f"在来源可见的 {observed_months:.1f} 个月基线窗内该 track 无任何事件，"
            f"而最近 {NOVELTY_RECENT_MONTHS} 个月有 {n_recent} 条；这是「相对可见基线为新」的候选，"
            "不是「企业对该公司全新」的证明（来源看不到更早历史）。"
        )
    elif n_baseline > 0:
        span_months = month_span(dates[0], dates[-1]) if len(dates) > 1 else 0
        if (
            span_months >= NOVELTY_ESTABLISHED_MIN_SPAN_MONTHS
            and len(dates) >= NOVELTY_ESTABLISHED_MIN_EVENTS
            and n_recent > 0
        ):
            profile["direction_novelty"] = "ESTABLISHED_DIRECTION"
            profile["reason_zh"] = (
                f"该 track 在可见期内跨 {span_months} 个月、共 {len(dates)} 条事件"
                f"（基线窗 {n_baseline} 条、最近 {NOVELTY_RECENT_MONTHS} 个月 {n_recent} 条）；"
                "对该企业属于既有方向，招聘更可能是业务常态而非新方向。"
            )
        else:
            profile["direction_novelty"] = "RECENT_ACTIVITY"
            profile["reason_zh"] = (
                f"该 track 在基线窗有 {n_baseline} 条、最近 {NOVELTY_RECENT_MONTHS} 个月有 {n_recent} 条，"
                f"但活动只跨 {span_months} 个月 / 共 {len(dates)} 条（未达「跨 "
                f"{NOVELTY_ESTABLISHED_MIN_SPAN_MONTHS} 个月且 ≥ {NOVELTY_ESTABLISHED_MIN_EVENTS} 条」），"
                "只能说近期有活动，不能判定为持续既有方向，也不能判定为新方向。"
            )
    return profile


def load_ctgov_cache(cache_dir: Path) -> dict[str, Any]:
    """Load pre-fetched ClinicalTrials.gov responses (offline; no network here)."""
    if not cache_dir.exists():
        return {"status": "NOT_QUERIED", "cache_dir": str(cache_dir), "files": [], "requests": [],
                "by_track": {}, "note": "no pre-fetched ClinicalTrials.gov cache present; external trials marked NOT_QUERIED"}
    files = sorted(file for file in cache_dir.glob("*.json") if not file.name.startswith("_"))
    by_track: dict[str, list[dict[str, Any]]] = {}
    requests: list[dict[str, Any]] = []
    for file in files:
        try:
            doc = _read_json(file)
        except json.JSONDecodeError:
            requests.append({"file": file.name, "error": "invalid json"})
            continue
        request = doc.get("request") or {}
        track_id = str(request.get("track_id") or "")
        requests.append(
            {
                "file": file.name,
                "url": request.get("url"),
                "track_id": track_id,
                "fetched_at": request.get("fetched_at"),
                "status": doc.get("status"),
                "n_studies": len(((doc.get("body") or {}).get("studies")) or []),
                "sha256": sha256_file(file),
            }
        )
        for study in ((doc.get("body") or {}).get("studies") or []):
            record = _parse_ctgov_study(study)
            if record.get("nct_id"):
                by_track.setdefault(track_id, []).append(record)
    return {
        "status": "QUERIED_CACHE_LOADED" if requests else "CACHE_DIR_EMPTY",
        "cache_dir": str(cache_dir),
        "files": [f.name for f in files],
        "requests": requests,
        "by_track": by_track,
        "note": "raw responses are cached outside git; this pipeline only reads the cache",
    }


def _parse_ctgov_study(study: Mapping[str, Any]) -> dict[str, Any]:
    protocol = (study.__getitem__("protocolSection") if "protocolSection" in study else {}) or {}
    identification = protocol.get("identificationModule") or {}
    status = protocol.get("statusModule") or {}
    sponsor = protocol.get("sponsorCollaboratorsModule") or {}
    conditions = protocol.get("conditionsModule") or {}
    interventions = protocol.get("armsInterventionsModule") or {}
    description = protocol.get("descriptionModule") or {}
    start = status.get("startDateStruct") or {}
    first_post = status.get("studyFirstPostDateStruct") or {}
    lead_sponsor = sponsor.get("leadSponsor") or {}
    return {
        "nct_id": identification.get("nctId"),
        "brief_title": identification.get("briefTitle"),
        "overall_status": status.get("overallStatus"),
        "start_date": start.get("date"),
        "study_first_post_date": first_post.get("date"),
        "lead_sponsor": lead_sponsor.get("name"),
        "conditions": [str(c) for c in (conditions.get("conditions") or [])],
        "interventions": [
            str(item.get("name")) for item in (interventions.get("interventions") or []) if item.get("name")
        ],
        "brief_summary": _truncate(description.get("briefSummary"), 1200),
    }


def _phrase_in_text(text_upper: str, phrase: str) -> bool:
    tokens = [re.escape(part) for part in phrase.upper().split()]
    if not tokens:
        return False
    pattern = r"(?<![0-9A-Z])" + r"\s+".join(tokens) + r"s?(?![0-9A-Z])"
    return re.search(pattern, text_upper) is not None


def evaluate_ctgov_item(
    record: Mapping[str, Any],
    cell: Mapping[str, Any],
    track: Mapping[str, Any],
    focus: Mapping[str, Mapping[str, Any]],
    window: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate the four pre-declared rules for one trial record."""
    sponsor_name = str(record.get("lead_sponsor") or "")
    sponsor_upper = sponsor_name.upper()
    alias_hits = sorted(
        {
            alias
            for alias in (focus.get(cell["company_key"], {}) or {}).get("aliases", [])
            if _phrase_in_text(sponsor_upper, alias)
        }
    )
    company_match = bool(alias_hits) and cell["company_key"] in focus
    trial_text = " ".join(
        [str(record.get("brief_title") or ""), *record.get("conditions", []),
         *record.get("interventions", []), str(record.get("brief_summary") or "")]
    ).upper()
    keyword_hits = sorted(
        {
            keyword
            for keyword in list(track.get("keywords") or []) + list(track.get("frontier_keywords") or [])
            if _phrase_in_text(trial_text, keyword)
        }
    )
    track_match = bool(keyword_hits) and bool(cell.get("track_in_config_taxonomy"))
    event_date = parse_date(record.get("start_date")) or parse_date(record.get("study_first_post_date"))
    window_start = parse_date(window["window_start"])
    window_end = parse_date(window["window_end"])
    in_window = bool(event_date and window_start and window_end and window_start <= event_date <= window_end)
    first_post = parse_date(record.get("study_first_post_date"))
    point_in_time = bool(first_post and window_end and first_post <= window_end)
    time_ok = in_window and point_in_time
    nct_id = record.get("nct_id")
    identifier_ok = bool(nct_id and re.fullmatch(r"NCT\d{8}", str(nct_id)))
    rules = {
        "R1_SAME_ENTITY": company_match,
        "R2_SAME_TRACK": track_match,
        "R3_TIME_WINDOW": time_ok,
        "R4_RESOLVABLE_IDENTIFIER": identifier_ok,
    }
    failed = [rule_id for rule_id, passed in rules.items() if not passed]
    return {
        "source": "clinicaltrials.gov_api_v2",
        "record_id": nct_id,
        "kind": "clinical_trial",
        "event_date": (parse_date(record.get("start_date")) or parse_date(record.get("study_first_post_date")) or "").isoformat()
        if (record.get("start_date") or record.get("study_first_post_date")) else None,
        "event_date_field": "startDateStruct" if record.get("start_date") else "studyFirstPostDateStruct",
        "first_post_date": record.get("study_first_post_date"),
        "overall_status": record.get("overall_status"),
        "lead_sponsor": sponsor_name,
        "title": _truncate(record.get("brief_title"), 180),
        "conditions": record.get("conditions", [])[:6],
        "interventions": record.get("interventions", [])[:6],
        "identifier": nct_id,
        "identifier_source": "protocolSection.identificationModule.nctId",
        "identifier_granularity": "nct",
        "evidence_specificity": "HIGH_CLINICAL_TRIAL",
        "entity_alias_hits": alias_hits,
        "track_keyword_hits": keyword_hits,
        "rules": rules,
        "failed_rules": failed,
        "linkable": all(rules.values()),
        "support_role": "SUPPORTING_CLINICAL_TRIAL",
        "is_contradiction": False,
        "in_window": in_window,
        "point_in_time_ok": point_in_time,
    }


# ------------------------------------------------------------- evidence rollup
def _cell_window(cell: Mapping[str, Any]) -> dict[str, Any]:
    anchor_raw = cell.get("first_seen_min") or cell.get("source_posted_max")
    anchor = parse_date(anchor_raw)
    if anchor is None:
        return {"anchor_date": None, "window_start": None, "window_end": None,
                "anchor_source": "unavailable", "lookback_months": HIRE_EVIDENCE_MAX_LOOKBACK_MONTHS}
    window_start = add_months(anchor, -HIRE_EVIDENCE_MAX_LOOKBACK_MONTHS)
    return {
        "anchor_date": anchor.isoformat(),
        "window_start": window_start.isoformat(),
        "window_end": anchor.isoformat(),
        "anchor_source": "earliest first_seen_at of the cell's postings (our wall clock)",
        "anchor_raw": anchor_raw,
        "lookback_months": HIRE_EVIDENCE_MAX_LOOKBACK_MONTHS,
    }


def evaluate_cell_evidence(
    cell: dict[str, Any],
    company_events: Sequence[Mapping[str, Any]],
    tracks: Mapping[str, Mapping[str, Any]],
    focus: Mapping[str, Mapping[str, Any]],
    db_tracks: Sequence[Mapping[str, Any]],
    ctgov: Mapping[str, Any],
    track_exists_query: Mapping[str, Any] | None = None,
    source_coverage_start: date | None = None,
) -> dict[str, Any]:
    window = _cell_window(cell)
    cell["hiring_window"] = window
    track = tracks.get(cell["track_id"], {})
    cell["track_in_evidence_source"] = any(t["id"] == cell["track_id"] for t in db_tracks)
    same_track_rows = [row for row in company_events if str(row.get("track_id")) == cell["track_id"]]
    direction_novelty = derive_direction_novelty(same_track_rows, window, source_coverage_start)
    cell["direction_novelty"] = direction_novelty

    if not cell["is_candidate"]:
        # Context only: count what the warehouse holds for this company+track, but
        # do not run the rule engine or issue an evidence verdict.
        return {
            "status": "NOT_EVALUATED_BELOW_CANDIDATE_THRESHOLD",
            "note": "cell is not a CANDIDATE_TECHNICAL_HIRING_SIGNAL; no independent-evidence verdict is issued",
            "context_rows_company": len(company_events),
            "context_rows_same_track": len(same_track_rows),
            "direction_novelty": direction_novelty,
            "queries": [{"id": f"track_exists:{cell['track_id']}", **(track_exists_query or {})}] if track_exists_query else [],
            "linked": [],
            "rejected": [],
            "contrary_context": [],
            "failed_rule_counts": {},
            "external": {"status": ctgov.get("status"), "n_considered": 0, "linked": [], "rejected": [], "requests": []},
        }

    evaluated = [evaluate_db_item(row, cell, window, focus) for row in company_events]
    same_track = [item for item in evaluated if item["rules"]["R2_SAME_TRACK"]]
    same_track_in_window = [item for item in same_track if item["in_window"]]
    linked_support_all = [
        item for item in evaluated if item["linkable"] and item["support_role"] in SUPPORTING_ROLES
    ]
    linked_contrary_context_all = [
        item for item in evaluated if item["linkable"] and item["support_role"] == CONTRARY_CONTEXT_ROLE
    ]
    contradiction_items_all = [item for item in evaluated if item["linkable"] and item["is_contradiction"]]

    def _recent(items: Iterable[Mapping[str, Any]], cap: int) -> list[dict[str, Any]]:
        ordered = sorted(
            items, key=lambda item: (str(item.get("event_date") or ""), str(item.get("record_id") or "")), reverse=True
        )
        return [dict(item) for item in ordered[:cap]]

    failed_rule_counts: Counter[str] = Counter()
    for item in evaluated:
        for rule_id in item["failed_rules"]:
            failed_rule_counts[rule_id] += 1
    failed_by_rule_examples: dict[str, list[dict[str, Any]]] = {}
    for rule_id in [rule["id"] for rule in LINKING_RULES]:
        examples = [
            {
                "record_id": item["record_id"],
                "kind": item["kind"],
                "event_date": item["event_date"],
                "title": item["title"],
                "failed_rules": item["failed_rules"],
            }
            for item in evaluated
            if rule_id in item["failed_rules"] and item["rules"]["R2_SAME_TRACK"]
        ][:3]
        if examples:
            failed_by_rule_examples[rule_id] = examples

    # External (ClinicalTrials.gov) evidence for this track, from the offline cache.
    ct_records = ctgov.get("by_track", {}).get(cell["track_id"], []) if ctgov.get("status") == "QUERIED_CACHE_LOADED" else []
    ct_evaluated = [evaluate_ctgov_item(record, cell, track, focus, window) for record in ct_records]
    ct_linked_all = [item for item in ct_evaluated if item["linkable"]]
    ct_requests = [r for r in ctgov.get("requests", []) if str(r.get("track_id")) == cell["track_id"]]
    specificity_counts = Counter(item["evidence_specificity"] for item in linked_support_all)
    n_high_specificity = sum(
        count for specificity, count in specificity_counts.items() if specificity in HIGH_SPECIFICITY_EVIDENCE
    ) + len(ct_linked_all)
    n_medium_specificity = sum(
        count for specificity, count in specificity_counts.items() if specificity in MEDIUM_SPECIFICITY_CLASSES
    )

    return {
        "status": "EVALUATED",
        "queries": [{"id": f"track_exists:{cell['track_id']}", **(track_exists_query or {})}] if track_exists_query else [],
        "direction_novelty": direction_novelty,
        "support_specificity_counts": dict(sorted(specificity_counts.items())),
        "n_high_specificity_support": n_high_specificity,
        "n_medium_specificity_support": n_medium_specificity,
        "n_company_events_considered": len(evaluated),
        "n_same_track_rows": len(same_track),
        "n_same_track_in_window": len(same_track_in_window),
        "n_other_track_rows": len(evaluated) - len(same_track),
        "n_linked_support_total": len(linked_support_all),
        "n_contrary_context_total": len(linked_contrary_context_all),
        "n_contradiction_total": len(contradiction_items_all),
        "linked": _recent(linked_support_all, MAX_LINKED_ITEMS_PER_CELL),
        "contrary_context": _recent(linked_contrary_context_all, MAX_CONTEXT_ITEMS_PER_CELL),
        "contradiction_items": _recent(contradiction_items_all, MAX_CONTEXT_ITEMS_PER_CELL),
        "rejected": [
            {
                "record_id": item["record_id"],
                "kind": item["kind"],
                "event_date": item["event_date"],
                "title": item["title"],
                "identifier": item["identifier"],
                "failed_rules": item["failed_rules"],
            }
            for item in sorted(
                (candidate for candidate in evaluated if not candidate["linkable"]),
                key=lambda candidate: (not candidate["rules"]["R2_SAME_TRACK"], str(candidate["record_id"] or "")),
            )
        ][:MAX_REJECTED_ITEMS_PER_CELL],
        "failed_rule_counts": dict(sorted(failed_rule_counts.items())),
        "failed_rule_examples": failed_by_rule_examples,
        "external": {
            "status": ctgov.get("status"),
            "n_considered": len(ct_evaluated),
            "n_linked_total": len(ct_linked_all),
            "linked": _recent(ct_linked_all, MAX_LINKED_ITEMS_PER_CELL),
            "rejected": [
                {
                    "record_id": item["record_id"],
                    "event_date": item["event_date"],
                    "lead_sponsor": item["lead_sponsor"],
                    "failed_rules": item["failed_rules"],
                }
                for item in ct_evaluated
                if not item["linkable"]
            ][:MAX_CONTEXT_ITEMS_PER_CELL],
            "requests": ct_requests,
        },
    }


def assign_verdict(cell: dict[str, Any]) -> dict[str, Any]:
    """Stage-1 hiring signal and stage-2 evidence verdict, from the closed vocabulary."""
    if cell["is_candidate"]:
        cell["hiring_signal_verdict"] = "CANDIDATE_TECHNICAL_HIRING_SIGNAL"
    else:
        cell["hiring_signal_verdict"] = "UNKNOWN"

    evidence = cell.get("evidence") or {}
    if not cell["is_candidate"]:
        code = (
            "BELOW_CANDIDATE_THRESHOLD"
            if cell["n_distinct_posting_ids"] < MIN_DISTINCT_POSTINGS_FOR_CANDIDATE
            else "NO_RD_POSTING_IN_CELL"
        )
        detail_zh = {
            "BELOW_CANDIDATE_THRESHOLD": (
                f"同一 track 只有 {cell['n_distinct_posting_ids']} 个独立岗位 ID（候选门槛为 "
                f"{MIN_DISTINCT_POSTINGS_FOR_CANDIDATE}），不构成候选技术招聘信号；本轮不对该单元下证据判定。"
            ),
            "NO_RD_POSTING_IN_CELL": (
                "岗位数量达到门槛，但没有任何一个岗位属于研发职能类（CORE_R&D / CLINICAL_R&D / "
                "PRODUCT_ENGINEERING / ALGORITHM_SOFTWARE / HARDWARE_SYSTEMS），因此不是技术研发招聘信号。"
            ),
        }[code]
        cell["verdict"] = "UNKNOWN"
        cell["verdict_reason"] = {"code": code, "detail_zh": detail_zh,
                                  "detail_en": "no evidence verdict is issued below the candidate threshold"}
        novelty = str((cell.get("direction_novelty") or {}).get("direction_novelty"))
        cell["interpretation_zh"] = _interpret_zh("UNKNOWN", cell, novelty)
        cell["escalation"] = {
            "human_review_recommended": False,
            "threshold_distinct_posting_ids": MIN_DISTINCT_POSTINGS_FOR_HUMAN_REVIEW,
            "requires_novelty_in": ["NEW_DIRECTION_CANDIDATE", "RECENT_ACTIVITY"],
            "direction_novelty": novelty,
            "reason_zh": "未达候选门槛，不建议人工升级审查。",
        }
        _assert_no_conclusion(cell)
        return cell

    linked = evidence.get("linked") or []
    contradiction = evidence.get("contradiction_items") or []
    contrary_context = evidence.get("contrary_context") or []
    external = evidence.get("external") or {}
    n_linked_support = int(evidence.get("n_linked_support_total") or len(linked)) + int(
        external.get("n_linked_total") or 0
    )
    n_contrary_context = int(evidence.get("n_contrary_context_total") or len(contrary_context))

    if int(evidence.get("n_contradiction_total") or len(contradiction)) > 0:
        verdict, code = "CONTRADICTED", "CONTRADICTED_BY_CESSATION_EVIDENCE"
        detail_zh = "存在满足四条规则、且携带退出/撤回信号的独立证据。"
    elif n_linked_support > 0:
        verdict, code = "INDEPENDENTLY_SUPPORTED", "LINKED_INDEPENDENT_EVIDENCE"
        n_support = int(evidence.get("n_linked_support_total") or 0)
        detail_zh = (
            f"有 {n_support} 条证据库记录与 {int(external.get('n_linked_total') or 0)} 条临床试验记录通过全部四条关联规则。"
            "这是「该企业在该 track 有独立公开活动」的必要但很弱的核验：对长期在该 track 经营的企业，它几乎自动成立，"
            "不等同于「新兴方向被证实」。方向是否新颖请看 direction_novelty 字段。"
        )
    elif not cell.get("track_in_evidence_source") and external.get("status") in ("NOT_QUERIED", "CACHE_DIR_EMPTY"):
        verdict, code = "UNKNOWN", "TRACK_NOT_IN_EVIDENCE_SOURCE"
        detail_zh = (
            "该 track 不在本轮只读证据库的 38 个 track 词表中，且没有可用的试验缓存；"
            "该来源在结构上无法给出这个 track 的证据，因此「没有证据」不等于「没有活动」，记为未知。"
        )
    elif n_contrary_context > 0 and n_linked_support == 0:
        verdict, code = "NO_INDEPENDENT_SUPPORT", "ONLY_CONTRARY_CONTEXT_EVIDENCE"
        detail_zh = (
            f"同一企业同一 track 内只有 {n_contrary_context} 条召回（售后不良事件）记录通过关联规则。"
            "召回是上市后问题，不是「该方向不存在」的反证，也不构成支持；因此没有独立支持证据。"
        )
    else:
        failed = evidence.get("failed_rule_counts") or {}
        n_same = evidence.get("n_same_track_rows") or 0
        n_window = evidence.get("n_same_track_in_window") or 0
        if n_same == 0:
            verdict, code = "NO_INDEPENDENT_SUPPORT", "NO_EVIDENCE_ROWS_IN_TRACK"
            detail_zh = (
                "证据库中该企业没有该 track 的任何记录（规则 R2 无法满足：0 条同 track 记录）。"
                "这是「该来源没有记录」，不是「该企业没有活动」。"
            )
        elif n_window == 0:
            verdict, code = "NO_INDEPENDENT_SUPPORT", "EVIDENCE_OUTSIDE_TIME_WINDOW"
            detail_zh = (
                f"该 track 有 {n_same} 条记录，但没有一条落在时间窗 "
                f"[{cell['hiring_window'].get('window_start')}, {cell['hiring_window'].get('window_end')}] 内"
                "（规则 R3 失败）。"
            )
        else:
            verdict, code = "NO_INDEPENDENT_SUPPORT", "EVIDENCE_FAILED_RULE"
            detail_zh = (
                f"该 track 有 {n_same} 条记录、其中 {n_window} 条在时间窗内，但没有一条通过全部规则；"
                f"失败计数：{failed}。"
            )
    cell["verdict"] = verdict
    cell["verdict_reason"] = {"code": code, "detail_zh": detail_zh,
                              "detail_en": "verdict assigned by the pre-declared rules; see evidence block"}
    novelty = str((cell.get("direction_novelty") or {}).get("direction_novelty"))
    cell["interpretation_zh"] = _interpret_zh(verdict, cell, novelty)
    novelty_is_reviewable = novelty in ("NEW_DIRECTION_CANDIDATE", "RECENT_ACTIVITY")
    human_review = bool(
        cell["n_distinct_posting_ids"] >= MIN_DISTINCT_POSTINGS_FOR_HUMAN_REVIEW and novelty_is_reviewable
    )
    cell["human_review_recommended"] = human_review
    if human_review:
        escalation_reason = (
            f"达到人工升级门槛：{cell['n_distinct_posting_ids']} 个独立岗位 ID（>= "
            f"{MIN_DISTINCT_POSTINGS_FOR_HUMAN_REVIEW}），且方向新颖度为 {novelty}。"
        )
    elif cell["n_distinct_posting_ids"] < MIN_DISTINCT_POSTINGS_FOR_HUMAN_REVIEW:
        escalation_reason = (
            f"独立岗位 ID 只有 {cell['n_distinct_posting_ids']} 个（< "
            f"{MIN_DISTINCT_POSTINGS_FOR_HUMAN_REVIEW}），不建议单独立项人工审查。"
        )
    else:
        escalation_reason = (
            f"独立岗位 ID 有 {cell['n_distinct_posting_ids']} 个（>= "
            f"{MIN_DISTINCT_POSTINGS_FOR_HUMAN_REVIEW}），但方向新颖度为 {novelty}"
            "（既有方向或基线不足），不建议按「新方向」升级审查；可作为常规招聘观察保留。"
        )
    cell["escalation"] = {
        "human_review_recommended": human_review,
        "threshold_distinct_posting_ids": MIN_DISTINCT_POSTINGS_FOR_HUMAN_REVIEW,
        "requires_novelty_in": ["NEW_DIRECTION_CANDIDATE", "RECENT_ACTIVITY"],
        "direction_novelty": novelty,
        "reason_zh": escalation_reason,
    }
    _assert_no_conclusion(cell)
    return cell


def _interpret_zh(verdict: str, cell: Mapping[str, Any], novelty: str) -> str:
    """One honest paragraph per verdict; never adds a conclusion the rules did not produce."""
    evidence = cell.get("evidence") or {}
    n_high = int(evidence.get("n_high_specificity_support") or 0)
    n_medium = int(evidence.get("n_medium_specificity_support") or 0)
    if verdict == "INDEPENDENTLY_SUPPORTED":
        if n_high > 0:
            specificity_note = f"其中高特异性证据 {n_high} 条（设备许可/临床试验）。"
        elif n_medium > 0:
            specificity_note = f"其中中特异性证据 {n_medium} 条（设计变更/上市后研究类 PMA 补充）。"
        else:
            specificity_note = "全部为低特异性行政类证据（生产、地点或标签类 PMA 补充）。"
        return (
            f"独立证据核验通过：{specificity_note}"
            f"方向新颖度 = {novelty}。该核验只说明企业在同一技术方向有公开活动，"
            "不说明招聘对应一个新研发方向；单快照也不支持趋势判断。"
        )
    if verdict == "NO_INDEPENDENT_SUPPORT":
        return (
            f"未通过独立证据核验（{cell.get('verdict_reason', {}).get('code')}）。"
            "「该来源没有记录 / 记录不在窗口内」不等于「企业没有活动」；"
            f"方向新颖度 = {novelty}。"
        )
    if verdict == "CONTRADICTED":
        return "存在满足四条规则且携带退出/撤回信号的独立证据；这仍不支持对研发意图的推断。"
    code = (cell.get("verdict_reason") or {}).get("code")
    if code in ("BELOW_CANDIDATE_THRESHOLD", "NO_RD_POSTING_IN_CELL"):
        return (
            "未达候选门槛，本轮不对该单元做独立证据核验；"
            f"direction_novelty = {novelty} 仅作背景，不构成信号。"
        )
    return (
        "本轮无法给出独立证据判定（来源结构限制或数据不足）；"
        f"方向新颖度 = {novelty}。未知应作为未知保留。"
    )


def _assert_no_conclusion(cell: Mapping[str, Any]) -> None:
    fields = [
        cell.get("verdict"),
        (cell.get("verdict_reason") or {}).get("code"),
        (cell.get("verdict_reason") or {}).get("detail_zh"),
        (cell.get("verdict_reason") or {}).get("detail_en"),
        cell.get("hiring_signal_verdict"),
        (cell.get("escalation") or {}).get("reason_zh"),
        cell.get("interpretation_zh"),
    ]
    blob = " | ".join(str(field) for field in fields if field)
    for pattern in CONCLUSION_FORBIDDEN_PATTERNS:
        if pattern.search(blob):
            raise AssertionError(
                f"verdict field contains a forbidden development conclusion: {pattern.pattern!r} in {blob!r}"
            )


# ------------------------------------------------------------------ summary/md
def summarise(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    verdict_counts = Counter(str(cell.get("verdict")) for cell in cells)
    signal_counts = Counter(str(cell.get("hiring_signal_verdict")) for cell in cells)
    novelty_counts = Counter(
        str((cell.get("direction_novelty") or {}).get("direction_novelty")) for cell in cells
    )
    candidates = [cell for cell in cells if cell.get("is_candidate")]
    n_distinct_postings = sum(cell["n_distinct_posting_ids"] for cell in cells)
    return {
        "n_cells": len(cells),
        "n_candidates": len(candidates),
        "verdict_counts": {v: int(verdict_counts.get(v, 0)) for v in VERDICTS},
        "hiring_signal_verdict_counts": {
            v: int(signal_counts.get(v, 0)) for v in HIRING_SIGNAL_VERDICTS
        },
        "direction_novelty_counts": {
            v: int(novelty_counts.get(v, 0)) for v in DIRECTION_NOVELTY_VOCABULARY
        },
        "n_independently_supported": int(verdict_counts.get("INDEPENDENTLY_SUPPORTED", 0)),
        "n_no_independent_support": int(verdict_counts.get("NO_INDEPENDENT_SUPPORT", 0)),
        "n_unknown": int(verdict_counts.get("UNKNOWN", 0)),
        "n_contradicted": int(verdict_counts.get("CONTRADICTED", 0)),
        "n_new_direction_candidate": int(novelty_counts.get("NEW_DIRECTION_CANDIDATE", 0)),
        "n_established_direction": int(novelty_counts.get("ESTABLISHED_DIRECTION", 0)),
        "n_human_review_recommended": sum(
            1 for cell in candidates if (cell.get("escalation") or {}).get("human_review_recommended")
        ),
        "sum_distinct_posting_ids_in_track_cells": n_distinct_postings,
    }


def render_markdown(artifact: Mapping[str, Any]) -> str:
    snapshot = artifact["snapshot"]
    summary = artifact["summary"]
    db = artifact["evidence_source"]["db_probe"]
    lines: list[str] = []
    lines.append("# 证据关联 · 简要机器摘要（WP2c）")
    lines.append("")
    lines.append(f"- 生成时间（UTC）：`{artifact['generated_at']}`")
    lines.append(f"- 快照：`{snapshot['path']}`（{snapshot['role']}，文件行数 n={snapshot['n_lines']}，"
                 f"按 posting_id 去重后 n={snapshot['n_postings_unique']}，"
                 f"丢弃分页重复行 {snapshot['n_duplicate_rows_dropped']} 行）")
    lines.append(f"- 分类器：`{artifact['classifier']['classifier_status']}`")
    lines.append(f"- 证据库：`{db['path']}`，实测窗口 {db['measured_event_date_min']} … "
                 f"{db['measured_event_date_max']}，共 {db['n_events']} 条")
    lines.append(f"- 关联规则：PROTOCOL §6 四条（R1 同企业 / R2 同 track / R3 时间窗 / R4 可回查标识）；"
                 f"回看窗口 = {artifact['constants']['HIRE_EVIDENCE_MAX_LOOKBACK_MONTHS']} 个月")
    lines.append("")
    lines.append("## 逐 track 计数")
    lines.append("")
    lines.append("> 读法：`INDEPENDENTLY_SUPPORTED` 只表示「独立来源确认该企业在该 track 有公开活动」，"
                 "这是必要但很弱的核验，对既有大企业几乎自动成立；真正有区分度的是 `方向新颖度`。")
    lines.append("")
    lines.append("| track | 名称 | 岗位数 | 独立岗位 ID | R&D 岗位 | 仅描述命中率 | 候选？ | 招聘信号判定 | 方向新颖度 | 独立证据判定 | 高特异性支持证据 | 建议人工审查 |")
    lines.append("|---|---|---:|---:|---:|---:|:--:|---|---|---|---:|:--:|")
    for cell in artifact["cells"]:
        quality = cell.get("track_evidence_quality") or {}
        lines.append(
            f"| `{cell['track_id']}` | {cell['track_name_zh']} | {cell['n_postings']} | "
            f"{cell['n_distinct_posting_ids']} | {cell['n_rd_postings']} | "
            f"{float(quality.get('description_only_rate') or 0):.0%} | "
            f"{'是' if cell['is_candidate'] else '否'} | {cell['hiring_signal_verdict']} | "
            f"{(cell.get('direction_novelty') or {}).get('direction_novelty')} | {cell['verdict']} | "
            f"{(cell.get('evidence') or {}).get('n_high_specificity_support', 0)} | "
            f"{'是' if (cell.get('escalation') or {}).get('human_review_recommended') else '否'} |"
        )
    lines.append("")
    lines.append("> 仅描述命中率 = 标题里没有 track 关键词、只靠正文关键词归入该 track 的岗位占比；"
                 "比例高说明关键词通胀风险高，人工复核要优先核对原文。")
    lines.append("")
    lines.append("## 判定计数")
    lines.append("")
    lines.append(f"- 招聘信号分级：`CANDIDATE_TECHNICAL_HIRING_SIGNAL` = {summary['hiring_signal_verdict_counts']['CANDIDATE_TECHNICAL_HIRING_SIGNAL']}，"
                 f"`UNKNOWN` = {summary['hiring_signal_verdict_counts']['UNKNOWN']}")
    for verdict in VERDICTS:
        lines.append(f"- 独立证据判定 `{verdict}`：{summary['verdict_counts'][verdict]}")
    lines.append("")
    lines.append("## 岗位职能分类与 track 赋值（分类器 = 规则臂 A）")
    lines.append("")
    lines.append("| 职能类 | 岗位数 |")
    lines.append("|---|---:|")
    for function_class, count in artifact["counts"]["function_class_counts"].items():
        lines.append(f"| `{function_class}` | {count} |")
    lines.append("")
    lines.append("| track 状态 | 岗位数 |")
    lines.append("|---|---:|")
    for status, count in artifact["counts"]["track_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")
    lines.append("")
    lines.append("## 数据质量与边界")
    lines.append("")
    for note in artifact["limitations"]:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------------- run
def run(
    *,
    jobs_path: Path | None = None,
    evidence_db: Path = DEFAULT_EVIDENCE_DB,
    config_dir: Path = CONFIG_DIR,
    results_dir: Path = RESULTS_DIR,
    ctgov_cache: Path = DEFAULT_CTGOV_CACHE,
    out_json: Path | None = None,
    out_md: Path | None = None,
    classify: Callable[[Mapping[str, Any]], dict[str, Any]] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Run the linking pipeline end to end and write the two artifacts."""
    results_dir = Path(results_dir)
    out_json = Path(out_json) if out_json else results_dir / "evidence_linking.json"
    out_md = Path(out_md) if out_md else results_dir / "evidence_linking.md"

    tracks = load_tracks(config_dir)
    focus = load_focus_companies(config_dir)
    if jobs_path is None:
        snapshot = resolve_snapshot(results_dir)
        jobs_path = Path(snapshot["path"])
    else:
        jobs_path = Path(jobs_path)
        snapshot = {
            "path": jobs_path,
            "role": "EXPLICIT",
            "n_lines": count_lines(jobs_path),
            "selection_note": "explicit --jobs path",
        }
    postings_raw = load_jobs(jobs_path)
    postings, duplicate_rows = dedupe_postings(postings_raw)
    classify = classify or make_taxonomy_classifier()
    classifier_meta = _classifier_meta(classify, postings)

    aggregate = build_cells(postings, classify, tracks, focus)

    conn = open_evidence_db(Path(evidence_db))
    try:
        db_probe = probe_evidence_db(conn, Path(evidence_db))
        db_tracks = db_probe["db_tracks"]
        ctgov_doc = load_ctgov_cache(Path(ctgov_cache))
        company_events: dict[str, list[dict[str, Any]]] = {}
        company_queries: list[dict[str, Any]] = []
        track_exists_queries: dict[str, dict[str, Any]] = {}
        for cell in aggregate["cells"]:
            company_key = cell["company_key"]
            if company_key not in company_events:
                rows, query = fetch_company_events(conn, company_key)
                company_events[company_key] = rows
                company_queries.append(query)
            if cell["track_id"] not in track_exists_queries:
                track_exists_sql = "SELECT id, name_zh, name_en FROM tracks WHERE id = ?"
                track_row = conn.execute(track_exists_sql, (cell["track_id"],)).fetchone()
                track_exists_queries[cell["track_id"]] = {
                    "source": "dev_device.sqlite",
                    "sql": track_exists_sql,
                    "params": [cell["track_id"]],
                    "row_count": 1 if track_row else 0,
                }
            cell["evidence"] = evaluate_cell_evidence(
                cell,
                company_events[company_key],
                tracks,
                focus,
                db_tracks,
                ctgov_doc,
                track_exists_queries[cell["track_id"]],
                source_coverage_start=parse_date(db_probe.get("measured_event_date_min")),
            )
            assign_verdict(cell)
    finally:
        conn.close()

    summary = summarise(aggregate["cells"])
    limitations = build_limitations(snapshot, db_probe, aggregate, postings)

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "generated_at": generated_at or utc_now_iso(),
        "snapshot": {
            "path": str(snapshot["path"]),
            "role": snapshot["role"],
            "n_lines": snapshot["n_lines"],
            "n_postings_unique": len(postings),
            "n_duplicate_rows_dropped": len(duplicate_rows),
            "duplicate_rows": duplicate_rows[:10],
            "dedupe_rule": (
                "posting_id is the source-stable identity; rows sharing a posting_id are one posting "
                "(offset-pagination duplicates). Counts use the de-duplicated set."
            ),
            "selection_note": snapshot.get("selection_note"),
            "sha256": sha256_file(Path(snapshot["path"])),
            "collection_report": snapshot.get("collection_report"),
            "first_seen_min": min(
                (p.get("first_seen_at") for p in postings if p.get("first_seen_at")), default=None
            ),
            "first_seen_max": max(
                (p.get("first_seen_at") for p in postings if p.get("first_seen_at")), default=None
            ),
            "source_posted_min": min(
                (p.get("source_posted_at") for p in postings if p.get("source_posted_at")), default=None
            ),
            "source_posted_max": max(
                (p.get("source_posted_at") for p in postings if p.get("source_posted_at")), default=None
            ),
            "company_keys": sorted({str(p.get("company_key")) for p in postings}),
        },
        "constants": {
            "HIRE_EVIDENCE_MAX_LOOKBACK_MONTHS": HIRE_EVIDENCE_MAX_LOOKBACK_MONTHS,
            "HIRE_EVIDENCE_MAX_LEAD_DAYS": HIRE_EVIDENCE_MAX_LEAD_DAYS,
            "MIN_DISTINCT_POSTINGS_FOR_CANDIDATE": MIN_DISTINCT_POSTINGS_FOR_CANDIDATE,
            "MIN_DISTINCT_POSTINGS_FOR_HUMAN_REVIEW": MIN_DISTINCT_POSTINGS_FOR_HUMAN_REVIEW,
            "RD_FUNCTIONS": list(RD_FUNCTIONS),
            "TECHNICAL_FUNCTIONS": list(TECHNICAL_FUNCTIONS),
            "NON_TECHNICAL_FUNCTIONS": list(NON_TECHNICAL_FUNCTIONS),
            "note": "all constants are declared before measurement and are not adjusted per cell",
        },
        "classifier": classifier_meta,
        "verdict_vocabulary": list(VERDICTS),
        "hiring_signal_vocabulary": list(HIRING_SIGNAL_VERDICTS),
        "direction_novelty_vocabulary": list(DIRECTION_NOVELTY_VOCABULARY),
        "verdict_definitions": {
            "CANDIDATE_TECHNICAL_HIRING_SIGNAL": (
                ">= 2 distinct posting ids in one track, at least one in an R&D function class. "
                "A hiring observation only; no independent evidence is implied."
            ),
            "INDEPENDENTLY_SUPPORTED": (
                "An independent source confirms the company has public activity in this track "
                "(it passes the four linking rules). This is a NECESSARY-BUT-WEAK check: for a firm "
                "with a long history in the track it is satisfied almost automatically, and it is "
                "NOT evidence that the hiring marks an emerging direction. Read direction_novelty."
            ),
            "NO_INDEPENDENT_SUPPORT": (
                "No independent item passed the four rules. This is 'the source has no record in "
                "this track/window', not 'the company has no activity'."
            ),
            "CONTRADICTED": (
                "An independent item passed the rules and carries a pre-declared cessation/"
                "withdrawal signal. Unreachable on this FDA snapshot (no such event kind)."
            ),
            "UNKNOWN": (
                "The question cannot be answered by the available data (below candidate threshold, "
                "or the evidence source cannot represent this track)."
            ),
        },
        "direction_novelty_definitions": {
            "NEW_DIRECTION_CANDIDATE": (
                f"No evidence in the track in the observed baseline window before the last "
                f"{NOVELTY_RECENT_MONTHS} months, and >=1 event in the recent window. New relative to "
                "the evidence source's observed coverage, NOT proven new to the company."
            ),
            "RECENT_ACTIVITY": (
                "Activity in the recent window and some earlier history, but the track does not qualify "
                f"as established (span >= {NOVELTY_ESTABLISHED_MIN_SPAN_MONTHS} months, "
                f">= {NOVELTY_ESTABLISHED_MIN_EVENTS} events, present recently); direction status ambiguous."
            ),
            "ESTABLISHED_DIRECTION": (
                f"Activity spans >= {NOVELTY_ESTABLISHED_MIN_SPAN_MONTHS} months with "
                f">= {NOVELTY_ESTABLISHED_MIN_EVENTS} events and is present in the recent window; for this "
                "firm the track is an existing line of business, so hiring there is business-as-usual."
            ),
            "NO_BASELINE_DATA": (
                "The evidence source cannot see far enough back (or has no usable dates) to distinguish "
                "new from established. Absence of a signal, not evidence of one."
            ),
        },
        "evidence_specificity_definitions": {
            "HIGH_DEVICE_CLEARANCE": "FDA 510(k) clearance: a specific device/software authorisation.",
            "HIGH_CLINICAL_TRIAL": "ClinicalTrials.gov registered trial with a resolvable NCT id.",
            "MEDIUM_DESIGN_CHANGE": "PMA supplement for a design/component/specification/material change.",
            "MEDIUM_POSTAPPROVAL_STUDY": "PMA supplement for a post-approval study protocol.",
            "LOW_MANUFACTURING_PROCESS_CHANGE": "PMA supplement for a manufacturing/process change (administrative).",
            "LOW_FACILITY_LOCATION_CHANGE": "PMA supplement for a facility/location change (administrative).",
            "LOW_LABELING_CHANGE": "PMA supplement for a labelling change (administrative).",
            "UNKNOWN_SPECIFICITY": "PMA supplement whose reason could not be recovered (truncated payload).",
            "POST_MARKET_CONTEXT": "Device recall: recorded as contrary context, never as contradiction or support.",
        },
        "linking_rules": [dict(rule) for rule in LINKING_RULES],
        "evidence_source": {
            "db_probe": db_probe,
            "external_trials": {
                "status": ctgov_doc["status"],
                "cache_dir": ctgov_doc["cache_dir"],
                "requests": ctgov_doc["requests"],
                "note": ctgov_doc["note"],
            },
            "external_publications": {
                "status": "NOT_QUERIED",
                "note": (
                    "Europe PMC was reachable but no deterministic affiliation query with acceptable "
                    "precision was used this round, so publications are a declared gap, not a silent zero."
                ),
            },
        },
        "queries": company_queries
        + [
            {
                "id": "events_window",
                "source": "dev_device.sqlite",
                "sql": "SELECT MIN(event_date), MAX(event_date), MIN(as_of), MAX(as_of) FROM events",
                "params": [],
                "row_count": 1,
            },
            {
                "id": "events_by_source_kind",
                "source": "dev_device.sqlite",
                "sql": "SELECT source, kind, COUNT(*) FROM events GROUP BY source, kind ORDER BY source, kind",
                "params": [],
                "row_count": len(db_probe["by_source_kind"]),
            },
        ],
        "summary": summary,
        "counts": {
            "postings": len(postings),
            "distinct_posting_ids": len({str(p.get("posting_id")) for p in postings}),
            "function_class_counts": aggregate["function_class_counts"],
            "track_status_counts": aggregate["track_status_counts"],
            "n_track_cells": len(aggregate["cells"]),
            "n_postings_in_track_cells": sum(cell["n_postings"] for cell in aggregate["cells"]),
        },
        "cells": aggregate["cells"],
        "unclassified_postings": aggregate["unclassified_postings"],
        "posting_labels": aggregate["posting_labels"],
        "limitations": limitations,
        "conclusion_guard": {
            "statement": (
                "This artifact contains candidate signals and evidence links only. It does not state "
                "that a company is developing a technology, has changed strategy, or has increased R&D "
                "investment; the mission forbids those claims from a single snapshot without a time "
                "series and independent evidence of intent."
            ),
            "forbidden_patterns_applied_to_verdict_fields": [p.pattern for p in CONCLUSION_FORBIDDEN_PATTERNS],
        },
    }

    json_bytes = _write_json(out_json, artifact)
    out_md.write_text(render_markdown(artifact), encoding="utf-8")
    artifact["_artifacts"] = {"json": str(out_json), "json_bytes": json_bytes, "md": str(out_md)}
    return artifact


def build_limitations(
    snapshot: Mapping[str, Any],
    db_probe: Mapping[str, Any],
    aggregate: Mapping[str, Any],
    postings: Sequence[Mapping[str, Any]],
) -> list[str]:
    n_cells = len(aggregate["cells"])
    n_mapped = sum(1 for p in aggregate["posting_labels"] if p.get("track_id"))
    first_seen = sorted(p.get("first_seen_at") for p in postings if p.get("first_seen_at"))
    first_seen_span = f"{first_seen[0]} … {first_seen[-1]}" if first_seen else "不可用"
    medtronic_tracks = db_probe.get("focus_company_tracks", {}).get("medtronic", {})
    n_medtronic_tracks = medtronic_tracks.get("n_tracks_with_events")
    n_db_tracks = len(db_probe.get("db_tracks") or [])
    novelty_counts = Counter(
        str((cell.get("direction_novelty") or {}).get("direction_novelty")) for cell in aggregate["cells"]
    )
    total_track_postings = sum(cell["n_postings"] for cell in aggregate["cells"])
    desc_only = sum(
        int((cell.get("track_evidence_quality") or {}).get("n_description_only") or 0)
        for cell in aggregate["cells"]
    )
    desc_only_rate = round(desc_only / total_track_postings, 4) if total_track_postings else 0.0
    anchor_raw = min(
        (str(p.get("first_seen_at") or "") for p in postings if p.get("first_seen_at")),
        default="",
    )
    anchor = parse_date(anchor_raw[:10])
    coverage_start = parse_date(db_probe.get("measured_event_date_min"))
    if anchor is not None and coverage_start is not None:
        baseline_end = add_months(anchor, -NOVELTY_RECENT_MONTHS)
        baseline_months_text = f"{(baseline_end - coverage_start).days / 30.44:.1f} 个月"
    else:
        baseline_months_text = "未知"
    headline = (
        "本轮最重要的方法是「先证明核验很弱，再区分新颖度」："
        "同企业 + 同 track 的独立证据核验对既有大企业几乎自动成立（Medtronic 在本证据库 "
        f"{n_medtronic_tracks}/{n_db_tracks} 个 track 中有事件），因此 INDEPENDENTLY_SUPPORTED "
        "不是「新兴方向被证实」，只是必要但很弱的背景核验；真正有区分度的是 direction_novelty。"
        f"本轮方向新颖度分布：{dict(novelty_counts)}。诚实结论是：核验容易且信息量低，"
        "判别性问题是新颖度；在这个证据库上，多数 track 只能判为既有方向或基线不足。"
    )
    return [
        headline,
        "INDEPENDENTLY_SUPPORTED 的定义被有意收窄：它 = 「独立来源确认该企业在该 track 有公开活动」，"
        "这是 NECESSARY-BUT-WEAK 核验，对长期在该 track 经营的企业几乎自动成立，不得读作「新兴方向被证实」。"
        "有科学含义的字段是 direction_novelty（NEW_DIRECTION_CANDIDATE / RECENT_ACTIVITY / "
        "ESTABLISHED_DIRECTION / NO_BASELINE_DATA），其基线窗口与覆盖月份在每格 direction_novelty 中逐项给出。",
        f"单快照：本轮只有一次 T0 观察（first_seen_at {first_seen_span}），"
        f"去重后岗位数 {len(postings)}、进入 track 单元的岗位 {n_mapped}、track 单元 {n_cells} 个。单次快照无法定义「变化」，也无法做趋势、领先/滞后或基线比较。",
        "岗位数按 posting_id 去重后计：同一 posting_id 的重复行是 Workday 偏移分页造成的重复返回，不是两个岗位；"
        "文件行数一般会略多于独立岗位数（本轮见 snapshot.n_duplicate_rows_dropped）。",
        "覆盖率未知：采集只覆盖该企业公开 Careers 站点上我们合法可见的部分；分母（企业实际在招岗位总数）未知，"
        "「看不见」不等于「没有」。",
        "岗位 ≠ 投入：岗位数量不能换算成研发投入、团队规模或项目立项；本文件不把岗位数当投入指标。",
        f"时间窗：独立证据的回看窗口固定为 {HIRE_EVIDENCE_MAX_LOOKBACK_MONTHS} 个月，写死在代码中；"
        "窗口外的证据（例如 2024-11-04 之前的记录）按规则拒绝，并计入 failed_rule_counts。",
        f"证据库实测窗口只有 {db_probe['measured_event_date_min']} … {db_probe['measured_event_date_max']}"
        f"（{db_probe['n_events']} 条），不是任务书最初描述的 2016-11 起全历史；因此 24 个月回看窗几乎覆盖了整个证据库，"
        f"更早的历史无法被检验。方向新颖度的可用基线只有约 "
        f"{baseline_months_text}（{db_probe['measured_event_date_min']} 到「近期窗」之前），"
        "NEW_DIRECTION_CANDIDATE 只能读作「相对可见基线为新」，绝不能读作「企业对该公司全新」。",
        f"证据库 payload 截断：{db_probe['payload_parse_failures_total']} 条记录的 payload 无法完整解析"
        f"（{db_probe['payload_parse_failures_by_kind']}），标识与 PMA 补充类型改用 url / payload 前缀正则提取；"
        "这一步本身已计入可回查率与特异性判定。",
        "证据来源结构限制：dev_device.sqlite 只含 FDA 510(k)/PMA/召回三类事件（无临床试验、无论文、无企业公告）；"
        "本轮临床试验仅用离线缓存中的 ClinicalTrials.gov 记录，论文（Europe PMC）明确记为 NOT_QUERIED。",
        "两家重点企业在证据库中为 0 条事件（Draeger、Mindray），若其岗位出现在后续快照中，"
        "只能记为来源限制导致的 NO_INDEPENDENT_SUPPORT，不得解释为「没有创新」。",
        "CONTRADICTED 在本轮不可达：FDA 事件流中没有「退出/撤回该技术方向」的信号；召回只作为售后背景记录，"
        "不当作反证。因此本轮没有任何单元被判为 CONTRADICTED，这是数据能力边界，不是「没有反证」。",
        "PMA 补充的绝大多数是行政类（生产/地点/标签变更），不是技术方向证据；本文件把每条关联证据的特异性"
        "（HIGH/MEDIUM/LOW）逐条记录，低特异性证据不能让一个候选变成「被证实的新方向」。",
        "分类器是保守的规则臂（A arm）：track 只在函数类别允许且关键词证据足够时才赋值，"
        "商业/临床现场岗位的 track 会被函数门槛压制（SUPPRESSED_BY_FUNCTION_CLASS）。因此本文件中的 track 覆盖是下限，"
        "未进入 track 的岗位保留在 unclassified_postings 中供审计。反过来，一次见到的关键词通胀是真实存在的："
        f"进入 track 单元的 {total_track_postings} 个岗位中，{desc_only} 个（{desc_only_rate:.1%}）的 track 证据只来自岗位描述、"
        "标题里没有该 track 关键词（medical_ai 的正文里 artificial intelligence / software 尤其容易出现在普通工程或合规段落）。"
        "每格的 track_evidence_quality 给出该比例；人工复核第一步必须是核对 postings[].track_quotes 的原文上下文。",
        "关联继承证据库既有的 track 赋值（上游 product-code→track 映射），本管线不重新分类上游事件；"
        "上游一个错误 track 赋值会原样传播到 same-track 关联，这一点必须在人工复核时抽查。",
        "规则匹配只做确定性字符串/结构化字段匹配，不做语义相似、不做模糊企业名匹配；"
        "「同一企业同一 track 两条公开事件」不构成「同一个研发项目」的证据（PROTOCOL §6 末条）。",
    ]


# ----------------------------------------------------------------------- CLI
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cross-source evidence linking (Phase 4 WP2c)")
    parser.add_argument("--jobs", default=None, help="job snapshot JSONL (default: auto-select)")
    parser.add_argument("--db", default=str(DEFAULT_EVIDENCE_DB), help="read-only evidence DB")
    parser.add_argument("--config-dir", default=str(CONFIG_DIR))
    parser.add_argument("--results-dir", default=str(RESULTS_DIR))
    parser.add_argument("--ctgov-cache", default=str(DEFAULT_CTGOV_CACHE))
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-md", default=None)
    args = parser.parse_args(argv)

    artifact = run(
        jobs_path=Path(args.jobs) if args.jobs else None,
        evidence_db=Path(args.db),
        config_dir=Path(args.config_dir),
        results_dir=Path(args.results_dir),
        ctgov_cache=Path(args.ctgov_cache),
        out_json=Path(args.out_json) if args.out_json else None,
        out_md=Path(args.out_md) if args.out_md else None,
    )
    print(json.dumps(
        {
            "json": artifact["_artifacts"]["json"],
            "json_bytes": artifact["_artifacts"]["json_bytes"],
            "md": artifact["_artifacts"]["md"],
            "snapshot_role": artifact["snapshot"]["role"],
            "snapshot_n": artifact["snapshot"]["n_lines"],
            "classifier_status": artifact["classifier"]["classifier_status"],
            "summary": artifact["summary"],
            "track_cells": [
                {
                    "track_id": cell["track_id"],
                    "n_distinct_posting_ids": cell["n_distinct_posting_ids"],
                    "hiring_signal_verdict": cell["hiring_signal_verdict"],
                    "verdict": cell["verdict"],
                    "verdict_code": cell["verdict_reason"]["code"],
                }
                for cell in artifact["cells"]
            ],
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
