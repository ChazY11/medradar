"""Read-only environment probe for the local small-LM research foundation.

What this script is
-------------------
A single stdlib-only entry point that answers one question *without changing
anything*: **what is this machine, and what can it run today?**

It is deliberately the opposite of an installer.  It performs no writes unless
``--out`` is passed, makes no network calls, requests no elevation, installs
nothing, loads no model and never initialises a CUDA context.  Every external
fact comes from a read-only OS command (``subprocess``), a read-only registry
key (``winreg``), a read-only ctypes call, or a package *metadata* lookup that
does not import the package.

Why the JSON has a status on every probe
----------------------------------------
This machine is a normal Windows 11 laptop, not a CI image: a command may be
missing, may not exist on this OS, may hang, or may print UTF-16 garbage.  A
probe that raises would make the whole document useless, and a probe that
silently reports ``0`` or ``null`` as if it had measured something is worse.  So
every section is individually guarded and always carries one of::

    "status": "ok"            measured, fields are trustworthy
    "status": "unavailable"   not measured; "reason" says exactly why
    "status": "skipped"       deliberately not run (``--skip-slow``)

``null`` therefore means "not measured", never "zero".

Document schema (stable, ``schema_version = "env_probe.v1"``)
-------------------------------------------------------------
Top-level keys, all present on every run::

    probe_version      str      probe implementation version
    schema_version     str      document schema identifier
    generated_at       str      ISO-8601 local timestamp with UTC offset
    generated_at_utc   str      ISO-8601 UTC timestamp ("Z" suffix)
    probe_duration_s   float    wall time spent probing
    read_only          bool     always true; the script asserts its own posture
    command_policy     dict     timeout / installs / writes / network / elevation
    host               dict     hostname, platform string, interpreter path
    os                 dict     OS identity and Windows build/edition
    cpu                dict     model, physical/logical cores, clock
    memory             dict     total / available / used RAM in bytes and GiB
    disks              dict     per-volume total/free/used
    gpu                dict     nvidia-smi devices + CIM inventory
    wsl                dict     presence / version / installed distributions
    python             dict     current interpreter + the `python`/`python3` on
                               PATH (versions from a read-only `--version` call)
    packages           dict     presence + version without importing anything
    safety_gates       dict     the four default-closed gates from safety.py
    limitations        list     one entry per probe that was not fully measured

Section keys are additive within a schema version; unknown keys must be ignored
by readers.  ``status`` values are ``ok``, ``unavailable`` and ``skipped``.

Usage
-----
::

    python experiments/local_llm_event_extraction/scripts/env_probe.py
    python experiments/local_llm_event_extraction/scripts/env_probe.py --json
    python experiments/local_llm_event_extraction/scripts/env_probe.py --out probe.json
    python experiments/local_llm_event_extraction/scripts/env_probe.py --skip-slow --json

Exit code is 0 when a document was produced (even if some probes were
unavailable); non-zero only for a CLI usage error or an unwritable ``--out``.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as _dt
import importlib.metadata as importlib_metadata
import importlib.util as importlib_util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

PROBE_VERSION = "1.0.0"
SCHEMA_VERSION = "env_probe.v1"

DEFAULT_TIMEOUT_S = 10.0
_MAX_TEXT_CHARS = 4000

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_SKIPPED = "skipped"

STATUSES = (STATUS_OK, STATUS_UNAVAILABLE, STATUS_SKIPPED)

_REPO_ROOT = Path(__file__).resolve().parents[3]

#: (import name, distribution name) pairs.  Presence is checked with
#: ``importlib.util.find_spec`` and the version with ``importlib.metadata``;
#: neither imports the package, so no CUDA context is created by this probe.
PACKAGE_MODULES: tuple[tuple[str, str], ...] = (
    ("torch", "torch"),
    ("transformers", "transformers"),
    ("peft", "peft"),
    ("trl", "trl"),
    ("accelerate", "accelerate"),
    ("bitsandbytes", "bitsandbytes"),
    ("datasets", "datasets"),
    ("safetensors", "safetensors"),
    ("tokenizers", "tokenizers"),
    ("huggingface_hub", "huggingface-hub"),
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("pytest", "pytest"),
    ("psutil", "psutil"),
)

#: NVIDIA query fields in the order they are printed by nvidia-smi.
_NVIDIA_FIELDS: tuple[str, ...] = (
    "index",
    "name",
    "driver_version",
    "memory.total",
    "memory.used",
    "memory.free",
    "compute_cap",
)

_PS_VIDEO = (
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
    "Get-CimInstance Win32_VideoController | "
    "Select-Object Name,DriverVersion,AdapterRAM,VideoProcessor,Status | "
    "ConvertTo-Json -Compress"
)

_PS_CPU = (
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
    "Get-CimInstance Win32_Processor | "
    "Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed | "
    "ConvertTo-Json -Compress"
)

#: The probe is not allowed to install anything and is not allowed to import a
#: model framework at any point; the unit test asserts both absences against the
#: source text itself, so those spellings are kept out of this file entirely.

_CREATE_NO_WINDOW = 0x08000000


# --------------------------------------------------------------------------- types
@dataclass(frozen=True)
class CommandResult:
    """Outcome of one read-only command.  Never contains a fabricated value."""

    argv: tuple[str, ...]
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    error: str | None = None
    duration_s: float | None = None

    @property
    def succeeded(self) -> bool:
        return (
            self.error is None
            and not self.timed_out
            and self.returncode == 0
        )

    def describe_failure(self) -> str:
        parts: list[str] = []
        if self.timed_out:
            parts.append("timed out")
        if self.error:
            parts.append(str(self.error))
        if self.returncode is not None:
            parts.append(f"exit={self.returncode}")
        stderr = _first_line(self.stderr)
        if stderr:
            parts.append(f"stderr={stderr!r}")
        return "; ".join(parts) or "failed for an unknown reason"


#: A runner takes the argv to execute and a timeout, and returns a
#: :class:`CommandResult`.  Tests inject a deterministic fake here.
CommandRunner = Callable[[Sequence[str], float], CommandResult]


class ProbeUnavailable(RuntimeError):
    """Raised inside a probe when a fact could not be measured; carries why."""


# ----------------------------------------------------------------------- plumbing
def _first_line(text: str, limit: int = 240) -> str:
    for line in (text or "").replace("\r", "\n").split("\n"):
        stripped = line.strip().replace("\x00", "")
        if stripped:
            return stripped[:limit]
    return ""


def decode_output(data: bytes) -> str:
    """Decode a command's bytes without ever raising.

    Windows System32 tools that use the UTF-16 console API (``wsl.exe`` is the
    one that matters here) emit UTF-16LE even when redirected.  Guessing UTF-8
    turns that into mojibake, so detect the BOM or a NUL-heavy stream first and
    fall back to UTF-8 with ``errors="replace"``.
    """
    if not data:
        return ""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8", errors="replace")
    if data.count(0) > max(1, len(data) // 4):
        return data.decode("utf-16-le", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        # Not valid UTF-8.  A CJK-only UTF-16LE stream contains no NUL bytes, so
        # the NUL heuristic cannot see it; strict UTF-16LE is the next best
        # hypothesis and is accepted only if it decodes cleanly.
        if len(data) % 2 == 0:
            try:
                return data.decode("utf-16-le")
            except UnicodeDecodeError:
                pass
        return data.decode("utf-8", errors="replace")


def default_command_runner(argv: Sequence[str], timeout: float = DEFAULT_TIMEOUT_S) -> CommandResult:
    """Run one read-only command, capturing bytes and decoding leniently."""
    argv = tuple(str(part) for part in argv)
    started = time.monotonic()
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "timeout": timeout,
        "check": False,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = _CREATE_NO_WINDOW
    try:
        completed = subprocess.run(list(argv), **kwargs)
    except FileNotFoundError as exc:
        return CommandResult(argv=argv, error=f"command not found: {exc}")
    except subprocess.TimeoutExpired:
        return CommandResult(
            argv=argv,
            timed_out=True,
            error=f"timed out after {timeout:.1f}s",
            duration_s=time.monotonic() - started,
        )
    except OSError as exc:
        return CommandResult(argv=argv, error=f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # pragma: no cover - defensive, e.g. permission errors
        return CommandResult(argv=argv, error=f"unexpected {type(exc).__name__}: {exc}")
    return CommandResult(
        argv=argv,
        returncode=completed.returncode,
        stdout=decode_output(completed.stdout),
        stderr=decode_output(completed.stderr),
        duration_s=time.monotonic() - started,
    )


def run_command(
    argv: Sequence[str],
    *,
    command_runner: CommandRunner | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> CommandResult:
    """Call the configured runner and normalise *any* failure into a result.

    A runner that raises ``FileNotFoundError``, ``TimeoutExpired``, or anything
    else must not abort the probe document; it becomes an unavailable result.
    """
    argv = tuple(str(part) for part in argv)
    runner = command_runner or default_command_runner
    try:
        result = runner(argv, timeout)
    except subprocess.TimeoutExpired:
        return CommandResult(
            argv=argv, timed_out=True, error=f"timed out after {timeout:.1f}s"
        )
    except FileNotFoundError as exc:
        return CommandResult(argv=argv, error=f"command not found: {exc}")
    except Exception as exc:
        return CommandResult(argv=argv, error=f"{type(exc).__name__}: {exc}")
    if not isinstance(result, CommandResult):
        return CommandResult(
            argv=argv,
            error=f"runner returned {type(result).__name__}, expected CommandResult",
        )
    if result.argv != argv:
        # Do not trust a mismatched result; report the mismatch rather than a
        # wrong measurement.
        return CommandResult(
            argv=argv,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
            error=result.error
            or f"runner returned a result for {result.argv!r}, not {argv!r}",
        )
    return result


def _require_success(result: CommandResult) -> CommandResult:
    if result.succeeded:
        return result
    raise ProbeUnavailable(
        f"{' '.join(result.argv[:2])} unavailable: {result.describe_failure()}"
    )


def _guarded(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Run one probe, converting every failure into an unavailable marker."""
    try:
        payload = fn()
    except ProbeUnavailable as exc:
        return {"status": STATUS_UNAVAILABLE, "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001 - the document must survive anything
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": f"unexpected {type(exc).__name__}: {exc}",
        }
    if not isinstance(payload, dict):
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": f"probe returned {type(payload).__name__}, expected dict",
        }
    payload.setdefault("status", STATUS_OK)
    return payload


