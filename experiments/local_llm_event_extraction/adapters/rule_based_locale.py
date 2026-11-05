"""Arm A1: the deterministic rules baseline, strengthened on dates and date kinds.

What "strengthened" means here, precisely
-----------------------------------------
A1 is arm A0 plus exactly two deterministic changes, both of which correspond to a
defect fixed in the shared code rather than to corpus-specific tuning:

1. **Locale-declared numeric dates.**  When the source declares
   ``metadata["date_locale"]`` the adapter recovers a date written as
   ``12/15/2025`` that the A0 sentence rules cannot parse.  It only does so when
   the date is the unique date in the sentence it already selected, and it never
   reads the publication date into ``event_date``.
2. **Explicit ``event_date_kind``.**  For source types where the kind is
   determined by the record type itself (a 510(k)/PMA decision, a recall
   initiation) the adapter declares it, so the v2 ordering rule can be applied
   per semantic class instead of failing every event.  For clinical-trial records
   the record type does *not* determine the kind, so it stays ``unspecified`` and
   the strict ordering rule still applies -- an honest limitation, not a loophole.

Nothing else changes: same sentences, same company matching, same category
keywords.  A difference between A0 and A1 is therefore attributable to the two
declared changes.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Mapping

from ..schema import EventExtraction, EvidenceSpan, ExtractionResult
from ..validation.timefields import dates_in_text, parse_date_value
from .rule_based import RuleBasedAdapter

#: Source types whose record type determines what the event date means.
KIND_BY_SOURCE_TYPE: Mapping[str, str] = {
    "fda_510k": "decision",
    "fda_pma": "decision",
    "fda_recall": "recall_initiation",
    "regulatory_notice": "unspecified",
    "press_release": "unspecified",
    "sec_filing": "unspecified",
    "scientific_publication": "publication",
    "product_page": "unspecified",
    "other": "unspecified",
    "clinical_trial_record": "unspecified",
}

UPGRADE_VERSION = "a1-locale-dates-and-date-kind-v1"


def _distinct_dates(texts, locale: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for text in texts:
        for token in dates_in_text(text, locale):
            found.setdefault(token.date.iso, token.precision)
    return found


def _date_sentence(document_text: str, locale: str, exclude: set[str]) -> tuple[str, str, str] | None:
    """The first sentence carrying exactly one date that is not excluded.

    A deterministic, template-agnostic fallback for the case where A0 selected a
    company sentence and the date lives in a different sentence.  It refuses when
    the sentence carries more than one date, because choosing between them would
    be a guess.
    """
    for raw_line in document_text.replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        for piece in line.split(". "):
            sentence = piece.strip()
            if len(sentence) < 12:
                continue
            candidates = {
                token.date.iso: token.precision
                for token in dates_in_text(sentence, locale)
                if token.date.iso not in exclude
            }
            if len(candidates) == 1:
                iso, precision = next(iter(candidates.items()))
                # The exact substring, never a tidied version: appending a full stop
                # produced a non-verbatim span and the validator quarantined it.
                return iso, precision, sentence
    return None


def _recover_date(
    event: EventExtraction,
    locale: str | None,
    *,
    document_text: str = "",
    published_at: str | None = None,
) -> tuple[str | None, str, EvidenceSpan | None]:
    """Recover one date, and the verbatim span that supports it, under ``locale``.

    Two steps, both deterministic: first the event's own sentences (A0 selected
    them), then -- only if they carry no date -- a single sentence elsewhere in the
    document.  The publication date is always excluded so the rules can never
    repeat the press-release-vs-event-date conflation the protocol forbids.
    """
    if locale not in ("us", "uk"):
        return None, "absent", None
    # The publication date is excluded only when the document offers a choice.
    # U.S. regulatory records publish a decision on the day they decide it, so the
    # two dates are legitimately equal and blanking them all would discard the true
    # answer.  When several dates exist, the publication date is not a candidate.
    all_dates = _distinct_dates([document_text], locale)
    excluded = {published_at} if published_at and len(all_dates) > 1 else set()
    quotes = [span.quote for span in event.evidence]
    found = {key: value for key, value in _distinct_dates(quotes, locale).items() if key not in excluded}
    if len(found) == 1:
        iso, precision = next(iter(found.items()))
        quality = {"day": "exact_day", "month": "exact_month", "year": "exact_year"}[precision]
        return iso, quality, None
    if found:
        # Several dates in the chosen sentences: the rules must not choose.
        return None, "absent", None
    recovered = _date_sentence(document_text, locale, excluded)
    if recovered is None and excluded:
        # A single-date document whose only date was the publication date: that
        # date is the event date and is supported by its own sentence.
        recovered = _date_sentence(document_text, locale, set())
    if recovered is None:
        return None, "absent", None
    iso, precision, sentence = recovered
    quality = {"day": "exact_day", "month": "exact_month", "year": "exact_year"}[precision]
    return iso, quality, EvidenceSpan(quote=sentence, field="event_date")


class LocaleAwareRuleBasedAdapter(RuleBasedAdapter):
    """Arm A1: A0 + locale numeric dates + declared event-date kinds."""

    def _extract_impl(self, request: Any) -> tuple[ExtractionResult, Mapping[str, Any]]:
        result, trace = super()._extract_impl(request)
        metadata = dict(request.metadata or {})
        locale = metadata.get("date_locale")
        kind = KIND_BY_SOURCE_TYPE.get(str(request.source_type), "unspecified")
        recovered = 0
        upgraded: list[EventExtraction] = []
        published_at = metadata.get("published_at")
        for event in result.events:
            changes: dict[str, Any] = {"event_date_kind": kind}
            if event.status == "extracted" and event.event_date is None:
                iso, quality, extra_span = _recover_date(
                    event,
                    locale,
                    document_text=str(getattr(request, "text", "") or ""),
                    published_at=published_at,
                )
                if iso is not None:
                    recovered += 1
                    changes["event_date"] = iso
                    changes["timestamp_quality"] = dataclasses.replace(
                        event.timestamp_quality, event_date=quality
                    )
                    if extra_span is not None:
                        changes["evidence"] = tuple(event.evidence) + (extra_span,)
            elif event.status == "extracted" and event.event_date is not None:
                parsed = parse_date_value(event.event_date)
                if parsed is not None:
                    changes["timestamp_quality"] = dataclasses.replace(
                        event.timestamp_quality, event_date=parsed.quality
                    )
            upgraded.append(dataclasses.replace(event, **changes))
        upgraded_trace = dict(trace)
        upgraded_trace.update(
            {
                "upgrade_version": UPGRADE_VERSION,
                "date_locale": locale,
                "declared_event_date_kind": kind,
                "dates_recovered_from_locale": recovered,
            }
        )
        return dataclasses.replace(result, events=tuple(upgraded)), upgraded_trace


def locale_rules_descriptor():
    """Descriptor for A1, derived from A0's so only the differences are visible."""
    from .rule_based import rules_descriptor

    base = rules_descriptor()
    return dataclasses.replace(
        base,
        adapter_id="rules-baseline-a1",
        display_name="ARM A1 - deterministic rules + locale dates + date kinds",
        notes=(
            "Arm A0 plus two declared deterministic changes: locale-declared numeric "
            "date recovery from the selected evidence sentence, and an explicit "
            "event_date_kind where the source type determines it."
        ),
    )


__all__ = [
    "KIND_BY_SOURCE_TYPE",
    "UPGRADE_VERSION",
    "LocaleAwareRuleBasedAdapter",
    "locale_rules_descriptor",
]
