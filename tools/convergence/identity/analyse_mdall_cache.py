#!/usr/bin/env python
"""P0-B / task-2: analyse the frozen Health Canada MDALL active device-identifier table.

The frozen artefact is a single-line JSON array (no newlines) of 1,673,926 objects:

    [{"original_licence_no":109559,"device_id":1053507,
      "first_licence_dt":"2023-06-19","end_date":null,
      "device_identifier":"NHK 21 15-40"}, ...]

It is streamed with json.JSONDecoder.raw_decode so memory stays bounded; the
whole file is never materialised as one Python object.

The *ATLAS* GTIN class is not "raw string is 14 digits": ATLAS's
`is_gtin_like()` first applies `normalize_di()` = remove all whitespace and
hyphens (`_DI_SEP = r"[\\s\\-]"`), then requires exactly 14 digits. Both
definitions are reported so the 5,477 (bare) vs 5,512 (separator-normalised)
difference in ATLAS's own docs is reconciled here rather than glossed over.

Questions answered (all bound to the SHA-256 of the file, verified against the
digest recorded in research/convergence/identity/FROZEN_INPUTS.json):
  1. How many rows, and how many distinct device_identifier values?
  2. How many rows/values fall in the ATLAS GTIN class (bare and normalised)?
  3. How many of those pass the GS1 Mod-10 check digit?
  4. What are the other identifier classes (model/catalogue tokens)?
  5. The "one GTIN, many MDALL rows" pattern: rows per GTIN, licences per GTIN,
     device_id per GTIN, and normalisation collisions.
  6. Does ATLAS's scanned row count (1,673,926) equal the whole table?

Writes research/convergence/identity/MDALL_CACHE_ANALYSIS.json
Run:
    python tools/convergence/identity/analyse_mdall_cache.py
"""

from __future__ import annotations

import collections
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gtin import DI_SEP_RE, GTIN14_RE, gtin14_check_digit_ok, is_gtin_like, normalize_di  # noqa: E402

WT = Path(r"D:\DEPPSKK\worktrees\convergence-001")
CACHE = Path(r"D:\DEPPSKK\worktrees\atlas-001\research\atlas\cache\mdall_active_deviceidentifier.json")
FROZEN = WT / "research" / "convergence" / "identity" / "FROZEN_INPUTS.json"
OUT = WT / "research" / "convergence" / "identity" / "MDALL_CACHE_ANALYSIS.json"

_GTIN14 = GTIN14_RE
ATLAS_REPORT_CACHE_SHA256 = "55d2b64189a2b8b6d3d7431462930196aebe5503addeeb6a4a6f0d65f5c2973f"