def _skipped(reason: str) -> dict[str, Any]:
    return {"status": STATUS_SKIPPED, "reason": reason}


def _bytes_to_gib(value: int | None) -> float | None:
    return None if value is None else round(value / (1024**3), 2)


def _bytes_to_gb(value: int | None) -> float | None:
    return None if value is None else round(value / (10**9), 2)


def _mib_to_gib(value: float | None) -> float | None:
    return None if value is None else round(value / 1024.0, 2)


def _to_int(text: str | None) -> int | None:
    if text is None:
        return None
    text = str(text).strip().replace("\x00", "")
    if not text or not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------- OS probes
def probe_os() -> dict[str, Any]:
    info: dict[str, Any] = {
        "status": STATUS_OK,
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "architecture": platform.architecture()[0],
        "platform": platform.platform(),
        "windows_build": None,
        "windows_ubr": None,
        "windows_display_version": None,
        "windows_edition_id": None,
        "windows_product_name": None,
        "source": "platform + sys.getwindowsversion + winreg (read-only key reads)",
        "notes": [],
    }
    if sys.platform != "win32":
        info["notes"].append("not Windows: registry details not applicable")
        return info

    version = sys.getwindowsversion()
    info["windows_build"] = int(getattr(version, "build", 0)) or None
    info["windows_release"] = f"{getattr(version, 'major', '?')}.{getattr(version, 'minor', '?')}"

    try:
        import winreg  # stdlib; read-only key reads only
    except ImportError as exc:  # pragma: no cover - Windows always has winreg
        info["notes"].append(f"winreg unavailable: {exc}")
        return info

    key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            def query(name: str) -> Any:
                try:
                    return winreg.QueryValueEx(key, name)[0]
                except OSError:
                    return None

            info["windows_display_version"] = query("DisplayVersion")
            info["windows_edition_id"] = query("EditionID")
            info["windows_product_name"] = query("ProductName")
            info["windows_ubr"] = query("UBR")
            registry_build = query("CurrentBuildNumber")
    except OSError as exc:
        info["notes"].append(f"registry read failed: {exc!r}")
        return info

    if registry_build is not None and info["windows_build"] is None:
        info["windows_build"] = _to_int(str(registry_build))
    if info["windows_ubr"] is not None:
        info["windows_build_full"] = f"{info['windows_build']}.{info['windows_ubr']}"
    # Windows 11 keeps reporting "Windows 10" in ProductName for compatibility.
    # The build number is the authoritative field; surface the discrepancy
    # instead of "fixing" it.
    if (
        info["windows_product_name"]
        and "Windows 10" in str(info["windows_product_name"])
        and (info["windows_build"] or 0) >= 22000
    ):
        info["notes"].append(
            "registry ProductName says 'Windows 10' but the build number is a "
            "Windows 11 build; ProductName is not updated by Windows"
        )
    return info


