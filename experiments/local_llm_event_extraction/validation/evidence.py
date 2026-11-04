"""Verbatim evidence location: the one thing a small model cannot bluff.

The rule
--------
An :class:`~..schema.EvidenceSpan` is supposed to be a quote, not a summary.
This module locates the quote in the source text and reports the exact span.  A
quote is a match when it differs from the source only by:

1. Unicode normalisation to **NFC**, and
2. whitespace runs collapsing to a single space (``\\s+`` -> ``" "``).

File:line wrapping, double spaces, tabs and newlines are exactly that kind of
formatting noise, so they still match; the location records *both* the offsets
in the raw text and the offsets in the normalised text so a reader can check.

Deliberate non-feature: no fuzzy matching
-----------------------------------------
There is **no** edit-distance, no token-overlap threshold, no "close enough"
fallback.  A paraphrase -- even a very good one -- fails with
``QUOTE_NOT_VERBATIM``.  This is a scientific instrument: if a model may reword
its citation, the citation no longer demonstrates that the model read the
sentence it claims to have read, and citation-correctness becomes a measure of
sentence embedding similarity rather than of evidence.  The validator therefore
never repairs a quote; it reports where (if anywhere) the exact text lives.

Offsets and Unicode
-------------------
NFC can change string length (``e`` + combining acute accent -> ``é``).  The
normalised-text builder tracks, for every normalised character, the raw
``[start, end)`` interval it came from.  Non-whitespace runs are normalised per
run; because NFC does not compose across whitespace, splitting at whitespace is
safe.  In the ordinary case the mapping is one normalised character per raw
character; when a run changes length the whole run's interval is attached to
each of its normalised characters (documented, conservative).

Boundary helper
---------------
:func:`span_boundary` returns the sentence or paragraph containing a span.  It
exists so a future UI can show a quote in context without re-implementing
sentence splitting; it is not used for matching.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from ..contracts import Severity, ValidationIssue
from ..schema import MAX_QUOTE_CHARS

__all__ = [
    "NormalisedText",
    "QuoteLocation",
    "QuoteCheck",
    "TextBoundary",
    "prepare_text",
    "normalise_text",
    "locate_quote",
    "locate_all_quotes",
    "check_quote",
    "paragraph_boundary",
    "sentence_boundary",
    "span_boundary",
]

_WHITESPACE_RUN = re.compile(r"\s+")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")
_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")


# --------------------------------------------------------------- normalisation
def _append_normalised_run(
    run: str,
    raw_offset: int,
    out_chars: list[str],
    out_starts: list[int],
    out_ends: list[int],
) -> None:
    """Append one non-whitespace run, recording per-character raw offsets."""
    normalised = unicodedata.normalize("NFC", run)
    if len(normalised) == len(run):
        for index, char in enumerate(normalised):
            out_chars.append(char)
            out_starts.append(raw_offset + index)
            out_ends.append(raw_offset + index + 1)
        return
    # Rare: NFC composed characters.  Attach the whole raw run to each output
    # character; conservative rather than silently wrong.
    run_end = raw_offset + len(run)
    for char in normalised:
        out_chars.append(char)
        out_starts.append(raw_offset)
        out_ends.append(run_end)


def prepare_text(text: str) -> "NormalisedText":
    """NFC-normalise ``text``, collapse whitespace runs, keep the raw mapping."""
    if not isinstance(text, str):
        raise TypeError(f"text must be a string, got {type(text).__name__}")
    chars: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    raw_index = 0
    for match in _WHITESPACE_RUN.finditer(text):
        if match.start() > raw_index:
            _append_normalised_run(text[raw_index : match.start()], raw_index, chars, starts, ends)
        chars.append(" ")
        starts.append(match.start())
        ends.append(match.end())
        raw_index = match.end()
    if raw_index < len(text):
        _append_normalised_run(text[raw_index:], raw_index, chars, starts, ends)
    return NormalisedText(
        text="".join(chars),
        raw_starts=tuple(starts),
        raw_ends=tuple(ends),
        raw_length=len(text),
    )


def normalise_text(text: str) -> str:
    """NFC + whitespace-collapse only, the exact allowance the matcher makes."""
    return prepare_text(text).text


@dataclass(frozen=True)
class NormalisedText:
    """Normalised text plus, per normalised character, its raw interval."""

    text: str
    raw_starts: tuple[int, ...]
    raw_ends: tuple[int, ...]
    raw_length: int

    def raw_span(self, normalised_start: int, normalised_end: int) -> tuple[int, int]:
        """Map a ``[start, end)`` range in normalised text to raw text."""
        if normalised_start < 0 or normalised_end > len(self.text) or normalised_start >= normalised_end:
            raise ValueError(
                f"normalised span [{normalised_start}:{normalised_end}] outside text of length {len(self.text)}"
            )
        return self.raw_starts[normalised_start], self.raw_ends[normalised_end - 1]


# -------------------------------------------------------------------- locating
@dataclass(frozen=True)
class QuoteLocation:
    """Where a quote lives, in both raw and normalised coordinates."""

    quote: str
    normalised_quote: str
    normalised_start: int
    normalised_end: int
    raw_start: int
    raw_end: int
    raw_text: str
    exact_raw: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "quote": self.quote,
            "normalised_quote": self.normalised_quote,
            "normalised_start": self.normalised_start,
            "normalised_end": self.normalised_end,
            "raw_start": self.raw_start,
            "raw_end": self.raw_end,
            "raw_text": self.raw_text,
            "exact_raw": self.exact_raw,
        }


def _matching_needle(quote: str) -> str:
    """The normalised search string for a quote.

    Collapsing whitespace already maps a leading/trailing run to a single space;
    searching for the *stripped* collapsed form additionally tolerates a quote
    that carries whitespace the source does not, which is still a formatting-only
    difference (never a wording difference).
    """
    return normalise_text(quote).strip()


def locate_all_quotes(document_text: str, quote: str) -> tuple[QuoteLocation, ...]:
    """Every occurrence of ``quote`` in ``document_text``, in source order."""
    if not isinstance(quote, str) or not quote.strip():
        return ()
    prepared = prepare_text(document_text)
    needle = _matching_needle(quote)
    if not needle:
        return ()
    locations: list[QuoteLocation] = []
    position = prepared.text.find(needle)
    while position != -1:
        normalised_end = position + len(needle)
        raw_start, raw_end = prepared.raw_span(position, normalised_end)
        raw_text = document_text[raw_start:raw_end]
        locations.append(
            QuoteLocation(
                quote=quote,
                normalised_quote=needle,
                normalised_start=position,
                normalised_end=normalised_end,
                raw_start=raw_start,
                raw_end=raw_end,
                raw_text=raw_text,
                exact_raw=raw_text == quote,
            )
        )
        position = prepared.text.find(needle, position + 1)
    return tuple(locations)


def locate_quote(document_text: str, quote: str, *, occurrence: int = 0) -> QuoteLocation | None:
    """Locate the ``occurrence``-th instance of ``quote``; ``None`` when absent."""
    locations = locate_all_quotes(document_text, quote)
    if occurrence < 0 or occurrence >= len(locations):
        return None
    return locations[occurrence]


@dataclass(frozen=True)
class QuoteCheck:
    """Result of checking one evidence quote against the document."""

    location: QuoteLocation | None
    issues: tuple[ValidationIssue, ...] = ()
    note: str | None = None


def check_quote(
    quote: str,
    *,
    document_text: str,
    min_chars: int = 8,
    max_chars: int = MAX_QUOTE_CHARS,
    require_verbatim: bool = True,
) -> QuoteCheck:
    """Check one quote for length and verbatim location.

    Returns findings as :class:`ValidationIssue` records with ``event_index``
    left as ``None``; the orchestrator fills in the event index.  Field names are
    relative to the span and get a ``evidence[i].`` prefix from the caller.
    """
    issues: list[ValidationIssue] = []
    stripped = quote.strip() if isinstance(quote, str) else ""
    if len(stripped) < min_chars:
        issues.append(
            ValidationIssue(
                code="EVIDENCE_TOO_SHORT",
                severity=Severity.ERROR,
                field="quote",
                detail=(
                    f"quote has {len(stripped)} characters after stripping outer whitespace; "
                    f"minimum is {min_chars}"
                ),
            )
        )
    if isinstance(quote, str) and len(quote) > max_chars:
        issues.append(
            ValidationIssue(
                code="EVIDENCE_TOO_LONG",
                severity=Severity.ERROR,
                field="quote",
                detail=f"quote has {len(quote)} characters; maximum is {max_chars}",
            )
        )
    location = locate_quote(document_text, quote) if stripped else None
    note: str | None = None
    if location is None:
        if require_verbatim:
            issues.append(
                ValidationIssue(
                    code="QUOTE_NOT_VERBATIM",
                    severity=Severity.ERROR,
                    field="quote",
                    detail=(
                        f"quote not found verbatim in the document (only NFC and whitespace "
                        f"normalisation are allowed; no fuzzy matching is performed): {quote[:120]!r}"
                    ),
                )
            )
    elif not location.exact_raw:
        note = (
            f"quote matched after NFC/whitespace normalisation only; "
            f"raw span [{location.raw_start}:{location.raw_end}] = {location.raw_text[:120]!r}"
        )
        issues.append(
            ValidationIssue(
                code="EVIDENCE_QUOTE_NORMALISED",
                severity=Severity.INFO,
                field="quote",
                detail=note,
            )
        )
    return QuoteCheck(location=location, issues=tuple(issues), note=note)


# ----------------------------------------------------------- boundary helper
@dataclass(frozen=True)
class TextBoundary:
    """A sentence or paragraph boundary in raw source coordinates."""

    start: int
    end: int
    unit: str

    def text_in(self, document_text: str) -> str:
        return document_text[self.start : self.end]

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "unit": self.unit}


def _clamp_span(text: str, start: int, end: int) -> tuple[int, int]:
    if not isinstance(start, int) or not isinstance(end, int):
        raise TypeError("start and end must be integers")
    if start > end:
        raise ValueError(f"start {start} is after end {end}")
    return max(0, start), min(len(text), end)


def _paragraph_segments(text: str) -> list[tuple[int, int]]:
    segments: list[tuple[int, int]] = []
    previous = 0
    for match in _PARAGRAPH_BREAK.finditer(text):
        segments.append((previous, match.start()))
        previous = match.end()
    segments.append((previous, len(text)))
    return segments


def paragraph_boundary(text: str, start: int, end: int) -> TextBoundary:
    """The paragraph(s) containing ``[start, end)``, expanded across breaks."""
    start, end = _clamp_span(text, start, end)
    segments = _paragraph_segments(text)
    first = next((seg for seg in segments if seg[0] <= start <= seg[1]), segments[-1])
    last = next((seg for seg in reversed(segments) if seg[0] <= end <= seg[1]), segments[-1])
    return TextBoundary(start=first[0], end=last[1], unit="paragraph")


def sentence_boundary(text: str, start: int, end: int) -> TextBoundary:
    """The sentence(s) containing ``[start, end)``, capped by paragraph bounds."""
    start, end = _clamp_span(text, start, end)
    paragraph = paragraph_boundary(text, start, end)
    sentence_spans: list[tuple[int, int]] = []
    sentence_start = paragraph.start
    for match in _SENTENCE_END.finditer(text, paragraph.start, paragraph.end):
        sentence_spans.append((sentence_start, match.end()))
        sentence_start = match.end()
        while sentence_start < paragraph.end and text[sentence_start].isspace():
            sentence_start += 1
    sentence_spans.append((sentence_start, paragraph.end))
    covering = [span for span in sentence_spans if span[0] <= end and span[1] >= start]
    if not covering:
        return TextBoundary(start=paragraph.start, end=paragraph.end, unit="sentence")
    return TextBoundary(start=covering[0][0], end=covering[-1][1], unit="sentence")


def span_boundary(text: str, start: int, end: int, *, unit: str = "sentence") -> TextBoundary:
    """Return the sentence or paragraph boundary containing a span."""
    if unit == "sentence":
        return sentence_boundary(text, start, end)
    if unit == "paragraph":
        return paragraph_boundary(text, start, end)
    raise ValueError(f"unknown boundary unit {unit!r}; expected 'sentence' or 'paragraph'")
