"""Extract FDA establishment identifiers for the audit.

Why this exists
---------------
SCIENCE-002 attributes a 510(k) to a registrant through the *applicant name* (with
an owner/operator hop for subsidiaries). That can only see firms whose name it can
match. The 510(k) record also carries the establishment identifiers of the filing
(\`openfda.registration_number\` and \`openfda.fei_number\`), and the registration file
maps those to an owner/operator number. That is a second, number-based channel:
510(k) -> establishment -> owner number -> owner firm -> SEC registrant.

This module only extracts the raw link tables. Interpretation lives in
entity_numbers.py, which must decide on its own what the numbers can and cannot
establish.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

from research.science_002 import fda

from . import common

LINKS_CSV = common.DATA_R / "510k_establishment_links.csv"
REG_CSV = common.DATA_R / "registration_owner_numbers.csv"

LINK_FIELDS = ("k_number", "decision_date", "applicant", "decision_code",
               "n_registration_numbers", "registration_numbers", "n_fei", "fei_numbers")
REG_FIELDS = ("registration_number", "fei_number", "registration_name",
              "owner_number", "owner_firm", "country")


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def extract_510k_links(target: Path = LINKS_CSV) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with_fei = 0
    with_reg = 0
    with open(target, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(LINK_FIELDS), lineterminator="\n")
        writer.writeheader()
        for record in fda.iter_json_records(common.zip510k()):
            rows += 1
            openfda = record.get("openfda") or {}
            regs = _as_list(openfda.get("registration_number"))
            feis = _as_list(openfda.get("fei_number"))
            if regs:
                with_reg += 1
            if feis:
                with_fei += 1
            writer.writerow({
                "k_number": (record.get("k_number") or "").strip(),
                "decision_date": (record.get("decision_date") or "").strip(),
                "applicant": (record.get("applicant") or "").strip(),
                "decision_code": (record.get("decision_code") or "").strip(),
                "n_registration_numbers": len(regs),
                "registration_numbers": "|".join(regs),
                "n_fei": len(feis),
                "fei_numbers": "|".join(feis),
            })
    return {"rows": rows, "with_registration_numbers": with_reg,
            "with_fei": with_fei, "path": str(target),
            "sha256": common.sha256_file(target)}


def extract_registration_owners(target: Path = REG_CSV) -> dict[str, Any]:
    """registration_number -> owner/operator, deduplicated across product rows."""
    seen: dict[str, dict[str, str]] = {}
    conflicts: dict[str, set[str]] = defaultdict(set)
    records = 0
    for part in common.zip_registration_parts():
        for record in fda.iter_json_records(part):
            records += 1
            registration = record.get("registration") or {}
            number = str(registration.get("registration_number") or "").strip()
            if not number:
                continue
            owner = registration.get("owner_operator") or {}
            row = {
                "registration_number": number,
                "fei_number": str(registration.get("fei_number") or "").strip(),
                "registration_name": str(registration.get("name") or "").strip(),
                "owner_number": str(owner.get("owner_operator_number") or "").strip(),
                "owner_firm": str(owner.get("firm_name") or "").strip(),
                "country": str(registration.get("iso_country_code") or "").strip(),
            }
            previous = seen.get(number)
            if previous is None:
                seen[number] = row
            elif previous["owner_number"] != row["owner_number"]:
                conflicts[number].add(previous["owner_number"] + "->" + row["owner_number"])
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REG_FIELDS), lineterminator="\n")
        writer.writeheader()
        for number in sorted(seen):
            writer.writerow(seen[number])
    return {"registration_records": records, "distinct_registrations": len(seen),
            "owner_conflicts": len(conflicts),
            "conflict_examples": {k: sorted(v)[:3] for k, v in list(conflicts.items())[:10]},
            "path": str(target), "sha256": common.sha256_file(target)}


def main() -> int:
    import json
    out = {"links": extract_510k_links(), "registrations": extract_registration_owners()}
    print(json.dumps(out, indent=1))
    common.write_json(common.ARTIFACTS_R / "establishment_extract.json", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
