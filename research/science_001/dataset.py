"""Build the analysis dataset: one row per disclosure event plus forward labels.

Design constraints enforced here
--------------------------------
* The label of an event uses only *later* filings and only SEC-assigned item
  codes / form types, never the event's own prose. Input and outcome therefore
  cannot be built from the same bytes.
* An event is only kept if its forward window is fully observable inside the
  sample window; otherwise the label would silently encode "we stopped
  collecting" as "nothing happened".
* 8-K/A amendments do not become separate observation units: they amend an
  earlier event and would double-count it. They are linked back to the original
  and reported separately.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Iterable, Sequence

HORIZON_DAYS = 90

#: A "technology-relevant corporate event" in the sense used by this study:
#: the issuer entered a material definitive agreement, or completed an
#: acquisition/disposition. Both are discrete, SEC-assigned item codes, so the
#: outcome is not derived from any text model.
TECH_EVENT_ITEMS: tuple[str, ...] = ("1.01", "2.01")

#: Placebo outcome, expected to be unrelated to R&D/technology prose: submission
#: of matters to a vote of security holders (an annual-meeting ritual).
PLACEBO_ITEMS: tuple[str, ...] = ("5.07",)

#: Routine disclosure items, used as an activity control rather than an outcome.
ROUTINE_ITEMS: tuple[str, ...] = ("2.02", "7.01", "8.01", "9.01")


def parse_items(raw: str | None) -> set[str]:
    """Normalise the API items field ("1.01,2.01,9.01") to a set of codes."""
    if not raw:
        return set()
    return {part.strip() for part in str(raw).replace(";", ",").split(",") if part.strip()}


def _day(value: str) -> dt.date:
    return dt.date.fromisoformat(value[:10])


def _utc(value: str) -> dt.datetime:
    text = value.replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)


#: "Month D, YYYY" anywhere in the amendment prose. Bounded per the archive's
#: own convention; no locale guessing.
_MONTH_DATE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2}),\s+(\d{4})\b")
_ACCESSION = re.compile(r"\b(\d{10}-\d{2}-\d{6})\b")
#: Words that make a nearby date likely to be a *filing* date rather than some
#: other event date (annual-meeting date, fiscal period end, ...).
_FILING_CONTEXT = re.compile(r"(?i)(form\s*8-?k|original report|amend|filed with|"
                             r"filed on|previously filed|current report)")


def _month_dates_near_filing_context(text: str, window: int = 320) -> set[dt.date]:
    """Dates that appear close to filing/amendment vocabulary.

    Proximity is used instead of a grammatical rule because filers write the
    reference both ways ('filed on May 2, 2023' and 'On May 2, 2023, Abbott
    filed ...'), and a strict direction-sensitive pattern silently misses half
    of them.
    """
    found: set[dt.date] = set()
    contexts = [match.start() for match in _FILING_CONTEXT.finditer(text)]
    if not contexts:
        return found
    for match in _MONTH_DATE.finditer(text):
        start, end = match.span()
        if any(abs(position - start) <= window for position in contexts):
            try:
                found.add(dt.datetime.strptime(
                    "%s %s, %s" % (match.group(1), match.group(2), match.group(3)),
                    "%B %d, %Y").date())
            except ValueError:
                continue
    return found


def link_amendments(rows: Sequence[dict[str, Any]],
                    prose_by_accession: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Link each 8-K/A to the original 8-K it amends, with graded evidence.

    Evidence sources in decreasing strength:

    high          the amendment text quotes the original accession number;
    medium        the amendment text names a filing date that matches exactly one
                  candidate, and the candidate's SEC item set equals the
                  amendment's item set (filers restate the original items on an
                  8-K/A, so agreement is corroboration, not decoration);
    low           no textual corroboration: the closest preceding 8-K of the
                  same issuer carrying the identical item set;
    low_unverified no item-set match either: the closest preceding 8-K, recorded
                  as an assumption and excluded from any scientific use;
    none          no earlier 8-K exists at all.

    Only the first two tiers are textual evidence. Every tier is reported, so a
    reader can see how much of the amendment graph is actually established.
    """
    by_issuer: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_issuer.setdefault(row["issuer"], []).append(row)
    links: dict[str, dict[str, Any]] = {}

    for row in rows:
        if row["form"] != "8-K/A":
            continue
        text = prose_by_accession.get(row["accession"], "")
        candidates = [r for r in by_issuer.get(row["issuer"], [])
                      if r["form"] == "8-K" and r["filing_date"] < row["filing_date"]]
        item_set = parse_items(row.get("items_raw"))
        link: dict[str, Any] | None = None

        if text and candidates:
            known = {r["accession"]: r for r in candidates}
            quoted = {a for a in _ACCESSION.findall(text) if a in known}
            if len(quoted) == 1:
                target = known[quoted.pop()]
                link = {"amends_accession": target["accession"],
                        "amends_filing_date": target["filing_date"],
                        "basis": "accession_quoted_in_amendment",
                        "confidence": "high",
                        "items_match": parse_items(target.get("items_raw")) == item_set,
                        "evidence": "accession number reproduced in the amendment text"}
            if link is None:
                referenced = _month_dates_near_filing_context(text)
                dated = [r for r in candidates if _day(r["filing_date"]) in referenced]
                if len(dated) > 1 and item_set:
                    dated = [r for r in dated if parse_items(r.get("items_raw")) == item_set]
                if len(dated) == 1:
                    target = dated[0]
                    link = {"amends_accession": target["accession"],
                            "amends_filing_date": target["filing_date"],
                            "basis": "date_reference_in_amendment",
                            "confidence": "medium",
                            "items_match": parse_items(target.get("items_raw")) == item_set,
                            "evidence": "a filing date named in the amendment text"}
                elif len(dated) > 1:
                    link = {"amends_accession": None, "amends_filing_date": None,
                            "basis": "ambiguous_date_reference",
                            "confidence": "none",
                            "items_match": None,
                            "evidence": "%d candidates share the referenced date" % len(dated)}

        if link is None:
            same_items = [r for r in candidates
                          if item_set and parse_items(r.get("items_raw")) == item_set]
            if same_items:
                target = max(same_items, key=lambda r: r["filing_date"])
                link = {"amends_accession": target["accession"],
                        "amends_filing_date": target["filing_date"],
                        "basis": "item_set_proximity",
                        "confidence": "low",
                        "items_match": True,
                        "evidence": "no date reference resolved; identical SEC item set"}
            elif candidates:
                target = max(candidates, key=lambda r: r["filing_date"])
                link = {"amends_accession": target["accession"],
                        "amends_filing_date": target["filing_date"],
                        "basis": "previous_filing_fallback",
                        "confidence": "low_unverified",
                        "items_match": False,
                        "evidence": "assumption only; no item-set or textual support"}
            else:
                link = {"amends_accession": None, "amends_filing_date": None,
                        "basis": "unresolved", "confidence": "none",
                        "items_match": None, "evidence": "no earlier 8-K of this issuer"}
        links[row["accession"]] = link
    return links


def _acceptance_of(row: dict[str, Any],
                    extracted: dict[str, dict[str, Any]]) -> dt.datetime | None:
    """Acceptance instant for label construction.

    Prefers the verified archive-derived value. Falls back to the API value so
    that a filing we failed to download still counts as a neighbour: a missing
    download must never be silently reinterpreted as "no event happened".
    """
    record = extracted.get(row["accession"]) or {}
    if record.get("acceptance_utc"):
        return _utc(record["acceptance_utc"])
    if row.get("acceptance_api"):
        try:
            return _utc(row["acceptance_api"])
        except ValueError:
            return None
    return None


def build_dataset(panel_rows: Sequence[dict[str, Any]],
                  extracted: dict[str, dict[str, Any]],
                  frame_end: dt.date = dt.date(2026, 9, 30),
                  horizon_days: int = HORIZON_DAYS) -> dict[str, Any]:
    """Join metadata + extracted evidence, then attach forward outcome labels."""
    by_issuer: dict[str, list[dict[str, Any]]] = {}
    for row in panel_rows:
        row["_acceptance"] = _acceptance_of(row, extracted)
        by_issuer.setdefault(row["issuer"], []).append(row)

    dataset: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for row in panel_rows:
        accession = row["accession"]
        record = extracted.get(accession)
        if record is None:
            dropped.append({"accession": accession, "reason": "not_fetched"})
            continue
        if record.get("tier") not in ("A_acceptance_verified", "A2_acceptance_header_only",
                                      "B_acceptance_api_only"):
            dropped.append({"accession": accession, "reason": "unusable_time_grade",
                            "tier": record.get("tier")})
            continue
        if row["form"] != "8-K":
            continue  # amendments are not observation units
        acceptance = _utc(record["acceptance_utc"])
        horizon_end = acceptance + dt.timedelta(days=horizon_days)
        if horizon_end.date() > frame_end:
            dropped.append({"accession": accession, "reason": "forward_window_censored",
                            "horizon_end": horizon_end.date().isoformat()})
            continue

        same_issuer = [other for other in by_issuer[row["issuer"]]
                       if other.get("_acceptance") is not None]
        forward = [other for other in same_issuer
                   if other["accession"] != accession
                   and acceptance < other["_acceptance"] <= horizon_end]
        forward_items = set()
        for other in forward:
            forward_items |= parse_items(other["items_raw"])
        prior_start = acceptance - dt.timedelta(days=horizon_days)
        prior = [other for other in same_issuer
                 if prior_start <= other["_acceptance"] < acceptance]

        feature_row = {
            "issuer": row["issuer"],
            "ticker": row["ticker"],
            "cik": row["cik"],
            "accession": accession,
            "form": row["form"],
            "filing_date": row["filing_date"],
            "report_date": row["report_date"],
            "acceptance_utc": record["acceptance_utc"],
            "acceptance_offset_hours": record["offset_hours"],
            "time_tier": record["tier"],
            "public_interval_seconds": record.get("public_interval_seconds"),
            "items": "|".join(sorted(parse_items(row["items_raw"]))),
            "is_earnings": int("2.02" in parse_items(row["items_raw"])),
            "n_forward_events": len(forward),
            "n_prior_events": len(prior),
            "label_tech_event": int(bool(forward_items & set(TECH_EVENT_ITEMS))),
            "label_placebo": int(bool(forward_items & set(PLACEBO_ITEMS))),
            "label_any_8k": int(len(forward) > 0),
            "words": record.get("words", 0),
            "n_documents": record.get("n_documents", 0),
            "exhibit_share": record.get("exhibit_share", 0.0),
            "rd_per_1k": record.get("rd_per_1k", 0.0),
            "tech_per_1k": record.get("tech_per_1k", 0.0),
            "dev_per_1k": record.get("dev_per_1k", 0.0),
            "rd_hits": record.get("rd_hits", 0),
            "tech_hits": record.get("tech_hits", 0),
            "amends_accession": None,
        }
        dataset.append(feature_row)

    # Drop events whose own prose was empty (parse failure) rather than imputing.
    kept: list[dict[str, Any]] = []
    for row in dataset:
        if row["words"] < 50:
            dropped.append({"accession": row["accession"], "reason": "too_few_words",
                            "words": row["words"]})
            continue
        kept.append(row)
    kept.sort(key=lambda r: (r["issuer"], r["acceptance_utc"]))
    ledger: dict[str, int] = {}
    for row in dropped:
        ledger[row["reason"]] = ledger.get(row["reason"], 0) + 1
    for row in kept:
        row.pop("_acceptance", None)
    return {"rows": kept, "dropped": dropped, "drop_ledger": ledger,
            "horizon_days": horizon_days}
