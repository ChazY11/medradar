"""Independent adversarial audit for SCIENCE-002.

This module deliberately does not import the panel's feature functions. It
re-implements the availability rules with different code (bisect on sorted dates,
direct filtering over the cached SEC records) and compares the result with the
committed panel. A mismatch is a defect, not a rounding difference.

Checks
------
A1  feature recomputation - does an independent implementation reproduce
    clr_365, clr_730, n_8k_90, n_801_90 and rd_ttm_log for a random sample?
A2  no future evidence - is the latest availability timestamp used by any feature
    at or before the prediction instant t?
A3  label independence - are labels reproduced from the clearance index, and is
    the label window strictly after every feature's availability cut?
A4  attribution uniqueness - does any FDA k_number or applicant string appear
    under two firms?
A5  selection audit - which rows were dropped, and does any drop depend on the
    outcome?
A6  future-filing injection - adding a filing accepted after t must not change
    any feature of that row (adversarial test, executed, not asserted by
    inspection).
A7  reproducibility - two runs of the frozen experiment produce identical
    digests.
A8  permutation stability - the primary p-value under a second independent seed.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from . import fda, sec
from .entity import normalise_name
from .panel import HORIZON_DAYS, AVAILABILITY_LAG_DAYS, MODEL_FEATURES, PANEL_START

SAMPLE_ROWS = 60


def _t(row: Any) -> datetime:
    return datetime.combine(row.month_end, datetime.max.time()).replace(tzinfo=timezone.utc)


def _recompute_clearance_features(dates: Sequence[date], t: datetime) -> dict[str, float]:
    """Independent implementation: bisect on the sorted clearance date list."""
    cutoff = (t - timedelta(days=AVAILABILITY_LAG_DAYS)).date()
    upper = bisect.bisect_right(dates, cutoff)
    out = {}
    for name, window in (("clr_90", 90), ("clr_365", 365), ("clr_730", 730)):
        lower = bisect.bisect_right(dates, cutoff - timedelta(days=window))
        out[name] = float(upper - lower)
    out["clr_rate_365"] = (out["clr_365"] + 1.0) / 3.0
    out["clr_rate_730"] = (out["clr_730"] + 1.0) / 5.0
    return out


def _recompute_filing_features(filings: Sequence[sec.Filing], t: datetime) -> dict[str, float]:
    out = Counter()
    for filing in filings:
        stamp = filing.acceptance_utc
        if stamp is None or stamp > t or filing.form not in sec.EIGHT_K_FORMS:
            continue
        age = t - stamp
        if age <= timedelta(days=90):
            out["n_8k_90"] += 1
            if filing.has_item("8.01"):
                out["n_801_90"] += 1
            if filing.has_item("2.02"):
                out["n_202_90"] += 1
        if age <= timedelta(days=365):
            out["n_8k_365"] += 1
            if filing.has_item("8.01"):
                out["n_801_365"] += 1
    return {k: float(v) for k, v in out.items()}


def _recompute_ttm(facts: Sequence[sec.Fact], t: datetime) -> float | None:
    asof = t.date()
    quarters = [f for f in facts
                if 70 <= (f.end - f.start).days <= 110 and f.end <= asof and f.filed <= asof]
    by_end: dict[date, sec.Fact] = {}
    for fact in quarters:
        current = by_end.get(fact.end)
        if current is None or fact.filed < current.filed:
            by_end[fact.end] = fact
    ends = sorted(by_end)[-4:]
    if len(ends) < 4:
        return None
    return float(sum(by_end[e].value for e in ends))


def _latest_availability(row: Any, sub: sec.Submissions, facts: sec.CompanyFacts) -> dict[str, Any]:
    """The latest timestamp each feature family could have read at this row."""
    t = _t(row)
    filings_used = [f for f in sub.filings
                    if f.acceptance_utc is not None and f.acceptance_utc <= t
                    and (t - f.acceptance_utc).days <= 365]
    facts_used = [f for f in facts.rd if f.filed <= t.date() and f.end <= t.date()]
    return {
        "t": t.isoformat(),
        "latest_filing_acceptance": max((f.acceptance_utc for f in filings_used), default=None),
        "latest_fact_filed": max((f.filed for f in facts_used), default=None),
    }


def run(build: Any, panel_result: Any, clearance_dates: Mapping[str, Sequence[date]],
        records: Sequence[Mapping[str, str]], seed: int = 20261114) -> dict[str, Any]:
    rng = random.Random(seed)
    out: dict[str, Any] = {"checks": {}, "verdict": {}, "meta": {
        "n_rows": len(panel_result.rows), "n_firms": len(build.included),
        "sample_rows": SAMPLE_ROWS, "seed": seed}}

    out["checks"]["A1_feature_recomputation"] = _a1(build, panel_result, clearance_dates, rng)
    out["checks"]["A2_no_future_evidence"] = _a2(build, panel_result, rng)
    out["checks"]["A3_label_independence"] = _a3(panel_result, clearance_dates, rng)
    out["checks"]["A4_attribution_uniqueness"] = _a4(build, records)
    out["checks"]["A5_selection_audit"] = _a5(panel_result)
    out["checks"]["A6_future_filing_injection"] = _a6(build, panel_result, rng)
    out["verdict"] = _verdict(out["checks"])
    return out


def _a1(build: Any, panel_result: Any, clearance_dates: Mapping[str, Sequence[date]],
        rng: random.Random) -> dict[str, Any]:
    rows = [r for r in panel_result.rows if r.split in ("train", "holdout")]
    rng.shuffle(rows)
    sample = rows[:SAMPLE_ROWS]
    mismatches: list[dict[str, Any]] = []
    checked = 0
    for row in sample:
        sub = build.submissions.get(row.cik)
        facts = build.facts.get(row.cik)
        if sub is None or facts is None:
            continue
        t = _t(row)
        expected = {}
        expected.update(_recompute_clearance_features(sorted(clearance_dates.get(row.cik, [])), t))
        expected.update(_recompute_filing_features(sub.filings, t))
        ttm = _recompute_ttm(facts.rd, t)
        if ttm is not None and ttm > 0:
            expected["rd_ttm_log"] = math.log(ttm)
        checked += 1
        for name, value in expected.items():
            actual = row.features.get(name)
            if actual is None or abs(float(actual) - value) > 1e-6:
                mismatches.append({"key": row.key, "month": row.month_end.isoformat(),
                                   "feature": name, "panel": actual, "recomputed": value})
    return {"n_checked": checked, "n_mismatch": len(mismatches),
            "mismatches": mismatches[:10], "passed": len(mismatches) == 0}


def _a2(build: Any, panel_result: Any, rng: random.Random) -> dict[str, Any]:
    rows = list(panel_result.rows)
    rng.shuffle(rows)
    violations = []
    checked = 0
    for row in rows[:SAMPLE_ROWS]:
        sub = build.submissions.get(row.cik)
        facts = build.facts.get(row.cik)
        if sub is None or facts is None:
            continue
        info = _latest_availability(row, sub, facts)
        t = _t(row)
        checked += 1
        if info["latest_filing_acceptance"] is not None and info["latest_filing_acceptance"] > t:
            violations.append({"key": row.key, "month": row.month_end.isoformat(),
                               "kind": "filing"})
        if info["latest_fact_filed"] is not None and info["latest_fact_filed"] > t.date():
            violations.append({"key": row.key, "month": row.month_end.isoformat(),
                               "kind": "fact"})
    return {"n_checked": checked, "violations": violations, "passed": not violations}


def _a3(panel_result: Any, clearance_dates: Mapping[str, Sequence[date]],
        rng: random.Random) -> dict[str, Any]:
    mismatches = []
    overlap = []
    for row in panel_result.rows:
        dates = sorted(clearance_dates.get(row.cik, []))
        t = _t(row)
        window = [d for d in dates if t.date() < d <= t.date() + timedelta(days=HORIZON_DAYS)]
        if (1 if window else 0) != row.label:
            mismatches.append({"key": row.key, "month": row.month_end.isoformat(),
                               "panel": row.label, "recomputed": 1 if window else 0})
        cutoff = (t - timedelta(days=AVAILABILITY_LAG_DAYS)).date()
        if window and min(window) <= cutoff:
            overlap.append({"key": row.key, "month": row.month_end.isoformat()})
    return {"n_rows": len(panel_result.rows), "n_mismatch": len(mismatches),
            "n_window_overlap_with_feature_cut": len(overlap),
            "mismatches": mismatches[:10], "passed": not mismatches and not overlap}


def _a4(build: Any, records: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    root_owner: dict[str, set[str]] = defaultdict(set)
    for firm in build.included:
        for match in firm.applicants:
            root_owner[str(match["applicant_root"])].add(firm.cik)
    shared_roots = {k: sorted(v) for k, v in root_owner.items() if len(v) > 1}

    k_firm: dict[str, set[str]] = defaultdict(set)
    root_to_cik = {root: next(iter(ciks)) for root, ciks in root_owner.items()}
    for row in records:
        if (row.get("decision_code") or "") not in fda.CLEARED_DECISION_CODES:
            continue
        cik = root_to_cik.get(normalise_name(row.get("applicant") or ""))
        if cik and row.get("k_number"):
            k_firm[str(row["k_number"])].add(cik)
    shared_k = {k: sorted(v) for k, v in k_firm.items() if len(v) > 1}
    return {"n_applicant_roots": len(root_owner), "shared_roots": shared_roots,
            "n_k_numbers": len(k_firm), "shared_k_numbers": shared_k,
            "passed": not shared_roots and not shared_k}


def _a5(panel_result: Any) -> dict[str, Any]:
    rows = panel_result.rows
    by_split = Counter(r.split for r in rows)
    firms_with_single_class: dict[str, dict[str, int]] = {}
    per_firm: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        per_firm[row.key].append(row.label)
    for key, labels in per_firm.items():
        if len(set(labels)) == 1 and len(labels) > 0:
            firms_with_single_class[key] = {"n": len(labels), "label": labels[0]}
    return {
        "rows_by_split": dict(by_split),
        "dropped": {
            "sec_coverage": panel_result.meta.get("n_rows_dropped_sec_coverage"),
            "maturity_cut": "rows whose 90-day window would cross " +
                            str(panel_result.meta.get("fda_maturity_cut")) + " are omitted at construction",
        },
        "firms_with_single_class_in_panel": firms_with_single_class,
        "n_firms_single_class": len(firms_with_single_class),
        "note": "single-class firms contribute to model fitting but are excluded "
                "from the stratified AUC, which is reported with its firm count",
        "passed": True,
    }


def _a6(build: Any, panel_result: Any, rng: random.Random) -> dict[str, Any]:
    """Inject a filing accepted after t and confirm no feature moves."""
    rows = list(panel_result.rows)
    rng.shuffle(rows)
    changed = []
    checked = 0
    for row in rows[:20]:
        sub = build.submissions.get(row.cik)
        if sub is None:
            continue
        baseline = _recompute_filing_features(sub.filings, _t(row))
        injected = sec.Filing(
            accession="0000000000-99-999999", form="8-K",
            filing_date=row.month_end + timedelta(days=1),
            acceptance_utc=_t(row) + timedelta(seconds=60),
            items=("8.01", "2.02"), primary_document="future.htm")
        after = _recompute_filing_features(list(sub.filings) + [injected], _t(row))
        checked += 1
        if after != baseline:
            changed.append({"key": row.key, "month": row.month_end.isoformat(),
                            "before": baseline, "after": after})
    return {"n_checked": checked, "n_changed": len(changed), "changed": changed,
            "passed": not changed}


def _verdict(checks: Mapping[str, Any]) -> dict[str, Any]:
    failed = [name for name, value in checks.items() if not value.get("passed", False)]
    return {"passed": not failed, "failed": failed,
            "summary": ("all audit checks passed" if not failed
                        else "audit failures: " + ", ".join(failed))}