"""Issuer-month panel, labels and point-in-time features for SCIENCE-002.

Observation unit
----------------
One **issuer-month**: firm i, month m. The prediction instant is the last second
of the month's last day in UTC: t = (last day of m) 23:59:59Z. Everything used as
a feature must be publicly available at or before t; the outcome is defined on a
window that *starts* strictly after t.

Outcome
-------
label = 1 iff firm i has at least one **cleared** 510(k) (decision_code SESE,
as published by FDA) whose decision_date falls in (t, t + 90 days].
A row is kept only if the whole window is inside the FDA data maturity cut, so a
partially observed window is never labelled 0.

Feature availability rules (enforced, not assumed)
--------------------------------------------------
* 8-K activity: SEC acceptanceDateTime (UTC instant) must be <= t.
* XBRL facts: the reporting filing's `filed` day must be <= t (day granularity,
  stated as a limitation), and the fact's fiscal period must end <= t.
* Historical clearance counts (the strong baseline): decision_date must be
  <= t - AVAILABILITY_LAG_DAYS. The lag is a conservative stand-in for the
  undocumented FDA database refresh delay (see TIME_SEMANTICS.md; the observed
  dataset-level freshness at the 2026-11 export is <= 10 days, and 30 is used).

No feature is computed from any filing accepted after t, and no feature reads the
outcome window. The panel builder never receives the full label series; labels
are produced by a separate function from the same clearance list.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from . import sec
from .entity import normalise_name
from .sources import Cache

PANEL_START = date(2021, 1, 1)
PANEL_END_MONTH = date(2026, 6, 1)      # last prediction month
FDA_MATURITY_CUT = date(2026, 9, 30)    # windows must close on or before this
HORIZON_DAYS = 90
AVAILABILITY_LAG_DAYS = 30
#: A firm-month is kept only if the registrant's own 8-K history starts at least
#: this far before t, so the trailing-365-day activity counts are complete.
SEC_COVERAGE_MARGIN_DAYS = 400
TRAIN_END = date(2024, 12, 31)
HOLDOUT_START = date(2025, 1, 1)

#: Model ladders. Names are frozen; the protocol refers to these identifiers.
B1_FEATURES = ("clr_rate_365", "clr_rate_730", "months_since_clear")
B2_FEATURES = B1_FEATURES + ("n_8k_90", "n_8k_365", "n_801_90", "n_801_365",
                             "n_202_90", "days_since_8k", "t_years", "month_sin", "month_cos")
B3_FEATURES = B2_FEATURES + ("rd_ttm_log", "rd_yoy", "rd_to_sales", "rd_growth_vol")
B4_FEATURES = B3_FEATURES + ("rd_yoy_lag1", "rd_yoy_lag2", "rd_yoy_lag3", "rd_intensity_rel")

MODEL_FEATURES: dict[str, tuple[str, ...]] = {
    "B0": (),
    "B1": B1_FEATURES,
    "B2": B2_FEATURES,
    "B3": B3_FEATURES,
    "B4": B4_FEATURES,
}


@dataclass
class PanelRow:
    key: str
    ticker: str
    cik: str
    month_end: date
    split: str
    label: int
    n_events_in_window: int
    label_507: int = 0
    label_any8k: int = 0
    features: dict[str, float] = field(default_factory=dict)

    @property
    def t_utc(self) -> datetime:
        return datetime.combine(self.month_end, datetime.max.time()).replace(tzinfo=timezone.utc)


@dataclass
class Panel:
    rows: list[PanelRow]
    meta: dict[str, Any]
    firms: list[str] = field(default_factory=list)
    label_events: list[dict[str, Any]] = field(default_factory=list)

    def feature_names(self, model: str) -> tuple[str, ...]:
        return MODEL_FEATURES[model]

    def complete_case(self, models: Sequence[str]) -> list[PanelRow]:
        needed = set()
        for model in models:
            needed.update(MODEL_FEATURES[model])
        out = []
        for row in self.rows:
            if all(_is_finite(row.features.get(name)) for name in needed):
                out.append(row)
        return out


def _is_finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def month_ends(start: date, end_month: date) -> list[date]:
    out = []
    year, month = start.year, start.month
    while (year, month) <= (end_month.year, end_month.month):
        if month == 12:
            nxt = date(year + 1, 1, 1)
        else:
            nxt = date(year, month + 1, 1)
        out.append(nxt - timedelta(days=1))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


# --------------------------------------------------------------------------- #
# feature blocks
# --------------------------------------------------------------------------- #
def _filing_counts(filings: Iterable[sec.Filing], t: datetime,
                   days: int, item: str | None = None) -> int:
    n = 0
    low = t - timedelta(days=days)
    for filing in filings:
        if filing.acceptance_utc is None or filing.form not in sec.EIGHT_K_FORMS:
            continue
        if not (low < filing.acceptance_utc <= t):
            continue
        if item is not None and not filing.has_item(item):
            continue
        n += 1
    return n


def _days_since_last_filing(filings: Iterable[sec.Filing], t: datetime) -> float:
    best = None
    for filing in filings:
        if filing.acceptance_utc is None or filing.form not in sec.EIGHT_K_FORMS:
            continue
        if filing.acceptance_utc > t:
            continue
        if best is None or filing.acceptance_utc > best:
            best = filing.acceptance_utc
    return float((t - best).days) if best is not None else 3650.0


def clearance_counts(clearances: Sequence[date], t: datetime,
                     lag_days: int = AVAILABILITY_LAG_DAYS) -> dict[str, float]:
    cutoff = (t - timedelta(days=lag_days)).date()
    def count(days: int) -> int:
        low = cutoff - timedelta(days=days)
        return sum(1 for d in clearances if low < d <= cutoff)
    c90, c365, c730 = count(90), count(365), count(730)
    last = max((d for d in clearances if d <= cutoff), default=None)
    months_since = 120.0 if last is None else min(120.0, (cutoff - last).days / 30.4375)
    return {"clr_90": float(c90), "clr_365": float(c365), "clr_730": float(c730),
            "clr_rate_365": (c365 + 1.0) / 3.0, "clr_rate_730": (c730 + 1.0) / 5.0,
            "months_since_clear": float(months_since)}


def _quarterly(facts: Sequence[sec.Fact]) -> list[sec.Fact]:
    return [f for f in facts if 70 <= (f.end - f.start).days <= 110]


def _ttm(facts: Sequence[sec.Fact], asof: date) -> tuple[float | None, list[float]]:
    """Trailing twelve months from the four most recent distinct quarters."""
    quarters = [f for f in _quarterly(facts) if f.end <= asof and f.filed <= asof]
    by_end: dict[date, sec.Fact] = {}
    for fact in quarters:
        current = by_end.get(fact.end)
        if current is None or fact.filed < current.filed:
            by_end[fact.end] = fact
    ends = sorted(by_end)[-4:]
    if len(ends) < 4:
        return None, []
    values = [by_end[end].value for end in ends]
    return float(sum(values)), values


def rd_features(rd: Sequence[sec.Fact], revenue: Sequence[sec.Fact],
                t: datetime) -> dict[str, float]:
    asof = t.date()
    ttm, values = _ttm(rd, asof)
    if ttm is None or ttm <= 0:
        return {}
    prev_asof = asof - timedelta(days=365)
    prev_ttm, _ = _ttm(rd, prev_asof)
    out: dict[str, float] = {"rd_ttm_log": math.log(ttm)}
    growth_series = []
    for lag_months in (0, 3, 6, 9):
        a = asof - timedelta(days=30 * lag_months)
        cur, _ = _ttm(rd, a)
        past, _ = _ttm(rd, a - timedelta(days=365))
        growth_series.append(math.log(cur / past) if (cur and past and cur > 0 and past > 0) else None)
    if growth_series[0] is not None:
        out["rd_yoy"] = growth_series[0]
    for i, name in enumerate(("rd_yoy_lag1", "rd_yoy_lag2", "rd_yoy_lag3")):
        value = growth_series[i + 1]
        if value is not None:
            out[name] = value
    observed = [g for g in growth_series if g is not None]
    if len(observed) >= 2:
        out["rd_growth_vol"] = statistics.pstdev(observed)
    rev_ttm, _ = _ttm(revenue, asof)
    if rev_ttm and rev_ttm > 0:
        intensity = ttm / rev_ttm
        out["rd_to_sales"] = intensity
        hist = []
        for months in (12, 24, 36):
            past_rev, _ = _ttm(revenue, asof - timedelta(days=30 * months))
            past_rd, _ = _ttm(rd, asof - timedelta(days=30 * months))
            if past_rev and past_rev > 0 and past_rd and past_rd > 0:
                hist.append(past_rd / past_rev)
        if hist:
            out["rd_intensity_rel"] = intensity - (sum(hist) / len(hist))
    return out


def base_features(t: datetime) -> dict[str, float]:
    out = {"t_years": (t.date() - PANEL_START).days / 365.25}
    angle = 2.0 * math.pi * (t.month - 1) / 12.0
    out["month_sin"] = math.sin(angle)
    out["month_cos"] = math.cos(angle)
    return out


def filing_window(filings: Sequence[sec.Filing], t: datetime,
                  item: str | None = None, horizon: int = HORIZON_DAYS) -> int:
    high = t + timedelta(days=horizon)
    n = 0
    for filing in filings:
        if filing.acceptance_utc is None or filing.form not in sec.EIGHT_K_FORMS:
            continue
        if not (t < filing.acceptance_utc <= high):
            continue
        if item is not None and not filing.has_item(item):
            continue
        n += 1
    return n


def clearance_window(clearances: Sequence[date], t: datetime,
                     horizon: int = HORIZON_DAYS) -> list[date]:
    low = t.date()
    high = t.date() + timedelta(days=horizon)
    return [d for d in clearances if low < d <= high]


def build_panel(build: Any, clearance_index: Mapping[str, Sequence[date]],
                availability_lag_days: int = AVAILABILITY_LAG_DAYS) -> Panel:
    """Build the issuer-month panel. The lag switch exists for sensitivity S3."""
    rows: list[PanelRow] = []
    label_events: list[dict[str, Any]] = []
    months = month_ends(PANEL_START, PANEL_END_MONTH)
    n_missing_rd = 0
    n_dropped_coverage = 0
    for firm in build.included:
        sub = build.submissions[firm.cik]
        facts = build.facts[firm.cik]
        clearances = sorted(clearance_index.get(firm.cik, ()))
        filing_list = sorted(sub.filings, key=lambda f: (f.filing_date, f.accession))
        first_8k = min((f.acceptance_utc for f in sub.filings
                        if f.acceptance_utc is not None and f.form in sec.EIGHT_K_FORMS),
                       default=None)
        for month_end in months:
            t = datetime.combine(month_end, datetime.max.time()).replace(tzinfo=timezone.utc)
            if month_end + timedelta(days=HORIZON_DAYS) > FDA_MATURITY_CUT:
                continue
            if first_8k is None or first_8k > t - timedelta(days=SEC_COVERAGE_MARGIN_DAYS):
                n_dropped_coverage += 1
                continue
            events = clearance_window(clearances, t)
            split = "train" if month_end <= TRAIN_END else "holdout"
            features: dict[str, float] = {}
            features.update(base_features(t))
            features.update(clearance_counts(clearances, t, availability_lag_days))
            features["n_8k_90"] = float(_filing_counts(filing_list, t, 90))
            features["n_8k_365"] = float(_filing_counts(filing_list, t, 365))
            features["n_801_90"] = float(_filing_counts(filing_list, t, 90, "8.01"))
            features["n_801_365"] = float(_filing_counts(filing_list, t, 365, "8.01"))
            features["n_202_90"] = float(_filing_counts(filing_list, t, 90, "2.02"))
            features["days_since_8k"] = _days_since_last_filing(filing_list, t)
            rd = rd_features(facts.rd, facts.revenue, t)
            if not rd:
                n_missing_rd += 1
            features.update(rd)
            lab507 = filing_window(filing_list, t, "5.07")
            lab_any = filing_window(filing_list, t)
            rows.append(PanelRow(key=firm.key, ticker=firm.ticker, cik=firm.cik,
                                 month_end=month_end, split=split,
                                 label=1 if events else 0, n_events_in_window=len(events),
                                 label_507=1 if lab507 else 0,
                                 label_any8k=1 if lab_any else 0,
                                 features=features))
            if events:
                label_events.append({"key": firm.key, "ticker": firm.ticker,
                                     "month_end": month_end.isoformat(),
                                     "n_events": len(events),
                                     "first_decision": min(events).isoformat()})
    meta = {
        "n_rows": len(rows),
        "n_firms": len(build.included),
        "months": len(months),
        "n_positive": sum(r.label for r in rows),
        "n_missing_rd_feature_rows": n_missing_rd,
        "n_rows_dropped_sec_coverage": n_dropped_coverage,
        "sec_coverage_margin_days": SEC_COVERAGE_MARGIN_DAYS,
        "availability_lag_days": availability_lag_days,
        "fda_maturity_cut": FDA_MATURITY_CUT.isoformat(),
        "panel_start": PANEL_START.isoformat(),
        "panel_end_month": PANEL_END_MONTH.isoformat(),
        "train_end": TRAIN_END.isoformat(),
        "holdout_start": HOLDOUT_START.isoformat(),
        "horizon_days": HORIZON_DAYS,
    }
    p = Panel(rows=rows, meta=meta, firms=sorted({r.key for r in rows}),
              label_events=label_events)
    p.meta["by_split"] = _split_summary(p)
    return p


def _split_summary(p: Panel) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for split in ("train", "holdout"):
        rows = [r for r in p.rows if r.split == split]
        out[split] = {"n": len(rows), "positive": sum(r.label for r in rows),
                      "prevalence": (sum(r.label for r in rows) / len(rows)) if rows else None,
                      "firms": len({r.key for r in rows})}
    return out