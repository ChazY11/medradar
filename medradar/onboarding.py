"""One-minute onboarding: offline demo report, environment doctor, watchlist.

Three user-facing helpers, kept free of side effects until called so ``import
medradar`` stays instant:

* :func:`run_demo` renders the full report from the committed
  ``docs/metrics.json`` snapshot. No network, no collectors, no SQLite: just
  "install -> see the product in under a minute".
* :func:`run_doctor` answers "why is this broken?" with six checks, each
  returning PASS/FAIL/WARN instead of raising.
* :func:`watchlist_add` / :func:`watchlist_remove` / :func:`watchlist_list`
  edit the curated ``config/companies_device.json`` registry atomically (UTF-8,
  Chinese kept readable, no half-written file on error).

The CLI wiring lives in ``medradar.__main__`` (Lead-owned); everything here is
importable and testable on its own.
"""

from __future__ import annotations

import os
import platform
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from . import config
from .util import ensure_dir, read_json, write_json

#: Committed offline snapshot used by ``medradar demo`` (also shipped in the
#: wheel as ``share/medradar/docs/metrics.json`` so an installed copy can demo).
DEMO_METRICS_ENV = "MEDRADAR_DEMO_METRICS"
DEMO_SUBDIR = "demo"
DEMO_BUDGET_SECONDS = 60.0

DOCTOR_NETWORK_URL = "https://api.fda.gov/device/510k.json?limit=1"
DOCTOR_NETWORK_TIMEOUT = 4.0

#: Files ``analyze``/``report`` cannot work without.
REQUIRED_CONFIG_FILES = (
    "companies_device.json",
    "companies_drug.json",
    "tracks_device.json",
    "tracks_drug.json",
    "sources.json",
)
#: Nice-to-have files: missing them degrades coverage but must not fail doctor.
OPTIONAL_CONFIG_FILES = (
    "product_code_tracks.json",
    "nmpa_demo_seed.csv",
)

WATCHLIST_NAME = "companies_device.json"

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


# --------------------------------------------------------------------------- demo
def _demo_metrics_candidates(metrics_path: str | Path | None = None) -> list[Path]:
    """Every place an offline metrics snapshot may live, in priority order.

    An explicit ``metrics_path`` or ``MEDRADAR_DEMO_METRICS`` is treated as the
    *only* candidate: silently falling back to the committed snapshot would hide
    a typo in a CI job that thinks it is testing a fixture.
    """
    if metrics_path is not None:
        return [Path(metrics_path).expanduser()]
    env_value = str(os.environ.get(DEMO_METRICS_ENV) or "").strip()
    if env_value:
        return [Path(env_value).expanduser()]

    candidates: list[Path] = []
    candidates.append(config.ROOT / "docs" / "metrics.json")
    candidates.append(config.SOURCE_ROOT / "docs" / "metrics.json")
    for shared in config.share_candidates("docs"):
        candidates.append(shared / "metrics.json")
    candidates.append(config.PACKAGE_DIR / "_data" / "metrics.json")

    ordered: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            ordered.append(path)
    return ordered


def find_demo_metrics(metrics_path: str | Path | None = None) -> Path | None:
    """First existing offline snapshot, or ``None``."""
    for candidate in _demo_metrics_candidates(metrics_path):
        if candidate.is_file():
            return candidate
    return None