def sha256_file(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def iter_json_array(path: Path, chunk: int = 1 << 20):
    """Yield each object of a top-level JSON array without loading the file."""
    dec = json.JSONDecoder()
    with path.open("r", encoding="utf-8") as f:
        buf = f.read(chunk)
        idx = 1  # skip '['
        while True:
            while idx < len(buf) and buf[idx] in " \t\r\n,":
                idx += 1
            if idx >= len(buf):
                more = f.read(chunk)
                if not more:
                    return
                buf = buf[idx:] + more
                idx = 0
                continue
            if buf[idx] == "]":
                return
            try:
                obj, end = dec.raw_decode(buf, idx)
            except json.JSONDecodeError:
                more = f.read(chunk)
                if not more:
                    raise
                buf = buf[idx:] + more
                idx = 0
                continue
            yield obj
            idx = end


def main() -> int:
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    recorded = next(b for b in frozen["required_inputs"] if b["role"] == "mdall_cache")
    digest = sha256_file(CACHE)
    if digest != recorded["sha256"]:
        raise SystemExit(f"MDALL cache digest changed: {digest} != {recorded['sha256']}")

    rows = 0
    missing = 0
    non_string = 0
    blank = 0
    raw_lengths = collections.Counter()
    bare_rows = 0
    bare_values: set[str] = set()
    # ATLAS class: separator-normalised
    atlas_rows = 0
    check_bad_rows = 0
    atlas_by_value: dict[str, dict] = {}
    gtin_licences: set = set()
    gtin_device_ids: set = set()
    raw_to_norm_collisions: dict[str, set[str]] = collections.defaultdict(set)
    classes_per_device: dict[object, set[str]] = collections.defaultdict(set)
    examples = {"gtin_ok": [], "gtin_bad_check": [], "numeric_other": [], "token": [],
                "separator_only": []}

    for obj in iter_json_array(CACHE):
        rows += 1
        raw = obj.get("device_identifier")
        if raw is None:
            missing += 1
            continue
        if not isinstance(raw, str):
            non_string += 1
            raw = str(raw)
        if not raw.strip():
            blank += 1
            continue
        norm = normalize_di(raw)
        if _GTIN14.match(raw):
            bare_rows += 1  # same predicate applied to the raw value
            bare_values.add(raw)
        if _GTIN14.match(norm):
            atlas_rows += 1
            raw_to_norm_collisions[norm].add(raw)
            gtin_licences.add(obj.get("original_licence_no"))
            gtin_device_ids.add(obj.get("device_id"))
            if raw != norm:
                if len(examples["separator_only"]) < 5:
                    examples["separator_only"].append({"raw": raw, "normalised": norm})
            ok = gtin14_check_digit_ok(norm)
            if not ok:
                check_bad_rows += 1
            site = atlas_by_value.get(norm)
            if site is None:
                site = {"rows": 0, "licences": set(), "device_ids": set(),
                        "check_ok": ok, "first_licence_dt": set(), "end_dates": set()}
                atlas_by_value[norm] = site
            site["rows"] += 1
            site["licences"].add(obj.get("original_licence_no"))
            site["device_ids"].add(obj.get("device_id"))
            site["first_licence_dt"].add(obj.get("first_licence_dt"))
            site["end_dates"].add(obj.get("end_date"))
            if ok and len(examples["gtin_ok"]) < 5:
                examples["gtin_ok"].append(norm)
            if not ok and len(examples["gtin_bad_check"]) < 5:
                examples["gtin_bad_check"].append(norm)
            cls = "gtin14"
        else:
            cls = "other"
            if norm.isdigit() and 8 <= len(norm) <= 17:
                if len(examples["numeric_other"]) < 5:
                    examples["numeric_other"].append(norm)
            elif len(examples["token"]) < 5:
                examples["token"].append(norm)
        raw_lengths[len(raw)] += 1
        did = obj.get("device_id")
        if did is not None:
            classes_per_device[did].add(cls)

    gtin_dist = collections.Counter(s["rows"] for s in atlas_by_value.values())
    multi_row = {v: s for v, s in atlas_by_value.items() if s["rows"] > 1}
    multi_licence = {v: s for v, s in atlas_by_value.items() if len(s["licences"]) > 1}
    multi_device = {v: s for v, s in atlas_by_value.items() if len(s["device_ids"]) > 1}
    norm_collisions = {v: raws for v, raws in raw_to_norm_collisions.items() if len(raws) > 1}
    check_ok_values = {v for v, s in atlas_by_value.items() if s["check_ok"]}
    check_bad_values = {v for v, s in atlas_by_value.items() if not s["check_ok"]}
    both_class_devices = [d for d, c in classes_per_device.items() if len(c) > 1]

    report = {
        "schema": "medradar.convergence.mdall_cache_analysis.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "tools/convergence/identity/analyse_mdall_cache.py",
        "network_used": False,
        "input": {
            "path": str(CACHE),
            "sha256": digest,
            "size_bytes": CACHE.stat().st_size,
            "format": "single-line JSON array of objects; keys original_licence_no, device_id, first_licence_dt, end_date, device_identifier",
            "sha256_matches_frozen_inputs": True,
            "sha256_matches_atlas_report_table_hash": digest == ATLAS_REPORT_CACHE_SHA256,
        },
        "totals": {
            "rows": rows,
            "distinct_device_identifier_values_raw": None,  # filled below
            "differs_from_atlas_scanned_until_limit": rows != 1673926,
        },
        "identifier_classes": {
            "atlas_gtin_class_definition": "normalize_di(value) removes whitespace/hyphen then requires exactly 14 digits (medradar/atlas/identity/normalize.py::is_gtin_like)",
            "atlas_gtin_class_rows": atlas_rows,
            "atlas_gtin_class_distinct_values": len(atlas_by_value),
            "atlas_gtin_class_share_of_rows": round(atlas_rows / rows, 8),
            "bare_14_digit_rows_without_normalisation": bare_rows,
            "bare_14_digit_distinct_values_without_normalisation": len(bare_values),
            "rows_that_needed_separator_normalisation": atlas_rows - bare_rows,
            "gtin14_check_digit_valid_rows": atlas_rows - check_bad_rows,
            "gtin14_check_digit_invalid_rows": check_bad_rows,
            "gtin14_check_digit_valid_distinct_values": len(check_ok_values),
            "gtin14_check_digit_invalid_distinct_values": len(check_bad_values),
            "gtin14_check_digit_invalid_examples": sorted(check_bad_values)[:20],
            "non_gtin_class_rows": rows - atlas_rows,
            "non_gtin_class_share_of_rows": round((rows - atlas_rows) / rows, 8),
            "first_examples": examples,
        },
        "one_gtin_many_rows": {
            "gtin_values_with_1_row": gtin_dist.get(1, 0),
            "gtin_values_with_2_rows": gtin_dist.get(2, 0),
            "gtin_values_with_3plus_rows": sum(n for k, n in gtin_dist.items() if k >= 3),
            "max_rows_per_single_gtin": max(gtin_dist) if gtin_dist else 0,
            "gtin_values_appearing_in_more_than_one_mdall_row": len(multi_row),
            "gtin_values_appearing_under_more_than_one_licence": len(multi_licence),
            "gtin_values_appearing_under_more_than_one_device_id": len(multi_device),
            "duplicate_surplus_rows": atlas_rows - len(atlas_by_value),
            "normalisation_collisions_more_than_one_raw_for_one_normalised": len(norm_collisions),
            "examples_multi_licence": [
                {"gtin": v, "rows": s["rows"],
                 "licences": sorted(map(str, s["licences"])),
                 "device_ids": sorted(map(str, s["device_ids"]))}
                for v, s in list(multi_licence.items())[:5]
            ],
            "examples_normalisation_collision": [
                {"normalised": v, "raw": sorted(raws)}
                for v, raws in list(norm_collisions.items())[:5]
            ],
        },
        "device_id_mixing_gtin_and_token": {
            "device_ids_with_both_classes": len(both_class_devices),
            "note": "device_id rows whose device_identifier is sometimes 14-digit and sometimes a model/catalogue token.",
        },
        "reach_denominators": {
            "distinct_licences_with_at_least_one_gtin_class_row": len(gtin_licences),
            "distinct_device_ids_with_at_least_one_gtin_class_row": len(gtin_device_ids),
            "note": "Denominators for how far a UDI bridge could ever reach inside MDALL.",
        },
        "atlas_reconciliation": {
            "atlas_scanned_until_limit": 1673926,
            "cache_rows": rows,
            "cache_rows_equals_atlas_scanned": rows == 1673926,
            "atlas_gtin_rows_kept": 5512,
            "cache_atlas_class_rows": atlas_rows,
            "gtin_rows_match_atlas": atlas_rows == 5512,
            "atlas_unique_di": 5005,
            "cache_atlas_class_distinct": len(atlas_by_value),
            "unique_di_match_atlas": len(atlas_by_value) == 5005,
            "atlas_share_published": 0.003293,
            "share_recomputed": round(atlas_rows / 1673926, 8),
            "atlas_identity_model_md_line": "5,477 bare 14-digit rows (5,512 after separator normalisation) out of 1,673,926 active identifier rows (0.33 %)",
            "bare_5477_matches_identity_model_doc": bare_rows == 5477,
            "normalised_5512_matches_atlas_report": atlas_rows == 5512,
        },
    }

    # numeric length distribution and distinct raw values need a second cheap pass
    length_dist = collections.Counter()
    raw_values: set[str] = set()
    numeric_by_length = collections.Counter()
    licence_ids: set = set()
    device_ids_all: set = set()
    for obj in iter_json_array(CACHE):
        raw = normalize_di(obj.get("device_identifier"))
        raw_values.add(raw)
        length_dist[len(raw)] += 1
        if raw.isdigit():
            numeric_by_length[len(raw)] += 1
        licence_ids.add(obj.get("original_licence_no"))
        device_ids_all.add(obj.get("device_id"))
    report["totals"]["distinct_device_identifier_values_raw"] = len(raw_values)
    report["totals"]["distinct_licences"] = len(licence_ids)
    report["totals"]["distinct_device_ids"] = len(device_ids_all)
    report["identifier_classes"]["length_distribution_all_rows"] = dict(sorted(length_dist.items()))
    report["identifier_classes"]["numeric_only_length_distribution_rows"] = dict(
        sorted(numeric_by_length.items())
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
