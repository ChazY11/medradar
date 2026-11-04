"""Render the arm comparison table (markdown) from a SUMMARY.json.

Kept as code rather than hand-copied numbers so the report and the artifacts
cannot drift, and so the `NOT_EVALUABLE` rule is enforced by construction: the
function writes the string, not a number, for precision/recall/F1.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

NOT_EVALUABLE = "NOT_EVALUABLE"

ARM_LABELS: Mapping[str, str] = {
    "rules-baseline": "A0 规则基线",
    "rules-baseline-a1": "A1 强化规则",
    "hf-qwen3-4b-instruct": "B 未微调 Qwen3-4B",
    "qlora-overnight": "C 探索性 QLoRA",
}


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def arm_table(summary: Mapping[str, Any], run_name: str) -> str:
    run = summary["runs"][run_name]
    arms = run["arms"]
    header = (
        "| 实验臂 | JSON 合法 | Schema 通过 | 逐字引用定位 | 抽取事件数 | 弃答率 | 错误弃答率 | "
        "负样本误报率 | 类别一致 | 日期一致 | 企业一致 | 中位延迟(s) | 峰值显存(MiB) |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    rows = [header]
    for adapter_id, arm in arms.items():
        label = ARM_LABELS.get(adapter_id, adapter_id)
        rows.append(
            "| {label} | {json_v} | {schema} | {quote} | {events} | {abst} | {wrong} | "
            "{false} | {cat} | {date} | {co} | {lat} | {vram} |".format(
                label=label,
                json_v=_fmt(arm["json_valid_rate"]),
                schema=_fmt(arm["schema_accepted_rate"]),
                quote=_fmt(arm["verbatim_quote_located_rate"]),
                events=arm["extracted_events"],
                abst=_fmt(arm["abstention_rate"]),
                wrong=_fmt(arm["wrong_abstention_rate"]),
                false=_fmt(arm["false_assertion_rate"]),
                cat=_fmt(arm["agreement"]["category_agreement"]),
                date=_fmt(arm["agreement"]["event_date_agreement"]),
                co=_fmt(arm["agreement"]["company_agreement"]),
                lat=_fmt(arm["latency_s"]["median"]),
                vram=_fmt(arm["peak_vram_mb"]),
            )
        )
    return "\n".join(rows)


def stratum_table(summary: Mapping[str, Any], run_name: str, stratum: str) -> str:
    arms = summary["runs"][run_name]["arms"]
    keys: list[str] = sorted(
        {key for arm in arms.values() for key in arm["strata"][stratum]}
    )
    header = (
        f"| {stratum} | " + " | ".join(
            f"{ARM_LABELS.get(adapter_id, adapter_id)} 类别/日期一致" for adapter_id in arms
        ) + " |\n|---|" + "|".join("---:" for _ in arms) + "|"
    )
    rows = [header]
    for key in keys:
        cells = []
        for arm in arms.values():
            bucket = arm["strata"][stratum].get(key)
            if bucket is None:
                cells.append("—")
            else:
                cells.append(
                    f"{_fmt(bucket['category_agreement'])} / {_fmt(bucket['event_date_agreement'])} "
                    f"(n={bucket['documents']})"
                )
        rows.append(f"| {key} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    blocks: list[str] = []
    for run_name in summary["runs"]:
        blocks.append(f"### {run_name}\n")
        blocks.append(arm_table(summary, run_name))
        blocks.append("")
        for stratum in ("text_origin", "source_type", "event_date_kind"):
            blocks.append(f"**分层：{stratum}**\n")
            blocks.append(stratum_table(summary, run_name, stratum))
            blocks.append("")
    blocks.append(
        f"\n> Precision / Recall / F1: **{NOT_EVALUABLE}** — 标签为 `source_record_derived` "
        "银标签，非人工金标准。上表所有“一致”列均为探索性一致率，不是准确率。\n"
    )
    Path(args.out).write_text("\n".join(blocks), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
