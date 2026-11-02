"""Add the seasonality claims (cycle 41) to papers/CLAIMS.json and build_claims.py."""
from __future__ import annotations

import json
from pathlib import Path

CLAIMS = Path("papers/CLAIMS.json")
BUILD = Path("papers/build_claims.py")

EXTRA = [
    ("CC1", "January month factor", "0.891", "experiments/b074/seasonality.json", '"0": 0.891'),
    ("CC2", "annual month-factor spread", "1.255", "experiments/b074/seasonality.json",
     '"spread_max_over_min": 1.255'),
    ("CC3", "month-of-year permutation p-value", "0.0005", "experiments/b074/seasonality.json",
     '"p_value": 0.0005'),
    ("CC4", "quarter-boundary factor", "1.058", "experiments/b074/seasonality.json",
     '"quarter_start_vs_interior": 1.058'),
    ("CC5", "detector alert rate on raw counts", "0.0090", "experiments/b074/seasonality.json",
     '"alert_rate": 0.009017223910840932'),
    ("CC6", "cell-months changed by seasonal adjustment", "9 of 39,151", "research/DECISIONS.md",
     "9 of 39,151"),
]


def main() -> int:
    payload = json.loads(CLAIMS.read_text(encoding="utf-8"))
    by_id = {claim["id"]: claim for claim in payload["claims"]}
    for claim_id, statement, value, source, needle in EXTRA:
        by_id[claim_id] = {"id": claim_id, "statement": statement, "value": value,
                           "source": source, "source_needle": needle}
    payload["claims"] = [by_id[key] for key in sorted(by_id)]
    CLAIMS.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8", newline="\n")

    build_text = BUILD.read_text(encoding="utf-8")
    if '"CC1"' not in build_text:
        block = "\n".join(
            f'    ("{claim_id}", "{statement}", "{value}", "{source}", "{needle}"),'
            for claim_id, statement, value, source, needle in EXTRA)
        anchor = [line for line in build_text.splitlines() if '"AA5"' in line][0]
        build_text = build_text.replace(
            anchor, anchor + "\n    # ---- seasonality (cycle 41)\n" + block, 1)
        BUILD.write_text(build_text, encoding="utf-8", newline="\n")
    print(f"claims now {len(payload['claims'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
