"""Run the real-document extraction experiment, arms A (rules) and B (local LLM).

This script is the entry point for Phase 2 of the local small-LM research programme.
It wires four pieces that were previously only separately testable:

1. a **real corpus** (``--corpus``) loaded through ``datasets.real_documents``,
2. the **rule baseline** and, optionally, the **local HF adapter** pinned to a
   concrete model revision and a concrete weights directory,
3. the **evidence validator** with the project's real entity roster and taxonomy,
4. the benchmark runner, which measures parse status, validation verdicts, tokens,
   latency and VRAM per case.

It deliberately reports *harness-level* facts (JSON validity, schema pass rate,
verbatim-quote location, abstention) as measurements, and treats event accuracy as
exploratory: the corpus has silver labels derived from source records for part of it
and **no human labels at all**, so no precision/recall/F1 can be research grade.

Exit codes: 0 run completed, 2 refused (gate/config/corpus), 3 every arm NOT_RUN.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:  # allow `python experiments/.../run_real_document_experiment.py`
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.local_llm_event_extraction.adapters import (  # noqa: E402
    AdapterDescriptor,
    HFLocalAdapter,
    RuleBasedAdapter,
    build_registry,
    rules_descriptor,
)
from experiments.local_llm_event_extraction.benchmark import run_benchmark  # noqa: E402
from experiments.local_llm_event_extraction.contracts import (  # noqa: E402
    DatasetManifest,
    default_run_status,
)
from experiments.local_llm_event_extraction.datasets.real_documents import (  # noqa: E402
    build_real_document_dataset,
    describe_corpus,
)
from experiments.local_llm_event_extraction.validation.entities import (  # noqa: E402
    EntityRoster,
    Taxonomy,
)
from experiments.local_llm_event_extraction.validation.validator import (  # noqa: E402
    validate_extraction,
)

GATE_ENV = "MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD"
DEFAULT_MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"
DEFAULT_REVISION = "cdbee75f17c01a7cc42f958dc650907174af0554"
DEFAULT_WEIGHTS = r"D:\DEPPSKK\ml-models\Qwen3-4B-Instruct-2507"


def _alias_map(roster: EntityRoster) -> dict[str, str]:
    """Alias -> canonical id, so arm A and the validator share one roster."""
    mapping: dict[str, str] = {}
    for canonical_id in roster.canonical_ids:
        mapping[canonical_id] = canonical_id
        for alias in roster.aliases_for(canonical_id):
            mapping.setdefault(alias, canonical_id)
    return mapping


def _hf_descriptor(args: argparse.Namespace) -> AdapterDescriptor:
    return AdapterDescriptor(
        adapter_id="hf-qwen3-4b-instruct",
        display_name=f"ARM B - {args.model_id} ({args.quantization}) local",
        backend="hf_local",
        model_id=args.model_id,
        model_revision=args.revision,
        quantization=args.quantization,
        device="cuda",
        max_input_chars=args.max_input_chars,
        max_new_tokens=args.max_new_tokens,
        prompt_version="extract-v1",
        requires_network=False,
        requires_gpu=True,
        deterministic=True,
        load_gate="model_load",
        enabled_by_default=False,
        notes=(
            "Instruction-tuned Qwen3-4B (2507) loaded 4-bit NF4 from a pinned local "
            "snapshot; greedy decoding; thinking disabled when the template supports it."
        ),
    )


def _build_arms(
    args: argparse.Namespace,
    roster: EntityRoster,
    *,
    include_model: bool,
    registry_aliases: Mapping[str, str],
) -> tuple[list[Any], dict[str, Any]]:
    info: dict[str, Any] = {}
    rule_descriptor = rules_descriptor()
    rules = RuleBasedAdapter(rule_descriptor, alias_map=registry_aliases)
    arms: list[Any] = [rules]
    info["rules-baseline"] = rule_descriptor.to_dict()
    if include_model:
        model = HFLocalAdapter(
            _hf_descriptor(args),
            weights_path=args.weights_path,
            cache_dir=args.cache_dir,
            seed=args.seed,
        )
        arms.append(model)
        info["hf-qwen3-4b-instruct"] = model.descriptor.to_dict()
    return arms, info


def _load_records(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "predictions.jsonl"
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _verdict_counts(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    parse: dict[str, int] = {}
    doc_verdict: dict[str, int] = {}
    event_verdict: dict[str, int] = {}
    issue_codes: dict[str, int] = {}
    abstained = 0
    extracted_events = 0
    docs_with_verbatim_quote = 0
    docs_with_any_event = 0
    for record in records:
        status = str(record.get("parse_status"))
        parse[status] = parse.get(status, 0) + 1
        validation = record.get("validation") or {}
        verdict = str(validation.get("verdict") or "not_run")
        doc_verdict[verdict] = doc_verdict.get(verdict, 0) + 1
        judgements = validation.get("judgements") or []
        has_event = False
        has_verbatim = False
        for judgement in judgements:
            event_verdict[str(judgement.get("verdict"))] = (
                event_verdict.get(str(judgement.get("verdict")), 0) + 1
            )
            for issue in judgement.get("issues") or []:
                code = str(issue.get("code"))
                issue_codes[code] = issue_codes.get(code, 0) + 1
                if code == "QUOTE_NOT_VERBATIM":
                    pass
                else:
                    has_verbatim = has_verbatim or code in ()
        result = record.get("result") or {}
        events = result.get("events") or []
        for event in events:
            if event.get("status") == "abstained":
                abstained += 1
            else:
                extracted_events += 1
                has_event = True
        if has_event:
            docs_with_any_event += 1
        # A document "located" a quote when its validation ran and no event carried
        # QUOTE_NOT_VERBATIM / QUOTE_TOO_SHORT.
        codes = {
            str(issue.get("code"))
            for judgement in judgements
            for issue in (judgement.get("issues") or [])
        }
        if not (codes & {"QUOTE_NOT_VERBATIM", "QUOTE_TOO_SHORT"}):
            has_verbatim = True
        if has_verbatim and has_event:
            docs_with_verbatim_quote += 1
    return {
        "documents": len(records),
        "parse_status": dict(sorted(parse.items())),
        "document_verdict": dict(sorted(doc_verdict.items())),
        "event_verdict": dict(sorted(event_verdict.items())),
        "issue_codes": dict(sorted(issue_codes.items(), key=lambda kv: -kv[1])),
        "abstained_events": abstained,
        "extracted_events": extracted_events,
        "documents_with_any_event": docs_with_any_event,
        "documents_with_located_quote": docs_with_verbatim_quote,
    }


def _numeric(records: Sequence[Mapping[str, Any]], key: str) -> dict[str, Any]:
    values = [float(r[key]) for r in records if isinstance(r.get(key), (int, float))]
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 4),
        "median": round(statistics.median(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "total": round(sum(values), 4),
    }


def _silver_agreement(records: Sequence[Mapping[str, Any]], dataset: DatasetManifest) -> dict[str, Any]:
    """Exploratory agreement with source-record silver labels (NOT human gold)."""
    by_case = {case.case_id: case for case in dataset.cases}
    compared = 0
    category_hits = 0
    date_hits = 0
    company_hits = 0
    product_hits = 0
    misses: list[dict[str, Any]] = []
    product_comparisons = 0
    for record in records:
        case = by_case.get(str(record.get("case_id")))
        if case is None or not case.gold_events:
            continue
        result = record.get("result") or {}
        events = [e for e in (result.get("events") or []) if e.get("status") == "extracted"]
        if not events:
            compared += 1
            misses.append({"case_id": case.case_id, "reason": "no extracted event"})
            continue
        compared += 1
        gold = case.gold_events[0]
        match = next(
            (e for e in events if e.get("event_category") == gold.event_category),
            events[0],
        )
        category_ok = match.get("event_category") == gold.event_category
        date_ok = str(match.get("event_date")) == str(gold.event_date)
        company = (match.get("company") or {}).get("canonical_id")
        company_ok = company == gold.company_canonical_id
        if category_ok:
            category_hits += 1
        if date_ok:
            date_hits += 1
        if company_ok:
            company_hits += 1
        # Product is only comparable when the source record supplies one.  A missing
        # gold product is "not measured", never a mismatch (the project's own rule).
        product_ok: bool | None = None
        if gold.product_or_technology:
            product_comparisons += 1
            product_ok = match.get("product_or_technology") == gold.product_or_technology
            if product_ok:
                product_hits += 1
        if not (category_ok and date_ok and company_ok) or product_ok is False:
            misses.append(
                {
                    "case_id": case.case_id,
                    "reason": "field mismatch",
                    "category": [match.get("event_category"), gold.event_category],
                    "event_date": [match.get("event_date"), gold.event_date],
                    "company": [company, gold.company_canonical_id],
                    "product": [match.get("product_or_technology"), gold.product_or_technology],
                }
            )
    denominator = max(compared, 1)
    return {
        "label": "EXPLORATORY",
        "tier": "source_record_derived (silver, not human)",
        "documents_compared": compared,
        "category_agreement": round(category_hits / denominator, 4),
        "event_date_agreement": round(date_hits / denominator, 4),
        "company_agreement": round(company_hits / denominator, 4),
        "product_exact_agreement": (
            round(product_hits / product_comparisons, 4) if product_comparisons else None
        ),
        "product_comparisons": product_comparisons,
        "agreement_counts": {
            "category": category_hits,
            "event_date": date_hits,
            "company": company_hits,
            "product": product_hits,
        },
        "caveat": (
            "Silver labels are copied from the same source record the document text was "
            "rendered from, so agreement measures reading fidelity of a record rendering, "
            "NOT extraction from prose and NOT accuracy against human annotation. "
            "Product agreement is None when the source record supplies no product string."
        ),
        "misses": misses,
    }


def _status_tag(record: Mapping[str, Any]) -> str:
    record = dict(record)
    return str(record.get("status") or record.get("run_status") or "UNKNOWN")


def summarise(
    *,
    run_dir: Path,
    dataset: DatasetManifest,
    arms: Mapping[str, Any],
    corpus_dir: str,
    model_manifest_path: Path | None,
) -> dict[str, Any]:
    records = _load_records(run_dir)
    by_adapter: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_adapter.setdefault(str(record.get("adapter_id")), []).append(record)
    metrics_path = run_dir / "metrics.json"
    metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.is_file() else {}
    run_status = str(metrics_payload.get("status") or "")
    metrics = metrics_payload.get("metrics") or {}

    per_arm: dict[str, Any] = {}
    for adapter_id, arm_records in sorted(by_adapter.items()):
        status = metrics.get(adapter_id, {}).get("status", "RUN")
        summary = {
            "status": status,
            "counts": _verdict_counts(arm_records),
            "latency_s": _numeric(arm_records, "wall_time_s"),
            "tokens_in": _numeric(arm_records, "tokens_in"),
            "tokens_out": _numeric(arm_records, "tokens_out"),
            "peak_vram_mb": _numeric(arm_records, "peak_vram_mb"),
            "silver_agreement": _silver_agreement(arm_records, dataset),
        }
        tokens_per_second = []
        for record in arm_records:
            tokens = record.get("tokens_out")
            wall = record.get("wall_time_s")
            if isinstance(tokens, int) and isinstance(wall, (int, float)) and wall > 0:
                tokens_per_second.append(tokens / wall)
        if tokens_per_second:
            summary["tokens_per_second"] = {
                "count": len(tokens_per_second),
                "median": round(statistics.median(tokens_per_second), 3),
            }
        per_arm[adapter_id] = summary

    return {
        "run_dir": str(run_dir),
        "run_status": run_status,
        "corpus": describe_corpus(corpus_dir),
        "dataset": {
            "name": dataset.name,
            "version": dataset.version,
            "cases": dataset.case_count,
            "label_tiers": sorted(set(dataset.label_tiers)),
            "default_run_status": default_run_status(dataset.label_tiers),
            "source_sha256": dataset.source_sha256,
        },
        "arms": arms,
        "per_arm": per_arm,
        "model_manifest": (
            json.loads(model_manifest_path.read_text(encoding="utf-8"))
            if model_manifest_path is not None and model_manifest_path.is_file()
            else None
        ),
        "notes": [
            "Harness-level measurements (parse status, validation verdict, latency, tokens, VRAM) are VERIFIED: they were measured in this run.",
            "Silver-label agreement is EXPLORATORY and not accuracy against human annotation.",
            "No precision/recall/F1 is reported for prose documents: no labels exist for them.",
        ],
    }


def _arm_info(args: argparse.Namespace) -> dict[str, Any]:
    """Descriptor records for the summary, without instantiating any adapter."""
    info: dict[str, Any] = {"rules-baseline": rules_descriptor().to_dict()}
    if not args.rules_only:
        info["hf-qwen3-4b-instruct"] = _hf_descriptor(args).to_dict()
    return info


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        default=str(Path(__file__).resolve().parents[1] / "datasets" / "real" / "corpus" / "2026-11-04"),
        help="frozen corpus directory (default: the copy committed with this module)",
    )
    parser.add_argument("--out", default=r"D:\DEPPSKK\ml-work\runs")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--weights-path", default=DEFAULT_WEIGHTS)
    parser.add_argument("--cache-dir", default=r"D:\DEPPSKK\ml-cache\hf")
    parser.add_argument("--quantization", default="nf4", choices=["nf4", "none"])
    parser.add_argument("--max-new-tokens", type=int, default=768)
    parser.add_argument("--max-input-chars", type=int, default=12_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--rules-only", action="store_true", help="skip the model arm")
    parser.add_argument("--model-manifest", default=r"D:\DEPPSKK\ml-work\model_download.json")
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument(
        "--summarize-only",
        action="store_true",
        help="rebuild EXPERIMENT_SUMMARY.json from an existing run directory (no model load)",
    )
    parser.add_argument("--run-dir", default=None, help="existing run directory for --summarize-only")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    corpus_dir = Path(args.corpus)
    if not corpus_dir.is_dir():
        print(f"REFUSED: corpus directory not found: {corpus_dir}", file=sys.stderr)
        return 2
    try:
        dataset = build_real_document_dataset(corpus_dir)
    except Exception as exc:  # noqa: BLE001 - refuse loudly on a bad corpus
        print(f"REFUSED: corpus failed integrity checks: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    roster = EntityRoster.from_config()
    taxonomy = Taxonomy.from_config()
    aliases = _alias_map(roster)
    include_model = not args.rules_only
    if args.summarize_only:
        run_dir = Path(args.run_dir) if args.run_dir else Path(args.out) / str(args.run_id)
        if not (run_dir / "predictions.jsonl").is_file():
            print(f"REFUSED: no predictions.jsonl in {run_dir}", file=sys.stderr)
            return 2
        summary = summarise(
            run_dir=run_dir,
            dataset=dataset,
            arms=_arm_info(args),
            corpus_dir=str(corpus_dir),
            model_manifest_path=Path(args.model_manifest) if args.model_manifest else None,
        )
        summary_path = run_dir / "EXPERIMENT_SUMMARY.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"\nsummary rewritten -> {summary_path}")
        return 0
    if include_model:
        if not Path(args.weights_path).is_dir():
            print(f"REFUSED: weights directory not found: {args.weights_path}", file=sys.stderr)
            return 2
        os.environ[GATE_ENV] = "1"

    arms, arm_info = _build_arms(args, roster, include_model=include_model, registry_aliases=aliases)
    run_id = args.run_id or f"real-{args.model_id.split('/')[-1].lower()}-{args.quantization}-s{args.seed}"
    out = Path(args.out)

    run = run_benchmark(
        dataset,
        arms,
        output_dir=out,
        run_id=run_id,
        validator=validate_extraction,
        roster=roster,
        taxonomy=taxonomy,
        limit=args.limit,
        config={
            "corpus_dir": str(corpus_dir),
            "corpus_manifest_sha256": dataset.source_sha256,
            "gate_env": {GATE_ENV: "1"} if include_model else {},
            "note": (
                "REAL_DOCUMENT_UNLABELLED run: real public documents, silver labels only for "
                "part of the corpus, no human labels. Accuracy is not research grade."
            ),
        },
    )

    summary = summarise(
        run_dir=Path(run.run_dir),
        dataset=dataset,
        arms=arm_info,
        corpus_dir=str(corpus_dir),
        model_manifest_path=Path(args.model_manifest) if args.model_manifest else None,
    )
    summary["run_status"] = run.status
    summary_path = Path(run.run_dir) / "EXPERIMENT_SUMMARY.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nsummary written to {summary_path}")
    if not summary["per_arm"]:
        return 3
    if all(payload.get("status") == "NOT_RUN" for payload in summary["per_arm"].values()):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