def _ps_json(
    script: str,
    *,
    command_runner: CommandRunner | None,
) -> Any:
    result = _require_success(
        run_command(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            command_runner=command_runner,
        )
    )
    text = (result.stdout or "").strip()
    if not text:
        raise ProbeUnavailable("PowerShell returned no output")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProbeUnavailable(f"PowerShell output was not JSON: {exc}") from exc


def probe_cpu(
    *,
    command_runner: CommandRunner | None = None,
    skip_slow: bool = False,
) -> dict[str, Any]:
    info: dict[str, Any] = {
        "status": STATUS_OK,
        "model": None,
        "model_source": None,
        "physical_cores": None,
        "logical_cores": os.cpu_count(),
        "max_clock_mhz": None,
        "processor_identifier": os.environ.get("PROCESSOR_IDENTIFIER"),
        "cim": _skipped("--skip-slow") if skip_slow else None,
        "notes": [],
    }

    if sys.platform == "win32":
        try:
            import winreg

            key_path = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                name = winreg.QueryValueEx(key, "ProcessorNameString")[0]
            if name:
                info["model"] = str(name).strip()
                info["model_source"] = "winreg ProcessorNameString"
        except (ImportError, OSError) as exc:
            info["notes"].append(f"registry CPU name unavailable: {exc!r}")

    if not skip_slow:
        try:
            payload = _ps_json(_PS_CPU, command_runner=command_runner)
            if isinstance(payload, list):
                payload = payload[0] if payload else {}
            if isinstance(payload, dict):
                info["physical_cores"] = _to_int(payload.get("NumberOfCores"))
                info["logical_cores"] = _to_int(payload.get("NumberOfLogicalProcessors")) or info["logical_cores"]
                info["max_clock_mhz"] = _to_int(payload.get("MaxClockSpeed"))
                if not info["model"] and payload.get("Name"):
                    info["model"] = str(payload["Name"]).strip()
                    info["model_source"] = "PowerShell Win32_Processor"
                info["cim"] = {"status": STATUS_OK, "source": "Win32_Processor"}
            else:
                info["cim"] = {
                    "status": STATUS_UNAVAILABLE,
                    "reason": "Win32_Processor returned an unexpected JSON shape",
                }
        except ProbeUnavailable as exc:
            info["cim"] = {"status": STATUS_UNAVAILABLE, "reason": str(exc)}

    if info["model"] is None:
        info["notes"].append("CPU marketing name not measured")
    if info["physical_cores"] is None:
        info["notes"].append("physical core count not measured (CIM unavailable)")
    return info


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _windows_memory() -> tuple[int, int, int]:
    status = _MemoryStatusEx()
    status.dwLength = ctypes.sizeof(_MemoryStatusEx)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ProbeUnavailable("GlobalMemoryStatusEx returned 0 (call failed)")
    return int(status.ullTotalPhys), int(status.ullAvailPhys), int(status.dwMemoryLoad)


def probe_memory() -> dict[str, Any]:
    if sys.platform == "win32":
        total, available, load_percent = _windows_memory()
        source = "ctypes kernel32.GlobalMemoryStatusEx"
    else:  # pragma: no cover - exercised only off Windows
        page = os.sysconf("SC_PAGE_SIZE")
        total = int(page * os.sysconf("SC_PHYS_PAGES"))
        available = int(page * os.sysconf("SC_AVPHYS_PAGES"))
        load_percent = int(round(100 * (total - available) / total)) if total else None
        source = "os.sysconf"
    used = max(0, total - available)
    return {
        "status": STATUS_OK,
        "source": source,
        "total_bytes": total,
        "available_bytes": available,
        "used_bytes": used,
        "percent_used": int(round(100 * used / total)) if total else load_percent,
        "total_gib": _bytes_to_gib(total),
        "available_gib": _bytes_to_gib(available),
        "used_gib": _bytes_to_gib(used),
        "total_gb": _bytes_to_gb(total),
    }


