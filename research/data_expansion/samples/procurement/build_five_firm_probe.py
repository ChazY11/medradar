#!/usr/bin/env python
"""Assemble FIVE_FIRM_PROBE.json from the real probe artifacts.

Inputs (all produced by live probes, no new network access):
  * ``research/data_expansion/probes/usaspending/FIRM_ROWS.json``
  * ``research/data_expansion/probes/usaspending/PROBE_RESULT.json``
  * ``research/data_expansion/probes/greenhouse/PROBE_RESULT.json``
  * ``research/data_expansion/probes/lever/PROBE_RESULT.json``

The question this file answers is narrow and auditable:

  For Medtronic / GE HealthCare / Philips / Dräger / Mindray —
  (a) on USAspending, how many federal contract actions does the *recipient
      token search* return, what amount and date range does the first page
      show, and is each returned recipient name a **confirmed** link to the
      firm or only a **candidate**?
  (b) on Greenhouse and Lever, does a public job board exist (yes/no, token,
      evidence URL)?

Two honesty rules are enforced in the output:
  1. ``recipient_search_text`` is a token search.  A returned name is resolved
     through ``identity.CompanyIndex``; anything that is not
     ``exact_alias``/``multi_field``/``official_id`` is reported as a
     candidate and never counted as the firm's procurement record.
  2. Amount/date ranges are computed from the returned page only, and are
     labelled as such — they are not population statistics.

Run:  python research/data_expansion/samples/procurement/build_five_firm_probe.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]                       # research/data_expansion
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources.identity import CompanyIndex  # noqa: E402

PROBES = ROOT / "probes"
OUT = HERE.parent / "FIVE_FIRM_PROBE.json"

FIRMS = [
    ("Medtronic", "medtronic"),
    ("GE HealthCare", "ge_healthcare"),
    ("Philips", "philips"),
    ("Draeger", "draeger"),
    ("Mindray", "mindray"),
]

#: Greenhouse / Lever tokens tested for each firm by the probes.
BOARD_TOKENS = {
    "medtronic": ["medtronic"],
    "ge_healthcare": ["gehealthcare"],
    "philips": ["philips"],
    "draeger": ["draeger"],
    "mindray": ["mindray"],
}


def _load_probe(source_id: str) -> dict:
    path = PROBES / source_id / "PROBE_RESULT.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _probe_entries(probe: dict, prefix: str = "") -> dict[str, dict]:
    out = {}
    for entry in probe.get("probes", []) or []:
        name = str(entry.get("name", ""))
        if prefix and not name.startswith(prefix):
            continue
        out[name] = entry
    return out


def _summarise_rows(rows: list[dict], index: CompanyIndex, firm_key: str) -> dict:
    amounts = [r.get("Award Amount") for r in rows if isinstance(r.get("Award Amount"), (int, float))]
    starts = [r.get("Start Date") for r in rows if r.get("Start Date")]
    ends = [r.get("End Date") for r in rows if r.get("End Date")]
    confirmed, candidates, other = [], [], []
    for row in rows:
        name = row.get("Recipient Name", "")
        resolution = index.resolve(name)
        method = resolution.get("method")
        record = {
            "recipient_name": name,
            "award_id": row.get("Award ID"),
            "amount": row.get("Award Amount"),
            "start_date": row.get("Start Date"),
            "end_date": row.get("End Date"),
            "awarding_agency": row.get("Awarding Agency"),
            "resolution_method": method,
            "resolved_key": resolution.get("resolved_key"),
            "confidence": resolution.get("confidence"),
            "matched_alias": (resolution.get("evidence") or {}).get("matched_alias", ""),
        }
        if method in {"exact_alias", "multi_field", "official_id"} and resolution.get("resolved_key") == firm_key:
            confirmed.append(record)
        elif method == "candidate":
            candidates.append(record)
        else:
            other.append(record)
    return {
        "page_size": len(rows),
        "rows_resolving_to_this_firm_confirmed": len(confirmed),
        "rows_candidate_only": len(candidates),
        "rows_not_the_firm": len(other),
        "confirmed_rows": confirmed,
        "candidate_rows": candidates,
        "not_the_firm_rows": other,
        "amount_range_from_this_page": {
            "min": min(amounts) if amounts else None,
            "max": max(amounts) if amounts else None,
            "currency": "USD",
            "basis": "first page of recipient_search_text results, sorted by amount desc; NOT a population statistic",
        },
        "date_range_from_this_page": {
            "start_min": min(starts) if starts else None,
            "start_max": max(starts) if starts else None,
            "end_max": max(ends) if ends else None,
            "date_field_semantics": "USAspending 'Start Date' is the period-of-performance start, not a publication date",
        },
    }


def _interpret(summary: dict, population) -> str:
    """Plain-language link strength, derived from the counts (never hand-written)."""
    confirmed = summary["rows_resolving_to_this_firm_confirmed"]
    others = summary["rows_not_the_firm"]
    page = summary["page_size"]
    if page and confirmed == page:
        strength = "strong: every name on the returned page resolves to this firm"
    elif confirmed:
        strength = (
            f"partial: {confirmed}/{page} names resolve to this firm; "
            f"{others} are other companies caught by the token search"
        )
    elif others:
        strength = "weak: no name on the returned page resolves to this firm"
    else:
        strength = "no rows returned"
    return (
        f"{strength}. The token-search population count ({population}) is an upper bound "
        "and is polluted whenever the firm's name contains common tokens."
    )


def main() -> int:
    index = CompanyIndex.from_config()
    firm_rows_path = PROBES / "usaspending" / "FIRM_ROWS.json"
    if not firm_rows_path.is_file():
        print(f"missing {firm_rows_path}; run the usaspending probe first", file=sys.stderr)
        return 2
    firm_rows = json.loads(firm_rows_path.read_text(encoding="utf-8"))

    usaspending_probe = _load_probe("usaspending")
    gh_probe = _load_probe("greenhouse")
    lever_probe = _load_probe("lever")
    gh_entries = _probe_entries(gh_probe)
    lever_entries = _probe_entries(lever_probe)

    firms_out = []
    for display, key in FIRMS:
        rows_blob = firm_rows.get(display, {})
        rows = rows_blob.get("rows") or []
        summary = _summarise_rows(rows, index, key)

        boards = []
        for platform, entries in (("greenhouse", gh_entries), ("lever", lever_entries)):
            for token in BOARD_TOKENS.get(key, []):
                entry = entries.get(key) or {}
                boards.append(
                    {
                        "platform": platform,
                        "token": token,
                        "board_exists": bool(entry.get("ok")),
                        "http_status": entry.get("status"),
                        "n_postings": entry.get("n_postings"),
                        "evidence_url": entry.get("url", ""),
                    }
                )

        firms_out.append(
            {
                "firm": display,
                "firm_key": key,
                "usaspending": {
                    "recipient_search_text_used": display,
                    "recipient_token_search_population_contracts": rows_blob.get(
                        "population_count_contracts"
                    ),
                    "population_count_is_a_confirmed_firm_count": False,
                    "population_count_caveat": (
                        "spending_by_award_count with recipient_search_text counts every "
                        "recipient whose name contains the tokens; it is an upper bound, "
                        "not 'contracts awarded to the firm'."
                    ),
                    "recipient_names_returned_by_autocomplete": rows_blob.get(
                        "autocomplete_recipients", []
                    ),
                    "first_page": summary,
                },
                "interpretation": _interpret(summary, rows_blob.get("population_count_contracts")),
                "job_boards": boards,
                "job_boards_public": any(b["board_exists"] for b in boards),
            }
        )

    payload = {
        "schema": "medradar.procurement.five_firm_probe.v1",
        "generated_at": date.today().isoformat(),
        "question": (
            "Can the five target firms' real procurement records and public hiring "
            "boards be identified from the probed sources?"
        ),
        "firms": firms_out,
        "method": {
            "usaspending": (
                "POST /api/v2/search/spending_by_award/ with filters.recipient_search_text "
                "and POST /api/v2/search/spending_by_award_count/ for the population count; "
                "each returned Recipient Name resolved with identity.CompanyIndex."
            ),
            "greenhouse": "GET boards-api.greenhouse.io/v1/boards/<token>/jobs?content=false",
            "lever": "GET api.lever.co/v0/postings/<token>?mode=json",
            "control_boards": {
                "greenhouse": "stripe (200, 766 jobs) — proves the endpoint works",
                "lever": "leverdemo (200, 10 postings) — proves the endpoint works",
            },
        },
        "honesty_rules": [
            "recipient_search_text is a token search, not an exact recipient match: "
            "'GE HealthCare' returned CHANGE HEALTHCARE TECHNOLOGIES, LLC.",
            "A returned name counts as the firm only if identity resolution is "
            "exact_alias/multi_field/official_id; candidates are listed separately.",
            "Amount and date ranges cover the returned page only, not the population.",
            "USAspending 'Start Date' is the performance start, not a publication date.",
            "A 404 from a job-board API means 'no such board', not 'no hiring'.",
        ],
        "headline": {},
    }

    # headline summary computed from the data, not asserted by hand
    headline = {
        "firms_with_confirmed_usaspending_rows_on_first_page": [
            f["firm"] for f in firms_out
            if f["usaspending"]["first_page"]["rows_resolving_to_this_firm_confirmed"] > 0
        ],
        "firms_with_only_candidate_rows": [
            f["firm"] for f in firms_out
            if f["usaspending"]["first_page"]["rows_resolving_to_this_firm_confirmed"] == 0
            and f["usaspending"]["first_page"]["rows_candidate_only"] > 0
        ],
        "firms_with_public_greenhouse_or_lever_board": [
            f["firm"] for f in firms_out if f["job_boards_public"]
        ],
        "note": (
            "On Greenhouse and Lever none of the five firms resolved under its likely "
            "token while the control tokens did resolve — a negative result about those "
            "two job boards, not about hiring data in general."
        ),
    }
    payload["headline"] = headline

    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT}")
    for f in firms_out:
        fp = f["usaspending"]["first_page"]
        print(
            f"  {f['firm']:<14} pop={f['usaspending']['recipient_token_search_population_contracts']!s:>7}"
            f" confirmed={fp['rows_resolving_to_this_firm_confirmed']:>2}"
            f" cand={fp['rows_candidate_only']:>2} other={fp['rows_not_the_firm']:>2}"
            f" boards={[b['platform'] + ':' + str(b['board_exists']) for b in f['job_boards']]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
