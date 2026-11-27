"""What this deployment actually holds, and what it does not.

The coverage page used to print raw JSON blobs and an empty source table, and its paper count
disagreed with the landing page by five because each counted at a different moment. A page whose job
is to say "this is what we know" cannot itself be approximate.

So coverage is assembled in one place: the materialised counts for the expensive numbers (so the
page agrees with the landing page), a handful of cheap live queries for the shape of each set, and an
explicit list of what is still missing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: Two scheduler cycles plus slack. Beyond this the graph is history, not a radar.
STALE_AFTER_HOURS = 12.0

#: (key, label, count-key, note). ``None`` for the note means "say nothing extra".
DATASETS: tuple[tuple[str, str, str, str], ...] = (
    ("devices", "UDI 设备注册", "devices", "FDA GUDID 全量释放文件"),
    ("corpus", "510(k) 批文语料", "corpus", "已归档的批文正文，逐份可查"),
    ("failures", "MAUDE 失效记录", "failures", "按产品码扫过；未扫的码见下方缺口"),
    ("trials", "临床试验", "trials", "ClinicalTrials.gov，按器械干预筛选"),
    ("patents", "专利", "patents", "Google Patents 分批抓取，覆盖有限"),
    ("papers", "论文全文", "papers", "已归档全文，不是摘要"),
    ("codes", "FDA 产品码分类", "codes", "每个产品码对应的器械类别与专科"),
)


def _scalar(reference, sql: str, default: int = 0) -> int:
    try:
        row = reference.conn.execute(sql).fetchone()
        return int(row[0] or 0) if row else default
    except Exception:  # noqa: BLE001 - an absent table is a zero with a reason elsewhere
        return default


def _distinct(reference, sql: str) -> int:
    return _scalar(reference, sql)


def shape(reference) -> dict[str, Any]:
    """The shape of each dataset: how many codes, models, sponsors, assignees it covers."""
    return {
        "failure_codes": _distinct(
            reference, "SELECT COUNT(DISTINCT product_code) FROM maude_failure_index"),
        "failure_models": _distinct(
            reference, "SELECT COUNT(DISTINCT model_norm) FROM maude_failure_index"),
        "failure_brands": _distinct(
            reference, "SELECT COUNT(DISTINCT brand_norm) FROM maude_failure_index"),
        "trial_sponsors": _distinct(
            reference, "SELECT COUNT(DISTINCT lead_sponsor) FROM trial"),
        "patent_assignees": _distinct(
            reference, "SELECT COUNT(DISTINCT organization_norm) FROM bulk_patent_assignee "
                       "WHERE COALESCE(assignee_type,'applicant') <> 'query_matched'"),
        "specialties": _distinct(
            reference, "SELECT COUNT(DISTINCT medical_specialty) FROM product_code_class"),
        "register_codes": _distinct(
            reference, "SELECT COUNT(DISTINCT j.value) FROM udi_device d, "
                       "json_each(d.product_codes) j"),
    }


def source_health(service: Any) -> dict[str, Any]:
    """Per-source status and how stale the graph is, for the coverage page.

    Measured 2026-11-26: the radar's three monitored sources had been refusing this host for days -
    draeger_official 403 Forbidden, 355 consecutive failures, newest observation 211 hours old - while
    /sources said only "the map covers three companies". A graph that has stopped updating and does
    not say so is the failure this whole product exists to avoid: the page looks fine and the numbers
    are historical.

    Everything here is read from the ledger's own records; nothing is inferred.
    """
    report: dict[str, Any] = {"available": False, "sources": [], "newest_observation": None,
                              "stale_hours": None, "stale": False, "reason": None}
    try:
        from .health import source_status

        with service.ledger() as ledger:
            rows = source_status(ledger, service.taxonomy())
            try:
                newest = ledger.raw(
                    "SELECT MAX(first_observed_at) AS newest FROM observation")[0]["newest"]
            except Exception:  # noqa: BLE001 - an empty ledger has no newest
                newest = None
    except Exception as error:  # noqa: BLE001 - no ledger is a state, not a crash
        report["reason"] = type(error).__name__
        return report

    sources = []
    now = datetime.now(timezone.utc)
    for row in rows:
        # `source_status` names these last_success_check_at / newest_observation_at /
        # last_failure_message; reading the wrong key silently printed "from never" for every source.
        last_success = (row.get("last_success_check_at")
                        or row.get("newest_observation_at"))
        hours = row.get("hours_since_success")
        if hours is None and last_success:
            try:
                stamp = datetime.fromisoformat(str(last_success).replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                hours = round((now - stamp).total_seconds() / 3600.0, 1)
            except ValueError:
                hours = None
        sources.append({
            "source_id": str(row.get("source_id") or ""),
            "status": str(row.get("status") or "UNKNOWN"),
            "enabled": bool(row.get("enabled", True)),
            "last_success": last_success,
            "hours_since_success": hours,
            "consecutive_failures": int(row.get("consecutive_failures") or 0),
            "reason": str(row.get("last_failure_message") or row.get("access_reason") or ""),
            "access_state": str(row.get("access_state") or ""),
            "observations": int(row.get("observations_total") or 0),
            "cadence_hours": row.get("cadence_hours"),
        })
    report["sources"] = sources
    report["available"] = True
    report["newest_observation"] = newest

    # Staleness is a fact about the graph, not about any one source: the newest observation any
    # source managed to record. Beyond two scheduler cycles without one, the page must say so.
    if newest:
        try:
            stamp = datetime.fromisoformat(str(newest).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            hours = (datetime.now(timezone.utc) - stamp).total_seconds() / 3600.0
            report["stale_hours"] = round(hours, 1)
            report["stale"] = hours >= STALE_AFTER_HOURS
        except ValueError:
            report["stale_hours"] = None
    return report


def coverage(reference, *, corpus_dir: str | Path | None = None,
             service: Any = None) -> dict[str, Any]:
    """Everything the coverage page prints, from the stored counts plus live shape queries."""
    from .store_stats import read as read_stats

    stored = read_stats(reference)
    counts = dict(stored.get("counts") or {})
    if not counts.get("corpus") and corpus_dir is not None:
        try:
            counts["corpus"] = sum(1 for _ in Path(corpus_dir).glob("*.json"))
        except OSError:
            counts["corpus"] = 0

    # The shape of each set is materialised too. Measured: `register_codes` expands the JSON product
    # codes of 5.2M rows (6.7 s warm), and reading it live made this page take 21.5 s. A live query
    # runs only for the keys the nightly pass has never written.
    keys = ("failure_codes", "failure_models", "failure_brands", "trial_sponsors",
            "patent_assignees", "specialties", "register_codes")
    parts = {key: int(counts[key]) for key in keys if key in counts}
    if len(parts) < len(keys):
        live = shape(reference)
        for key in keys:
            parts.setdefault(key, int(live.get(key) or 0))

    datasets = []
    for key, label, count_key, note in DATASETS:
        item = {"key": key, "label": label, "count": int(counts.get(count_key) or 0),
                "note": note}
        if key == "papers":
            # Files beside the index that are not in it. Measured 2026-11-28: 5,755 corpus files, 5,485
            # indexed, and 270 that produced no vocabulary term - invisible until the indexer counted
            # them, so the page called 5,485 the whole literature lane.
            files = int(counts.get("paper_files") or 0)
            indexed = int(counts.get("paper_indexed") or item["count"] or 0)
            if files and files > indexed:
                item["beside"] = (f'语料目录里还有 {files - indexed} 个文件没有被索引：'
                                  f'它们没有命中注册表词表的词，无法检索。')
        datasets.append(item)

    # Gaps are computed, not remembered: each one names what is missing and why.
    gaps: list[dict[str, str]] = []
    with_rows = parts.get("failure_codes") or 0
    register_codes = parts.get("register_codes") or 0
    # "Checked" and "had records" are different numbers, and printing one where the other belongs is
    # how this page claimed 838 of 5,229 forever: 838 counted codes that produced rows, so a code that
    # was swept and found empty could never be counted as covered. The sweep record fixes the count;
    # this sentence reports both halves of it.
    try:
        from .code_census import product_code_census, swept_codes
        from .failure_index import sweep_state

        checked_state = sweep_state(reference)
        # The union, not the maximum: the codes that produced rows and the codes that were checked
        # and found empty are disjoint sets, and taking either alone undercounts the work done.
        checked = len(swept_codes(reference))
        # The sweep can only reach codes that sit on a device with a clearance; the register holds
        # more codes than that. Reporting progress against the larger number would make complete
        # coverage of everything reachable look like partial coverage forever.
        sweeper_census = len(product_code_census(reference))
    except Exception:  # noqa: BLE001 - no sweep table yet
        checked_state = {"swept": 0, "empty": 0, "last_swept_at": None}
        checked, sweeper_census = 0, 0
    empty = int(checked_state.get("empty") or 0)
    parts["failure_codes_checked"] = checked
    parts["failure_codes_empty"] = empty
    denominator = sweeper_census or register_codes
    if denominator and checked < denominator:
        detail = (f"已检查 {checked:,} 个产品码（其中 {empty:,} 个查了没有任何可连接的失效记录）。"
                  f"可扫的码是那些出现在某台有批文设备上的码，共 {denominator:,} 个；"
                  f"寄存器里还有 {max(0, register_codes - denominator):,} 个码没有和任何批文关联，"
                  f"扫不到。没查到的码下，设备会显示「产品码还没扫过」，而不是「没有失效」。")
        if checked_state.get("last_swept_at"):
            detail += f"最近一次扫描：{str(checked_state['last_swept_at'])[:16]}。"
        gaps.append({"title": "失效记录只扫了部分产品码", "detail": detail})
    elif denominator:
        gaps.append({
            "title": "失效记录已覆盖全部可扫产品码",
            "detail": (f"已检查 {denominator:,} 个可扫的产品码，其中 {empty:,} 个查了没有可连接的"
                       f"失效记录。「没有失效」是查过的结论，不是空白。"),
        })
    covered_assignees = parts.get("patent_assignees") or 0
    labelers = int(counts.get("labelers") or _scalar(
        reference, "SELECT COUNT(DISTINCT labeler_duns) FROM udi_device"))
    # "Behind" and "refused" are different facts. Measured: eight companies returned HTTP 503 every
    # night for a week; the page said only that 92 of 12,537 had patents, which reads as "the job is
    # catching up" when in reality the source had stopped answering this host.
    try:
        from .patent_status import read as read_patent_status

        patent_state = read_patent_status(reference)
    except Exception:  # noqa: BLE001 - no status table yet
        patent_state = {"available": False}
    if patent_state.get("available") and patent_state.get("refused"):
        gaps.append({
            "title": "专利源拒绝本机",
            "detail": (f"Google Patents 对自动化请求返回 503（拦截页），最近一次尝试 "
                       f"{str(patent_state.get('attempted_at'))[:16]}："
                       f"{patent_state.get('failed')}/{patent_state.get('attempted')} 家公司全部失败。"
                       f"这不是抓得慢，是抓不到；专利数停在 {int(counts.get('patents') or 0):,} 条，"
                       f"覆盖 {covered_assignees:,} 个受让人。EPO OPS 的账号仍在审核，"
                       f"换源需要 key，不是改几行代码能解决的。"),
        })
    elif covered_assignees and labelers and covered_assignees < labelers:
        gaps.append({
            "title": "专利只覆盖了部分受让人",
            "detail": f"{covered_assignees:,} 个受让人有专利数据，注册表里有 {labelers:,} 个 labeler。"
                      f"没有记录的公司在页面上会写「还没抓过」，不是「没有专利」。",
        })
    if not counts.get("patents"):
        gaps.append({"title": "专利源未接通",
                     "detail": "EPO OPS 账号仍在审核（受理号 51279）。"})
    gaps.append({
        "title": "预印本抓取被拒",
        "detail": "bioRxiv/medRxiv 拒绝本机出口地址；论文增量目前靠 europepmc 那条线。",
    })
    gaps.append({
        "title": "图谱只覆盖 3 家公司",
        "detail": "科技地图追踪 Philips / GE / Dräger。其余公司有「技术领域」（按产品码分类），"
                  "但没有图谱。",
    })
    # A source that has failed for days is worth its own gap, even when the graph as a whole is
    # still moving: draeger_official had refused this host 356 times while crossref published
    # normally, and "the map covers three companies" said nothing about that.
    health = source_health(service) if service is not None else {}
    for source in health.get("sources") or []:
        if source["status"] == "FAILED" and source["consecutive_failures"] >= 5:
            gaps.append({
                "title": f"源 {source['source_id']} 持续失败",
                "detail": (f"连续失败 {source['consecutive_failures']} 次"
                           + (f"，最后成功 {str(source['last_success'])[:10]}" if source["last_success"]
                              else "，从未成功")
                           + (f"；原因：{source['reason'][:80]}" if source["reason"] else "")
                           + "。这个源贡献的数据停在那一刻。"),
            })

    if health.get("stale"):
        gaps.insert(0, {
            "title": "图谱数据已停止更新",
            "detail": f"最新的观测记录是 {health.get('stale_hours')} 小时前。"
                      f"科技地图与实时雷达展示的是历史快照，不是当前状态。",
        })
    return {"datasets": datasets, "shape": parts, "gaps": gaps,
            "updated_at": stored.get("updated_at"), "available": stored.get("available", False),
            "health": health}


__all__ = ["DATASETS", "STALE_AFTER_HOURS", "coverage", "shape", "source_health"]
