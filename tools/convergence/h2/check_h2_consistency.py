#!/usr/bin/env python3
"""EXP-H2 consistency gate.

Recomputes the EXP-H2 verdict distribution directly from
``research/horizon/experiments/regulatory/EXP_H2_PAIRS.jsonl`` and then checks
that the frozen machine summary and the two prose documents quote the same
numbers.

It never trusts the summary JSON: every count is derived from the pair rows
(``verdict``, ``signal_set``, ``signals``, ``construction_rule``) first, and the
summary JSON is treated as just another claimant.

Exit codes
----------
0   everything consistent
1   at least one numeric mismatch (or a required claim could not be found)
2   an input file is missing / unreadable

Usage
-----
    python tools/convergence/h2/check_h2_consistency.py
    python tools/convergence/h2/check_h2_consistency.py --json

Optional overrides exist only so the test-suite can point the gate at fixtures;
a clean checkout needs none of them.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "..", ".."))

DEFAULT_PATHS = {
    "pairs": "research/horizon/experiments/regulatory/EXP_H2_PAIRS.jsonl",
    "summary": "research/horizon/experiments/regulatory/EXP_H2_SUMMARY.json",
    "experiment_results": "research/horizon/EXPERIMENT_RESULTS.md",
    "report": "research/horizon/reports/REGULATORY_FRONTIER_REPORT.md",
}

VERDICTS = ("CONFIRMED", "REJECTED", "UNKNOWN")
SIGNALS = ("S1", "S2", "S3", "S4", "S5")


# --------------------------------------------------------------------------- io
def _read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
    return rows


def _read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# ------------------------------------------------------------------ recompute
def recompute(rows):
    """Derive every EXP-H2 count from the pair rows themselves."""
    verdicts = Counter(r.get("verdict") for r in rows)
    construction = Counter(r.get("construction_rule") or "candidate" for r in rows)

    per_signal = {}
    for sig in SIGNALS:
        fired = [r for r in rows if (r.get("signals") or {}).get(sig)]
        per_signal[sig] = {
            "fired": len(fired),
            "CONFIRMED": sum(1 for r in fired if r.get("verdict") == "CONFIRMED"),
            "REJECTED": sum(1 for r in fired if r.get("verdict") == "REJECTED"),
            "UNKNOWN": sum(1 for r in fired if r.get("verdict") == "UNKNOWN"),
        }

    combos = defaultdict(lambda: {"n": 0, "CONFIRMED": 0, "REJECTED": 0, "UNKNOWN": 0})
    for r in rows:
        sig_set = r.get("signal_set")
        if sig_set is None:
            # fall back to the boolean map; '+' order follows the canonical order
            sig_set = [s for s in SIGNALS if (r.get("signals") or {}).get(s)]
        label = "+".join(sig_set)
        combos[label]["n"] += 1
        combos[label][r.get("verdict")] = combos[label].get(r.get("verdict"), 0) + 1

    ids = [r.get("pair_id") for r in rows]
    duplicated = sorted(k for k, v in Counter(ids).items() if v > 1)

    candidate = sum(1 for r in rows if not r.get("construction_rule"))
    hard_negative = len(rows) - candidate

    return {
        "pairs_total": len(rows),
        "pairs_candidate": candidate,
        "pairs_hard_negative": hard_negative,
        "verdicts": {v: verdicts.get(v, 0) for v in VERDICTS},
        "by_construction_rule": dict(construction),
        "hard_negative_rules": {
            k: v for k, v in construction.items() if k != "candidate"
        },
        "per_signal": per_signal,
        "signal_combinations": {
            k: dict(v) for k, v in sorted(combos.items())
        },
        "pair_id_total": len(ids),
        "pair_id_unique": len(set(ids)),
        "duplicate_pair_ids": duplicated,
    }


# ------------------------------------------------------------ doc extraction
def _section(lines, start_pred, stop_pred=None):
    """Return (slice_of_lines, first_line_number)."""
    start = None
    for i, line in enumerate(lines):
        if start_pred(line):
            start = i
            break
    if start is None:
        return None, None
    stop = len(lines)
    for j in range(start + 1, len(lines)):
        if stop_pred is not None:
            if stop_pred(lines[j]):
                stop = j
                break
        elif re.match(r"^##\s", lines[j]):
            stop = j
            break
    return lines[start:stop], start + 1


def _num(cell):
    """Parse an optional integer cell; '—', '-', '' -> None."""
    if cell is None:
        return None
    c = cell.strip().strip("*").strip("`").strip()
    if re.fullmatch(r"-?\d+", c):
        return int(c)
    return None


def _norm_combo(label):
    return re.sub(r"\s+", "", label)


def _parse_table_row(line):
    """Split a markdown table line into stripped cells (no outer pipes)."""
    s = line.strip()
    if not s.startswith("|"):
        return None
    s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


VERDICT_ROW_RE = re.compile(
    r"^\|\s*[`*]{0,2}(CONFIRMED|REJECTED|UNKNOWN)[`*]{0,2}\s*\|\s*[`*]{0,2}(-?\d+)[`*]{0,2}\s*\|")
COMBO_LABEL_RE = re.compile(r"^(S\d(?:\s*\+\s*S\d)*)$")
SIGNAL_ROW_RE = re.compile(r"^(S\d)\b")


def extract_doc_claims(path, doc_key, text):
    """Extract every numeric EXP-H2 claim the gate knows how to read.

    Returns (claims, errors).  Each claim is a dict with:
        key, kind, expected_key, doc, line, raw, value
    ``expected_key`` names the recomputed truth field to compare against.
    """
    claims = []
    errors = []

    lines = text.splitlines()
    if doc_key == "experiment_results":
        sec, base = _section(lines, lambda l: l.startswith("## EXP-H2"),
                             lambda l: bool(re.match(r"^##\s", l)) and not l.startswith("## EXP-H2"))
    elif doc_key == "report":
        sec, base = _section(lines, lambda l: l.startswith("## 5. EXP-H2"),
                             lambda l: bool(re.match(r"^##\s", l)) and not l.startswith("## 5. EXP-H2"))
    else:  # pragma: no cover - defensive
        raise ValueError(doc_key)
    if sec is None:
        errors.append({"claim": "section", "doc": path, "line": None,
                       "message": "EXP-H2 section not found"})
        return claims, errors

    def add(key, lineno, raw, value, expected_key):
        claims.append({"key": key, "doc": path, "line": lineno,
                       "raw": raw.strip(), "value": value,
                       "expected_key": expected_key})

    for offset, line in enumerate(sec):
        lineno = base + offset

        # -- total pair counts ------------------------------------------------
        m = re.search(r"`EXP_H2_PAIRS\.jsonl`\s*\((\d+)\s+pairs\)", line)
        if m:
            add("pairs_total(file-list)", lineno, line, int(m.group(1)), "pairs_total")

        m = re.search(r"###\s*Result:\s*(\d+)\s+pairs,\s*(\d+)\s+CONFIRMED", line)
        if m:
            add("pairs_total(result-heading)", lineno, line, int(m.group(1)), "pairs_total")
            add("confirmed(result-heading)", lineno, line, int(m.group(2)),
                "verdict.CONFIRMED")

        m = re.search(r"(\d+)\s+(candidate\s+)?pairs were generated", line)
        if m:
            if m.group(2):
                add("pairs_candidate", lineno, line, int(m.group(1)), "pairs_candidate")
            else:
                add("pairs_total", lineno, line, int(m.group(1)), "pairs_total")

        m = re.search(r"(\d+)\s+pairs in total", line)
        if m:
            add("pairs_total(in-total)", lineno, line, int(m.group(1)), "pairs_total")

        m = re.search(r"Hard negatives:\s*\*{0,2}(\d+)\s+pairs?\*{0,2}", line)
        if m:
            add("pairs_hard_negative", lineno, line, int(m.group(1)),
                "pairs_hard_negative")

        m = re.search(r"(\d+)\s+pairs share a model token", line)
        if m:
            add("S2.fired(sentence)", lineno, line, int(m.group(1)),
                "per_signal.S2.fired")

        # -- verdict table ----------------------------------------------------
        m = VERDICT_ROW_RE.match(line)
        if m:
            add(f"verdict.{m.group(1)}", lineno, line, int(m.group(2)),
                f"verdict.{m.group(1)}")
            continue

        # -- signal / combination table --------------------------------------
        cells = _parse_table_row(line)
        if not cells or len(cells) < 5:
            continue
        label = cells[0]
        combo_m = COMBO_LABEL_RE.match(label)
        signal_m = SIGNAL_ROW_RE.match(label)
        if combo_m:
            combo = _norm_combo(label)
            for idx, verdict in ((2, "CONFIRMED"), (3, "REJECTED"), (4, "UNKNOWN")):
                val = _num(cells[idx])
                if val is not None:
                    add(f"combo.{combo}.{verdict}", lineno, line, val,
                        f"combo.{combo}.{verdict}")
            val = _num(cells[1])
            if val is not None:
                add(f"combo.{combo}.n", lineno, line, val, f"combo.{combo}.n")
        elif signal_m and "(" in label:
            sig = signal_m.group(1)
            fired_m = re.search(r"(\d+)\s+fired", label + " " + cells[1])
            if fired_m:
                add(f"{sig}.fired", lineno, line, int(fired_m.group(1)),
                    f"per_signal.{sig}.fired")
            for idx, verdict in ((2, "CONFIRMED"), (3, "REJECTED"), (4, "UNKNOWN")):
                val = _num(cells[idx])
                if val is not None:
                    add(f"{sig}.{verdict}", lineno, line, val,
                        f"per_signal.{sig}.{verdict}")

    # Required claim families per document (fail closed if a template vanished).
    keys = [c["key"] for c in claims]
    if not any(k.startswith("pairs_total") or k.startswith("pairs_candidate")
               for k in keys):
        errors.append({"claim": "pairs_total", "doc": path, "line": None,
                       "message": "no total/candidate pair-count claim matched"})
    missing_verdicts = [v for v in VERDICTS
                        if f"verdict.{v}" not in keys]
    if missing_verdicts:
        errors.append({"claim": "verdict-table", "doc": path, "line": None,
                       "message": "verdict rows not found: " + ",".join(missing_verdicts)})
    missing_signals = [s for s in ("S2", "S3")
                       if f"{s}.fired" not in keys]
    if missing_signals:
        errors.append({"claim": "signal-table", "doc": path, "line": None,
                       "message": "per-signal fired claims not found: " + ",".join(missing_signals)})
    if "pairs_hard_negative" not in keys:
        errors.append({"claim": "hard-negatives", "doc": path, "line": None,
                       "message": "hard-negative pair count not found"})

    return claims, errors


# --------------------------------------------------------------- truth lookup
def resolve_truth(recomputed, expected_key):
    """Map a claim's expected_key to (value, human_path) from recomputed truth."""
    if expected_key == "pairs_total":
        return recomputed["pairs_total"], "pairs_total"
    if expected_key == "pairs_candidate":
        return recomputed["pairs_candidate"], "pairs_candidate"
    if expected_key == "pairs_hard_negative":
        return recomputed["pairs_hard_negative"], "pairs_hard_negative"
    m = re.fullmatch(r"verdict\.(CONFIRMED|REJECTED|UNKNOWN)", expected_key)
    if m:
        return recomputed["verdicts"][m.group(1)], expected_key
    m = re.fullmatch(r"per_signal\.(S\d)\.(fired|CONFIRMED|REJECTED|UNKNOWN)", expected_key)
    if m:
        return recomputed["per_signal"][m.group(1)][m.group(2)], expected_key
    m = re.fullmatch(r"combo\.(S\d(?:\+S\d)*)\.(n|CONFIRMED|REJECTED|UNKNOWN)", expected_key)
    if m:
        combo = recomputed["signal_combinations"].get(m.group(1), {})
        default = {"n": 0, "CONFIRMED": 0, "REJECTED": 0, "UNKNOWN": 0}[m.group(2)]
        return combo.get(m.group(2), default), expected_key
    raise KeyError(expected_key)