def probe_disks() -> dict[str, Any]:
    drives: list[dict[str, Any]] = []
    if sys.platform == "win32":
        candidates = [f"{letter}:\\" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
    else:  # pragma: no cover - exercised only off Windows
        candidates = ["/"]
    for root in candidates:
        if not os.path.exists(root):
            continue
        entry: dict[str, Any] = {"mount": root}
        try:
            usage = shutil.disk_usage(root)
        except OSError as exc:
            entry["status"] = STATUS_UNAVAILABLE
            entry["reason"] = f"{type(exc).__name__}: {exc}"
            drives.append(entry)
            continue
        entry.update(
            {
                "status": STATUS_OK,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "total_gb": _bytes_to_gb(usage.total),
                "free_gb": _bytes_to_gb(usage.free),
                "total_gib": _bytes_to_gib(usage.total),
                "free_gib": _bytes_to_gib(usage.free),
                "percent_used": int(round(100 * usage.used / usage.total)) if usage.total else None,
            }
        )
        drives.append(entry)
    measured = [drive for drive in drives if drive.get("status") == STATUS_OK]
    payload: dict[str, Any] = {
        "status": STATUS_OK if measured else STATUS_UNAVAILABLE,
        "source": "shutil.disk_usage",
        "drives": drives,
    }
    if not measured:
        payload["reason"] = "no mounted volume could be measured"
    return payload


# --------------------------------------------------------------------- GPU probe
def _parse_nvidia_csv(stdout: str, fields: Sequence[str]) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for raw_line in stdout.replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != len(fields):
            raise ProbeUnavailable(
                f"nvidia-smi row had {len(parts)} columns, expected {len(fields)}: {line!r}"
            )
        row = dict(zip(fields, parts))
        device: dict[str, Any] = {
            "index": _to_int(row.get("index")),
            "name": row.get("name") or None,
            "driver_version": row.get("driver_version") or None,
            "memory_total_mib": _to_int(row.get("memory.total")),
            "memory_used_mib": _to_int(row.get("memory.used")),
            "memory_free_mib": _to_int(row.get("memory.free")),
            "compute_capability": _parse_compute_capability(row.get("compute_cap")),
            "source": "nvidia-smi --query-gpu",
        }
        device["memory_total_gib"] = _mib_to_gib(device["memory_total_mib"])
        devices.append(device)
    if not devices:
        raise ProbeUnavailable("nvidia-smi printed no GPU rows")
    return devices


def _parse_compute_capability(raw: str | None) -> dict[str, Any]:
    text = (raw or "").strip().replace("\x00", "")
    if not text or text.upper() in {"N/A", "[NOT SUPPORTED]", "NOT SUPPORTED", "[N/A]"}:
        return {
            "reported": "not reported",
            "major": None,
            "minor": None,
            "targeted_sm": None,
            "source": "nvidia-smi compute_cap (field missing or unsupported)",
        }
    match = re.fullmatch(r"(\d+)(?:\.(\d+))?", text)
    if not match:
        return {
            "reported": "not reported",
            "major": None,
            "minor": None,
            "targeted_sm": None,
            "source": f"nvidia-smi compute_cap unparseable ({text!r})",
        }
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    return {
        "reported": f"{major}.{minor}",
        "major": major,
        "minor": minor,
        "targeted_sm": f"sm_{major}{minor}",
        "source": "nvidia-smi compute_cap",
    }


def _cim_video_inventory(
    *, command_runner: CommandRunner | None, skip_slow: bool
) -> dict[str, Any]:
    if skip_slow:
        return _skipped("--skip-slow")
    try:
        payload = _ps_json(_PS_VIDEO, command_runner=command_runner)
    except ProbeUnavailable as exc:
        return {"status": STATUS_UNAVAILABLE, "reason": str(exc)}
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": "Win32_VideoController returned an unexpected JSON shape",
        }
    controllers = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        controllers.append(
            {
                "index": index,
                "name": item.get("Name"),
                "driver_version_raw": item.get("DriverVersion"),
                "adapter_ram_bytes": _to_int(item.get("AdapterRAM")),
                "status_field": item.get("Status"),
            }
        )
    return {
        "status": STATUS_OK,
        "source": "PowerShell Get-CimInstance Win32_VideoController",
        "controllers": controllers,
    }


def probe_gpu(
    *,
    command_runner: CommandRunner | None = None,
    skip_slow: bool = False,
) -> dict[str, Any]:
    cim = _cim_video_inventory(command_runner=command_runner, skip_slow=skip_slow)
    payload: dict[str, Any] = {
        "status": STATUS_OK,
        "source": "nvidia-smi",
        "devices": [],
        "device_count": 0,
        "cuda_runtime_version": None,
        "cim_inventory": cim,
        "notes": [],
    }

    nvidia_error: str | None = None
    try:
        query = ",".join(_NVIDIA_FIELDS)
        result = run_command(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            command_runner=command_runner,
        )
        fields: Sequence[str] = _NVIDIA_FIELDS
        if not result.succeeded:
            # compute_cap is not available on every driver; retry without it and
            # report the capability as "not reported" rather than failing the GPU
            # section for a cosmetic field.
            fallback_fields = _NVIDIA_FIELDS[:-1]
            fallback = run_command(
                [
                    "nvidia-smi",
                    f"--query-gpu={','.join(fallback_fields)}",
                    "--format=csv,noheader,nounits",
                ],
                command_runner=command_runner,
            )
            if not fallback.succeeded:
                raise ProbeUnavailable(
                    "nvidia-smi unavailable: " + result.describe_failure()
                )
            result, fields = fallback, fallback_fields
        payload["devices"] = _parse_nvidia_csv(result.stdout, fields)
        if "compute_cap" not in fields:
            for device in payload["devices"]:
                device["compute_capability"] = _parse_compute_capability(None)
    except ProbeUnavailable as exc:
        nvidia_error = str(exc)
        payload["notes"].append(nvidia_error)

    if payload["devices"]:
        payload["device_count"] = len(payload["devices"])
        driver_versions = {
            device["driver_version"]
            for device in payload["devices"]
            if device.get("driver_version")
        }
        payload["driver_version"] = (
            sorted(driver_versions)[0] if len(driver_versions) == 1 else sorted(driver_versions)
        )
        payload["memory_total_mib"] = sum(
            device.get("memory_total_mib") or 0 for device in payload["devices"]
        ) or None
        payload["memory_used_mib"] = sum(
            device.get("memory_used_mib") or 0 for device in payload["devices"]
        ) or None
        payload["memory_free_mib"] = sum(
            device.get("memory_free_mib") or 0 for device in payload["devices"]
        ) or None

        banner = run_command(["nvidia-smi"], command_runner=command_runner)
        if banner.succeeded:
            match = re.search(r"CUDA Version:\s*([0-9]+\.[0-9]+)", banner.stdout)
            if match:
                payload["cuda_runtime_version"] = {
                    "reported": match.group(1),
                    "source": "nvidia-smi banner 'CUDA Version' (runtime the driver reports, not an installed toolkit)",
                }
            else:
                payload["cuda_runtime_version"] = {
                    "reported": "not reported",
                    "source": "nvidia-smi banner (pattern not found)",
                }
        else:
            payload["cuda_runtime_version"] = {
                "reported": "not reported",
                "source": f"nvidia-smi banner unavailable ({banner.describe_failure()})",
            }
        return payload

    # nvidia-smi failed: fall back to the Windows device-manager inventory.
    controllers = cim.get("controllers") if cim.get("status") == STATUS_OK else None
    if controllers:
        payload["status"] = STATUS_OK
        payload["source"] = "powershell_cim_fallback"
        payload["devices"] = [
            {
                "index": controller.get("index"),
                "name": controller.get("name"),
                "driver_version": controller.get("driver_version_raw"),
                "memory_total_mib": None,
                "memory_used_mib": None,
                "memory_free_mib": None,
                "memory_total_gib": None,
                "compute_capability": _parse_compute_capability(None),
                "source": "Win32_VideoController (no VRAM or compute capability reported by CIM)",
            }
            for controller in controllers
        ]
        payload["device_count"] = len(payload["devices"])
        payload["notes"].append(
            "nvidia-smi unavailable; device list came from CIM and carries no "
            "VRAM, driver-branch or compute-capability measurement"
        )
        return payload

    payload["status"] = STATUS_UNAVAILABLE
    payload["source"] = None
    payload["reason"] = (
        f"nvidia-smi: {nvidia_error or 'unavailable'}; "
        f"CIM inventory: {cim.get('reason', cim.get('status'))}"
    )
    return payload


