"""Bounded, re-runnable runner for the Phase 4 job-text extraction experiment.

Arms
----
``A``  deterministic rules (``medradar.recruitment.taxonomy.classify_rules``), no model
``B``  untuned Qwen3-4B-Instruct-2507, local weights, bf16, batch 1, greedy decoding
``C``  NOT_RUN (the existing QLoRA adapter is event-specific; see
       ``job_text_schema.ARM_C_NOT_RUN_REASON``)
``stub`` scripted fixture adapter for offline end-to-end tests (NOT a model arm)

Why this is a thin runner and not a new stack
---------------------------------------------
* The model backend is the existing gated ``HFLocalAdapter`` from
  ``experiments/local_llm_event_extraction/adapters`` (loads only after its gate
  opens, never downloads, reports measured VRAM/tokens).
* Parsing reuses the harness's balanced-JSON extractor; the *decoder* is the new
  job-text contract (``job_text_schema``).
* Every run writes its manifest, its predictions and its sample selection before
  the scorer touches them, so a later reader can reproduce exactly which postings
  were run, with which prompt hash and which weights fingerprint.

Boundedness and VRAM discipline
-------------------------------
One item at a time, greedy, fixed seed, ``max_input_chars`` (default 8000) and
``max_new_tokens`` (default 700) declared on the command line and recorded in the
manifest per item.  If the description is longer than the budget it is truncated
in-band with an explicit marker and counted -- the run never silently shortens a
posting and never retries an over-long prompt by clipping it behind the scenes.

Usage (from the repo root)::

    python -m experiments.innovation_signals_observatory.llm.run_job_text_experiment \
        --arm B --data <snapshot.jsonl> --out <results dir> \
        --n-primary 32 --n-negative 10 --allow-model-load

Nothing here runs at import time; the module is offline-testable with the
``stub`` arm.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from experiments.local_llm_event_extraction.adapters.base import (
    AdapterDescriptor,
    ExtractionRequest,
)
from experiments.local_llm_event_extraction.adapters.hf_local import HFLocalAdapter
from experiments.local_llm_event_extraction.adapters.mock import ScriptedAdapter, scripted_descriptor
from experiments.local_llm_event_extraction.safety import (
    ENV_MODEL_LOAD,
    GATE_MODEL_LOAD,
    gate_open,
    gate_report,
)

from .evaluate import evaluate_run
from .job_text_schema import (
    ARM_C_NOT_RUN_REASON,
    SCHEMA_VERSION,
    TRACK_FIELD_UNCLASSIFIED,
    UNCLASSIFIED,
    ExtractorProvenance,
    parse_job_response,
)
from .prompt_job_v1 import (
    DEFAULT_MAX_INPUT_CHARS,
    PROMPT_VERSION,
    build_job_prompt,
    prompt_fingerprint,
    truncate_description,
)
from .subset import (
    SALT_VERSION,
    hash_key,
    load_postings,
    select_subset,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA = (
    REPO_ROOT
    / "experiments"
    / "innovation_signals_observatory"
    / "results"
    / "2026-11-04"
    / "jobs_medtronic.jsonl"
)
DEFAULT_WEIGHTS = Path(
    os.environ.get("MEDRADAR_JOB_TEXT_WEIGHTS", r"D:\DEPPSKK\ml-models\Qwen3-4B-Instruct-2507")
)
DEFAULT_MAX_NEW_TOKENS = 320
DEFAULT_ITEM_TIMEOUT_S = 90.0
"""Wall-clock budget per item.  A generation that exceeds it is recorded as
`TIMEOUT` in the prediction and the error taxonomy: "the model cannot answer
within a usable budget" is a deployment finding, not a reason to hide the item."""
DEFAULT_SEED = 0

ARM_C_STATUS = "NOT_RUN"


# --------------------------------------------------------------------- helpers
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _relative(path: Path | str | None) -> str | None:
    if path is None:
        return None
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except (ValueError, OSError):
        return str(path)


