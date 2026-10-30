"""Product-level intelligence API on top of the family taxonomy.

Everything here is a **pure read-only function of the SQLite facts plus two
generated knowledge files** (``config/product_families.json`` and
``config/product_catalog_zh.json``). No CLI, no writes, no network.

Definitions mirror ``medradar.analyze`` so product numbers stay comparable with
the track-level metrics in ``out/metrics.json``:

* *activity* = 510(k) clearances and material PMA submissions (original PMA or
  Panel-Track supplement). Routine manufacturing supplements are excluded - a
  factory relocation must not look like a product launch.
* *THI* = Gamma-Poisson shrunk recent rate / baseline rate (prior strength
  3 quarters). A family with one clearance in the window is not "4x hotter".
* *window* = last ``window_quarters`` ending at the latest observed event date,
  baseline = the ``baseline_quarters`` before it, exposure capped by actual data.

Public API
----------
``family_stats(db, ...)``       per-family recent/base counts, rate, THI, companies,
                                new entrants, first-seen date
``company_portfolio(db, ...)``  company -> product-family mix + recent migration (JS)
``new_products(db, days=90)``   first-ever (company, product code) pairs in window
``family_detail(db, family_id)`` codes, representative products and recent events
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any, Iterable, Mapping

from .config import CONFIG_DIR
from .families import INVALID_PRODUCT_CODES, family_lookup, load_families
from .util import (
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
    today_utc,
)

CATALOG_FILE = CONFIG_DIR / "product_catalog_zh.json"
PRIOR_STRENGTH_QUARTERS = 3.0
NO_FAMILY = "unclassified"


# --------------------------------------------------------------------------- io
def load_catalog(path=None) -> dict[str, dict[str, str]]:
    """Read the generated Chinese product catalog (``{code: {name_zh, ...}}``)."""
    payload = read_json(path or CATALOG_FILE)
    return payload if isinstance(payload, dict) else {}


def catalog_name(
    code: str | None,
    catalog: Mapping[str, Mapping[str, str]] | None = None,
    device_name: str = "",
) -> str:
    """Chinese product name for a code, falling back to the English device name."""
    data = catalog if catalog is not None else load_catalog()
    entry = data.get(str(code or "")) if data else None
    if entry and entry.get("name_zh"):
        return str(entry["name_zh"])
    return device_name or (str(code) if code else "")


def catalog_definition(
    code: str | None,
    catalog: Mapping[str, Mapping[str, str]] | None = None,
    definition: str = "",
) -> str:
    """One-sentence Chinese use for a code, falling back to the English definition."""
    data = catalog if catalog is not None else load_catalog()
    entry = data.get(str(code or "")) if data else None
    if entry and entry.get("definition_zh"):
        return str(entry["definition_zh"])
    return definition or ""


# -------------------------------------------------------------------- internals
def _parse_payload(event: Mapping[str, Any]) -> dict[str, Any]:
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


def _is_material_pma(event: Mapping[str, Any]) -> bool:
    """Original PMA or Panel-Track supplement only (mirrors medradar.analyze)."""
    payload = _parse_payload(event)
    number = str(payload.get("supplement_number") or "").strip().upper()
    supplement_type = str(payload.get("supplement_type") or "").strip().upper()
    if number in ("", "0", "S0"):
        return True
    return "PANEL TRACK" in supplement_type


def _is_activity(event: Mapping[str, Any]) -> bool:
    kind = event.get("kind")
    if kind == "510k":
        return True
    if kind == "pma":
        return _is_material_pma(event)
    return False


def _valid_code(code: Any) -> bool:
    text = str(code or "").strip()
    return bool(text) and text.upper() not in INVALID_PRODUCT_CODES


def _load_events(db, kinds: Iterable[str] | None = None) -> list[dict[str, Any]]:
    sql = (
        "SELECT event_id, kind, source, event_date, as_of, company_key, track_id,"
        " product_code, applicant_raw, title, summary, url, payload FROM events"
        " WHERE event_date IS NOT NULL AND event_date != ''"
    )
    params: list[Any] = []
    kinds = tuple(kinds or ())
    if kinds:
        sql += " AND kind IN (%s)" % ",".join("?" * len(kinds))
        params = list(kinds)
    rows = db.query(sql, params)
    events: list[dict[str, Any]] = []
    for row in rows:
        day = parse_date(row["event_date"])
        if not day:
            continue
        row["_day"] = day
        events.append(row)
    events.sort(key=lambda item: (item["_day"], str(item["event_id"])))
    return events


def _resolve_window(
    events: list[dict[str, Any]],
    window_quarters: int,
    baseline_quarters: int,
    today: date | None = None,
) -> dict[str, Any]:
    """Recent/baseline window exactly like ``medradar.analyze`` (honest exposure)."""
    today = today or today_utc()
    latest = max((event["_day"] for event in events), default=today)
    earliest = min((event["_day"] for event in events), default=latest)
    end = min(latest, today)
    end_idx = quarter_index(end)
    win_start_idx = end_idx - window_quarters + 1
    base_end_idx = win_start_idx - 1
    base_start_idx = base_end_idx - baseline_quarters + 1
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


def _split(
    events: list[dict[str, Any]], win: Mapping[str, Any]
) -> tuple[list[dict], list[dict]]:
    recent = [e for e in events if win["window_start"] <= e["_day"] <= win["end"]]
    base = [e for e in events if win["baseline_start"] <= e["_day"] < win["window_start"]]
    return recent, base


def _rate_metric(
    count_recent: int, count_base: int, win: Mapping[str, Any], fallback_prior: float
) -> dict[str, Any]:
    """Gamma-Poisson posterior rate ratio (THI) and P(rate > baseline)."""
    recent_q = max(1, int(win.get("recent_q") or win["window_quarters"]))
    base_q = int(win.get("base_q") or 0)
    recent_per_q = count_recent / recent_q
    base_per_q = (count_base / base_q) if base_q > 0 else 0.0
    emerging = base_per_q <= 0.0
    reference = base_per_q if base_per_q > 0 else max(fallback_prior, 1e-6)
    post = gamma_poisson(count_recent, recent_q, reference, PRIOR_STRENGTH_QUARTERS)
    thi = post["mean"] / reference if reference > 0 else None
    prob_up = (
        prob_rate_above(count_recent, recent_q, reference, PRIOR_STRENGTH_QUARTERS, reference)
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


def _company_meta(db, keys: Iterable[str]) -> dict[str, dict[str, Any]]:
    wanted = {key for key in keys if key}
    if not wanted:
        return {}
    rows = db.query("SELECT key, name_en, name_zh, ticker, is_major FROM companies")
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("key") or "")
        if key not in wanted:
            continue
        out[key] = {
            "key": key,
            "name_zh": row.get("name_zh") or row.get("name_en") or key,
            "ticker": row.get("ticker") or "",
            "is_major": bool(row.get("is_major")),
        }
    return out


def _activity_with_codes(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if _is_activity(event) and _valid_code(event.get("product_code"))
    ]


# ----------------------------------------------------------------- public API
def family_stats(
    db,
    window_quarters: int = 8,
    baseline_quarters: int = 20,
    families: Mapping[str, Any] | None = None,
    catalog: Mapping[str, Mapping[str, str]] | None = None,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Per-family activity stats: recent/base counts, rate, THI, companies, new entrants.

    ``families`` / ``catalog`` default to the generated ``config/*.json`` files;
    pass explicit payloads to run against synthetic databases (tests do).
    """
    family_payload = families if families is not None else load_families()
    catalog_data = catalog if catalog is not None else load_catalog()
    by_id, code_to_family = family_lookup(family_payload)
    all_events = _load_events(db)
    activity = _activity_with_codes(all_events)
    win = _resolve_window(all_events, window_quarters, baseline_quarters, today)
    recent, base = _split(activity, win)
    recalls_recent_events = _split(
        [e for e in all_events if e["kind"] == "device_recall" and _valid_code(e.get("product_code"))],
        win,
    )[0]

    recent_by_family: Counter[str] = Counter()
    base_by_family: Counter[str] = Counter()
    for event in recent:
        family_id = code_to_family.get(event["product_code"])
        if family_id:
            recent_by_family[family_id] += 1
    for event in base:
        family_id = code_to_family.get(event["product_code"])
        if family_id:
            base_by_family[family_id] += 1
    base_rates = [count / max(1, int(win["base_q"])) for count in base_by_family.values()]
    typical_rate = (sum(base_rates) / len(base_rates)) if base_rates else 0.5

    cutoff_12m = win["end"] - timedelta(days=365)
    # family-level aggregates, computed in one pass over the data
    companies_by_family: dict[str, set[str]] = defaultdict(set)
    recent_companies_by_family: dict[str, set[str]] = defaultdict(set)
    first_seen_by_family: dict[str, date] = {}
    first_company_family: dict[tuple, date] = {}
    product_counts: dict[str, Counter] = defaultdict(Counter)
    recalls_by_family: Counter[str] = Counter()
    for event in activity:
        family_id = code_to_family.get(event["product_code"])
        if not family_id:
            continue
        company = event.get("company_key")
        if company:
            companies_by_family[family_id].add(company)
            key = (company, family_id)
            if key not in first_company_family:
                first_company_family[key] = event["_day"]
        product_counts[family_id][event["product_code"]] += 1
        day = event["_day"]
        if family_id not in first_seen_by_family or day < first_seen_by_family[family_id]:
            first_seen_by_family[family_id] = day
    for event in recent:
        family_id = code_to_family.get(event["product_code"])
        if family_id and event.get("company_key"):
            recent_companies_by_family[family_id].add(event["company_key"])
    for event in recalls_recent_events:
        family_id = code_to_family.get(event["product_code"])
        if family_id:
            recalls_by_family[family_id] += 1
    new_entrants_by_family: dict[str, set[str]] = defaultdict(set)
    for (company, family_id), day in first_company_family.items():
        if day >= cutoff_12m:
            new_entrants_by_family[family_id].add(company)
    code_names = {
        str(row["product_code"]): str(row["device_name"] or "")
        for row in db.query("SELECT product_code, device_name FROM product_codes")
    }

    rows: list[dict[str, Any]] = []
    for family_id, family in by_id.items():
        codes = set(family.get("codes") or [])
        if not codes:
            continue
        recent_count = recent_by_family.get(family_id, 0)
        base_count = base_by_family.get(family_id, 0)
        row: dict[str, Any] = {
            "family_id": family_id,
            "name_zh": family.get("name_zh", family_id),
            "name_en": family.get("name_en", ""),
            "category": family.get("category", ""),
            "code_count": len(codes),
        }
        row.update(_rate_metric(recent_count, base_count, win, typical_rate))
        row["base"] = base_count
        row["companies"] = len(recent_companies_by_family.get(family_id, set()))
        row["companies_total"] = len(companies_by_family.get(family_id, set()))
        row["new_entrants_12m"] = len(new_entrants_by_family.get(family_id, set()))
        row["first_seen"] = iso(first_seen_by_family.get(family_id)) or None
        row["recalls_recent"] = recalls_by_family.get(family_id, 0)
        top = product_counts.get(family_id)
        top_code = top.most_common(1)[0][0] if top else ""
        row["top_product"] = catalog_name(top_code, catalog_data, code_names.get(top_code, ""))
        rows.append(row)

    # Busiest families first (stable, volume makes tiny-sample THI comparable);
    # ties are broken by THI so accelerating families surface near the top.
    rows.sort(
        key=lambda row: (
            -row["recent"],
            row["thi"] is None,
            -(row["thi"] or 0),
            row["family_id"],
        )
    )
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def company_portfolio(
    db,
    window_quarters: int = 8,
    baseline_quarters: int = 20,
    families: Mapping[str, Any] | None = None,
    catalog: Mapping[str, Mapping[str, str]] | None = None,
    min_recent: int = 1,
    today: date | None = None,
) -> dict[str, dict[str, Any]]:
    """Company -> product-family mix, plus recent portfolio migration.

    Returns ``{company_key: {...}}`` with the recent family shares, the
    Jensen-Shannon divergence between the recent and baseline portfolios, and
    the families whose share moved by at least 8 percentage points.
    """
    family_payload = families if families is not None else load_families()
    catalog_data = catalog if catalog is not None else load_catalog()
    by_id, code_to_family = family_lookup(family_payload)
    all_events = _load_events(db)
    activity = [e for e in _activity_with_codes(all_events) if e.get("company_key")]
    win = _resolve_window(all_events, window_quarters, baseline_quarters, today)
    recent, base = _split(activity, win)

    recent_by_company: dict[str, Counter] = defaultdict(Counter)
    base_by_company: dict[str, Counter] = defaultdict(Counter)
    for event in recent:
        family_id = code_to_family.get(event["product_code"])
        if family_id:
            recent_by_company[event["company_key"]][family_id] += 1
    for event in base:
        family_id = code_to_family.get(event["product_code"])
        if family_id:
            base_by_company[event["company_key"]][family_id] += 1

    keys = set(recent_by_company) | set(base_by_company)
    companies = _company_meta(db, keys)
    # first time a company is seen in a family (portfolio expansion proxy)
    first_company_family: dict[tuple, date] = {}
    for event in activity:
        family_id = code_to_family.get(event["product_code"])
        if not family_id:
            continue
        key = (event["company_key"], family_id)
        if key not in first_company_family:
            first_company_family[key] = event["_day"]
    cutoff_12m = win["end"] - timedelta(days=365)

    result: dict[str, dict[str, Any]] = {}
    for company in sorted(keys):
        recent_counter = recent_by_company.get(company, Counter())
        base_counter = base_by_company.get(company, Counter())
        total_recent = sum(recent_counter.values())
        if total_recent < min_recent:
            continue
        shares_recent = normalize_dist(recent_counter)
        shares_base = normalize_dist(base_counter) if base_counter else {}
        meta = companies.get(
            company, {"key": company, "name_zh": company or "未匹配", "ticker": "", "is_major": False}
        )
        ordered = sorted(shares_recent.items(), key=lambda pair: (-pair[1], pair[0]))
        top_families = [
            [
                family_id,
                round(value, 3),
                by_id.get(family_id, {}).get("name_zh", family_id),
                recent_counter.get(family_id, 0),
            ]
            for family_id, value in ordered[:5]
        ]
        migration = []
        distance = js_divergence(shares_recent, shares_base) if shares_base else 0.0
        for family_id in sorted(set(shares_recent) | set(shares_base)):
            delta = shares_recent.get(family_id, 0.0) - shares_base.get(family_id, 0.0)
            if abs(delta) >= 0.08:
                migration.append(
                    {
                        "family_id": family_id,
                        "name_zh": by_id.get(family_id, {}).get("name_zh", family_id),
                        "share_recent": round(shares_recent.get(family_id, 0.0), 3),
                        "share_base": round(shares_base.get(family_id, 0.0), 3),
                        "delta": round(delta, 3),
                    }
                )
        migration.sort(key=lambda row: -abs(row["delta"]))
        result[company] = {
            "key": company,
            "name_zh": meta["name_zh"],
            "ticker": meta["ticker"],
            "is_major": meta["is_major"],
            "recent": total_recent,
            "base": sum(base_counter.values()),
            "family_count": len(recent_counter),
            "top_families": top_families,
            "migration": migration,
            "js": round(distance, 4),
            "new_families_12m": sum(
                1
                for (key, family_id), day in first_company_family.items()
                if key == company and day >= cutoff_12m
            ),
        }
    return result