# ------------------------------------------------------- summary comparisons
def summary_checks(summary, recomputed):
    """Compare the frozen summary JSON against the recomputed truth."""
    checks = []

    def check(name, actual, expected, location):
        ok = actual == expected
        checks.append({"name": name, "actual": actual, "expected": expected,
                       "ok": ok, "location": location})
        return ok

    summary_path = "EXP_H2_SUMMARY.json"
    for key in ("pairs_total", "pairs_candidate", "pairs_hard_negative"):
        if key in summary:
            check(f"summary.{key}", summary[key], recomputed[key], summary_path)
    if "hard_negative_pair_count" in summary:
        check("summary.hard_negative_pair_count", summary["hard_negative_pair_count"],
              recomputed["pairs_hard_negative"], summary_path)

    sv = summary.get("verdicts") or {}
    normalized = {v: sv.get(v, 0) for v in VERDICTS}
    check("summary.verdicts", normalized, recomputed["verdicts"], summary_path)

    sb = summary.get("by_construction_rule") or {}
    check("summary.by_construction_rule", sb, recomputed["by_construction_rule"],
          summary_path)

    sps = summary.get("per_signal_sufficiency") or {}
    for sig in SIGNALS:
        if sig in sps and "fired" in sps[sig]:
            check(f"summary.per_signal.{sig}.fired", sps[sig]["fired"],
                  recomputed["per_signal"][sig]["fired"], summary_path)

    # primary block (duplicated at top level in the frozen artifact)
    primary = summary.get("primary") or {}
    if primary:
        for key in ("pairs_total", "pairs_candidate", "pairs_hard_negative"):
            if key in primary:
                check(f"summary.primary.{key}", primary[key], recomputed[key],
                      summary_path)
        if "verdicts" in primary:
            pv = {v: primary["verdicts"].get(v, 0) for v in VERDICTS}
            check("summary.primary.verdicts", pv, recomputed["verdicts"], summary_path)
        if "by_construction_rule" in primary:
            check("summary.primary.by_construction_rule",
                  primary["by_construction_rule"], recomputed["by_construction_rule"],
                  summary_path)
        hn_rules = primary.get("hard_negative_rules_attempted") or {}
        if hn_rules:
            expected_hn = {k: recomputed["by_construction_rule"].get(k, 0)
                           for k in hn_rules}
            check("summary.primary.hard_negative_rules_attempted", hn_rules,
                  expected_hn, summary_path)

    finding = summary.get("finding") or {}
    if "confirmed_pairs" in finding:
        check("summary.finding.confirmed_pairs", finding["confirmed_pairs"],
              recomputed["verdicts"]["CONFIRMED"], summary_path)
    if "rejected_pairs" in finding:
        check("summary.finding.rejected_pairs", finding["rejected_pairs"],
              recomputed["verdicts"]["REJECTED"], summary_path)
    if "S4_official_identifier_fired" in finding:
        check("summary.finding.S4_official_identifier_fired",
              finding["S4_official_identifier_fired"],
              recomputed["per_signal"]["S4"]["fired"], summary_path)
    if "s2_model_in_both_fired" in finding:
        check("summary.finding.s2_model_in_both_fired",
              finding["s2_model_in_both_fired"],
              recomputed["per_signal"]["S2"]["fired"], summary_path)
    if "s1_exact_name_fired" in finding:
        check("summary.finding.s1_exact_name_fired",
              finding["s1_exact_name_fired"],
              recomputed["per_signal"]["S1"]["fired"], summary_path)

    return checks