def _collection_reports(data_path: Path) -> list[dict[str, Any]]:
    """The snapshot's own collection report(s), copied into the manifest for traceability.

    Only reports for the same company as the data file are included: the results
    directory also contains other companies' collection runs (other work packages),
    and copying those into this run's manifest would misrepresent its provenance.
    """
    company = data_path.stem.split("_", 1)[1] if "_" in data_path.stem else data_path.stem
    reports: list[dict[str, Any]] = []
    for candidate in sorted(data_path.parent.glob("collection*.json")):
        if company not in candidate.name:
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        report = payload.get("report") or {}
        availability = payload.get("availability") or {}
        reports.append(
            {
                "file": candidate.name,
                "sha256": _sha256_file(candidate),
                "company_key": payload.get("company_key"),
                "collection_started_at": report.get("started_at"),
                "collection_finished_at": report.get("finished_at"),
                "listings_seen": report.get("listings_seen"),
                "details_ok": report.get("details_ok"),
                "details_failed": report.get("details_failed"),
                "truncated_at_ceiling": report.get("truncated_at_ceiling"),
                "policy_max_postings": (payload.get("policy") or {}).get("max_postings"),
                "n_distinct_postings": availability.get("distinct_postings"),
                "collector_version": payload.get("collector_version"),
                "schema_version": payload.get("schema_version"),
            }
        )
    return reports


def _latency_summary(values: Sequence[float]) -> dict[str, Any]:
    clean = sorted(float(value) for value in values if isinstance(value, (int, float)))
    if not clean:
        return {"n_measured": 0, "median_s": None, "mean_s": None, "p95_s": None, "max_s": None}
    index = min(len(clean) - 1, max(0, int(round(0.95 * (len(clean) - 1)))))
    return {
        "n_measured": len(clean),
        "median_s": round(statistics.median(clean), 3),
        "mean_s": round(statistics.fmean(clean), 3),
        "p95_s": round(clean[index], 3),
        "max_s": round(clean[-1], 3),
        "min_s": round(clean[0], 3),
    }


def _ordered_items(selection: Mapping[str, Any], max_items: int | None) -> list[tuple[dict[str, Any], str]]:
    items: list[tuple[dict[str, Any], str]] = [(row, "primary") for row in selection["primary"]]
    items.extend((row, "negative") for row in selection["negative"])
    if max_items is not None:
        items = items[: max(0, int(max_items))]
    return items


