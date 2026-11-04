"""Deterministic (A-arm) function-class and technology-track classification of job postings.

Why this module exists
----------------------
The recruitment lane can observe that a company published a job advert. That is a
fact. It is **not** yet a technology signal: the advert must be placed in the
mission's job-function vocabulary and, where the evidence allows, in the existing
device technology taxonomy. This module is the **rules baseline** — the A arm —
against which a local language model (B arm, ``experiments/innovation_signals_observatory``)
is compared. It is deliberately simple, auditable and offline:

* **No model, no network, no database.** Only committed configuration files are
  read, and every function is pure.
* **Vocabulary is not invented here.** The function vocabulary is the mission's
  (``CORE_R&D … UNCLASSIFIED``), loaded from
  ``config/recruitment_function_classes.json``. Track ids/keywords/domains are the
  existing ones in ``config/tracks_device.json``; the versioned regime comes from
  :mod:`medradar.intelligence.taxonomy`.
* **Everything that can change a label is versioned.** ``RULES_VERSION`` names the
  matching logic, the committed function map carries ``map_version`` and a SHA-256
  fingerprint, and every output is stamped with the taxonomy regime (version,
  effective date and file fingerprints).
* **Abstention is legitimate.** ``UNCLASSIFIED`` is a counted outcome when no cue
  fires, when the description fallback is below its evidence floor, or when two
  classes tie. A description-only label is never silently produced from one
  incidental phrase.
* **Evidence is emitted, not summarised.** Every decision carries the actual
  matched substrings with their character span in the normalised text, the rule
  phrase that fired, and whether the hit was in the title or the description, so a
  human (or the B arm) can verify or overturn it.
* **Confidence is rule-derived, not calibrated.** ``confidence_basis`` counts rule
  firings (how many, how specific, by what margin). It is explicitly **not a
  probability** and must never be read as one.
* **Commercial/administrative postings never get a technology track.** A device
  keyword in a sales advert is the product being sold, not an R&D direction. The
  track gate refuses to attach a track to ``SALES_ADMIN_OTHER`` / ``UNCLASSIFIED``
  and keeps the refused candidate as audit evidence.

Interface (the documented A-arm contract)
-----------------------------------------
``classify_rules(job) -> dict`` with at least::

    {
      "function_class": "CORE_R&D" | ... | "UNCLASSIFIED",
      "track_id": "ep_pfa" | None,
      "evidence_spans": [ {field, start, end, text, rule, target, kind, ...}, ... ],
      "confidence_basis": { ... rule-derived counts, NOT a probability ... },
      # plus: track_status, function_evidence, track_evidence, unclassified_reason,
      #       rules_version, function_map_version, taxonomy_regime
    }

``job`` may be a mapping (a ``JobObservation.to_dict()`` row, or a dict with
``job_title``/``job_description``) or any object exposing those attributes.

Character spans are offsets into ``medradar.recruitment.records.normalise_text`` of
the *field being matched* (title or description), not into the raw HTML; the matched
substring is included verbatim, so a span can be re-verified without re-deriving
offsets.

Known limits (reported, not hidden)
-----------------------------------
* Cue lists are English; a non-English title is only classified when its (usually
  English) description clears the fallback floor, otherwise ``UNCLASSIFIED``.
* The device taxonomy's keywords were built for product-code/device text, not for
  job adverts. Many are generic in this context ("software", "algorithm",
  "next generation", benefits boilerplate "dental"); the ``generic_keywords`` list
  below prevents them from assigning a track on their own, at the cost of lower
  track coverage. Coverage is reported, never patched by lowering the floor.
* A title phrase names the occupation, so a title hit outranks description hits; a
  role whose title says "Engineer I" is decided by description evidence only and
  carries a correspondingly weaker rule label.
"""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import records as rec

# --------------------------------------------------------------------- versions
#: Version of the *matching logic*. Bump when the algorithm changes, not when a
#: cue phrase changes (that changes the map fingerprint and ``map_version``).
RULES_VERSION = "recruitment_taxonomy_rules_2026-11-04"
#: A-arm identity recorded in every output, for the A/B comparison.
ARM = "rules_A"
SCHEMA_VERSION = "recruitment-classification-v1"