# --------------------------------------------------------------------- main
def evaluate(pairs_path, summary_path, experiment_results_path, report_path):
    """Run every check.  Returns a result dict (never raises for mismatches)."""
    errors = []
    try:
        rows = _read_jsonl(pairs_path)
    except (OSError, ValueError) as exc:
        return {"status": "error", "exit_code": 2, "error": str(exc),
                "checks": [], "mismatches": [], "errors": [], "recomputed": None}
    try:
        summary = json.loads(_read_text(summary_path))
    except (OSError, ValueError) as exc:
        return {"status": "error", "exit_code": 2, "error": str(exc),
                "checks": [], "mismatches": [], "errors": [], "recomputed": None}
    try:
        exp_text = _read_text(experiment_results_path)
        rep_text = _read_text(report_path)
    except OSError as exc:
        return {"status": "error", "exit_code": 2, "error": str(exc),
                "checks": [], "mismatches": [], "errors": [], "recomputed": None}

    recomputed = recompute(rows)
    checks = []

    # 1. structural sanity of the pair file itself
    if recomputed["duplicate_pair_ids"]:
        checks.append({
            "name": "pairs.unique_pair_ids",
            "actual": recomputed["duplicate_pair_ids"],
            "expected": "no duplicate pair_id",
            "ok": False,
            "location": pairs_path,
        })
    else:
        checks.append({
            "name": "pairs.unique_pair_ids",
            "actual": recomputed["pair_id_total"],
            "expected": recomputed["pair_id_unique"],
            "ok": recomputed["pair_id_total"] == recomputed["pair_id_unique"],
            "location": pairs_path,
        })

    # 2. summary JSON must agree with the recomputed truth
    checks.extend(summary_checks(summary, recomputed))

    # 3. both prose documents must quote the recomputed truth
    doc_claims = []
    for doc_key, path, text in (
        ("experiment_results", experiment_results_path, exp_text),
        ("report", report_path, rep_text),
    ):
        claims, doc_errors = extract_doc_claims(path, doc_key, text)
        errors.extend(doc_errors)
        doc_claims.extend(claims)
        for claim in claims:
            expected, human = resolve_truth(recomputed, claim["expected_key"])
            checks.append({
                "name": f"doc.{os.path.basename(path)}.{claim['key']}",
                "actual": claim["value"],
                "expected": expected,
                "ok": claim["value"] == expected,
                "location": f"{claim['doc']}:{claim['line']}",
                "expected_path": human,
            })

    mismatches = [c for c in checks if not c["ok"]]
    status = "consistent" if (not mismatches and not errors) else "inconsistent"
    return {
        "status": status,
        "exit_code": 0 if status == "consistent" else 1,
        "checks": checks,
        "mismatches": mismatches,
        "errors": errors,
        "recomputed": recomputed,
    }