def run_demo(
    out_dir: str | Path | None = None,
    metrics_path: str | Path | None = None,
) -> dict[str, Any]:
    """Render the full report from a committed snapshot, fully offline.

    Args:
        out_dir: output directory, defaults to ``<MEDRADAR_HOME>/out/demo``.
        metrics_path: explicit snapshot override (tests/fixtures); by default
            the committed ``docs/metrics.json`` is located via
            :func:`find_demo_metrics`.

    Returns:
        ``{"status": "ok"|"failed", ...}`` -- never raises for an expected
        failure such as a missing snapshot, so a CLI wrapper can just print it.
    """

    started = time.perf_counter()
    snapshot = find_demo_metrics(metrics_path)
    if snapshot is None:
        return {
            "status": "failed",
            "error": "no offline metrics snapshot found",
            "hint": (
                "run from the repo root (docs/metrics.json is committed) or set "
                f"{DEMO_METRICS_ENV}=/path/to/metrics.json"
            ),
            "searched": [str(path) for path in _demo_metrics_candidates(metrics_path)],
        }

    metrics = read_json(snapshot, default={})
    if not isinstance(metrics, dict) or not metrics:
        return {
            "status": "failed",
            "error": f"snapshot is missing or not valid JSON: {snapshot}",
            "hint": "the demo needs the committed docs/metrics.json snapshot",
        }

    target = Path(out_dir).expanduser() if out_dir is not None else config.OUT_DIR / DEMO_SUBDIR
    if target.exists() and not target.is_dir():
        return {
            "status": "failed",
            "error": f"demo output path is a file, not a directory: {target}",
        }
    ensure_dir(target)

    from .report import build_report  # lazy: report.py is heavy and only demo needs it

    result = build_report(metrics_path=snapshot, out_dir=target, docs_dir=target)
    elapsed = round(time.perf_counter() - started, 3)

    return {
        "status": "ok",
        "offline": True,
        "elapsed_seconds": elapsed,
        "budget_seconds": DEMO_BUDGET_SECONDS,
        "snapshot": str(snapshot),
        "out_dir": str(target),
        "index_html": result["files"]["index_html"],
        "files": result["files"],
        "html_bytes": result["html_bytes"],
        "html_lines": result["html_lines"],
        "chapters_zh": result["chapters_zh"],
        "device_tracks": result["device_tracks"],
        "device_companies": result["device_companies"],
        "drug_approvals": result["drug_approvals"],
        "signals": result["signals"],
        "cn_gap_status": result["cn_gap_status"],
        "trading": result["trading"],
        "next": f"open {result['files']['index_html']} in a browser",
    }


# ------------------------------------------------------------------------- doctor
def _check(name: str, status: str, detail: str, **extra: Any) -> dict[str, Any]:
    payload = {"name": name, "status": status, "detail": detail}
    payload.update(extra)
    return payload


def _check_python() -> dict[str, Any]:
    required = (3, 10)
    current = sys.version_info[:2]
    version = ".".join(str(part) for part in sys.version_info[:3])
    status = PASS if current >= required else FAIL
    return _check(
        "python",
        status,
        f"{platform.python_implementation()} {version} (requires >= 3.10)",
    )


def _check_config_dir(config_dir: Path) -> dict[str, Any]:
    if not config_dir.exists():
        return _check("config_dir", FAIL, f"missing: {config_dir}")
    if not config_dir.is_dir():
        return _check("config_dir", FAIL, f"not a directory: {config_dir}")
    try:
        with os.scandir(config_dir) as entries:
            next(entries, None)
    except OSError as exc:
        return _check("config_dir", FAIL, f"cannot read {config_dir}: {exc}")
    return _check("config_dir", PASS, f"readable: {config_dir}")


def _check_config_files(config_dir: Path) -> dict[str, Any]:
    missing = [name for name in REQUIRED_CONFIG_FILES if not (config_dir / name).is_file()]
    if missing:
        return _check(
            "config_files",
            FAIL,
            f"missing {len(missing)} required file(s): {', '.join(missing)}",
            missing=missing,
        )
    optional_missing = [
        name for name in OPTIONAL_CONFIG_FILES if not (config_dir / name).is_file()
    ]
    detail = f"{len(REQUIRED_CONFIG_FILES)} required file(s) present"
    if optional_missing:
        return _check(
            "config_files",
            WARN,
            f"{detail}; optional missing: {', '.join(optional_missing)}",
            optional_missing=optional_missing,
        )
    return _check("config_files", PASS, detail)