def new_products(
    db,
    days: int = 90,
    families: Mapping[str, Any] | None = None,
    catalog: Mapping[str, Mapping[str, str]] | None = None,
    max_items: int = 500,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """First-ever ``(company, product code)`` pairs whose first event is inside the window.

    Each row carries the Chinese product name and use, the family, the event
    date, the 510(k)/PMA number and the source link, so the list is directly
    actionable for a "what did this company just launch" review.
    """
    family_payload = families if families is not None else load_families()
    catalog_data = catalog if catalog is not None else load_catalog()
    by_id, code_to_family = family_lookup(family_payload)
    events = _load_events(db)
    activity = [e for e in _activity_with_codes(events) if e.get("company_key")]
    today = today or today_utc()
    latest = max((event["_day"] for event in events), default=today)
    end = min(latest, today)
    cutoff = end - timedelta(days=days)

    first: dict[tuple, dict[str, Any]] = {}
    for event in activity:
        key = (event["company_key"], event["product_code"])
        if key not in first:
            first[key] = event

    companies = _company_meta(db, {event["company_key"] for event in activity})
    code_rows = {
        str(row["product_code"]): row
        for row in db.query("SELECT product_code, device_name, definition FROM product_codes")
    }
    items: list[dict[str, Any]] = []
    for (company, code), event in first.items():
        if event["_day"] < cutoff:
            continue
        payload = _parse_payload(event)
        number = ""
        if event["kind"] == "510k":
            number = str(payload.get("k_number") or "")
        elif event["kind"] == "pma":
            pma = str(payload.get("pma_number") or "")
            supplement = str(payload.get("supplement_number") or "")
            number = f"{pma}/{supplement}" if pma and supplement else pma
        code_row = code_rows.get(code, {})
        name_zh = catalog_name(code, catalog_data, str(code_row.get("device_name") or ""))
        family_id = code_to_family.get(code, NO_FAMILY)
        family = by_id.get(family_id, {})
        meta = companies.get(company, {"name_zh": company, "ticker": ""})
        items.append(
            {
                "event_date": iso(event["_day"]),
                "event_id": event["event_id"],
                "company_key": company,
                "name_zh": meta["name_zh"],
                "ticker": meta.get("ticker", ""),
                "product_code": code,
                "product_name_zh": name_zh,
                "product_definition_zh": catalog_definition(
                    code, catalog_data, str(code_row.get("definition") or "")
                ),
                "family_id": family_id,
                "family_zh": family.get("name_zh", "未分类"),
                "kind": event["kind"],
                "number": number,
                "url": event.get("url") or "",
                "title": event.get("title") or "",
            }
        )
    items.sort(
        key=lambda row: (row["event_date"], row["company_key"], row["product_code"]),
        reverse=True,
    )
    return items[:max_items]


def family_detail(
    db,
    family_id: str,
    families: Mapping[str, Any] | None = None,
    catalog: Mapping[str, Mapping[str, str]] | None = None,
    recent_limit: int = 30,
    today: date | None = None,
) -> dict[str, Any]:
    """Codes, representative products and recent activity for one family."""
    family_payload = families if families is not None else load_families()
    catalog_data = catalog if catalog is not None else load_catalog()
    by_id, code_to_family = family_lookup(family_payload)
    family = by_id.get(str(family_id))
    if not family:
        return {"family_id": family_id, "error": "unknown family", "families": sorted(by_id)}
    codes = sorted(str(code) for code in family.get("codes") or [])
    code_set = set(codes)
    events = _load_events(db)
    activity = [e for e in _activity_with_codes(events)]
    today = today or today_utc()
    win = _resolve_window(events, 8, 20, today)
    recent, base = _split(activity, win)

    code_rows = {
        str(row["product_code"]): row
        for row in db.query("SELECT product_code, device_name, definition FROM product_codes")
    }
    counts = Counter(e["product_code"] for e in activity if e["product_code"] in code_set)
    recent_counts = Counter(
        e["product_code"] for e in recent if e["product_code"] in code_set
    )
    company_map = _company_meta(db, {e["company_key"] for e in activity if e.get("company_key")})
    first_seen: dict[str, date] = {}
    for event in activity:
        code = event["product_code"]
        if code in code_set and code not in first_seen:
            first_seen[code] = event["_day"]

    code_list = []
    for code in codes:
        code_row = code_rows.get(code, {})
        code_list.append(
            {
                "product_code": code,
                "device_name": str(code_row.get("device_name") or ""),
                "name_zh": catalog_name(code, catalog_data, str(code_row.get("device_name") or "")),
                "definition_zh": catalog_definition(
                    code, catalog_data, str(code_row.get("definition") or "")
                ),
                "events": counts.get(code, 0),
                "recent": recent_counts.get(code, 0),
                "first_seen": iso(first_seen.get(code)) or None,
            }
        )
    code_list.sort(key=lambda row: (-row["recent"], -row["events"], row["product_code"]))
    representative = code_list[:8]

    family_events = [
        e for e in activity if e["product_code"] in code_set
    ]
    family_events.sort(key=lambda e: (e["_day"], str(e["event_id"])), reverse=True)
    recent_events = []
    for event in family_events[: max(0, recent_limit)]:
        meta = company_map.get(event.get("company_key") or "", {})
        code_row = code_rows.get(event["product_code"], {})
        recent_events.append(
            {
                "event_date": iso(event["_day"]),
                "event_id": event["event_id"],
                "kind": event["kind"],
                "company_key": event.get("company_key") or "",
                "name_zh": meta.get("name_zh", event.get("company_key") or ""),
                "product_code": event["product_code"],
                "product_name_zh": catalog_name(
                    event["product_code"], catalog_data, str(code_row.get("device_name") or "")
                ),
                "title": event.get("title") or "",
                "url": event.get("url") or "",
            }
        )
    stats = None
    for row in family_stats(
        db,
        window_quarters=win["window_quarters"],
        baseline_quarters=win["baseline_quarters"],
        families=family_payload,
        catalog=catalog_data,
        today=today,
    ):
        if row["family_id"] == family_id:
            stats = row
            break
    return {
        "family_id": family_id,
        "name_zh": family.get("name_zh", family_id),
        "name_en": family.get("name_en", ""),
        "category": family.get("category", ""),
        "note": family.get("note", ""),
        "keywords": list(family.get("keywords") or []),
        "code_count": len(codes),
        "codes": code_list,
        "representative_products": representative,
        "stats": stats,
        "recent_events": recent_events,
        "window": {
            "start": iso(win["window_start"]),
            "end": iso(win["end"]),
            "label": win["window_label"],
            "quarters": win["window_quarters"],
        },
        "recent_total": sum(recent_counts.values()),
        "base_total": sum(
            e["product_code"] in code_set for e in base
        ),
    }
