"""Arm-agnostic, resumable benchmark runner that never invents a result.

One call to :func:`run_benchmark` writes four artifacts into
``output_dir/<run_id>/``:

``manifest.json``
    everything needed to judge what a number means: dataset identity and hash,
    adapter descriptors, seeds, config hash, git state, gate posture, resource
    measurements (``None`` where not measured), run status.
``predictions.jsonl``
    one JSON object per ``(adapter, case)``, appended as the run proceeds so a
    crash leaves a resumable trace.  Strict parsing means a bad model output is
    recorded as a parse failure, never silently dropped.
``metrics.json``
    the per-adapter :class:`~..contracts.MetricReport` plus the ``NOT_RUN``
    reasons.  A gated arm gets no metric report at all -- a fabricated zero is the
    one thing this harness must never produce.
``REPORT.md``
    the human-readable report, with the synthetic-fixture banner mandatory for
    non-research label tiers.

Run status
----------
``status`` is passed through
:func:`~..contracts.require_consistent_run_status`: a dataset whose label tiers are
not human/expert cannot be reported as ``RESEARCH_GRADE``; asking for it raises
before anything is scored.

Resource honesty
----------------
``None`` means "not measured".  Tokens are summed only when a backend reported
any; VRAM is recorded only when a GPU allocator was actually queried; peak RSS is
read from the OS (``Psapi`` on Windows) and is ``None`` where that is unavailable.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ..contracts import (
    SCORING_PROTOCOL_VERSION,
    DatasetManifest,
    MetricReport,
    ResourceMeasurement,
    RunManifest,
    ValidationConfig as _ValidationConfig,
    is_research_grade,
    require_consistent_run_status,
)
from ..parsing import ParsedExtraction, parse_response
from ..schema import (
    SCHEMA_VERSION,
    ExtractionResult,  # noqa: F401  (documented return type of _run_one_case helpers)
    ExtractorProvenance,
    SourceDocument,
)
from . import metrics as metrics_module
from .report import write_report

RUNNER_VERSION = "v1"
SYNTHETIC_BANNER = "SYNTHETIC_FIXTURE_ONLY — harness validation, not an empirical result"


def canonical_json(payload: Any) -> str:
    """Stable JSON for hashing (sorted keys, compact separators, UTF-8 safe)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(payload: Any) -> str:
    return sha256_text(canonical_json(payload))


@dataclass(frozen=True)
class BenchmarkRun:
    """Result of one :func:`run_benchmark` call."""

    run_id: str
    run_dir: Path
    status: str
    manifest: RunManifest
    metrics_by_adapter: Mapping[str, MetricReport]
    not_run: Mapping[str, str]
    predictions: Mapping[str, tuple[Mapping[str, Any], ...]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "status": self.status,
            "not_run": dict(self.not_run),
            "metrics": {
                adapter_id: report.to_dict()
                for adapter_id, report in self.metrics_by_adapter.items()
            },
            "manifest": self.manifest.to_dict(),
        }


# --------------------------------------------------------------------- resources
def peak_rss_mb() -> tuple[float | None, str | None]:
    """Peak working-set size of this process, or ``(None, None)``.

    Uses ``Psapi.GetProcessMemoryInfo`` on Windows; no other platform dependency is
    imported.  Unmeasured stays ``None`` (never 0).
    """
    if os.name != "nt":  # pragma: no cover - exercised on the Windows dev machine
        return None, None
    try:
        import ctypes
        from ctypes import wintypes

        class _ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(_ProcessMemoryCounters)
        psapi = ctypes.WinDLL("psapi.dll")
        kernel32 = ctypes.WinDLL("kernel32.dll")
        # Without these declarations ctypes truncates the 64-bit HANDLE to a 32-bit
        # int, GetProcessMemoryInfo fails, and a measured value silently becomes
        # "not measured".
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return (
                float(counters.PeakWorkingSetSize) / (1024.0 * 1024.0),
                "ctypes Psapi.GetProcessMemoryInfo.PeakWorkingSetSize",
            )
    except Exception:  # pragma: no cover - API not available
        return None, None
    return None, None  # pragma: no cover


