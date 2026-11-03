"""Write ``REPORT.md`` for a benchmark run -- with the banner the data deserves.

A score produced on hand-written synthetic fixtures is a *harness* result.  The
report says so at the top, lists gated arms as ``NOT RUN: <reason>`` instead of
inventing a zero, and has a section headed "what this does not show".  If a caller
tries to write a research-grade report for non-research label tiers, the writer
refuses (the runner would already have refused via
:func:`..contracts.require_consistent_run_status`; defence in depth).

Rendering rules
---------------
* a rate that was not measured prints as ``not measured`` (never ``0``);
* a gated arm prints its refusal reason, with no metric cells at all;
* the matching protocol is included in full, so a reader can check the numbers;
* the deterministic rule table is included for arm A, so its behaviour is not a
  black box.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..contracts import RUN_STATUSES, is_research_grade

SYNTHETIC_BANNER = "SYNTHETIC_FIXTURE_ONLY — harness validation, not an empirical result"
NOT_MEASURED = "not measured"


def _as_dict(value: Any) -> dict[str, Any]:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"cannot serialise {type(value).__name__} for the report")


def _md(text: Any) -> str:
    """Make an arbitrary string safe inside a markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def _fmt_rate(value: Any) -> str:
    if value is None:
        return NOT_MEASURED
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return _md(value)


