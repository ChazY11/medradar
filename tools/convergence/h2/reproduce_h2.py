#!/usr/bin/env python3
"""Reproduce the frozen EXP-H2 artifact with the current code, offline.

Runs the local, algorithm-identical copy of
``research/horizon/experiments/regulatory/exp_h2_identity.py`` against the two
frozen JSONL inputs and compares the result with the committed
``EXP_H2_SUMMARY.json``.

No network.  No writes.  Stdlib only (plus the local copy of the pipeline).

Usage
-----
    python tools/convergence/h2/reproduce_h2.py
    python tools/convergence/h2/reproduce_h2.py --json

Exit code 0 only when the recomputed distribution equals the frozen summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)

import exp_h2_identity_local as pipe  # noqa: E402

FROZEN_DIR = os.path.join(REPO_ROOT, "research", "horizon", "experiments", "regulatory")
FROZEN_SUMMARY = os.path.join(FROZEN_DIR, "EXP_H2_SUMMARY.json")
FROZEN_PAIRS = os.path.join(FROZEN_DIR, "EXP_H2_PAIRS.jsonl")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    fda, md = pipe.load()
    primary = pipe.run_pass(fda, md, "strict")
    primary.pop("_pairs", None)
    lenient = pipe.run_pass(fda, md, "lenient")
    lenient.pop("_pairs", None)

    with open(FROZEN_SUMMARY, "r", encoding="utf-8") as fh:
        frozen = json.load(fh)

    recomputed = {
        "fda_records": len(fda),
        "canada_records": len(md),
        "pairs_total": primary["pairs_total"],
        "pairs_candidate": primary["pairs_candidate"],
        "pairs_hard_negative": primary["pairs_hard_negative"],
        "verdicts": primary["verdicts"],
        "by_construction_rule": primary["by_construction_rule"],
        "hard_negative_rules_attempted": primary["hard_negative_rules_attempted"],
        "lenient_pairs_total": lenient["pairs_total"],
        "lenient_verdicts": lenient["verdicts"],
    }

    checks = []

    def check(name, actual, expected):
        checks.append({"name": name, "actual": actual, "expected": expected,
                       "ok": actual == expected})

    check("generated_from.fda_records", recomputed["fda_records"],
          frozen["generated_from"]["fda_records"])
    check("generated_from.canada_records", recomputed["canada_records"],
          frozen["generated_from"]["canada_records"])
    for key in ("pairs_total", "pairs_candidate", "pairs_hard_negative"):
        check(f"primary.{key}", recomputed[key], frozen["primary"][key])
    # summary stores only the non-zero verdict buckets; normalise both sides
    check("primary.verdicts", {k: recomputed["verdicts"].get(k, 0)
                               for k in ("CONFIRMED", "REJECTED", "UNKNOWN")},
          {k: frozen["primary"]["verdicts"].get(k, 0)
           for k in ("CONFIRMED", "REJECTED", "UNKNOWN")})
    check("primary.by_construction_rule", recomputed["by_construction_rule"],
          frozen["primary"]["by_construction_rule"])
    check("primary.hard_negative_rules_attempted",
          {k: recomputed["hard_negative_rules_attempted"].get(k, 0)
           for k in frozen["primary"]["hard_negative_rules_attempted"]},
          frozen["primary"]["hard_negative_rules_attempted"])
    check("sensitivity_lenient.pairs_total", recomputed["lenient_pairs_total"],
          frozen["sensitivity_lenient_model_tokens"]["pairs_total"])
    check("sensitivity_lenient.verdicts",
          {k: recomputed["lenient_verdicts"].get(k, 0)
           for k in ("CONFIRMED", "REJECTED", "UNKNOWN")},
          {k: frozen["sensitivity_lenient_model_tokens"]["verdicts"].get(k, 0)
           for k in ("CONFIRMED", "REJECTED", "UNKNOWN")})

    frozen_pairs_sha = sha256(FROZEN_PAIRS)
    generated_pairs = os.path.join(REPO_ROOT, "research", "convergence", "h2", "out",
                                   "recomputed_pairs.jsonl")
    generated_sha = sha256(generated_pairs) if os.path.exists(generated_pairs) else None
    pairs_match = generated_sha == frozen_pairs_sha if generated_sha else None

    failures = [c for c in checks if not c["ok"]]
    result = {
        "status": "reproduced" if not failures else "mismatch",
        "exit_code": 0 if not failures else 1,
        "recomputed": recomputed,
        "checks": checks,
        "mismatches": failures,
        "pairs_file": {
            "frozen_sha256": frozen_pairs_sha,
            "recomputed_sha256": generated_sha,
            "byte_identical": pairs_match,
        },
    }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("EXP-H2 reproduction: current code vs frozen artifact")
        print(f"  inputs: accessgudid={recomputed['fda_records']} records, "
              f"canada_mdall={recomputed['canada_records']} records")
        print(f"  pairs_total={recomputed['pairs_total']} "
              f"(candidate={recomputed['pairs_candidate']}, "
              f"hard_negative={recomputed['pairs_hard_negative']})")
        print(f"  verdicts={recomputed['verdicts']}")
        print(f"  by_construction_rule={recomputed['by_construction_rule']}")
        print(f"  frozen pairs sha256={frozen_pairs_sha}")
        print(f"  local pairs sha256="
              f"{generated_sha if generated_sha else '(not generated; run exp_h2_identity_local.py)'}")
        print(f"  checks: {len(checks) - len(failures)}/{len(checks)} passed")
        for failure in failures:
            print(f"  MISMATCH {failure['name']}: expected {failure['expected']!r}, "
                  f"got {failure['actual']!r}")
        print("RESULT:", result["status"].upper())
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
