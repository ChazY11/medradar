"""JATS XML -> sections, for the full-text paper lane.

Why a separate parser instead of flattening to text and re-splitting
--------------------------------------------------------------------
``documents.split_sections`` was written for 510(k) PDFs, where the only structure available is
line-level: a heading is a short line, everything until the next heading is its body. A journal
article arrives as JATS XML, which states the structure explicitly in ``<sec>``/``<title>``/<p>``.
Flattening that to text and guessing the boundaries again would throw away the one thing the
publisher was sure about.

Measured 2026-11-24: ``PMC13787585`` returns 54,517 bytes of JATS with one ``<abstract>``, one
``<body>``, 5 top-level ``<sec>`` and 13 ``<title>`` elements.

Namespaces
----------
Europe PMC serves JATS without a default namespace; the preprint servers serve NLM JATS 3.x, which
sometimes carries one. Tags are therefore matched with any ``{namespace}`` prefix stripped, so the
same walker reads both.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

#: Headings that mean the same thing in different journals, so a caller can ask one question.
#: Mapped to a canonical name; the original heading is kept in ``headings``.
CANONICAL = {
    "methods": ("method", "methods", "materials and methods", "methodology",
                "patients and methods", "subjects and methods", "experimental section"),
    "results": ("result", "results", "findings"),
    "conclusions": ("conclusion", "conclusions", "concluding remarks", "interpretation"),
    "discussion": ("discussion",),
    "introduction": ("introduction", "background"),
    "limitations": ("limitations", "study limitations"),
}

MAX_SECTION_CHARS = 20_000
MAX_TOTAL_CHARS = 400_000


@dataclass
class JatsDocument:
    title: str = ""
    abstract: str = ""
    journal: str = ""
    licence: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    headings: list[str] = field(default_factory=list)
    canonical: dict[str, str] = field(default_factory=dict)
    body_chars: int = 0
    reference_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "abstract": self.abstract, "journal": self.journal,
                "licence": self.licence, "sections": self.sections,
                "headings": self.headings, "canonical": self.canonical,
                "body_chars": self.body_chars, "reference_count": self.reference_count}


class JatsError(ValueError):
    """The payload is not parseable JATS. Never treated as 'the paper has no sections'."""


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1].lower()


def _text(element: ET.Element) -> str:
    return " ".join("".join(element.itertext()).split())


def _clean_heading(raw: str) -> str:
    """Drop numbering and punctuation so "2.3 Study Limitations." becomes "study limitations".

    The numeral token must be followed by a separator. Without that rule ``[IVXLC]+`` eats the
    leading "I" of "Introduction" and the section arrives as "ntroduction" - measured on the first
    real record this parser ever saw (PMC13744766, Cureus).
    """
    text = re.sub(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[IVXLC]+[.)])\s*", "", raw or "")
    return text.strip(" .:;—-").strip()


def _canonical_for(heading: str) -> str | None:
    lowered = heading.lower()
    for name, variants in CANONICAL.items():
        for variant in variants:
            if lowered == variant or lowered.startswith(variant):
                return name
    return None


def _walk(element: ET.Element, prefix: str, out: dict[str, str], headings: list[str],
          budget: list[int]) -> None:
    for child in element:
        if _tag(child) != "sec":
            continue
        title_element = next((c for c in child if _tag(c) == "title"), None)
        heading = _clean_heading(_text(title_element)) if title_element is not None else ""
        label = heading or (f"section {len(headings) + 1}")
        full = f"{prefix} > {label}" if prefix else label
        headings.append(full)
        # Body text of this section only: stop at nested <sec> so a parent does not swallow its
        # children's paragraphs and report them twice.
        pieces: list[str] = []
        for node in child:
            tag = _tag(node)
            if tag in ("sec", "title"):
                # ``title`` is the heading itself; collecting it would repeat the heading at the
                # start of every section body, which is exactly what the canonical map then
                # hands to a caller who asked for "the results".
                continue
            if tag in ("p", "list-item", "caption", "disp-quote", "statement"):
                text = _text(node)
                if text:
                    pieces.append(text)
        body = " ".join(pieces)[:MAX_SECTION_CHARS]
        if body:
            if budget[0] <= 0:
                return
            body = body[:budget[0]]
            budget[0] -= len(body)
            out[full] = body
        _walk(child, full, out, headings, budget)


def parse_jats(raw: bytes) -> JatsDocument:
    """Parse one JATS article into a section map, or raise :class:`JatsError`."""
    if not raw or b"<" not in raw[:2048]:
        raise JatsError("payload does not look like XML")
    text = raw.decode("utf-8", errors="replace")
    # Several publishers prepend a DOCTYPE with an external DTD; ElementTree never fetches it, but
    # a stray DOCTYPE internal subset can still confuse the parser, so it is dropped.
    text = re.sub(r"<!(?:DOCTYPE|ENTITY)[^>]*>", "", text, flags=re.IGNORECASE)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise JatsError(f"unparseable JATS: {error}") from error

    document = JatsDocument()
    article_title = next((e for e in root.iter() if _tag(e) == "article-title"), None)
    if article_title is not None:
        document.title = _text(article_title)
    journal = next((e for e in root.iter() if _tag(e) == "journal-title"), None)
    if journal is not None:
        document.journal = _text(journal)

    for element in root.iter():
        tag = _tag(element)
        if tag in ("license", "licence"):
            candidate = element.get("{http://www.w3.org/1999/xlink}href") or _text(element)
            if candidate:
                document.licence = candidate.strip()[:200]
        elif tag == "abstract" and not document.abstract:
            document.abstract = _text(element)[:MAX_SECTION_CHARS]
        elif tag == "ref-list":
            document.reference_count += sum(1 for c in element if _tag(c) == "ref")

    body = next((e for e in root.iter() if _tag(e) == "body"), None)
    budget = [MAX_TOTAL_CHARS]
    if body is not None:
        _walk(body, "", document.sections, document.headings, budget)
        document.body_chars = sum(len(value) for value in document.sections.values())

    for heading in document.headings:
        leaf = heading.rsplit(" > ", 1)[-1]
        name = _canonical_for(leaf)
        if name and name not in document.canonical:
            document.canonical[name] = document.sections.get(heading, "")

    if not document.sections and not document.abstract:
        raise JatsError("JATS parsed but contained no body text or abstract")
    return document


__all__ = ["CANONICAL", "JatsDocument", "JatsError", "parse_jats"]
