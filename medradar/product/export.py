"""Export the analysis without losing its provenance.

Every export reproduces the exact filtered set and basis shown on screen:

* CSV: one row per regulatory record, with the official identifier, the official record URL,
  the four time fields, attribution state, category, source and snapshot identity;
* Markdown: comparison report and organization brief with warnings, coverage, counting rule
  and a source list.

Nothing is added that is not in the API response, and nothing shown on screen is omitted.
"""
from __future__ import annotations

import base64
import csv
import io
import json
from typing import Any, Iterable, Sequence

from .compare import build_compare
from .dataset import (
    EVENT_TYPE_LABELS,
    EVENT_TYPE_ORDER,
    SOURCE_NAMES,
    Dataset,
    Event,
)

CSV_COLUMNS = [
    "event_id",
    "official_id",
    "source_id",
    "source_name",
    "official_url",
    "event_date",
    "published_at",
    "published_at_status",
    "first_observed_at",
    "available_at",
    "time_quality",
    "event_type",
    "organization_key",
    "organization_name",
    "applicant_name",
    "attribution_status",
    "attribution_basis",
    "attribution_review",
    "attribution_verification",
    "attribution_verified",
    "attribution_rule",
    "attribution_evidence_count",
    "attribution_reviewer",
    "attribution_reviewer_kind",
    "attribution_predecessor_entity",
    "historical_owner_state",
    "historical_owner_reason",
    "historical_owner",
    "historical_owner_relation",
    "historical_owner_effective_from",
    "ownership_basis",
    "product_code",
    "category",
    "device_class",
    "device_name",
    "title",
    "summary",
    "snapshot_id",
    "collected_at",
]


def csv_filename(dataset: Dataset) -> str:
    stamp = str(dataset.collected_at)[:10] or "snapshot"
    return "medradar-events-" + stamp + ".csv"


def provenance_header(dataset: Dataset, filters: dict[str, Any]) -> str:
    payload = {
        "snapshot_id": dataset.snapshot_id,
        "collected_at": dataset.collected_at,
        "product": "MedRadar PRODUCT-002",
        "filters": filters,
        "metrics": dataset.metrics_summary(),
        "note": "Counts are regulatory records, not products or innovations. Applicable 510(k)/PMA records have no publication timestamp in openFDA. attribution_verification states the strength of the claim behind each row; curated means evidence-verified or human-reviewed only.",
    }
    return base64.urlsafe_b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")


def events_csv(dataset: Dataset, events: Sequence[Event], basis: str | None = None) -> str:
    buffer = io.StringIO()
    buffer.write("﻿")  # UTF-8 BOM so spreadsheet tools detect the encoding
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for event in events:
        writer.writerow([
            event.event_id,
            event.official_id,
            event.source_id,
            SOURCE_NAMES.get(event.source_id, event.source_id),
            event.official_url,
            event.event_date or "",
            event.published_at or "",
            event.published_at_status,
            event.first_observed_at,
            event.available_at,
            event.time_quality,
            event.event_type,
            event.organization_key or "",
            event.organization_name or "",
            event.applicant_name,
            event.attribution_status,
            event.attribution_basis or "",
            event.attribution_review or "",
            event.attribution_verification,
            "true" if event.attribution_verified else "false",
            event.attribution_rule or "",
            str(event.attribution_evidence_count),
            event.attribution_reviewer or "",
            event.attribution_reviewer_kind or "",
            "true" if event.attribution_is_predecessor else "false",
            event.historical_owner_state,
            event.historical_owner_reason,
            event.historical_owner_display or "",
            event.historical_owner_relation_id or "",
            event.historical_owner_effective_from or "",
            basis or "current_group",
            event.product_code or "",
            event.category.label if event.category else "",
            event.device_class or "",
            event.device_name or "",
            event.title,
            event.summary or "",
            dataset.snapshot_id,
            dataset.collected_at,
        ])
    return buffer.getvalue()


def _escape_md(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(_escape_md(header) for header in headers) + " |"]
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(_escape_md(cell) for cell in row) + " |")
    return "\n".join(lines)


def compare_markdown_filename(keys: Sequence[str], dataset: Dataset) -> str:
    stamp = str(dataset.collected_at)[:10] or "snapshot"
    return "medradar-comparison-" + "-".join(keys) + "-" + stamp + ".md"


