"""Add the product-integration claims (cycle 22) and re-verify."""
from __future__ import annotations

import json
from pathlib import Path

CLAIMS = Path("papers/CLAIMS.json")
BUILD = Path("papers/build_claims.py")

EXTRA = [
    ("V1", "deployment false-alarm rate stated in profiles", "0.018",
     "research/DECISIONS.md", "**0.018**"),
    ("V2", "profile test count after the deployment block", "44",
     "research/RESULTS/cycle22_product_2026-11-03.md", "44 tests"),
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

    text = BUILD.read_text(encoding="utf-8")
    if '"V1"' not in text:
        block = "\n".join(
            f'    ("{claim_id}", "{statement}", "{value}", "{source}", "{needle}"),'
            for claim_id, statement, value, source, needle in EXTRA)
        marker = ('    ("U4", "Kendall tau between quarterly and monthly rankings", '
                  '"\\u22121.0", "research/DECISIONS.md", "\\u22121.0"),')
        if marker not in text:
            # tolerate the literal form
            marker = [line for line in text.splitlines() if '"U4"' in line][0]
        text = text.replace(marker, marker + "\n    # ---- product integration (cycle 22)\n" + block, 1)
        BUILD.write_text(text, encoding="utf-8", newline="\n")
        print("build_claims.py updated")
    print(f"claims: {len(payload['claims'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
