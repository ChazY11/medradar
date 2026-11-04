"""Summarise overnight evaluation runs into honest, stratified numbers.

The one rule this script enforces in code: **precision, recall and F1 are not
computed against these labels.**  The gold events are SOURCE_DERIVED_SILVER, so
`precision_recall_f1` is written as ``NOT_EVALUABLE`` with the reason attached,
and what is reported instead is *exploratory agreement* -- category, date, company
and product agreement on documents that carry a silver event.

Everything is stratified by text origin (structural rendering vs synthetic
narrative), source type and event-date kind, because an average over those strata
would hide exactly the failure modes this run is looking for.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.local_llm_event_extraction.datasets.overnight_corpus import (  # noqa: E402
    build_dataset,
)

DEFAULT_CORPUS = r"D:\DEPPSKK\ml-work\overnight\corpus\ovn-2026-11-04"
NOT_EVALUABLE = "NOT_EVALUABLE"


def _load_predictions(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "predictions.jsonl"
    if not path.is_file():
        raise SystemExit(f"no predictions.jsonl in {run_dir}")
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _rate(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _issue_codes(record: Mapping[str, Any]) -> set[str]:
    validation = record.get("validation") or {}
    codes: set[str] = set()
    for judgement in validation.get("judgements") or []:
        for issue in judgement.get("issues") or []:
            codes.add(str(issue.get("code")))
    return codes


def _extracted_events(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = record.get("result") or {}
    return [event for event in (result.get("events") or []) if event.get("status") == "extracted"]


def _abstained(record: Mapping[str, Any]) -> bool:
    return not _extracted_events(record)


def _stratum(record: Mapping[str, Any], datasets_by_case: Mapping[str, Any], key: str) -> str:
    case = datasets_by_case.get(record.get("case_id"))
    if case is None:
        return "unknown"
    if key == "text_origin":
        return str(case.document.metadata.get("text_origin") or "unknown")
    if key == "source_type":
        return case.document.source_type
    if key == "event_date_kind":
        return str(case.document.metadata.get("event_date_kind") or "none")
    raise KeyError(key)


def _agreement(records: Sequence[Mapping[str, Any]], datasets_by_case: Mapping[str, Any]) -> dict[str, Any]:
    """Exploratory field agreement with silver labels (never accuracy)."""
    compared = 0
    category_hits = date_hits = company_hits = 0
    product_compared = product_hits = 0
    combined_hits = 0
    misses: list[dict[str, Any]] = []
    for record in records:
        case = datasets_by_case.get(record.get("case_id"))
        if case is None or not case.gold_events:
            continue
        compared += 1
        gold = case.gold_events[0]
        events = _extracted_events(record)
        if not events:
            misses.append({"case_id": case.case_id, "reason": "no extracted event"})
            continue
        match = next(
            (event for event in events if event.get("event_category") == gold.event_category),
            events[0],
        )
        category_ok = match.get("event_category") == gold.event_category
        date_ok = str(match.get("event_date")) == str(gold.event_date)
        company_ok = (match.get("company") or {}).get("canonical_id") == gold.company_canonical_id
        category_hits += int(category_ok)
        date_hits += int(date_ok)
        company_hits += int(company_ok)
        product_ok: bool | None = None
        if gold.product_or_technology:
            product_compared += 1
            product_ok = match.get("product_or_technology") == gold.product_or_technology
            product_hits += int(bool(product_ok))
        if category_ok and date_ok and company_ok:
            combined_hits += 1
        else:
            misses.append(
                {
                    "case_id": case.case_id,
                    "reason": "field mismatch",
                    "category": [match.get("event_category"), gold.event_category],
                    "event_date": [match.get("event_date"), gold.event_date],
                    "company": [(match.get("company") or {}).get("canonical_id"), gold.company_canonical_id],
                    "product": [match.get("product_or_technology"), gold.product_or_technology],
                }
            )
    return {
        "documents_compared": compared,
        "category_agreement": _rate(category_hits, compared),
        "event_date_agreement": _rate(date_hits, compared),
        "company_agreement": _rate(company_hits, compared),
        "product_exact_agreement": _rate(product_hits, product_compared),
        "product_comparisons": product_compared,
        "category_date_company_joint_agreement": _rate(combined_hits, compared),
        "misses": misses[:20],
    }


def summarise_arm(
    records: Sequence[Mapping[str, Any]],
    datasets_by_case: Mapping[str, Any],
) -> dict[str, Any]:
    documents = len(records)
    parse_ok = sum(1 for record in records if record.get("parse_status") == "ok")
    parse_status: dict[str, int] = {}
    for record in records:
        key = str(record.get("parse_status"))
        parse_status[key] = parse_status.get(key, 0) + 1
    accepted = sum(
        1
        for record in records
        if (record.get("validation") or {}).get("verdict") == "accepted"
    )
    quote_ok = sum(
        1
        for record in records
        if record.get("parse_status") == "ok"
        and not (_issue_codes(record) & {"QUOTE_NOT_VERBATIM", "EVIDENCE_TOO_SHORT", "EVIDENCE_TOO_LONG"})
    )
    extracted = sum(len(_extracted_events(record)) for record in records)
    abstained_docs = sum(1 for record in records if _abstained(record))
    with_gold = [record for record in records if datasets_by_case.get(record.get("case_id")) and datasets_by_case[record["case_id"]].gold_events]
    negatives = [
        record
        for record in records
        if datasets_by_case.get(record.get("case_id"))
        and datasets_by_case[record["case_id"]].expected_abstain
    ]
    wrong_abstention = sum(1 for record in with_gold if _abstained(record))
    false_assertion = sum(1 for record in negatives if _extracted_events(record))
    issue_counts: dict[str, int] = {}
    for record in records:
        for code in _issue_codes(record):
            issue_counts[code] = issue_counts.get(code, 0) + 1
    walls = [float(record["wall_time_s"]) for record in records if isinstance(record.get("wall_time_s"), (int, float))]
    vrams = [float(record["peak_vram_mb"]) for record in records if isinstance(record.get("peak_vram_mb"), (int, float))]
    throughput = [
        float(record["tokens_out"]) / float(record["wall_time_s"])
        for record in records
        if isinstance(record.get("tokens_out"), int)
        and isinstance(record.get("wall_time_s"), (int, float))
        and float(record["wall_time_s"]) > 0
    ]

    ledger = {
        "harness_level": "MEASURED",
        "precision_recall_f1": NOT_EVALUABLE,
        "precision_recall_f1_reason": (
            "gold events are SOURCE_DERIVED_SILVER labels copied from the same records the "
            "documents were rendered from; they are not human annotations, so precision, "
            "recall and F1 are not defined as research metrics here"
        ),
        "agreement": "EXPLORATORY",
    }

    def stratified(key: str) -> dict[str, Any]:
        buckets: dict[str, list[Mapping[str, Any]]] = {}
        for record in records:
            buckets.setdefault(_stratum(record, datasets_by_case, key), []).append(record)
        return {
            name: {
                "documents": len(bucket),
                "json_valid_rate": _rate(
                    sum(1 for item in bucket if item.get("parse_status") == "ok"), len(bucket)
                ),
                "schema_accepted_rate": _rate(
                    sum(1 for item in bucket if (item.get("validation") or {}).get("verdict") == "accepted"),
                    len(bucket),
                ),
                "abstention_rate": _rate(sum(1 for item in bucket if _abstained(item)), len(bucket)),
                **{
                    key_: value
                    for key_, value in _agreement(bucket, datasets_by_case).items()
                    if key_ != "misses"
                },
            }
            for name, bucket in sorted(buckets.items())
        }

    return {
        "documents": documents,
        "ledger": ledger,
        "parse_status": dict(sorted(parse_status.items())),
        "json_valid_rate": _rate(parse_ok, documents),
        "schema_accepted_rate": _rate(accepted, documents),
        "verbatim_quote_located_rate": _rate(quote_ok, documents),
        "extracted_events": extracted,
        "abstained_documents": abstained_docs,
        "abstention_rate": _rate(abstained_docs, documents),
        "documents_with_silver_gold": len(with_gold),
        "wrong_abstention_rate": _rate(wrong_abstention, len(with_gold)),
        "negative_control_documents": len(negatives),
        "false_assertion_rate": _rate(false_assertion, len(negatives)),
        "error_taxonomy": dict(sorted(issue_counts.items(), key=lambda kv: -kv[1])),
        "latency_s": {
            "median": round(statistics.median(walls), 3) if walls else None,
            "mean": round(statistics.fmean(walls), 3) if walls else None,
            "max": round(max(walls), 3) if walls else None,
        },
        "peak_vram_mb": round(max(vrams), 1) if vrams else None,
        "tokens_per_s_median": round(statistics.median(throughput), 2) if throughput else None,
        "agreement": _agreement(records, datasets_by_case),
        "strata": {
            "text_origin": stratified("text_origin"),
            "source_type": stratified("source_type"),
            "event_date_kind": stratified("event_date_kind"),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=DEFAULT_CORPUS)
    parser.add_argument("--run-dir", action="append", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--splits", default="test")
    args = parser.parse_args(argv)

    manifest, audit = build_dataset(args.corpus)
    splits = {part.strip() for part in args.splits.split(",") if part.strip()}
    datasets_by_case = {case.case_id: case for case in manifest.cases if case.split in splits}

    payload: dict[str, Any] = {
        "dataset": {
            "corpus_sha256": audit["corpus"]["corpus_sha256"],
            "label_tier": audit["label_tier"],
            "splits_evaluated": sorted(splits),
            "leakage_audit": audit["leakage_audit"],
            "counts": audit["counts"]["by_split"],
        },
        "runs": {},
    }
    for run_dir_text in args.run_dir:
        run_dir = Path(run_dir_text)
        records = _load_predictions(run_dir)
        per_arm: dict[str, dict[str, Any]] = {}
        by_adapter: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            if record.get("split") not in splits:
                continue
            by_adapter.setdefault(str(record.get("adapter_id")), []).append(record)
        for adapter_id, arm_records in sorted(by_adapter.items()):
            per_arm[adapter_id] = summarise_arm(arm_records, datasets_by_case)
        manifest_path = run_dir / "manifest.json"
        run_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        payload["runs"][run_dir.name] = {
            "run_dir": str(run_dir),
            "prompt": (run_manifest.get("config") or {}).get("config", {}).get("prompt_version"),
            "arms": per_arm,
        }
        print(f"== {run_dir.name} ==")
        for adapter_id, summary in per_arm.items():
            print(
                f"  {adapter_id:26s} json={summary['json_valid_rate']} "
                f"schema={summary['schema_accepted_rate']} "
                f"cat={summary['agreement']['category_agreement']} "
                f"date={summary['agreement']['event_date_agreement']} "
                f"co={summary['agreement']['company_agreement']} "
                f"lat={summary['latency_s']['median']}s"
            )
    out = Path(args.out) if args.out else Path(args.run_dir[0]).parent / "SUMMARY.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
