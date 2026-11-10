"""P0-B regression tests: the 934-vs-0 identity reconciliation.

What is asserted (and why):

1.  The six frozen inputs are byte-identical to the ones every number in
    `docs/convergence/IDENTITY_RECONCILIATION.md` is bound to (SHA-256 + size +
    mtime).  If any input is re-fetched or edited, this test must fail loudly.
2.  The GTIN-14 validator accepts known-good GTINs and rejects deliberately
    corrupted ones (single-digit corruption at every one of the 14 positions),
    malformed strings, and the 78 check-digit-invalid 14-digit MDALL values.
3.  The 934 ATLAS pairs are 934 distinct relation ids / device pairs /
    shared GTINs / evidence records, every shared identifier is a
    check-digit-valid GTIN-14, and exactly 2 are package-DI anchored.
4.  The raw MDALL table really does contain the GTIN-14 minority ATLAS used:
    5,512 rows / 5,005 distinct values out of 1,673,926, with 5,434
    check-digit-valid rows and 78 distinct invalid-check values.
5.  HORIZON's Canada slice contains no GTIN-14 at all, and its 726 pairs are
    all UNKNOWN with S4 false — the structural reason for the 0.
6.  The frozen unified sample is one 1,660-row table with 0 record overlap
    between the two experiments, and both confusion tables reproduce.
7.  The coverage ceilings and concentration facts are the documented ones.

Runtime: the only slow test is the full 220 MB MDALL table scan (~60 s); every
other test is sub-second.  Tests that require the original `atlas-001` worktree
FAIL (not skip) when an input is missing, because the whole point of this
reconciliation is that it is reproducible against those exact bytes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ID = ROOT / "research" / "convergence" / "identity"
TOOLS = ROOT / "tools" / "convergence" / "identity"
sys.path.insert(0, str(TOOLS))

from gtin import (  # noqa: E402
    GTIN14_RE,
    gtin14_check_digit_ok,
    is_gtin_like,
    normalize_di,
)

FROZEN = json.loads((ID / "FROZEN_INPUTS.json").read_text(encoding="utf-8"))
REQUIRED = {b["role"]: b for b in FROZEN["required_inputs"]}

# Known-good GTINs taken from the frozen evidence itself, plus one canonical
# example used in GS1 documentation.
KNOWN_GOOD = [
    "00195278070265",  # ATLAS shared identifier (GE Hualun Definium Tempo Pro)
    "00884838085299",  # HORIZON GUDID record
    "08800022300803",  # MDALL separator-form row normalised to a GTIN
    "00012345600012",  # canonical valid GTIN-14 example
]
# The 14-digit values in the MDALL table that are numeric catalogue tokens, not
# GTINs: they fail the Mod-10 check.
KNOWN_BAD_FROM_MDALL = ["02002262000040", "02002264000000", "02022720030150"]


def sha256_file(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _require(role: str) -> dict:
    block = REQUIRED[role]
    path = Path(block["path"])
    if not path.exists():
        pytest.fail(f"frozen input missing: {role} -> {path}")
    return block


def iter_json_array(path: Path, chunk: int = 1 << 20):
    """Stream a top-level JSON array without materialising 220 MB."""
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


# ---------------------------------------------------------------------------
# 1. frozen inputs
# ---------------------------------------------------------------------------


def test_frozen_input_digests_still_match() -> None:
    assert FROZEN["network_used"] is False
    for role in (
        "atlas_db",
        "mdall_cache",
        "atlas_identity_report",
        "horizon_mdall_records",
        "horizon_gudid_records",
        "horizon_h2_pairs",
    ):
        block = _require(role)
        path = Path(block["path"])
        assert path.stat().st_size == block["size_bytes"], f"{role}: size changed"
        assert sha256_file(path) == block["sha256"], f"{role}: digest changed"
        recorded_mtime = datetime.fromisoformat(block["mtime_utc"]).timestamp()
        assert path.stat().st_mtime == pytest.approx(recorded_mtime, abs=1e-3), (
            f"{role}: mtime changed")


def test_mdall_cache_digest_is_the_one_atlas_recorded() -> None:
    cache = _require("mdall_cache")
    report = json.loads(Path(REQUIRED["atlas_identity_report"]["path"]).read_text(encoding="utf-8"))
    staged = report["stages"]["canada_mdall"]["table"]
    assert staged["sha256"] == cache["sha256"]
    assert staged["bytes"] == cache["size_bytes"]
    assert staged["truncated"] is False


# ---------------------------------------------------------------------------
# 2. GTIN-14 check-digit validator
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", KNOWN_GOOD)
def test_check_digit_validator_accepts_known_good(value: str) -> None:
    assert GTIN14_RE.match(value)
    assert is_gtin_like(value)
    assert gtin14_check_digit_ok(value) is True


@pytest.mark.parametrize("value", KNOWN_BAD_FROM_MDALL)
def test_check_digit_validator_rejects_mdall_numeric_tokens(value: str) -> None:
    # 14 digits, but not a GTIN: these are why "14 digits" alone is not enough.
    assert GTIN14_RE.match(value)
    assert is_gtin_like(value) is True
    assert gtin14_check_digit_ok(value) is False


def test_check_digit_validator_rejects_every_single_digit_corruption() -> None:
    base = "00195278070265"
    assert gtin14_check_digit_ok(base)
    for pos in range(14):
        digit = int(base[pos])
        corrupted = base[:pos] + str((digit + 1) % 10) + base[pos + 1:]
        assert corrupted != base
        assert gtin14_check_digit_ok(corrupted) is False, f"accepted corruption at pos {pos}"


@pytest.mark.parametrize(
    "value",
    ["", None, "1", "0019527807026", "001952780702655", "0019527807026X",
     "ABCDEFGHIJKLMN", "0019527807026-"],
)
def test_check_digit_validator_rejects_malformed(value) -> None:
    assert gtin14_check_digit_ok(value) is False


def test_normalize_di_removes_separators_and_keeps_leading_zeros() -> None:
    assert normalize_di("0 8800022 30080 3") == "08800022300803"
    assert normalize_di("0019-5278-070265") == "00195278070265"
    assert normalize_di(None) == ""
    assert gtin14_check_digit_ok("0 8800022 30080 3") is True


# ---------------------------------------------------------------------------
# 3. the 934 pairs: distinctness, validity, anchor typing
# ---------------------------------------------------------------------------


def test_934_pairs_are_distinct_and_check_digit_valid() -> None:
    bridge = json.loads((ID / "ATLAS_BRIDGE_934.json").read_text(encoding="utf-8"))
    pairs = bridge["pairs"]
    assert len(pairs) == 934
    assert len({p["relation_id"] for p in pairs}) == 934
    assert len({(p["fda_device_ref"], p["mdall_device_ref"]) for p in pairs}) == 934
    assert len({p["di"] for p in pairs}) == 934
    assert len({p["fda_evidence_id"] for p in pairs}) == 934
    assert len({p["mdall_evidence_id"] for p in pairs}) == 934
    assert all(GTIN14_RE.match(p["di"]) for p in pairs)
    assert all(gtin14_check_digit_ok(p["di"]) for p in pairs)
    assert all(p["relation_status"] == "CONFIRMED" for p in pairs)
    assert all(p["relation_method"] == "official_identifier" for p in pairs)
    assert all(p["relation_authority"] == "source_declared" for p in pairs)
    assert all(p["basis_shared_fields"] == ["di"] for p in pairs)
    # no DI in more than one pair, no US record in more than one pair
    assert max(Counter(p["di"] for p in pairs).values()) == 1
    assert max(Counter(p["fda_evidence_id"] for p in pairs).values()) == 1

    summary = bridge["gtin_validity"]
    assert summary["check_digit_valid"] == 934
    assert summary["check_digit_invalid"] == 0
    assert summary["duplicate_values"] == 0


def test_934_count_matches_the_atlas_relation_table() -> None:
    db = Path(_require("atlas_db")["path"])
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        rows = cur.execute(
            "select relation_type, status, method, authority, basis_json, run_id "
            "from entity_relations where relation_type='SAME_DEVICE_IDENTITY'"
        ).fetchall()
    finally:
        con.close()
    assert len(rows) == 934
    assert {(r[1], r[2], r[3]) for r in rows} == {("CONFIRMED", "official_identifier",
                                                  "source_declared")}
    assert len({r[5] for r in rows}) == 1  # one bridge run
    db_dis = {json.loads(r[4])["shared_identifier"] for r in rows}
    bridge = json.loads((ID / "ATLAS_BRIDGE_934.json").read_text(encoding="utf-8"))
    assert db_dis == {f"di:{p['di']}" for p in bridge["pairs"]}


def test_934_anchor_typing_and_the_942_accounting() -> None:
    bridge = json.loads((ID / "ATLAS_BRIDGE_934.json").read_text(encoding="utf-8"))
    pairs = bridge["pairs"]
    assert sum(1 for p in pairs if p["fda_di_is_primary"] is True) == 932
    assert sum(1 for p in pairs if p["fda_di_is_primary"] is False) == 2
    assert bridge["anchor_typing"]["payload_first_di_differs_from_primary"] == 2

    unified = json.loads((ID / "UNIFIED_SAMPLE_RESULTS.json").read_text(encoding="utf-8"))
    anchor = unified["anchor_sensitivity"]
    assert anchor["records_returned_by_bridge_query"] == 942
    assert anchor["published_pairs_first_di_anchored"] == 934
    assert anchor["primary_di_anchored_on_same_records"] == 941
    assert anchor["dropped_primary_di_matches"] == 7
    assert anchor["published_pairs_whose_anchor_is_not_the_primary_di"] == 2
    assert anchor["unpaired_total"] == 8


# ---------------------------------------------------------------------------
# 4. the raw MDALL table: the 0.33% GTIN minority (slow: full 220 MB scan)
# ---------------------------------------------------------------------------


SCAN_CACHE: dict | None = None


def _scan_mdall_classes() -> dict:
    """One full pass over the frozen 220 MB table, cached for the session."""
    global SCAN_CACHE
    if SCAN_CACHE is not None:
        return SCAN_CACHE
    cache = Path(_require("mdall_cache")["path"])
    rows = 0
    class_rows = 0
    class_values: set[str] = set()
    valid_class_values: set[str] = set()
    invalid_class_values: set[str] = set()
    multi_row: dict[str, int] = {}
    for obj in iter_json_array(cache):
        rows += 1
        raw = obj.get("device_identifier")
        if not is_gtin_like(raw):
            continue
        class_rows += 1
        value = normalize_di(raw)
        class_values.add(value)
        (valid_class_values if gtin14_check_digit_ok(value) else invalid_class_values).add(value)
        multi_row[value] = multi_row.get(value, 0) + 1
    SCAN_CACHE = {
        "rows": rows,
        "class_rows": class_rows,
        "class_values": class_values,
        "valid_class_values": valid_class_values,
        "invalid_class_values": invalid_class_values,
        "max_rows_per_gtin": max(multi_row.values()),
        "gtins_with_multiple_rows": sum(1 for n in multi_row.values() if n > 1),
    }
    return SCAN_CACHE


def test_mdall_table_gtin_minority_and_check_digits() -> None:
    scan = _scan_mdall_classes()
    assert scan["rows"] == 1673926
    assert scan["class_rows"] == 5512
    assert len(scan["class_values"]) == 5005
    assert len(scan["valid_class_values"]) == 4927
    assert len(scan["invalid_class_values"]) == 78
    assert round(scan["class_rows"] / scan["rows"], 8) == 0.00329286
    assert scan["max_rows_per_gtin"] == 5
    assert scan["gtins_with_multiple_rows"] == 235

    # every one of ATLAS's 934 shared identifiers is in the class and valid
    bridge = json.loads((ID / "ATLAS_BRIDGE_934.json").read_text(encoding="utf-8"))
    confirmed = {p["di"] for p in bridge["pairs"]}
    assert confirmed <= scan["class_values"]
    assert confirmed <= scan["valid_class_values"]
    assert confirmed & scan["invalid_class_values"] == set()


# ---------------------------------------------------------------------------
# 5. HORIZON's zero is structural
# ---------------------------------------------------------------------------


def test_horizon_canada_slice_contains_no_gtin14() -> None:
    mdall = Path(_require("horizon_mdall_records")["path"])
    records = [json.loads(line) for line in mdall.read_text(encoding="utf-8").splitlines() if line]
    assert len(records) == 174
    assert Counter(r["entity_type"] for r in records) == {
        "regulatory_clearance": 60, "regulatory_listing": 65, "product_identifier": 49}
    values = [str(i["value"]) for r in records for i in r.get("identifiers") or []]
    assert len(values) >= 49
    assert all(not (v.isdigit() and len(v) == 14) for v in values)
    assert sum(1 for v in values if gtin14_check_digit_ok(v)) == 0

    gudid = Path(_require("horizon_gudid_records")["path"])
    gudid_records = [json.loads(line) for line in gudid.read_text(encoding="utf-8").splitlines()
                     if line]
    assert len(gudid_records) == 320
    gudid_dis = {str(i["value"]) for r in gudid_records for i in r.get("identifiers") or []
                 if i.get("scheme") == "udi_di"}
    assert len(gudid_dis) == 320
    idents = {str(i["value"]) for r in records for i in r.get("identifiers") or []
              if i.get("scheme") == "hc_mdall_device_identifier"}
    assert len(idents) == 49
    assert idents & gudid_dis == set()


def test_horizon_h2_pairs_are_all_unknown_with_s4_false() -> None:
    pairs = Path(_require("horizon_h2_pairs")["path"])
    recs = [json.loads(line) for line in pairs.read_text(encoding="utf-8").splitlines() if line]
    assert len(recs) == 726
    assert Counter(r["verdict"] for r in recs) == {"UNKNOWN": 726}
    assert sum(1 for r in recs if r["signals"]["S4"]) == 0
    assert sum(1 for r in recs if r["construction_rule"] is not None) == 26


def test_horizon_identifier_semantics_claim_is_overgeneral_in_its_universal_form() -> None:
    mdall = Path(_require("horizon_mdall_records")["path"])
    records = [json.loads(line) for line in mdall.read_text(encoding="utf-8").splitlines() if line]
    claims = [r["attributes"].get("identifier_semantics") for r in records
              if r["entity_type"] == "product_identifier"]
    assert len(claims) == 49 and all(claims)
    assert len(set(claims)) == 1
    claim = claims[0]
    assert "NOT a UDI-DI" in claim and "shares no namespace" in claim
    # ... and it is contradicted as a universal statement by the table itself:
    scan = _scan_mdall_classes()
    assert scan["class_rows"] == 5512 and len(scan["valid_class_values"]) == 4927


# ---------------------------------------------------------------------------
# 6. the unified 1,660-pair sample and both confusion tables
# ---------------------------------------------------------------------------


def test_unified_sample_is_one_frozen_table_with_no_record_overlap() -> None:
    results = json.loads((ID / "UNIFIED_SAMPLE_RESULTS.json").read_text(encoding="utf-8"))
    sample_path = ID / "UNIFIED_SAMPLE.jsonl"
    assert sha256_file(sample_path) == results["sample"]["sha256"]
    rows = [json.loads(line) for line in sample_path.read_text(encoding="utf-8").splitlines()
            if line]
    assert len(rows) == 1660 == results["sample"]["rows"]
    assert Counter(r["origin_experiment"] for r in rows) == {
        "atlas_identity_pilot": 934, "horizon_exp_h2": 726}
    assert len({r["sample_row_id"] for r in rows}) == 1660

    atlas = [r for r in rows if r["origin_experiment"] == "atlas_identity_pilot"]
    horizon = [r for r in rows if r["origin_experiment"] == "horizon_exp_h2"]
    assert {r["us_di"] for r in atlas} & {r["us_di"] for r in horizon} == set()
    assert {r["ca_identifier_normalised"] for r in atlas} & {
        normalize_di(v) for r in horizon for v in r.get("ca_identifier_values_all", [])
    } == set()
    assert ({r["ca_licence"] for r in atlas if r["ca_licence"]}
            & {r["ca_licence"] for r in horizon if r["ca_licence"]}) == set()
    assert all(r["ca_is_valid_gtin14"] for r in atlas)
    assert not any(r["ca_is_valid_gtin14"] for r in horizon)


def test_unified_confusion_tables_reproduce() -> None:
    results = json.loads((ID / "UNIFIED_SAMPLE_RESULTS.json").read_text(encoding="utf-8"))
    native = results["confusion_native_typing"]
    assert (native["both_confirmed"], native["atlas_only_confirmed"],
            native["h2_only_confirmed"], native["neither_confirmed"]) == (0, 934, 0, 726)
    assert native["atlas_rejected"] == 0 and native["h2_rejected"] == 0
    assert native["atlas_unknown"] == 726 and native["h2_unknown"] == 1660
    assert native["raw_cells"] == {"CONFIRMED|UNKNOWN": 934, "UNKNOWN|UNKNOWN": 726}

    namespace = results["confusion_namespace_typing"]
    assert (namespace["both_confirmed"], namespace["atlas_only_confirmed"],
            namespace["h2_only_confirmed"], namespace["neither_confirmed"]) == (934, 0, 0, 726)
    assert namespace["raw_cells"] == {"CONFIRMED|CONFIRMED": 934, "UNKNOWN|UNKNOWN": 726}


# ---------------------------------------------------------------------------
# 7. coverage ceiling and concentration
# ---------------------------------------------------------------------------


def test_coverage_ceilings_and_concentration() -> None:
    cov = json.loads((ID / "COVERAGE_AND_ATTRIBUTION.json").read_text(encoding="utf-8"))
    ceiling = cov["joinable_ceiling"]
    assert ceiling["rows_number"] == 5512 and ceiling["total_rows"] == 1673926
    assert round(5512 / 1673926, 8) == 0.00329286
    assert ceiling["licences_number"] == 227 and ceiling["total_licences"] == 36056
    assert ceiling["device_lines_number"] == 679 and ceiling["total_device_lines"] == 146183

    confirmed = cov["confirmed_against_denominators"]
    assert confirmed["confirmed_pairs"] == 934
    assert round(934 / 5005, 6) == 0.186613
    assert round(934 / 1673926, 8) == 0.00055797
    assert cov["sampling"]["queried_gtin_values"] == 1200
    assert cov["sampling"]["unqueried_gtin_values"] == 3805

    conc = cov["concentration"]
    assert conc["distinct_us_labelers"] == 37
    assert conc["largest_labeler_pairs"] == 760
    assert conc["top4_labelers_pairs"] == 867
    assert conc["five_firm_register_pairs_strict_alias"] == 10
    assert conc["five_firm_register_pairs_atlas_stored"] == 12
    assert conc["ca_side_pairs_fully_unattributable"] == 925
    assert len(cov["falsifiers"]) >= 6