#: Position of this file: .../<repo>/medradar/recruitment/taxonomy.py
_REPO_ROOT = Path(__file__).resolve().parents[2]
FUNCTION_MAP_PATH = _REPO_ROOT / "config" / "recruitment_function_classes.json"
TRACKS_PATH = _REPO_ROOT / "config" / "tracks_device.json"
PRODUCT_CODE_MAP_PATH = _REPO_ROOT / "config" / "product_code_tracks.json"

# ------------------------------------------------------------------ vocabularies
#: The mission's job-function vocabulary. ``UNCLASSIFIED`` is a real outcome.
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
UNCLASSIFIED = "UNCLASSIFIED"
SALES_ADMIN_OTHER = "SALES_ADMIN_OTHER"

#: Track status vocabulary. Only ``MAPPED`` carries a ``track_id``.
TRACK_MAPPED = "MAPPED"
TRACK_AMBIENT_ONLY = "AMBIENT_ONLY"
TRACK_NO_EVIDENCE = "NO_EVIDENCE"
TRACK_SUPPRESSED = "SUPPRESSED_BY_FUNCTION_CLASS"
TRACK_STATUSES = (TRACK_MAPPED, TRACK_AMBIENT_ONLY, TRACK_NO_EVIDENCE, TRACK_SUPPRESSED)

#: Rule-derived strength labels. These are *not* probabilities and are not
#: calibrated; they only say how much of the rule fired.
STRENGTH_NONE = "NONE"
STRENGTH_WEAK = "WEAK"
STRENGTH_MODERATE = "MODERATE"
STRENGTH_STRONG = "STRONG"

CONFIDENCE_DISCLAIMER = (
    "Rule-derived evidence strength, NOT a calibrated probability. The numbers count keyword-rule "
    "firings and their specificity; they were not fitted to labels and have no probabilistic meaning."
)


# ---------------------------------------------------------------------- loading
def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def function_class_map() -> dict[str, Any]:
    """The committed function-class map (data, not code)."""
    return _read_json(FUNCTION_MAP_PATH)


@lru_cache(maxsize=1)
def _function_map_bytes() -> bytes:
    return FUNCTION_MAP_PATH.read_bytes()


def function_map_fingerprint() -> str:
    """SHA-256 of the committed function map, so an unversioned cue edit is visible."""
    return hashlib.sha256(_function_map_bytes()).hexdigest()


def function_map_version() -> str:
    return str(function_class_map().get("map_version"))


@lru_cache(maxsize=1)
def _tracks_document() -> dict[str, Any]:
    return _read_json(TRACKS_PATH)


@lru_cache(maxsize=1)
def track_table() -> tuple[dict[str, Any], ...]:
    """The existing device tracks, exactly as committed in ``config/tracks_device.json``."""
    tracks = []
    for track in _tracks_document().get("tracks", []):
        keywords = [str(k) for k in (track.get("keywords") or [])]
        frontier = [str(k) for k in (track.get("frontier_keywords") or [])]
        tracks.append(
            {
                "track_id": track["id"],
                "name_en": track.get("name_en"),
                "name_zh": track.get("name_zh"),
                "domain": track.get("domain"),
                "domain_zh": track.get("domain_zh"),
                "category": track.get("category"),
                "keywords": keywords,
                "frontier_keywords": frontier,
            }
        )
    return tuple(tracks)


@lru_cache(maxsize=1)
def track_ids() -> tuple[str, ...]:
    return tuple(t["track_id"] for t in track_table())


@lru_cache(maxsize=1)
def taxonomy_regime() -> dict[str, Any]:
    """Versioned taxonomy regime (reuses :mod:`medradar.intelligence.taxonomy`).

    Explicit paths are passed so the fingerprint does not depend on the process
    working directory.
    """
    from ..intelligence import taxonomy as taxonomy_regime_module

    try:
        return taxonomy_regime_module.regime(code_map=PRODUCT_CODE_MAP_PATH, tracks=TRACKS_PATH)
    except OSError:  # pragma: no cover - only when the checkout is incomplete
        return {
            "version": taxonomy_regime_module.TAXONOMY_VERSION,
            "effective_from": taxonomy_regime_module.EFFECTIVE_FROM,
            "code_map_fingerprint": None,
            "track_list_fingerprint": None,
            "note": "taxonomy files unreadable in this checkout; regime recorded without fingerprints",
        }


