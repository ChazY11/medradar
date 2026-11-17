"""Measure the relevance assessment against a frozen, independently labelled sample.

Single command, one source of truth: it reads a labelled sample and a read-only ledger, runs
the production classifier (medradar.radar.relevance.classify_observation), and writes
machine-readable metrics. The Markdown report is generated from the same JSON, so a number in
prose cannot drift from the JSON that produced it (QA-002 finding: they did).

Usage:

    python scripts/evaluate_relevance.py --data-dir data/radar \
        --labels docs/refoundation/004/quality/independent-sample.json \
        --json docs/refoundation/004/quality/quality-after.json \
        --markdown docs/refoundation/004/quality/QUALITY_AFTER.md

    python scripts/evaluate_relevance.py --check ...   # fail if JSON/Markdown disagree
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from medradar.radar.relevance import ADMISSION_VERSION, classify_observation

FEED_WINDOW_DAYS = 30
FEED_TIERS = ("HIGH_RELEVANCE",)
LABELS = ("DIRECT", "TRANSFER", "CLINICAL", "MEDICAL_UNRELATED", "NON_MEDICAL")


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> list | None:
    """95% Wilson score interval; None when there is no denominator."""
    if total <= 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)]


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def load_rows(db: Path, ids: list) -> dict:
    con = sqlite3.connect("file:" + db.as_posix() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    facets: dict = {}
    for row in con.execute("SELECT observation_id, kind, value FROM observation_facet"):
        entry = facets.setdefault(row["observation_id"], {"topic": [], "product": [], "organization": []})
        entry.setdefault(row["kind"], []).append(row["value"])
    rows: dict = {}
    chunk = 400
    for start in range(0, len(ids), chunk):
        batch = ids[start:start + chunk]
        placeholders = ",".join("?" * len(batch))
        sql = (
            "SELECT o.observation_id, o.source, o.record_type, o.title, o.published_at,"
            " o.published_at_precision, o.event_at, o.event_at_precision, o.first_observed_at,"
            " v.payload"
            " FROM observation o JOIN observation_version v ON v.version_id=o.latest_version_id"
            " WHERE o.observation_id IN (" + placeholders + ")"
        )
        for row in con.execute(sql, tuple(batch)):
            payload = json.loads(row["payload"] or "{}")
            mapped = facets.get(row["observation_id"], {})
            rows[row["observation_id"]] = {
                "observation_id": row["observation_id"],
                "source": row["source"],
                "record_type": row["record_type"],
                "title": row["title"],
                "published_at": row["published_at"],
                "published_at_precision": row["published_at_precision"],
                "event_at": row["event_at"],
                "event_at_precision": row["event_at_precision"],
                "first_observed_at": row["first_observed_at"],
                "payload": payload,
                "mapped_topics": mapped.get("topic", []),
                "mapped_products": mapped.get("product", []),
            }
    con.close()
    return rows


def classify(row: dict):
    return classify_observation(
        {"record_type": row["record_type"], "title": row["title"], "payload": row["payload"]},
        mapped_topics=row.get("mapped_topics"),
        mapped_products=row.get("mapped_products"),
    )


def feed_eligible(admission) -> bool:
    return admission.tier in FEED_TIERS


def label_of(admission) -> str:
    dimensions = getattr(admission, "dimensions", None) or {}
    return str(dimensions.get("monitoring_relevance") or admission.category)


def build_metrics(sample: dict, rows: dict) -> dict:
    items = sample["items"]
    missing = [item["observation_id"] for item in items if item["observation_id"] not in rows]
    evaluated = [item for item in items if item["observation_id"] in rows]
    records = []
    for item in evaluated:
        row = rows[item["observation_id"]]
        admission = classify(row)
        records.append({
            "observation_id": item["observation_id"],
            "stratum": item.get("stratum"),
            "source": row["source"],
            "record_type": row["record_type"],
            "title": row["title"],
            "label": item["label"],
            "label_feed_eligible": bool(item.get("feed_eligible")),
            "rationale": item.get("rationale"),
            "predicted_tier": admission.tier,
            "predicted_category": admission.category,
            "predicted_dimensions": getattr(admission, "dimensions", None) or {},
            "predicted_feed_eligible": feed_eligible(admission),
            "predicted_label": label_of(admission),
            "reasons": admission.reasons,
        })
    tp = sum(1 for r in records if r["label_feed_eligible"] and r["predicted_feed_eligible"])
    fp = sum(1 for r in records if not r["label_feed_eligible"] and r["predicted_feed_eligible"])
    fn = sum(1 for r in records if r["label_feed_eligible"] and not r["predicted_feed_eligible"])
    tn = sum(1 for r in records if not r["label_feed_eligible"] and not r["predicted_feed_eligible"])
    precision = ratio(tp, tp + fp)
    recall = ratio(tp, tp + fn)
    binary = {
        "labelled_positive": tp + fn,
        "predicted_positive": tp + fp,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "precision": precision,
        "precision_wilson95": wilson(tp, tp + fp),
        "recall": recall,
        "recall_wilson95": wilson(tp, tp + fn),
        "specificity": ratio(tn, tn + fp),
        "note": "N/A appears as null, never as 100 percent: a metric with no denominator is not a success.",
    }
    confusion: dict = {label: {other: 0 for other in LABELS} for label in LABELS}
    for record in records:
        label = record["label"]
        predicted = record["predicted_label"]
        if predicted not in LABELS:
            predicted = "MEDICAL_UNRELATED"
        confusion.setdefault(label, {other: 0 for other in LABELS})
        confusion[label][predicted] = confusion[label].get(predicted, 0) + 1
    per_class = {}
    for label in LABELS:
        total = sum(confusion.get(label, {}).values())
        hit = confusion.get(label, {}).get(label, 0)
        per_class[label] = {"n": total, "recall": ratio(hit, total), "recall_wilson95": wilson(hit, total)}
    by_source: dict = {}
    for source in sorted({r["source"] for r in records}):
        subset = [r for r in records if r["source"] == source]
        s_tp = sum(1 for r in subset if r["label_feed_eligible"] and r["predicted_feed_eligible"])
        s_fp = sum(1 for r in subset if not r["label_feed_eligible"] and r["predicted_feed_eligible"])
        s_fn = sum(1 for r in subset if r["label_feed_eligible"] and not r["predicted_feed_eligible"])
        by_source[source] = {
            "n": len(subset),
            "labelled_positive": s_tp + s_fn,
            "predicted_positive": s_tp + s_fp,
            "precision": ratio(s_tp, s_tp + s_fp),
            "recall": ratio(s_tp, s_tp + s_fn),
            "precision_wilson95": wilson(s_tp, s_tp + s_fp),
            "recall_wilson95": wilson(s_tp, s_tp + s_fn),
        }
    by_stratum: dict = {}
    for stratum in sorted({str(r["stratum"]) for r in records}):
        subset = [r for r in records if str(r["stratum"]) == stratum]
        by_stratum[stratum] = {
            "n": len(subset),
            "labelled_positive": sum(1 for r in subset if r["label_feed_eligible"]),
            "predicted_positive": sum(1 for r in subset if r["predicted_feed_eligible"]),
        }
    false_accepts = [
        {"observation_id": r["observation_id"], "source": r["source"], "title": r["title"],
         "label": r["label"], "category": r["predicted_category"], "rationale": r["rationale"],
         "reasons": r["reasons"]}
        for r in records if r["predicted_feed_eligible"] and not r["label_feed_eligible"]
    ]
    false_rejects = [
        {"observation_id": r["observation_id"], "source": r["source"], "title": r["title"],
         "label": r["label"], "predicted_tier": r["predicted_tier"],
         "category": r["predicted_category"], "rationale": r["rationale"], "reasons": r["reasons"]}
        for r in records if r["label_feed_eligible"] and not r["predicted_feed_eligible"]
    ]
    return {
        "schema": "medradar.quality.relevance-eval.v2",
        "admission_version": ADMISSION_VERSION,
        "sample": {
            "version": sample.get("version"),
            "sha256_items": sample.get("sha256_items"),
            "size": len(items),
            "evaluated": len(records),
            "missing_from_ledger": missing,
            "labelled_by": sample.get("labelled_by"),
            "sampling_frame": sample.get("sampling_frame"),
            "label_rule": sample.get("label_rule"),
        },
        "window": {
            "feed_window_days": FEED_WINDOW_DAYS,
            "note": "The evaluator and the product default feed both use 30 days; QA-002 found the development evaluator used 14.",
        },
        "binary": binary,
        "five_class": {"labels": list(LABELS), "confusion": confusion, "per_class": per_class},
        "by_source": by_source,
        "by_stratum": by_stratum,
        "label_counts": dict(Counter(r["label"] for r in records)),
        "predicted_tier_counts": dict(Counter(r["predicted_tier"] for r in records)),
        "false_accepts": false_accepts,
        "false_rejects": false_rejects,
        "records": records,
    }


def default_feed(db: Path, *, now: str, limit: int = 40) -> dict:
    """The exact default feed the product serves: the stored FEED decisions inside the window.

    It reads the admission projection and the ledger, not a fresh in-memory classification, so
    this number describes what a user sees. Coarse date precision is compared on the date part
    only (the earliest instant a month/year-precision date can denote), never on a fabricated
    midnight timestamp.
    """
    con = sqlite3.connect("file:" + db.as_posix() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT o.observation_id, o.source, o.title, o.published_at, o.event_at,"
            " o.published_at_precision, o.event_at_precision, a.tier, a.category, a.decision,"
            " a.dimensions"
            " FROM observation_admission_latest a"
            " JOIN observation o ON o.observation_id = a.observation_id"
            " WHERE a.admission_version = ? AND a.decision = 'FEED'",
            (ADMISSION_VERSION,),
        ).fetchall()
        projection_version = con.execute(
            "SELECT MAX(admission_version) FROM observation_admission"
        ).fetchone()[0]
    finally:
        con.close()
    moment = datetime.fromisoformat(now.replace("Z", "+00:00"))
    cutoff_date = (moment - timedelta(days=FEED_WINDOW_DAYS)).date().isoformat()
    selected = []
    for row in rows:
        stamp = row["published_at"] or row["event_at"]
        if not stamp or stamp[:10] < cutoff_date:
            continue
        dimensions = {}
        try:
            dimensions = json.loads(row["dimensions"] or "{}")
        except ValueError:
            dimensions = {}
        selected.append({
            "observation_id": row["observation_id"],
            "source": row["source"],
            "title": row["title"],
            "published_at": row["published_at"],
            "event_at": row["event_at"],
            "tier": row["tier"],
            "category": row["category"],
            "label": dimensions.get("monitoring_relevance"),
            "importance": dimensions.get("importance"),
        })
    selected.sort(key=lambda item: (item["published_at"] or item["event_at"] or ""), reverse=True)
    return {"window_days": FEED_WINDOW_DAYS, "now": now, "count": len(selected),
            "limit": limit, "items": selected[:limit],
            "projection_versions": projection_version}


def render_markdown(metrics: dict) -> str:
    binary = metrics["binary"]
    feed = metrics.get("default_feed") or {}
    lines: list = []
    add = lines.append
    add("# Relevance quality - generated report")
    add("")
    add("> Generated by scripts/evaluate_relevance.py from the JSON beside it. Do not edit by hand:")
    add("> the command regenerates this file from the same machine-readable metrics.")
    add("")
    add("- Assessment version: " + str(metrics["admission_version"]))
    add("- Sample: " + str(metrics["sample"]["version"]) + " (" + str(metrics["sample"]["size"])
        + " records, " + str(metrics["sample"]["evaluated"]) + " found in the ledger)")
    add("- Sample digest: " + str(metrics["sample"]["sha256_items"]))
    add("- Labelled by: " + str(metrics["sample"]["labelled_by"]))
    add("- Feed window: " + str(metrics["window"]["feed_window_days"]) + " days (product default)")
    add("")
    add("## Feed-relevant precision and recall")
    add("")
    add("| Metric | Value | 95% Wilson interval | Denominator |")
    add("| --- | --- | --- | --- |")
    add("| Precision | " + str(binary["precision"] if binary["precision"] is not None else "n/a")
        + " | " + str(binary["precision_wilson95"] or "n/a") + " | " + str(binary["predicted_positive"]) + " |")
    add("| Recall | " + str(binary["recall"] if binary["recall"] is not None else "n/a")
        + " | " + str(binary["recall_wilson95"] or "n/a") + " | " + str(binary["labelled_positive"]) + " |")
    add("| Specificity | " + str(binary["specificity"] if binary["specificity"] is not None else "n/a")
        + " | - | " + str(binary["true_negative"] + binary["false_positive"]) + " |")
    add("")
    add("Confusion (feed-relevant): TP " + str(binary["true_positive"]) + ", FP " + str(binary["false_positive"])
        + ", FN " + str(binary["false_negative"]) + ", TN " + str(binary["true_negative"]) + ".")
    add("")
    add("## Five-class agreement")
    add("")
    add("| Label | n | Recall | 95% Wilson |")
    add("| --- | --- | --- | --- |")
    for label in metrics["five_class"]["labels"]:
        row = metrics["five_class"]["per_class"][label]
        add("| " + label + " | " + str(row["n"]) + " | "
            + str(row["recall"] if row["recall"] is not None else "n/a") + " | "
            + str(row["recall_wilson95"] or "n/a") + " |")
    add("")
    add("## Per source")
    add("")
    add("| Source | n | Labelled + | Predicted + | Precision | Recall |")
    add("| --- | --- | --- | --- | --- | --- |")
    for source, row in metrics["by_source"].items():
        add("| " + source + " | " + str(row["n"]) + " | " + str(row["labelled_positive"]) + " | "
            + str(row["predicted_positive"]) + " | "
            + str(row["precision"] if row["precision"] is not None else "n/a") + " | "
            + str(row["recall"] if row["recall"] is not None else "n/a") + " |")
    add("")
    add("## Errors")
    add("")
    add("### False accepts (" + str(len(metrics["false_accepts"])) + ")")
    add("")
    if metrics["false_accepts"]:
        add("| Source | Title | Label | Predicted category |")
        add("| --- | --- | --- | --- |")
        for row in metrics["false_accepts"]:
            add("| " + row["source"] + " | " + row["title"][:110] + " | " + row["label"] + " | " + row["category"] + " |")
    else:
        add("None in this sample.")
    add("")
    add("### False rejects (" + str(len(metrics["false_rejects"])) + ")")
    add("")
    if metrics["false_rejects"]:
        add("| Source | Title | Label | Predicted | Category |")
        add("| --- | --- | --- | --- | --- |")
        for row in metrics["false_rejects"]:
            add("| " + row["source"] + " | " + row["title"][:110] + " | " + row["label"] + " | "
                + row["predicted_tier"] + " | " + row["category"] + " |")
    else:
        add("None in this sample.")
    add("")
    add("## Default feed composition")
    add("")
    add(str(feed.get("count", 0)) + " feed-eligible records inside " + str(feed.get("window_days"))
        + " days as of " + str(feed.get("now")) + "; the first " + str(len(feed.get("items") or [])) + " are listed.")
    add("")
    add("| Published/event | Source | Title | Category |")
    add("| --- | --- | --- | --- |")
    for row in (feed.get("items") or []):
        add("| " + str(row["published_at"] or row["event_at"]) + " | " + row["source"] + " | "
            + row["title"][:90] + " | " + row["category"] + " |")
    add("")
    add("## Limits of this measurement")
    add("")
    frame = metrics["sample"].get("sampling_frame") or {}
    add("- " + str(frame.get("inference_limit", "See the sample metadata.")))
    add("- Labels are a single reviewer adjudication against a frozen rule, not an independent panel.")
    add("- The sample is drawn from one corpus snapshot: it measures how the rules treat records like")
    add("  these, not how good the product is for every topic.")
    add("- Wilson intervals are reported because a 120-item sample has a wide interval.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure relevance against a frozen labelled sample")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--json", default="")
    parser.add_argument("--markdown", default="")
    parser.add_argument("--now", default=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    db = Path(args.data_dir) / "radar.db"
    sample = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    ids = [item["observation_id"] for item in sample["items"]]
    rows = load_rows(db, ids)
    metrics = build_metrics(sample, rows)
    metrics["default_feed"] = default_feed(db, now=args.now)
    text = json.dumps(metrics, ensure_ascii=False, indent=1, sort_keys=True)
    markdown = render_markdown(metrics)
    if args.check:
        ok = True
        if args.json:
            on_disk = Path(args.json).read_text(encoding="utf-8").strip()
            if on_disk != text.strip():
                print("STALE: " + args.json + " does not match a fresh computation")
                ok = False
        if args.markdown:
            on_disk = Path(args.markdown).read_text(encoding="utf-8").strip()
            if on_disk != markdown.strip():
                print("STALE: " + args.markdown + " does not match a fresh generation")
                ok = False
        return 0 if ok else 1
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(text + "\n", encoding="utf-8")
    if args.markdown:
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text(markdown, encoding="utf-8")
    summary = {key: metrics[key] for key in ("binary", "five_class", "by_source")}
    print(json.dumps(summary, ensure_ascii=False, indent=1)[:4000])
    print("default feed:", (metrics.get("default_feed") or {}).get("count"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
