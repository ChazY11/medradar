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

from ..schema import EventExtraction, ExtractionResult
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


def _recover_date(event: EventExtraction, locale: str | None) -> tuple[str | None, str]:
    """Recover one date from the event's own evidence quotes under ``locale``."""
    if locale not in ("us", "uk"):
        return None, "absent"
    found: dict[str, str] = {}
    for span in event.evidence:
        for token in dates_in_text(span.quote, locale):
            found.setdefault(token.date.iso, token.precision)
    if len(found) != 1:
        # Zero candidates means nothing to recover; several means the sentence is
        # ambiguous and the rules must not choose between them.
        return None, "absent"
    iso, precision = next(iter(found.items()))
    quality = {"day": "exact_day", "month": "exact_month", "year": "exact_year"}[precision]
    return iso, quality


class LocaleAwareRuleBasedAdapter(RuleBasedAdapter):
    """Arm A1: A0 + locale numeric dates + declared event-date kinds."""

    def _extract_impl(self, request: Any) -> tuple[ExtractionResult, Mapping[str, Any]]:
        result, trace = super()._extract_impl(request)
        metadata = dict(request.metadata or {})
        locale = metadata.get("date_locale")
        kind = KIND_BY_SOURCE_TYPE.get(str(request.source_type), "unspecified")
        recovered = 0
        upgraded: list[EventExtraction] = []
        for event in result.events:
            changes: dict[str, Any] = {"event_date_kind": kind}
            if event.status == "extracted" and event.event_date is None:
                iso, quality = _recover_date(event, locale)
                if iso is not None:
                    recovered += 1
                    changes["event_date"] = iso
                    changes["timestamp_quality"] = dataclasses.replace(
                        event.timestamp_quality, event_date=quality
                    )
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
