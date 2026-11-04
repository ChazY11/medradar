"""Offline tests for the read-only environment probe (no GPU, no network).

The probe lives outside the importable package (``.../scripts/env_probe.py``), so
it is loaded from its file path.  Every test injects a scripted command runner:
nothing here shells out to ``nvidia-smi``, ``powershell`` or WSL, so the suite is
deterministic and runs on a machine with no GPU at all.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE_PATH = (
    REPO_ROOT / "experiments" / "local_llm_event_extraction" / "scripts" / "env_probe.py"
)


def _load_probe():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "medradar_env_probe_under_test", PROBE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load_probe()

GATE_NAMES = {"model_load", "training", "network", "remote_api"}
GATE_ENV_VARS = {
    "MEDRADAR_LOCAL_LLM_ALLOW_MODEL_LOAD",
    "MEDRADAR_LOCAL_LLM_ALLOW_TRAINING",
    "MEDRADAR_LOCAL_LLM_ALLOW_NETWORK",
    "MEDRADAR_LOCAL_LLM_ALLOW_REMOTE_API",
}

TOP_LEVEL_KEYS = {
    "probe_version",
    "schema_version",
    "generated_at",
    "generated_at_utc",
    "probe_duration_s",
    "read_only",
    "command_policy",
    "host",
    "os",
    "cpu",
    "memory",
    "disks",
    "gpu",
    "wsl",
    "python",
    "packages",
    "safety_gates",
    "limitations",
}

SECTION_KEYS = (
    "os",
    "cpu",
    "memory",
    "disks",
    "gpu",
    "wsl",
    "python",
    "packages",
    "safety_gates",
)


# --------------------------------------------------------------------- fixtures
def result(argv, **kwargs):
    """A CommandResult whose argv matches what the caller asked for."""
    return probe.CommandResult(argv=tuple(argv), **kwargs)


class ScriptedRunner:
    """Deterministic command runner keyed by executable name.

    Values may be a ``CommandResult``, a callable ``(argv, timeout)`` or an
    exception to raise.  Unlisted commands fail with exit code 1.
    """

    def __init__(self, results=None):
        self.results = dict(results or {})
        self.calls = []

    def __call__(self, argv, timeout):
        argv = tuple(argv)
        self.calls.append({"argv": argv, "timeout": timeout})
        key = os.path.basename(argv[0]).lower() if argv else ""
        value = self.results.get(key)
        if value is None:
            return result(argv, returncode=1, stderr="scripted: no such command")
        if isinstance(value, BaseException):
            raise value
        if callable(value):
            return value(argv, timeout)
        return value

    def commands(self):
        return [call["argv"] for call in self.calls]


def failing_runner():
    return ScriptedRunner()


def timing_out_runner():
    def runner(argv, timeout):
        return result(argv, timed_out=True, error=f"timed out after {timeout:.1f}s")

    return runner


def collecting(monkeypatch, runner):
    """Collect twice with the four gate variables removed (default posture)."""
    for name in GATE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return probe.collect_environment(command_runner=runner)


# ----------------------------------------------------------------------- schema
def test_document_exposes_documented_top_level_keys(monkeypatch):
    document = collecting(monkeypatch, failing_runner())
    assert TOP_LEVEL_KEYS <= set(document)
    assert document["probe_version"] == probe.PROBE_VERSION
    assert document["schema_version"] == probe.SCHEMA_VERSION
    assert document["read_only"] is True
    assert document["command_policy"]["installs"] is False
    assert document["command_policy"]["network"] is False
    assert document["command_policy"]["elevation_required"] is False
    # A timestamp with an explicit UTC offset, so the reader knows the zone.
    assert "T" in document["generated_at"]
    assert document["generated_at_utc"].endswith("Z")


def test_every_section_reports_a_known_status(monkeypatch):
    document = collecting(monkeypatch, failing_runner())
    for key in SECTION_KEYS:
        section = document[key]
        assert isinstance(section, dict), key
        assert section["status"] in probe.STATUSES, (key, section["status"])
    assert isinstance(document["limitations"], list)


def test_json_document_round_trips(monkeypatch):
    document = collecting(monkeypatch, failing_runner())
    encoded = json.dumps(document, ensure_ascii=False)
    assert json.loads(encoded) == document


# ------------------------------------------------------------- degraded probes
def test_failing_commands_become_unavailable_markers(monkeypatch):
    document = collecting(monkeypatch, failing_runner())
    gpu = document["gpu"]
    assert gpu["status"] == "unavailable"
    assert "nvidia-smi" in gpu["reason"]
    assert any(item["probe"] == "gpu" for item in document["limitations"])
    # Not command-based, so still measured even when every command fails.
    assert document["memory"]["status"] == "ok"
    assert document["safety_gates"]["status"] == "ok"


def test_timed_out_commands_still_yield_a_valid_document(monkeypatch):
    document = collecting(monkeypatch, timing_out_runner())
    assert json.loads(json.dumps(document)) == document
    assert document["gpu"]["status"] == "unavailable"
    assert "timed out" in document["gpu"]["reason"]
    assert document["probe_duration_s"] is not None


def test_missing_executable_marks_wsl_unavailable(monkeypatch):
    def runner(argv, timeout):
        raise FileNotFoundError(f"scripted missing executable: {argv[0]}")

    document = collecting(monkeypatch, runner)
    wsl = document["wsl"]
    assert wsl["status"] == "unavailable"
    assert "not found" in wsl["reason"]


def test_successful_wsl_status_is_a_measurement(monkeypatch):
    def wsl_runner(argv, timeout):
        if "--status" in argv:
            return result(
                argv, returncode=0, stderr="Default Distribution: Ubuntu-24.04\nDefault Version: 2"
            )
        if "-l" in argv:
            return result(
                argv,
                returncode=0,
                stdout="  NAME            STATE           VERSION\n* Ubuntu-24.04   Running         2\n",
            )
        if "--version" in argv:
            return result(
                argv,
                returncode=0,
                stdout="WSL version: 2.6.1.0\nKernel version: 6.6.87.2-1\nDefault Version: 2\n",
            )
        return result(argv, returncode=1)

    document = probe.collect_environment(
        command_runner=ScriptedRunner({"wsl.exe": wsl_runner})
    )
    wsl = document["wsl"]
    assert wsl["status"] == "ok"
    assert wsl["installed"] is True
    assert wsl["default_version"] == 2
    assert [d["name"] for d in wsl["distributions"]] == ["Ubuntu-24.04"]
    assert wsl["distributions"][0]["default"] is True


def test_wsl_not_installed_is_reported_not_fabricated(monkeypatch):
    def wsl_runner(argv, timeout):
        if "--status" in argv:
            return result(
                argv,
                returncode=50,
                stderr="Windows Subsystem for Linux is not installed.",
            )
        return result(argv, returncode=1, stderr="Windows Subsystem for Linux is not installed.")

    document = probe.collect_environment(
        command_runner=ScriptedRunner({"wsl.exe": wsl_runner})
    )
    wsl = document["wsl"]
    assert wsl["status"] == "ok"
    assert wsl["installed"] is False
    assert wsl["status_exit_code"] == 50
    assert wsl["distributions"] == []


def test_gpu_compute_capability_falls_back_to_not_reported(monkeypatch):
    reduced = "index,name,driver_version,memory.total,memory.used,memory.free"

    def smi(argv, timeout):
        if "--query-gpu=" in " ".join(argv):
            joined = " ".join(argv)
            if "compute_cap" in joined:
                return result(argv, returncode=1, stderr="Field compute_cap not supported")
            return result(
                argv,
                returncode=0,
                stdout="0, NVIDIA GeForce RTX 5080 Laptop GPU, 581.42, 16303, 4000, 12000",
            )
        return result(
            argv,
            returncode=0,
            stdout="| NVIDIA-SMI 581.42   Driver Version: 581.42   CUDA Version: 13.0 |",
        )

    document = probe.collect_environment(
        command_runner=ScriptedRunner({"nvidia-smi": smi})
    )
    gpu = document["gpu"]
    assert gpu["status"] == "ok"
    assert gpu["source"] == "nvidia-smi"
    assert gpu["device_count"] == 1
    device = gpu["devices"][0]
    assert device["memory_total_mib"] == 16303
    assert device["compute_capability"]["reported"] == "not reported"
    assert gpu["cuda_runtime_version"]["reported"] == "13.0"


def test_command_runner_receives_argv_and_timeout(monkeypatch):
    runner = ScriptedRunner()
    collecting(monkeypatch, runner)
    assert runner.calls
    for call in runner.calls:
        assert isinstance(call["argv"], tuple)
        assert call["timeout"] == probe.DEFAULT_TIMEOUT_S
    flat = [" ".join(call["argv"]) for call in runner.calls]
    assert any("nvidia-smi" in line for line in flat)
    assert any("wsl.exe" in line for line in flat)


def test_skip_slow_marks_cim_enrichment_skipped(monkeypatch):
    for name in GATE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    document = probe.collect_environment(
        command_runner=failing_runner(), skip_slow=True
    )
    assert document["cpu"]["cim"]["status"] == "skipped"
    assert document["gpu"]["cim_inventory"]["status"] == "skipped"
    skipped = {item["probe"] for item in document["limitations"]}
    assert {"cpu.cim", "gpu.cim_inventory"} <= skipped


# --------------------------------------------------------------- safety gates
def test_four_safety_gates_are_reported_closed_by_default(monkeypatch):
    document = collecting(monkeypatch, failing_runner())
    gates = document["safety_gates"]
    assert gates["status"] == "ok"
    assert set(gates["gates"]) == GATE_NAMES
    assert gates["gate_count"] == 4
    assert gates["all_closed"] is True
    for name, entry in gates["gates"].items():
        assert entry["open"] is False, name
        assert entry["env_var"].startswith("MEDRADAR_LOCAL_LLM_ALLOW_")
    assert {entry["env_var"] for entry in gates["gates"].values()} == GATE_ENV_VARS


def test_gate_report_reflects_an_explicitly_opened_gate(monkeypatch):
    monkeypatch.setenv("MEDRADAR_LOCAL_LLM_ALLOW_NETWORK", "1")
    for name in GATE_ENV_VARS - {"MEDRADAR_LOCAL_LLM_ALLOW_NETWORK"}:
        monkeypatch.delenv(name, raising=False)
    document = probe.collect_environment(command_runner=failing_runner())
    gates = document["safety_gates"]
    assert gates["gates"]["network"]["open"] is True
    assert gates["gates"]["network"]["raw_value"] == "1"
    assert gates["all_closed"] is False


# -------------------------------------------------------------------- packages
def test_package_detection_uses_find_spec_without_importing(monkeypatch):
    seen = []

    def fake_find_spec(name, *args, **kwargs):
        seen.append(name)
        return None

    def fake_version(distribution):
        raise probe.importlib_metadata.PackageNotFoundError(distribution)

    monkeypatch.setattr(
        probe, "PACKAGE_MODULES", (("totally_fake_module_xyz", "totally-fake-dist-xyz"),)
    )
    monkeypatch.setattr(probe.importlib_util, "find_spec", fake_find_spec)
    monkeypatch.setattr(probe.importlib_metadata, "version", fake_version)
    sys.modules.pop("totally_fake_module_xyz", None)

    payload = probe.probe_packages()
    assert seen == ["totally_fake_module_xyz"]
    assert payload["packages"]["totally_fake_module_xyz"]["present"] is False
    assert "find_spec" in payload["method"]
    assert "totally_fake_module_xyz" not in sys.modules

    # A module that the finder can see must be reported present, still without
    # any import happening.
    monkeypatch.setattr(
        probe.importlib_util, "find_spec", lambda name, *a, **k: object()
    )
    payload = probe.probe_packages()
    assert payload["packages"]["totally_fake_module_xyz"]["present"] is True


def test_package_registry_covers_the_research_stack():
    names = {module for module, _distribution in probe.PACKAGE_MODULES}
    assert {"torch", "transformers", "peft", "trl", "accelerate", "bitsandbytes"} <= names
    payload = probe.probe_packages()
    for name, entry in payload["packages"].items():
        assert "present" in entry and "version" in entry, name
        assert entry["present"] in (True, False)


# ------------------------------------------------------------------ static scan
def test_probe_source_never_installs_or_imports_torch():
    source = PROBE_PATH.read_text(encoding="utf-8")
    assert "--install" not in source
    assert "import torch" not in source
    assert "pip install" not in source.lower()
    assert ".write_text(" in source  # only --out may write
    assert source.count(".write_text(") == 1
    assert "find_spec(" in source


# ------------------------------------------------------------------- CLI / files
def test_main_json_mode_writes_no_files(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    for name in GATE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    code = probe.main(["--json"], command_runner=failing_runner())
    assert code == 0
    assert list(tmp_path.iterdir()) == []
    document = json.loads(capsys.readouterr().out)
    assert document["schema_version"] == probe.SCHEMA_VERSION


def test_main_out_writes_only_the_requested_json(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    out_path = tmp_path / "probe.json"
    code = probe.main(
        ["--json", "--out", str(out_path)], command_runner=failing_runner()
    )
    assert code == 0
    assert out_path.exists()
    document = json.loads(out_path.read_text(encoding="utf-8"))
    assert document["probe_version"] == probe.PROBE_VERSION
    captured = capsys.readouterr()
    assert "wrote" in captured.err
    assert json.loads(captured.out) == document
    assert [path.name for path in tmp_path.iterdir()] == ["probe.json"]


def test_human_report_contains_the_main_sections(monkeypatch):
    document = collecting(monkeypatch, failing_runner())
    text = probe.render_text(document)
    assert probe.PROBE_VERSION in text
    for marker in ("[os]", "[cpu]", "[memory]", "[disks]", "[gpu]", "[wsl]",
                   "[python]", "[packages]", "[safety gates]", "[limitations]"):
        assert marker in text, marker
    assert text.isascii()


def test_python_probe_measures_a_path_interpreter_version(monkeypatch):
    def runner(argv, timeout):
        if str(argv[0]).lower().endswith(("python", "python3")) and "--version" in argv:
            return result(argv, returncode=0, stdout="Python 3.13.2\n")
        return result(argv, returncode=1, stderr="scripted")

    monkeypatch.setattr(
        probe.shutil, "which", lambda name: "/usr/bin/python3" if name == "python3" else None
    )
    payload = probe.probe_python(command_runner=runner)
    assert payload["status"] == "ok"
    measured = [entry for entry in payload["path_interpreters"] if entry["status"] == "ok"]
    assert measured and measured[0]["version"] == "3.13.2"


# -------------------------------------------------------------- encoding/runner
def test_decode_output_handles_utf16_and_garbage():
    assert probe.decode_output("未安装".encode("utf-16")) == "未安装"
    assert probe.decode_output("未安装".encode("utf-16-le")) == "未安装"
    assert probe.decode_output(b"plain ascii") == "plain ascii"
    assert probe.decode_output(b"\xff\xfe\x00") is not None  # never raises
    assert probe.decode_output(b"") == ""


def test_run_command_converts_runner_failures():
    def boom(argv, timeout):
        raise subprocess.TimeoutExpired(list(argv), timeout)

    timed = probe.run_command(["nvidia-smi"], command_runner=boom)
    assert timed.timed_out is True
    assert "timed out" in timed.error
    assert timed.succeeded is False

    missing = probe.run_command(["nope"], command_runner=lambda a, t: (_ for _ in ()).throw(
        FileNotFoundError("nope")
    ))
    assert "not found" in missing.error

    wrong = probe.run_command(["x"], command_runner=lambda a, t: "not a result")
    assert "expected CommandResult" in wrong.error


def test_probe_cli_help_and_unknown_flag():
    with pytest.raises(SystemExit):
        probe.main(["--definitely-not-a-flag"])


def test_probe_source_is_a_script_entry_point():
    assert PROBE_PATH.name == "env_probe.py"
    assert PROBE_PATH.exists()
    assert PROBE_PATH.parent.name == "scripts"
