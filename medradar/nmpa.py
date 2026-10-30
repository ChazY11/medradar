"""NMPA (China NMPA / 国家药监局) adapter - honest by construction.

What was measured (2026-10-31)
------------------------------
``https://www.nmpa.gov.cn`` answers **HTTP 412** and ``https://www.cmde.org.cn``
answers **HTTP 202** with a JavaScript WAF challenge. Both responses are a WAF
gate, not data. MedRadar therefore does **not** scrape NMPA and does **not** try
to solve or bypass the challenge. As a consequence:

* If a user-exported CSV is present (``--csv_path`` argument ->
  ``MEDRADAR_NMPA_CSV`` -> ``data/nmpa_registrations.csv``) it is parsed and
  loaded as ``source="nmpa"`` / ``kind="nmpa_registration"`` events.
* Otherwise the collector returns ``{"status": "unavailable", ...}`` and writes
  **zero** events. The China-gap metric then reports ``unavailable`` instead of
  pretending "0 Chinese registrations" (docs/SCHEMA.md §4).
* Only when ``MEDRADAR_NMPA_DEMO=1`` is set does it load the *clearly fictional*
  demo seed in ``config/nmpa_demo_seed.csv``, tagged ``source="nmpa_demo"`` and
  ``payload.demo=true`` so downstream code and reports can label it as a demo.

CSV columns accept both Chinese and English headers, e.g.::

    注册证编号/registration_no, 产品名称/product_name, 企业名称/company_name,
    批准日期/approval_date, 有效期/valid_until, 类别/class, 省份/province

Payload contract (shared with ``analyze``)
------------------------------------------
``payload`` keeps the source row under ``raw`` and normalised keys directly:
``registration_no``, ``product_name``, ``company_name``, ``approval_date``,
``class``, ``province``, ``valid_until``, ``demo``, ``raw``.
"""

from __future__ import annotations

import calendar
import csv
import io
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from .config import (
    CONFIG_DIR,
    DATA_DIR,
    CompanyRegistry,
    TrackRegistry,
    load_companies,
    load_tracks,
)
from .db import DB, make_event_id
from .util import parse_date, today_utc

SOURCE = "nmpa"
DEMO_SOURCE = "nmpa_demo"
KIND = "nmpa_registration"
COUNTRY = "CN"

DEFAULT_CSV = DATA_DIR / "nmpa_registrations.csv"
DEMO_SEED = CONFIG_DIR / "nmpa_demo_seed.csv"

#: Honest, user-facing explanation. Wording is part of the delivered contract.
UNAVAILABLE_REASON = (
    "NMPA 查询页有 JS WAF（实测 HTTP 412/202），"
    "请导出 CSV 放到 data/nmpa_registrations.csv 后重跑"
)

_COLUMNS: dict[str, tuple[str, ...]] = {
    "registration_no": (
        "registration_no",
        "registration_number",
        "certificate_no",
        "注册证编号",
        "注册证号",
        "证书编号",
    ),
    "product_name": ("product_name", "产品名称", "产品名", "注册产品名称"),
    "company_name": (
        "company_name",
        "企业名称",
        "注册人名称",
        "注册人",
        "申请人名称",
        "公司名称",
    ),
    "approval_date": (
        "approval_date",
        "批准日期",
        "注册日期",
        "发证日期",
        "批准/发证日期",
    ),
    "valid_until": ("valid_until", "有效期", "有效期至", "截止日期"),
    "class": ("class", "类别", "管理类别", "分类", "注册类别"),
    "province": ("province", "省份", "所在省份", "省"),
    "source": ("source", "来源", "数据来源"),
}

_HEADER_LOOKUP: dict[str, str] = {}
for _key, _aliases in _COLUMNS.items():
    for _alias in _aliases:
        _HEADER_LOOKUP[re.sub(r"\s+", "", str(_alias).strip().lower())] = _key


# --------------------------------------------------------------------------- dates
def window(months: int, today: date | None = None) -> tuple[date, date]:
    end = today or today_utc()
    months = max(1, int(months or 1))
    total = end.year * 12 + (end.month - 1) - months
    year, month = divmod(total, 12)
    month += 1
    day = min(end.day, calendar.monthrange(year, month)[1])
    return date(year, month, day), end


