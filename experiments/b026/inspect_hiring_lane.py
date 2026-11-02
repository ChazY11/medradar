"""Inspect the hiring lane's monthly series density (feasibility for second-domain validation)."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    payload = json.loads(Path("experiments/b030/hiring_panel_v2.json").read_text(encoding="utf-8"))
    companies = payload["companies"]
    print(f"{'company':22s} {'postings':>8s} {'months':>6s} {'per month':>9s}")
    usable = 0
    for key, block in companies.items():
        postings = block.get("distinct_postings") or 0
        if not postings:
            continue
        months = block.get("months") or 0
        per_month = postings / months if months else 0.0
        print(f"{key:22s} {postings:8d} {months:6d} {per_month:9.1f}")
        if months >= 24 and per_month >= 0.15:
            usable += 1
    print(f"\ncompanies meeting the same eligibility floors (>=24 months, >=0.15/month): {usable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