def compare_markdown(dataset: Dataset, keys: Sequence[str], date_from: str | None, date_to: str | None,
                     event_types: Sequence[str] | None, basis: str | None = None, review: str | None = None) -> str:
    payload = build_compare(dataset, keys, date_from, date_to, event_types, basis=basis, review=review)
    window = payload["window"]
    sides = payload["organizations"]
    names = [side["display_name"] for side in sides]
    lines: list[str] = []
    lines.append("# MedRadar comparison report: " + " vs ".join(names))
    lines.append("")
    lines.append("Generated by MedRadar PRODUCT-001 from an immutable openFDA snapshot.")
    lines.append("")
    lines.append("- Snapshot: " + str(payload["snapshot"]["id"]))
    lines.append("- Collected at: " + str(payload["snapshot"]["collected_at"]) + " (source last updated: " + str(payload["snapshot"]["openfda_last_updated"] or "unknown") + ")")
    lines.append("- Effective window: " + str(window["effective"]["from"]) + " to " + str(window["effective"]["to"]))
    lines.append("- Complete calendar years used for rates: " + (", ".join(window["complete_years"]) if window["complete_years"] else "none"))
    lines.append("- Counting rule: " + payload["basis"]["rule"])
    lines.append("- Ownership basis: " + payload["comparability"]["ownership_basis"])
    excluded = payload.get("basis_excluded_totals") or {}
    if payload["comparability"]["ownership_basis"] == "historical_owner_verified":
        lines.append(
            "- Excluded by the historical-owner basis: "
            + str(excluded.get("excluded_predecessor_owner", 0))
            + " record(s) owned by a predecessor at event time and "
            + str(excluded.get("excluded_unknown_owner", 0))
            + " record(s) whose owner at event time is UNKNOWN (unknown is reported, not treated as zero)"
        )
    lines.append("- Review filter: " + payload["comparability"]["review_filter"])
    lines.append("- Comparability: " + payload["comparability"]["verdict"])
    lines.append("- Product version: MedRadar PRODUCT-002 (metrics and status vocabulary are part of the output)")
    lines.append("")
    lines.append("> " + payload["disclaimer"])
    lines.append("")
    lines.append("## What this comparison does not show")
    lines.append("")
    for item in payload["not_evidence_of"]:
        lines.append("- " + item)
    lines.append("")
    if payload["warnings"]:
        lines.append("## Warnings")
        lines.append("")
        for warning in payload["warnings"]:
            lines.append("> **" + warning["code"] + "** (" + warning["severity"] + "): " + warning["message"])
            lines.append("")
    lines.append("## Identity and coverage")
    lines.append("")
    rows = []
    for side in sides:
        sources = ", ".join(
            row["source_id"] + " " + str(row["records"])
            for row in side["coverage"]["sources"]
            if row["records"]
        ) or "no source with records"
        rows.append([
            side["display_name"],
            side["legal_name"] or "",
            side["ticker"] or "",
            side["country"] or "",
            str(side["counts"]["records"]),
            sources,
            str(side["coverage"]["pending_review"]),
            str(side["coverage"]["unmapped_category"]),
        ])
    lines.append(_table(["Organization", "Legal name", "Ticker", "Country", "Records", "Records by source", "Pending-review records", "Unclassified records"], rows))
    lines.append("")
    lines.append("## Attribution verification of the compared counts")
    lines.append("")
    lines.append(_table(
        ["Organization", "Attributed records", "Evidence/human verified", "Curated share", "Rule-verified", "Provisional", "Records from predecessor entities"],
        [
            [
                side["display_name"],
                str(side["counts"]["records"]),
                str(side["counts"]["verified_records"]),
                "UNKNOWN" if side["counts"]["curated_share"] is None else format(side["counts"]["curated_share"] * 100, ".1f") + "%",
                str(side["counts"]["rule_verified_records"]),
                str(side["counts"]["provisional"]),
                str(side["historical_ownership"]["records_from_predecessor_entities"]),
            ]
            for side in sides
        ],
    ))
    lines.append("")
    lines.append("Curated share counts only evidence-verified or human-reviewed mappings. Rule-verified mappings are a deterministic name rule, not review, and are reported separately.")
    lines.append("")
    lines.append("## Owner at event time")
    lines.append("")
    lines.append(_table(
        ["Organization", "Records counted", "Owner was this group", "Owner was a predecessor", "Owner UNKNOWN"],
        [
            [
                side["display_name"],
                str(side["counts"]["records"]),
                str(side["historical_ownership"]["verified_current_group"]),
                str(side["historical_ownership"]["verified_predecessor"]),
                str(side["historical_ownership"]["unknown"]),
            ]
            for side in sides
        ],
    ))
    lines.append("")
    lines.append(
        "Owner at event time is derived from verified ownership relations with effective dates. UNKNOWN means no verified "
        "relation, no effective date, or no event date: it is not a zero and not evidence of no activity."
    )
    lines.append("")
    lines.append("## Records by event type")
    lines.append("")
    for row in payload["totals_by_type"]:
        values = {item["org_key"]: item["count"] for item in row["values"]}
        lines.append("- " + row["label"] + ": " + ", ".join(side["display_name"] + " " + str(values.get(side["key"], 0)) for side in sides))
    lines.append("")
    lines.append("## Records by FDA medical specialty")
    lines.append("")
    lines.append(_table(["Category"] + names, [[row["label"]] + [str({item["org_key"]: item["count"] for item in row["values"]}.get(side["key"], 0)) for side in sides] for row in payload["category_matrix"]]))
    lines.append("")
    lines.append("## Records by device class")
    lines.append("")
    lines.append(_table(["Device class"] + names, [[row["label"]] + [str({item["org_key"]: item["count"] for item in row["values"]}.get(side["key"], 0)) for side in sides] for row in payload["class_matrix"]]))
    lines.append("")
    lines.append("## Records per complete calendar year")
    lines.append("")
    totals_header = ["Year"] + [side["display_name"] for side in sides]
    year_rows = []
    for year in window["complete_years"]:
        row = [year]
        for side in sides:
            match = next((item for item in side["per_year_totals"] if item["year"] == year), None)
            row.append(str(match["total"]) if match else "0")
        year_rows.append(row)
    lines.append(_table(totals_header, year_rows))
    lines.append("")
    lines.append("## Share of all tracked records")
    lines.append("")
    share_rows = []
    for event_type in EVENT_TYPE_ORDER:
        if not any(side["counts_by_type"].get(event_type, 0) for side in sides):
            continue
        share_rows.append([
            EVENT_TYPE_LABELS[event_type],
            *[format(side["share_of_all_tracked"].get(event_type, 0.0) * 100, ".1f") + "%" for side in sides],
        ])
    lines.append(_table(["Event type"] + names, share_rows))
    lines.append("")
    lines.append("## Sources")
    lines.append("")
    for source_id in ("openfda_510k", "openfda_pma", "openfda_recall"):
        base = {
            "openfda_510k": "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm",
            "openfda_pma": "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm",
            "openfda_recall": "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm",
        }[source_id]
        lines.append("- " + SOURCE_NAMES[source_id] + ": " + base)
    lines.append("")
    lines.append("## Example records (official pages)")
    lines.append("")
    for side in sides:
        events = dataset.filter_events(org_keys=[side["key"]], event_types=list(event_types or EVENT_TYPE_ORDER), date_from=window["effective"]["from"], date_to=window["effective"]["to"])
        examples = dataset.sort_events(events, "event_date_desc")[:5]
        lines.append("### " + side["display_name"])
        lines.append("")
        for event in examples:
            lines.append("- " + (event.event_date or "undated") + " - " + event.official_id + " - " + (event.device_name or event.title)[:120] + " - " + event.official_url)
        lines.append("")
    return "\n".join(lines)


