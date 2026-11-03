"""Offline tests for the training-readiness layer (WP5).

Everything here runs on CPU with no model library, no network and no GPU.  The
point of the suite is the *refusals*: each readiness blocker is made to fire on
its own, each config violation is rejected, and the dataset builder refuses weak
labels instead of silently filtering them.  The one path that must succeed -- the
ready path -- is exercised with a synthetic manifest and a synthetic pinned config
so that the mechanism is proven without pretending any real data exists.

The fixture notes say ``SYNTHETIC TEST FIXTURE`` everywhere: no label in this file
is a human label, and the manifest names say so.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.local_llm_event_extraction.contracts import (
    DatasetCase,
    DatasetManifest,
    GoldEvent,
)
from experiments.local_llm_event_extraction.schema import (
    ExtractionResult,
    SourceDocument,
    result_from_dict,
)
from experiments.local_llm_event_extraction.training import checkpoint as checkpoint_module
from experiments.local_llm_event_extraction.training import dataset_builder, guard, qlora_config, run_train, runlog, vram_guard

ROOT = Path(__file__).resolve().parents[1]
TRAINING_DIR = ROOT / "experiments" / "local_llm_event_extraction" / "training"
MODULE = "experiments.local_llm_event_extraction.training"

PIN = "0f3a9c1d8e7b6a5f4c3d2e1f0a9b8c7d6e5f4a3b"
GATE_ENV = "MEDRADAR_LOCAL_LLM_ALLOW_TRAINING"
QUOTE = "Medtronic today announced a 510(k) clearance"


# --------------------------------------------------------------------------- fixtures
def _document(doc_id: str) -> SourceDocument:
    return SourceDocument(
        doc_id=doc_id,
        source_type="press_release",
        text=f"{QUOTE} for the Test Monitor 3000 on 2024-03-02.",
        title=f"Test document {doc_id}",
        published_at="2024-03-01",
        first_seen_at="2024-03-05",
        url="https://example.invalid/test",
        publisher="Test Publisher",
    )


def _gold(case_id: str, *, tier: str = "human_confirmed") -> GoldEvent:
    return GoldEvent(
        event_id=f"ev-{case_id}",
        company_canonical_id="medtronic",
        event_category="regulatory_clearance",
        event_date="2024-03-02",
        published_at="2024-03-01",
        product_or_technology="Test Monitor 3000",
        technology_domains=("patient_monitoring",),
        evidence_quote=QUOTE,
        label_tier=tier,
        label_source="SYNTHETIC TEST FIXTURE - not a human label",
    )


def _manifest(
    splits=(("train", 48), ("validation", 12), ("test", 24)),
    *,
    tier: str = "human_confirmed",
    leak: bool = False,
) -> DatasetManifest:
    cases = []
    for split, count in splits:
        for index in range(count):
            case_id = f"{split}-{index:03d}"
            cases.append(
                DatasetCase(
                    case_id=case_id,
                    document=_document(case_id),
                    gold_events=(_gold(case_id, tier=tier),),
                    expected_abstain=False,
                    label_tier=tier,
                    group=f"firm-{split}-{index:03d}",
                    split=split,
                )
            )
    if leak:
        # Same leakage group in train and test; split sizes unchanged, so only
        # SPLIT_LEAKAGE may fire.
        cases[-1] = dataclasses.replace(cases[-1], group=cases[0].group)
    return DatasetManifest(
        name="SYNTHETIC_TEST_FIXTURE",
        version="0",
        cases=tuple(cases),
        notes="SYNTHETIC TEST FIXTURE - these are not human labels and are not evidence of anything",
    )


def _ready_config(**overrides):
    values = {
        "revision": PIN,
        "enabled": True,
        "notes": (
            "hardware report: docs/HARDWARE_COMPATIBILITY.md (measured values recorded by the Team Lead)",
            "peak memory measured: measured in a dry run before authorisation",
        ),
    }
    values.update(overrides)
    return qlora_config.QLoRAConfig(**values)


def _ready_kwargs(tmp_path: Path, **overrides):
    kwargs = {
        "dataset": _manifest(),
        "checkpoint_root": str(tmp_path / "checkpoints"),
        "config": _ready_config(),
        "environ": {GATE_ENV: "1"},
        "explicit_flag": True,
        "min_disk_gb": 0.0,
    }
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------- guard: each blocker
def _gate_kwargs(tmp_path):
    return _ready_kwargs(tmp_path, environ={})


def _flag_kwargs(tmp_path):
    return _ready_kwargs(tmp_path, explicit_flag=False)


def _data_kwargs(tmp_path):
    return _ready_kwargs(tmp_path, dataset=None)


def _too_small_kwargs(tmp_path):
    return _ready_kwargs(tmp_path, dataset=_manifest((("train", 48), ("validation", 12), ("test", 5))))


def _leakage_kwargs(tmp_path):
    return _ready_kwargs(tmp_path, dataset=_manifest(leak=True))


def _pin_kwargs(tmp_path):
    return _ready_kwargs(tmp_path, config=_ready_config(revision="PENDING-A-PIN"))


def _root_kwargs(tmp_path):
    return _ready_kwargs(tmp_path, checkpoint_root="relative/checkpoints")


def _disk_kwargs(tmp_path):
    return _ready_kwargs(tmp_path, min_disk_gb=1_000_000_000.0)


def _vram_kwargs(tmp_path):
    return _ready_kwargs(tmp_path, config=_ready_config(vram_budget_mb=16384, abort_at_vram_mb=16384))


def _disabled_kwargs(tmp_path):
    return _ready_kwargs(tmp_path, config=_ready_config(enabled=False))


@pytest.mark.parametrize(
    "code,factory",
    [
        ("GATE_CLOSED", _gate_kwargs),
        ("NO_EXPLICIT_FLAG", _flag_kwargs),
        ("DATA_NOT_READY", _data_kwargs),
        ("SPLIT_TOO_SMALL", _too_small_kwargs),
        ("SPLIT_LEAKAGE", _leakage_kwargs),
        ("MODEL_NOT_PINNED", _pin_kwargs),
        ("CHECKPOINT_ROOT_UNSAFE", _root_kwargs),
        ("DISK_INSUFFICIENT", _disk_kwargs),
        ("VRAM_BUDGET_TOO_HIGH", _vram_kwargs),
        ("CONFIG_DISABLED", _disabled_kwargs),
    ],
)
def test_each_blocker_fires_individually(tmp_path, code, factory):
    readiness = guard.assess_readiness(**factory(tmp_path))
    assert readiness.ready is False
    assert readiness.blockers == (code,), f"expected only {code}, got {readiness.blockers}"
    entry = readiness.checks[[name for name, c in guard.CHECKS if c == code][0]]
    assert entry["ok"] is False
    assert entry["blocker_code"] == code
    assert entry["detail"], "every blocker must carry a human explanation"
    assert code in readiness.to_dict()["blockers"]


def test_ready_path_is_reachable(tmp_path):
    readiness = guard.assess_readiness(**_ready_kwargs(tmp_path))
    assert readiness.ready is True
    assert readiness.blockers == ()
    assert readiness.warnings == ()
    payload = readiness.to_dict()
    assert payload["ready"] is True
    assert set(payload["checks"]) == {name for name, _ in guard.CHECKS}
    assert all(entry["ok"] is not None for entry in payload["checks"].values()), (
        "the ready path must have evaluated every check"
    )


def test_warnings_do_not_block_but_are_reported(tmp_path):
    config = _ready_config(notes=("peak memory assumed: arithmetic only, not measured",))
    readiness = guard.assess_readiness(**_ready_kwargs(tmp_path, config=config))
    assert readiness.ready is True
    assert "W_PEAK_MEMORY_UNVERIFIED" in readiness.warnings
    assert "W_HARDWARE_REPORT_MISSING" in readiness.warnings


def test_waiving_human_labels_is_a_warning_not_a_silent_pass(tmp_path):
    readiness = guard.assess_readiness(
        **_ready_kwargs(tmp_path, require_human_labels=False, dataset=_manifest(tier="ai_preliminary"))
    )
    assert readiness.ready is True
    assert "W_LABELS_NOT_RESEARCH_GRADE" in readiness.warnings


def test_require_ready_raises_with_readiness_attached(tmp_path):
    readiness = guard.assess_readiness(**_gate_kwargs(tmp_path))
    with pytest.raises(guard.TrainingRefused) as excinfo:
        guard.require_ready(readiness)
    assert excinfo.value.readiness is readiness
    assert "GATE_CLOSED" in str(excinfo.value)


def test_require_ready_accepts_a_ready_assessment(tmp_path):
    readiness = guard.assess_readiness(**_ready_kwargs(tmp_path))
    assert guard.require_ready(readiness) is None


def test_checkpoint_root_inside_repository_is_refused(tmp_path):
    readiness = guard.assess_readiness(
        **_ready_kwargs(tmp_path, checkpoint_root=str(TRAINING_DIR / "checkpoints"))
    )
    assert "CHECKPOINT_ROOT_UNSAFE" in readiness.blockers
    detail = readiness.checks["checkpoint_root"]["detail"]
    assert "inside the repository" in detail


def test_unassigned_cases_are_a_data_blocker(tmp_path):
    manifest = _manifest()
    cases = list(manifest.cases)
    cases[0] = dataclasses.replace(cases[0], split="unassigned")
    broken = dataclasses.replace(manifest, cases=tuple(cases))
    readiness = guard.assess_readiness(**_ready_kwargs(tmp_path, dataset=broken))
    assert "DATA_NOT_READY" in readiness.blockers
    assert "unassigned" in readiness.checks["dataset"]["detail"]


def test_missing_group_is_a_leakage_blocker(tmp_path):
    manifest = _manifest()
    cases = list(manifest.cases)
    cases[0] = dataclasses.replace(cases[0], group="")
    readiness = guard.assess_readiness(**_ready_kwargs(tmp_path, dataset=dataclasses.replace(manifest, cases=tuple(cases))))
    assert "SPLIT_LEAKAGE" in readiness.blockers


def test_readiness_output_is_deterministic(tmp_path):
    first = guard.assess_readiness(**_ready_kwargs(tmp_path)).to_dict()
    second = guard.assess_readiness(**_ready_kwargs(tmp_path)).to_dict()
    # Free disk space is a live measurement, so it is excluded from the equality
    # claim: everything the guard decides must be stable, the measured free space
    # is allowed to be whatever the disk actually reports.
    for payload in (first, second):
        payload["checks"].pop("disk_space")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# ------------------------------------------------------------- qlora config validation
def test_committed_draft_loads_and_is_disabled():
    config = qlora_config.load_draft()
    assert config.enabled is False
    assert config.executed is False
    assert config.revision == "PENDING-A-PIN"
    assert qlora_config.is_pinned(config.revision) is False
    assert config.quantization == "nf4"
    assert config.base_adapter_id == "hf-qwen3-4b"


def test_draft_metadata_records_provenance():
    document = qlora_config.load_document()
    notes = document.metadata.get("_notes")
    assert isinstance(notes, dict)
    assert "PENDING-A-PIN" in json.dumps(notes) or "read_this_first" in notes
    measured = notes["measured_by_the_team_lead"]
    assert measured["vram_total_mb"] == 16384
    assert measured["wsl2_installed"] is False
    assumed = notes["assumed_or_estimated"]
    assert assumed["throughput"]["tokens_per_second"] is None
    assert "ASSUMED" in assumed["peak_process_vram_mb"]["provenance"]
    assert document.sha256 and len(document.sha256) == 64


def test_config_dict_roundtrip():
    config = _ready_config()
    assert qlora_config.QLoRAConfig.from_dict(config.to_dict()) == config
    payload = config.to_dict()
    payload["_notes"] = {"ignored": True}
    assert qlora_config.QLoRAConfig.from_dict(payload) == config


def test_config_rejects_unknown_key():
    with pytest.raises(qlora_config.ConfigError, match="unknown key"):
        qlora_config.QLoRAConfig.from_dict({"revision": PIN, "learning_rate_x": 1})


def test_config_rejects_floating_revision_in_both_modes():
    config = qlora_config.QLoRAConfig(revision="main")
    with pytest.raises(qlora_config.ConfigError, match="floating ref"):
        config.validate(draft=False)
    with pytest.raises(qlora_config.ConfigError, match="floating ref"):
        config.validate(draft=True)


def test_config_rejects_enabled_true_in_a_draft():
    with pytest.raises(qlora_config.ConfigError, match="enabled=True in a draft"):
        _ready_config().validate(draft=True)


def test_config_run_mode_requires_a_real_pin():
    with pytest.raises(qlora_config.ConfigError, match="placeholder"):
        _ready_config(revision="PENDING-A-PIN").validate(draft=False)
    with pytest.raises(qlora_config.ConfigError, match="revision is required"):
        _ready_config(revision="").validate(draft=False)
    assert _ready_config().validate(draft=False).revision == PIN


def test_config_rejects_placeholder_in_draft_only_as_readiness_blocker():
    # A draft may *declare* the placeholder; the guard turns it into MODEL_NOT_PINNED.
    assert qlora_config.load_draft().validate(draft=True).revision == "PENDING-A-PIN"


def test_config_always_rejects_executed():
    for mode in (True, False):
        with pytest.raises(qlora_config.ConfigError, match="executed=True"):
            _ready_config(executed=True).validate(draft=mode)


def test_config_rejects_resume_in_draft():
    with pytest.raises(qlora_config.ConfigError, match="resume_from"):
        _ready_config(resume_from="/tmp/state").validate(draft=True)


@pytest.mark.parametrize(
    "overrides",
    [
        {"r": 0},
        {"alpha": 0},
        {"dropout": 0.9},
        {"learning_rate": 0.05},
        {"learning_rate": 0.0},
        {"warmup_ratio": 0.7},
        {"num_epochs": 0},
        {"max_seq_len": 64},
        {"per_device_batch_size": 0},
        {"gradient_accumulation_steps": 0},
        {"seed": -1},
        {"vram_budget_mb": 0},
        {"abort_at_vram_mb": 14336},  # == budget: not greater
        {"save_steps": 0},
        {"quantization": "int8"},
        {"compute_dtype": "float32"},
        {"bias": "weird"},
        {"lr_scheduler": "poly"},
        {"target_modules": "bad modules !"},
        {"base_adapter_id": "Not An Adapter Id"},
    ],
)
def test_config_rejects_out_of_range_values(overrides):
    with pytest.raises(qlora_config.ConfigError):
        _ready_config(**overrides).validate(draft=False)


def test_load_draft_refuses_enabled_file(tmp_path):
    payload = _ready_config().to_dict()
    target = tmp_path / "enabled.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    assert qlora_config.load_document(target).config.enabled is True
    with pytest.raises(qlora_config.ConfigError, match="enabled=true"):
        qlora_config.load_draft(target)


def test_load_draft_refuses_broken_json(tmp_path):
    target = tmp_path / "broken.json"
    target.write_text("{not json", encoding="utf-8")
    with pytest.raises(qlora_config.ConfigError, match="not valid UTF-8 JSON"):
        qlora_config.load_draft(target)


# ---------------------------------------------------------------- dataset_builder
def test_bundle_builds_and_reuses_the_frozen_contracts():
    manifest = _manifest()
    bundle = dataset_builder.build_sft_records(manifest)
    assert bundle.counts == {"train": 48, "validation": 12, "test": 24}
    assert bundle.total == 84
    assert bundle.rejected == {}
    assert bundle.label_tiers == ("human_confirmed",)
    assert len(bundle.sha256) == 64

    record = bundle.train[0]
    assert set(record) == {"case_id", "system", "user", "target_json", "meta"}
    assert set(record["meta"]) == {"label_tier", "group", "split"}
    assert record["meta"]["split"] == "train"
    assert record["system"] and record["user"]
    assert "\n" not in record["target_json"]

    result = result_from_dict(json.loads(record["target_json"]))
    assert isinstance(result, ExtractionResult)
    assert result.parse_status == "ok"
    assert result.extractor.system == dataset_builder.GOLD_SYSTEM
    assert len(result.events) == 1
    event = result.events[0]
    assert event.status == "extracted"
    assert event.event_category == "regulatory_clearance"
    assert event.evidence[0].quote == QUOTE
    assert event.timestamp_quality.event_date == "exact_day"
    assert event.timestamp_quality.published_at == "exact_day"
    assert event.timestamp_quality.first_seen_at == "absent"


def test_bundle_sha256_is_deterministic_and_sensitive():
    first = dataset_builder.build_sft_records(_manifest())
    second = dataset_builder.build_sft_records(_manifest())
    assert first.sha256 == second.sha256
    other = dataset_builder.build_sft_records(_manifest((("train", 48), ("validation", 12), ("test", 23))))
    assert other.sha256 != first.sha256


def test_bundle_refuses_ai_preliminary_labels():
    with pytest.raises(dataset_builder.DataNotReady) as excinfo:
        dataset_builder.build_sft_records(_manifest(tier="ai_preliminary"))
    assert excinfo.value.rejected == {"ai_preliminary": 84}
    assert "ai_preliminary" in " ".join(excinfo.value.reasons)


def test_bundle_refuses_no_cases():
    manifest = DatasetManifest(name="empty", version="0", cases=())
    with pytest.raises(dataset_builder.DataNotReady, match="no cases"):
        dataset_builder.build_sft_records(manifest)


def test_bundle_refuses_empty_split():
    with pytest.raises(dataset_builder.DataNotReady, match="'test' split is empty"):
        dataset_builder.build_sft_records(_manifest((("train", 48), ("validation", 12))))


def test_bundle_refuses_split_leakage():
    with pytest.raises(dataset_builder.DataNotReady) as excinfo:
        dataset_builder.build_sft_records(_manifest(leak=True))
    assert "cross splits" in " ".join(excinfo.value.reasons)


def test_bundle_refuses_unassigned_case():
    manifest = _manifest()
    cases = list(manifest.cases)
    cases[0] = dataclasses.replace(cases[0], split="unassigned")
    with pytest.raises(dataset_builder.DataNotReady, match="only .* may appear"):
        dataset_builder.build_sft_records(dataclasses.replace(manifest, cases=tuple(cases)))


def test_bundle_refuses_case_without_group():
    manifest = _manifest()
    cases = list(manifest.cases)
    cases[0] = dataclasses.replace(cases[0], group="")
    with pytest.raises(dataset_builder.DataNotReady, match="no leakage group"):
        dataset_builder.build_sft_records(dataclasses.replace(manifest, cases=tuple(cases)))


def test_bundle_refuses_gold_event_without_evidence():
    manifest = _manifest()
    cases = list(manifest.cases)
    broken_gold = dataclasses.replace(cases[0].gold_events[0], evidence_quote=None)
    cases[0] = dataclasses.replace(cases[0], gold_events=(broken_gold,))
    with pytest.raises(dataset_builder.DataNotReady, match="no evidence_quote"):
        dataset_builder.build_sft_records(dataclasses.replace(manifest, cases=tuple(cases)))


def test_bundle_refuses_gold_event_outside_the_vocabulary():
    manifest = _manifest()
    cases = list(manifest.cases)
    broken_gold = dataclasses.replace(cases[0].gold_events[0], event_category="invented_category")
    cases[0] = dataclasses.replace(cases[0], gold_events=(broken_gold,))
    with pytest.raises(dataset_builder.DataNotReady, match="not in the pre-registered vocabulary"):
        dataset_builder.build_sft_records(dataclasses.replace(manifest, cases=tuple(cases)))


def test_bundle_accepts_a_mapping_prompt_builder():
    bundle = dataset_builder.build_sft_records(
        _manifest(), prompt_builder=lambda document: {"system": "SYS-TEST", "user": "USER-TEST"}
    )
    assert bundle.train[0]["system"] == "SYS-TEST"
    assert bundle.train[0]["user"] == "USER-TEST"


def test_bundle_accepts_an_object_prompt_builder():
    bundle = dataset_builder.build_sft_records(
        _manifest(), prompt_builder=lambda document: SimpleNamespace(system="SYS-OBJ", user="USER-OBJ")
    )
    assert bundle.validation[0]["system"] == "SYS-OBJ"


def test_bundle_falls_back_when_prompt_builder_has_a_bad_signature():
    def broken(document):
        raise TypeError("signature drift")

    bundle = dataset_builder.build_sft_records(_manifest(), prompt_builder=broken)
    assert "PROVISIONAL FALLBACK" in bundle.train[0]["system"]


def test_fallback_prompt_is_used_when_prompting_module_is_absent(monkeypatch):
    monkeypatch.setattr(dataset_builder, "_import_prompt_builder", lambda: None)
    bundle = dataset_builder.build_sft_records(_manifest())
    assert "PROVISIONAL FALLBACK" in bundle.train[0]["system"]
    assert dataset_builder.FALLBACK_PROMPT_VERSION in bundle.train[0]["system"]


def test_manifest_loader_roundtrips_a_fixture(tmp_path):
    manifest = _manifest()
    payload = {
        "name": "SYNTHETIC_TEST_FIXTURE",
        "version": "0",
        "notes": "SYNTHETIC TEST FIXTURE",
        "cases": [
            {
                "case_id": case.case_id,
                "document": case.document.to_dict(),
                "gold_events": [event.to_dict() for event in case.gold_events],
                "expected_abstain": case.expected_abstain,
                "label_tier": case.label_tier,
                "group": case.group,
                "split": case.split,
            }
            for case in manifest.cases
        ],
    }
    target = tmp_path / "manifest.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    loaded = dataset_builder.load_manifest(target)
    assert loaded.case_count == 84
    bundle = dataset_builder.build_sft_records(loaded)
    assert bundle.counts == {"train": 48, "validation": 12, "test": 24}


def test_manifest_loader_refuses_broken_json(tmp_path):
    target = tmp_path / "broken.json"
    target.write_text("[not a manifest", encoding="utf-8")
    with pytest.raises(dataset_builder.DataNotReady, match="not valid UTF-8 JSON"):
        dataset_builder.load_manifest(target)


def test_manifest_loader_refuses_missing_file(tmp_path):
    with pytest.raises(dataset_builder.DataNotReady, match="cannot read"):
        dataset_builder.load_manifest(tmp_path / "absent.json")


# ---------------------------------------------------------------------- runlog
def test_runlog_append_read_and_order(tmp_path):
    log = runlog.RunLog(tmp_path / "runs")
    first = log.append("readiness_assessed", {"status": "refused", "ready": False})
    log.append("run_started", {"status": "running"})
    log.append("run_aborted", {"status": "aborted", "peak_vram_mb": 12000})

    records = log.read_all()
    assert [record["event"] for record in records] == [
        "readiness_assessed",
        "run_started",
        "run_aborted",
    ]
    assert records[0]["payload"]["ready"] is False
    assert first["event"] == "readiness_assessed"
    parsed = datetime.fromisoformat(records[0]["ts"])
    assert parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0
    assert log.latest_status() == "aborted"
    assert json.loads(log.to_json())[-1]["payload"]["peak_vram_mb"] == 12000


def test_runlog_is_append_only_across_instances(tmp_path):
    root = tmp_path / "runs"
    runlog.RunLog(root).append("a", {})
    runlog.RunLog(root).append("b", {})
    assert [record["event"] for record in runlog.RunLog(root).read_all()] == ["a", "b"]


def test_runlog_latest_status_without_status_events(tmp_path):
    log = runlog.RunLog(tmp_path / "runs")
    assert log.latest_status() is None
    log.append("note", {"text": "no status here"})
    assert log.latest_status() is None


def test_runlog_refuses_path_escape(tmp_path):
    with pytest.raises(runlog.PathEscapeError):
        runlog.RunLog(tmp_path, "../escaped.jsonl")
    with pytest.raises(runlog.PathEscapeError):
        runlog.RunLog(tmp_path, "sub/dir/log.jsonl")
    with pytest.raises(runlog.PathEscapeError):
        runlog.RunLog(tmp_path, "..")


def test_runlog_refuses_bad_records(tmp_path):
    log = runlog.RunLog(tmp_path / "runs")
    with pytest.raises(runlog.RunLogError):
        log.append("", {})
    with pytest.raises(runlog.RunLogError):
        log.append("event", ["not", "a", "mapping"])


def test_runlog_refuses_to_skip_a_malformed_line(tmp_path):
    log = runlog.RunLog(tmp_path / "runs")
    log.append("good", {})
    with open(log.path, "a", encoding="utf-8") as handle:
        handle.write("{torn\n")
    with pytest.raises(runlog.RunLogError, match="not valid JSON"):
        log.read_all()


# -------------------------------------------------------------------- checkpoint
def test_plan_resume_absent_returns_none(tmp_path):
    assert checkpoint_module.plan_resume(tmp_path / "ckpts", "run-1") is None


def test_write_state_then_plan_resume(tmp_path):
    root = tmp_path / "ckpts"
    written = checkpoint_module.write_state(
        root, "run-1", {"latest_step": 50, "rng_state": {"seed": 20261104, "torch_rng": [1, 2]}}
    )
    assert written.name == "state.json"
    plan = checkpoint_module.plan_resume(root, "run-1")
    assert isinstance(plan, checkpoint_module.ResumePlan)
    assert plan.run_id == "run-1"
    assert plan.latest_step == 50
    assert plan.rng_state == {"seed": 20261104, "torch_rng": [1, 2]}
    resolved_root = (tmp_path / "ckpts").resolve()
    assert Path(plan.state_path).resolve().is_relative_to(resolved_root)
    assert Path(plan.adapter_path).resolve().is_relative_to(resolved_root)
    assert plan.to_dict()["latest_step"] == 50


@pytest.mark.parametrize("bad_run_id", ["..", "../escape", "a/b", "a\\b", "C:/tmp/x", "/abs", ""])
def test_checkpoint_rejects_path_traversal(tmp_path, bad_run_id):
    root = tmp_path / "ckpts"
    with pytest.raises(checkpoint_module.PathEscapeError):
        checkpoint_module.plan_resume(root, bad_run_id)
    with pytest.raises(checkpoint_module.PathEscapeError):
        checkpoint_module.write_state(root, bad_run_id, {"latest_step": 0})


def test_checkpoint_refuses_bad_state(tmp_path):
    root = tmp_path / "ckpts"
    run_dir = root / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(checkpoint_module.CheckpointError, match="not valid JSON"):
        checkpoint_module.plan_resume(root, "run-1")

    (run_dir / "state.json").write_text(json.dumps({"latest_step": -1}), encoding="utf-8")
    with pytest.raises(checkpoint_module.CheckpointError, match="latest_step"):
        checkpoint_module.plan_resume(root, "run-1")

    with pytest.raises(checkpoint_module.CheckpointError, match="latest_step"):
        checkpoint_module.write_state(root, "run-1", {"latest_step": "fifty"})


# -------------------------------------------------------------------- vram_guard
def test_vram_budget_from_draft_config():
    budget = vram_guard.budget_from_config(qlora_config.load_draft())
    assert budget.total_mb == 16384
    assert budget.warn_at_mb == 14336
    assert budget.abort_at_mb == 15360


@pytest.mark.parametrize(
    "used_mb,reserved_mb,expected",
    [
        (0, 0, "continue"),
        (14335, 0, "continue"),
        (14336, 0, "warn"),  # exactly at the warn threshold: warn (>=)
        (14337, 0, "warn"),
        (15359, 0, "warn"),
        (15360, 0, "abort"),  # exactly at the abort threshold: abort (>=)
        (15361, 0, "abort"),
        (14335, 1, "warn"),  # reserved memory pushes it to the warn boundary
        (15359, 1, "abort"),  # reserved memory pushes it over the abort boundary
        (16384, 0, "abort"),
    ],
)
def test_vram_decide_boundaries(used_mb, reserved_mb, expected):
    budget = vram_guard.VramBudget(total_mb=16384, warn_at_mb=14336, abort_at_mb=15360)
    decision = budget.decide(used_mb, reserved_mb)
    assert decision.action == expected
    assert decision.projected_mb == used_mb + reserved_mb
    assert decision.used_mb == used_mb and decision.reserved_mb == reserved_mb
    assert decision.reason
    assert decision.to_dict()["action"] == expected
    assert vram_guard.decide(budget, used_mb, reserved_mb).action == expected


def test_vram_budget_rejects_inconsistent_thresholds():
    with pytest.raises(ValueError):
        vram_guard.VramBudget(total_mb=0, warn_at_mb=1, abort_at_mb=2)
    with pytest.raises(ValueError):
        vram_guard.VramBudget(total_mb=16384, warn_at_mb=0, abort_at_mb=15360)
    with pytest.raises(ValueError):
        vram_guard.VramBudget(total_mb=16384, warn_at_mb=15360, abort_at_mb=14336)
    with pytest.raises(ValueError):
        vram_guard.VramBudget(total_mb=16384, warn_at_mb=14336, abort_at_mb=17000)


def test_vram_decide_refuses_negative_measurements():
    budget = vram_guard.VramBudget(total_mb=16384, warn_at_mb=14336, abort_at_mb=15360)
    with pytest.raises(ValueError):
        budget.decide(-1, 0)
    with pytest.raises(ValueError):
        budget.decide(0, -1)
    with pytest.raises(ValueError):
        budget.decide(1.5, 0)


# ----------------------------------------------------------------------- CLI
def _write_cli_fixture(tmp_path: Path, *, tier: str = "human_confirmed", splits=(("train", 48), ("validation", 12), ("test", 24))):
    manifest = _manifest(splits, tier=tier)
    payload = {
        "name": "SYNTHETIC_TEST_FIXTURE",
        "version": "0",
        "notes": "SYNTHETIC TEST FIXTURE - not human labels",
        "cases": [
            {
                "case_id": case.case_id,
                "document": case.document.to_dict(),
                "gold_events": [event.to_dict() for event in case.gold_events],
                "expected_abstain": case.expected_abstain,
                "label_tier": case.label_tier,
                "group": case.group,
                "split": case.split,
            }
            for case in manifest.cases
        ],
    }
    target = tmp_path / "manifest.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _write_ready_config(tmp_path: Path) -> Path:
    payload = _ready_config().to_dict()
    payload["_notes"] = {
        "assumed_or_estimated": {
            "peak_process_vram_mb": {
                "low": 7168,
                "high": 12288,
                "provenance": "ASSUMED - test fixture value, not a measurement",
            }
        }
    }
    target = tmp_path / "ready.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_cli_exit_2_when_gate_is_closed(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(GATE_ENV, raising=False)
    dataset = tmp_path / "does-not-exist.json"  # proves the gate is checked before the dataset is read
    code = run_train.main(
        [
            "--config",
            str(qlora_config.DEFAULT_CONFIG_PATH),
            "--dataset-manifest",
            str(dataset),
            "--checkpoint-root",
            str(tmp_path / "ckpts"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    first_line = captured.err.splitlines()[0]
    assert first_line.startswith("REFUSED (2): training gate is closed")
    payload = json.loads(captured.err.splitlines()[1])
    assert payload["exit_code"] == 2
    assert "GATE_CLOSED" in payload["blockers"]
    assert "GATE_CLOSED" in payload["readiness"]["blockers"]
    assert captured.out == ""


def test_cli_exit_2_when_config_is_unusable(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(GATE_ENV, "1")
    code = run_train.main(
        [
            "--config",
            str(tmp_path / "absent.json"),
            "--dataset-manifest",
            str(_write_cli_fixture(tmp_path)),
            "--checkpoint-root",
            str(tmp_path / "ckpts"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert captured.err.splitlines()[0].startswith("REFUSED (2): config unusable")


def test_cli_exit_3_with_the_committed_draft(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(GATE_ENV, "1")
    code = run_train.main(
        [
            "--config",
            str(qlora_config.DEFAULT_CONFIG_PATH),
            "--dataset-manifest",
            str(_write_cli_fixture(tmp_path)),
            "--checkpoint-root",
            str(tmp_path / "ckpts"),
            "--enable-training",
            "--i-understand",
        ]
    )
    captured = capsys.readouterr()
    assert code == 3
    first_line = captured.err.splitlines()[0]
    assert first_line.startswith("REFUSED (3): readiness blockers:")
    assert "CONFIG_DISABLED" in first_line
    assert "MODEL_NOT_PINNED" in first_line
    job = json.loads(captured.err.splitlines()[1])
    assert job["exit_code"] == 3
    assert "CONFIG_DISABLED" in job["blockers"]
    assert captured.out == ""


def test_cli_exit_3_with_weak_labels(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(GATE_ENV, "1")
    code = run_train.main(
        [
            "--config",
            str(_write_ready_config(tmp_path)),
            "--dataset-manifest",
            str(_write_cli_fixture(tmp_path, tier="ai_preliminary")),
            "--checkpoint-root",
            str(tmp_path / "ckpts"),
            "--enable-training",
            "--i-understand",
        ]
    )
    captured = capsys.readouterr()
    assert code == 3
    payload = json.loads(captured.err.splitlines()[1])
    assert "DATA_NOT_READY" in payload["blockers"]


def test_cli_exit_3_without_explicit_flags(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(GATE_ENV, "1")
    code = run_train.main(
        [
            "--config",
            str(_write_ready_config(tmp_path)),
            "--dataset-manifest",
            str(_write_cli_fixture(tmp_path)),
            "--checkpoint-root",
            str(tmp_path / "ckpts"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 3
    payload = json.loads(captured.err.splitlines()[1])
    assert "NO_EXPLICIT_FLAG" in payload["blockers"]


def test_cli_exit_4_phase_guard_and_plan(tmp_path, monkeypatch, capsys):
    free_gib = shutil.disk_usage(tmp_path).free / (1024**3)
    if free_gib < 20.0:  # pragma: no cover - depends on the machine running the tests
        pytest.skip(f"exit-4 needs >= 20 GiB free on the pytest tmp drive, found {free_gib:.1f} GiB")
    monkeypatch.setenv(GATE_ENV, "1")
    code = run_train.main(
        [
            "--config",
            str(_write_ready_config(tmp_path)),
            "--dataset-manifest",
            str(_write_cli_fixture(tmp_path)),
            "--checkpoint-root",
            str(tmp_path / "ckpts"),
            "--enable-training",
            "--i-understand",
        ]
    )
    captured = capsys.readouterr()
    assert code == 4
    first_line = captured.out.splitlines()[0]
    assert first_line == run_train.PHASE_GUARD_MESSAGE
    assert first_line == "PHASE_GUARD: training is not executed in this phase"
    plan = json.loads("\n".join(captured.out.splitlines()[1:]))
    assert plan["exit_code"] == 4
    assert plan["base_model"]["revision"] == PIN
    assert plan["training_config"]["values"]["enabled"] is True
    assert plan["dataset"]["counts"] == {"train": 48, "validation": 12, "test": 24}
    assert plan["dataset"]["label_tiers"] == ["human_confirmed"]
    assert plan["resources"]["estimated_peak_vram_mb"]["provenance"].startswith("ASSUMED")
    assert plan["resources"]["measured_here"]["peak_vram_mb"] is None
    assert plan["resources"]["vram_budget_mb"] == 14336
    assert plan["output"]["run_log"].endswith("runlog.jsonl")
    assert captured.err == ""
    assert not (tmp_path / "ckpts").exists(), "the CLI must not write anything to the checkpoint root"


def test_cli_with_committed_draft_never_reaches_exit_4(tmp_path, monkeypatch, capsys):
    """The committed draft is disabled AND unpinned, so exit 4 is unreachable by design."""
    monkeypatch.setenv(GATE_ENV, "1")
    code = run_train.main(
        [
            "--config",
            str(qlora_config.DEFAULT_CONFIG_PATH),
            "--dataset-manifest",
            str(_write_cli_fixture(tmp_path)),
            "--checkpoint-root",
            str(tmp_path / "ckpts"),
            "--enable-training",
            "--i-understand",
        ]
    )
    capsys.readouterr()
    assert code == 3


# ------------------------------------------------------- no ML library may be imported
TRAINING_MODULES = (
    "guard",
    "qlora_config",
    "dataset_builder",
    "runlog",
    "checkpoint",
    "vram_guard",
    "run_train",
)


def test_importing_every_training_module_pulls_in_no_ml_library():
    for name in TRAINING_MODULES:
        importlib.import_module(f"{MODULE}.{name}")
    for library in ("torch", "transformers", "peft", "bitsandbytes", "accelerate", "datasets"):
        assert library not in sys.modules, f"{library} was imported by the training package"


def test_training_sources_never_import_torch_or_transformers():
    pattern = re.compile(r"^\s*(?:import|from)\s+(torch|transformers|peft|bitsandbytes)\b", re.MULTILINE)
    for path in sorted(TRAINING_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert not pattern.search(text), f"{path} imports a model library at module scope"


def test_guard_module_is_reachable_without_a_dataset():
    readiness = guard.assess_readiness()
    assert readiness.ready is False
    assert "GATE_CLOSED" in readiness.blockers
    assert "DATA_NOT_READY" in readiness.blockers
    assert readiness.checks["split_sizes"]["ok"] is None, "a missing dataset must not fake a split failure"
