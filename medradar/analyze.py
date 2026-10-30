"""Metrics engine: SQLite facts -> ``out/metrics.json`` (contract: docs/SCHEMA.md).

Design notes
------------
* **One event table in, one JSON out.** Collectors know nothing about metrics;
  the report and the trading study know nothing about SQL. This file is the
  only place where "what happened" becomes "what it means".
* **Shrink before you shout.** A company with two 510(k) clearances this
  quarter has an infinite growth rate and no information. Every rate is
  therefore a Gamma-Poisson posterior: the company's (or track's) own baseline
  rate is the prior with strength ``PRIOR_STRENGTH_QUARTERS`` quarters, so
  "THI = 4.8" means "even after assuming no change, the evidence still says
  4.8x".
* **Determinism.** Bootstrap seeds are fixed, rounding is explicit, so the same
  database always renders the same report.
* **Honest gaps.** Unmapped product codes and unmatched applicants are counted
  and surfaced, never silently dropped. China-gap values stay ``None`` when no
  Chinese data is loaded.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any, Iterable

from .config import OUT_DIR, load_companies, load_tracks
from .util import (
    bootstrap_ci,
    gamma_poisson,
    iso,
    js_divergence,
    normalize_dist,
    parse_date,
    prob_rate_above,
    quarter_index,
    quarter_label,
    quarter_start,
    read_json,
    share,
    summarize,
    t_stat,
    today_utc,
    utc_now_iso,
)

DEVICE_ACTIVITY_KINDS = ("510k", "pma")
DEVICE_KINDS = ("510k", "pma", "device_recall")
DRUG_KINDS = ("drug_approval",)
TRIAL_KINDS = ("trial",)
PRIOR_STRENGTH_QUARTERS = 3.0
MAX_SIGNALS = 400
UNTRACKED = "__untracked__"


# --------------------------------------------------------------------------- helpers
def _parse_payload(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("payload")
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _load_events(db, kinds: Iterable[str] | None = None) -> list[dict[str, Any]]:
    sql = (
        "SELECT event_id, kind, source, event_date, as_of, available_at, timestamp_quality,"
        " company_key, track_id, product_code, applicant_raw, title, summary, payload"
        " FROM events"
        " WHERE event_date IS NOT NULL AND event_date != ''"
    )
    params: list[Any] = []
    if kinds:
        kinds = tuple(kinds)
        sql += " AND kind IN (%s)" % ",".join("?" * len(kinds))
        params = list(kinds)
    rows = db.query(sql, params)
    for row in rows:
        row["_day"] = parse_date(row["event_date"])
        # The backtest may only use what was publicly available. Older databases
        # fall back to the event date and are marked as estimated quality.
        row["_available_day"] = parse_date(row.get("available_at")) or row["_day"]
        quality = str(row.get("timestamp_quality") or "estimated").lower()
        row["timestamp_quality"] = quality if quality in ("datetime", "date", "estimated", "unknown") else "unknown"
    return [row for row in rows if row["_day"]]


def _resolve_window(
    events: list[dict[str, Any]],
    window_quarters: int,
    baseline_quarters: int,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or today_utc()
    latest = max((event["_day"] for event in events), default=today)
    earliest = min((event["_day"] for event in events), default=latest)
    end = min(latest, today)
    end_idx = quarter_index(end)
    win_start_idx = end_idx - window_quarters + 1
    base_end_idx = win_start_idx - 1
    base_start_idx = base_end_idx - baseline_quarters + 1
    # Exposure must be what the data actually covers. Dividing a 24-month pull
    # by a nominal 20-quarter baseline is how naive FDA dashboards manufacture
    # "40x growth" out of a single clearance.
    data_q = quarter_index(earliest)
    observed_recent_q = max(1, end_idx - max(win_start_idx, data_q) + 1)
    observed_base_q = max(0, base_end_idx - max(base_start_idx, data_q) + 1)
    return {
        "end": end,
        "window_start": quarter_start(win_start_idx),
        "baseline_start": quarter_start(base_start_idx),
        "baseline_end": quarter_start(win_start_idx) - timedelta(days=1),
        "window_quarters": window_quarters,
        "baseline_quarters": baseline_quarters,
        "recent_q": observed_recent_q,
        "base_q": observed_base_q,
        "data_start": earliest,
        "window_label": f"{quarter_label(win_start_idx)}-{quarter_label(end_idx)}",
        "baseline_label": f"{quarter_label(base_start_idx)}-{quarter_label(base_end_idx)}",
    }


def _split(events: list[dict[str, Any]], win: dict[str, Any]) -> tuple[list, list]:
    recent = [e for e in events if win["window_start"] <= e["_day"] <= win["end"]]
    base = [e for e in events if win["baseline_start"] <= e["_day"] < win["window_start"]]
    return recent, base


def _base_exposure(win: dict[str, Any]) -> int:
    """Observed baseline quarters - never the nominal window."""
    return max(1, int(win.get("base_q") or 0))


def _rate_metric(
    count_recent: int,
    count_base: int,
    win: dict[str, Any],
    fallback_prior: float,
) -> dict[str, Any]:
    """Gamma-Poisson posterior rate ratio ("THI") and P(rate > baseline)."""
    recent_q = max(1, int(win.get("recent_q") or win["window_quarters"]))
    base_q = int(win.get("base_q") or 0)
    recent_per_q = count_recent / recent_q
    base_per_q = (count_base / base_q) if base_q > 0 else 0.0
    emerging = base_per_q <= 0.0
    reference = base_per_q if base_per_q > 0 else max(fallback_prior, 1e-6)
    post = gamma_poisson(count_recent, recent_q, reference, PRIOR_STRENGTH_QUARTERS)
    thi = post["mean"] / reference if reference > 0 else None
    prob_up = (
        prob_rate_above(
            count_recent, recent_q, reference, PRIOR_STRENGTH_QUARTERS, reference
        )
        if reference > 0
        else None
    )
    return {
        "recent": count_recent,
        "recent_per_q": round(recent_per_q, 3),
        "baseline_per_q": round(base_per_q, 3),
        "thi": round(thi, 2) if thi is not None else None,
        "prob_up": round(prob_up, 3) if prob_up is not None else None,
        "ci": (
            [round(post["lo"] / reference, 2), round(post["hi"] / reference, 2)]
            if reference > 0
            else None
        ),
        "emerging": emerging,
    }


def _company_meta(reg, key: str | None) -> dict[str, Any]:
    entry = reg.get(key) if key else None
    if not entry:
        return {"key": key, "name_zh": key or "未匹配", "ticker": ""}
    return {
        "key": key,
        "name_en": entry.get("name_en", ""),
        "name_zh": entry.get("name_zh") or entry.get("name_en", key),
        "ticker": entry.get("ticker", ""),
        "is_major": bool(entry.get("is_major", 0)),
    }


def _track_meta(tracks, track_id: str | None) -> dict[str, Any]:
    entry = tracks.get(track_id) if track_id and track_id != UNTRACKED else None
    if not entry:
        return {"track_id": UNTRACKED, "name_zh": "未分类（产品码未映射）", "name_en": "Unmapped"}
    return {
        "track_id": track_id,
        "name_zh": entry.get("name_zh") or track_id,
        "name_en": entry.get("name_en", ""),
    }


def _first_occurrence(
    events: list[dict[str, Any]],
    key_fields: tuple[str, ...],
    day_key: str = "_day",
) -> dict[tuple, date]:
    first: dict[tuple, date] = {}
    for event in sorted(events, key=lambda item: item.get(day_key) or item["_day"]):
        key = tuple((event.get(field) or "") for field in key_fields)
        if key not in first:
            first[key] = event.get(day_key) or event["_day"]
    return first


def _phases(event: dict[str, Any]) -> list[str]:
    payload = _parse_payload(event)
    raw = payload.get("phase") or payload.get("phases") or []
    if isinstance(raw, str):
        raw = [raw]
    values = []
    for item in raw if isinstance(raw, list) else []:
        text = str(item).upper().replace("PHASE ", "PHASE").replace("-", "")
        if text:
            values.append(text)
    return values


def _is_nme(payload: dict[str, Any]) -> bool:
    codes = []
    direct = payload.get("submission_class_code")
    if direct:
        codes.append(str(direct))
    for submission in payload.get("submissions") or []:
        if isinstance(submission, dict) and submission.get("submission_class_code"):
            codes.append(str(submission["submission_class_code"]))
    return any("TYPE 1" in code.upper() for code in codes)


def _is_material_pma(event: dict[str, Any]) -> bool:
    """Only PMA submissions that actually reveal product direction.

    Measured on 24 months of data: 30-Day Notice (2,979), Real-Time Process
    (565) and 135-Review-Track-30-Day (179) supplements account for ~78% of all
    PMA rows, and they are manufacturing / labelling / packaging changes. A
    factory relocation must not look like a strategic bet, so activity counts
    original PMAs and Panel-Track supplements only.
    """
    payload = _parse_payload(event)
    number = str(payload.get("supplement_number") or "").strip().upper()
    supplement_type = str(payload.get("supplement_type") or "").strip().upper()
    if number in ("", "0", "S0"):
        return True
    return "PANEL TRACK" in supplement_type


def _device_activity(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if event["kind"] == "510k" or (event["kind"] == "pma" and _is_material_pma(event))
    ]


def _dedupe_recalls(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One recall event often spans several product records; count it once."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for event in events:
        payload = _parse_payload(event)
        key = (
            payload.get("res_event_number")
            or payload.get("product_res_number")
            or event["event_id"]
        )
        key = str(key)
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique


# --------------------------------------------------------------------- device block
def _device_section(events, reg, tracks, win) -> dict[str, Any]:
    activity = _device_activity(events)
    recent, base = _split(activity, win)
    recalls = _dedupe_recalls([e for e in events if e["kind"] == "device_recall"])
    recall_recent, recall_base = _split(recalls, win)

    recent_by_track = Counter(e["track_id"] or UNTRACKED for e in recent)
    base_by_track = Counter(e["track_id"] or UNTRACKED for e in base)
    base_rates = [base_by_track[t] / _base_exposure(win) for t in base_by_track if t != UNTRACKED]
    typical_track_rate = (sum(base_rates) / len(base_rates)) if base_rates else 0.5

    first_track_seen = _first_occurrence(activity, ("company_key", "track_id"))
    cutoff_12m = win["end"] - timedelta(days=365)
    recent_recalls_by_track = Counter(e["track_id"] or UNTRACKED for e in recall_recent)
    major_recent_by_track = Counter(
        e["track_id"] or UNTRACKED for e in recent if _is_major_company(reg, e)
    )
    major_base_by_track = Counter(
        e["track_id"] or UNTRACKED for e in base if _is_major_company(reg, e)
    )

    track_rows = []
    for track_id in set(recent_by_track) | set(base_by_track):
        if track_id == UNTRACKED:
            continue
        meta = _track_meta(tracks, track_id)
        row = dict(meta)
        row.update(_rate_metric(recent_by_track[track_id], base_by_track[track_id], win, typical_track_rate))
        row["recalls_recent"] = recent_recalls_by_track.get(track_id, 0)
        track_recent = recent_by_track[track_id]
        track_base = base_by_track[track_id]
        row["major_share_recent"] = (
            round(share(major_recent_by_track.get(track_id, 0), track_recent), 3)
            if track_recent
            else 0.0
        )
        row["major_share_base"] = (
            round(share(major_base_by_track.get(track_id, 0), track_base), 3)
            if track_base
            else 0.0
        )
        row["new_entrants_12m"] = sum(
            1
            for (company, track), day in first_track_seen.items()
            if track == track_id and day >= cutoff_12m
        )
        track_rows.append(row)

    track_rows.sort(key=lambda r: (r["thi"] is None, -(r["thi"] or 0), -r["recent"]))
    for rank, row in enumerate(track_rows, start=1):
        row["rank"] = rank

    # ---- company momentum
    activity_by_company = [e for e in activity if e["company_key"]]
    recent_c, base_c = _split(activity_by_company, win)
    recent_by_company = Counter(e["company_key"] for e in recent_c)
    base_by_company = Counter(e["company_key"] for e in base_c)
    company_base_rates = [
        base_by_company[k] / _base_exposure(win) for k in base_by_company
    ]
    typical_company_rate = (
        sum(company_base_rates) / len(company_base_rates) if company_base_rates else 1.0
    )
    first_code_seen = _first_occurrence(
        [e for e in activity_by_company if e["product_code"]], ("company_key", "product_code")
    )
    recall_by_company = Counter(e["company_key"] for e in recall_recent if e["company_key"])

    company_rows = []
    for key in set(recent_by_company) | set(base_by_company):
        meta = _company_meta(reg, key)
        row = dict(meta)
        row.update(
            _rate_metric(recent_by_company[key], base_by_company[key], win, typical_company_rate)
        )
        company_recent = [e for e in recent_c if e["company_key"] == key]
        shares = normalize_dist(Counter(e["track_id"] or UNTRACKED for e in company_recent))
        ordered = sorted(shares.items(), key=lambda pair: pair[1], reverse=True)
        row["top_tracks"] = [[track, round(value, 3)] for track, value in ordered[:3]]
        row["novelty_12m"] = sum(
            1
            for (company, _code), day in first_code_seen.items()
            if company == key and day >= cutoff_12m
        )
        row["recalls_recent"] = recall_by_company.get(key, 0)
        company_rows.append(row)

    company_rows.sort(key=lambda r: (r["thi"] is None, -(r["thi"] or 0), -r["recent"]))
    for rank, row in enumerate(company_rows, start=1):
        row["rank"] = rank

    # ---- portfolio migration
    migration = []
    for key in set(recent_by_company) | set(base_by_company):
        company_recent = [e for e in recent_c if e["company_key"] == key]
        company_base = [e for e in base_c if e["company_key"] == key]
        if len(company_recent) < 4 or len(company_base) < 2:
            continue
        shares_recent = normalize_dist(Counter(e["track_id"] or UNTRACKED for e in company_recent))
        shares_base = normalize_dist(Counter(e["track_id"] or UNTRACKED for e in company_base))
        distance = js_divergence(shares_recent, shares_base)
        deltas = []
        for track_id in set(shares_recent) | set(shares_base):
            delta = shares_recent.get(track_id, 0.0) - shares_base.get(track_id, 0.0)
            if abs(delta) >= 0.08 and track_id != UNTRACKED:
                deltas.append((track_id, delta))
        for track_id, delta in sorted(deltas, key=lambda pair: abs(pair[1]), reverse=True)[:2]:
            meta = _company_meta(reg, key)
            track_meta = _track_meta(tracks, track_id)
            migration.append(
                {
                    "key": key,
                    "name_zh": meta["name_zh"],
                    "track_id": track_id,
                    "track_zh": track_meta["name_zh"],
                    "share_recent": round(shares_recent.get(track_id, 0.0), 3),
                    "share_base": round(shares_base.get(track_id, 0.0), 3),
                    "delta": round(delta, 3),
                    "js": round(distance, 4),
                }
            )
    migration.sort(key=lambda row: (-row["js"], -abs(row["delta"])))
    migration = migration[:20]

    # ---- first seen (last 90 days)
    cutoff_90 = win["end"] - timedelta(days=90)
    seen_code = _first_occurrence(
        [e for e in activity_by_company if e["product_code"]], ("company_key", "product_code")
    )
    firstseen = []
    for event in sorted(activity_by_company, key=lambda item: item["_day"], reverse=True):
        if event["_day"] < cutoff_90:
            continue
        if event["product_code"]:
            if seen_code.get((event["company_key"], event["product_code"])) != event["_day"]:
                continue
        meta = _company_meta(reg, event["company_key"])
        track_meta = _track_meta(tracks, event["track_id"])
        firstseen.append(
            {
                "event_date": iso(event["_day"]),
                "event_id": event["event_id"],
                "key": meta["key"],
                "name_zh": meta["name_zh"],
                "track_id": track_meta["track_id"],
                "track_zh": track_meta["name_zh"],
                "product_code": event["product_code"] or "",
                "device_name": event["title"] or "",
                "title": event["title"] or "",
            }
        )
        if len(firstseen) >= 40:
            break

    # ---- recall clusters
    recall_rows = []
    base_recall_by_company = Counter(e["company_key"] for e in recall_base if e["company_key"])
    for key, count in recall_by_company.most_common(10):
        if count < 2:
            continue
        meta = _company_meta(reg, key)
        reasons = Counter()
        for event in recall_recent:
            if event["company_key"] != key:
                continue
            payload = _parse_payload(event)
            reason = (
                payload.get("reason_for_recall")
                or payload.get("reason_top")
                or ""
            )
            if reason:
                reasons[str(reason)[:60]] += 1
        recall_rows.append(
            {
                "key": key,
                "name_zh": meta["name_zh"],
                "recent": count,
                "baseline_per_q": round(base_recall_by_company.get(key, 0) / _base_exposure(win), 2),
                "reason_top": (reasons.most_common(1)[0][0] if reasons else ""),
            }
        )

    return {
        "tracks": track_rows[:24],
        "companies": company_rows[:24],
        "migration": migration,
        "firstseen": firstseen[:30],
        "recalls": recall_rows,
        "coverage": {
            "events": len(activity),
            "unmapped_track_events": sum(1 for e in activity if not e["track_id"]),
            "unmapped_company_events": sum(1 for e in activity if not e["company_key"]),
        },
    }


def _is_major_company(reg, event: dict[str, Any]) -> bool:
    entry = reg.get(event.get("company_key"))
    return bool(entry and entry.get("is_major"))


# ----------------------------------------------------------------------- drug block
def _drug_section(events, reg, tracks, win) -> dict[str, Any]:
    approvals = [e for e in events if e["kind"] in DRUG_KINDS and e["company_key"]]
    recent, base = _split(approvals, win)
    recent_by_company = Counter(e["company_key"] for e in recent)
    base_by_company = Counter(e["company_key"] for e in base)
    base_rates = [base_by_company[k] / _base_exposure(win) for k in base_by_company]
    typical = sum(base_rates) / len(base_rates) if base_rates else 0.5

    approval_rows = []
    for key in set(recent_by_company) | set(base_by_company):
        meta = _company_meta(reg, key)
        row = dict(meta)
        row.update(_rate_metric(recent_by_company[key], base_by_company[key], win, typical))
        row["nme_recent"] = sum(
            1
            for event in recent
            if event["company_key"] == key and _is_nme(_parse_payload(event))
        )
        approval_rows.append(row)
    approval_rows.sort(key=lambda r: (r["thi"] is None, -(r["thi"] or 0), -r["recent"]))

    # therapeutic areas from trial registrations (leading indicator)
    trials = [e for e in events if e["kind"] in TRIAL_KINDS]
    trials_recent, trials_base = _split(trials, win)
    area_recent = Counter(e["track_id"] for e in trials_recent if e["track_id"])
    area_base = Counter(e["track_id"] for e in trials_base if e["track_id"])
    area_rates = [area_base[t] / _base_exposure(win) for t in area_base]
    typical_area = sum(area_rates) / len(area_rates) if area_rates else 1.0
    area_rows = []
    for track_id, count in area_recent.most_common(30):
        meta = _track_meta(tracks, track_id)
        row = dict(meta)
        row.update(_rate_metric(count, area_base.get(track_id, 0), win, typical_area))
        area_rows.append(row)
    area_rows.sort(key=lambda r: (r["thi"] is None, -(r["thi"] or 0), -r["recent"]))

    # company trial starts + phase mix
    trial_by_company_recent = Counter(e["company_key"] for e in trials_recent if e["company_key"])
    trial_by_company_base = Counter(e["company_key"] for e in trials_base if e["company_key"])
    company_rates = [
        trial_by_company_base[k] / _base_exposure(win) for k in trial_by_company_base
    ]
    typical_trial = sum(company_rates) / len(company_rates) if company_rates else 1.0
    trial_rows = []
    for key in set(trial_by_company_recent) | set(trial_by_company_base):
        if trial_by_company_recent.get(key, 0) + trial_by_company_base.get(key, 0) < 2:
            continue
        meta = _company_meta(reg, key)
        row = dict(meta)
        row.update(
            _rate_metric(
                trial_by_company_recent.get(key, 0),
                trial_by_company_base.get(key, 0),
                win,
                typical_trial,
            )
        )
        phase_counter: Counter[str] = Counter()
        for event in trials_recent:
            if event["company_key"] == key:
                for phase in _phases(event):
                    phase_counter[phase] += 1
        total_phases = sum(phase_counter.values()) or 1
        row["phase_mix"] = {
            phase: round(count / total_phases, 3)
            for phase, count in sorted(phase_counter.items())
        }
        trial_rows.append(row)
    trial_rows.sort(key=lambda r: (r["thi"] is None, -(r["thi"] or 0), -r["recent"]))

    return {
        "approvals": approval_rows[:24],
        "areas": area_rows[:20],
        "trials": trial_rows[:24],
        "coverage": {"approvals": len(approvals), "trials": len(trials)},
    }


# ------------------------------------------------------------------------- cn gap
def _cn_gap(events, tracks, win) -> tuple[list[dict[str, Any]], str]:
    """US activity vs loaded Chinese registrations, per track.

    Returns ``(rows, status)`` where status is ``loaded`` (real NMPA CSV),
    ``demo`` (clearly-labelled demo seed) or ``unavailable``. When no Chinese
    data exists every CN value is ``None`` - never 0.
    """
    device_recent, _ = _split(_device_activity(events), win)
    us_by_track = Counter(e["track_id"] for e in device_recent if e["track_id"])
    cn_events = [
        e
        for e in events
        if e["kind"] == "nmpa_registration"
        or e["source"] in ("nmpa", "nmpa_demo")
    ]
    cn_by_track = Counter(e["track_id"] for e in cn_events if e["track_id"])
    if any(e["source"] == "nmpa" for e in cn_events):
        cn_status = "loaded"
    elif cn_events:
        cn_status = "demo"
    else:
        cn_status = "unavailable"

    us_total = sum(us_by_track.values()) or 1
    cn_total = sum(cn_by_track.values())
    rows = []
    for track_id, count in us_by_track.most_common(24):
        meta = _track_meta(tracks, track_id)
        row = dict(meta)
        row["us_recent"] = count
        row["us_share"] = round(share(count, us_total), 4)
        if cn_status == "unavailable":
            row.update(
                {
                    "cn_count": None,
                    "cn_share": None,
                    "gap_index": None,
                    "cn_data_status": "unavailable",
                }
            )
        else:
            cn_count = cn_by_track.get(track_id, 0)
            cn_share_value = share(cn_count, cn_total) if cn_total else 0.0
            row.update(
                {
                    "cn_count": cn_count,
                    "cn_share": round(cn_share_value, 4),
                    "gap_index": round(row["us_share"] - cn_share_value, 4),
                    "cn_data_status": cn_status,
                }
            )
        rows.append(row)
    return rows, cn_status


# ------------------------------------------------------------------------- signals
def _signals(
    events,
    device_reg,
    drug_reg,
    device_tracks,
    drug_tracks,
    win,
) -> list[dict[str, Any]]:
    """Turn notable events into dated, direction-tagged candidates.

    Everything here is point-in-time: the signal date is the day *after* the
    event became publicly available, and the "is this new?" test uses only
    history up to that availability date. The old version boosted scores with a
    track THI computed over the whole window, which quietly used future data.
    """
    signals: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    import bisect

    def registries_for(kind: str):
        if kind in ("drug_approval", "trial"):
            return drug_reg, drug_tracks
        return device_reg, device_tracks

    def avail(event: dict[str, Any]) -> date:
        return event.get("_available_day") or event["_day"]

    activity = [event for event in _device_activity(events) if event["company_key"]]
    # Point-in-time track popularity: how many events did this track already have
    # in the 180 days *before* this one became public? No future data involved.
    track_days: dict[str, list[date]] = {}
    for event in activity:
        if event.get("track_id"):
            track_days.setdefault(event["track_id"], []).append(avail(event))
    for days in track_days.values():
        days.sort()

    def prior_track_count(track_id: str | None, day: date) -> int:
        days = track_days.get(track_id or "")
        if not days:
            return 0
        low = bisect.bisect_left(days, day - timedelta(days=180))
        high = bisect.bisect_right(days, day)
        return max(0, high - low)

    def add(event, kind, direction, score, reason):
        key = (event.get("company_key"), kind, event.get("track_id"), iso(avail(event)))
        if key in seen:
            return
        seen.add(key)
        reg, tracks = registries_for(kind)
        meta = _company_meta(reg, event.get("company_key"))
        track_meta = _track_meta(tracks, event.get("track_id"))
        signals.append(
            {
                "signal_id": f"sig-{len(signals)+1:04d}",
                "event_id": event["event_id"],
                "signal_date": iso(avail(event) + timedelta(days=1)),
                "available_at": iso(avail(event)),
                "timestamp_quality": event.get("timestamp_quality") or "estimated",
                "company_key": event.get("company_key"),
                "name_zh": meta["name_zh"],
                "ticker": meta.get("ticker", ""),
                "kind": kind,
                "direction": direction,
                "score": round(score, 3),
                "track_id": event.get("track_id"),
                "track_zh": track_meta["name_zh"],
                "reason_zh": reason,
            }
        )

    cutoff_180 = win["end"] - timedelta(days=180)
    first_code = _first_occurrence(
        [e for e in activity if e["product_code"]], ("company_key", "product_code"), "_available_day"
    )
    first_track = _first_occurrence(activity, ("company_key", "track_id"), "_available_day")

    for event in sorted(activity, key=lambda item: avail(item), reverse=True):
        if avail(event) < cutoff_180:
            break
        code = event.get("product_code")
        is_new_code = code and first_code.get((event["company_key"], code)) == avail(event)
        is_new_track = first_track.get((event["company_key"], event["track_id"])) == avail(event)
        if not (is_new_code or is_new_track):
            continue
        track_meta = _track_meta(device_tracks, event["track_id"])
        prior = prior_track_count(event["track_id"], avail(event))
        boost = min(0.2, 0.02 * prior)
        if is_new_code:
            add(
                event,
                "device_novel_code",
                1,
                min(0.9, 0.55 + boost),
                f"首次出现产品码 {code}（{track_meta['name_zh']}）",
            )
        else:
            add(
                event,
                "device_new_track",
                1,
                min(0.85, 0.5 + boost),
                f"首次进入赛道「{track_meta['name_zh']}」",
            )

    for event in sorted([e for e in events if e["kind"] == "drug_approval"], key=lambda item: avail(item), reverse=True):
        if avail(event) < win["end"] - timedelta(days=365):
            break
        if not event["company_key"]:
            continue
        nme = _is_nme(_parse_payload(event))
        add(
            event,
            "drug_approval",
            1,
            0.72 if nme else 0.6,
            ("新分子实体获批：" if nme else "原始申请获批：") + (event["title"] or ""),
        )

    for event in sorted([e for e in events if e["kind"] == "trial"], key=lambda item: avail(item), reverse=True):
        if avail(event) < win["end"] - timedelta(days=180):
            break
        if not event["company_key"] or "PHASE3" not in _phases(event):
            continue
        track_meta = _track_meta(drug_tracks, event["track_id"])
        add(event, "trial_start", 1, 0.5, f"III 期试验启动（{track_meta['name_zh']}）")

    recall_by_company = Counter(
        e["company_key"]
        for e in _dedupe_recalls([event for event in events if event["kind"] == "device_recall"])
        if e["company_key"] and (e.get("_available_day") or e["_day"]) >= win["end"] - timedelta(days=90)
    )
    for key, count in recall_by_company.items():
        if count < 2:
            continue
        latest = max(
            (e for e in events if e["kind"] == "device_recall" and e["company_key"] == key),
            key=lambda item: item["_day"],
        )
        add(latest, "recall_cluster", -1, 0.7, f"90 天内 {count} 起召回")

    signals.sort(key=lambda row: row["signal_date"], reverse=True)
    return signals[:MAX_SIGNALS]


# -------------------------------------------------------------------------- alerts
def _alerts(device, drug, cn_gap) -> dict[str, Any]:
    accelerating = [
        {
            "track_id": row["track_id"],
            "name_zh": row["name_zh"],
            "thi": row["thi"],
            "prob_up": row["prob_up"],
            "recent": row["recent"],
        }
        for row in device["tracks"]
        if row.get("thi") and row["thi"] >= 1.4 and (row.get("prob_up") or 0) >= 0.85
    ][:6]
    movers = [
        {
            "key": row["key"],
            "name_zh": row["name_zh"],
            "thi": row["thi"],
            "recent": row["recent"],
            "novelty_12m": row["novelty_12m"],
        }
        for row in device["companies"]
        if row.get("thi") and row["thi"] >= 1.3
    ][:6]
    return {
        "accelerating_tracks": accelerating,
        "company_movers": movers,
        "new_entries": device["firstseen"][:8],
        "recall_clusters": [
            {"key": row["key"], "name_zh": row["name_zh"], "recent": row["recent"]}
            for row in device["recalls"][:5]
        ],
        "cn_gap_top": [row for row in cn_gap[:5] if row.get("gap_index") is not None],
    }


# -------------------------------------------------------------------------- research
def _research_block(db, events, device, win, signals) -> dict[str, Any]:
    """Sample split + multiple-testing correction + survivorship flags.

    Kept best-effort: if ``medradar.stats`` is unavailable the block is omitted
    rather than breaking the whole analysis.
    """
    try:
        from .stats import multiple_testing, survivorship_flags, time_split_by_dates
    except Exception:  # pragma: no cover - stats is part of the package
        return {}

    holdout_start = win["end"] - timedelta(days=365)
    validation_start = holdout_start - timedelta(days=365)
    items = [{"event_date": iso(event["_day"]), "kind": event["kind"]} for event in events]
    split: dict[str, Any] = {}
    try:
        split = time_split_by_dates(
            items,
            dev_end=iso(validation_start - timedelta(days=1)),
            validation_end=iso(holdout_start - timedelta(days=1)),
        )
    except Exception:
        split = {}

    p_values = []
    labels = []
    for row in device.get("tracks") or []:
        prob_up = row.get("prob_up")
        if prob_up is None:
            continue
        p_values.append(max(0.0, min(1.0, 1.0 - float(prob_up))))
        labels.append(row.get("track_id") or "")
    testing: dict[str, Any] = {}
    if p_values:
        try:
            testing = multiple_testing(p_values, method="holm", labels=labels)
        except Exception:
            testing = {}

    # Survivorship is a number we can actually compute: a signal whose ticker has
    # no price coverage in the local store cannot enter the return study. Reporting
    # a hard-coded 0 would be a fake zero.
    survivorship: dict[str, Any] = {
        "flagged": 0,
        "note": "免费行情源不含完整退市收益；退市/并购标的单独标注，不静默剔除",
    }
    try:
        price_tickers = {
            row["ticker"] for row in db.query("SELECT DISTINCT ticker FROM prices")
        }
        universe = [
            {"ticker": signal.get("ticker"), "key": signal.get("company_key")}
            for signal in signals
            if signal.get("ticker")
        ]
        if universe and price_tickers:
            flags = survivorship_flags(
                universe, price_tickers=price_tickers, window_end=iso(win["end"])
            )
            survivorship.update(
                {
                    "flagged": int(flags.get("flagged") or 0),
                    "reasons": flags.get("reasons") or flags.get("by_reason") or {},
                    "note": flags.get("note") or survivorship["note"],
                }
            )
    except Exception:
        pass

    return {
        "sample_split": split,
        "multiple_testing": testing,
        "survivorship": survivorship,
    }


# ------------------------------------------------------------------- optional blocks
def _compact_cases(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Trim the case library for the report (keeps metrics.json readable)."""
    return {
        "status": payload.get("status"),
        "benchmark": payload.get("benchmark"),
        "window": payload.get("window"),
        "stats": payload.get("stats") or {},
        "selected": list(payload.get("selected") or [])[:30],
        "negative_examples": list(payload.get("negative_examples") or [])[:6],
    }


