"""Deterministic applicant-entity universe for the research lane.

Why this module exists
----------------------
``data/research.sqlite`` holds 55,090 device events (31,219 510(k) + 23,871
PMA, 2016-11 .. 2026-10).  The hand-curated roster in
``config/companies_device.json`` (51 parents) resolves only 16.9% of 510(k)
rows, and two of the five project-mission focus companies (**Shenzhen
Mindray**, **Dräger**) are not in that roster at all, so every one of their
rows is unmatched by construction.

Fuzzy matching is deliberately *not* used here: a false merge silently poisons
every downstream label.  This module instead builds a **deterministic legal-
entity universe** straight from ``events.applicant_raw``: one entity per
normalised applicant string, with the raw variants that produced it.  Corporate
*parent* aggregation is a separate, explicitly labelled reporting view (see
``resolve_entities``) keyed on curated aliases; it never rewrites entity keys.

Construction rules (``applicant_normalise_v1``)
-----------------------------------------------
``normalise_applicant`` applies exactly these steps, in this order, and nothing
else:

1. Unicode NFKD compatibility decomposition, then remove combining marks
   (so ``Dräger`` -> ``DRAGER``, ``Sàrl`` -> ``SARL``).  This is a deterministic
   character fold, not a similarity match.
2. Upper-case.
3. Table-driven pre-substitutions (``_PRE_SUBSTITUTIONS``): dotted / slashed
   legal forms are joined so the suffix table can see them, e.g.
   ``A/S`` -> ``AS``, ``S.A.`` -> ``SA``, ``K.K.`` -> ``KK``,
   ``D.B.A.`` -> ``DBA``.
4. Replace every non-alphanumeric character with a space and collapse runs of
   whitespace (punctuation, ``&``, ``+``, ``.``, ``-``, ``_`` all become
   separators).
5. Cut the string at the first *descriptive clause* marker
   (``_CLAUSE_MARKERS``): ``FORMERLY``, ``DBA``, ``DOING BUSINESS AS``, ``FKA``,
   ``AKA``, ``NKA``.  A former name or trade name is not the registered
   applicant name; the prefix is kept.
6. Drop a leading article ``THE``.
7. Repeatedly strip trailing corporate-suffix tokens from
   ``CORPORATE_SUFFIX_TOKENS`` (``INC``, ``LLC``, ``GMBH``, ``AG``, ``KGAA``,
   ``CO``, ...).  Only tokens at the very end are stripped, so a suffix used in
   the middle of a registered name is preserved.
8. If steps 5-7 would consume the *entire* name (e.g. the raw string is just
   ``"Ltd."``), keep the punctuation-normalised form instead of returning an
   empty string.  An empty raw string maps to ``""`` and is bucketed as
   ``UNKNOWN APPLICANT`` at build time so no event is ever lost.

Legal-entity granularity is preserved: two names that differ in a substantive
token stay two entities even when one is a subsidiary of the other (``MEDTRONIC
VASCULAR`` != ``MEDTRONIC NEUROMODULATION``).  The one documented merge is
*suffix-only*: ``ACME MEDICAL INC`` and ``ACME MEDICAL GMBH`` both normalise to
``ACME MEDICAL`` and therefore belong to one entity.  That cross-legal-form
collapse is the accepted cost of suffix stripping; it is listed as a limitation
in ``docs/research/UNIVERSE.md``.

Everything is sorted before it is written, so the same (database, config) input
yields a byte-identical ``config/universe_v1.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "universe_v1"
NORMALISATION_VERSION = "applicant_normalise_v1"
MATERIAL_EVENT_RULE = (
    "material = one 510(k) clearance or one original PMA approval; PMA "
    "supplements (payload.supplement_number non-empty) are administrative "
    "follow-ups and are counted in n_events but not in n_material"
)
SELECTION_RULE = (
    "select_cohort: eligible entities need n_material >= min_material_events and "
    "active_years >= min_active_years; rank by (n_material desc, n_events desc, "
    "entity_key asc) and keep the first max_entities"
)
DEFAULT_MIN_EVENTS = 2
DEFAULT_MIN_MATERIAL_EVENTS = 3
DEFAULT_MIN_ACTIVE_YEARS = 2
DEFAULT_MAX_COHORT = 200
UNKNOWN_APPLICANT = "UNKNOWN APPLICANT"

#: Corporate legal-form tokens stripped from the END of a normalised name.
#: Multi-word forms are reduced to these single tokens by the pre-substitution
#: table above (e.g. ``GMBH & CO KG`` -> ``GMBH CO KG`` -> all three stripped).
CORPORATE_SUFFIX_TOKENS: tuple[str, ...] = (
    "INC", "INCORPORATED", "LLC", "LTD", "LIMITED", "CORP", "CORPORATION",
    "CO", "COMPANY", "GMBH", "AG", "SA", "SAS", "SARL", "SPA", "BV", "NV",
    "AB", "AS", "OY", "OYJ", "PTY", "LP", "LLP", "KG", "KK", "PTE", "SDN",
    "BHD", "SRL", "SL", "SE", "KGAA", "BVBA", "CV", "PLC", "ULC", "LTDA",
    "PJSC", "OJSC", "CJSC", "JSC", "ZOO", "DOO", "OOO",
)

#: Dotted / slashed legal forms joined before punctuation stripping so that the
#: suffix table sees one token.  Applied longest source first on the upper-cased
#: text (so ``S.A.S.`` is not clipped by the shorter ``S.A.`` rule).
_PRE_SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("FORMERLY KNOWN AS", "FORMERLY"),
    ("DOING BUSINESS AS", "DBA"),
    ("L.L.C.", "LLC"),
    ("L.P.", "LP"),
    ("L.P", "LP"),
    ("A/S", "AS"),
    ("S.A.S.", "SAS"),
    ("S.A.R.L.", "SARL"),
    ("A.S.", "AS"),
    ("A.G.", "AG"),
    ("K.K.", "KK"),
    ("S.A.", "SA"),
    ("S.R.L.", "SRL"),
    ("S.P.A.", "SPA"),
    ("B.V.", "BV"),
    ("N.V.", "NV"),
    ("K.G.", "KG"),
    ("P.T.E.", "PTE"),
    ("D.B.A.", "DBA"),
    ("D/B/A", "DBA"),
)
#: Deterministic application order: longest source string first, then source.
_PRE_SUBSTITUTIONS_ORDERED: tuple[tuple[str, str], ...] = tuple(
    sorted(_PRE_SUBSTITUTIONS, key=lambda pair: (-len(pair[0]), pair[0]))
)

#: Descriptive clauses that are not part of the registered applicant name; the
#: name is cut at the first marker and the prefix kept.
_CLAUSE_MARKERS: tuple[tuple[str, ...], ...] = (
    ("FORMERLY",),
    ("DBA",),
    ("DOING", "BUSINESS", "AS"),
    ("FKA",),
    ("AKA",),
    ("NKA",),
)

_SUFFIX_SET = frozenset(CORPORATE_SUFFIX_TOKENS)

#: The five focus companies required by the project mission.  Three are already
#: in the curated roster; Dräger and Mindray are not, which is exactly the gap
#: this module records and closes.  ``aliases`` are normalised-form fallbacks so
#: the focus view also catches FDA transcription variants (``Draegerwerk`` vs
#: ``Drägerwerk``).  Curated aliases are unioned with these when the company is
#: in the roster.
FOCUS_COMPANIES: dict[str, dict[str, Any]] = {
    "medtronic": {"display_name": "Medtronic", "aliases": ("MEDTRONIC",)},
    "ge_healthcare": {
        "display_name": "GE HealthCare",
        "aliases": ("GE HEALTHCARE", "GE MEDICAL SYSTEMS"),
    },
    "philips": {"display_name": "Philips", "aliases": ("PHILIPS",)},
    "draeger": {
        "display_name": "Dräger",
        "aliases": ("DRAEGER", "DRAEGERWERK", "DRAGERWERK"),
    },
    "mindray": {"display_name": "Mindray", "aliases": ("MINDRAY",)},
}


# --------------------------------------------------------------- normalisation
def _strip_marks(text: str) -> str:
    """NFKD-decompose and drop combining marks (diacritic fold)."""
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def _tokenise(raw: str) -> list[str]:
    """Steps 2-4 of the normalisation: upper-case, substitute, split on punctuation."""
    text = _strip_marks(str(raw or "")).upper()
    for source, target in _PRE_SUBSTITUTIONS_ORDERED:
        text = text.replace(source, target)
    return "".join(char if char.isalnum() else " " for char in text).split()


def _cut_clause(tokens: list[str]) -> list[str]:
    """Step 5: remove a trailing descriptive clause (former/trade name)."""
    for marker in _CLAUSE_MARKERS:
        width = len(marker)
        for index in range(1, len(tokens) - width + 1):
            if tuple(tokens[index:index + width]) == marker:
                head = tokens[:index]
                # "X MEDICAL ALSO DOING BUSINESS AS Y" -> drop the dangling ALSO.
                while head and head[-1] == "ALSO":
                    head.pop()
                return head
    return tokens


def normalise_applicant(raw: str | None) -> str:
    """Canonical applicant form for one raw FDA applicant string.

    Deterministic, table-driven and idempotent (``normalise(normalise(x)) ==
    normalise(x)``).  See the module docstring for the exact rule order.  Two
    raw strings are the *same legal entity* iff this function returns the same
    value; no fuzzy or substring matching is performed here.
    """
    tokens = _tokenise(raw)
    if not tokens:
        return ""
    tokens = _cut_clause(tokens)
    if tokens and tokens[0] == "THE":
        tokens = tokens[1:]
    stripped = list(tokens)
    while stripped and stripped[-1] in _SUFFIX_SET:
        stripped.pop()
    if not stripped:
        # Step 8: never return empty for a non-empty raw string.
        return " ".join(tokens)
    return " ".join(stripped)


def entity_key(normalised: str) -> str:
    """Stable key: lower-case ASCII slug of the normalised name + 8-hex digest.

    The digest is ``sha1(normalised)`` so the key is collision-safe for the
    universe size and independent of insertion order.
    """
    slug_chars = [
        char if ("a" <= char <= "z" or "0" <= char <= "9") else "-"
        for char in normalised.lower()
    ]
    slug = "-".join(part for part in "".join(slug_chars).split("-") if part)
    slug = slug[:40].strip("-")
    digest = hashlib.sha1(normalised.encode("utf-8")).hexdigest()[:8]
    return f"{slug or 'entity'}-{digest}"


# ------------------------------------------------------------------- indexing
def _index_events(events: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group events by normalised applicant.

    One pass; every aggregate below is order-independent, so shuffling the
    event iterable cannot change the output.
    """
    index: dict[str, dict[str, Any]] = {}
    for event in events:
        raw = str(event.get("applicant_raw") or "")
        normalised = normalise_applicant(raw) or UNKNOWN_APPLICANT
        stats = index.get(normalised)
        if stats is None:
            stats = {
                "normalised": normalised,
                "members": Counter(),
                "n_events": 0,
                "n_510k": 0,
                "n_pma": 0,
                "n_material": 0,
                "first_date": "",
                "last_date": "",
                "active_years": set(),
                "tracks": Counter(),
                "sources": set(),
                "n_curated_linked": 0,
            }
            index[normalised] = stats
        stats["n_events"] += 1
        stats["members"][raw if raw else "(blank applicant)"] += 1
        kind = str(event.get("kind") or "")
        supplement = str(event.get("supplement_number") or "").strip()
        if kind == "510k":
            stats["n_510k"] += 1
            stats["n_material"] += 1
        elif kind == "pma":
            stats["n_pma"] += 1
            if not supplement:
                stats["n_material"] += 1
        if event.get("company_key"):
            stats["n_curated_linked"] += 1
        date = str(event.get("event_date") or "")
        if date:
            if not stats["first_date"] or date < stats["first_date"]:
                stats["first_date"] = date
            if not stats["last_date"] or date > stats["last_date"]:
                stats["last_date"] = date
            year = date[:4]
            if len(year) == 4 and year.isdigit():
                stats["active_years"].add(year)
        track = str(event.get("track_id") or "").strip()
        if track:
            stats["tracks"][track] += 1
        source = str(event.get("source") or "").strip()
        if source:
            stats["sources"].add(source)
    return index


