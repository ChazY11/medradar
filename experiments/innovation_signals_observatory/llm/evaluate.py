"""Arm-agnostic scorer for the job-text extraction experiment.

What it measures (pre-registered in ``docs/PROTOCOL.md`` §4, second layer)
--------------------------------------------------------------------------
1. JSON-valid and schema-valid rates, with the exact failure classes.
2. **Verbatim evidence locatability**: every quote the extractor asserts is
   located in the posting using the existing harness matcher (NFC + whitespace
   collapse only, no fuzzy matching; ``validation/evidence.py``).
3. **Evidence support**: an *independent deterministic* check that the located
   quote contains the assigned technology track's keyword family (from
   ``config/tracks_device.json``) or the assigned function class's cue phrase
   (from ``config/recruitment_function_classes.json``).  This check is
   conservative: a False means "the quote does not contain the declared cue", not
   "the label is wrong".  The A arm's support check is near-circular by
   construction (its evidence *is* the rule match) and is reported with an
   explicit note.
4. **Abstention and negative-control false positives.**  A deliberately selected
   non-technical subset is scored as: did the arm abstain / emit UNCLASSIFIED, or
   did it invent a technology track or an R&D function class for a Buyer/Planner?
   That false-positive count is a headline result, never a footnote, because the
   programme's prior fine-tuning run made exactly this metric worse (0.000 ->
   0.667; PR #20).
5. Measured wall-clock latency per item and peak VRAM where recorded.
6. Error taxonomy with counts.

What it deliberately does not measure
-------------------------------------
**No Precision / Recall / F1.**  There is no human gold standard for this corpus:
the function/track labels of the real postings have not been annotated by humans,
so any "accuracy" would be accuracy against either the rule arm (circular) or
against the model's own output (meaningless).  The evaluator emits
``precision_recall_f1: "NOT_EVALUABLE"`` everywhere instead.  Likewise, the
model's ``uncertainty_note`` is qualitative text, not a calibrated probability,
and no calibration metric is computed.

Arm A vs arm B
--------------
Both arms are scored by the same functions on the same postings.  Arm A's
evidence is a list of character-span records produced by its own rules; arm B's
evidence is the quote fields of its JSON payload.  The scorer treats a "claim
quote" as evidence for an asserted label and keeps arm A's non-asserted candidate
spans as *audit* spans (located too, but not counted as claims).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from experiments.local_llm_event_extraction.validation.evidence import (
    locate_quote,
    normalise_text,
)

from .job_text_schema import (
    ABSTAIN_REASONS,
    ARM_C_NOT_RUN_REASON,
    FUNCTION_CLASSES,
    RND_FUNCTION_CLASSES,
    SCHEMA_VERSION,
    TRACK_FIELD_UNCLASSIFIED,
    UNCLASSIFIED,
    load_track_registry,
)
from .subset import is_negative_title, posting_text

NON_TECHNICAL_FUNCTION_CLASSES: tuple[str, ...] = ("SALES_ADMIN_OTHER", UNCLASSIFIED)
"""Function classes that must not carry a technology track (the A-arm track gate,
mirrored here for scoring; see ``config/recruitment_function_classes.json``)."""

DEFAULT_FUNCTION_CONFIG = Path(__file__).resolve().parents[3] / "config" / "recruitment_function_classes.json"

PRECISION_RECALL_F1 = "NOT_EVALUABLE: no human gold standard exists for this corpus"
CONFIDENCE_CALIBRATION = "NOT_AVAILABLE: rule-derived strength / qualitative note, not a calibrated probability"


# ------------------------------------------------------------------- vocabularies
def load_function_cues(config_path: str | Path | None = None) -> dict[str, tuple[str, ...]]:
    """Per-class cue phrases (title + description) from the committed function map.

    Used only for the *support* check; this module does not classify anything.
    """
    path = Path(config_path) if config_path is not None else DEFAULT_FUNCTION_CONFIG
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        classes = payload.get("classes") or {}
    except (OSError, json.JSONDecodeError):
        return {}
    cues: dict[str, tuple[str, ...]] = {}
    for name, spec in classes.items():
        phrases: list[str] = []
        for key in ("title_phrases", "description_phrases"):
            phrases.extend(str(p) for p in (spec.get(key) or ()))
        cues[name] = tuple(dict.fromkeys(phrases))
    return cues


def _phrase_pattern(phrase: str) -> re.Pattern[str] | None:
    normalised = " ".join(phrase.split()).strip()
    if not normalised:
        return None
    escaped = re.escape(normalised)
    # ASCII-alnum word boundaries; a phrase like "r&d" or "ml ops" still works.
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.IGNORECASE)


def phrase_in(quote: str, phrase: str) -> bool:
    """Case-insensitive, whitespace-normalised whole-phrase containment."""
    if not quote or not phrase:
        return False
    pattern = _phrase_pattern(phrase)
    if pattern is None:
        return False
    return bool(pattern.search(normalise_text(quote)))


def any_phrase_in(quote: str, phrases: Iterable[str]) -> bool:
    return any(phrase_in(quote, phrase) for phrase in phrases)


# ------------------------------------------------------------- record inspection
def _f(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def collect_claim_quotes(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every quote that backs an asserted label, tagged by the field it supports.

    Arm B: the JSON payload's quote fields.
    Arm A: evidence spans whose ``target`` is the label the arm actually asserted
    (spans for *suppressed* candidates are audit evidence, not claims).
    """
    arm = record.get("arm")
    quotes: list[dict[str, Any]] = []
    if arm == "A":
        asserted_function = _f(record.get("function_class")) or UNCLASSIFIED
        asserted_track = _f(record.get("technology_track")) or TRACK_FIELD_UNCLASSIFIED
        for span in record.get("evidence_spans") or []:
            if not isinstance(span, Mapping):
                continue
            quote = _f(span.get("quote") or span.get("text"))
            if not quote:
                continue
            target = _f(span.get("target"))
            kind = _f(span.get("kind")) or _f(span.get("rule")) or "unknown"
            is_claim = (kind == "function" and target == asserted_function) or (
                kind == "track" and asserted_track != TRACK_FIELD_UNCLASSIFIED and target == asserted_track
            )
            if not is_claim:
                continue
            quotes.append(
                {
                    "field": "function_class" if kind == "function" else "technology_track",
                    "quote": quote,
                    "source": "rule_span",
                    "span_target": target,
                    "span_kind": kind,
                }
            )
        return quotes

    _FIELD_BY_RECORD_KEY = {
        "function_evidence_quote": "function_class",
        "track_evidence_quote": "technology_track",
        "r_and_d_evidence_quote": "r_and_d_evidence",
    }
    for record_key in ("function_evidence_quote", "track_evidence_quote", "r_and_d_evidence_quote"):
        quote = _f(record.get(record_key))
        if quote:
            quotes.append(
                {"field": _FIELD_BY_RECORD_KEY[record_key], "quote": quote, "source": "model_quote"}
            )
    for index, phrase in enumerate(record.get("capability_phrases") or []):
        if isinstance(phrase, Mapping):
            quote = _f(phrase.get("evidence_quote"))
            if quote:
                quotes.append(
                    {"field": f"capability_phrases[{index}]", "quote": quote, "source": "model_quote"}
                )
    return quotes