# ------------------------------------------------------------------------- CSV I/O
def resolve_csv_path(csv_path: str | Path | None = None) -> Path:
    """``argument -> MEDRADAR_NMPA_CSV -> data/nmpa_registrations.csv``."""
    if csv_path:
        return Path(csv_path)
    env_path = os.environ.get("MEDRADAR_NMPA_CSV")
    if env_path:
        return Path(env_path)
    return DEFAULT_CSV


def demo_enabled() -> bool:
    return os.environ.get("MEDRADAR_NMPA_DEMO", "").strip() == "1"


def read_rows(path: str | Path) -> list[dict[str, str]]:
    """Parse an NMPA CSV into normalised dicts (UTF-8 with or without BOM / GBK).

    Unknown columns are ignored; a row needs at least one identifying column to
    be kept. Reading is intentionally forgiving because the file is produced by
    a human in Excel, but nothing is invented when a value is missing.
    """
    raw_bytes = Path(path).read_bytes()
    text = ""
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not text:
        raise ValueError(f"cannot decode NMPA CSV: {path}")

    rows: list[dict[str, str]] = []
    for row in csv.DictReader(io.StringIO(text)):
        mapped: dict[str, str] = {}
        for header, value in row.items():
            key = _HEADER_LOOKUP.get(re.sub(r"\s+", "", str(header or "").strip().lower()))
            if key:
                mapped[key] = str(value or "").strip()
        if any(
            mapped.get(key)
            for key in ("registration_no", "product_name", "company_name")
        ):
            rows.append(mapped)
    return rows


# ------------------------------------------------------------------- normalising
def normalize_registration(
    row: Mapping[str, str],
    *,
    source: str,
    demo: bool,
    company_key: str | None = None,
    confidence: float = 0.0,
    alias: str = "",
    track_id: str | None = None,
    as_of: str | None = None,
) -> dict[str, Any] | None:
    """Build one ``nmpa_registration`` event; ``None`` when the row is unusable."""
    product_name = str(row.get("product_name") or "").strip()
    registration_no = str(row.get("registration_no") or "").strip()
    company_name = str(row.get("company_name") or "").strip()
    approval = parse_date(row.get("approval_date"))
    if not (product_name or registration_no) or approval is None:
        return None

    valid_until = parse_date(row.get("valid_until"))
    payload = {
        "registration_no": registration_no,
        "product_name": product_name,
        "company_name": company_name,
        "approval_date": approval.isoformat(),
        "valid_until": valid_until.isoformat() if valid_until else None,
        "class": str(row.get("class") or "").strip() or None,
        "province": str(row.get("province") or "").strip() or None,
        "demo": bool(demo),
        "match_confidence": confidence,
        "matched_alias": alias,
        "raw": dict(row),
    }
    label = f"{product_name}｜{company_name}" if company_name else product_name
    badge = "【演示数据·非真实】" if demo else ""
    return {
        "event_id": make_event_id(
            source, KIND, registration_no or f"{product_name}|{company_name}"
        ),
        "source": source,
        "kind": KIND,
        "event_date": approval.isoformat(),
        "as_of": as_of or today_utc().isoformat(),
        "company_key": company_key,
        "applicant_raw": company_name,
        "country": COUNTRY,
        "track_id": track_id,
        "product_code": None,
        "title": f"{badge}{label}".strip(),
        "summary": (
            f"{badge}NMPA 注册证 {registration_no or 'N/A'}｜{product_name}"
            f"｜{company_name or '未知企业'}｜{approval.isoformat()}"
            f"｜类别 {payload['class'] or 'N/A'}｜{payload['province'] or '未知省份'}"
        ),
        "url": "",
        "payload": payload,
    }


def _tables(
    db: DB,
) -> tuple[CompanyRegistry, TrackRegistry]:
    companies = load_companies("device")
    tracks = load_tracks("device")
    db.upsert_companies(companies.all())
    db.upsert_tracks(tracks.all())
    return companies, tracks


