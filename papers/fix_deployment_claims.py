"""Fix the deployment-resolution claims: the documents use a Unicode minus sign (U+2212)."""
from __future__ import annotations

import json
from pathlib import Path

MINUS = "\u2212"          # −
CLAIMS = Path("papers/CLAIMS.json")
BUILD = Path("papers/build_claims.py")

EXTRA = [
    ("U1", "quarterly deployment sensitivity of the z-score", "0.147",
     "research/DECISIONS.md", "0.147"),
    ("U2", "quarterly deployment z-score CI lower bound", "0.112",
     "research/DECISIONS.md", "0.112"),
    ("U3", "quarterly deployment z-score CI upper bound", "0.182",
     "research/DECISIONS.md", "0.182"),
    ("U4", "Kendall tau between quarterly and monthly rankings", f"{MINUS}1.0",
     "research/DECISIONS.md", f"{MINUS}1.0"),
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
    if '"U1"' not in text:
        block = "\n".join(
            f'    ("{claim_id}", "{statement}", "{value}", "{source}", "{needle}"),'
            for claim_id, statement, value, source, needle in EXTRA)
        marker = '    ("S6", "post-hoc discovery balanced accuracy", "0.608", "research/DECISIONS.md", "0.608"),'
        if marker not in text:
            print("anchor missing in build_claims.py")
            return 1
        text = text.replace(marker, marker + "\n    # ---- deployment resolution (cycle 21)\n" + block, 1)
        BUILD.write_text(text, encoding="utf-8", newline="\n")
        print("build_claims.py updated")
    print(f"claims: {len(payload['claims'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