def collect_audit_quotes(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Arm A's non-asserted candidate spans (located, reported, not scored as claims)."""
    if record.get("arm") != "A":
        return []
    claimed = {item["quote"] for item in collect_claim_quotes(record)}
    audit: list[dict[str, Any]] = []
    for span in record.get("evidence_spans") or []:
        if not isinstance(span, Mapping):
            continue
        quote = _f(span.get("quote") or span.get("text"))
        if not quote or quote in claimed:
            continue
        audit.append(
            {
                "field": f"audit.{_f(span.get('kind')) or 'span'}",
                "quote": quote,
                "source": "rule_span",
                "span_target": _f(span.get("target")),
            }
        )
    return audit


def _locate_quote(quote: str, title: str, description: str, combined: str) -> dict[str, Any]:
    """Locate a quote in the combined posting; report which section it landed in."""
    location = locate_quote(combined, quote)
    in_title = locate_quote(title, quote) is not None if title else False
    in_description = locate_quote(description, quote) is not None if description else False
    return {
        "located": location is not None,
        "exact_raw": bool(location.exact_raw) if location is not None else False,
        "in_title": bool(in_title),
        "in_description": bool(in_description),
        "raw_start": location.raw_start if location is not None else None,
        "raw_end": location.raw_end if location is not None else None,
    }


def _track_keywords(track_id: str, tracks: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    spec = tracks.get(track_id) or {}
    keywords = list(spec.get("keywords") or ()) + list(spec.get("frontier_keywords") or ())
    return tuple(str(k) for k in keywords if str(k).strip())


def evaluate_record(
    record: Mapping[str, Any],
    posting: Mapping[str, Any],
    *,
    tracks: Mapping[str, Mapping[str, Any]] | None = None,
    function_cues: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Score one prediction against one posting.  Pure, deterministic."""
    tracks = tracks if tracks is not None else load_track_registry()
    function_cues = function_cues if function_cues is not None else load_function_cues()
    title = str(posting.get("job_title") or "")
    description = str(posting.get("job_description") or "")
    combined = posting_text(posting)

    arm = str(record.get("arm") or "?")
    function_class = _f(record.get("function_class")) or UNCLASSIFIED
    track = _f(record.get("technology_track")) or TRACK_FIELD_UNCLASSIFIED
    r_and_d = bool(record.get("r_and_d_evidence"))
    abstain = bool(record.get("abstain"))
    parse_status = str(record.get("parse_status") or "ok")
    schema_ok = parse_status == "ok"
    sample = str(record.get("sample") or ("negative" if is_negative_title(title) else "primary"))

    errors: list[str] = []
    if parse_status != "ok":
        errors.append(f"parse_{parse_status}")
    if record.get("timed_out"):
        errors.append("TIMEOUT")

    claim_quotes = collect_claim_quotes(record) if schema_ok else []
    audit_quotes = collect_audit_quotes(record) if schema_ok else []

    checked_claims: list[dict[str, Any]] = []
    for item in claim_quotes:
        located = _locate_quote(item["quote"], title, description, combined)
        checked_claims.append({**item, **located})
        if not located["located"]:
            errors.append("quote_not_located")
    checked_audit: list[dict[str, Any]] = []
    for item in audit_quotes:
        located = _locate_quote(item["quote"], title, description, combined)
        checked_audit.append({**item, **located})
        if not located["located"]:
            errors.append("audit_span_not_located")

    # ---------------------------------------------------------- evidence support
    # Only *located* quotes can support a claim: a quote that is not in the
    # posting is a failure (quote_not_located), not evidence.
    located_by_field: dict[str, list[str]] = {}
    for claim in checked_claims:
        if claim["located"]:
            located_by_field.setdefault(claim["field"], []).append(claim["quote"])
    all_located_quotes = " ".join(claim["quote"] for claim in checked_claims if claim["located"])

    function_support: bool | None = None
    function_support_any: bool | None = None
    if schema_ok and function_class != UNCLASSIFIED and function_class in FUNCTION_CLASSES:
        cues = function_cues.get(function_class, ())
        target_quotes = located_by_field.get("function_class", [])
        if not target_quotes:
            errors.append("function_label_without_located_quote")
        else:
            function_support = any_phrase_in(" ".join(target_quotes), cues)
            if not function_support:
                errors.append("function_quote_lacks_class_cue")
        if all_located_quotes:
            function_support_any = any_phrase_in(all_located_quotes, cues)

    track_support: bool | None = None
    track_support_any: bool | None = None
    if schema_ok and track != TRACK_FIELD_UNCLASSIFIED:
        if track not in tracks:
            errors.append("track_unknown_to_taxonomy")
        keywords = _track_keywords(track, tracks)
        target_quotes = located_by_field.get("technology_track", [])
        if not target_quotes:
            errors.append("track_label_without_located_quote")
        elif track in tracks:
            track_support = any_phrase_in(" ".join(target_quotes), keywords)
            if not track_support:
                errors.append("track_quote_lacks_track_keyword")
        if all_located_quotes and track in tracks:
            track_support_any = any_phrase_in(all_located_quotes, keywords)

    if schema_ok and r_and_d and not _f(record.get("r_and_d_evidence_quote")):
        if arm != "A":  # B schema already forbids this; A has no such field
            errors.append("rnd_true_without_quote")

    # --------------------------------------------------------- track-gate / claims
    track_gate_violation = (
        schema_ok
        and track != TRACK_FIELD_UNCLASSIFIED
        and (function_class in NON_TECHNICAL_FUNCTION_CLASSES or abstain)
    )
    if track_gate_violation:
        errors.append("track_on_non_technical_function")
    if schema_ok and abstain and (track != TRACK_FIELD_UNCLASSIFIED or function_class != UNCLASSIFIED):
        errors.append("abstain_with_labels")
    rnd_on_commercial_function = (
        schema_ok
        and r_and_d
        and (function_class in NON_TECHNICAL_FUNCTION_CLASSES or abstain)
    )
    if rnd_on_commercial_function:
        errors.append("rnd_evidence_on_commercial_function")
    internal_contradiction = bool(track_gate_violation or rnd_on_commercial_function)
    if internal_contradiction:
        errors.append("internal_contradiction")

    # What counts as "inventing a direction" on a posting: a technology track, or
    # an R&D/engineering function class.  This is the negative-control metric; it
    # is deliberately independent of how many other fields were schema-compliant.
    fp_track = track != TRACK_FIELD_UNCLASSIFIED
    fp_rnd_function = function_class in RND_FUNCTION_CLASSES
    false_positive = bool(fp_track or fp_rnd_function)
    if sample == "negative" and false_positive:
        errors.append("negative_control_false_positive")

    return {
        "posting_id": str(record.get("posting_id")),
        "arm": arm,
        "sample": sample,
        "job_title": title,
        "parse_status": parse_status,
        "schema_ok": schema_ok,
        "json_parsed": bool(record.get("json_parsed")),
        "abstain": abstain,
        "abstain_reason": _f(record.get("abstain_reason")),
        "function_class": function_class,
        "technology_track": track,
        "r_and_d_evidence": r_and_d,
        "function_support": function_support,
        "function_support_any": function_support_any,
        "track_support": track_support,
        "track_support_any": track_support_any,
        "track_gate_violation": bool(track_gate_violation),
        "rnd_on_commercial_function": bool(rnd_on_commercial_function),
        "internal_contradiction": internal_contradiction,
        "claimed_direction": bool(false_positive),
        "fp_track": bool(fp_track),
        "fp_rnd_function": bool(fp_rnd_function),
        "claims": checked_claims,
        "audit_spans": checked_audit,
        "claims_total": len(checked_claims),
        "claims_located": sum(1 for item in checked_claims if item["located"]),
        "audit_total": len(checked_audit),
        "audit_located": sum(1 for item in checked_audit if item["located"]),
        "latency_s": record.get("latency_s"),
        "peak_vram_mb": record.get("peak_vram_mb"),
        "tokens_in": record.get("tokens_in"),
        "tokens_out": record.get("tokens_out"),
        "input_truncated": bool(record.get("input", {}).get("truncated")) if isinstance(record.get("input"), Mapping) else False,
        "errors": sorted(set(errors)),
        "error_counts": _count_errors(errors),
    }


def _count_errors(codes: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    return counts


# ----------------------------------------------------------------- aggregation
def _rate(numerator: int, denominator: int) -> float | None:
    return (numerator / denominator) if denominator else None


def _latency_stats(values: Sequence[float]) -> dict[str, Any]:
    clean = sorted(float(v) for v in values if isinstance(v, (int, float)))
    if not clean:
        return {"n_measured": 0, "median_s": None, "mean_s": None, "p95_s": None, "max_s": None}
    index = min(len(clean) - 1, max(0, int(round(0.95 * (len(clean) - 1)))))
    return {
        "n_measured": len(clean),
        "median_s": round(statistics.median(clean), 3),
        "mean_s": round(statistics.fmean(clean), 3),
        "p95_s": round(clean[index], 3),
        "max_s": round(clean[-1], 3),
        "min_s": round(clean[0], 3),
    }


def summarise_arm(records: Sequence[Mapping[str, Any]], items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate per-item evaluations of one arm into the protocol metrics."""
    arm = records[0].get("arm") if records else None
    n = len(records)
    if n == 0:
        return {"arm": arm, "n": 0, "status": "NO_ITEMS"}

    schema_ok = sum(1 for item in items if item["schema_ok"])
    json_valid = sum(1 for item in items if item["json_parsed"])
    claims_total = sum(item["claims_total"] for item in items)
    claims_located = sum(item["claims_located"] for item in items)
    audit_total = sum(item["audit_total"] for item in items)
    audit_located = sum(item["audit_located"] for item in items)

    by_field: dict[str, dict[str, int]] = {}
    for item in items:
        for claim in item["claims"]:
            bucket = by_field.setdefault(claim["field"].split("[")[0], {"total": 0, "located": 0})
            bucket["total"] += 1
            bucket["located"] += int(claim["located"])

    function_claims = [item for item in items if item["function_class"] != UNCLASSIFIED and item["schema_ok"]]
    function_supported = [item for item in function_claims if item["function_support"] is True]
    function_checked = [item for item in function_claims if item["function_support"] is not None]
    function_supported_any = [item for item in function_claims if item.get("function_support_any") is True]
    track_claims = [item for item in items if item["technology_track"] != TRACK_FIELD_UNCLASSIFIED and item["schema_ok"]]
    track_supported = [item for item in track_claims if item["track_support"] is True]
    track_checked = [item for item in track_claims if item["track_support"] is not None]
    track_supported_any = [item for item in track_claims if item.get("track_support_any") is True]

    primary = [item for item in items if item["sample"] == "primary"]
    negative = [item for item in items if item["sample"] == "negative"]
    neg_fp_track = [item for item in negative if item["fp_track"]]
    neg_fp_rnd = [item for item in negative if item["fp_rnd_function"]]
    neg_false_positive = [item for item in negative if item["claimed_direction"]]
    neg_abstained = [item for item in negative if item["abstain"]]
    neg_unclassified = [
        item
        for item in negative
        if item["function_class"] == UNCLASSIFIED and item["technology_track"] == TRACK_FIELD_UNCLASSIFIED
    ]
    neg_correct_rejection = [item for item in negative if not item["claimed_direction"]]

    error_counts: dict[str, int] = {}
    for item in items:
        for code, count in item["error_counts"].items():
            error_counts[code] = error_counts.get(code, 0) + count

    function_distribution: dict[str, int] = {}
    track_distribution: dict[str, int] = {}
    for item in items:
        function_distribution[item["function_class"]] = function_distribution.get(item["function_class"], 0) + 1
        track_distribution[item["technology_track"]] = track_distribution.get(item["technology_track"], 0) + 1

    parse_counts: dict[str, int] = {}
    for item in items:
        parse_counts[item["parse_status"]] = parse_counts.get(item["parse_status"], 0) + 1

    return {
        "arm": arm,
        "n": n,
        "n_primary": len(primary),
        "n_negative": len(negative),
        "schema_pass_rate": _rate(schema_ok, n),
        "json_valid_rate": _rate(json_valid, n),
        "parse_status_counts": parse_counts,
        "evidence": {
            "claim_quotes_total": claims_total,
            "claim_quotes_located": claims_located,
            "claim_locatability_rate": _rate(claims_located, claims_total),
            "records_with_at_least_one_claim_quote": sum(1 for item in items if item["claims_total"] > 0),
            "records_all_claim_quotes_located": sum(
                1 for item in items if item["claims_total"] > 0 and item["claims_located"] == item["claims_total"]
            ),
            "by_field": by_field,
            "audit_spans_total": audit_total,
            "audit_spans_located": audit_located,
            "audit_locatability_rate": _rate(audit_located, audit_total),
            "method": "existing harness locate_quote: NFC + whitespace collapse only, no fuzzy matching",
        },
        "support": {
            "function_claims": len(function_claims),
            "function_checked": len(function_checked),
            "function_supported": len(function_supported),
            "function_support_rate": _rate(len(function_supported), len(function_checked)),
            "function_supported_any_quote": len(function_supported_any),
            "function_support_any_quote_rate": _rate(len(function_supported_any), len(function_claims)),
            "track_claims": len(track_claims),
            "track_checked": len(track_checked),
            "track_supported": len(track_supported),
            "track_support_rate": _rate(len(track_supported), len(track_checked)),
            "track_supported_any_quote": len(track_supported_any),
            "track_support_any_quote_rate": _rate(len(track_supported_any), len(track_claims)),
            "method": (
                "deterministic conservative check: located claim quote must contain the assigned "
                "track's keyword family / the assigned function class's cue phrase (committed "
                "config files). False means 'cue absent from the quote', NOT 'label wrong'."
            ),
            "arm_a_circularity_note": (
                "Arm A's evidence spans are the rule match that produced its label, so its "
                "support rate is circular by construction and is NOT independent evidence."
                if arm == "A"
                else None
            ),
        },
        "abstention": {
            "abstain_count": sum(1 for item in items if item["abstain"]),
            "abstain_rate": _rate(sum(1 for item in items if item["abstain"]), n),
            "abstain_rate_primary": _rate(sum(1 for item in primary if item["abstain"]), len(primary)),
            "abstain_rate_negative": _rate(len(neg_abstained), len(negative)),
            "unclassified_function_rate": _rate(sum(1 for item in items if item["function_class"] == UNCLASSIFIED), n),
            "unclassified_track_rate": _rate(sum(1 for item in items if item["technology_track"] == TRACK_FIELD_UNCLASSIFIED), n),
            "abstain_reasons": _distribution([item["abstain_reason"] for item in items if item["abstain"]]),
            "note": (
                "Arm A has no abstain field: 'abstained' is derived by the evaluator as "
                "function_class==UNCLASSIFIED and track_id==UNCLASSIFIED."
                if arm == "A"
                else "Arm B abstain is model-reported and schema-validated."
            ),
        },
        "negative_control": {
            "n": len(negative),
            "false_positive_count": len(neg_false_positive),
            "false_positive_rate": _rate(len(neg_false_positive), len(negative)),
            "track_false_positive_count": len(neg_fp_track),
            "track_false_positive_rate": _rate(len(neg_fp_track), len(negative)),
            "rnd_function_claim_count": len(neg_fp_rnd),
            "rnd_function_claim_rate": _rate(len(neg_fp_rnd), len(negative)),
            "abstained_count": len(neg_abstained),
            "abstained_rate": _rate(len(neg_abstained), len(negative)),
            "unclassified_both_count": len(neg_unclassified),
            "correct_rejection_count": len(neg_correct_rejection),
            "correct_rejection_rate": _rate(len(neg_correct_rejection), len(negative)),
            "track_gate_violation_count": sum(1 for item in items if item["track_gate_violation"]),
            "false_positive_postings": [item["posting_id"] for item in neg_false_positive],
            "definition": (
                "false positive = the arm asserted a technology track OR an R&D function class "
                f"({', '.join(RND_FUNCTION_CLASSES)}) for a title-declared non-technical posting"
            ),
        },
        "internal_consistency": {
            "n_schema_ok": sum(1 for item in items if item["schema_ok"]),
            "contradiction_count": sum(1 for item in items if item["internal_contradiction"]),
            "contradiction_rate": _rate(
                sum(1 for item in items if item["internal_contradiction"]),
                sum(1 for item in items if item["schema_ok"]),
            ),
            "track_on_commercial_function_count": sum(
                1 for item in items if item["track_gate_violation"]
            ),
            "rnd_evidence_on_commercial_function_count": sum(
                1 for item in items if item["rnd_on_commercial_function"]
            ),
            "contradiction_postings": [
                item["posting_id"] for item in items if item["internal_contradiction"]
            ],
            "definition": (
                "an internal contradiction is a payload that is structurally valid but "
                "self-inconsistent: a technology track attached to a commercial/administrative/"
                "abstained function class, or r_and_d_evidence=true for such a class. No human "
                "gold standard is needed to call that a failure."
            ),
        },
        "function_class_distribution": function_distribution,
        "track_distribution": track_distribution,
        "r_and_d_true_rate": _rate(sum(1 for item in items if item["r_and_d_evidence"]), n),
        "input_truncated_count": sum(1 for item in items if item["input_truncated"]),
        "latency": _latency_stats([item["latency_s"] for item in items if item["latency_s"] is not None]),
        "peak_vram_mb_max": max(
            (float(item["peak_vram_mb"]) for item in items if item["peak_vram_mb"] is not None),
            default=None,
        ),
        "error_taxonomy": dict(sorted(error_counts.items())),
        "precision_recall_f1": PRECISION_RECALL_F1,
        "confidence_calibration": CONFIDENCE_CALIBRATION,
    }


def _distribution(values: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = "null" if value is None else str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def compare_arms(arms: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Agreement between arms on the primary sample (agreement, not accuracy)."""
    if "A" not in arms or "B" not in arms:
        return {"available": False, "reason": "need both arm A and arm B predictions on the same items"}
    a, b = arms["A"], arms["B"]
    a_pairs = {item["posting_id"]: item for item in a["_items"]} if "_items" in a else {}
    b_pairs = {item["posting_id"]: item for item in b["_items"]} if "_items" in b else {}
    shared = [pid for pid in a_pairs if pid in b_pairs and a_pairs[pid]["sample"] == "primary"]
    if not shared:
        return {"available": False, "reason": "no shared primary postings"}
    both_unclassified = a_labelled_b_unclassified = a_unclassified_b_labelled = both_labelled = 0
    same_function = same_track = 0
    for pid in shared:
        ai, bi = a_pairs[pid], b_pairs[pid]
        a_unclass = ai["function_class"] == UNCLASSIFIED and ai["technology_track"] == TRACK_FIELD_UNCLASSIFIED
        b_unclass = bi["function_class"] == UNCLASSIFIED and bi["technology_track"] == TRACK_FIELD_UNCLASSIFIED
        if a_unclass and b_unclass:
            both_unclassified += 1
        elif a_unclass:
            a_unclassified_b_labelled += 1
        elif b_unclass:
            a_labelled_b_unclassified += 1
        else:
            both_labelled += 1
        same_function += int(ai["function_class"] == bi["function_class"])
        same_track += int(
            ai["technology_track"] == bi["technology_track"] and ai["technology_track"] != TRACK_FIELD_UNCLASSIFIED
        )
    return {
        "available": True,
        "n_shared_primary": len(shared),
        "both_unclassified": both_unclassified,
        "a_unclassified_b_labelled": a_unclassified_b_labelled,
        "a_labelled_b_unclassified": a_labelled_b_unclassified,
        "both_labelled": both_labelled,
        "same_function_class_count": same_function,
        "same_non_unclassified_track_count": same_track,
        "note": "agreement between classifiers, NOT accuracy: there is no human gold standard",
    }


# --------------------------------------------------------------------- reporting
def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _build_provenance(manifests: Mapping[str, Mapping[str, Any]], run_dir: Path) -> dict[str, Any]:
    """Assemble model/prompt/schema/subset provenance for the report header.

    The mission requires every AI classification to carry model version, prompt
    version, evidence and uncertainty. ``prompt: None`` in a table header is a
    provenance hole, so the header is rendered from the manifests, never retyped.
    """
    prompt_versions: set[str] = set()
    template_hashes: set[str] = set()
    model_ids: set[str] = set()
    revisions: set[str] = set()
    fingerprints: set[str] = set()
    input_budgets: set[int] = set()
    max_new_tokens: set[int] = set()
    schema_versions: set[str] = set()
    data_files: list[dict[str, Any]] = []
    for payload in manifests.values():
        prompt = payload.get("prompt") or {}
        if prompt.get("prompt_version"):
            prompt_versions.add(str(prompt["prompt_version"]))
        if prompt.get("template_sha256"):
            template_hashes.add(str(prompt["template_sha256"]))
        if payload.get("schema_version"):
            schema_versions.add(str(payload["schema_version"]))
        inputs = payload.get("inputs") or {}
        if inputs.get("max_input_chars"):
            input_budgets.add(int(inputs["max_input_chars"]))
        decoding = payload.get("decoding") or {}
        if decoding.get("max_new_tokens"):
            max_new_tokens.add(int(decoding["max_new_tokens"]))
        model = payload.get("model") or {}
        describe = model.get("describe") or {}
        if describe.get("model_id"):
            model_ids.add(str(describe["model_id"]))
        if describe.get("model_revision"):
            revisions.add(str(describe["model_revision"]))
        if model.get("weights_fingerprint"):
            fingerprints.add(str(model["weights_fingerprint"]))
        if payload.get("data"):
            data_files.append(payload["data"])

    subset_rule: dict[str, Any] = {}
    for path in sorted(run_dir.glob("subset_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rule = payload.get("rule") or {}
        if rule:
            subset_rule = {
                "file": path.name,
                "rule_id": rule.get("rule_id"),
                "salt": rule.get("salt"),
                "hash": rule.get("hash"),
                "order": rule.get("order"),
                "n_primary": rule.get("n_primary_requested"),
                "n_negative": rule.get("n_negative_requested"),
                "negative_title_pattern": rule.get("negative_title_pattern"),
            }
            break

    return {
        "schema_version": sorted(schema_versions)[0] if schema_versions else SCHEMA_VERSION,
        "prompt_version": ", ".join(sorted(prompt_versions)) if prompt_versions else None,
        "prompt_template_sha256": sorted(template_hashes)[0] if template_hashes else None,
        "model_id": ", ".join(sorted(model_ids)) if model_ids else None,
        "model_revision": ", ".join(sorted(revisions)) if revisions else None,
        "model_revision_note": (
            "local weights directory has no immutable HF revision; the unpinned override and the "
            "weights fingerprint are recorded instead"
            if not revisions
            else None
        ),
        "weights_fingerprint": ", ".join(sorted(fingerprints)) if fingerprints else None,
        "input_char_budget": sorted(input_budgets) if input_budgets else None,
        "max_new_tokens": sorted(max_new_tokens) if max_new_tokens else None,
        "subset_rule": subset_rule or None,
        "data": data_files,
    }


def render_arm_table(metrics: Mapping[str, Any], comparison: Mapping[str, Any] | None = None) -> str:
    """Markdown arm table in the programme's pre-registered metric vocabulary."""
    arms = metrics.get("arms", {})
    prov = metrics.get("provenance") or {}
    lines: list[str] = []
    lines.append("# LLM job-text experiment · arm table")
    lines.append("")
    template = prov.get("prompt_template_sha256")
    fingerprint = prov.get("weights_fingerprint")
    subset = prov.get("subset_rule") or {}
    revision = prov.get("model_revision") or "unpinned-local-weights"
    lines.append(
        "Provenance (from run manifests, not retyped): "
        f"model `{prov.get('model_id')}` revision `{revision}`"
        + (f" ({prov['model_revision_note']})" if prov.get("model_revision_note") else "")
        + f"; weights sha256 `{(fingerprint or 'n/a')[:16]}…`; "
        f"prompt `{prov.get('prompt_version')}` template sha256 `{(template or 'n/a')[:16]}…`; "
        f"schema `{prov.get('schema_version')}`; "
        f"subset rule `{subset.get('rule_id')}` (salt `{subset.get('salt')}`, "
        f"n_primary={subset.get('n_primary')}, n_negative={subset.get('n_negative')}); "
        f"input_char_budget={prov.get('input_char_budget')}; max_new_tokens={prov.get('max_new_tokens')}."
    )
    lines.append("")
    lines.append(f"Generated: {metrics.get('generated_at')}")
    lines.append("## Headline metrics (per arm, same items)")
    lines.append("")
    lines.append(
        "| Arm | n | items (primary/negative) | JSON valid | Schema pass | Claim-quote locatability | "
        "Function cue-support (field / any quote) | Track cue-support (field / any quote) | Abstain rate | "
        "Neg-control false positives | Median latency (s) | Peak VRAM (MiB) |"
    )
    lines.append("|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for arm_id in ("A", "B", "C"):
        arm = arms.get(arm_id)
        if arm is None:
            continue
        if arm.get("status") == "NOT_RUN":
            lines.append(
                f"| {arm_id} | — | — | — | — | — | — | — | — | — | — | — |"
            )
            continue
        ev = arm.get("evidence") or {}
        sup = arm.get("support") or {}
        ab = arm.get("abstention") or {}
        nc = arm.get("negative_control") or {}
        lat = arm.get("latency") or {}
        vram = arm.get("peak_vram_mb_max")
        lines.append(
            f"| {arm_id} | {arm.get('n')} | {arm.get('n_primary')}/{arm.get('n_negative')} | "
            f"{_pct(arm.get('json_valid_rate'))} | {_pct(arm.get('schema_pass_rate'))} | "
            f"{_pct(ev.get('claim_locatability_rate'))} ({ev.get('claim_quotes_located')}/{ev.get('claim_quotes_total')}) | "
            f"{_pct(sup.get('function_support_rate'))} / {_pct(sup.get('function_support_any_quote_rate'))} | "
            f"{_pct(sup.get('track_support_rate'))} / {_pct(sup.get('track_support_any_quote_rate'))} | "
            f"{_pct(ab.get('abstain_rate'))} | "
            f"{_pct(nc.get('false_positive_rate'))} ({nc.get('false_positive_count')}/{nc.get('n')}) | "
            f"{_pct(lat.get('median_s'))} | "
            f"{'n/a' if vram is None else f'{vram:.0f}'} |"
        )
    for arm_id, arm in arms.items():
        if arm.get("status") == "NOT_RUN":
            lines.append("")
            lines.append(f"**Arm {arm_id} = NOT_RUN.** {arm.get('reason')}")
    lines.append("")
    lines.append("## Negative-control detail (headline, not a footnote)")
    lines.append("")
    lines.append("| Arm | n negatives | FP (track or R&D class) | FP track only | FP R&D function only | Abstained | UNCLASSIFIED both | Correct rejection |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for arm_id in ("A", "B"):
        arm = arms.get(arm_id)
        if not arm or arm.get("status") == "NOT_RUN":
            continue
        nc = arm.get("negative_control") or {}
        lines.append(
            f"| {arm_id} | {nc.get('n')} | {nc.get('false_positive_count')} | "
            f"{nc.get('track_false_positive_count')} | {nc.get('rnd_function_claim_count')} | "
            f"{nc.get('abstained_count')} | {nc.get('unclassified_both_count')} | "
            f"{nc.get('correct_rejection_count')} |"
        )
    lines.append("")
    lines.append("Definition: a negative-control posting is a real posted role whose **title** declares a "
                 "non-technical occupation (Buyer/Planner, customer service, warehouse, administrative, "
                 "finance, non-technical co-op). False positive = arm asserted a technology track or an "
                 "R&D function class on such a posting.")
    lines.append("")
    lines.append("## Error taxonomy (counts)")
    lines.append("")
    lines.append("| Arm | Error counts |")
    lines.append("|---|---|")
    for arm_id in ("A", "B"):
        arm = arms.get(arm_id)
        if not arm or arm.get("status") == "NOT_RUN":
            continue
        errors = arm.get("error_taxonomy") or {}
        rendered = ", ".join(f"{code}={count}" for code, count in errors.items()) or "(none)"
        lines.append(f"| {arm_id} | {rendered} |")
    lines.append("")
    lines.append("## Internal consistency (no gold standard needed)")
    lines.append("")
    lines.append(
        "A structurally valid payload can still be self-contradictory: a technology track "
        "attached to a `SALES_ADMIN_OTHER` / `UNCLASSIFIED` function class, or "
        "`r_and_d_evidence=true` for such a class. That is a reliability failure "
        "regardless of what the true label is."
    )
    lines.append("")
    lines.append("| Arm | schema-ok items | contradictions | contradiction rate | track-on-commercial | R&D-flag-on-commercial |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for arm_id in ("A", "B"):
        arm = arms.get(arm_id)
        if not arm or arm.get("status") == "NOT_RUN":
            continue
        ic = arm.get("internal_consistency") or {}
        lines.append(
            f"| {arm_id} | {ic.get('n_schema_ok')} | {ic.get('contradiction_count')} | "
            f"{_pct(ic.get('contradiction_rate'))} | {ic.get('track_on_commercial_function_count')} | "
            f"{ic.get('rnd_evidence_on_commercial_function_count')} |"
        )
    lines.append("")
    lines.append("## Explicit non-metrics")
    lines.append("")
    lines.append(f"- Precision / Recall / F1: **{PRECISION_RECALL_F1}**.")
    lines.append(f"- Confidence calibration: **{CONFIDENCE_CALIBRATION}**.")
    lines.append("- Cue-support rates are a conservative deterministic check against committed cue lists; "
                 "a False does not prove a label wrong, and arm A's support is circular by construction.")
    lines.append("")
    if comparison and comparison.get("available"):
        lines.append("## Arm A vs arm B agreement on the shared primary sample")
        lines.append("")
        lines.append(f"- shared primary items: {comparison['n_shared_primary']}")
        lines.append(f"- both arms UNCLASSIFIED (no direction claimed): {comparison['both_unclassified']}")
        lines.append(f"- A UNCLASSIFIED / B labelled: {comparison['a_unclassified_b_labelled']}")
        lines.append(f"- A labelled / B UNCLASSIFIED: {comparison['a_labelled_b_unclassified']}")
        lines.append(f"- both labelled: {comparison['both_labelled']}")
        lines.append(f"- same function class: {comparison['same_function_class_count']}")
        lines.append(f"- same non-UNCLASSIFIED track: {comparison['same_non_unclassified_track_count']}")
        lines.append("")
        lines.append(f"> {comparison['note']}.")
        lines.append("")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------ CLIs
def evaluate_run(
    run_dir: str | Path,
    *,
    data_path: str | Path,
    tracks_config: str | Path | None = None,
    function_config: str | Path | None = None,
    out_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Score every ``predictions_<arm>.jsonl`` in ``run_dir`` against the data file."""
    from .subset import load_postings

    run_dir = Path(run_dir)
    out_dir = Path(out_dir) if out_dir is not None else run_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    postings = {str(row["posting_id"]): row for row in load_postings(str(data_path))}
    tracks = load_track_registry(tracks_config)
    cues = load_function_cues(function_config)

    prediction_files = sorted(run_dir.glob("predictions_*.jsonl"))
    if not prediction_files:
        raise SystemExit(f"no predictions_*.jsonl in {run_dir}")

    arms: dict[str, dict[str, Any]] = {}
    arm_items: dict[str, list[dict[str, Any]]] = {}
    for path in prediction_files:
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        if not records:
            continue
        arm = str(records[0].get("arm") or path.stem.removeprefix("predictions_"))
        items = []
        missing_postings = 0
        for record in records:
            posting = postings.get(str(record.get("posting_id")))
            if posting is None:
                missing_postings += 1
                continue
            items.append(evaluate_record(record, posting, tracks=tracks, function_cues=cues))
        summary = summarise_arm(records, items)
        summary["_items"] = items
        if missing_postings:
            summary["postings_missing_from_data_file"] = missing_postings
        arms[arm] = summary
        arm_items[arm] = items

    arm_c = {"arm": "C", "status": "NOT_RUN", "reason": ARM_C_NOT_RUN_REASON}
    arms["C"] = arm_c

    manifests: dict[str, Any] = {}
    for path in sorted(run_dir.glob("manifest_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        manifests[path.name] = {
            "run_id": payload.get("run_id"),
            "arm": payload.get("arm"),
            "data": payload.get("data"),
            "collection_reports": payload.get("collection_reports"),
            "prompt": payload.get("prompt"),
            "schema_version": payload.get("schema_version"),
            "decoding": payload.get("decoding"),
            "inputs": payload.get("inputs"),
            "model": payload.get("model"),
            "weights_path": payload.get("weights_path"),
            "latency": payload.get("latency"),
            "peak_vram_mb_max": payload.get("peak_vram_mb_max"),
            "environment": payload.get("environment"),
            "gates": payload.get("gates"),
        }

    comparison = compare_arms({k: v for k, v in arms.items() if k in ("A", "B")})
    provenance = _build_provenance(manifests, run_dir)
    # Per-item evaluations are written to their own artefact; metrics.json stays a
    # compact, reviewable summary.
    evaluation_items = {arm: arms[arm].pop("_items") for arm in list(arms) if "_items" in arms[arm]}
    (out_dir / "evaluation_items.json").write_text(
        json.dumps(evaluation_items, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    metrics: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompt_version": _prompt_version_from_manifest(run_dir),
        "provenance": provenance,
        "data_path": str(data_path),
        "arms": arms,
        "manifests": manifests,
        "comparison": comparison,
        "caveats": [
            PRECISION_RECALL_F1,
            CONFIDENCE_CALIBRATION,
            "Negative controls are selected by a declared title pattern; the set is small and is not a "
            "representative sample of all non-technical postings.",
            "Cue-support is a lower-bound deterministic check, not human adjudication; the manual "
            "adjudication table in this directory is the only human judgement in this experiment.",
            "Arm A's evidence support is circular (the evidence span is the rule that fired).",
            "Single snapshot (T0): no trend, no lag test, no claim about the company's R&D direction.",
        ],
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "ARM_TABLE.md").write_text(
        render_arm_table(metrics, comparison), encoding="utf-8"
    )
    _write_adjudication_candidates(out_dir / "adjudication_candidates.md", arm_items)
    return metrics


def _prompt_version_from_manifest(run_dir: Path) -> str | None:
    manifest_paths = sorted(run_dir.glob("manifest*.json"))
    for path in manifest_paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        prompt = payload.get("prompt") or {}
        if prompt.get("prompt_version"):
            return str(prompt["prompt_version"])
        if payload.get("prompt_version"):
            return str(payload["prompt_version"])
    return None


def _write_adjudication_candidates(path: Path, arm_items: Mapping[str, list[dict[str, Any]]]) -> None:
    """Emit a review table: one row per primary item per arm, with the actual quotes.

    The file is a *candidate* table.  The experiment author fills the verdict
    column (AGREE / DISAGREE / UNCERTAIN) in ``MANUAL_ADJUDICATION.md``; nothing
    here is a human label.
    """
    lines = [
        "# Manual adjudication candidates (fill verdicts in MANUAL_ADJUDICATION.md)",
        "",
        "One row per primary posting per arm: assigned function/track, the quote the arm",
        "asserted, whether it was located verbatim, and whether the deterministic cue",
        "check found the declared keyword family. Verdict is deliberately left blank.",
        "",
        "| Arm | posting_id | title | function_class | technology_track | r_and_d | quote | located | cue-support |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in ("A", "B"):
        for item in arm_items.get(arm, []):
            if item["sample"] != "primary" or not item["schema_ok"]:
                continue
            quote = item["claims"][0]["quote"] if item["claims"] else ""
            quote = quote.replace("|", "\\|")
            if len(quote) > 180:
                quote = quote[:177] + "..."
            located = "—"
            if item["claims"]:
                located = "yes" if item["claims"][0]["located"] else "NO"
            support = "n/a"
            if item["technology_track"] != TRACK_FIELD_UNCLASSIFIED:
                support = "yes" if item["track_support"] else "NO"
            elif item["function_class"] != UNCLASSIFIED:
                support = "yes" if item["function_support"] else "NO"
            title = str(item["job_title"]).replace("|", "\\|")
            lines.append(
                f"| {arm} | {item['posting_id']} | {title} | {item['function_class']} | "
                f"{item['technology_track']} | {item['r_and_d_evidence']} | {quote} | {located} | {support} |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score job-text extraction predictions (offline).")
    parser.add_argument("--run-dir", required=True, help="directory containing predictions_<arm>.jsonl")
    parser.add_argument("--data", required=True, help="JSONL snapshot the predictions were made from")
    parser.add_argument("--tracks", default=None, help="config/tracks_device.json (default: repo config)")
    parser.add_argument("--functions", default=None, help="config/recruitment_function_classes.json")
    parser.add_argument("--out", default=None, help="output directory (default: run dir)")
    args = parser.parse_args(list(argv) if argv is not None else None)
    metrics = evaluate_run(
        args.run_dir,
        data_path=args.data,
        tracks_config=args.tracks,
        function_config=args.functions,
        out_dir=args.out,
    )
    for arm, summary in metrics["arms"].items():
        if summary.get("status") == "NOT_RUN":
            print(f"arm {arm}: NOT_RUN")
            continue
        print(
            f"arm {arm}: n={summary['n']} schema={_pct(summary['schema_pass_rate'])} "
            f"locatability={_pct(summary['evidence']['claim_locatability_rate'])} "
            f"neg-FP={_pct(summary['negative_control']['false_positive_rate'])} "
            f"median_latency={summary['latency']['median_s']}s"
        )
    print(f"wrote {Path(args.out or args.run_dir) / 'metrics.json'}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
