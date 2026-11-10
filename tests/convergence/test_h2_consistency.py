"""Tests for the EXP-H2 consistency gate.

The gate exists to make a documentation/artifact disagreement fail loudly.  A
test that only proved the gate runs would be useless, so every test here drives
the gate to a definite outcome and asserts the outcome, including two
deliberately inconsistent fixtures that the gate MUST reject.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = REPO_ROOT / "tools" / "convergence" / "h2" / "check_h2_consistency.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("h2_consistency_gate", GATE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


# ---------------------------------------------------------------------------
# fixture construction
# ---------------------------------------------------------------------------
def _row(pair_id, signals, verdict, construction=None):
    sig = {s: (s in signals) for s in ("S1", "S2", "S3", "S4", "S5")}
    return {
        "pair_id": pair_id,
        "signal_set": list(signals),
        "signals": sig,
        "signal_detail": {"models_shared": [], "name_tokens_shared": [],
                          "official_id_match": None},
        "verdict": verdict,
        "rationale": "fixture",
        "source_record_ids": {"fda": {"source_record_id": pair_id.split("__")[0]},
                              "canada": {"source_record_id": pair_id.split("__")[1]}},
        "fda_name": "fixture",
        "mdall_name": "fixture",
        "fda_firm": "Fixture",
        "mdall_firm": "Fixture",
        "construction_rule": construction,
    }


def _default_rows():
    return [
        _row("f1__m1", ["S3"], "UNKNOWN"),
        _row("f2__m2", ["S3"], "UNKNOWN"),
        _row("f3__m3", ["S3"], "UNKNOWN"),
        _row("f4__m4", ["S2"], "REJECTED"),
        _row("f5__m5", ["S3"], "UNKNOWN", construction="HN4_subsidiary_vs_parent"),
    ]


EXP_TEMPLATE = """# EXPERIMENT_RESULTS (fixture)

## EXP-H2 — fixture experiment

**Files:** `EXP_H2_PAIRS.jsonl` ({total} pairs), `EXP_H2_SUMMARY.json`.

### Result: {total} pairs, {confirmed} CONFIRMED

| verdict | n |
|---|---|
| `CONFIRMED` | **{confirmed}** |
| `REJECTED` | {rejected} |
| `UNKNOWN` | {unknown} |

Signal sufficiency:

| signal combination | pairs | CONFIRMED | REJECTED | UNKNOWN | reaches CONFIRMED? |
|---|---|---|---|---|---|
| S1 + S2 + S3 | — | 0 | — | — | **no** |
| S2 (shared model token) | {s2_fired} fired | 0 | {s2_rejected} | {s2_unknown} | no |
| S3 (same firm) | {s3_fired} fired | 0 | {s3_rejected} | {s3_unknown} | no |

Hard negatives: **{hn} pairs** constructed by the stated rule
`HN4_subsidiary_vs_parent`; all {hn} land in `UNKNOWN`.

## Next section (must not be scanned)
"""

REPORT_TEMPLATE = """# REGULATORY_FRONTIER_REPORT (fixture)

## 5. EXP-H2 — fixture experiment

{candidate} candidate pairs were generated from the fixture, plus {hn} hard
negatives, for {total} pairs in total.

| verdict | n |
|---|---|
| **CONFIRMED** | **{confirmed}** |
| REJECTED | {rejected} |
| UNKNOWN | {unknown} |

| signal combination | pairs | CONFIRMED | REJECTED | UNKNOWN |
|---|---|---|---|---|
| S2 alone (shared model token, {s2_fired} fired) | — | 0 | {s2_rejected} | {s2_unknown} |
| S3 alone (same firm, {s3_fired} fired) | — | 0 | {s3_rejected} | {s3_unknown} |

Hard negatives: {hn} pairs built by the stated rule
`HN4_subsidiary_vs_parent`.