def _load_rows(
    db: DB,
    path: Path,
    *,
    source: str,
    demo: bool,
    start: date,
    end: date,
    limit: int,
    as_of: str,
) -> dict[str, Any]:
    registry, tracks = _tables(db)
    rows = read_rows(path)
    events: dict[str, dict[str, Any]] = {}
    undated = 0
    out_of_window = 0
    for row in rows:
        approval = parse_date(row.get("approval_date"))
        if approval is None:
            undated += 1
            continue
        if approval < start or approval > end:
            out_of_window += 1
            continue
        company_name = str(row.get("company_name") or "")
        company_key, confidence, alias = registry.resolve(company_name)
        track_id = tracks.match_text(row.get("product_name"))
        event = normalize_registration(
            row,
            source=source,
            demo=demo,
            company_key=company_key,
            confidence=confidence,
            alias=alias,
            track_id=track_id,
            as_of=as_of,
        )
        if event is not None:
            events[event["event_id"]] = event

    chosen = list(events.values())
    chosen.sort(key=lambda event: event["event_date"])
    if limit:
        chosen = chosen[:limit]
    inserted = db.upsert_events(chosen) if chosen else 0

    track_counts: dict[str, int] = {}
    for event in chosen:
        key = event.get("track_id") or "unmatched"
        track_counts[key] = track_counts.get(key, 0) + 1
    stats = {
        "source": source,
        "status": "demo" if demo else "loaded",
        "demo": bool(demo),
        "file": str(path),
        "rows": len(rows),
        "undated": undated,
        "out_of_window": out_of_window,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "events": inserted,
        "per_kind": {KIND: inserted},
        "tracks": track_counts,
        "track_matched": sum(count for key, count in track_counts.items() if key != "unmatched"),
        "companies_matched": sum(1 for event in chosen if event.get("company_key")),
        "requests": 0,
    }
    if demo:
        stats["note"] = (
            "演示数据（config/nmpa_demo_seed.csv，内容为明显虚构的示例），"
            "不可用于任何真实结论；设置 MEDRADAR_NMPA_DEMO=1 才会加载。"
        )
    return stats


def unavailable(start: date, end: date, csv_path: Path | None = None) -> dict[str, Any]:
    """The honest empty answer: no events, no guessing."""
    return {
        "source": SOURCE,
        "status": "unavailable",
        "reason": UNAVAILABLE_REASON,
        "csv_expected": str(csv_path or DEFAULT_CSV),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "events": 0,
        "per_kind": {},
        "requests": 0,
    }


# ---------------------------------------------------------------------- collectors
def load_demo(
    db: DB,
    months: int = 120,
    limit: int = 0,
    *,
    path: str | Path | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Load the obviously fictional demo seed (``source="nmpa_demo"``)."""
    seed = Path(path or DEMO_SEED)
    start, end = window(months, today)
    as_of = (today or today_utc()).isoformat()
    if not seed.exists():
        result = unavailable(start, end, seed)
        result["reason"] = f"demo 种子文件不存在：{seed}（本应随仓库提交）"
        return result
    stats = _load_rows(
        db,
        seed,
        source=DEMO_SOURCE,
        demo=True,
        start=start,
        end=end,
        limit=limit,
        as_of=as_of,
    )
    db.log_run("collect_nmpa_demo", stats)
    print(
        f"[nmpa] DEMO only: {stats['events']} fictional registrations loaded "
        f"from {seed.name} (source={DEMO_SOURCE})",
        file=sys.stderr,
    )
    return stats


def collect(
    db: DB,
    fetcher: Any,
    months: int = 120,
    limit: int = 0,
    *,
    csv_path: str | Path | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Load a user-exported CSV, else the demo seed, else report ``unavailable``."""
    start, end = window(months, today)
    requests_before = int(fetcher.stats.get("requests", 0)) if fetcher is not None else 0
    path = resolve_csv_path(csv_path)

    if path.exists():
        stats = _load_rows(
            db,
            path,
            source=SOURCE,
            demo=False,
            start=start,
            end=end,
            limit=limit,
            as_of=(today or today_utc()).isoformat(),
        )
        db.log_run("collect_nmpa", stats)
        print(
            f"[nmpa] loaded {stats['events']} registrations from {path}",
            file=sys.stderr,
        )
    elif demo_enabled():
        stats = load_demo(db, months=months, limit=limit, today=today)
    else:
        stats = unavailable(start, end, path)
        print(
            "[nmpa] unavailable: NMPA WAF blocks scraping (HTTP 412/202); "
            "drop a CSV at data/nmpa_registrations.csv or set MEDRADAR_NMPA_DEMO=1",
            file=sys.stderr,
        )

    if fetcher is not None:
        stats["requests"] = int(fetcher.stats.get("requests", 0)) - requests_before
    return stats