def _check_data_dir(home: Path) -> dict[str, Any]:
    data_dir = home / "data"
    try:
        ensure_dir(data_dir)
        with tempfile.NamedTemporaryFile("w", dir=str(data_dir), delete=False, suffix=".probe") as handle:
            probe = Path(handle.name)
            handle.write("ok")
        probe.unlink()
    except OSError as exc:
        return _check("data_dir", FAIL, f"not writable: {data_dir} ({exc})")
    return _check("data_dir", PASS, f"writable: {data_dir}")


def _check_db(home: Path) -> dict[str, Any]:
    db_path = home / "data" / "medradar.sqlite"
    existed = db_path.exists()
    conn: sqlite3.Connection | None = None
    try:
        ensure_dir(db_path.parent)
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.execute("PRAGMA schema_version")
        conn.execute("SELECT 1")
    except (OSError, sqlite3.Error) as exc:
        return _check("db", FAIL, f"cannot open {db_path}: {exc}")
    finally:
        if conn is not None:
            conn.close()
    return _check("db", PASS, f"opened ({'existing' if existed else 'new'}): {db_path}")


def _check_network(timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        DOCTOR_NETWORK_URL,
        method="HEAD",
        headers={"User-Agent": "medradar-doctor/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https URL
            status = getattr(response, "status", 200)
        return _check("network", PASS, f"openFDA reachable (HTTP {status})")
    except urllib.error.HTTPError as exc:  # a 4xx still proves connectivity
        return _check("network", PASS, f"openFDA reachable (HTTP {exc.code}, HEAD not allowed)")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return _check(
            "network",
            WARN,
            f"openFDA unreachable ({type(exc).__name__}: {exc}); offline mode still works",
        )


def run_doctor(
    config_dir: str | Path | None = None,
    home: str | Path | None = None,
    network: bool = True,
    timeout: float = DOCTOR_NETWORK_TIMEOUT,
) -> dict[str, Any]:
    """Six environment checks; returns a report dict, never raises.

    Checks: python version, config dir readable, required config files present,
    data dir writable, SQLite store openable, optional openFDA reachability.

    Args:
        config_dir: override the resolved config directory (tests/CI).
        home: override ``MEDRADAR_HOME`` (tests/CI).
        network: set ``False`` for a deterministic offline doctor run.
        timeout: seconds for the single HEAD probe.

    Returns:
        ``{"status": "ok"|"fail", "checks": [...], ...}`` with one entry per
        check. ``status`` is ``"fail"`` only when a check returned ``FAIL``.
    """

    started = time.perf_counter()
    resolved_config_dir = Path(config_dir).expanduser() if config_dir is not None else config.CONFIG_DIR
    resolved_home = Path(home).expanduser() if home is not None else config.ROOT

    checks = [
        _check_python(),
        _check_config_dir(resolved_config_dir),
        _check_config_files(resolved_config_dir),
        _check_data_dir(resolved_home),
        _check_db(resolved_home),
        _check_network(timeout) if network else _check("network", WARN, "skipped (offline)"),
    ]

    failures = [check["name"] for check in checks if check["status"] == FAIL]
    warnings = [check["name"] for check in checks if check["status"] == WARN]
    try:
        same_config = resolved_config_dir.resolve() == config.CONFIG_DIR.resolve()
    except OSError:  # pragma: no cover - unresolvable path on exotic filesystems
        same_config = False
    payload: dict[str, Any] = {
        "status": "fail" if failures else "ok",
        "python": platform.python_version(),
        "config_dir": str(resolved_config_dir),
        "config_origin": config.CONFIG_ORIGIN if same_config else "explicit",
        "home": str(resolved_home),
        "checks": checks,
        "failures": failures,
        "warnings": warnings,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    if failures:
        payload["hint"] = (
            "fix the FAIL entries above; set MEDRADAR_CONFIG_DIR to a writable "
            "config copy and MEDRADAR_HOME to a writable data home if the install "
            "directory is read-only"
        )
    return payload


# ----------------------------------------------------------------------- watchlist
def watchlist_path(config_dir: str | Path | None = None) -> Path:
    """Path of the curated device-company registry edited by the watchlist helpers."""
    base = Path(config_dir).expanduser() if config_dir is not None else config.CONFIG_DIR
    return base / WATCHLIST_NAME


def _load_watchlist(config_dir: str | Path | None) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    path = watchlist_path(config_dir)
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise FileNotFoundError(
            f"watchlist config not found: {path} "
            "(run from the repo root or set MEDRADAR_CONFIG_DIR)"
        )
    companies = payload.get("companies")
    if not isinstance(companies, list):
        raise ValueError(f"malformed watchlist config (no 'companies' list): {path}")
    return path, payload, companies


def watchlist_list(config_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """Return the curated company entries, in file order."""
    _, _, companies = _load_watchlist(config_dir)
    return [dict(company) for company in companies]


def _normalise_key(key: Any) -> str:
    text = str(key or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not text:
        raise ValueError("watchlist key must be a non-empty string")
    return text


def _write_watchlist(path: Path, payload: dict[str, Any], companies: list[dict[str, Any]]) -> None:
    """Atomic UTF-8 rewrite (Chinese stays literal, no torn file on crash)."""
    if not path.parent.exists():
        raise FileNotFoundError(f"config directory does not exist: {path.parent}")
    if not os.access(path.parent, os.W_OK):
        raise PermissionError(
            f"config directory is not writable: {path.parent} "
            "(set MEDRADAR_CONFIG_DIR to a writable copy)"
        )
    payload["companies"] = companies
    payload["updated"] = date.today().isoformat()
    write_json(path, payload, indent=2)


def watchlist_add(
    key: str,
    name_en: str | None = None,
    name_zh: str | None = None,
    ticker: str | None = None,
    aliases: Iterable[str] | None = None,
    sector: str = "device",
    is_major: int = 0,
    config_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Append a company to the curated registry; idempotent by ``key``.

    Returns ``{"status": "added"|"exists", "key": ..., "count": ..., "path": ...}``.
    """
    path, payload, companies = _load_watchlist(config_dir)
    company_key = _normalise_key(key)
    for company in companies:
        if str(company.get("key", "")).strip().lower() == company_key:
            return {
                "status": "exists",
                "key": company_key,
                "count": len(companies),
                "path": str(path),
            }
    entry: dict[str, Any] = {
        "key": company_key,
        "name_en": str(name_en if name_en is not None else key).strip(),
        "name_zh": str(name_zh or "").strip(),
        "ticker": str(ticker or "").strip(),
        "sector": str(sector or "device"),
        "is_major": int(is_major),
        "aliases": [str(alias).strip() for alias in (aliases or []) if str(alias).strip()],
    }
    companies.append(entry)
    _write_watchlist(path, payload, companies)
    return {"status": "added", "key": company_key, "count": len(companies), "path": str(path)}


def watchlist_remove(key: str, config_dir: str | Path | None = None) -> dict[str, Any]:
    """Drop a company from the curated registry; missing key is a no-op."""
    path, payload, companies = _load_watchlist(config_dir)
    company_key = _normalise_key(key)
    remaining = [
        company
        for company in companies
        if str(company.get("key", "")).strip().lower() != company_key
    ]
    if len(remaining) == len(companies):
        return {
            "status": "missing",
            "key": company_key,
            "count": len(companies),
            "path": str(path),
        }
    _write_watchlist(path, payload, remaining)
    return {"status": "removed", "key": company_key, "count": len(remaining), "path": str(path)}


__all__ = [
    "DEMO_METRICS_ENV",
    "FAIL",
    "PASS",
    "WARN",
    "find_demo_metrics",
    "run_demo",
    "run_doctor",
    "watchlist_add",
    "watchlist_list",
    "watchlist_path",
    "watchlist_remove",
]