def select_items(
    data_path: str | Path,
    *,
    n_primary: int,
    n_negative: int,
    max_items: int | None = None,
    postings: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply the declared sampling rule and return the selection record."""
    rows = list(postings) if postings is not None else load_postings(str(data_path))
    selection = select_subset(rows, n_primary=n_primary, n_negative=n_negative)
    selection["items"] = [
        {
            "posting_id": str(row["posting_id"]),
            "sample": sample,
            "job_title": row.get("job_title"),
            "hash_key": hash_key(str(row["posting_id"])),
            "description_chars": len(str(row.get("job_description") or "")),
        }
        for row, sample in _ordered_items(selection, max_items)
    ]
    selection["max_items_applied"] = max_items
    return selection


# ---------------------------------------------------------------------- records
def _rules_provenance() -> ExtractorProvenance:
    return ExtractorProvenance(
        system="deterministic_rules",
        adapter_id="recruitment-taxonomy-rules",
        model_id=None,
        model_revision=None,
        prompt_version=None,
        decoding={},
        schema_version=SCHEMA_VERSION,
    )


def _model_provenance(descriptor: AdapterDescriptor, *, max_new_tokens: int, seed: int) -> ExtractorProvenance:
    return ExtractorProvenance(
        system=descriptor.backend,
        adapter_id=descriptor.adapter_id,
        model_id=descriptor.model_id,
        model_revision=descriptor.model_revision,
        prompt_version=PROMPT_VERSION,
        decoding={"temperature": 0, "do_sample": False, "seed": seed, "max_new_tokens": max_new_tokens},
        schema_version=SCHEMA_VERSION,
    )


def _base_record(
    posting: Mapping[str, Any],
    *,
    arm: str,
    sample: str,
    run_id: str,
) -> dict[str, Any]:
    return {
        "arm": arm,
        "posting_id": str(posting["posting_id"]),
        "job_title": posting.get("job_title"),
        "sample": sample,
        "subset_rule": SALT_VERSION,
        "run_id": run_id,
        "latency_s": None,
        "peak_vram_mb": None,
        "tokens_in": None,
        "tokens_out": None,
        "finish_reason": None,
        "input": None,
    }


def _rules_record(
    posting: Mapping[str, Any],
    *,
    sample: str,
    run_id: str,
    classifier: Callable[[Mapping[str, Any]], dict[str, Any]],
    max_input_chars: int,
) -> dict[str, Any]:
    """Run arm A on one posting and map its output into the shared prediction record.

    Arm A sees exactly the same visible description text as arm B: the same
    ``truncate_description`` call with the same character budget and the same
    in-band marker.  Without that, an A/B difference in coverage could be a
    difference in how much of the posting each arm was allowed to read.
    """
    visible_description, truncated, omitted = truncate_description(
        str(posting.get("job_description") or ""), max_input_chars
    )
    visible_posting = dict(posting)
    visible_posting["job_description"] = visible_description

    started = time.perf_counter()
    output = classifier(visible_posting)
    latency = time.perf_counter() - started

    function_class = str(output.get("function_class") or UNCLASSIFIED)
    track = output.get("track_id")
    technology_track = str(track) if track else TRACK_FIELD_UNCLASSIFIED
    spans = [dict(span) for span in (output.get("evidence_spans") or []) if isinstance(span, Mapping)]

    record = _base_record(posting, arm="A", sample=sample, run_id=run_id)
    record.update(
        {
            "parse_status": "ok",
            "json_parsed": True,
            "parse_error": None,
            "abstain": function_class == UNCLASSIFIED and technology_track == TRACK_FIELD_UNCLASSIFIED,
            "abstain_semantics": "derived_by_evaluator: function UNCLASSIFIED and track UNCLASSIFIED",
            "abstain_reason": None,
            "function_class": function_class,
            "function_evidence_quote": None,
            "technology_track": technology_track,
            "track_evidence_quote": None,
            "capability_phrases": [],
            "r_and_d_evidence": False,
            "r_and_d_evidence_quote": None,
            "uncertainty_note": None,
            "evidence_spans": spans,
            "raw_arm_output": output,
            "raw_output": None,
            "latency_s": round(latency, 6),
            "peak_vram_mb": None,
            "tokens_in": None,
            "tokens_out": None,
            "finish_reason": "rule_engine",
            "input": {
                "max_input_chars": int(max_input_chars),
                "description_chars": len(str(posting.get("job_description") or "")),
                "prompt_description_chars": len(visible_description),
                "truncated": bool(truncated),
                "omitted_chars": int(omitted),
                "note": "same visible description text and marker as arm B",
            },
        }
    )
    return record


def _model_record(
    posting: Mapping[str, Any],
    *,
    sample: str,
    run_id: str,
    arm: str,
    adapter: Any,
    provenance: ExtractorProvenance,
    max_input_chars: int,
) -> dict[str, Any]:
    """Run the model arm on one posting: render prompt, generate, parse against the job contract."""
    prompt, item_meta = build_job_prompt(posting, max_input_chars=max_input_chars)
    request = ExtractionRequest(
        doc_id=str(posting["posting_id"]),
        text=prompt.user,
        source_type="job_posting",
        prompt=prompt,
        metadata={"sample": sample},
    )
    started = time.perf_counter()
    response = adapter.generate(request)
    latency = time.perf_counter() - started

    result = parse_job_response(
        response.text,
        posting_id=str(posting["posting_id"]),
        extractor=provenance,
        finish_reason=response.finish_reason,
    )
    record = _base_record(posting, arm=arm, sample=sample, run_id=run_id)
    extraction = result.extraction.to_dict() if result.extraction else None
    record.update(
        {
            "parse_status": result.parse_status,
            "json_parsed": result.json_parsed,
            "parse_error": result.parse_error,
            "abstain": extraction["abstain"] if extraction else False,
            "abstain_semantics": "model_reported",
            "abstain_reason": extraction["abstain_reason"] if extraction else None,
            "function_class": extraction["function_class"] if extraction else UNCLASSIFIED,
            "function_evidence_quote": extraction["function_evidence_quote"] if extraction else None,
            "technology_track": extraction["technology_track"] if extraction else TRACK_FIELD_UNCLASSIFIED,
            "track_evidence_quote": extraction["track_evidence_quote"] if extraction else None,
            "capability_phrases": extraction["capability_phrases"] if extraction else [],
            "r_and_d_evidence": extraction["r_and_d_evidence"] if extraction else False,
            "r_and_d_evidence_quote": extraction["r_and_d_evidence_quote"] if extraction else None,
            "uncertainty_note": extraction["uncertainty_note"] if extraction else None,
            "evidence_spans": None,
            "raw_arm_output": None,
            # Full model text is kept (capped) so parse failures can be quoted in the report.
            "raw_output": (result.raw_output or "")[:8_000],
            "raw_output_chars": len(result.raw_output or ""),
            "latency_s": round(latency, 6),
            "peak_vram_mb": response.peak_vram_mb,
            "tokens_in": response.tokens_in,
            "tokens_out": response.tokens_out,
            "finish_reason": response.finish_reason,
            "input": item_meta,
            "prompt_template_sha256": prompt.template_sha256,
            # Backend-measured facts kept in the record so the manifest can be rebuilt
            # from the predictions alone (no private adapter attributes needed).
            "response_metadata": {
                key: response.metadata.get(key)
                for key in (
                    "weights_fingerprint",
                    "weights_source",
                    "peak_vram_measurement_method",
                    "tokens_per_second",
                    "chat_template",
                    "load",
                )
            },
        }
    )
    return record


# ------------------------------------------------------------------------ runs
def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _dedupe_ordered(records: Sequence[Mapping[str, Any]], order: Sequence[str]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        by_id[str(record.get("posting_id"))] = dict(record)
    return [by_id[posting_id] for posting_id in order if posting_id in by_id]


def _build_model_adapter(
    *,
    weights_path: Path,
    max_input_chars: int,
    max_new_tokens: int,
    seed: int,
    allow_model_load: bool,
) -> tuple[HFLocalAdapter, AdapterDescriptor, dict[str, Any]]:
    environ = dict(os.environ)
    # The laptop GPU's Windows driver starts paging when the SDPA path allocates
    # large temporary attention buffers; expandable segments measurably reduces the
    # fragmentation-driven part of that. This is an allocator setting (torch 2.9:
    # PYTORCH_ALLOC_CONF), not a driver or CUDA change, and it is recorded in the
    # manifest.
    alloc_conf = os.environ.get("PYTORCH_ALLOC_CONF", "expandable_segments:True")
    os.environ["PYTORCH_ALLOC_CONF"] = alloc_conf
    environ["PYTORCH_ALLOC_CONF"] = alloc_conf
    gate_info = {"model_load_gate_was_open": gate_open(GATE_MODEL_LOAD, environ=environ)}
    if not gate_info["model_load_gate_was_open"]:
        if not allow_model_load:
            raise SystemExit(
                "Model-load gate is closed. Re-run with --allow-model-load to acknowledge that this "
                f"command loads a 4B model onto the GPU ({ENV_MODEL_LOAD}=1)."
            )
        environ[ENV_MODEL_LOAD] = "1"
        # ``HFLocalAdapter.load()`` re-checks the gate against the process environment,
        # so the acknowledgement must be visible there too. This is the one place the
        # harness opens its own gate, and it is recorded in the run manifest.
        os.environ[ENV_MODEL_LOAD] = "1"
        gate_info["model_load_gate_opened_by_runner"] = True
    # The local weights directory has no immutable HF revision; record the override
    # rather than pretending it is a pin (the weights fingerprint is recorded too).
    environ["MEDRADAR_LOCAL_LLM_ALLOW_UNPINNED"] = "1"
    gate_info["unpinned_weights_override"] = True
    gate_info["gates"] = gate_report(environ)

    descriptor = AdapterDescriptor(
        adapter_id="job-text-qwen3-4b-instruct-2507-b",
        display_name="Qwen3-4B-Instruct-2507 (untuned, arm B)",
        backend="hf_local",
        model_id="Qwen/Qwen3-4B-Instruct-2507",
        model_revision=None,
        quantization="none",
        device="cuda",
        max_input_chars=int(max_input_chars),
        max_new_tokens=int(max_new_tokens),
        prompt_version=PROMPT_VERSION,
        requires_network=False,
        requires_gpu=True,
        deterministic=True,
        load_gate=GATE_MODEL_LOAD,
        enabled_by_default=False,
        notes="Untuned local model, inference only; no training in this run.",
    )
    adapter = HFLocalAdapter(
        descriptor,
        weights_path=str(weights_path),
        seed=int(seed),
        environ=environ,
    )
    return adapter, descriptor, gate_info


def run_experiment(
    *,
    arm: str,
    data_path: str | Path,
    out_dir: str | Path,
    n_primary: int = 32,
    n_negative: int = 10,
    max_input_chars: int = DEFAULT_MAX_INPUT_CHARS,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    weights_path: str | Path | None = None,
    max_items: int | None = None,
    seed: int = DEFAULT_SEED,
    resume: bool = False,
    allow_model_load: bool = False,
    stub_responses: Mapping[str, str] | None = None,
    stub_default_response: str | None = None,
    do_evaluate: bool = True,
    postings: Sequence[Mapping[str, Any]] | None = None,
    time_budget_s: float | None = None,
) -> dict[str, Any]:
    """Run one arm and write predictions + subset + manifest (and score if requested).

    ``postings`` lets an offline test supply a tiny fixture instead of a file.
    Returns the manifest payload.
    """
    arm = str(arm).upper() if str(arm).upper() in {"A", "B", "C"} else str(arm).lower()
    data_path = Path(data_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if arm == "C":
        manifest = {
            "run_id": f"arm-C-{_now()}",
            "arm": "C",
            "status": ARM_C_STATUS,
            "reason": ARM_C_NOT_RUN_REASON,
            "data": {"path": _relative(data_path), "sha256": _sha256_file(data_path)},
            "schema_version": SCHEMA_VERSION,
        }
        _write_json(out_dir / "manifest_C.json", manifest)
        return manifest

    if arm not in ("A", "B", "stub"):
        raise SystemExit(f"unknown arm {arm!r}; expected A, B, C or stub")

    started_at = _now()
    run_id = f"{arm}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    rows = list(postings) if postings is not None else load_postings(str(data_path))
    selection = select_items(
        data_path,
        n_primary=n_primary,
        n_negative=n_negative,
        max_items=max_items,
        postings=rows,
    )
    ordered = _ordered_items(selection, max_items)
    order_ids = [str(row["posting_id"]) for row, _sample in ordered]
    _write_json(
        out_dir / f"subset_{arm}.json",
        {
            "arm": arm,
            "run_id": run_id,
            "data": {"path": _relative(data_path), "sha256": _sha256_file(data_path)},
            "n_postings_loaded": len(rows),
            **selection,
        },
    )

    predictions_path = out_dir / f"predictions_{arm}.jsonl"
    previous = _read_jsonl(predictions_path) if resume else []
    by_id = {str(record.get("posting_id")): record for record in previous}

    classifier: Callable[[Mapping[str, Any]], dict[str, Any]] | None = None
    adapter: Any = None
    descriptor: AdapterDescriptor | None = None
    gate_info: dict[str, Any] | None = None
    load_seconds: float | None = None
    provenance: ExtractorProvenance | None = None
    model_runtime: dict[str, Any] = {}

    if arm == "A":
        try:
            from medradar.recruitment.taxonomy import classify_rules  # local import: optional dependency
        except ImportError as exc:  # pragma: no cover - shipped with the repo
            raise SystemExit(f"arm A requires medradar.recruitment.taxonomy: {exc}") from exc
        classifier = classify_rules
        provenance = _rules_provenance()
    elif arm == "B":
        adapter, descriptor, gate_info = _build_model_adapter(
            weights_path=Path(weights_path or DEFAULT_WEIGHTS),
            max_input_chars=max_input_chars,
            max_new_tokens=max_new_tokens,
            seed=seed,
            allow_model_load=allow_model_load,
        )
        provenance = _model_provenance(descriptor, max_new_tokens=max_new_tokens, seed=seed)
        load_started = time.perf_counter()
        adapter.load()
        load_seconds = round(time.perf_counter() - load_started, 3)
        model_runtime["describe"] = adapter.describe()
    else:  # stub
        if stub_responses is None and stub_default_response is None:
            raise SystemExit("arm 'stub' needs stub_responses or stub_default_response")
        descriptor = scripted_descriptor(adapter_id="job-text-scripted-stub")
        adapter = ScriptedAdapter(
            descriptor,
            responses=stub_responses or {},
            default_response=stub_default_response,
            raise_on_missing=stub_responses is not None and stub_default_response is None,
        )
        provenance = _model_provenance(descriptor, max_new_tokens=max_new_tokens, seed=seed)
        adapter.load()
        gate_info = {"stub": True, "gates": gate_report(os.environ)}

    assert provenance is not None
    records: list[dict[str, Any]] = []
    print(
        f"[{arm}] run_id={run_id} data={_relative(data_path)} "
        f"items={len(ordered)} (primary={len(selection['primary'])}, negative={len(selection['negative'])}) "
        f"input_cap={max_input_chars} max_new_tokens={max_new_tokens} "
        f"time_budget_s={time_budget_s}",
        flush=True,
    )
    loop_started = time.perf_counter()
    stopped_early = False
    try:
        for index, (posting, sample) in enumerate(ordered, start=1):
            if time_budget_s is not None and (time.perf_counter() - loop_started) > float(time_budget_s):
                stopped_early = True
                print(
                    f"[{arm}] wall-clock budget {time_budget_s}s exhausted after {len(records)} items; "
                    "remaining items recorded as NOT_RUN",
                    flush=True,
                )
                break
            posting_id = str(posting["posting_id"])
            if posting_id in by_id:
                records.append(by_id[posting_id])
                print(f"[{arm}] {index}/{len(ordered)} {posting_id} (resumed)", flush=True)
                continue
            if arm == "A":
                record = _rules_record(
                    posting,
                    sample=sample,
                    run_id=run_id,
                    classifier=classifier,  # type: ignore[arg-type]
                    max_input_chars=max_input_chars,
                )
            else:
                record = _model_record(
                    posting,
                    sample=sample,
                    run_id=run_id,
                    arm=arm,
                    adapter=adapter,
                    provenance=provenance,
                    max_input_chars=max_input_chars,
                )
            latency = record.get("latency_s")
            record["timed_out"] = bool(
                latency is not None and float(latency) > DEFAULT_ITEM_TIMEOUT_S
            )
            records.append(record)
            with predictions_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(
                f"[{arm}] {index}/{len(ordered)} {posting_id} parse={record['parse_status']} "
                f"function={record['function_class']} track={record['technology_track']} "
                f"latency={record['latency_s']}s"
                + (" TIMEOUT" if record.get("timed_out") else ""),
                flush=True,
            )
            if arm == "B" and "load" not in model_runtime:
                metadata = record.get("response_metadata") or {}
                if metadata.get("load"):
                    model_runtime["load"] = metadata.get("load")
                    model_runtime["weights_fingerprint"] = metadata.get("weights_fingerprint")
                    model_runtime["weights_source"] = metadata.get("weights_source")
                    model_runtime["chat_template"] = metadata.get("chat_template")
                    model_runtime["peak_vram_mb_max"] = record.get("peak_vram_mb")
    finally:
        if adapter is not None:
            adapter.unload()

    # Rewrite predictions in selection order without duplicates (resume-safe).
    records = _dedupe_ordered(records, order_ids)
    with predictions_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    finished_at = _now()
    not_run_ids = order_ids[len(records):]
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "arm": arm,
        "status": "PARTIAL" if stopped_early else ("COMPLETED" if records else "NO_ITEMS"),
        "completion": {
            "n_selected": len(order_ids),
            "n_run": len(records),
            "n_not_run": len(not_run_ids),
            "not_run_ids": not_run_ids,
            "stopped_early_wall_clock": stopped_early,
            "resumed_from_previous_predictions": bool(resume),
            "wall_clock_budget_s": time_budget_s,
            "item_timeout_s": DEFAULT_ITEM_TIMEOUT_S,
            "items_timed_out": sum(1 for record in records if record.get("timed_out")),
            "note": (
                "A TIMEOUT item exceeded the declared per-item wall-clock budget but its output "
                "was still parsed and scored; it is a measured deployment limit, not a dropped item."
            ),
        },
        "started_at": started_at,
        "finished_at": finished_at,
        "data": {
            "path": _relative(data_path),
            "sha256": _sha256_file(data_path),
            "n_postings_loaded": len(rows),
            "n_lines_in_file": sum(1 for _ in data_path.open("rb")) if data_path.exists() else None,
        },
        "collection_reports": _collection_reports(data_path) if data_path.exists() else [],
        "subset": {
            "rule": selection["rule"],
            "n_available": selection["n_available"],
            "primary_ids": [str(row["posting_id"]) for row in selection["primary"]],
            "negative_ids": [str(row["posting_id"]) for row in selection["negative"]],
            "max_items_applied": max_items,
            "n_run": len(records),
            "not_run_ids": not_run_ids,
            "items": selection["items"],
        },
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION if arm in ("B", "stub") else None,
        "prompt": prompt_fingerprint() if arm in ("B", "stub") else None,
        "decoding": (
            {"temperature": 0, "do_sample": False, "seed": seed, "max_new_tokens": max_new_tokens}
            if arm in ("B", "stub")
            else None
        ),
        "inputs": {
            "max_input_chars": max_input_chars,
            "applied_to": "both arms (arm A receives the same truncated description text and marker)",
            "description_truncation": "in-band [TRUNCATED: ...] marker; counted per item",
        },
        "model": model_runtime if arm in ("B", "stub") else {"kind": "deterministic_rules"},
        "weights_path": str(weights_path or DEFAULT_WEIGHTS) if arm == "B" else None,
        "model_load_seconds": load_seconds,
        "gates": gate_info,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "cwd": str(Path.cwd()),
            "pytorch_alloc_conf": os.environ.get("PYTORCH_ALLOC_CONF"),
            "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE"),
            "transformers_offline": os.environ.get("TRANSFORMERS_OFFLINE"),
        },
        "latency": _latency_summary([record.get("latency_s") for record in records]),
        "peak_vram_mb_max": max(
            (float(record["peak_vram_mb"]) for record in records if record.get("peak_vram_mb") is not None),
            default=None,
        ),
        "items": [
            {
                "posting_id": record["posting_id"],
                "sample": record["sample"],
                "parse_status": record["parse_status"],
                "function_class": record["function_class"],
                "technology_track": record["technology_track"],
                "abstain": record["abstain"],
                "latency_s": record["latency_s"],
                "timed_out": bool(record.get("timed_out")),
                "tokens_in": record.get("tokens_in"),
                "tokens_out": record.get("tokens_out"),
                "finish_reason": record.get("finish_reason"),
                "input_truncated": (record.get("input") or {}).get("truncated"),
            }
            for record in records
        ],
        "artifacts": {
            "predictions": predictions_path.name,
            "subset": f"subset_{arm}.json",
        },
        "arm_C": {"status": ARM_C_STATUS, "reason": ARM_C_NOT_RUN_REASON},
        "caveats": [
            "Single snapshot (T0): no trend, no lag test, no claim about the company's R&D direction.",
            "No human gold standard: Precision/Recall/F1 are NOT_EVALUABLE.",
            "r_and_d_evidence is a model judgement quoted from text, not a validated R&D measurement.",
            "Negative controls are title-declared and deliberately selected, not a random population sample.",
        ],
    }
    _write_json(out_dir / f"manifest_{arm}.json", manifest)
    if do_evaluate and records:
        try:
            evaluate_run(out_dir, data_path=data_path)
        except Exception as exc:  # pragma: no cover - scoring must not hide a completed run
            print(f"[{arm}] evaluation failed: {exc}", file=sys.stderr, flush=True)
    return manifest


# ------------------------------------------------------------------------- CLI
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bounded job-text extraction experiment (arm A rules / arm B local model / arm C NOT_RUN)."
    )
    parser.add_argument("--arm", required=True, choices=["A", "B", "C", "stub"])
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="JSONL posting snapshot")
    parser.add_argument("--out", required=True, help="output directory for predictions + manifest")
    parser.add_argument("--n-primary", type=int, default=32)
    parser.add_argument("--n-negative", type=int, default=10)
    parser.add_argument("--max-items", type=int, default=None, help="cap the selection (smoke runs)")
    parser.add_argument("--max-input-chars", type=int, default=DEFAULT_MAX_INPUT_CHARS)
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS), help="local model directory")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--time-budget-s",
        type=float,
        default=None,
        help="stop after this many seconds and record remaining items as NOT_RUN (partial run)",
    )
    parser.add_argument("--resume", action="store_true", help="skip postings already present in predictions")
    parser.add_argument(
        "--allow-model-load",
        action="store_true",
        help="acknowledge loading the 4B model on the GPU (opens the model_load gate for this run)",
    )
    parser.add_argument("--no-evaluate", action="store_true", help="skip the scorer after the run")
    parser.add_argument(
        "--stub-responses",
        default=None,
        help=argparse.SUPPRESS,  # offline tests only: JSON file of posting_id -> response text
    )
    parser.add_argument(
        "--stub-default-response",
        default=None,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    stub_responses = None
    if args.stub_responses:
        stub_responses = json.loads(Path(args.stub_responses).read_text(encoding="utf-8"))

    manifest = run_experiment(
        arm=args.arm,
        data_path=args.data,
        out_dir=args.out,
        n_primary=args.n_primary,
        n_negative=args.n_negative,
        max_input_chars=args.max_input_chars,
        max_new_tokens=args.max_new_tokens,
        weights_path=args.weights,
        max_items=args.max_items,
        seed=args.seed,
        resume=args.resume,
        allow_model_load=args.allow_model_load,
        stub_responses=stub_responses,
        stub_default_response=args.stub_default_response,
        do_evaluate=not args.no_evaluate,
        time_budget_s=args.time_budget_s,
    )
    if manifest.get("status") == ARM_C_STATUS:
        print(f"arm C: {ARM_C_STATUS} — {ARM_C_NOT_RUN_REASON}")
        return 0
    print(
        f"[{manifest['arm']}] wrote {Path(args.out) / ('predictions_' + manifest['arm'] + '.jsonl')} "
        f"({manifest['subset']['n_run']} items, median latency {manifest['latency']['median_s']}s)"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