def _display_name(members: Counter) -> str:
    """Most frequent raw string; ties broken by the lexicographically smallest."""
    return sorted(members.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _evidence(stats: Mapping[str, Any]) -> str:
    """Short, machine-checkable provenance tag for one entity record."""
    kinds = []
    if stats["n_510k"]:
        kinds.append("510k")
    if stats["n_pma"]:
        kinds.append("pma")
    return f"{NORMALISATION_VERSION}|{'/'.join(kinds) or 'no-kind'}"


def _entity_record(normalised: str, stats: Mapping[str, Any]) -> dict[str, Any]:
    members = sorted(stats["members"])
    return {
        "entity_key": entity_key(normalised),
        "normalised_name": normalised,
        "display_name": _display_name(stats["members"]),
        "members": members,
        "n_events": stats["n_events"],
        "n_510k": stats["n_510k"],
        "n_pma": stats["n_pma"],
        "n_material": stats["n_material"],
        "first_date": stats["first_date"],
        "last_date": stats["last_date"],
        "active_years": len(stats["active_years"]),
        "tracks": {track: count for track, count in sorted(stats["tracks"].items())},
        "evidence": _evidence(stats),
    }


def build_universe(
    events: Iterable[Mapping[str, Any]],
    min_events: int = DEFAULT_MIN_EVENTS,
    pinned_normalised: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Build the detailed legal-entity records from event mappings.

    Parameters
    ----------
    events
        Mappings with ``applicant_raw`` plus optional ``kind``, ``event_date``,
        ``track_id``, ``source``, ``company_key`` and ``supplement_number``.
    min_events
        Entities with at least this many events get a full record.
    pinned_normalised
        Normalised names that must be included even below ``min_events`` (used
        to pin every curated/focus company's applicant strings so the artifact
        always contains them).

    Returns
    -------
    list of entity records sorted by ``(-n_events, entity_key)``.
    """
    index = _index_events(events)
    pinned = set(pinned_normalised)
    records = [
        _entity_record(normalised, stats)
        for normalised, stats in index.items()
        if stats["n_events"] >= min_events or normalised in pinned
    ]
    records.sort(key=lambda record: (-record["n_events"], record["entity_key"]))
    return records


# ------------------------------------------------------------- family resolution
def resolve_normalised(
    normalised_names: Iterable[str], aliases: Iterable[str]
) -> list[str]:
    """Resolve curated aliases to entity normalised names (corporate-family view).

    Rule: an entity belongs to an alias's family iff **every** token of the
    normalised alias appears as a token of the entity's normalised name (exact
    normalised equality is the one-token case).  This is token containment, the
    same deterministic rule the existing ``CompanyRegistry`` uses for its
    "all alias tokens present" tier; it is *not* fuzzy string similarity and it
    never rewrites entity records.

    Returns the matching normalised names, sorted.
    """
    alias_tokens: list[tuple[str, ...]] = []
    for alias in aliases:
        normalised = normalise_applicant(alias)
        if normalised:
            alias_tokens.append(tuple(normalised.split()))
    matches: list[str] = []
    for name in sorted(set(normalised_names)):
        tokens = set(name.split())
        if any(all(token in tokens for token in alias) for alias in alias_tokens):
            matches.append(name)
    return matches


def resolve_entities(
    entities: Iterable[Mapping[str, Any]], aliases: Iterable[str]
) -> list[str]:
    """Entity keys in an alias's corporate family (see :func:`resolve_normalised`)."""
    aliases = list(aliases)
    by_name = {str(entity["normalised_name"]): str(entity["entity_key"]) for entity in entities}
    matched = resolve_normalised(by_name, aliases)
    return sorted(by_name[name] for name in matched)


# ---------------------------------------------------------------- cohort rule
def select_cohort(
    entities: Sequence[Mapping[str, Any]],
    max_entities: int = DEFAULT_MAX_COHORT,
    min_material_events: int = DEFAULT_MIN_MATERIAL_EVENTS,
    min_active_years: int = DEFAULT_MIN_ACTIVE_YEARS,
    required_keys: Iterable[str] = (),
) -> list[str]:
    """Deterministic comparison-pool selection rule.

    Eligible entity: ``n_material >= min_material_events`` **and**
    ``active_years >= min_active_years`` (a minimum-history filter).  Eligible
    entities are ranked by ``(n_material desc, n_events desc, entity_key asc)``.

    ``required_keys`` that pass the eligibility filter are always included (in
    rank order) — the build uses this to guarantee the five mission focus
    companies enter the comparison pool even when their legal entities fall
    below the rank cut-off.  The remaining slots are filled from the ranking.
    The first ``max_entities`` of ``required + ranked`` are returned in order.
    Input order is irrelevant; identical entity sets always yield the identical
    cohort.
    """
    if max_entities < 0:
        raise ValueError("max_entities must be >= 0")
    eligible = [
        entity
        for entity in entities
        if int(entity["n_material"]) >= min_material_events
        and int(entity["active_years"]) >= min_active_years
    ]
    eligible.sort(
        key=lambda entity: (
            -int(entity["n_material"]),
            -int(entity["n_events"]),
            str(entity["entity_key"]),
        )
    )
    ranked = [str(entity["entity_key"]) for entity in eligible]
    required = set(str(key) for key in required_keys)
    pinned = [key for key in ranked if key in required]
    rest = [key for key in ranked if key not in required]
    return (pinned + rest)[:max_entities]


# ------------------------------------------------------------- coverage audit
def _curated_alias_map(
    curated_companies: Iterable[Mapping[str, Any]],
) -> dict[str, list[str]]:
    """Curated roster -> aliases (name_en, curated aliases, key itself is not used)."""
    alias_map: dict[str, list[str]] = {}
    for company in curated_companies:
        key = str(company.get("key") or "")
        if not key:
            continue
        aliases = [str(company.get("name_en") or "")]
        aliases.extend(str(alias) for alias in company.get("aliases") or ())
        alias_map[key] = [alias for alias in aliases if normalise_applicant(alias)]
    return alias_map


def _family_summary(
    index: Mapping[str, Mapping[str, Any]], matched: Iterable[str]
) -> dict[str, int]:
    names = set(matched)
    return {
        "n_entities": len(names),
        "n_events": sum(index[name]["n_events"] for name in names),
        "n_510k": sum(index[name]["n_510k"] for name in names),
        "n_pma": sum(index[name]["n_pma"] for name in names),
        "n_material": sum(index[name]["n_material"] for name in names),
        "n_events_curated_linked": sum(index[name]["n_curated_linked"] for name in names),
    }


def build_focus_section(
    index: Mapping[str, Mapping[str, Any]],
    curated_companies: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Mission requirement: prove the five focus companies are resolvable.

    Aliases are the curated roster aliases (when present) **unioned** with the
    normalised fallbacks in ``FOCUS_COMPANIES`` so FDA transcription variants
    (``Draegerwerk`` / ``Drägerwerk`` / ``DRAEGER``) are still caught.  Each
    entry reports the corporate-family counts, the canonical single-entity
    counts when an exact-normalised entity exists, and the roster status.
    """
    curated = {str(company.get("key") or ""): company for company in curated_companies}
    focus: dict[str, Any] = {}
    for key in sorted(FOCUS_COMPANIES):
        spec = FOCUS_COMPANIES[key]
        aliases = list(spec["aliases"])
        roster_status = "absent_from_curated_roster"
        if key in curated:
            roster_status = "in_curated_roster"
            aliases.extend(
                str(alias) for alias in curated[key].get("aliases") or ()
            )
            name_en = curated[key].get("name_en")
            if name_en:
                aliases.append(str(name_en))
        matched = resolve_normalised(index, aliases)
        summary = _family_summary(index, matched)
        canonical = normalise_applicant(spec["display_name"])
        canonical_stats = index.get(canonical)
        ordered = sorted(matched, key=lambda name: (-index[name]["n_events"], name))
        focus[key] = {
            "display_name": str(spec["display_name"]),
            "roster_status": roster_status,
            "aliases": sorted(dict.fromkeys(aliases)),
            "canonical_entity_key": entity_key(canonical) if canonical_stats else None,
            "canonical_entity_events": canonical_stats["n_events"] if canonical_stats else 0,
            **summary,
            "entities": [
                {
                    "entity_key": entity_key(name),
                    "normalised_name": name,
                    "n_events": index[name]["n_events"],
                    "n_material": index[name]["n_material"],
                }
                for name in ordered
            ],
        }
    return focus


def build_curated_section(
    index: Mapping[str, Mapping[str, Any]],
    curated_companies: Iterable[Mapping[str, Any]],
    config_path: str | None = None,
    config_sha256: str | None = None,
) -> dict[str, Any]:
    """Coverage audit of the hand-curated roster against the legal-entity universe."""
    alias_map = _curated_alias_map(curated_companies)
    by_company: dict[str, Any] = {}
    union: set[str] = set()
    linked_sum = 0
    events_sum = 0
    resolved = 0
    with_events = 0
    for key in sorted(alias_map):
        matched = resolve_normalised(index, alias_map[key])
        summary = _family_summary(index, matched)
        by_company[key] = {
            **summary,
            "unlinked_events": summary["n_events"] - summary["n_events_curated_linked"],
            "normalised_names": sorted(matched),
            "entity_keys": [entity_key(name) for name in sorted(matched)],
        }
        union.update(matched)
        events_sum += summary["n_events"]
        linked_sum += summary["n_events_curated_linked"]
        resolved += 1 if matched else 0
        with_events += 1 if summary["n_events"] else 0
    union_events = sum(index[name]["n_events"] for name in union)
    return {
        "config_path": config_path,
        "config_sha256": config_sha256,
        "companies_total": len(by_company),
        "companies_resolved": resolved,
        "companies_with_events": with_events,
        "distinct_entities_in_any_family": len(union),
        "distinct_family_events": union_events,
        "family_events_sum": events_sum,
        "family_events_curated_linked_sum": linked_sum,
        "unlinked_events_sum": events_sum - linked_sum,
        "by_company": by_company,
    }


def _remainder_section(
    index: Mapping[str, Mapping[str, Any]],
    detailed: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    detailed_names = {str(record["normalised_name"]) for record in detailed}
    remainder = [name for name in sorted(index) if name not in detailed_names]
    kinds = Counter()
    for name in remainder:
        stats = index[name]
        if stats["n_510k"]:
            kinds["510k"] += stats["n_510k"]
        if stats["n_pma"]:
            kinds["pma"] += stats["n_pma"]
    return {
        "definition": (
            "entities below min_events that are not pinned by a curated/focus "
            "alias; aggregated rather than stored one-by-one to keep the "
            "artifact small.  Every entity here contributes exactly one event "
            "when min_events >= 2 (verified invariant of the build)."
        ),
        "n_entities": len(remainder),
        "n_events": sum(index[name]["n_events"] for name in remainder),
        "n_510k": kinds.get("510k", 0),
        "n_pma": kinds.get("pma", 0),
        "normalised_names_sample": remainder[:25],
    }


def _focus_required_keys(focus_section: Mapping[str, Any]) -> list[str]:
    """One highest-material detailed entity per focus company, for cohort pinning."""
    required: list[str] = []
    for section in focus_section.values():
        candidates = [
            entry
            for entry in section.get("entities", [])
            if entry.get("entity_key")
        ]
        if not candidates:
            continue
        candidates.sort(
            key=lambda entry: (
                -int(entry["n_material"]),
                -int(entry["n_events"]),
                str(entry["entity_key"]),
            )
        )
        required.append(str(candidates[0]["entity_key"]))
    return sorted(set(required))


def build_document(
    events: Iterable[Mapping[str, Any]],
    min_events: int = DEFAULT_MIN_EVENTS,
    curated_companies: Iterable[Mapping[str, Any]] = (),
    *,
    db_path: str | None = None,
    db_bytes: int | None = None,
    db_sha256: str | None = None,
    config_path: str | None = None,
    config_sha256: str | None = None,
) -> dict[str, Any]:
    """Build the full, JSON-serialisable universe document.

    Pure function over ``events`` (+ the optional curated roster): all counts,
    coverage percentages, focus/curated sections and the remainder bucket are
    derived here so tests can exercise the exact artifact without touching the
    real database.  No timestamps are embedded — the same (events, roster)
    input must serialise to byte-identical bytes.
    """
    events = list(events)
    curated_companies = list(curated_companies)
    index = _index_events(events)
    alias_map = _curated_alias_map(curated_companies)

    pinned: set[str] = set()
    for aliases in alias_map.values():
        pinned.update(resolve_normalised(index, aliases))
    for spec in FOCUS_COMPANIES.values():
        pinned.update(resolve_normalised(index, spec["aliases"]))

    detailed = build_universe(events, min_events=min_events, pinned_normalised=pinned)
    remainder = _remainder_section(index, detailed)
    focus_section = build_focus_section(index, curated_companies)

    events_total = sum(stats["n_events"] for stats in index.values())
    detailed_events = sum(record["n_events"] for record in detailed)
    raw_applicants = sum(len(stats["members"]) for stats in index.values())
    event_kinds = {
        "510k": sum(stats["n_510k"] for stats in index.values()),
        "pma": sum(stats["n_pma"] for stats in index.values()),
    }
    covered = detailed_events + remainder["n_events"]
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "normalisation_version": NORMALISATION_VERSION,
        "normalisation_rules": {
            "summary": (
                "NFKD + combining-mark strip -> upper-case -> table-driven "
                "dotted-form substitution -> punctuation-to-space -> cut "
                "descriptive clause (FORMERLY/DBA/FKA/AKA/NKA) -> drop leading "
                "THE -> strip trailing corporate suffix tokens; no fuzzy merge"
            ),
            "corporate_suffix_tokens": sorted(CORPORATE_SUFFIX_TOKENS),
            "pre_substitutions": [
                [source, target] for source, target in _PRE_SUBSTITUTIONS_ORDERED
            ],
            "clause_markers": [" ".join(marker) for marker in _CLAUSE_MARKERS],
        },
        "source": {
            "db_path": db_path,
            "db_bytes": db_bytes,
            "db_sha256": db_sha256,
            "access": "sqlite3 read-only (mode=ro)",
            "curated_config_path": config_path,
            "curated_config_sha256": config_sha256,
        },
        "material_event_rule": MATERIAL_EVENT_RULE,
        "selection_rule": SELECTION_RULE,
        "counts": {
            "events_total": events_total,
            "event_kinds": event_kinds,
            "raw_applicant_strings": raw_applicants,
            "entities_total": len(index),
            "entities_detailed": len(detailed),
            "events_detailed": detailed_events,
            "events_detailed_pct": round(100.0 * detailed_events / events_total, 2)
            if events_total
            else 0.0,
            "entities_remainder": remainder["n_entities"],
            "events_remainder": remainder["n_events"],
            "events_remainder_pct": round(100.0 * remainder["n_events"] / events_total, 2)
            if events_total
            else 0.0,
            "events_accounted": covered,
            "events_accounted_pct": round(100.0 * covered / events_total, 2)
            if events_total
            else 0.0,
            "min_events_for_detailed_records": min_events,
        },
        "focus_companies": focus_section,
        "curated_coverage": build_curated_section(
            index,
            curated_companies,
            config_path=config_path,
            config_sha256=config_sha256,
        ),
        "entities": detailed,
        "remainder": remainder,
    }
    required_keys = _focus_required_keys(focus_section)
    document["cohort"] = {
        "rule": SELECTION_RULE,
        "max_entities": DEFAULT_MAX_COHORT,
        "min_material_events": DEFAULT_MIN_MATERIAL_EVENTS,
        "min_active_years": DEFAULT_MIN_ACTIVE_YEARS,
        "required_focus_entity_keys": required_keys,
        "entity_keys": select_cohort(detailed, required_keys=required_keys),
    }
    return document


# ------------------------------------------------------------------ DB reader
def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_events(db_path: Path) -> tuple[list[dict[str, Any]], int, str]:
    """Read the lane events from the database read-only, plus file size and hash."""
    resolved = db_path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"research database not found: {resolved}")
    digest = _sha256_file(resolved)
    uri = f"file:{resolved.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='events'"
        ).fetchone()[0]
        if not exists:
            raise RuntimeError(f"no `events` table in {resolved}")
        rows = connection.execute(
            "SELECT applicant_raw, kind, event_date, track_id, source, company_key, "
            "CASE WHEN kind = 'pma' THEN json_extract(payload, '$.supplement_number') END "
            "AS supplement_number FROM events"
        )
        events = [dict(row) for row in rows]
    finally:
        connection.close()
    return events, resolved.stat().st_size, digest


def _load_curated(config_path: Path | None = None) -> tuple[list[dict[str, Any]], str, str]:
    """Load the curated device roster without importing the rest of the package."""
    from ..config import CONFIG_DIR

    path = config_path or (CONFIG_DIR / "companies_device.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    companies = [dict(company) for company in payload.get("companies", [])]
    return companies, str(path), _sha256_file(path)


def write_universe(
    db_path: str | Path,
    out_path: str | Path,
    min_events: int = DEFAULT_MIN_EVENTS,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Read the real database read-only, build the document and write it.

    Returns the document.  The output is compact, key-sorted JSON with a
    trailing newline, written with UTF-8 and ``\\n`` newlines so the same
    (database, config) input produces byte-identical bytes on every platform.
    """
    db = Path(db_path)
    events, db_bytes, db_sha256 = _read_events(db)
    curated, curated_path, curated_sha256 = _load_curated(
        Path(config_path) if config_path else None
    )
    document = build_document(
        events,
        min_events=min_events,
        curated_companies=curated,
        db_path=str(db),
        db_bytes=db_bytes,
        db_sha256=db_sha256,
        config_path=curated_path,
        config_sha256=curated_sha256,
    )
    text = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes((text + "\n").encode("utf-8"))
    return document


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m medradar.intelligence.universe --out config/universe_v1.json``."""
    from ..config import CONFIG_DIR, DATA_DIR

    parser = argparse.ArgumentParser(
        description="Build the deterministic applicant-entity universe (read-only DB access)"
    )
    parser.add_argument("--db", default=str(DATA_DIR / "research.sqlite"))
    parser.add_argument("--out", default=str(CONFIG_DIR / "universe_v1.json"))
    parser.add_argument("--config", default=None, help="curated companies_device.json path")
    parser.add_argument("--min-events", type=int, default=DEFAULT_MIN_EVENTS)
    args = parser.parse_args(argv)
    document = write_universe(
        args.db, args.out, min_events=args.min_events, config_path=args.config
    )
    counts = document["counts"]
    summary = {
        "out": str(args.out),
        "schema_version": document["schema_version"],
        "entities_total": counts["entities_total"],
        "entities_detailed": counts["entities_detailed"],
        "events_total": counts["events_total"],
        "events_detailed_pct": counts["events_detailed_pct"],
        "events_accounted_pct": counts["events_accounted_pct"],
        "focus_companies": {
            key: {
                "n_entities": value["n_entities"],
                "n_events": value["n_events"],
                "roster_status": value["roster_status"],
            }
            for key, value in document["focus_companies"].items()
        },
        "bytes": Path(args.out).stat().st_size,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
