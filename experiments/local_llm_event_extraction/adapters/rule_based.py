"""Arm A: a deterministic, dependency-free rules baseline over the source text.

This is a real, executable baseline, not a stub.  It is also deliberately
conservative:

* it only fires when a keyword rule matches inside one sentence AND the sentence
  (or the document) names a company from the injected alias map;
* the evidence it emits is the verbatim sentence span that carried the match, so
  the real validator can locate it character-for-character;
* it never carries a date across sentences and never reads the publication date
  into ``event_date`` -- the press-release-vs-event-date conflation that
  ``research/DATA_PROVENANCE.md`` §1 forbids;
* it abstains, with an explicit reason, rather than emitting a guessed event.

The alias map is injected as a plain ``Mapping[str, str]`` (alias text ->
canonical company id) so this module does not import or depend on the validator's
``EntityRoster``.  When the validator exists, the caller can build the mapping
from the roster; when it does not, the rules still run.

``describe_rules()`` returns the rule table for the benchmark report, so a reader
can see exactly which patterns produced which arm-A numbers.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Mapping

from ..schema import (
    EntityClaim,
    EventExtraction,
    EvidenceSpan,
    ExtractionResult,
    ExtractorProvenance,
    TimestampQuality,
)
from .base import (
    AdapterDescriptor,
    AdapterResponse,
    AdapterUnavailable,
    ExtractionRequest,
    ModelAdapter,
)

RULES_VERSION = "rules-v1"
_MAX_QUOTE_CHARS = 600
_MIN_QUOTE_CHARS = 8


@dataclass(frozen=True)
class Rule:
    """One keyword rule: an event category plus its patterns and suppression set."""

    category: str
    patterns: tuple[str, ...]
    description: str
    suppresses: tuple[str, ...] = ()


# Order matters: the table is the deterministic priority order.  Negative and
# trial-specific rules suppress the broader positive rules so that one sentence
# does not produce both "approval" and "not approved".
_RULE_TABLE: tuple[Rule, ...] = (
    Rule(
        "regulatory_negative",
        (
            r"\bcomplete response letter\b",
            r"\bnot\s+(?:been\s+)?approved\b",
            r"\bdeclin(?:ed|es)\s+to\s+approve\b",
            r"\brefus(?:ed|es)\s+to\s+(?:approve|clear|grant)\b",
            r"\bdeni(?:ed|es)\b",
            r"\brejected\b",
            r"\bwarning letter\b",
            r"\bfailed to (?:win|gain|obtain) (?:approval|clearance)\b",
        ),
        "A regulator refused, rejected or blocked the product.",
        suppresses=("regulatory_approval", "regulatory_clearance", "regulatory_submission"),
    ),
    Rule(
        "regulatory_submission",
        (
            r"\b510\s*\(k\)\s+submission\b",
            r"\bpremarket approval application\b",
            r"\b(?:submitted|filed)\b[^.]{0,60}\b(?:510\s*\(k\)|pma|premarket|de novo)\b",
            r"\bregulatory submission\b",
        ),
        "A dossier was filed with a regulator.",
        suppresses=("regulatory_approval", "regulatory_clearance"),
    ),
    Rule(
        "regulatory_approval",
        (
            r"\bpremarket approval\b",
            r"\bfda approval\b",
            r"\bapproved by the\b[^.]{0,20}\bfood and drug administration\b",
            r"\b(?:granted|received|obtained|won)\b[^.]{0,40}\bapproval\b",
            r"\bpma (?:approval|supplement)\b",
        ),
        "A regulator granted approval (e.g. PMA).",
    ),
    Rule(
        "regulatory_clearance",
        (
            r"\b510\s*\(k\)\s+clearance\b",
            r"\bfda clearance\b",
            r"\bclear(?:ed|ance)\b[^.]{0,40}\bfood and drug administration\b",
            r"\bfood and drug administration\b[^.]{0,60}\bclearance\b",
            r"\bce mark\b",
            r"\bde novo\b",
            r"\bgranted\b[^.]{0,40}\bclearance\b",
            r"\bclearance\b",
        ),
        "A regulator cleared a device (510(k), CE mark, De Novo).",
    ),
    Rule(
        "safety_recall",
        (
            r"\brecall(?:s|ed)?\b",
            r"\bclass (?:i|ii|iii) recall\b",
            r"\bfield safety (?:notice|corrective action)\b",
            r"\bmarket withdrawal\b",
            r"\bwithdraw(?:s|n)?\b[^.]{0,40}\bfrom (?:the )?market\b",
            r"\bsafety alert\b",
        ),
        "A product was recalled or withdrawn from the market.",
    ),
    Rule(
        "clinical_trial_start",
        (
            r"\b(?:initiated|began|started|commenced|launched)\b[^.]{0,60}\b(?:phase\s+(?:i|ii|iii|1|2|3)|pivotal|clinical)\s+(?:trial|study)\b",
            r"\b(?:phase\s+(?:i|ii|iii|1|2|3)|pivotal|clinical)\s+(?:trial|study)\b[^.]{0,40}\b(?:began|started|initiated|commenced)\b",
            r"\b(?:study|trial)\s+(?:began|started|was initiated)\b",
            r"\bfirst patient (?:was )?(?:enrolled|dosed)\b",
            r"\b(?:enrolled|dosed)\b[^.]{0,30}\bfirst patient\b",
        ),
        "A clinical trial or study started.",
        suppresses=("product_launch",),
    ),
    Rule(
        "clinical_trial_result",
        (
            r"\btopline (?:results|data)\b",
            r"\b(?:primary|secondary) endpoint\b",
            r"\bmet (?:the |its )?(?:primary|secondary) endpoint\b",
            r"\bresults (?:from|of) the\b[^.]{0,60}\b(?:trial|study)\b",
            r"\bdid not meet\b[^.]{0,40}\bendpoint\b",
        ),
        "Trial results were reported.",
        suppresses=("product_launch",),
    ),
    Rule(
        "product_discontinuation",
        (
            r"\bdiscontinu(?:ed|es|ation)\b",
            r"\bceas(?:ed|es)\b[^.]{0,40}\b(?:sales|distribution|manufacturing)\b",
            r"\bend(?:ed|s)\b[^.]{0,30}\b(?:sales|distribution)\b",
        ),
        "A product or line was discontinued.",
        suppresses=("product_launch",),
    ),
    Rule(
        "product_launch",
        (
            r"\blaunch(?:ed|es|ing)?\b",
            r"\bcommercial(?:ly)? (?:launch|availability|release)\b",
            r"\bnow available\b",
            r"\bmarket (?:launch|release|availability)\b",
            r"\bintroduc(?:ed|es)\b[^.]{0,40}\b(?:product|system|device|platform)\b",
            r"\breleased\b[^.]{0,40}\b(?:commercially|in the us|nationwide)\b",
            r"\bbeg(?:an|un)\b[^.]{0,40}\b(?:selling|shipping|commercial)\b",
        ),
        "A product was launched or made commercially available.",
    ),
    Rule(
        "m_and_a",
        (
            r"\bdefinitive agreement to acquire\b",
            r"\bacquir(?:e|ed|es|ing|ition)\b",
            r"\bmerger\b",
        ),
        "One company acquired or merged with another.",
    ),
    Rule(
        "rd_collaboration",
        (
            r"\bjoint development\b",
            r"\bco-?develop(?:ment|ed|s)?\b",
            r"\bresearch (?:agreement|collaboration)\b",
            r"\blicen[cs]e agreement\b",
            r"\bcollaborat(?:e|ed|ion|ions)\b",
        ),
        "A research/development collaboration or licence was announced.",
    ),
    Rule(
        "partnership",
        (
            r"\bstrategic alliance\b",
            r"\bpartnership\b",
            r"\bpartner(?:ed|s)? with\b",
        ),
        "A commercial partnership or alliance was announced.",
    ),
    Rule(
        "manufacturing_change",
        (
            r"\bmanufacturing (?:facility|expansion|plant|site)\b",
            r"\bnew (?:manufacturing|production) (?:line|facility|site)\b",
        ),
        "A manufacturing footprint change.",
    ),
    Rule(
        "patent_grant",
        (
            r"\bpatent (?:was |is |has been )?granted\b",
            r"\b(?:granted|issued)\b[^.]{0,30}\bpatent\b",
        ),
        "A patent was granted.",
    ),
    Rule(
        "scientific_publication",
        (
            r"\bpublished\b[^.]{0,60}\b(?:journal|peer[- ]reviewed|study|paper|article)\b",
            r"\bpublished in\b",
            r"\bpeer[- ]reviewed\b",
            r"\bjournal of\b",
            r"\bmanuscript\b",
        ),
        "A peer-reviewed result was published.",
    ),
)

_COMPILED_RULES: tuple[tuple[Rule, tuple[re.Pattern[str], ...]], ...] = tuple(
    (rule, tuple(re.compile(pattern, re.IGNORECASE) for pattern in rule.patterns))
    for rule in _RULE_TABLE
)

_SENTENCE_SPLITTER = re.compile(r"[.!?](?=\s|$)|\n+")

_MONTHS: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_ALTERNATION = "|".join(_MONTHS)

_DATE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})\b"),
        "exact_day",
    ),
    (
        re.compile(r"\b(?P<month>0?[1-9]|1[0-2])/(?P<day>0?[1-9]|[12]\d|3[01])/(?P<year>\d{4})\b"),
        "exact_day",
    ),
    (
        re.compile(
            rf"\b(?P<month_name>{_MONTH_ALTERNATION})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<year>\d{{4}})\b",
            re.IGNORECASE,
        ),
        "exact_day",
    ),
    (
        re.compile(
            rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month_name>{_MONTH_ALTERNATION})\s+(?P<year>\d{{4}})\b",
            re.IGNORECASE,
        ),
        "exact_day",
    ),
    (
        re.compile(r"\b(?P<year>\d{4})-(?P<month>0?[1-9]|1[0-2])\b"),
        "exact_month",
    ),
    (
        re.compile(
            rf"\b(?P<month_name>{_MONTH_ALTERNATION})\s+(?P<year>\d{{4}})\b",
            re.IGNORECASE,
        ),
        "exact_month",
    ),
)


@dataclass(frozen=True)
class DateMatch:
    start: int
    end: int
    iso: str
    quality: str


@dataclass(frozen=True)
class Sentence:
    start: int
    end: int
    text: str


def rules_descriptor(
    adapter_id: str = "rules-baseline",
    *,
    display_name: str = "ARM A - deterministic rules baseline",
    max_input_chars: int = 12_000,
    enabled_by_default: bool = True,
    notes: str = (
        "No model, no network, no dependency. Alias map and keyword rules are injected; "
        "abstains with an explicit reason instead of guessing."
    ),
) -> AdapterDescriptor:
    return AdapterDescriptor(
        adapter_id=adapter_id,
        display_name=display_name,
        backend="rule_based",
        model_id=None,
        model_revision=None,
        quantization=None,
        device="cpu",
        max_input_chars=max_input_chars,
        max_new_tokens=0,
        prompt_version=None,
        requires_network=False,
        requires_gpu=False,
        deterministic=True,
        load_gate=None,
        enabled_by_default=enabled_by_default,
        notes=notes,
    )


def split_sentences(text: str) -> tuple[Sentence, ...]:
    """Split text into sentence spans while keeping absolute character offsets.

    Abbreviation handling is intentionally minimal (the rule baseline should not
    pretend to be a parser); the fixtures avoid abbreviations so evidence spans
    line up exactly with what a validator will locate.
    """
    sentences: list[Sentence] = []
    cursor = 0
    for match in _SENTENCE_SPLITTER.finditer(text):
        end = match.end()
        _append_sentence(sentences, text, cursor, end)
        cursor = end
    if cursor < len(text):
        _append_sentence(sentences, text, cursor, len(text))
    return tuple(sentences)


def _append_sentence(target: list[Sentence], text: str, start: int, end: int) -> None:
    raw = text[start:end]
    stripped = raw.strip()
    if not stripped:
        return
    left = len(raw) - len(raw.lstrip())
    right = len(raw) - len(raw.rstrip())
    target.append(Sentence(start=start + left, end=end - right, text=stripped))


def extract_dates(text: str) -> tuple[DateMatch, ...]:
    """All plausible dates in ``text``, longest/leftmost wins on overlap."""
    candidates: list[DateMatch] = []
    for pattern, quality in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            iso = _date_iso(match, quality)
            if iso is None:
                continue
            candidates.append(DateMatch(start=match.start(), end=match.end(), iso=iso, quality=quality))
    if not candidates:
        return ()
    candidates.sort(key=lambda item: (item.start, -(item.end - item.start)))
    kept: list[DateMatch] = []
    for candidate in candidates:
        if kept and candidate.start < kept[-1].end:
            continue
        kept.append(candidate)
    return tuple(kept)


def _date_iso(match: re.Match[str], quality: str) -> str | None:
    groups = match.groupdict()
    year_text = groups.get("year")
    if year_text is None:
        return None
    year = int(year_text)
    if not 1900 <= year <= 2100:
        return None
    if quality == "exact_day":
        month_text = groups.get("month")
        if month_text is not None:
            month = int(month_text)
        else:
            month_name = (groups.get("month_name") or "").lower()
            month = _MONTHS.get(month_name, 0)
        day = int(groups.get("day") or 0)
        if not 1 <= month <= 12 or not 1 <= day <= 31:
            return None
        return f"{year:04d}-{month:02d}-{day:02d}"
    month_text = groups.get("month")
    if month_text is not None:
        month = int(month_text)
    else:
        month_name = (groups.get("month_name") or "").lower()
        month = _MONTHS.get(month_name, 0)
    if not 1 <= month <= 12:
        return None
    return f"{year:04d}-{month:02d}"


def _quality_for_iso(value: str | None) -> str:
    if not value:
        return "absent"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return "exact_day"
    if re.fullmatch(r"\d{4}-\d{2}", value):
        return "exact_month"
    if re.fullmatch(r"\d{4}", value):
        return "exact_year"
    return "approximate"


def _alias_sort_key(alias: str) -> tuple[int, str]:
    return (-len(alias), alias.lower())


def find_alias(text: str, alias_map: Mapping[str, str]) -> tuple[str, str, int, str] | None:
    """Earliest, then longest alias occurrence.

    Returns ``(raw_text_as_seen, canonical_id, start, matched_alias)`` or ``None``.
    """
    best: tuple[int, int, str, str, str] | None = None  # (start, -length, raw, canonical, alias)
    for alias in sorted(alias_map, key=_alias_sort_key):
        canonical = alias_map[alias]
        if not alias or not canonical:
            continue
        pattern = re.compile(
            r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])", re.IGNORECASE
        )
        match = pattern.search(text)
        if match is None:
            continue
        raw = match.group(0)
        candidate = (match.start(), -len(alias), raw, canonical, alias)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    if best is None:
        return None
    return best[2], best[3], best[0], best[4]


class RuleBasedAdapter(ModelAdapter):
    """Deterministic extractor implementing the ``ModelAdapter`` protocol."""

    def __init__(
        self,
        descriptor: AdapterDescriptor | None = None,
        *,
        alias_map: Mapping[str, str] | None = None,
        max_quote_chars: int = _MAX_QUOTE_CHARS,
        min_quote_chars: int = _MIN_QUOTE_CHARS,
    ) -> None:
        self._descriptor = descriptor or rules_descriptor()
        if self._descriptor.backend != "rule_based":
            raise ValueError("RuleBasedAdapter requires a descriptor with backend='rule_based'")
        self._alias_map: dict[str, str] = {}
        for alias, canonical in dict(alias_map or {}).items():
            if not isinstance(alias, str) or not isinstance(canonical, str) or not alias or not canonical:
                raise ValueError("alias_map must map non-empty alias strings to non-empty canonical ids")
            self._alias_map[alias] = canonical
        self._max_quote_chars = int(max_quote_chars)
        self._min_quote_chars = int(min_quote_chars)
        self._loaded = False
        self._last_trace: dict[str, Any] = {}

    # ------------------------------------------------------------- protocol
    @property
    def descriptor(self) -> AdapterDescriptor:
        return self._descriptor

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        # No weights, no network: "loading" only flips a flag so the protocol is
        # uniform and a caller cannot forget a real load step for the other arms.
        self._loaded = True

    def unload(self) -> None:
        self._loaded = False

    def generate(self, request: ExtractionRequest) -> AdapterResponse:
        if not self._loaded:
            raise AdapterUnavailable(
                f"{self._descriptor.adapter_id}: generate() called before load(); refusing implicit load"
            )
        started = time.perf_counter()
        result, trace = self._extract_impl(request)
        elapsed = time.perf_counter() - started
        self._last_trace = trace
        return AdapterResponse(
            text=json.dumps(result.to_dict(include_raw=False), ensure_ascii=False),
            finish_reason="stop",
            tokens_in=None,  # not tokenised: not measured, not zero
            tokens_out=None,
            wall_time_s=elapsed,
            peak_vram_mb=None,
            metadata={
                "deterministic": True,
                "rules_version": RULES_VERSION,
                "trace": trace,
            },
        )

    # ------------------------------------------------------------- extraction
    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        """Produce the ExtractionResult directly (used by tests and the report)."""
        result, _trace = self._extract_impl(request)
        return result

    def describe_rules(self) -> list[dict[str, Any]]:
        return [
            {
                "category": rule.category,
                "patterns": list(rule.patterns),
                "description": rule.description,
                "suppresses": list(rule.suppresses),
            }
            for rule in _RULE_TABLE
        ]

    @property
    def last_trace(self) -> dict[str, Any]:
        return dict(self._last_trace)

    def _provenance(self) -> ExtractorProvenance:
        return ExtractorProvenance(
            system="rule_based",
            adapter_id=self._descriptor.adapter_id,
            model_id=None,
            model_revision=None,
            prompt_version=None,
            decoding={
                "temperature": 0,
                "deterministic": True,
                "rules_version": RULES_VERSION,
                "alias_map_size": len(self._alias_map),
            },
        )

    def _extract_impl(self, request: ExtractionRequest) -> tuple[ExtractionResult, dict[str, Any]]:
        text = request.text or ""
        metadata = dict(request.metadata or {})
        published_at = metadata.get("published_at")
        first_seen_at = metadata.get("first_seen_at")

        doc_alias = find_alias(text, self._alias_map)
        sentences = split_sentences(text)
        events: list[EventExtraction] = []
        # One event per (category, company) per document: a later sentence that
        # re-states the same claim (e.g. "the clearance follows ...") must not
        # become a second, date-less duplicate.
        seen_keys: set[tuple[str, str]] = set()
        rule_fired = False
        company_missing = False

        for sentence in sentences:
            categories = self._match_categories(sentence.text)
            if not categories:
                continue
            rule_fired = True
            sentence_alias = find_alias(sentence.text, self._alias_map) or doc_alias
            if sentence_alias is None:
                company_missing = True
                continue
            raw_company, canonical_id, _alias_start, matched_alias = sentence_alias
            match_basis = (
                "roster_alias_verbatim"
                if raw_company == matched_alias
                else "roster_alias_in_document"
            )
            date = extract_dates(sentence.text)
            sentence_date = date[0] if date else None
            for category in categories:
                key = (category, canonical_id)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                events.append(
                    EventExtraction(
                        status="extracted",
                        company=EntityClaim(
                            raw_text=raw_company,
                            canonical_id=canonical_id,
                            match_basis=match_basis,
                        ),
                        event_category=category,
                        event_date=sentence_date.iso if sentence_date else None,
                        published_at=published_at,
                        first_seen_at=first_seen_at,
                        timestamp_quality=TimestampQuality(
                            event_date=sentence_date.quality if sentence_date else "absent",
                            published_at=_quality_for_iso(published_at),
                            first_seen_at=_quality_for_iso(first_seen_at),
                        ),
                        evidence=(
                            self._evidence_span(sentence, text, field="event_category"),
                        ),
                        rationale=None,
                    )
                )

        if events:
            result = ExtractionResult(
                doc_id=request.doc_id,
                parse_status="ok",
                extractor=self._provenance(),
                events=tuple(events),
            )
            return result, {
                "rules_fired": True,
                "events": len(events),
                "categories": [event.event_category for event in events],
                "abstain_reason": None,
            }

        abstain_reason = "ambiguous_company" if (rule_fired and company_missing) else "no_event"
        fallback_company = (
            EntityClaim(raw_text=doc_alias[0], canonical_id=doc_alias[1], match_basis="roster_alias_in_document")
            if doc_alias
            else EntityClaim()
        )
        abstained = EventExtraction(
            status="abstained",
            company=fallback_company,
            abstain_reason=abstain_reason,
            rationale=(
                "keyword rule matched but no roster company could be resolved"
                if abstain_reason == "ambiguous_company"
                else "no deterministic keyword rule matched a target event"
            ),
        )
        result = ExtractionResult(
            doc_id=request.doc_id,
            parse_status="ok",
            extractor=self._provenance(),
            events=(abstained,),
        )
        return result, {
            "rules_fired": rule_fired,
            "events": 0,
            "categories": [],
            "abstain_reason": abstain_reason,
        }

    def _evidence_span(self, sentence: Sentence, text: str, *, field: str) -> EvidenceSpan:
        quote = text[sentence.start : sentence.end]
        if len(quote) > self._max_quote_chars:
            quote = quote[: self._max_quote_chars]
        # ``quote`` is a slice of the source text, so it is verbatim by construction.
        if len(quote.strip()) < self._min_quote_chars:  # pragma: no cover - fixtures never hit this
            raise ValueError("rule evidence span is shorter than the configured minimum")
        return EvidenceSpan(
            quote=quote,
            field=field,
            char_start=sentence.start,
            char_end=sentence.start + len(quote),
        )

    @staticmethod
    def _match_categories(sentence: str) -> list[str]:
        matched = [rule for rule, patterns in _COMPILED_RULES if any(p.search(sentence) for p in patterns)]
        if not matched:
            return []
        suppressed: set[str] = set()
        for rule in matched:
            suppressed.update(rule.suppresses)
        ordered: list[str] = []
        for rule in matched:
            if rule.category in suppressed:
                continue
            if rule.category not in ordered:
                ordered.append(rule.category)
        return ordered


__all__ = [
    "DateMatch",
    "RULES_VERSION",
    "Rule",
    "RuleBasedAdapter",
    "Sentence",
    "extract_dates",
    "find_alias",
    "rules_descriptor",
    "split_sentences",
]