# --------------------------------------------------------------------- WSL probe
_WSL_STATUS_COMMANDS: tuple[tuple[str, Sequence[str]], ...] = (
    ("status", ("wsl.exe", "--status")),
    ("list", ("wsl.exe", "-l", "-v")),
    ("version", ("wsl.exe", "--version")),
)


def _wsl_text(result: CommandResult) -> str:
    text = "\n".join(part for part in (result.stdout, result.stderr) if part)
    return text.replace("\x00", "").strip()


def _parse_distributions(text: str) -> list[dict[str, Any]]:
    """Parse ``wsl -l -v`` output tolerant of NULs, CRs and a UTF-16 decode."""
    lines = [
        line.replace("\x00", "").strip()
        for line in text.replace("\r", "\n").split("\n")
    ]
    distributions: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if not line:
            continue
        is_default = line.startswith("*")
        body = line.lstrip("*").strip()
        parts = body.split()
        if not parts:
            continue
        if index == 0 and parts[0].upper() in {"NAME", "名称"}:
            continue
        if parts[0].upper() in {"NAME"}:
            continue
        distributions.append(
            {
                "name": parts[0],
                "state": parts[1] if len(parts) > 1 else None,
                "version": parts[2] if len(parts) > 2 else None,
                "default": is_default,
            }
        )
    return distributions


def probe_wsl(*, command_runner: CommandRunner | None = None) -> dict[str, Any]:
    """Inspect WSL without ever enabling or installing it.

    The section is ``ok`` when the question "is WSL usable here?" was answered,
    including the answer "no": ``wsl.exe --status`` exiting non-zero is a
    legitimate measurement of "not installed", not a probe failure, and the exit
    codes are preserved in the document.  The section is ``unavailable`` only
    when ``wsl.exe`` itself cannot be executed.
    """
    payload: dict[str, Any] = {
        "status": STATUS_OK,
        "executable": "wsl.exe",
        "executable_present": True,
        "installed": None,
        "status_exit_code": None,
        "detail": None,
        "wsl_version": None,
        "kernel_version": None,
        "default_version": None,
        "distributions": [],
        "source": "wsl.exe status/list/version queries only (read-only inspection)",
        "notes": [],
    }

    results: dict[str, CommandResult] = {}
    for key, argv in _WSL_STATUS_COMMANDS:
        results[key] = run_command(argv, command_runner=command_runner)

    first_error = results["status"].error or results["list"].error
    if first_error and "not found" in str(first_error).lower():
        raise ProbeUnavailable(f"wsl.exe not found on PATH: {first_error}")

    status = results["status"]
    payload["status_exit_code"] = status.returncode
    detail = _wsl_text(status) or _wsl_text(results["list"])
    payload["detail"] = detail[-_MAX_TEXT_CHARS:] or None

    list_result = results["list"]
    if list_result.succeeded:
        distributions = _parse_distributions(_wsl_text(list_result))
        payload["distributions"] = distributions
        payload["installed"] = True
        if not distributions:
            payload["notes"].append(
                "WSL is installed but reports no registered distributions"
            )
    elif status.succeeded:
        payload["installed"] = True
        payload["notes"].append(
            f"wsl -l -v failed ({list_result.describe_failure()}) but --status succeeded"
        )
    else:
        payload["installed"] = False
        payload["notes"].append(
            "wsl.exe is present but WSL reports it is not installed "
            f"(exit codes: status={status.returncode}, list={list_result.returncode}); "
            "this probe does not and cannot install it"
        )

    version = results["version"]
    if version.succeeded:
        text = _wsl_text(version)
        wsl_version = re.search(r"WSL\s+version:\s*([0-9][0-9.]*)", text, re.IGNORECASE)
        kernel = re.search(r"Kernel\s+version:\s*([0-9][0-9.\-a-zA-Z_]*)", text)
        default_version = re.search(r"Default\s+Version:\s*(\d+)", text, re.IGNORECASE)
        payload["wsl_version"] = wsl_version.group(1) if wsl_version else None
        payload["kernel_version"] = kernel.group(1) if kernel else None
        payload["default_version"] = (
            int(default_version.group(1)) if default_version else None
        )
        if wsl_version is None and kernel is None:
            payload["notes"].append("wsl --version succeeded but the output pattern was not recognised")
    else:
        payload["notes"].append(
            f"wsl --version unavailable ({version.describe_failure()})"
        )

    # WSL 2 is the only version with GPU support; state what was measured and
    # leave the conclusion to the reader.
    if payload["installed"] and payload["default_version"] is None:
        payload["notes"].append("default WSL version not measured")
    return payload


