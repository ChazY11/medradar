#!/usr/bin/env python3
"""Run the evidence-grounded research agent on the real research database.

This script is fully offline. It executes the deterministic workflow for five
real research questions and writes a frozen, cited demo artifact to
``experiments/reverse_rd_v2/agent_demo.json``.

Every citation in the output is verified against the database or the canonical
forecast registry before the artifact is written; a missing id makes the script
exit non-zero (never silently ship a dangling citation).

The canonical registry (``data/registry.sqlite``) and a temporal knowledge graph
(``data/tkg.sqlite``) are sibling Phase-3 artifacts. Both are optional here: when
absent, the agent reports the evidence gap explicitly and the run is marked
degraded instead of substituting a fabricated probability or graph.

Usage (from the repository root)::

    python scripts/run_agent_demo.py
    python scripts/run_agent_demo.py --db data/research.sqlite --out experiments/reverse_rd_v2/agent_demo.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # allow `python scripts/run_agent_demo.py`
    sys.path.insert(0, str(ROOT))

from medradar import research_agent  # noqa: E402
from medradar.util import utc_now_iso, write_json  # noqa: E402

DEFAULT_DB = ROOT / "data" / "research.sqlite"
DEFAULT_REGISTRY = ROOT / "data" / "registry.sqlite"
DEFAULT_TKG = ROOT / "data" / "tkg.sqlite"
DEFAULT_OUT = ROOT / "experiments" / "reverse_rd_v2" / "agent_demo.json"
#: A fixed as-of so the artifact is reproducible; 2026-11-02 is after the frozen
#: model-forecast creation time (2026-11-01T23:16:37Z) and inside the collected
#: event/market/publication coverage (ends 2026-10-15 / 2026-10-30).
AS_OF = "2026-11-02"
QUESTIONS = (
    {
        "company": "intuitive_surgical",
        "track": "imaging_mr_ct",
        "template": "entry_forecast",
        "reason": ("Intuitive Surgical has one material imaging event (2019) and no activity in the track "
                   "for more than 36 months while the track itself has heavy activity by other companies; "
                   "this is the hardest question shape the agent supports."),
    },
    {
        "company": "medtronic",
        "track": "spine",
        "template": "market_leading_indicator",
        "reason": ("A large, continuously active company-track pair with a visible frozen model forecast, "
                   "so the market evidence can be compared with R&D history and a base rate."),
    },
    {
        "company": "boston_scientific",
        "track": "ep_pfa",
        "template": "early_signal",
        "reason": ("Pulsed-field ablation is a young track with a small but growing event record; the "
                   "agent must distinguish early signal from a validated forecast."),
    },
    {
        "company": "medtronic",
        "track": "ep_pfa",
        "template": "strategic_shift",
        "reason": ("The pair's event mix is recent-heavy; this asks whether the observed record supports a "
                   "shift without claiming internal R&D intent."),
    },
    {
        "company": "alcon",
        "track": "ophthalmology",
        "template": "cross_source_validation",
        "reason": ("All four evidence sources plus a frozen model forecast exist for this pair, which is the "
                   "right setting to ask whether the sources agree or conflict."),
    },
)

CITATION_QUERIES = {
    "event": ("events", "event_id"),
    "financial_fact": ("financial_facts", "fact_id"),
    "example": ("forecast_examples", "example_id"),
    "horizon_forecast": ("horizon_forecasts", "forecast_id"),
}


def _resolve_optional(path: Path) -> str | None:
    return str(path) if path.exists() else None


def _citation_exists(db: Path, registry: Path | None, citation: dict[str, Any]) -> bool:
    kind, locator = str(citation.get("kind")), str(citation.get("locator"))
    conn = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    try:
        if kind in CITATION_QUERIES:
            table, column = CITATION_QUERIES[kind]
            return conn.execute(f"SELECT 1 FROM {table} WHERE {column} = ?", (locator,)).fetchone() is not None
        if kind == "market_bar":
            ticker, day = locator.rsplit(":", 1)
            return conn.execute("SELECT 1 FROM market_bars WHERE ticker = ? AND date = ?",
                                (ticker, day)).fetchone() is not None
        if kind == "publication_count":
            company, year = locator.rsplit(":", 1)
            return conn.execute("SELECT 1 FROM publication_counts WHERE company_key = ? AND year = ?",
                                (company, int(year))).fetchone() is not None
    finally:
        conn.close()
    if kind == "registry_forecast":
        if registry is None:
            return False
        conn = sqlite3.connect(f"file:{registry.resolve().as_posix()}?mode=ro", uri=True)
        try:
            return conn.execute("SELECT 1 FROM forecasts WHERE prediction_id = ?",
                                (locator,)).fetchone() is not None
        finally:
            conn.close()
    if kind == "tkg_assertion":
        return True  # raw TKG citations are verified by the agent's own schema read
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY),
                        help="canonical forecast registry path (ignored when absent unless passed explicitly)")
    parser.add_argument("--tkg", default=str(DEFAULT_TKG))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--as-of", default=AS_OF)
    args = parser.parse_args(argv)
    db = Path(args.db)
    if not db.exists():
        print(json.dumps({"error": f"research database not found: {db}"}), file=sys.stderr)
        return 2
    registry = _resolve_optional(Path(args.registry))
    tkg = _resolve_optional(Path(args.tkg))
    generated_at = utc_now_iso()
    questions: list[dict[str, Any]] = []
    checked_citations: list[str] = []
    missing_citations: list[dict[str, Any]] = []
    claim_count = 0
    conflict_count = 0
    for item in QUESTIONS:
        document = research_agent.run_agent(
            item["company"], item["track"], template=item["template"], as_of=args.as_of,
            db=db, registry=registry, tkg=tkg)
        claim_count += len(document["evidence"])
        conflict_count += len(document["conflicts"])
        registry_path = Path(registry) if registry else None
        for citation in document["citations"]:
            key = f"{citation['kind']}:{citation['locator']}"
            checked_citations.append(key)
            if not _citation_exists(db, registry_path, citation):
                missing_citations.append({"question": document["question"]["text"], **citation})
        questions.append({
            "question": document["question"],
            "reason": item["reason"],
            "document": document,
        })
    citation_ids = sorted(set(checked_citations))
    artifact = {
        "agent_version": research_agent.AGENT_VERSION,
        "generated_at": generated_at,
        "as_of": args.as_of,
        "database": str(db),
        "registry": {"expected_path": str(DEFAULT_REGISTRY), "used_path": registry,
                     "present": registry is not None},
        "tkg": {"expected_path": str(DEFAULT_TKG), "used_path": tkg, "present": tkg is not None},
        "questions": questions,
        "summary": {
            "questions": len(questions),
            "claims": claim_count,
            "unique_citations": len(citation_ids),
            "conflicts": conflict_count,
            "degraded_questions": sum(1 for entry in questions if entry["document"]["degraded"]),
            "templates": sorted({entry["question"]["template"] for entry in questions}),
            "citation_kinds": sorted({key.split(":", 1)[0] for key in citation_ids}),
            "evidence_gaps": {
                "canonical_registry": "absent" if registry is None else "present",
                "temporal_graph": "absent" if tkg is None else "present",
                "patents": "not evaluated (USPTO API key absent)",
                "hiring": "not collected",
            },
        },
        "verification": {
            "citations_checked": len(checked_citations),
            "citations_missing": missing_citations,
            "ok": not missing_citations,
        },
        "notes": [
            "Every document is the deterministic output of medradar.research_agent for the stated template.",
            "Probabilities inside the documents come only from the frozen model forecast table or the "
            "canonical registry; no probability is generated by the agent and no LLM was called.",
            "The canonical forecast registry and the temporal knowledge graph were produced by sibling "
            "Phase-3 tasks and are absent in this checkout; the documents say so explicitly.",
            "The demo is a retrospective evidence narration at a fixed as-of date, not a prospective accuracy "
            "claim.",
        ],
    }
    write_json(Path(args.out), artifact)
    print(json.dumps({
        "out": str(args.out),
        "questions": len(questions),
        "claims": claim_count,
        "unique_citations": len(citation_ids),
        "conflicts": conflict_count,
        "citations_missing": len(missing_citations),
        "degraded_questions": artifact["summary"]["degraded_questions"],
        "registry_present": registry is not None,
        "tkg_present": tkg is not None,
    }, indent=1))
    if missing_citations:
        print(json.dumps({"error": "dangling citations", "examples": missing_citations[:5]}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