## Next section (must not be scanned)
"""


def _default_summary():
    return {
        "experiment": "EXP-H2",
        "pairs_total": 5,
        "pairs_candidate": 4,
        "pairs_hard_negative": 1,
        "hard_negative_pair_count": 1,
        "verdicts": {"REJECTED": 1, "UNKNOWN": 4},
        "by_construction_rule": {"candidate": 4,
                                 "HN4_subsidiary_vs_parent": 1},
        "per_signal_sufficiency": {
            "S1": {"fired": 0, "CONFIRMED": 0, "REJECTED": 0, "UNKNOWN": 0},
            "S2": {"fired": 1, "CONFIRMED": 0, "REJECTED": 1, "UNKNOWN": 0},
            "S3": {"fired": 4, "CONFIRMED": 0, "REJECTED": 0, "UNKNOWN": 4},
            "S4": {"fired": 0, "CONFIRMED": 0, "REJECTED": 0, "UNKNOWN": 0},
            "S5": {"fired": 0, "CONFIRMED": 0, "REJECTED": 0, "UNKNOWN": 0},
        },
        "primary": {
            "pairs_total": 5,
            "pairs_candidate": 4,
            "pairs_hard_negative": 1,
            "verdicts": {"REJECTED": 1, "UNKNOWN": 4},
            "by_construction_rule": {"candidate": 4,
                                     "HN4_subsidiary_vs_parent": 1},
            "hard_negative_rules_attempted": {
                "HN1_same_brand_different_device": 0,
                "HN2_same_model_token_different_firm": 0,
                "HN3_same_family_different_device": 0,
                "HN4_subsidiary_vs_parent": 1,
            },
        },
        "finding": {
            "confirmed_pairs": 0,
            "rejected_pairs": 1,
            "S4_official_identifier_fired": 0,
            "s1_exact_name_fired": 0,
            "s2_model_in_both_fired": 1,
        },
    }


def _doc_params(rows, summary):
    truth = gate.recompute(rows)
    return {
        "total": truth["pairs_total"],
        "candidate": truth["pairs_candidate"],
        "hn": truth["pairs_hard_negative"],
        "confirmed": truth["verdicts"]["CONFIRMED"],
        "rejected": truth["verdicts"]["REJECTED"],
        "unknown": truth["verdicts"]["UNKNOWN"],
        "s2_fired": truth["per_signal"]["S2"]["fired"],
        "s2_rejected": truth["per_signal"]["S2"]["REJECTED"],
        "s2_unknown": truth["per_signal"]["S2"]["UNKNOWN"],
        "s3_fired": truth["per_signal"]["S3"]["fired"],
        "s3_rejected": truth["per_signal"]["S3"]["REJECTED"],
        "s3_unknown": truth["per_signal"]["S3"]["UNKNOWN"],
    }


def build_fixture(tmp_path, *, rows=None, summary=None, exp_override=None,
                  report_override=None):
    rows = rows if rows is not None else _default_rows()
    summary = summary if summary is not None else _default_summary()
    params = _doc_params(rows, summary)
    if exp_override:
        params = dict(params, **exp_override)
    if report_override:
        params = dict(params, **report_override)

    pairs_path = tmp_path / "EXP_H2_PAIRS.jsonl"
    summary_path = tmp_path / "EXP_H2_SUMMARY.json"
    exp_path = tmp_path / "EXPERIMENT_RESULTS.md"
    report_path = tmp_path / "REGULATORY_FRONTIER_REPORT.md"

    with open(pairs_path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    with open(summary_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(summary, fh, indent=2)
    exp_path.write_text(EXP_TEMPLATE.format(**params), encoding="utf-8")
    report_path.write_text(REPORT_TEMPLATE.format(**params), encoding="utf-8")
    return {
        "pairs": str(pairs_path),
        "summary": str(summary_path),
        "experiment_results": str(exp_path),
        "report": str(report_path),
    }


def _evaluate(paths):
    return gate.evaluate(paths["pairs"], paths["summary"],
                         paths["experiment_results"], paths["report"])


# ---------------------------------------------------------------------------
# the gate must PASS a consistent fixture
# ---------------------------------------------------------------------------
def test_gate_passes_on_consistent_fixture(tmp_path):
    paths = build_fixture(tmp_path)
    result = _evaluate(paths)
    assert result["exit_code"] == 0, result["mismatches"]
    assert result["status"] == "consistent"
    assert result["mismatches"] == []
    assert result["errors"] == []
    rec = result["recomputed"]
    assert rec["pairs_total"] == 5
    assert rec["verdicts"] == {"CONFIRMED": 0, "REJECTED": 1, "UNKNOWN": 4}


def test_gate_recomputes_from_pairs_not_from_summary(tmp_path):
    """A lying summary must fail even when both documents agree with the lie."""
    rows = _default_rows()
    lying_summary = _default_summary()
    lying_summary["verdicts"] = {"UNKNOWN": 5}
    lying_summary["pairs_total"] = 5  # total still true
    paths = build_fixture(tmp_path, rows=rows, summary=lying_summary)
    result = _evaluate(paths)
    assert result["exit_code"] == 1
    names = [m["name"] for m in result["mismatches"]]
    assert "summary.verdicts" in names
    # docs are still correct against the recomputed truth, so they must pass
    assert not any(n.startswith("doc.") for n in names)


# ---------------------------------------------------------------------------
# the gate must FAIL deliberately inconsistent fixtures
# ---------------------------------------------------------------------------
def test_gate_fails_on_stale_document_numbers(tmp_path):
    """The exact defect under investigation: docs quote a superseded run."""
    paths = build_fixture(
        tmp_path,
        exp_override={"total": 712, "rejected": 387, "unknown": 325,
                      "s2_fired": 445, "s3_fired": 365, "hn": 12,
                      "s2_rejected": 387, "s2_unknown": 58,
                      "s3_rejected": 40, "s3_unknown": 325},
        report_override={"candidate": 712, "rejected": 387, "unknown": 325,
                         "s2_fired": 445, "s3_fired": 365, "hn": 12,
                         "s2_rejected": 387, "s2_unknown": 58,
                         "s3_rejected": 40, "s3_unknown": 325, "total": 712},
    )
    result = _evaluate(paths)
    assert result["exit_code"] == 1
    by_name = {m["name"]: m for m in result["mismatches"]}
    exp_pairs = [m for n, m in by_name.items()
                 if n.startswith("doc.EXPERIMENT_RESULTS") and "pairs_total" in n]
    assert exp_pairs, by_name.keys()
    assert exp_pairs[0]["actual"] == 712
    rejected = by_name.get("doc.EXPERIMENT_RESULTS.md.verdict.REJECTED")
    assert rejected is not None and rejected["actual"] == 387
    assert rejected["expected"] == 1
    fired = by_name.get("doc.EXPERIMENT_RESULTS.md.S2.fired")
    assert fired is not None and fired["actual"] == 445
    assert fired["expected"] == 1
    # every mismatch carries a file:line location
    for mismatch in result["mismatches"]:
        assert mismatch["location"]


def test_gate_fails_on_summary_numbers_that_do_not_match_pairs(tmp_path):
    bad_summary = _default_summary()
    bad_summary["pairs_total"] = 999
    bad_summary["primary"]["verdicts"] = {"CONFIRMED": 0, "REJECTED": 0,
                                          "UNKNOWN": 5}
    paths = build_fixture(tmp_path, summary=bad_summary)
    result = _evaluate(paths)
    assert result["exit_code"] == 1
    names = {m["name"] for m in result["mismatches"]}
    assert "summary.pairs_total" in names
    assert "summary.primary.verdicts" in names


def test_gate_fails_on_duplicate_pair_ids(tmp_path):
    rows = _default_rows()
    rows.append(dict(rows[0]))  # same pair_id, extra row
    # keep the summary/docs describing the un-duplicated truth so the duplicate
    # check is what fires (pairs_total also shifts, which is fine)
    paths = build_fixture(tmp_path, rows=rows)
    result = _evaluate(paths)
    assert result["exit_code"] == 1
    dup = [m for m in result["mismatches"]
           if m["name"] == "pairs.unique_pair_ids"]
    assert dup and dup[0]["actual"] == ["f1__m1"]


# ---------------------------------------------------------------------------
# CLI contract: --json + exit codes
# ---------------------------------------------------------------------------
def test_cli_json_contract(tmp_path, capsys):
    good = build_fixture(tmp_path)
    rc = gate.main(["--json", "--pairs", good["pairs"],
                    "--summary", good["summary"],
                    "--experiment-results", good["experiment_results"],
                    "--report", good["report"]])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    payload = json.loads(captured.out)
    assert payload["status"] == "consistent"
    assert payload["exit_code"] == 0
    assert payload["recomputed"]["pairs_total"] == 5

    # mutate one quoted number: the same invocation must now exit non-zero
    exp = Path(good["experiment_results"])
    exp.write_text(exp.read_text(encoding="utf-8").replace("| `REJECTED` | 1 |",
                                                           "| `REJECTED` | 7 |"),
                   encoding="utf-8")
    rc = gate.main(["--json", "--pairs", good["pairs"],
                    "--summary", good["summary"],
                    "--experiment-results", good["experiment_results"],
                    "--report", good["report"]])
    captured = capsys.readouterr()
    assert rc == 1
    payload = json.loads(captured.out)
    assert payload["status"] == "inconsistent"
    assert any(m["actual"] == 7 for m in payload["mismatches"])


def test_gate_uses_only_stdlib():
    """The gate must run from a clean checkout with no third-party imports."""
    source = GATE_PATH.read_text(encoding="utf-8")
    for forbidden in ("import requests", "import pandas", "import numpy",
                      "import pytest", "from requests"):
        assert forbidden not in source