def label_versions() -> dict[str, Any]:
    """Everything that could change a label, in one place."""
    return {
        "schema_version": SCHEMA_VERSION,
        "arm": ARM,
        "rules_version": RULES_VERSION,
        "function_map_version": function_map_version(),
        "function_map_fingerprint": function_map_fingerprint(),
        "taxonomy": taxonomy_regime(),
    }


# --------------------------------------------------------------------- matching
_MATCH_LEFT = r"(?<![0-9a-z])"
_MATCH_RIGHT = r"(?![0-9a-z])"


def normalise_field(text: str | None) -> str:
    """The exact text that spans refer to (records' whitespace normalisation)."""
    return rec.normalise_text(text)


def _phrase_body(phrase: str, *, plural: bool = False) -> str:
    words = [re.escape(part) for part in phrase.split()]
    body = r"\s+".join(words)
    if plural and phrase and phrase[-1].isalnum() and not phrase.endswith("s"):
        body += "s?"
    elif plural and phrase.endswith("s"):
        body += "(?:es)?"
    return body


@lru_cache(maxsize=4096)
def _compiled(pattern_key: str, phrase: str, plural: bool = False) -> re.Pattern[str]:
    return re.compile(_MATCH_LEFT + _phrase_body(phrase, plural=plural) + _MATCH_RIGHT, re.IGNORECASE)


def _substring_variants(phrase: str, plural: bool) -> tuple[str, ...]:
    """Plain-substring forms used only as a fast pre-filter (positions come from the regex)."""
    base = " ".join(phrase.lower().split())
    variants = [base]
    if plural and phrase:
        if phrase.endswith("s"):
            variants.append(base + "es")
        elif phrase[-1].isalnum():
            variants.append(base + "s")
    return tuple(variants)


def _find_spans(text: str, canonical_lower: str, phrase: str, *, plural: bool = False) -> list[dict[str, Any]]:
    """Occurrences of one phrase, skipping the regex when the phrase is absent.

    ``canonical_lower`` is ``" ".join(text.split()).lower()``; it exists only to
    make the absent-phrase case cheap on long job descriptions (hundreds of track
    keywords are tried, almost all absent). All spans still come from the regex
    against ``text``, so the returned positions are exact.
    """
    if not text or not phrase:
        return []
    if canonical_lower and not any(variant in canonical_lower for variant in _substring_variants(phrase, plural)):
        return []
    pattern = _compiled(phrase, phrase, plural)
    return [
        {"phrase": phrase, "start": m.start(), "end": m.end(), "text": text[m.start():m.end()]}
        for m in pattern.finditer(text)
    ]


def find_phrase_spans(text: str, phrase: str, *, plural: bool = False) -> list[dict[str, Any]]:
    """All occurrences of one phrase in ``text``, with exact character spans."""
    return _find_spans(text, " ".join(text.split()).lower() if text else "", phrase, plural=plural)


def _context(text: str, start: int, end: int, window: int = 48) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    return (" " if left else "") + text[left:right].replace("\n", " ") + (" " if right < len(text) else "")


# ------------------------------------------------------------- function classify
def _function_cue_spans(text: str, canonical_lower: str, field: str, spec: Mapping[str, Any], *,
                        title: bool) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    key = "title_phrases" if title else "description_phrases"
    for phrase in spec.get(key, []) or []:
        for hit in _find_spans(text, canonical_lower, phrase, plural=not title):
            spans.append(
                {
                    "kind": "function",
                    "field": field,
                    "start": hit["start"],
                    "end": hit["end"],
                    "text": hit["text"],
                    "rule": ("function_title_phrase" if title else "function_description_phrase"),
                    "target": None,  # filled by caller
                    "phrase": phrase,
                    "context": _context(text, hit["start"], hit["end"]),
                }
            )
    return spans


def _class_specs() -> dict[str, dict[str, Any]]:
    return dict(function_class_map()["classes"])


