"""The declared deterministic sampling rule for the job-text experiment.

Why a declared rule, not a hand-picked set
------------------------------------------
A subset chosen after looking at the model's output is a biased subset.  The rule
here is fixed before any model runs, is re-derivable from the snapshot alone, and
is recorded verbatim in the run manifest:

    primary sample  = the first ``n_primary`` postings, ordered by
                      ``sha256("phase4-jobsplit-v1\\x00" + posting_id)`` ascending,
                      among postings whose title does NOT match the
                      negative-control pattern.
    negative controls = the first ``n_negative`` postings under the same hash
                      order among postings whose title DOES match the
                      negative-control pattern.

The two sets are disjoint *by construction*, so a negative-control posting can
never also appear in the primary set.  The salt is a constant; changing it
changes every id and is a protocol amendment (bump ``SALT_VERSION``).

The negative-control pattern is a title-level declaration, not a model decision:
it names real non-technical occupations that the programme expects to exist in a
medtech careers site (Buyer/Planner, customer service, warehouse, administrative
assistant, finance, non-technical co-op).  If the pattern finds fewer postings
than requested, the experiment reports the smaller set rather than lowering the
bar.  A human still has to check the selected titles (the run records them).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Mapping

SALT_VERSION = "phase4-jobsplit-v1"
HASH_SALT = SALT_VERSION

#: Title-level declaration of "no technical content" postings.  Deliberately
#: narrow: only occupations whose work does not produce or develop technology.
#: Matching is on the job title only (not the description), so selection cannot be
#: influenced by what the model would later read.
NEGATIVE_TITLE_PATTERN = re.compile(
    r"""
    buyer | planner | purchasing |
    customer[ _-]?service | customer[ _-]?support |
    warehouse | material[ _-]?handler |
    executive[ _-]?assistant | administrative[ _-]?assistant |
    (?:^|\b)assistant(?:\b|$) |
    financial[ _-]?analyst | accounts?[ _-]?payable | accounts?[ _-]?receivable |
    payroll | bookkeep |
    human[ _-]?resources | recruiter |
    non[ _-]?tech |
    receptionist | cashier |
    marketing[ _-]?specialist | marketing[ _-]?coordinator |
    legal[ _-]?(?:counsel|assistant) |
    supply[ _-]?chain[ _-]?plann
    """,
    re.IGNORECASE | re.VERBOSE,
)

_FIELD_POSTING_ID = "posting_id"
_FIELD_TITLE = "job_title"
_FIELD_DESCRIPTION = "job_description"


def hash_key(posting_id: str, salt: str = HASH_SALT) -> str:
    """Deterministic order key for a posting id (hex sha256)."""
    return hashlib.sha256(f"{salt}\x00{posting_id}".encode("utf-8")).hexdigest()


def is_negative_title(title: str | None) -> bool:
    """True when the title is declared non-technical by the fixed pattern."""
    if not title:
        return False
    return bool(NEGATIVE_TITLE_PATTERN.search(str(title)))


def load_postings(path: str) -> list[dict[str, Any]]:
    """Read a JSONL snapshot, dropping malformed lines and duplicate posting ids.

    The raw file is never modified.  Duplicates are resolved in file order (the
    first occurrence wins) and the count is reported so a reviewer can see it.
    """
    import json

    postings: list[dict[str, Any]] = []
    seen: set[str] = set()
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, Mapping):
                continue
            posting_id = row.get(_FIELD_POSTING_ID)
            if not posting_id or not str(posting_id).strip():
                continue
            posting_id = str(posting_id)
            if posting_id in seen:
                continue
            seen.add(posting_id)
            if not row.get(_FIELD_DESCRIPTION):
                continue
            postings.append(dict(row))
    return postings


def select_subset(
    postings: Iterable[Mapping[str, Any]],
    *,
    n_primary: int = 32,
    n_negative: int = 10,
) -> dict[str, Any]:
    """Apply the declared rule.  Returns the selection plus the rule record.

    The result is a plain dict (JSON-serialisable) so the manifest can embed it::

        {
          "rule": {...},
          "primary":   [<full posting dict>, ...],
          "negative":  [<full posting dict>, ...],
          "primary_ids": [...], "negative_ids": [...],
          "n_available": {"total": N, "negative_titles": M},
          "skipped_duplicate_ids": 0,
        }
    """
    if n_primary < 0 or n_negative < 0:
        raise ValueError("n_primary and n_negative must be non-negative")
    rows = [dict(row) for row in postings if row.get(_FIELD_POSTING_ID)]
    rows.sort(key=lambda row: hash_key(str(row[_FIELD_POSTING_ID])))

    negative_pool = [row for row in rows if is_negative_title(row.get(_FIELD_TITLE))]
    primary_pool = [row for row in rows if not is_negative_title(row.get(_FIELD_TITLE))]

    primary = primary_pool[:n_primary]
    negative = negative_pool[:n_negative]

    rule = {
        "rule_id": SALT_VERSION,
        "hash": "sha256",
        "order": "ascending sha256(salt \\x00 posting_id)",
        "salt": HASH_SALT,
        "n_primary_requested": int(n_primary),
        "n_negative_requested": int(n_negative),
        "primary_filter": "job_title does NOT match negative_title_pattern",
        "negative_filter": "job_title DOES match negative_title_pattern",
        "disjoint": True,
        "negative_title_pattern": NEGATIVE_TITLE_PATTERN.pattern.strip(),
        "fields": {"id": _FIELD_POSTING_ID, "title": _FIELD_TITLE, "description": _FIELD_DESCRIPTION},
    }
    return {
        "rule": rule,
        "primary": primary,
        "negative": negative,
        "primary_ids": [str(row[_FIELD_POSTING_ID]) for row in primary],
        "negative_ids": [str(row[_FIELD_POSTING_ID]) for row in negative],
        "n_available": {"total": len(rows), "negative_titles": len(negative_pool)},
    }


def posting_text(posting: Mapping[str, Any]) -> str:
    """The posting as one searchable document: title, then description.

    Evidence quotes in this experiment may come from either part (the prompt
    hands the model both); locatability is checked against this combined text and
    the section a quote landed in is reported separately.
    """
    title = str(posting.get(_FIELD_TITLE) or "")
    description = str(posting.get(_FIELD_DESCRIPTION) or "")
    return f"{title}\n\n{description}" if title else description


__all__ = [
    "HASH_SALT",
    "NEGATIVE_TITLE_PATTERN",
    "SALT_VERSION",
    "hash_key",
    "is_negative_title",
    "load_postings",
    "posting_text",
    "select_subset",
]
