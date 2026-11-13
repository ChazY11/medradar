"""Pre-registered text features, extracted from the archive document itself.

The lexicons below are the *operational definition* of "technology or R&D
relevant public disclosure". They were fixed before the experiment was run and
are not tuned. A feature is a rate per 1,000 words inside the prose of one
filing's own documents, so length cannot masquerade as intensity.
"""

from __future__ import annotations

import html
import re
from typing import Any, Iterable, Sequence

from .edgar import RawDocument, content_documents

#: Activity terms: research spending and clinical/regulatory development.
RD_TERMS: tuple[str, ...] = (
    "research and development",
    "research & development",
    "r&d",
    "clinical trial",
    "clinical trials",
    "clinical study",
    "clinical studies",
    "clinical data",
    "randomized",
    "randomised",
    "pivotal",
    "premarket approval",
    "pre-market approval",
    "510(k)",
    "investigational device",
    "regulatory submission",
    "regulatory approval",
    "fda clearance",
    "fda approval",
    "ce mark",
    "ce-mark",
    "product development",
    "design verification",
    "prototype",
    "pipeline",
)

#: Technology/innovation terms: the "technology development" half of the question.
TECH_TERMS: tuple[str, ...] = (
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "generative ai",
    "algorithm",
    "algorithms",
    "software",
    "platform",
    "sensor",
    "sensors",
    "robotic",
    "robotics",
    "next-generation",
    "next generation",
    "innovation",
    "innovative",
    "automation",
    "connectivity",
    "cloud",
    "precision medicine",
    "minimally invasive",
    "wearable",
    "wearables",
    "digital health",
    "telehealth",
)

_TAG = re.compile(r"<[^>]{0,400}>")
_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_ENTITY = re.compile(r"&[a-zA-Z]{2,10};|&#\d{1,6};")
_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{0,40}")
_NON_PRINTABLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def to_text(raw: str) -> str:
    """HTML-ish document fragment -> lowercase prose with collapsed whitespace."""
    text = _SCRIPT.sub(" ", raw)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    text = _ENTITY.sub(" ", text)
    text = _NON_PRINTABLE.sub(" ", text)
    text = text.replace("\u00a0", " ").replace("\u2019", "'")
    return re.sub(r"\s+", " ", text).strip()


def words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def count_terms(text: str, terms: Sequence[str]) -> int:
    """Non-overlapping phrase counts on lowercased, whitespace-collapsed text."""
    lowered = " " + text.lower() + " "
    total = 0
    for term in terms:
        needle = " " + term + " "
        start = 0
        while True:
            index = lowered.find(needle, start)
            if index < 0:
                break
            total += 1
            start = index + len(needle) - 1
    return total


def extract_features(documents: Iterable[RawDocument]) -> dict[str, Any]:
    """Word-count and lexicon features for one filing's own prose."""
    prose = content_documents(documents)
    joined = " ".join(to_text(document.text) for document in prose)
    tokens = words(joined)
    n_words = len(tokens)
    rd_hits = count_terms(joined, RD_TERMS)
    tech_hits = count_terms(joined, TECH_TERMS)
    exhibit_words = 0
    for document in prose:
        if document.doc_type.upper().startswith("EX-"):
            exhibit_words += len(words(to_text(document.text)))
    scale = max(n_words, 1) / 1000.0
    return {
        "n_documents": len(prose),
        "words": n_words,
        "words_per_document": round(n_words / len(prose), 1) if prose else 0.0,
        "exhibit_words": exhibit_words,
        "exhibit_share": round(exhibit_words / n_words, 4) if n_words else 0.0,
        "rd_hits": rd_hits,
        "tech_hits": tech_hits,
        "rd_per_1k": round(rd_hits / scale, 4) if n_words else 0.0,
        "tech_per_1k": round(tech_hits / scale, 4) if n_words else 0.0,
        "dev_hits": rd_hits + tech_hits,
        "dev_per_1k": round((rd_hits + tech_hits) / scale, 4) if n_words else 0.0,
    }