def _fmt_number(value: Any, unit: str = "") -> str:
    if value is None:
        return NOT_MEASURED
    try:
        number = float(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return _md(value)
    suffix = f" {unit}" if unit else ""
    return f"{number:.3f}{suffix}"


def _fmt_int(value: Any) -> str:
    if value is None:
        return NOT_MEASURED
    return str(int(value))


def _arm_status_rows(
    adapters: list[dict[str, Any]],
    metrics: Mapping[str, dict[str, Any]],
    not_run: Mapping[str, str],
) -> list[str]:
    rows: list[str] = []
    known = set()
    for info in adapters:
        adapter_id = str(info.get("adapter_id"))
        known.add(adapter_id)
        backend = _md(info.get("backend", ""))
        display = _md(info.get("display_name", adapter_id))
        if adapter_id in metrics:
            rows.append(f"| `{adapter_id}` | {display} | {backend} | RUN |")
        elif adapter_id in not_run:
            # Literal "NOT RUN: <reason>" so a reader (and the report test) can see
            # exactly why an arm has no number, with no metric cells invented.
            rows.append(
                f"| `{adapter_id}` | {display} | {backend} | "
                f"NOT RUN: {_md(not_run[adapter_id])} |"
            )
        else:
            raise ValueError(
                f"adapter {adapter_id!r} has neither a metric report nor a NOT RUN reason; "
                "refusing to write a report that omits it silently"
            )
    for adapter_id in metrics:
        if adapter_id not in known:
            rows.append(f"| `{adapter_id}` | {adapter_id} | | RUN (not described in manifest) |")
    return rows


def _metrics_table(metrics: Mapping[str, dict[str, Any]]) -> list[str]:
    lines = [
        "| Adapter | Support | TP | FP | FN | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for adapter_id, report in metrics.items():
        lines.append(
            "| `{id}` | {support} | {tp} | {fp} | {fn} | {p} | {r} | {f1} |".format(
                id=_md(adapter_id),
                support=_fmt_int(report.get("support")),
                tp=_fmt_int(report.get("tp")),
                fp=_fmt_int(report.get("fp")),
                fn=_fmt_int(report.get("fn")),
                p=_fmt_rate(report.get("precision")),
                r=_fmt_rate(report.get("recall")),
                f1=_fmt_rate(report.get("f1")),
            )
        )
    return lines


def _field_metrics_table(metrics: Mapping[str, dict[str, Any]]) -> list[str]:
    lines = [
        "| Adapter | Entity acc. | Event-date acc. | Published-at acc. | Citation correct "
        "| Abstention | Wrong abstention | False assertion | Parse failure |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for adapter_id, report in metrics.items():
        lines.append(
            "| `{id}` | {entity} | {date} | {pub} | {cite} | {abst} | {wrong} | {false} | {parse} |".format(
                id=_md(adapter_id),
                entity=_fmt_rate(report.get("entity_match_accuracy")),
                date=_fmt_rate(report.get("event_date_accuracy")),
                pub=_fmt_rate(report.get("published_at_accuracy")),
                cite=_fmt_rate(report.get("citation_correctness_rate")),
                abst=_fmt_rate(report.get("abstention_rate")),
                wrong=_fmt_rate(report.get("wrong_abstention_rate")),
                false=_fmt_rate(report.get("false_assertion_rate")),
                parse=_fmt_rate(report.get("parse_failure_rate")),
            )
        )
    return lines


def _per_category_section(adapter_id: str, report: Mapping[str, Any]) -> list[str]:
    per_category = report.get("per_category") or {}
    if not per_category:
        return [f"`{adapter_id}`: no per-category data.", ""]
    lines = [
        f"**`{adapter_id}`**",
        "",
        "| Category | Gold | Predicted | TP | FP | FN | Precision | Recall |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for category, stats in per_category.items():
        lines.append(
            "| {category} | {gold} | {pred} | {tp} | {fp} | {fn} | {p} | {r} |".format(
                category=_md(category),
                gold=_fmt_int(stats.get("gold")),
                pred=_fmt_int(stats.get("predicted")),
                tp=_fmt_int(stats.get("tp")),
                fp=_fmt_int(stats.get("fp")),
                fn=_fmt_int(stats.get("fn")),
                p=_fmt_rate(stats.get("precision")),
                r=_fmt_rate(stats.get("recall")),
            )
        )
    lines.append("")
    return lines


def _per_source_section(adapter_id: str, report: Mapping[str, Any]) -> list[str]:
    per_source = report.get("per_source_type") or {}
    if not per_source:
        return []
    lines = [
        f"**`{adapter_id}`** by source type",
        "",
        "| Source type | Gold | Predicted | TP | FP | FN |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for source_type, stats in per_source.items():
        lines.append(
            "| {source} | {gold} | {pred} | {tp} | {fp} | {fn} |".format(
                source=_md(source_type),
                gold=_fmt_int(stats.get("gold")),
                pred=_fmt_int(stats.get("predicted")),
                tp=_fmt_int(stats.get("tp")),
                fp=_fmt_int(stats.get("fp")),
                fn=_fmt_int(stats.get("fn")),
            )
        )
    lines.append("")
    return lines


def _per_arm_summary(adapter_id: str, report: Mapping[str, Any]) -> list[str]:
    """One compact table per arm (a reader can paste a single arm's numbers)."""
    rows: list[tuple[str, str]] = [
        ("support (documents with a prediction record)", _fmt_int(report.get("support"))),
        ("tp / fp / fn", f"{_fmt_int(report.get('tp'))} / {_fmt_int(report.get('fp'))} / {_fmt_int(report.get('fn'))}"),
        ("precision", _fmt_rate(report.get("precision"))),
        ("recall", _fmt_rate(report.get("recall"))),
        ("f1", _fmt_rate(report.get("f1"))),
        ("entity match accuracy", _fmt_rate(report.get("entity_match_accuracy"))),
        ("event-date accuracy", _fmt_rate(report.get("event_date_accuracy"))),
        ("published-at accuracy", _fmt_rate(report.get("published_at_accuracy"))),
        ("citation correctness", _fmt_rate(report.get("citation_correctness_rate"))),
        ("abstention rate", _fmt_rate(report.get("abstention_rate"))),
        ("wrong abstention rate", _fmt_rate(report.get("wrong_abstention_rate"))),
        ("false assertion rate", _fmt_rate(report.get("false_assertion_rate"))),
        ("parse failure rate", _fmt_rate(report.get("parse_failure_rate"))),
    ]
    lines = [f"**`{adapter_id}`**", "", "| Metric | Value |", "|---|---:|"]
    for label, value in rows:
        lines.append(f"| {_md(label)} | {value} |")
    lines.append("")
    return lines


def _taxonomy_section(metrics: Mapping[str, dict[str, Any]]) -> list[str]:
    lines = [
        "| Adapter | Error | Count |",
        "|---|---|---:|",
    ]
    any_row = False
    for adapter_id, report in metrics.items():
        taxonomy = report.get("error_taxonomy") or {}
        for error, count in taxonomy.items():
            if not count:
                continue
            any_row = True
            lines.append(f"| `{_md(adapter_id)}` | {_md(error)} | {_fmt_int(count)} |")
    if not any_row:
        lines = ["No error-taxonomy entries: no false positives, false negatives or parse failures were observed."]
    lines.append("")
    return lines


def _resources_section(resources: Mapping[str, Any]) -> list[str]:
    if not resources:
        return ["No resource measurements were recorded.", ""]
    lines = [
        "| Adapter | Wall (s) | CPU (s) | Peak RSS (MB) | Peak VRAM (MB) | Tokens in | "
        "Tokens out | Est. cost (USD) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for adapter_id, resource in resources.items():
        if not isinstance(resource, Mapping):
            lines.append(f"| `{_md(adapter_id)}` | {NOT_MEASURED} | {NOT_MEASURED} | {NOT_MEASURED} | {NOT_MEASURED} | {NOT_MEASURED} | {NOT_MEASURED} | {NOT_MEASURED} |")
            continue
        if resource.get("status") == "NOT_RUN":
            lines.append(
                f"| `{_md(adapter_id)}` | NOT RUN; not measured | | | | | | |"
            )
            continue
        lines.append(
            "| `{id}` | {wall} | {cpu} | {rss} | {vram} | {tin} | {tout} | {cost} |".format(
                id=_md(adapter_id),
                wall=_fmt_number(resource.get("wall_time_s")),
                cpu=_fmt_number(resource.get("cpu_time_s")),
                rss=_fmt_number(resource.get("peak_rss_mb")),
                vram=_fmt_number(resource.get("peak_vram_mb")),
                tin=_fmt_int(resource.get("tokens_in")),
                tout=_fmt_int(resource.get("tokens_out")),
                cost=_fmt_number(resource.get("estimated_cost_usd")),
            )
        )
    lines.append("")
    lines.append("`not measured` is a real value: the backend did not report it (no tokenizer, no GPU, remote arm). It is never rendered as zero.")
    lines.append("")
    return lines


def _rules_section(adapters: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for info in adapters:
        rules = info.get("rules")
        if not rules:
            continue
        lines.append(f"Arm `{_md(info.get('adapter_id'))}` rule table (`rules-v1`, deterministic):")
        lines.append("")
        for rule in rules:
            patterns = ", ".join(f"`{_md(pattern)}`" for pattern in rule.get("patterns", []))
            lines.append(
                f"- `{_md(rule.get('category'))}`: {_md(rule.get('description', ''))} "
                f"(patterns: {patterns})"
            )
        lines.append("")
    return lines


def _matching_protocol_section(metrics: Mapping[str, dict[str, Any]]) -> list[str]:
    protocol: Mapping[str, Any] | None = None
    for report in metrics.values():
        candidate = report.get("matching_protocol")
        if isinstance(candidate, Mapping):
            protocol = candidate
            break
    if protocol is None:
        return ["No matching protocol was recorded (no arm produced a metric report).", ""]
    lines = [f"Scoring protocol version: `{_md(protocol.get('version'))}`", ""]
    for key, value in protocol.items():
        if key == "version":
            continue
        if isinstance(value, (list, tuple)):
            rendered = "; ".join(_md(item) for item in value)
        elif isinstance(value, Mapping):
            rendered = ", ".join(f"{_md(k)}={_md(v)}" for k, v in value.items())
        else:
            rendered = _md(value)
        lines.append(f"- **{_md(key)}**: {rendered}")
    lines.append("")
    return lines


def write_report(
    run_dir: str | Path,
    manifest: Any,
    metrics_by_adapter: Mapping[str, Any],
) -> Path:
    """Write ``run_dir/REPORT.md`` and return its path."""
    run_path = Path(run_dir)
    manifest_dict = _as_dict(manifest)
    status = str(manifest_dict.get("status") or "")
    if status not in RUN_STATUSES:  # pragma: no cover - runner guarantees this
        raise ValueError(f"unknown run status {status!r}")
    dataset = manifest_dict.get("dataset") or {}
    tiers = dataset.get("label_tiers") or []
    if status == "RESEARCH_GRADE" and not is_research_grade(tiers):
        raise ValueError(
            "refusing to write a research-grade report for label tiers "
            f"{sorted(set(tiers))}; only {sorted(('human_confirmed', 'expert_adjudicated'))} "
            "are research grade"
        )
    research_grade = status == "RESEARCH_GRADE" and is_research_grade(tiers)

    metrics: dict[str, dict[str, Any]] = {}
    for adapter_id, report in metrics_by_adapter.items():
        if report is None:
            continue
        metrics[str(adapter_id)] = _as_dict(report)

    adapter_block = manifest_dict.get("adapter") or {}
    adapters = list(adapter_block.get("adapters") or [])
    not_run = dict(adapter_block.get("not_run") or {})
    # A NOT RUN reason may also live in the metrics payload; keep one source.
    for adapter_id, payload in (manifest_dict.get("metrics") or {}).items():
        if isinstance(payload, Mapping) and payload.get("status") == "NOT_RUN":
            not_run.setdefault(str(adapter_id), str(payload.get("reason", "")))

    resources = dict(manifest_dict.get("resources") or {})
    config = manifest_dict.get("config") or {}
    config_summary = config.get("config") if isinstance(config.get("config"), Mapping) else {}

    lines: list[str] = []
    lines.append("# Local small-LM event extraction - benchmark report")
    lines.append("")
    if not research_grade:
        lines.append(f"> **{SYNTHETIC_BANNER}.**")
        lines.append(">")
        lines.append(
            "> Every number in this report was computed on hand-written synthetic fixtures or "
            "on a scripted test double. The fixtures exist to prove that the harness runs, can "
            "be resumed and cannot lie about what it measured. They are not a sample of real "
            "documents, they are not human labels, and none of these numbers may be quoted as "
            "an empirical result about any model."
        )
        lines.append("")
    lines.append(f"Run `{_md(manifest_dict.get('run_id'))}` - status: **{_md(status)}**")
    lines.append("")
    lines.append("## Run identity")
    lines.append("")
    lines.append(f"- run_id: `{_md(manifest_dict.get('run_id'))}`")
    lines.append(f"- created_at (UTC): {_md(manifest_dict.get('created_at'))}")
    lines.append(f"- status: `{_md(status)}`")
    lines.append(
        f"- dataset: `{_md(dataset.get('name'))}` version `{_md(dataset.get('version'))}`; "
        f"{_fmt_int(dataset.get('case_count'))} cases; label tiers {sorted(set(tiers))}"
    )
    lines.append(
        f"- dataset sha256: `{_md(dataset.get('dataset_sha256'))}` "
        f"(source files: `{_md(dataset.get('source_sha256'))}`)"
    )
    splits = dataset.get("splits") or {}
    if splits:
        lines.append("- cases per split: " + ", ".join(f"{k}={v}" for k, v in splits.items()))
    lines.append(f"- seeds: {list(manifest_dict.get('seeds') or [])}")
    git = manifest_dict.get("git") or {}
    lines.append(
        f"- git: commit `{_md(git.get('commit'))}`, branch `{_md(git.get('branch'))}`, "
        f"dirty={git.get('dirty')}"
    )
    lines.append(f"- config sha256: `{_md(manifest_dict.get('config_sha256'))}`")
    for note in manifest_dict.get("notes") or []:
        lines.append(f"- note: {_md(note)}")
    if config_summary:
        lines.append(f"- config: `{_md(config_summary)}`")
    lines.append("")
    lines.append("## Arms")
    lines.append("")
    lines.append("| Adapter | Display name | Backend | Status / reason |")
    lines.append("|---|---|---|---|")
    lines.extend(_arm_status_rows(adapters, metrics, not_run))
    lines.append("")
    if metrics:
        lines.append("## Event-level metrics (micro, over events)")
        lines.append("")
        lines.extend(_metrics_table(metrics))
        lines.append("")
        lines.append("## Field and failure metrics")
        lines.append("")
        lines.extend(_field_metrics_table(metrics))
        lines.append("")
        lines.append("## Per-arm summary")
        lines.append("")
        for adapter_id, report in metrics.items():
            lines.extend(_per_arm_summary(adapter_id, report))
        lines.append("## Per-category metrics")
        lines.append("")
        for adapter_id, report in metrics.items():
            lines.extend(_per_category_section(adapter_id, report))
        lines.append("## Per-source-type metrics")
        lines.append("")
        for adapter_id, report in metrics.items():
            lines.extend(_per_source_section(adapter_id, report))
        lines.append("## Error taxonomy")
        lines.append("")
        lines.extend(_taxonomy_section(metrics))
    else:
        lines.append("## Metrics")
        lines.append("")
        lines.append("No arm produced a metric report. Gated arms are reported as NOT RUN above; "
                     "this run contains no score at all, which is the correct outcome.")
        lines.append("")
    lines.append("## Measured resources")
    lines.append("")
    lines.extend(_resources_section(resources))
    lines.append("## Matching protocol")
    lines.append("")
    lines.extend(_matching_protocol_section(metrics))
    lines.extend(_rules_section(adapters))
    lines.append("## What this does not show")
    lines.append("")
    lines.append("- It does not show how any model performs on real medtech documents. "
                 "The documents are hand-written synthetic fixtures.")
    lines.append("- It does not show whether local small models beat the rule baseline in "
                 "production; no model was loaded for this run.")
    lines.append("- It does not contain human-confirmed labels. Label tiers recorded above: "
                 f"{sorted(set(tiers))}.")
    lines.append("- It does not estimate cost or latency of a real local deployment. "
                 "Wall/CPU/RSS numbers are for this process on this machine and only for the "
                 "cases that actually ran.")
    lines.append("- It does not validate the rule table against an external corpus; the rule "
                 "table is included only so arm A's behaviour is inspectable.")
    lines.append("- It does not turn `not measured` into zero: any field rendered as "
                 "`not measured` was genuinely unavailable, and a zero denominator is `None` "
                 "in `metrics.json`, never `0.0`.")
    lines.append("- Arm A's scores on this fixture set are partly a property of the fixtures: "
                 "several sentences were written deliberately in the keyword style the rule "
                 "table targets, and the synthetic roster aliases were supplied to arm A. "
                 "That is not a field accuracy estimate.")
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    lines.append(f"- `predictions.jsonl` - one record per (adapter, case), appended live")
    lines.append(f"- `metrics.json` - per-adapter metric reports and NOT RUN reasons")
    lines.append(f"- `manifest.json` - dataset/adapter/git/config identity and resources")
    lines.append("")

    report_path = run_path / "REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


__all__ = ["NOT_MEASURED", "SYNTHETIC_BANNER", "write_report"]