def _non_overlapping_first_occurrences(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """First occurrence of each distinct phrase, then greedily keep non-overlapping spans.

    Nested cues ("research", "research scientist", "scientist") describe the same
    words; counting all of them would let a generic core phrase outrank a specific
    compound phrase. Scoring the non-overlapping longest phrases instead keeps
    ``Clinical Research Scientist`` clinical rather than core.
    """
    first: dict[str, dict[str, Any]] = {}
    for span in spans:
        phrase = span["phrase"]
        current = first.get(phrase)
        if current is None or (span["start"], span["end"]) < (current["start"], current["end"]):
            first[phrase] = span
    chosen: list[dict[str, Any]] = []
    for span in sorted(first.values(), key=lambda item: (-(item["end"] - item["start"]), item["start"])):
        if all(span["end"] <= kept["start"] or span["start"] >= kept["end"] for kept in chosen):
            chosen.append(span)
    return chosen


def _score_title(text: str) -> dict[str, Any]:
    """Title evidence per class: distinct phrases, non-overlapping score, first position."""
    canonical_lower = " ".join(text.split()).lower()
    by_class: dict[str, dict[str, Any]] = {}
    for cls, spec in _class_specs().items():
        spans = _function_cue_spans(text, canonical_lower, "job_title", spec, title=True)
        by_class[cls] = {"spans": spans, "phrases": sorted({s["phrase"] for s in spans})}
    for cls, info in by_class.items():
        scoring_spans = _non_overlapping_first_occurrences(info["spans"])
        info["score_phrases"] = [span["phrase"] for span in scoring_spans]
        info["score"] = sum(span["end"] - span["start"] for span in scoring_spans)
        info["first_start"] = min((span["start"] for span in info["spans"]), default=len(text) + 1)
        info["precedence"] = int(_class_specs()[cls].get("precedence", 50))
    return by_class


def _score_description(text: str) -> dict[str, Any]:
    canonical_lower = " ".join(text.split()).lower()
    by_class: dict[str, dict[str, Any]] = {}
    for cls, spec in _class_specs().items():
        spans = _function_cue_spans(text, canonical_lower, "job_description", spec, title=False)
        by_class[cls] = {"spans": spans, "phrases": sorted({s["phrase"] for s in spans})}
    for cls, info in by_class.items():
        info["count"] = len(info["phrases"])
        info["precedence"] = int(_class_specs()[cls].get("precedence", 50))
    return by_class


def _decide_function(title_scores: Mapping[str, Mapping[str, Any]],
                     desc_scores: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Title first (occupation), description only as a floored fallback."""
    matching = function_class_map().get("matching", {})
    min_desc_hits = int(matching.get("min_description_hits", 3))

    ranked = sorted(
        ((cls, info["score"], info["phrases"]) for cls, info in title_scores.items() if info["phrases"]),
        key=lambda row: (
            -row[1],
            title_scores[row[0]]["first_start"],
            title_scores[row[0]]["precedence"],
            row[0],
        ),
    )
    if ranked:
        winner_cls, winner_score, winner_phrases = ranked[0]
        tie_break = False
        if len(ranked) > 1 and ranked[1][1] == winner_score:
            # Config resolves score ties by the phrase that starts earliest in the
            # title (the head of the occupation phrase) and then class precedence;
            # record that a tie was broken so the reader knows the title was not
            # uniquely decisive.
            tie_break = True
        info = title_scores[winner_cls]
        return {
            "function_class": winner_cls,
            "decision_basis": "title_phrases",
            "title_score": winner_score,
            "title_phrases": winner_phrases,
            "title_score_phrases": title_scores[winner_cls]["score_phrases"],
            "title_hits": len(info["spans"]),
            "title_longest_phrase_chars": max((len(p) for p in winner_phrases), default=0),
            "title_first_phrase_start": info["first_start"],
            "precedence": info["precedence"],
            "tie_break_used": tie_break,
            "runner_up": ranked[1][0] if len(ranked) > 1 else None,
            "runner_up_score": ranked[1][1] if len(ranked) > 1 else 0,
            "margin": (winner_score - ranked[1][1]) if len(ranked) > 1 else winner_score,
            "description_only": False,
            "spans": [dict(span, target=winner_cls) for span in info["spans"]],
            "unclassified_reason": None,
            "description_candidates": {},
        }

    # ---- description fallback: only multi-phrase evidence, never one incidental word
    desc_ranked = sorted(
        ((cls, info["count"], info["phrases"]) for cls, info in desc_scores.items() if info["phrases"]),
        key=lambda row: (-row[1], desc_scores[row[0]]["precedence"], row[0]),
    )
    if not desc_ranked:
        return {
            "function_class": UNCLASSIFIED,
            "decision_basis": "abstain",
            "title_score": 0,
            "title_phrases": [],
            "title_hits": 0,
            "title_longest_phrase_chars": 0,
            "precedence": None,
            "tie_break_used": False,
            "runner_up": None,
            "runner_up_score": 0,
            "margin": 0,
            "description_only": False,
            "spans": [],
            "unclassified_reason": "no_cue_in_title_or_description",
            "description_candidates": {},
        }

    winner_cls, winner_count, winner_phrases = desc_ranked[0]
    runner = desc_ranked[1] if len(desc_ranked) > 1 else None
    if winner_count < min_desc_hits:
        reason = "description_below_min_hits"
    elif runner is not None and runner[1] == winner_count:
        reason = "description_tie"
    else:
        reason = None
    if reason is not None:
        return {
            "function_class": UNCLASSIFIED,
            "decision_basis": "abstain",
            "title_score": 0,
            "title_phrases": [],
            "title_hits": 0,
            "title_longest_phrase_chars": 0,
            "precedence": None,
            "tie_break_used": False,
            "runner_up": winner_cls,
            "runner_up_score": winner_count,
            "margin": 0,
            "description_only": True,
            "spans": [],
            "unclassified_reason": reason,
            "description_candidates": {
                cls: {"count": info["count"], "phrases": info["phrases"]}
                for cls, info in desc_scores.items() if info["phrases"]
            },
        }
    info = desc_scores[winner_cls]
    return {
        "function_class": winner_cls,
        "decision_basis": "description_phrases",
        "title_score": 0,
        "title_phrases": [],
        "title_hits": 0,
        "title_longest_phrase_chars": 0,
        "precedence": info["precedence"],
        "tie_break_used": False,
        "runner_up": runner[0] if runner else None,
        "runner_up_score": runner[1] if runner else 0,
        "margin": (winner_count - runner[1]) if runner else winner_count,
        "description_only": True,
        "description_hits": len(info["spans"]),
        "description_distinct_phrases": winner_count,
        "description_phrases": winner_phrases,
        "spans": [dict(span, target=winner_cls) for span in info["spans"]],
        "unclassified_reason": None,
        "description_candidates": {
            cls: {"count": e["count"], "phrases": e["phrases"]}
            for cls, e in desc_scores.items() if e["phrases"]
        },
    }


# ---------------------------------------------------------------- track classify
def _generic_keywords() -> set[str]:
    gate = function_class_map().get("track_gate", {})
    return {str(k).upper() for k in gate.get("generic_keywords", [])}


def _match_track_keywords(title_norm: str, desc_norm: str) -> list[dict[str, Any]]:
    """All track keyword occurrences, regardless of class/gate, for audit evidence."""
    generic = _generic_keywords()
    fields = {
        "job_title": (title_norm, " ".join(title_norm.split()).lower()),
        "job_description": (desc_norm, " ".join(desc_norm.split()).lower()),
    }
    hits: list[dict[str, Any]] = []
    for track in track_table():
        entries = [("keyword", kw) for kw in track["keywords"]]
        entries += [("frontier", kw) for kw in track["frontier_keywords"]]
        for kind, keyword in entries:
            is_generic = keyword.upper() in generic
            for field, (text, canonical_lower) in fields.items():
                for hit in _find_spans(text, canonical_lower, keyword, plural=True):
                    hits.append(
                        {
                            "kind": "track",
                            "field": field,
                            "start": hit["start"],
                            "end": hit["end"],
                            "text": hit["text"],
                            "rule": ("track_frontier_keyword" if kind == "frontier" else "track_keyword"),
                            "target": track["track_id"],
                            "keyword": keyword,
                            "keyword_kind": kind,
                            "generic": is_generic,
                            "context": _context(text, hit["start"], hit["end"]),
                        }
                    )
    return hits


def _decide_track(function_class: str, track_spans: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    gate = function_class_map().get("track_gate", {})
    eligible = set(gate.get("eligible_function_classes", []))
    min_desc = int(gate.get("min_distinct_description_keywords", 2))
    frontier_alone = bool(gate.get("frontier_keyword_hit_alone_is_sufficient", True))

    spans = [dict(s) for s in track_spans]
    per_track: dict[str, dict[str, Any]] = {}
    for span in spans:
        entry = per_track.setdefault(
            span["target"],
            {
                "title_specific": set(),
                "title_generic": set(),
                "desc_specific": set(),
                "desc_generic": set(),
                "frontier_hits": 0,
                "longest_specific_keyword": 0,
            },
        )
        if span["generic"]:
            entry["title_generic" if span["field"] == "job_title" else "desc_generic"].add(span["keyword"])
            continue
        if span["keyword_kind"] == "frontier":
            entry["frontier_hits"] += 1
        entry["longest_specific_keyword"] = max(entry["longest_specific_keyword"], len(span["keyword"]))
        if span["field"] == "job_title":
            entry["title_specific"].add(span["keyword"])
        else:
            entry["desc_specific"].add(span["keyword"])

    tracks = {
        track: entry
        for track, entry in per_track.items()
        if entry["title_specific"] or entry["desc_specific"] or entry["frontier_hits"]
        or entry["title_generic"] or entry["desc_generic"]
    }
    eligible_tracks = {
        track: entry
        for track, entry in tracks.items()
        if entry["title_specific"] or entry["desc_specific"] or entry["frontier_hits"]
    }

    def rank_key(item: tuple[str, Mapping[str, Any]]) -> tuple:
        track_id, entry = item
        return (
            -len(entry["title_specific"]),
            -len(entry["desc_specific"]),
            -int(entry["frontier_hits"]),
            -int(entry["longest_specific_keyword"]),
            track_id,
        )

    ranked = sorted(eligible_tracks.items(), key=rank_key)
    best_id, best = ranked[0] if ranked else (None, None)
    assigned = False
    if best is not None:
        assigned = (
            bool(best["title_specific"])
            or len(best["desc_specific"]) >= min_desc
            or (frontier_alone and int(best["frontier_hits"]) >= 1)
        )
    tie_break = False
    if len(ranked) > 1 and best is not None:
        tie_break = rank_key(ranked[0])[:4] == rank_key(ranked[1])[:4]

    def candidate_block(track_id: str | None, entry: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if track_id is None or entry is None:
            return None
        table = {t["track_id"]: t for t in track_table()}[track_id]
        return {
            "track_id": track_id,
            "name_en": table.get("name_en"),
            "domain": table.get("domain"),
            "title_specific_keywords": sorted(entry["title_specific"]),
            "description_specific_keywords": sorted(entry["desc_specific"]),
            "frontier_hits": int(entry["frontier_hits"]),
            "longest_specific_keyword_chars": int(entry["longest_specific_keyword"]),
            "generic_keywords_only": sorted(entry["title_generic"] | entry["desc_generic"]),
        }

    candidate = candidate_block(best_id, best)
    if function_class not in eligible:
        return {
            "track_id": None,
            "track_status": TRACK_SUPPRESSED,
            "track_name_en": None,
            "track_domain": None,
            "candidate": candidate,
            "spans": spans,
            "reason": gate.get(
                "ineligible_reason_en",
                "function class is not a technology function; a track would manufacture a technology signal",
            ),
            "tie_break_used": tie_break,
        }
    if assigned and best is not None:
        table = {t["track_id"]: t for t in track_table()}[best_id]
        return {
            "track_id": best_id,
            "track_status": TRACK_MAPPED,
            "track_name_en": table.get("name_en"),
            "track_domain": table.get("domain"),
            "candidate": candidate,
            "spans": spans,
            "reason": (
                "title keyword hit"
                if best["title_specific"]
                else (
                    f">= {min_desc} distinct description keywords"
                    if len(best["desc_specific"]) >= min_desc
                    else "frontier keyword hit"
                )
            ),
            "tie_break_used": tie_break,
        }
    # Not enough evidence: keep the single ambient candidate visible rather than
    # assigning it. A single incidental phrase is not a technology classification.
    return {
        "track_id": None,
        "track_status": TRACK_AMBIENT_ONLY if (candidate or tracks) else TRACK_NO_EVIDENCE,
        "track_name_en": None,
        "track_domain": None,
        "candidate": candidate,
        "spans": spans,
        "reason": (
            "one description keyword is ambient evidence, not a track assignment"
            if candidate
            else "no track keyword matched"
        ),
        "tie_break_used": tie_break,
    }


# ------------------------------------------------------------------- public API
def _job_field(job: Any, *names: str) -> str | None:
    for name in names:
        value = job.get(name) if isinstance(job, Mapping) else getattr(job, name, None)
        if value:
            return str(value)
    return None


def _confidence_basis(function: Mapping[str, Any], track: Mapping[str, Any]) -> dict[str, Any]:
    if function["decision_basis"] == "title_phrases":
        longest = int(function["title_longest_phrase_chars"])
        strength = STRENGTH_STRONG if (longest >= 12 or len(function["title_phrases"]) >= 2) else STRENGTH_MODERATE
    elif function["decision_basis"] == "description_phrases":
        distinct = int(function.get("description_distinct_phrases", 0))
        strength = STRENGTH_MODERATE if (distinct >= 5 or int(function["margin"]) >= 2) else STRENGTH_WEAK
    else:
        strength = STRENGTH_NONE
    track_strength = STRENGTH_NONE
    if track["track_status"] == TRACK_MAPPED:
        candidate = track.get("candidate") or {}
        if candidate.get("title_specific_keywords"):
            track_strength = STRENGTH_STRONG if len(candidate["title_specific_keywords"]) >= 2 else STRENGTH_MODERATE
        else:
            track_strength = STRENGTH_MODERATE if len(candidate.get("description_specific_keywords", [])) >= 3 else STRENGTH_WEAK
    return {
        "kind": "rule_derived_not_probability",
        "calibrated_probability": False,
        "statement": CONFIDENCE_DISCLAIMER,
        "rules_version": RULES_VERSION,
        "function_map_version": function_map_version(),
        "function": {
            "decision_basis": function["decision_basis"],
            "rule_strength": strength,
            "title_score": int(function["title_score"]),
            "title_distinct_phrases": len(function["title_phrases"]),
            "title_hits": int(function["title_hits"]),
            "title_longest_phrase_chars": int(function["title_longest_phrase_chars"]),
            "title_first_phrase_start": function.get("title_first_phrase_start"),
            "title_phrases": list(function["title_phrases"]),
            "title_score_phrases": list(function.get("title_score_phrases") or function["title_phrases"]),
            "description_distinct_phrases": int(function.get("description_distinct_phrases", 0)),
            "runner_up": function.get("runner_up"),
            "runner_up_score": int(function.get("runner_up_score") or 0),
            "margin": int(function.get("margin") or 0),
            "tie_break_used": bool(function.get("tie_break_used")),
        },
        "track": {
            "track_status": track["track_status"],
            "rule_strength": track_strength,
            "candidate": track.get("candidate"),
            "reason": track.get("reason"),
            "tie_break_used": bool(track.get("tie_break_used")),
        },
    }


def classify_rules(job: Any) -> dict[str, Any]:
    """Classify one posting. Deterministic; see the module docstring for the contract."""
    title_raw = _job_field(job, "job_title", "title")
    desc_raw = _job_field(job, "job_description", "description")
    title = normalise_field(title_raw)
    desc = normalise_field(desc_raw)

    title_scores = _score_title(title)
    desc_scores = _score_description(desc)
    function = _decide_function(title_scores, desc_scores)
    track = _decide_track(function["function_class"], _match_track_keywords(title, desc))

    confidence = _confidence_basis(function, track)
    versions = {
        "schema_version": SCHEMA_VERSION,
        "arm": ARM,
        "rules_version": RULES_VERSION,
        "function_map_version": function_map_version(),
        "function_map_fingerprint": function_map_fingerprint(),
        "taxonomy": taxonomy_regime(),
    }
    # ``quote`` is a verbatim alias of ``text`` for callers that only need the
    # matched string; positions stay available for exact verification.
    function_spans = [
        dict(span, quote=span["text"])
        for span in sorted(function["spans"], key=lambda s: (s["field"] != "job_title", s["start"], s["end"]))
    ]
    track_spans = [
        dict(span, quote=span["text"])
        for span in sorted(track["spans"], key=lambda s: (s["field"] != "job_title", s["start"], s["end"]))
    ]
    return {
        "function_class": function["function_class"],
        "track_id": track["track_id"],
        # the documented contract name, keeping both function and track spans
        "evidence_spans": function_spans + track_spans,
        "confidence_basis": confidence,
        # richer detail for the B arm / human review
        "function_evidence": {
            "decision_basis": function["decision_basis"],
            "spans": function_spans,
            "unclassified_reason": function.get("unclassified_reason"),
            "description_candidates": function.get("description_candidates") or {},
        },
        "track_evidence": {
            "track_status": track["track_status"],
            "candidate": track.get("candidate"),
            "reason": track.get("reason"),
            "spans": track_spans,
        },
        "unclassified_reason": function.get("unclassified_reason") if function["function_class"] == UNCLASSIFIED else None,
        "notes": _notes_for(function, track),
        **versions,
    }


#: Alias so callers can name the action either way; the contract is ``classify_rules``.
classify_job = classify_rules


def _notes_for(function: Mapping[str, Any], track: Mapping[str, Any]) -> list[str]:
    notes: list[str] = []
    if function["function_class"] == UNCLASSIFIED:
        notes.append("UNCLASSIFIED is an accepted outcome: " + str(function.get("unclassified_reason")))
    if function["decision_basis"] == "description_phrases":
        notes.append(
            "no title cue matched; the class comes from description evidence only, which is weaker and "
            "carries no calibrated probability"
        )
    if track["track_status"] == TRACK_SUPPRESSED:
        notes.append("technology track suppressed by the function-class gate")
    if track["track_status"] == TRACK_AMBIENT_ONLY:
        notes.append("track candidate retained as ambient evidence but not assigned")
    return notes


# --------------------------------------------------------------------- reporting
def load_job_rows(path: str | Path) -> list[dict[str, Any]]:
    """Read a committed JSONL observation file (offline; never edits it)."""
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def summarise(jobs: Iterable[Any]) -> dict[str, Any]:
    """Per-class / UNCLASSIFIED / track rates on a sample, with the regime attached."""
    return summarise_classifications([classify_rules(job) for job in jobs])


def summarise_classifications(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The same report from *already classified* rows (no re-classification)."""
    rows = list(rows)
    n = len(rows)
    fn_counts = {cls: 0 for cls in FUNCTION_CLASSES}
    track_status_counts = {status: 0 for status in TRACK_STATUSES}
    track_counts: dict[str, int] = {}
    by_basis: dict[str, int] = {}
    unclassified_reasons: dict[str, int] = {}
    for row in rows:
        fn_counts[row["function_class"]] += 1
        track_status_counts[row["track_evidence"]["track_status"]] += 1
        basis = row["function_evidence"]["decision_basis"]
        by_basis[basis] = by_basis.get(basis, 0) + 1
        if row["track_id"]:
            track_counts[row["track_id"]] = track_counts.get(row["track_id"], 0) + 1
        if row["unclassified_reason"]:
            unclassified_reasons[row["unclassified_reason"]] = unclassified_reasons.get(row["unclassified_reason"], 0) + 1

    def rate(value: int) -> float:
        return round(value / n, 4) if n else 0.0

    return {
        "n": n,
        "function_class_counts": fn_counts,
        "function_class_rates": {cls: rate(v) for cls, v in fn_counts.items()},
        "unclassified_count": fn_counts[UNCLASSIFIED],
        "unclassified_rate": rate(fn_counts[UNCLASSIFIED]),
        "unclassified_reasons": unclassified_reasons,
        "function_decision_basis": by_basis,
        "track_status_counts": track_status_counts,
        "track_assigned_count": sum(track_counts.values()),
        "track_assigned_rate": rate(sum(track_counts.values())),
        "track_counts": dict(sorted(track_counts.items())),
        "versions": {
            "arm": ARM,
            "rules_version": RULES_VERSION,
            "function_map_version": function_map_version(),
            "function_map_fingerprint": function_map_fingerprint(),
            "taxonomy": taxonomy_regime(),
        },
        "confidence_statement": CONFIDENCE_DISCLAIMER,
    }
