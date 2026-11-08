#!/usr/bin/env python3
"""Self-test for the RAEA entity-attribution module.

Run:  python experiments/phoenix/innovation/test_raea.py
Exit code 0 = all pass. No database access; synthetic registry only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import raea  # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"PASS  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILS.append(name)


REGISTRY = [
    {"key": "medtronic", "name_en": "Medtronic",
     "aliases": ["MEDTRONIC", "MEDTRONIC MINIMED", "COVIDIEN"]},
    {"key": "abbott", "name_en": "Abbott", "aliases": ["ABBOTT LABORATORIES"]},
    {"key": "acme_a", "name_en": "Acme A", "aliases": ["ACME NEURO"]},
    {"key": "acme_b", "name_en": "Acme B", "aliases": ["ACME ORTHO"]},
]


def main() -> int:
    idx = raea.AliasIndex.build(REGISTRY)

    # --- normalisation -----------------------------------------------------
    check("normalize: punctuation removed",
          raea.normalize_name("  Medtronic, Inc.  ") == "MEDTRONIC INC")
    check("normalize: empty/None safe",
          raea.normalize_name(None) == "" and raea.normalize_name("") == "")
    check("strip: legal suffix removed",
          raea.strip_qualifiers("MEDTRONIC INC") == "MEDTRONIC")
    check("strip: suffix + country removed",
          raea.strip_qualifiers("ABBOTT LABORATORIES USA") == "ABBOTT LABORATORIES")
    check("strip: repeated suffixes removed",
          raea.strip_qualifiers("FOO CORP INC LLC") == "FOO")

    # --- R1 exact ----------------------------------------------------------
    key, rule, _ = raea.attribute("Medtronic", idx)
    check("R1: exact alias", key == "medtronic" and rule == "R1_exact", f"{key}/{rule}")

    # --- R2 suffix ---------------------------------------------------------
    key, rule, _ = raea.attribute("Abbott Laboratories, Inc.", idx)
    check("R2: stripped suffix match", key == "abbott" and rule == "R2_suffix", f"{key}/{rule}")

    # --- R3 family ---------------------------------------------------------
    key, rule, _ = raea.attribute("Medtronic Minimed Puerto Rico", idx)
    check("R3: distinctive family token",
          key == "medtronic" and rule == "R3_family", f"{key}/{rule}")

    # --- R3 must refuse an ambiguous family token --------------------------
    # "ACME" is the leading token of two different companies, so it is not
    # distinctive and must not be used to attribute anything by itself.
    key, rule, _ = raea.attribute("Acme Holdings Ltd", idx)
    check("R3: ambiguous token refuses to guess",
          key is None and rule == "unmatched", f"{key}/{rule}")

    # --- precision guard ---------------------------------------------------
    key, rule, detail = raea.attribute("Boehringer Mannheim Corp", idx)
    check("guard: conflict token abstains",
          key is None and rule == "abstain_conflict", f"{key}/{rule}")

    # A guard phrase must NOT block an exact registered alias (registry wins).
    reg2 = REGISTRY + [{"key": "x", "name_en": "Gynecare", "aliases": ["GYNECARE"]}]
    idx2 = raea.AliasIndex.build(reg2)
    key, rule, _ = raea.attribute("Gynecare", idx2)
    check("guard: exact match beats conflict list",
          key == "x" and rule == "R1_exact", f"{key}/{rule}")

    # A bare "LABORATORIES" token must not be treated as a conflict; only the
    # BOEHRINGER LABORATORIES phrase is. (Regression test for a real bug.)
    key, rule, _ = raea.attribute("Abbott Laboratories", idx)
    check("guard: 'LABORATORIES' alone is not a conflict",
          key is None or rule != "abstain_conflict", f"{key}/{rule}")
    key, rule, _ = raea.attribute("Boehringer Laboratories", idx)
    check("guard: BOEHRINGER LABORATORIES phrase abstains",
          key is None and rule == "abstain_conflict", f"{key}/{rule}")

    # --- unmatched paths ---------------------------------------------------
    key, rule, _ = raea.attribute("Totally Unrelated Device Company", idx)
    check("unmatched: returns None", key is None and rule == "unmatched", f"{key}/{rule}")

    print()
    if FAILS:
        print(f"RESULT: FAIL ({len(FAILS)} failures)")
        return 1
    print("RESULT: PASS (all checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