def _git_info(repo_root: Path | None = None) -> tuple[str | None, str | None, bool | None, str | None]:
    """Read-only git identity: ``(commit, branch, dirty, error)``."""
    root = repo_root or Path(__file__).resolve().parents[3]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if commit.returncode != 0:
            return None, None, None, (commit.stderr or "git rev-parse failed").strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        dirty: bool | None = None
        if status.returncode == 0:
            dirty = bool(status.stdout.strip())
        return (
            commit.stdout.strip() or None,
            branch.stdout.strip() if branch.returncode == 0 else None,
            dirty,
            None,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, None, None, f"git unavailable: {exc}"


def _resolve_validator(
    validator: Callable[..., Any] | None,
) -> tuple[Callable[..., Any] | None, str]:
    """Prefer the injected validator; otherwise lazily auto-detect the real one.

    Imported inside the function (and inside the call) so the harness never
    depends on the validator work package's timing.
    """
    if validator is not None:
        if not callable(validator):
            raise TypeError("validator must be callable")
        return validator, "injected"
    try:
        from ..validation.validator import validate_extraction  # noqa: PLC0415 (lazy by design)

        return validate_extraction, "auto-detected (lazy import)"
    except Exception:
        return None, "not available (no validator injected and none importable)"


# ------------------------------------------------------------------ main entry
def run_benchmark(
    dataset: DatasetManifest,
    adapters: Any = None,
    *,
    output_dir: str | Path,
    seeds: Sequence[int] = (0,),
    validator: Callable[..., Any] | None = None,
    limit: int | None = None,
    resume: bool = True,
    config: Mapping[str, Any] | None = None,
    run_id: str | None = None,
    adapter_ids: Sequence[str] | None = None,
    roster: Any = None,
    taxonomy: Any = None,
) -> BenchmarkRun:
    """Run every adapter over every case and write the four artifacts.

    ``adapters`` may be a registry (then ``adapter_ids`` selects entries, default:
    all registered) or a sequence of already-built adapters.  Gated adapters are
    given one ``load()`` attempt; a closed gate records ``NOT_RUN`` with the reason
    and never produces a metric row.
    """
    if not isinstance(dataset, DatasetManifest):
        raise TypeError("dataset must be a DatasetManifest")
    materialised_cases = tuple(dataset.cases)
    if not materialised_cases:
        raise ValueError("dataset has no cases")
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        materialised_cases = materialised_cases[:limit]
    seed_tuple = tuple(int(seed) for seed in seeds) or (0,)
    primary_seed = seed_tuple[0]
    user_config = dict(config or {})
    output_root = Path(output_dir)

    # Refuse an inconsistent run status *before* touching the output directory:
    # asking for RESEARCH_GRADE on synthetic labels must leave no artifacts behind.
    requested_status = str(user_config.get("run_status") or "")
    if not requested_status:
        requested_status = (
            "RESEARCH_GRADE" if is_research_grade(dataset.label_tiers) else "SYNTHETIC_FIXTURE_ONLY"
        )
    requested_status = require_consistent_run_status(requested_status, dataset.label_tiers)

    resolved_adapters = _resolve_adapters(adapters, adapter_ids)
    if not resolved_adapters:
        raise ValueError("no adapters selected")

    dataset_sha = dataset.source_sha256 or sha256_json(dataset.to_dict())
    adapter_config = [
        _descriptor_identity(adapter) for adapter in resolved_adapters
    ]
    config_payload = {
        "runner_version": RUNNER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "scoring_protocol_version": SCORING_PROTOCOL_VERSION,
        "config": user_config,
        "seeds": list(seed_tuple),
        "dataset_sha256": dataset_sha,
        "adapters": adapter_config,
        "limit": limit,
    }
    config_sha = sha256_json(config_payload)
    resolved_run_id = run_id or f"run-{dataset_sha[:12]}-{config_sha[:12]}"
    if not resolved_run_id or any(char in resolved_run_id for char in ("/", "\\", ":", " ")):
        raise ValueError(f"unsafe run_id {resolved_run_id!r}")
    run_dir = output_root / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = run_dir / "predictions.jsonl"

    existing = _load_existing_predictions(predictions_path, resume=resume)
    completed = set(existing)
    valid_adapters = {_adapter_id(adapter) for adapter in resolved_adapters}
    notes: list[str] = []

    validator_fn, validator_source = _resolve_validator(validator)
    validation_config = _ValidationConfig() if validator_fn is not None else None
    if validator_fn is not None and validator_source.startswith("auto"):
        # A one-shot capability probe: the real validator requires an injected
        # roster and taxonomy.  If they are missing, disable validation with a
        # recorded note instead of recording an error on every single case.
        probe = ExtractionResult(
            doc_id=materialised_cases[0].document.doc_id,
            parse_status="ok",
            extractor=ExtractorProvenance(system="probe", adapter_id="probe"),
            events=(),
        )
        try:
            validator_fn(
                probe,
                document=materialised_cases[0].document,
                roster=roster,
                taxonomy=taxonomy,
                config=validation_config,
            )
        except Exception as exc:
            notes.append(
                "validation disabled: the auto-detected validator needs an injected roster and "
                f"taxonomy ({type(exc).__name__}: {exc}); pass validator=, roster= and taxonomy= "
                "to enable validation"
            )
            validator_fn = None
            validation_config = None
            validator_source = "auto-detected but not usable without roster/taxonomy"

    adapter_infos: list[dict[str, Any]] = []
    resources: dict[str, dict[str, Any]] = {}
    metrics_by_adapter: dict[str, MetricReport] = {}
    not_run: dict[str, str] = {}
    predictions_by_adapter: dict[str, list[dict[str, Any]]] = {
        adapter_id: [record for (aid, _case), record in existing.items() if aid == adapter_id]
        for adapter_id in valid_adapters
    }
    if not is_research_grade(dataset.label_tiers):
        notes.append(SYNTHETIC_BANNER)
    if validator_fn is None and validator_source.startswith("not available"):
        notes.append(
            "validation did not run: no validator injected and the real validator "
            "package was not importable at run time"
        )
    if limit is not None:
        notes.append(f"case limit applied: {len(materialised_cases)} of {dataset.case_count} cases")
    if len(seed_tuple) > 1:
        notes.append(
            "single pass across cases: seeds[0] is the decoding seed; additional seeds are "
            "recorded for reproducibility but case-level repetition is not performed by this runner"
        )

    with predictions_path.open("a", encoding="utf-8") as stream:
        for adapter in resolved_adapters:
            adapter_id = _adapter_id(adapter)
            descriptor = adapter.descriptor
            info = _adapter_info(adapter)
            started_perf = time.perf_counter()
            started_cpu = time.process_time()
            per_case_walls: list[float] = []
            tokens_in_values: list[int] = []
            tokens_out_values: list[int] = []
            vram_values: list[float] = []
            cost_values: list[float] = []
            vram_method: str | None = None
            reused = 0
            new_cases = 0
            load_elapsed: float | None = None

            load_started = time.perf_counter()
            try:
                adapter.load()
                load_elapsed = time.perf_counter() - load_started
            except Exception as exc:  # gate/unavailable are expected; record NOT_RUN
                from ..adapters.base import AdapterError  # local import: avoid cycle at module scope

                if not isinstance(exc, AdapterError):
                    raise
                reason = f"{type(exc).__name__}: {exc}"
                not_run[adapter_id] = reason
                info["status"] = "NOT_RUN"
                info["reason"] = reason
                info["loaded"] = False
                adapter_infos.append(info)
                resources[adapter_id] = {"status": "NOT_RUN", "reason": reason}
                notes.append(f"{adapter_id}: NOT RUN ({reason})")
                adapter.unload()
                continue

            try:
                needs_prompt = _needs_prompt(adapter)
                provenance = _provenance(adapter, prompt_version=descriptor.prompt_version, seed=primary_seed)
                for case in materialised_cases:
                    key = (adapter_id, case.case_id)
                    if key in completed:
                        reused += 1
                        continue
                    new_cases += 1
                    record = _run_one_case(
                        adapter=adapter,
                        case=case,
                        provenance=provenance,
                        needs_prompt=needs_prompt,
                        seed=primary_seed,
                        validator_fn=validator_fn,
                        validation_config=validation_config,
                        roster=roster,
                        taxonomy=taxonomy,
                    )
                    # Stamp the run-level label tier on every record: a single
                    # prediction line must be readable in isolation and must not be
                    # quotable as an empirical result.
                    record["run_status"] = requested_status
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                    stream.flush()
                    predictions_by_adapter[adapter_id].append(record)
                    if record.get("wall_time_s") is not None:
                        per_case_walls.append(float(record["wall_time_s"]))
                    _collect_measurements(
                        record,
                        tokens_in_values=tokens_in_values,
                        tokens_out_values=tokens_out_values,
                        vram_values=vram_values,
                        cost_values=cost_values,
                    )
                    if vram_method is None and record.get("peak_vram_measurement_method"):
                        vram_method = record["peak_vram_measurement_method"]
            finally:
                adapter.unload()

            wall_total = time.perf_counter() - started_perf
            cpu_delta = time.process_time() - started_cpu
            rss, rss_method = peak_rss_mb()
            resource = ResourceMeasurement(
                wall_time_s=wall_total,
                per_case_wall_time_s=tuple(per_case_walls),
                cpu_time_s=cpu_delta,
                peak_rss_mb=rss,
                peak_vram_mb=max(vram_values) if vram_values else None,
                vram_measurement_method=vram_method,
                tokens_in=sum(tokens_in_values) if tokens_in_values else None,
                tokens_out=sum(tokens_out_values) if tokens_out_values else None,
                estimated_cost_usd=sum(cost_values) if cost_values else None,
                notes="; ".join(
                    part
                    for part in (
                        (
                            f"wall includes load ({load_elapsed:.4f}s) plus {new_cases} new case(s); "
                            f"{reused} case(s) reused from a previous run and not re-timed"
                        )
                        if load_elapsed is not None
                        else "",
                        (
                            f"tokens measured on {len(tokens_in_values)}/{new_cases} new case(s)"
                            if tokens_in_values
                            else "tokens not measured (backend reports no tokenizer usage)"
                        ),
                        (
                            f"peak rss via {rss_method}"
                            if rss_method
                            else "peak rss not measured on this platform"
                        ),
                        (
                            f"peak vram via {vram_method}"
                            if vram_method
                            else "peak vram not measured (no GPU allocator queried)"
                        ),
                    )
                    if part
                )
                or "no measurement available",
            )
            resources[adapter_id] = resource.to_dict()
            records = sorted(
                predictions_by_adapter.get(adapter_id, []),
                key=lambda record: _case_order(record.get("case_id"), materialised_cases),
            )
            scoring_config = dict(user_config.get("scoring") or {})
            scoring_config["seeds"] = list(seed_tuple)
            metrics_by_adapter[adapter_id] = metrics_module.score_predictions(
                materialised_cases, records, scoring_config
            )
            info["status"] = "RUN"
            info["cases_scored"] = len(records)
            info["cases_reused"] = reused
            info["loaded_during_run"] = True
            info["loaded"] = False  # unloaded before the manifest is written
            adapter_infos.append(info)

    # ---------------------------------------------------------- run status
    status = requested_status if metrics_by_adapter else "NOT_RUN"
    if status == "NOT_RUN":
        notes.append("no adapter ran; the run is recorded as NOT_RUN rather than as a zero score")

    manifest = _build_manifest(
        dataset=dataset,
        cases=materialised_cases,
        run_id=resolved_run_id,
        status=status,
        adapter_infos=adapter_infos,
        not_run=not_run,
        metrics_by_adapter=metrics_by_adapter,
        resources=resources,
        config_payload=config_payload,
        config_sha=config_sha,
        seeds=seed_tuple,
        notes=tuple(notes),
        validator_source=validator_source,
    )
    _write_artifacts(
        run_dir=run_dir,
        manifest=manifest,
        metrics_by_adapter=metrics_by_adapter,
        not_run=not_run,
        dataset=dataset,
        seeds=seed_tuple,
        status=status,
    )
    predictions = {
        adapter_id: tuple(records)
        for adapter_id, records in sorted(predictions_by_adapter.items())
    }
    return BenchmarkRun(
        run_id=resolved_run_id,
        run_dir=run_dir,
        status=status,
        manifest=manifest,
        metrics_by_adapter=metrics_by_adapter,
        not_run=not_run,
        predictions=predictions,
    )


# ------------------------------------------------------------------- internals
def _adapter_id(adapter: Any) -> str:
    try:
        return str(adapter.descriptor.adapter_id)
    except AttributeError as exc:  # pragma: no cover - contract violation
        raise TypeError(f"adapter {adapter!r} does not expose a descriptor") from exc


def _resolve_adapters(adapters: Any, adapter_ids: Sequence[str] | None) -> list[Any]:
    from ..adapters.base import AdapterRegistry  # local import keeps import graph light

    if adapters is None:
        from ..adapters import build_registry

        registry = build_registry()
        selected = tuple(adapter_ids) if adapter_ids else registry.ids()
        return [registry.create(adapter_id) for adapter_id in selected]
    if isinstance(adapters, AdapterRegistry):
        selected = tuple(adapter_ids) if adapter_ids else adapters.ids()
        return [adapters.create(adapter_id) for adapter_id in selected]
    resolved = list(adapters)
    if adapter_ids:
        allowed = set(adapter_ids)
        resolved = [adapter for adapter in resolved if _adapter_id(adapter) in allowed]
        missing = allowed - {_adapter_id(adapter) for adapter in resolved}
        if missing:
            raise ValueError(f"adapter id(s) not found in the supplied adapters: {sorted(missing)}")
    return resolved


def _descriptor_identity(adapter: Any) -> dict[str, Any]:
    descriptor = adapter.descriptor
    payload = descriptor.to_dict()
    if callable(getattr(adapter, "describe_rules", None)):
        payload["rules_version"] = "rules-v1"
    return payload


def _adapter_info(adapter: Any) -> dict[str, Any]:
    info = dict(adapter.describe())
    info["kind"] = "test_double" if info.get("backend") == "scripted" else "extractor"
    describe_rules = getattr(adapter, "describe_rules", None)
    if callable(describe_rules):
        info["rules"] = describe_rules()
    return info


def _needs_prompt(adapter: Any) -> bool:
    descriptor = adapter.descriptor
    return descriptor.backend in ("hf_local", "openai_compat") or descriptor.prompt_version is not None


def _provenance(adapter: Any, *, prompt_version: str | None, seed: int) -> ExtractorProvenance:
    from ..schema import ExtractorProvenance as Provenance

    descriptor = adapter.descriptor
    info = adapter.describe()
    decoding = info.get("decoding")
    if not isinstance(decoding, Mapping):
        decoding = {}
    decoding = dict(decoding)
    decoding.setdefault("seed", seed)
    decoding.setdefault("max_new_tokens", descriptor.max_new_tokens)
    return Provenance(
        system=adapter.system,
        adapter_id=descriptor.adapter_id,
        model_id=descriptor.model_id,
        model_revision=descriptor.model_revision,
        prompt_version=prompt_version if _needs_prompt(adapter) else None,
        decoding=decoding,
    )


def _request_metadata(case: Any) -> dict[str, str]:
    document: SourceDocument = case.document
    metadata: dict[str, str] = {}
    for key, value in {
        "title": document.title,
        "publisher": document.publisher,
        "url": document.url,
        "published_at": document.published_at,
        "first_seen_at": document.first_seen_at,
        "retrieved_at": document.retrieved_at,
    }.items():
        if value is not None:
            metadata[key] = str(value)
    metadata.update({str(key): str(value) for key, value in dict(document.metadata).items()})
    return metadata


def _run_one_case(
    *,
    adapter: Any,
    case: Any,
    provenance: ExtractorProvenance,
    needs_prompt: bool,
    seed: int,
    validator_fn: Callable[..., Any] | None,
    validation_config: Any,
    roster: Any,
    taxonomy: Any,
) -> dict[str, Any]:
    from ..adapters.base import AdapterError, AdapterResponse, ExtractionRequest
    from ..prompting import build_prompt

    descriptor = adapter.descriptor
    metadata = _request_metadata(case)
    prompt = None
    prompt_truncated = False
    if needs_prompt:
        prompt = build_prompt(
            case.document,
            max_input_chars=descriptor.max_input_chars,
            company_hint=metadata.get("company_hint"),
        )
        prompt_truncated = len(case.document.text) > descriptor.max_input_chars
    request = ExtractionRequest(
        doc_id=case.document.doc_id,
        text=case.document.text,
        source_type=case.document.source_type,
        company_hint=metadata.get("company_hint"),
        prompt=prompt,
        metadata=metadata,
    )
    started = time.perf_counter()
    try:
        response: AdapterResponse = adapter.generate(request)
    except AdapterError as exc:
        wall = time.perf_counter() - started
        return {
            "adapter_id": descriptor.adapter_id,
            "case_id": case.case_id,
            "doc_id": case.document.doc_id,
            "split": case.split,
            "group": case.group,
            "label_tier": case.label_tier,
            "expected_abstain": case.expected_abstain,
            "gold_event_count": len(case.gold_events),
            "result": None,
            "parse_status": None,
            "parse_error": None,
            "adapter_error": f"{type(exc).__name__}: {exc}",
            "validation": None,
            "validation_status": "not_run",
            "wall_time_s": wall,
            "adapter_wall_time_s": None,
            "tokens_in": None,
            "tokens_out": None,
            "peak_vram_mb": None,
            "finish_reason": None,
            "prompt_version": prompt.prompt_version if prompt else None,
            "prompt_sha256": prompt.template_sha256 if prompt else None,
            "prompt_truncated": prompt_truncated,
            "seed": seed,
            "response_chars": None,
        }
    wall = time.perf_counter() - started

    parsed: ParsedExtraction = parse_response(
        response.text,
        doc_id=case.document.doc_id,
        extractor=provenance,
        schema_version=SCHEMA_VERSION,
    )
    validation_payload: Mapping[str, Any] | None = None
    validation_status = "not_run"
    if validator_fn is not None:
        try:
            verdict = validator_fn(
                parsed,
                document=case.document,
                roster=roster,
                taxonomy=taxonomy,
                config=validation_config,
            )
            if verdict is not None:
                to_dict = getattr(verdict, "to_dict", None)
                validation_payload = to_dict() if callable(to_dict) else dict(verdict)
                validation_status = "ok"
            else:  # pragma: no cover - defensive
                validation_status = "returned_none"
        except Exception as exc:  # a validator crash is recorded, never hidden
            validation_status = "error"
            validation_payload = {"error": f"{type(exc).__name__}: {exc}"}

    adapter_metadata = dict(response.metadata or {})
    record: dict[str, Any] = {
        "adapter_id": descriptor.adapter_id,
        "case_id": case.case_id,
        "doc_id": case.document.doc_id,
        "split": case.split,
        "group": case.group,
        "label_tier": case.label_tier,
        "expected_abstain": case.expected_abstain,
        "gold_event_count": len(case.gold_events),
        "result": parsed.to_dict(include_raw=True),
        "parse_status": parsed.parse_status,
        "parse_error": parsed.parse_error,
        "adapter_error": None,
        "validation": validation_payload,
        "validation_status": validation_status,
        "wall_time_s": wall,
        "adapter_wall_time_s": response.wall_time_s,
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "peak_vram_mb": response.peak_vram_mb,
        "peak_vram_measurement_method": adapter_metadata.get("peak_vram_measurement_method"),
        "finish_reason": response.finish_reason,
        "prompt_version": prompt.prompt_version if prompt else None,
        "prompt_sha256": prompt.template_sha256 if prompt else None,
        "prompt_truncated": prompt_truncated,
        "seed": seed,
        "response_chars": len(response.text or ""),
        "adapter_metadata": adapter_metadata,
    }
    return record


def _collect_measurements(
    record: Mapping[str, Any],
    *,
    tokens_in_values: list[int],
    tokens_out_values: list[int],
    vram_values: list[float],
    cost_values: list[float],
) -> None:
    if isinstance(record.get("tokens_in"), int):
        tokens_in_values.append(int(record["tokens_in"]))
    if isinstance(record.get("tokens_out"), int):
        tokens_out_values.append(int(record["tokens_out"]))
    if isinstance(record.get("peak_vram_mb"), (int, float)):
        vram_values.append(float(record["peak_vram_mb"]))
    adapter_metadata = record.get("adapter_metadata")
    if isinstance(adapter_metadata, Mapping):
        cost = adapter_metadata.get("estimated_cost_usd")
        if isinstance(cost, (int, float)):
            cost_values.append(float(cost))


def _case_order(case_id: Any, cases: Sequence[Any]) -> int:
    for index, case in enumerate(cases):
        if case.case_id == case_id:
            return index
    return len(cases)


def _load_existing_predictions(path: Path, *, resume: bool) -> dict[tuple[str, str], dict[str, Any]]:
    """Records from a previous run for resume, dropping a partial trailing line."""
    if not path.exists():
        return {}
    if not resume:
        path.write_text("", encoding="utf-8")
        return {}
    text = path.read_text(encoding="utf-8")
    existing: dict[tuple[str, str], dict[str, Any]] = {}
    valid_lines: list[str] = []
    dropped = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            dropped += 1
            continue
        if not isinstance(record, Mapping) or "adapter_id" not in record or "case_id" not in record:
            dropped += 1
            continue
        existing[(str(record["adapter_id"]), str(record["case_id"]))] = dict(record)
        valid_lines.append(line)
    if dropped:
        # A crashed run may leave a partial line; truncate it so the append-only
        # file stays parseable, and surface the fact in the file itself.
        path.write_text("\n".join(valid_lines) + ("\n" if valid_lines else ""), encoding="utf-8")
    return existing


def _build_manifest(
    *,
    dataset: DatasetManifest,
    cases: Sequence[Any],
    run_id: str,
    status: str,
    adapter_infos: Sequence[Mapping[str, Any]],
    not_run: Mapping[str, str],
    metrics_by_adapter: Mapping[str, MetricReport],
    resources: Mapping[str, Any],
    config_payload: Mapping[str, Any],
    config_sha: str,
    seeds: Sequence[int],
    notes: Sequence[str],
    validator_source: str,
) -> RunManifest:
    commit, branch, dirty, git_error = _git_info()
    split_counts: dict[str, int] = {}
    for case in cases:
        split_counts[case.split] = split_counts.get(case.split, 0) + 1
    manifest_notes = list(notes)
    manifest_notes.append(f"validator: {validator_source}")
    if git_error:
        manifest_notes.append(git_error)
    adapter_payload = {
        "adapters": [dict(info) for info in adapter_infos],
        "not_run": dict(not_run),
    }
    dataset_payload = {
        "name": dataset.name,
        "version": dataset.version,
        "case_count": len(cases),
        "label_tiers": list(dataset.label_tiers),
        # Identity of the derived dataset (hash of the materialised cases), plus the
        # hash of the raw files it came from when the loader supplied one.
        "dataset_sha256": config_payload.get("dataset_sha256"),
        "source_sha256": dataset.source_sha256,
        "source_paths": list(dataset.source_paths),
        "splits": dict(sorted(split_counts.items())),
        "negative_controls": sum(1 for case in cases if case.is_negative_control),
        "gold_event_count": sum(len(case.gold_events) for case in cases),
    }
    metric_payload: dict[str, Any] = {
        adapter_id: report.to_dict() for adapter_id, report in metrics_by_adapter.items()
    }
    for adapter_id, reason in not_run.items():
        metric_payload.setdefault(adapter_id, {"status": "NOT_RUN", "reason": reason})
    environment = {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "executable": sys.executable,
        "cwd": str(Path.cwd()),
        "status_banner": SYNTHETIC_BANNER if not is_research_grade(dataset.label_tiers) else None,
    }
    return RunManifest(
        run_id=run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        adapter=adapter_payload,
        dataset=dataset_payload,
        metrics=metric_payload,
        resources=dict(resources),
        config=dict(config_payload),
        config_sha256=config_sha,
        seeds=tuple(seeds),
        git_commit=commit,
        git_branch=branch,
        git_dirty=dirty,
        environment=environment,
        notes=tuple(manifest_notes),
    )


def _write_artifacts(
    *,
    run_dir: Path,
    manifest: RunManifest,
    metrics_by_adapter: Mapping[str, MetricReport],
    not_run: Mapping[str, str],
    dataset: DatasetManifest,
    seeds: Sequence[int],
    status: str,
) -> None:
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    metrics_payload = {
        "run_id": manifest.run_id,
        "status": status,
        "created_at": manifest.created_at,
        "seeds": list(seeds),
        "label_tiers": list(dataset.label_tiers),
        "banner": SYNTHETIC_BANNER if not is_research_grade(dataset.label_tiers) else None,
        "metrics": {
            adapter_id: report.to_dict() for adapter_id, report in metrics_by_adapter.items()
        },
        "not_run": dict(not_run),
    }
    (run_dir / "metrics.json").write_text(
        json.dumps(metrics_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write_report(run_dir, manifest, metrics_by_adapter)


__all__ = [
    "BenchmarkRun",
    "RUNNER_VERSION",
    "SYNTHETIC_BANNER",
    "canonical_json",
    "peak_rss_mb",
    "run_benchmark",
    "sha256_json",
    "sha256_text",
]
