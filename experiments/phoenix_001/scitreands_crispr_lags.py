#!/usr/bin/env python3
"""Recompute SciTrends' small CRISPR patent/publication lag correlations."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_repo", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.source_repo.resolve()
    frame = pd.read_csv(repo / "S2-crispr_patents_papers.csv", parse_dates=["Year"]).set_index("Year")
    frame = frame.tail(19)
    diff = frame.diff().tail(19)
    papers, patents = frame["crispr"], frame["patents filed  Count"]
    payload = {
        "status": "completed_descriptive_reproduction",
        "source_repository": "https://github.com/ddofer/Trends",
        "source_notebook": "crispr_patent_paper_Corr.ipynb",
        "source_commit": subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
        "rows": int(len(frame)),
        "year_min": int(frame.index.year.min()), "year_max": int(frame.index.year.max()),
        "same_year": float(patents.corr(papers)),
        "future_patents_shift_minus_1": float(patents.shift(-1).corr(papers)),
        "diff_same_year": float(diff["patents filed  Count"].corr(diff["crispr"])),
        "diff_papers_shift_1_vs_patents": float(diff["crispr"].shift(1).corr(diff["patents filed  Count"])),
        "diff_patents_shift_1_vs_papers": float(diff["patents filed  Count"].shift(1).corr(diff["crispr"])),
        "level_cross_correlations": [
            {"shift": int(i), "correlation": float(papers.corr(patents.shift(i)))}
            for i in range(-6, 6)
        ],
        "evidence_category": 2,
        "warning": "N=19 annual observations; lag correlations are descriptive retrospective associations, not a trained or prospectively validated patent-leading indicator.",
    }
    output = args.output.resolve()
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