def _compact_replay(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Trim the replay payload to what the report needs (keeps metrics.json small)."""
    steps = list(payload.get("steps") or [])[:60]
    return {
        "status": payload.get("status"),
        "window": payload.get("window"),
        "method": payload.get("method"),
        "assumptions_url": payload.get("assumptions_url") or "docs/ASSUMPTIONS.md",
        "summary_by_cost": payload.get("summary_by_cost") or {},
        "event_study": payload.get("event_study") or {},
        "skipped": payload.get("skipped") or {},
        "steps": steps,
        "disclaimer_zh": payload.get("disclaimer_zh"),
    }


def _products_block(db, win) -> dict[str, Any]:
    """Product-family intelligence; best-effort so a missing module never breaks analyze."""
    try:
        from .products import company_portfolio, family_stats, new_products
    except Exception:
        return {}
    try:
        families = family_stats(db, window_quarters=win["window_quarters"])
    except Exception:
        return {}
    try:
        news = new_products(db, days=90, max_items=200)
    except Exception:
        news = []
    try:
        portfolio = company_portfolio(db, window_quarters=win["window_quarters"])
    except Exception:
        portfolio = {}

    def short(value: Any, limit: int = 200) -> str:
        text = str(value or "").strip()
        return text if len(text) <= limit else text[: limit - 1] + "…"

    news_rows = [
        {
            "date": item.get("event_date"),
            "event_id": item.get("event_id"),
            "company_zh": item.get("name_zh") or item.get("company_key") or "",
            "ticker": item.get("ticker") or "",
            "family_id": item.get("family_id") or "",
            "family_zh": item.get("family_zh") or "",
            "code": item.get("product_code") or "",
            "device_name_zh": short(item.get("product_name_zh"), 120),
            "definition_zh": short(item.get("product_definition_zh"), 240),
            "kind": item.get("kind") or "",
            "k_number": item.get("number") or "",
            "url": item.get("url") or "",
            "title": short(item.get("title"), 160),
        }
        for item in (news or [])
    ]
    portfolio_rows = []
    for value in (portfolio or {}).values():
        top = []
        for entry in value.get("top_families") or []:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                top.append([entry[2] if len(entry) > 2 else str(entry[0]), round(float(entry[1]), 3)])
        portfolio_rows.append(
            {
                "company_zh": value.get("name_zh") or value.get("key") or "",
                "ticker": value.get("ticker") or "",
                "recent": value.get("recent") or 0,
                "family_count": value.get("family_count") or 0,
                "new_families_12m": value.get("new_families_12m") or 0,
                "top_families": top[:5],
                "js_shift": value.get("js") or 0.0,
            }
        )
    portfolio_rows.sort(key=lambda row: (-row["recent"], row["company_zh"]))

    total_recent = sum(float(row.get("recent") or 0) for row in families) or 1.0
    top20_recent = sum(float(row.get("recent") or 0) for row in families[:20])
    return {
        "families": families[:60],
        "new_products": news_rows[:60],
        "company_portfolio": portfolio_rows[:40],
        "coverage": {
            "families": len(families),
            "top20_event_share": round(top20_recent / total_recent, 4),
            "new_products_90d": len(news_rows),
        },
    }


# --------------------------------------------------------------------------- build
def build_metrics(
    db,
    window_quarters: int = 8,
    baseline_quarters: int = 20,
    today: date | None = None,
) -> dict[str, Any]:
    all_events = _load_events(db)
    device_events = [e for e in all_events if e["kind"] in DEVICE_KINDS]
    drug_events = [e for e in all_events if e["kind"] in DRUG_KINDS + TRIAL_KINDS]
    win = _resolve_window(all_events, window_quarters, baseline_quarters, today)

    device_reg = load_companies("device")
    drug_reg = load_companies("drug")
    device_tracks = load_tracks("device")
    drug_tracks = load_tracks("drug")

    device = _device_section(device_events, device_reg, device_tracks, win)
    drug = _drug_section(drug_events, drug_reg, drug_tracks, win)
    cn_gap, cn_status = _cn_gap(all_events, device_tracks, win)
    signals = _signals(
        device_events + drug_events,
        device_reg,
        drug_reg,
        device_tracks,
        drug_tracks,
        win,
    )
    alerts = _alerts(device, drug, cn_gap)

    quality_counts = Counter(event.get("timestamp_quality") or "unknown" for event in all_events)
    excluded_from_trading = sum(
        1 for event in all_events if (event.get("timestamp_quality") or "unknown") in ("unknown",)
    )
    timestamps = {
        "by_quality": {key: int(value) for key, value in quality_counts.items()},
        "excluded_from_trading": excluded_from_trading,
        "policy": "回测只使用 available_at；quality=unknown 的事件不进入交易研究",
    }

    counts = {
        row["kind"]: row["n"]
        for row in db.query("SELECT kind, COUNT(*) AS n FROM events GROUP BY kind")
    }
    data_status = {
        "device": "ok" if device["coverage"]["events"] else "empty",
        "drug": "ok" if drug["coverage"]["approvals"] else "empty",
        "trials": "ok" if drug["coverage"]["trials"] else "empty",
        "nmpa": cn_status,
        "prices": "ok" if db.table_count("prices") else "missing",
    }

    metrics: dict[str, Any] = {
        "meta": {
            "generated_at": utc_now_iso(),
            "db": str(db.path),
            "window": {
                "start": iso(win["window_start"]),
                "end": iso(win["end"]),
                "quarters": win["window_quarters"],
                "observed_quarters": win.get("recent_q"),
                "label": win["window_label"],
            },
            "baseline": {
                "start": iso(win["baseline_start"]),
                "end": iso(win["baseline_end"]),
                "quarters": win["baseline_quarters"],
                "observed_quarters": win.get("base_q"),
                "label": win["baseline_label"],
            },
            "counts": counts,
            "data_status": data_status,
            "event_total": len(all_events),
            "definitions": {
                "thi": "Gamma-Poisson 收缩后的近期速率 / 基线速率（先验强度 3 个季度）",
                "prob_up": "真实速率高于基线速率的后验概率",
                "signal_date": "event_date + 1 天（最早可公开获知的近似）",
                "prior_strength_quarters": PRIOR_STRENGTH_QUARTERS,
            },
        },
        "device": device,
        "drug": drug,
        "cn_gap": cn_gap,
        "signals": signals,
        "alerts": alerts,
        "timestamps": timestamps,
        "research": _research_block(db, all_events, device, win, signals),
    }

    # Replay study (optional): the CLI writes out/replay/replay.json first, then
    # analyze embeds a compact view so the report can render the timeline.
    replay_payload = read_json(OUT_DIR / "replay" / "replay.json")
    if replay_payload:
        metrics["replay"] = _compact_replay(replay_payload)

    # Product-level intelligence (optional): requires medradar.products.
    products_payload = _products_block(db, win)
    if products_payload:
        metrics["products"] = products_payload

    # Traceable case library (optional): built by `medradar cases`.
    cases_payload = read_json(OUT_DIR / "cases" / "cases.json")
    if cases_payload:
        metrics["cases"] = _compact_cases(cases_payload)

    trading_path = OUT_DIR / "trading.json"
    trading = read_json(trading_path)
    if trading:
        metrics["trading"] = trading
    return metrics
