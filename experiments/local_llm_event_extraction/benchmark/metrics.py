"""Scoring: turn extraction results into a :class:`MetricReport` that cannot flatter.

Matching protocol (also recorded in every returned report)
----------------------------------------------------------
Event metrics are computed **within each document** with a greedy 1:1 match.  A
predicted event matches a gold event iff

1. ``company.canonical_id`` is equal, **and**
2. ``event_category`` is equal, **and**
3. the dates are compatible: exact string equality when the gold ``event_date``
   is present, and date-agnostic when the gold date is ``null``.

Unmatched asserted events are false positives; unmatched gold events are false
negatives.  ``precision``/``recall``/``f1`` are micro-averaged over events.

A second, category-only greedy pairing exists so that a wrong *entity* or a wrong
*date* is visible as such rather than disappearing into "one fp plus one fn".
Field metrics (entity accuracy, event-date accuracy, published-at accuracy,
citation correctness) are computed over that pairing.

Rates with a zero denominator are ``None`` -- "not measured" -- never ``0.0``.
Counts (tp/fp/fn, taxonomy counts) are counts and may legitimately be zero.

The scorer is arm-agnostic: it consumes ``DatasetCase`` objects and prediction
records, and knows nothing about adapters, prompts or models.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from ..contracts import (
    SCORING_PROTOCOL_VERSION,
    DatasetCase,
    ExtractionResult,
    GoldEvent,
    MetricReport,
)
from ..schema import PARSE_STATUSES, ContractError, EventExtraction, result_from_dict

_ZERO_DENOMINATOR = None  # explicit: a rate with no denominator is not measured

TAXONOMY_KEYS: tuple[str, ...] = (
    "false_positive",
    "false_negative",
    "entity_mismatch",
    "date_mismatch",
    "published_at_mismatch",
    "citation_not_verbatim",
    "citation_not_overlapping",
    "parse_invalid_json",
    "parse_refused",
    "parse_empty",
    "adapter_error",
    "missing_prediction",
    "prediction_decode_error",
    "wrong_abstention",
    "false_assertion",
    "duplicate_event",
)

_WHITESPACE = re.compile(r"\s+")

DEFAULT_SCORING_CONFIG: dict[str, Any] = {
    "require_verbatim_quote": True,
    "min_quote_chars": 8,
    "citation_overlap_min_chars": 24,
}


def _rate(numerator: int | float, denominator: int | float) -> float | None:
    """A rate, or ``None`` when the denominator is zero (not measured)."""
    if not denominator:
        return _ZERO_DENOMINATOR
    return float(numerator) / float(denominator)


def _normalise(text: str) -> str:
    return _WHITESPACE.sub(" ", text.strip().lower())


def _verbatim_supported(quote: str, document_text: str, *, min_quote_chars: int) -> bool:
    quote = quote.strip()
    if len(quote) < min_quote_chars:
        return False
    if quote in document_text:
        return True
    # Formatting-only normalisation (collapsed whitespace, case) is still the
    # same characters in the same order; paraphrases are not.
    return _normalise(quote) in _normalise(document_text)


def _quotes_overlap(gold_quote: str, predicted_quote: str, *, min_chars: int) -> bool:
    gold = _normalise(gold_quote)
    predicted = _normalise(predicted_quote)
    if not gold or not predicted:
        return False
    if gold in predicted or predicted in gold:
        return True
    matcher = difflib.SequenceMatcher(None, gold, predicted, autojunk=False)
    block = matcher.find_longest_match(0, len(gold), 0, len(predicted))
    threshold = max(int(min_chars), len(gold) // 2)
    return block.size >= threshold


def _dates_compatible(gold_date: str | None, predicted_date: str | None) -> bool:
    if gold_date is None:
        return True
    return predicted_date == gold_date


def _asserted_events(result: ExtractionResult | None) -> list[EventExtraction]:
    if result is None or result.parse_status != "ok":
        return []
    return [event for event in result.events if event.status == "extracted"]


def _is_abstention(result: ExtractionResult | None) -> bool:
    """Document-level abstention: no event was asserted at all."""
    return not _asserted_events(result)


@dataclass(frozen=True)
class _NormalisedPrediction:
    case_id: str
    result: ExtractionResult | None
    parse_status: str
    parse_error: str | None
    adapter_error: str | None = None


def _normalise_predictions(
    predictions: Any,
) -> dict[str, _NormalisedPrediction]:
    """Accept runner records, result dicts, ExtractionResults or a mapping thereof."""
    items: list[tuple[str, Any]] = []
    if isinstance(predictions, Mapping):
        for key, value in predictions.items():
            if not isinstance(key, str):
                raise ValueError("prediction mapping keys must be case ids")
            items.append((key, value))
    else:
        for index, item in enumerate(predictions):
            if not isinstance(item, Mapping) or "case_id" not in item:
                raise ValueError(f"prediction[{index}] must be a mapping with a 'case_id'")
            items.append((str(item["case_id"]), item))

    normalised: dict[str, _NormalisedPrediction] = {}
    for case_id, item in items:
        if isinstance(item, ExtractionResult):
            normalised[case_id] = _NormalisedPrediction(case_id, item, item.parse_status, None)
            continue
        if not isinstance(item, Mapping):
            raise ValueError(f"prediction for {case_id!r} must be a mapping or ExtractionResult")
        raw = item.get("result", item)
        parse_error = item.get("parse_error")
        adapter_error = item.get("adapter_error")
        if raw is None:
            status = item.get("parse_status")
            status = status if status in PARSE_STATUSES else "invalid_json"
            normalised[case_id] = _NormalisedPrediction(
                case_id, None, str(status), parse_error, adapter_error
            )
            continue
        if isinstance(raw, ExtractionResult):
            normalised[case_id] = _NormalisedPrediction(
                case_id, raw, raw.parse_status, parse_error
            )
            continue
        if isinstance(raw, Mapping):
            try:
                decoded = result_from_dict(raw)
            except ContractError as exc:
                normalised[case_id] = _NormalisedPrediction(
                    case_id, None, "invalid_json", f"prediction decode error: {exc}"
                )
                continue
            normalised[case_id] = _NormalisedPrediction(
                case_id, decoded, decoded.parse_status, parse_error
            )
            continue
        raise ValueError(f"prediction for {case_id!r} has an unusable 'result' value")
    return normalised


def _greedy_pair(
    gold_events: Sequence[GoldEvent],
    predicted: Sequence[EventExtraction],
    compatible: Any,
) -> tuple[list[tuple[int, int]], list[int]]:
    """Greedy 1:1 pairing in gold order then predicted order.

    Returns ``(pairs, unmatched_predicted_indices)``.  Deterministic, and never
    matches the same predicted event twice.
    """
    used_predictions: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for gold_index, gold in enumerate(gold_events):
        for predicted_index, prediction in enumerate(predicted):
            if predicted_index in used_predictions:
                continue
            if compatible(gold, prediction):
                used_predictions.add(predicted_index)
                pairs.append((gold_index, predicted_index))
                break
    unmatched = [index for index in range(len(predicted)) if index not in used_predictions]
    return pairs, unmatched


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter.get(key, 0)) for key in TAXONOMY_KEYS}


def score_predictions(
    cases: Sequence[DatasetCase],
    predictions: Any,
    config: Mapping[str, Any] | None = None,
) -> MetricReport:
    """Score prediction records for ``cases`` and return a :class:`MetricReport`.

    ``predictions`` may be the runner's JSONL records (mappings with ``case_id``
    and ``result``), a ``case_id -> ExtractionResult`` mapping, or a sequence of
    ``ExtractionResult``-shaped mappings.  Predictions are never repaired.
    """
    scoring = dict(DEFAULT_SCORING_CONFIG)
    scoring.update(dict(config or {}))
    require_verbatim = bool(scoring.get("require_verbatim_quote", True))
    min_quote_chars = int(scoring.get("min_quote_chars", 8))
    overlap_min_chars = int(scoring.get("citation_overlap_min_chars", 24))

    materialised_cases = list(cases)
    normalised = _normalise_predictions(predictions)

    taxonomy: Counter[str] = Counter()
    tp = fp = fn = 0
    scored_documents = 0
    gold_documents = 0
    abstained_documents = 0
    wrong_abstentions = 0
    control_documents = 0
    false_assertions = 0

    pair_count = 0
    entity_matches = 0
    date_denominator = 0
    date_matches = 0
    published_denominator = 0
    published_matches = 0
    citation_denominator = 0
    citation_correct = 0

    category_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"gold": 0, "predicted": 0, "tp": 0}
    )
    source_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"gold": 0, "predicted": 0, "tp": 0}
    )

    for case in materialised_cases:
        record = normalised.get(case.case_id)
        if record is None:
            # A document without a prediction record is not scored: it must not
            # leak into a denominator and turn "not measured" into a zero.
            taxonomy["missing_prediction"] += 1
            continue
        gold_events = list(case.gold_events)
        source_type = case.document.source_type
        for gold in gold_events:
            category_stats[gold.event_category]["gold"] += 1
            source_stats[source_type]["gold"] += 1
        if gold_events:
            gold_documents += 1
        if case.is_negative_control:
            control_documents += 1

        scored_documents += 1
        result = record.result
        if result is None:
            if record.adapter_error:
                taxonomy["adapter_error"] += 1
            elif record.parse_status in ("invalid_json", "refused", "empty"):
                taxonomy[f"parse_{record.parse_status}"] += 1
            else:  # pragma: no cover - defensive
                taxonomy["prediction_decode_error"] += 1
        elif result.parse_status != "ok":
            if result.parse_status in ("invalid_json", "refused", "empty"):
                taxonomy[f"parse_{result.parse_status}"] += 1
        predicted = _asserted_events(result)
        for event in predicted:
            if event.event_category:
                category_stats[event.event_category]["predicted"] += 1
            source_stats[source_type]["predicted"] += 1

        if _is_abstention(result):
            abstained_documents += 1
            if gold_events:
                wrong_abstentions += 1
                taxonomy["wrong_abstention"] += 1
        if case.is_negative_control and predicted:
            false_assertions += 1
            taxonomy["false_assertion"] += 1

        # Duplicate assertions are counted, not silently de-duplicated: a model
        # that emits the same event twice has made an error even if one copy matches.
        signatures: set[tuple[Any, ...]] = set()
        for event in predicted:
            signature = (
                event.company.canonical_id,
                event.event_category,
                event.event_date,
                event.published_at,
            )
            if signature in signatures:
                taxonomy["duplicate_event"] += 1
            signatures.add(signature)

        # Primary matching: entity + category + compatible dates.
        primary_pairs, unmatched_predicted = _greedy_pair(
            gold_events,
            predicted,
            lambda gold, prediction: (
                gold.company_canonical_id == prediction.company.canonical_id
                and gold.event_category == prediction.event_category
                and _dates_compatible(gold.event_date, prediction.event_date)
            ),
        )
        case_tp = len(primary_pairs)
        tp += case_tp
        fp += len(unmatched_predicted)
        fn += len(gold_events) - case_tp
        taxonomy["false_positive"] += len(unmatched_predicted)
        taxonomy["false_negative"] += len(gold_events) - case_tp
        for gold_index, _predicted_index in primary_pairs:
            category_stats[gold_events[gold_index].event_category]["tp"] += 1
            source_stats[source_type]["tp"] += 1

        # Secondary matching (category only) for field-level diagnostics.
        loose_pairs, _loose_unmatched = _greedy_pair(
            gold_events,
            predicted,
            lambda gold, prediction: gold.event_category == prediction.event_category,
        )
        pair_count += len(loose_pairs)
        for gold_index, predicted_index in loose_pairs:
            gold = gold_events[gold_index]
            prediction = predicted[predicted_index]
            if gold.company_canonical_id == prediction.company.canonical_id:
                entity_matches += 1
            else:
                taxonomy["entity_mismatch"] += 1
            if gold.event_date is not None:
                date_denominator += 1
                if prediction.event_date == gold.event_date:
                    date_matches += 1
                else:
                    taxonomy["date_mismatch"] += 1
            if gold.published_at is not None:
                published_denominator += 1
                if prediction.published_at == gold.published_at:
                    published_matches += 1
                else:
                    taxonomy["published_at_mismatch"] += 1
            if gold.evidence_quote:
                citation_denominator += 1
                span_ok = any(
                    (
                        not require_verbatim
                        or _verbatim_supported(
                            span.quote, case.document.text, min_quote_chars=min_quote_chars
                        )
                    )
                    for span in prediction.evidence
                )
                overlap_ok = any(
                    _quotes_overlap(
                        gold.evidence_quote, span.quote, min_chars=overlap_min_chars
                    )
                    for span in prediction.evidence
                )
                if span_ok and overlap_ok:
                    citation_correct += 1
                elif not span_ok:
                    taxonomy["citation_not_verbatim"] += 1
                else:
                    taxonomy["citation_not_overlapping"] += 1

    per_category = {
        category: _group_stats(stats) for category, stats in sorted(category_stats.items())
    }
    per_source_type = {
        source: _group_stats(stats) for source, stats in sorted(source_stats.items())
    }

    precision = _rate(tp, tp + fp)
    recall = _rate(tp, tp + fn)
    if precision is None or recall is None or (precision + recall) == 0:
        f1: float | None = None
    else:
        f1 = 2 * precision * recall / (precision + recall)

    matching_protocol = {
        "version": SCORING_PROTOCOL_VERSION,
        "unit": "events, micro-averaged over documents that have a prediction record",
        "matching": (
            "greedy 1:1 within each document: gold events in dataset order, predicted "
            "events in output order, first compatible unused pair wins"
        ),
        "match_requires": [
            "predicted.company.canonical_id == gold.company_canonical_id",
            "predicted.event_category == gold.event_category",
            "dates compatible: exact equality when gold.event_date is present; "
            "date-agnostic when gold.event_date is null",
        ],
        "field_protocol": (
            "entity/date/published-at/citation metrics use a second greedy pairing that "
            "requires only event_category, so a wrong entity or date is reported as such "
            "instead of collapsing into fp+fn"
        ),
        "date_rule": (
            "exact string equality on YYYY / YYYY-MM / YYYY-MM-DD when the gold date is "
            "present; a null gold date is date-agnostic"
        ),
        "citation_rule": (
            "correct when at least one predicted evidence quote is a verbatim substring "
            "of the document (whitespace/case-normalised fallback) and overlaps the gold "
            "evidence quote (containment, or longest common substring >= max(24, half the "
            "gold quote length))"
        ),
        "abstention_rule": (
            "a document abstains when it asserts zero extracted events (no events, all "
            "abstained, or a parse failure); wrong_abstention is an abstention on a "
            "document that has gold events"
        ),
        "negative_control_rule": (
            "a case with expected_abstain=True and no gold events; asserting any event on "
            "it is a false assertion"
        ),
        "duplicate_rule": "identical asserted events within one document are counted in the error taxonomy",
        "zero_denominator": "null (not measured), never 0.0",
        "support": "documents that have a prediction record",
        "seeds": list(scoring.get("seeds") or ()),
    }

    return MetricReport(
        matching_protocol=matching_protocol,
        support=scored_documents,
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        entity_match_accuracy=_rate(entity_matches, pair_count),
        event_date_accuracy=_rate(date_matches, date_denominator),
        published_at_accuracy=_rate(published_matches, published_denominator),
        citation_correctness_rate=_rate(citation_correct, citation_denominator),
        abstention_rate=_rate(abstained_documents, scored_documents),
        wrong_abstention_rate=_rate(wrong_abstentions, gold_documents),
        false_assertion_rate=_rate(false_assertions, control_documents),
        parse_failure_rate=_rate(
            sum(
                taxonomy[key]
                for key in ("parse_invalid_json", "parse_refused", "parse_empty")
            ),
            scored_documents,
        ),
        per_category=per_category,
        per_source_type=per_source_type,
        error_taxonomy=_counter_dict(taxonomy),
    )


def _group_stats(stats: Mapping[str, int]) -> dict[str, Any]:
    gold = int(stats.get("gold", 0))
    predicted = int(stats.get("predicted", 0))
    true_positives = int(stats.get("tp", 0))
    return {
        "gold": gold,
        "predicted": predicted,
        "tp": true_positives,
        "fp": predicted - true_positives,
        "fn": gold - true_positives,
        "precision": _rate(true_positives, predicted),
        "recall": _rate(true_positives, gold),
    }


__all__ = ["DEFAULT_SCORING_CONFIG", "TAXONOMY_KEYS", "score_predictions"]