def organization_markdown_filename(key: str, dataset: Dataset) -> str:
    stamp = str(dataset.collected_at)[:10] or "snapshot"
    return "medradar-organization-" + key + "-" + stamp + ".md"


def organization_markdown(dataset: Dataset, key: str) -> str:
    profile = dataset.organization_profile(key)
    agg = profile["aggregations"]
    lines: list[str] = []
    lines.append("# MedRadar organization brief: " + profile["display_name"])
    lines.append("")
    if profile["legal_name"] and profile["legal_name"] != profile["display_name"]:
        lines.append("Legal name: " + profile["legal_name"] + "  ")
    if profile["ticker"]:
        lines.append("Ticker: " + str(profile["ticker"]) + (" (" + profile["exchange"] + ")" if profile["exchange"] else "") + "  ")
    lines.append("Country: " + str(profile["country_name"] or profile["country"] or "not recorded"))
    lines.append("")
    lines.append("- Snapshot: " + str(profile["snapshot"]["id"]) + " (collected " + str(profile["snapshot"]["collected_at"]) + ")")
    lines.append("- Registry review: " + profile["registry"]["review_status"])
    verification = profile.get("verification") or {}
    lines.append(
        "- Attribution verification: "
        + str(verification.get("verified_records"))
        + " of "
        + str(verification.get("attributed_records"))
        + " attributed records are evidence-verified or human-reviewed (curated share "
        + ("UNKNOWN" if verification.get("curated_share") is None else format(verification["curated_share"] * 100, ".1f") + "%")
        + "); "
        + str(verification.get("rule_verified_records"))
        + " rest on a deterministic rule; "
        + str(verification.get("provisional_records"))
        + " are provisional."
    )
    ownership = profile.get("ownership") or {}
    lines.append(
        "- Ownership: "
        + str(ownership.get("verified_relation_count"))
        + " verified relation(s), "
        + str(ownership.get("unresolved_relation_count"))
        + " unresolved. Counts use current-group attribution."
    )
    record_level = ownership.get("record_level") or {}
    if record_level:
        lines.append(
            "- Owner at event time: "
            + str(record_level.get("verified_current_group"))
            + " record(s) controlled by this group on the event date, "
            + str(record_level.get("verified_predecessor"))
            + " controlled by a predecessor, "
            + str(record_level.get("unknown"))
            + " UNKNOWN (no verified relation, no effective date, or no event date). Unknown is reported, not counted as zero."
        )
    lines.append("")
    lines.append(profile["description"])
    lines.append("")
    lines.append("> Counts are regulatory records attributed by exact applicant spelling. They are not a measure of innovation or market share.")
    lines.append("")
    if profile["data_quality_notes"]:
        lines.append("## Data quality notes")
        lines.append("")
        for note in profile["data_quality_notes"]:
            lines.append("- " + note)
        lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append("| Event type | Records |")
    lines.append("|---|---|")
    for row in profile["counts"]["by_type"]:
        lines.append("| " + EVENT_TYPE_LABELS[row["event_type"]] + " | " + str(row["count"]) + " |")
    lines.append("")
    lines.append("## Coverage by source")
    lines.append("")
    lines.append(_table(["Source", "Records", "Earliest event date", "Latest event date", "Publication date published by source"], [
        [row["name"], row["records"], row["min_event_date"] or "-", row["max_event_date"] or "-", "yes" if row["published_field_available"] else "not published"]
        for row in profile["coverage"]["sources"]
    ]))
    lines.append("")
    lines.append("## Records per year")
    lines.append("")
    lines.append(_table(["Year", "510(k)", "PMA", "PMA supplement", "Recall", "Total"], [
        [row["year"], row["counts"]["510k"], row["counts"]["pma"], row["counts"]["pma_supplement"], row["counts"]["recall"], row["total"]]
        for row in agg["by_year"]
    ]))
    lines.append("")
    lines.append("## Records by FDA medical specialty")
    lines.append("")
    lines.append(_table(["Category", "Records"], [[row["label"], row["total"]] for row in agg["by_category"][:25]]))
    lines.append("")
    lines.append("## Attribution detail")
    lines.append("")
    lines.append(_table(["Applicant spelling (verbatim)", "Basis", "Review", "Records"], [
        [row["applicant_name"], row["basis"], row["review"], row["record_count"]] for row in profile["attribution"]["examples"]
    ]))
    lines.append("")
    lines.append("## Recent records")
    lines.append("")
    for event in profile["recent_events"]:
        lines.append("- " + (event["event_date"] or "undated") + " - " + event["official_id"] + " - " + event["event_type"] + " - " + event["official_url"])
    return "\n".join(lines)