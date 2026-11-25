"""What this deployment actually holds, and what it does not.

The coverage page used to print raw JSON blobs and an empty source table, and its paper count
disagreed with the landing page by five because each counted at a different moment. A page whose job
is to say "this is what we know" cannot itself be approximate.

So coverage is assembled in one place: the materialised counts for the expensive numbers (so the
page agrees with the landing page), a handful of cheap live queries for the shape of each set, and an
explicit list of what is still missing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


def coverage(reference, *, corpus_dir: str | Path | None = None) -> dict[str, Any]:
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
        datasets.append({"key": key, "label": label, "count": int(counts.get(count_key) or 0),
                         "note": note})

    # Gaps are computed, not remembered: each one names what is missing and why.
    gaps: list[dict[str, str]] = []
    swept = parts.get("failure_codes") or 0
    register_codes = parts.get("register_codes") or 0
    if register_codes and swept < register_codes:
        gaps.append({
            "title": "失效记录只扫了部分产品码",
            "detail": f"已扫 {swept:,} 个产品码，注册表里共有 {register_codes:,} 个。"
                      f"没扫到的码下，设备会显示「产品码还没扫过」，而不是「没有失效」。",
        })
    covered_assignees = parts.get("patent_assignees") or 0
    labelers = int(counts.get("labelers") or _scalar(
        reference, "SELECT COUNT(DISTINCT labeler_duns) FROM udi_device"))
    if covered_assignees and labelers and covered_assignees < labelers:
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
    return {"datasets": datasets, "shape": parts, "gaps": gaps,
            "updated_at": stored.get("updated_at"), "available": stored.get("available", False)}


__all__ = ["DATASETS", "coverage", "shape"]