def _print_human(result, pairs_path, summary_path):
    if result["status"] == "error":
        print(f"ERROR: {result['error']}", file=sys.stderr)
        return
    rec = result["recomputed"]
    print("EXP-H2 recomputed from", pairs_path)
    print(f"  pairs_total={rec['pairs_total']}  candidate={rec['pairs_candidate']}  "
          f"hard_negative={rec['pairs_hard_negative']}  "
          f"unique_pair_ids={rec['pair_id_unique']}")
    print("  verdicts:", json.dumps(rec["verdicts"], sort_keys=True))
    print("  per-signal fired:",
          {s: rec["per_signal"][s]["fired"] for s in SIGNALS})
    print("  by construction rule:", json.dumps(rec["by_construction_rule"],
                                                sort_keys=True))
    print()
    total = len(result["checks"])
    passed = total - len(result["mismatches"])
    print(f"checks: {passed}/{total} passed, {len(result['mismatches'])} mismatched, "
          f"{len(result['errors'])} extraction error(s)")
    for err in result["errors"]:
        print(f"  EXTRACT {err['doc']}: {err['message']}")
    for mm in result["mismatches"]:
        print(f"  MISMATCH {mm['name']}")
        print(f"           location: {mm['location']}")
        print(f"           quoted:   {mm['actual']!r}")
        print(f"           truth:    {mm['expected']!r}")
    print()
    print("RESULT:", result["status"].upper())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--repo-root", default=REPO_ROOT,
                    help="repository root (default: three levels above this script)")
    ap.add_argument("--pairs", help="override EXP_H2_PAIRS.jsonl path")
    ap.add_argument("--summary", help="override EXP_H2_SUMMARY.json path")
    ap.add_argument("--experiment-results", help="override EXPERIMENT_RESULTS.md path")
    ap.add_argument("--report", help="override REGULATORY_FRONTIER_REPORT.md path")
    args = ap.parse_args(argv)

    def resolve(override, key):
        if override:
            return os.path.abspath(override)
        return os.path.join(os.path.abspath(args.repo_root), DEFAULT_PATHS[key])

    pairs_path = resolve(args.pairs, "pairs")
    summary_path = resolve(args.summary, "summary")
    exp_path = resolve(args.experiment_results, "experiment_results")
    rep_path = resolve(args.report, "report")

    result = evaluate(pairs_path, summary_path, exp_path, rep_path)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        _print_human(result, pairs_path, summary_path)
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