# ------------------------------------------------------------------ Python probe
def _interpreter_version(
    executable: str, *, command_runner: CommandRunner | None
) -> dict[str, Any]:
    """Ask one interpreter for its version with a read-only ``--version`` call."""
    result = run_command([executable, "--version"], command_runner=command_runner)
    if not result.succeeded:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": result.describe_failure(),
            "executable": executable,
        }
    text = "\n".join(part for part in (result.stdout, result.stderr) if part)
    match = re.search(r"Python\s+([0-9]+\.[0-9]+\.[0-9]+[^\s]*)", text)
    if not match:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": f"unrecognised --version output: {_first_line(text)!r}",
            "executable": executable,
        }
    return {
        "status": STATUS_OK,
        "version": match.group(1),
        "executable": executable,
        "source": "`--version` (read-only process launch)",
    }


def probe_python(*, command_runner: CommandRunner | None = None) -> dict[str, Any]:
    version = sys.version_info
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    path_python = shutil.which("python")
    path_python3 = shutil.which("python3")
    # "Python version(s)": this interpreter, plus the one `python` on PATH if it
    # is a different installation.  `sys.executable` may be a venv shim, so the
    # PATH one is worth measuring separately.
    others: list[dict[str, Any]] = []
    for candidate in (path_python, path_python3):
        if not candidate:
            continue
        if os.path.normcase(os.path.abspath(candidate)) == os.path.normcase(
            os.path.abspath(sys.executable)
        ):
            continue
        if any(
            os.path.normcase(os.path.abspath(entry["executable"]))
            == os.path.normcase(os.path.abspath(candidate))
            for entry in others
        ):
            continue
        if "\\windowsapps\\" in os.path.normcase(os.path.abspath(candidate)):
            # A Microsoft Store app-execution alias is a stub, not an
            # interpreter; running it can open the Store.  Report it, do not
            # execute it.
            others.append(
                {
                    "status": STATUS_SKIPPED,
                    "reason": "Microsoft Store app-execution alias; not executed to avoid a UI side effect",
                    "executable": candidate,
                }
            )
            continue
        others.append(_interpreter_version(candidate, command_runner=command_runner))
    return {
        "status": STATUS_OK,
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "version_info": [version.major, version.minor, version.micro],
        "compiler": platform.python_compiler(),
        "executable": sys.executable,
        "prefix": sys.prefix,
        "base_prefix": getattr(sys, "base_prefix", None),
        "in_virtualenv": bool(in_venv),
        "virtualenv": sys.prefix if in_venv else None,
        "platform": sys.platform,
        "path_python": path_python,
        "path_python3": path_python3,
        "path_interpreters": others,
        "source": "sys + platform + shutil.which + read-only `--version` calls",
    }


# ---------------------------------------------------------------- package probe
def probe_packages() -> dict[str, Any]:
    packages: dict[str, Any] = {}
    failures: list[dict[str, str]] = []
    for module_name, distribution in PACKAGE_MODULES:
        present: bool | None = None
        try:
            # find_spec locates a loader without executing the module, so this
            # never creates a CUDA context or downloads anything.
            present = importlib_util.find_spec(module_name) is not None
        except Exception as exc:  # noqa: BLE001 - a broken install must not abort
            present = None
            failures.append(
                {"package": module_name, "stage": "find_spec", "error": f"{type(exc).__name__}: {exc}"}
            )
        version: str | None = None
        try:
            version = importlib_metadata.version(distribution)
        except importlib_metadata.PackageNotFoundError:
            version = None
        except Exception as exc:  # noqa: BLE001
            failures.append(
                {"package": module_name, "stage": "metadata", "error": f"{type(exc).__name__}: {exc}"}
            )
        packages[module_name] = {
            "present": present,
            "version": version,
            "distribution": distribution,
        }
    return {
        "status": STATUS_OK,
        "method": (
            "importlib.util.find_spec (module presence, no import) + "
            "importlib.metadata.version (distribution metadata); no package is imported"
        ),
        "packages": packages,
        "failures": failures,
    }


