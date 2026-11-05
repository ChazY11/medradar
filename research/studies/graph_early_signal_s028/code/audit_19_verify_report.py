"""S-028 audit 19: verify that every number printed in the .md report also exists in
artifacts/entity_time_audit.json (the "do not hand-type numbers" rule).

Method: flatten the JSON into
  (a) a set of numeric values (ints/floats, with rounding buckets),
  (b) a set of digit-runs found inside JSON strings,
then scan the markdown for numeric tokens (dates/ISO stamps masked out) and require
each to match one of them within its own printed precision.
"""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal

from audit_common import STUDY, now_iso, dump

JSON_PATH = STUDY + r"\artifacts\entity_time_audit.json"
MD_PATH = STUDY + r"\RELATION_AND_TIME_EVIDENCE_AUDIT.md"

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}(?:T[\d:.]+(?:Z|[+-]\d{2}:\d{2})?)?")
NUM_RE = re.compile(r"(?<![\w./-])(\d[\d,]*(?:\.\d+)?)(%?)")


def flatten(obj, nums: set, digit_runs: set):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        nums.add(Decimal(str(obj)))
        return
    if isinstance(obj, str):
        for run in re.findall(r"\d+", obj):
            digit_runs.add(run)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(k, nums, digit_runs)
            flatten(v, nums, digit_runs)
        return
    if isinstance(obj, (list, tuple)):
        for v in obj:
            flatten(v, nums, digit_runs)


def matches(tok: Decimal, nums: set, digit_runs: set, raw: str) -> bool:
    digits = raw.replace(",", "")
    dec_places = len(digits.split(".")[1]) if "." in digits else 0
    tol = Decimal(1).scaleb(-dec_places) / 2 if dec_places else Decimal(0)
    if dec_places == 0:
        if digits in digit_runs:
            return True
    for n in nums:
        if abs(n - tok) <= tol + Decimal("1e-9"):
            return True
    # also accept rounded representations of a stored value (e.g. 44.11 from 44.1077)
    if dec_places:
        q = Decimal(1).scaleb(-dec_places)
        for n in nums:
            if abs(n.quantize(q) - tok) <= Decimal("1e-9"):
                return True
    return False


def main():
    doc = json.load(open(JSON_PATH, encoding="utf-8"))
    nums, digit_runs = set(), set()
    flatten(doc, nums, digit_runs)

    md = open(MD_PATH, encoding="utf-8").read()
    # strip only the structural part of headings ("## 5.2 R2 ..." -> "R2 ...") so that
    # data numbers sitting inside a heading are still verified.
    lines = []
    for line in md.splitlines():
        s = line.lstrip()
        if s.startswith("#"):
            s = re.sub(r"^#+\s*", "", s)
            s = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", s)
        lines.append(s)
    body = "\n".join(lines)
    body = re.sub(r"\]\([^)]*\)", "](", body)          # markdown link targets
    body = re.sub(r"https?://\S+", "URL", body)
    masked = DATE_RE.sub(" <DATE> ", body)

    tokens = []
    for m in NUM_RE.finditer(masked):
        raw, pctsign = m.group(1), m.group(2)
        start = max(0, m.start() - 28)
        ctx = masked[start:m.end() + 12].replace("\n", " ")
        tokens.append((raw, pctsign, ctx))

    unmatched = []
    for raw, pctsign, ctx in tokens:
        try:
            tok = Decimal(raw.replace(",", ""))
        except Exception:  # noqa: BLE001
            unmatched.append((raw, ctx, "unparsable"))
            continue
        if not matches(tok, nums, digit_runs, raw):
            unmatched.append((raw, ctx, "not in json"))

    res = {"generated_at": now_iso(), "md_path": MD_PATH, "json_path": JSON_PATH,
           "numeric_tokens_in_md": len(tokens), "unmatched": len(unmatched),
           "unmatched_examples": unmatched[:40],
           "numbers_in_json": len(nums), "digit_runs_in_json_strings": len(digit_runs)}
    print(f"numeric tokens in report : {len(tokens)}")
    print(f"distinct numeric values in json: {len(nums)}  (plus {len(digit_runs)} digit-runs inside strings)")
    print(f"unmatched: {len(unmatched)}")
    for raw, ctx, why in unmatched[:40]:
        print(f"  !! {raw:>12s}  [{why}]  ...{ctx}...")
    dump("19_report_verification", res)
    return 0 if not unmatched else 1


if __name__ == "__main__":
    sys.exit(main())