# ------------------------------------------------------------------ safety gate
def probe_safety_gates() -> dict[str, Any]:
    repo_root = str(_REPO_ROOT)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        from experiments.local_llm_event_extraction.safety import gate_report
    except Exception as exc:  # noqa: BLE001 - the document must survive a broken checkout
        raise ProbeUnavailable(
            f"contract module experiments.local_llm_event_extraction.safety could not be imported: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    report = gate_report()
    gates: dict[str, Any] = {}
    for gate, entry in report.items():
        gates[gate] = {
            "open": bool(entry.get("open")),
            "env_var": entry.get("env_var"),
            "raw_value": entry.get("raw_value"),
        }
    return {
        "status": STATUS_OK,
        "source": "experiments.local_llm_event_extraction.safety.gate_report()",
        "gate_count": len(gates),
        "gates": gates,
        "all_closed": all(not gate["open"] for gate in gates.values()),
    }


# ------------------------------------------------------------------ aggregation
_PROBE_KEYS: tuple[str, ...] = (
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


def collect_environment(
    *,
    command_runner: CommandRunner | None = None,
    skip_slow: bool = False,
    clock: Callable[[], _dt.datetime] | None = None,
    probe_version: str = PROBE_VERSION,
) -> dict[str, Any]:
    """Collect the whole document.  Never raises because of a failing probe.

    ``command_runner`` is injectable so tests can run fully offline and
    deterministically; it must accept ``(argv, timeout)`` and return a
    :class:`CommandResult`.
    """
    started = time.monotonic()
    now = (clock or _dt.datetime.now)().astimezone()
    document: dict[str, Any] = {
        "probe_version": probe_version,
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(timespec="seconds"),
        "generated_at_utc": now.astimezone(_dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "probe_duration_s": None,
        "read_only": True,
        "command_policy": {
            "timeout_s": DEFAULT_TIMEOUT_S,
            "installs": False,
            "writes": "none unless --out is given",
            "network": False,
            "elevation_required": False,
            "skip_slow": bool(skip_slow),
        },
        "host": {
            "hostname": platform.node() or None,
            "platform": platform.platform(),
            "python_executable": sys.executable,
        },
    }

    document["os"] = _guarded(probe_os)
    document["cpu"] = _guarded(
        lambda: probe_cpu(command_runner=command_runner, skip_slow=skip_slow)
    )
    document["memory"] = _guarded(probe_memory)
    document["disks"] = _guarded(probe_disks)
    document["gpu"] = _guarded(
        lambda: probe_gpu(command_runner=command_runner, skip_slow=skip_slow)
    )
    document["wsl"] = _guarded(lambda: probe_wsl(command_runner=command_runner))
    document["python"] = _guarded(lambda: probe_python(command_runner=command_runner))
    document["packages"] = _guarded(probe_packages)
    document["safety_gates"] = _guarded(probe_safety_gates)

    limitations: list[dict[str, Any]] = []
    for key in _PROBE_KEYS:
        section = document[key]
        status = section.get("status")
        if status in (STATUS_UNAVAILABLE, STATUS_SKIPPED):
            limitations.append(
                {
                    "probe": key,
                    "status": status,
                    "reason": section.get("reason", "no reason recorded"),
                }
            )
    # A top-level probe can be "ok" while one of its optional enrichments was
    # skipped; say so rather than letting the report claim nothing was omitted.
    for parent, child in (("cpu", "cim"), ("gpu", "cim_inventory")):
        nested = document.get(parent, {}).get(child)
        if isinstance(nested, dict) and nested.get("status") in (
            STATUS_UNAVAILABLE,
            STATUS_SKIPPED,
        ):
            limitations.append(
                {
                    "probe": f"{parent}.{child}",
                    "status": nested.get("status"),
                    "reason": nested.get("reason", "no reason recorded"),
                }
            )
    document["limitations"] = limitations
    document["probe_duration_s"] = round(time.monotonic() - started, 3)
    return document


# --------------------------------------------------------------------- reporting
def _yes_no(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _fmt_gib(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "?"
    return f"{value:.2f} GiB"


def _reason_of(section: Mapping[str, Any]) -> str:
    return str(section.get("reason") or section.get("detail") or "no reason recorded")


def render_text(document: Mapping[str, Any]) -> str:
    """Render the human report.  ASCII-only so any console codepage can print it."""
    lines: list[str] = []
    add = lines.append

    add("=" * 78)
    add(f"MedRadar local small-LM research - environment probe {document.get('probe_version')}")
    add(f"schema {document.get('schema_version')} | generated {document.get('generated_at')}")
    add(f"read-only: {_yes_no(document.get('read_only'))} | "
        f"duration {document.get('probe_duration_s')} s")
    add("=" * 78)

    host = document.get("host", {})
    add("")
    add("[host]")
    add(f"  hostname : {host.get('hostname')}")
    add(f"  platform : {host.get('platform')}")

    os_info = document.get("os", {})
    add("")
    add("[os]")
    if os_info.get("status") == STATUS_OK:
        add(f"  {os_info.get('system')} {os_info.get('release')} "
            f"(build {os_info.get('windows_build_full') or os_info.get('windows_build')})")
        add(f"  edition  : {os_info.get('windows_product_name')} / "
            f"{os_info.get('windows_edition_id')} / display {os_info.get('windows_display_version')}")
        add(f"  arch     : {os_info.get('machine')} / {os_info.get('architecture')}")
        for note in os_info.get("notes") or []:
            add(f"  note     : {note}")
    else:
        add(f"  unavailable: {_reason_of(os_info)}")

    cpu = document.get("cpu", {})
    add("")
    add("[cpu]")
    if cpu.get("status") == STATUS_OK:
        add(f"  model    : {cpu.get('model') or 'not measured'} "
            f"({cpu.get('model_source') or 'no source'})")
        add(f"  cores    : {cpu.get('physical_cores') or '?'} physical / "
            f"{cpu.get('logical_cores') or '?'} logical")
        if cpu.get("max_clock_mhz"):
            add(f"  clock    : {cpu.get('max_clock_mhz')} MHz")
        cim = cpu.get("cim")
        if isinstance(cim, Mapping) and cim.get("status") != STATUS_OK:
            add(f"  note     : CIM core topology {cim.get('status')}: {_reason_of(cim)}")
    else:
        add(f"  unavailable: {_reason_of(cpu)}")

    memory = document.get("memory", {})
    add("")
    add("[memory]")
    if memory.get("status") == STATUS_OK:
        add(f"  total    : {_fmt_gib(memory.get('total_gib'))} "
            f"({memory.get('total_bytes')} bytes)")
        add(f"  available: {_fmt_gib(memory.get('available_gib'))} "
            f"({memory.get('available_bytes')} bytes)")
        add(f"  used     : {memory.get('percent_used')}%")
    else:
        add(f"  unavailable: {_reason_of(memory)}")

    disks = document.get("disks", {})
    add("")
    add("[disks]")
    if disks.get("status") == STATUS_OK:
        for drive in disks.get("drives") or []:
            if drive.get("status") != STATUS_OK:
                add(f"  {drive.get('mount')}: unavailable ({drive.get('reason')})")
                continue
            add(f"  {drive.get('mount'):<10} total {drive.get('total_gb')} GB "
                f"({drive.get('total_gib')} GiB)   free {drive.get('free_gb')} GB "
                f"({drive.get('free_gib')} GiB)   used {drive.get('percent_used')}%")
    else:
        add(f"  unavailable: {_reason_of(disks)}")

    gpu = document.get("gpu", {})
    add("")
    add("[gpu]")
    if gpu.get("status") == STATUS_OK:
        add(f"  source   : {gpu.get('source')}")
        for device in gpu.get("devices") or []:
            capability = device.get("compute_capability") or {}
            add(f"  [{device.get('index')}] {device.get('name')}")
            add(f"      driver {device.get('driver_version')} | "
                f"vram {device.get('memory_total_mib')} MiB total, "
                f"{device.get('memory_used_mib')} used, {device.get('memory_free_mib')} free")
            add(f"      compute capability {capability.get('reported')} "
                f"({capability.get('targeted_sm')})")
        runtime = gpu.get("cuda_runtime_version") or {}
        add(f"  CUDA runtime reported by driver: {runtime.get('reported')}")
        cim = gpu.get("cim_inventory") or {}
        if cim.get("status") == STATUS_OK:
            for controller in cim.get("controllers") or []:
                add(f"  CIM [{controller.get('index')}] {controller.get('name')} "
                    f"driver_raw {controller.get('driver_version_raw')}")
        elif cim.get("status"):
            add(f"  CIM inventory {cim.get('status')}: {_reason_of(cim)}")
        for note in gpu.get("notes") or []:
            add(f"  note     : {note}")
    else:
        add(f"  unavailable: {_reason_of(gpu)}")

    wsl = document.get("wsl", {})
    add("")
    add("[wsl]")
    if wsl.get("status") == STATUS_OK:
        add(f"  installed: {_yes_no(wsl.get('installed'))} "
            f"(status exit {wsl.get('status_exit_code')})")
        add(f"  version  : {wsl.get('wsl_version') or 'not measured'} "
            f"| kernel {wsl.get('kernel_version') or 'not measured'}")
        distributions = wsl.get("distributions") or []
        add(f"  distros  : {len(distributions)} registered")
        for distro in distributions:
            add(f"      {distro.get('name')} state={distro.get('state')} "
                f"version={distro.get('version')} default={_yes_no(distro.get('default'))}")
        for note in wsl.get("notes") or []:
            add(f"  note     : {note}")
    else:
        add(f"  unavailable: {_reason_of(wsl)}")

    python_info = document.get("python", {})
    add("")
    add("[python]")
    if python_info.get("status") == STATUS_OK:
        add(f"  {python_info.get('implementation')} {python_info.get('version')} "
            f"({python_info.get('compiler')})")
        add(f"  executable: {python_info.get('executable')}")
        add(f"  virtualenv: {_yes_no(python_info.get('in_virtualenv'))} "
            f"({python_info.get('virtualenv')})")
        for entry in python_info.get("path_interpreters") or []:
            if entry.get("status") == STATUS_OK:
                add(f"  PATH python: {entry.get('version')} at {entry.get('executable')}")
            else:
                add(f"  PATH python: {entry.get('status')} ({_reason_of(entry)})")
    else:
        add(f"  unavailable: {_reason_of(python_info)}")

    packages = document.get("packages", {})
    add("")
    add("[packages]  (metadata only; nothing was imported)")
    if packages.get("status") == STATUS_OK:
        present: list[str] = []
        absent: list[str] = []
        for name, entry in (packages.get("packages") or {}).items():
            if entry.get("present"):
                present.append(f"{name}=={entry.get('version') or '?'}")
            else:
                absent.append(name)
        add(f"  present  : {', '.join(present) if present else '(none)'}")
        add(f"  absent   : {', '.join(absent) if absent else '(none)'}")
    else:
        add(f"  unavailable: {_reason_of(packages)}")

    gates = document.get("safety_gates", {})
    add("")
    add("[safety gates]  (default-closed run gates)")
    if gates.get("status") == STATUS_OK:
        for gate, entry in (gates.get("gates") or {}).items():
            state = "OPEN" if entry.get("open") else "closed"
            add(f"  {gate:<12} {state:<7} {entry.get('env_var')} raw={entry.get('raw_value')!r}")
        add(f"  all closed: {_yes_no(gates.get('all_closed'))}")
    else:
        add(f"  unavailable: {_reason_of(gates)}")

    limitations = document.get("limitations") or []
    add("")
    add("[limitations]")
    if limitations:
        for item in limitations:
            add(f"  - {item.get('probe')}: {item.get('status')}: {item.get('reason')}")
    else:
        add("  none at top level: every top-level probe was measured "
            "(nested notes, if any, appear in their section)")

    add("")
    add("This probe performed no writes, no network access, no installs and no "
        "model loading.")
    return "\n".join(lines) + "\n"


# -------------------------------------------------------------------------- CLI
def _emit(text: str) -> None:
    """Write text to stdout as UTF-8, tolerating a non-UTF-8 console codepage."""
    stream = sys.stdout
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - capture fixtures may not support reconfigure
        pass
    stream.write(text)
    if not text.endswith("\n"):
        stream.write("\n")
    stream.flush()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="env_probe.py",
        description=(
            "Read-only environment probe for the MedRadar local small-LM research "
            "foundation. It installs nothing, writes nothing unless --out is given, "
            "uses no network and never loads a model or initialises CUDA."
        ),
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        default=None,
        help="write the JSON document to PATH (the only write this script performs)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the JSON document instead of the human-readable report",
    )
    parser.add_argument(
        "--skip-slow",
        action="store_true",
        help="skip the PowerShell CIM queries (CPU topology, video inventory)",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    command_runner: CommandRunner | None = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    document = collect_environment(
        command_runner=command_runner, skip_slow=bool(args.skip_slow)
    )
    payload = json.dumps(document, indent=2, ensure_ascii=False) + "\n"

    if args.out:
        out_path = Path(args.out)
        try:
            out_path.write_text(payload, encoding="utf-8", newline="\n")
        except OSError as exc:
            print(f"env_probe: cannot write {out_path}: {exc}", file=sys.stderr)
            return 2
        print(f"env_probe: wrote {out_path}", file=sys.stderr)

    if args.json:
        _emit(payload)
    else:
        _emit(render_text(document))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    raise SystemExit(main())
