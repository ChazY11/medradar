#!/usr/bin/env python
"""Prove an installed wheel is self-sufficient (used by CI, safe to run locally).

What it does, all inside a throwaway directory:

1. ``pip install --no-deps --target <tmp>/site .`` -- installs the wheel exactly
   like ``pip install medradar`` does, just into a disposable prefix.
2. Runs a probe with ``PYTHONPATH=<tmp>/site`` from ``<tmp>/run`` -- a directory
   *outside* the git checkout, so the source tree can never satisfy an import.
3. The probe imports the package, resolves the config through
   ``share/medradar/config`` (data-files), loads companies/tracks and locates
   the demo snapshot, then asserts nothing landed in ``site-packages``.
4. Still in that probe, ``MEDRADAR_HOME`` points at ``<tmp>/home``: ``run_demo``
   must write its report there (never into ``site-packages``) and an offline
   ``run_doctor`` must come back green.

Exit code 0 = installed copy works; 1 = a concrete problem (printed as JSON).

    python scripts/check_install.py            # build + verify
    python scripts/check_install.py --keep     # keep the temp dir for poking
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Executed with the installed package on PYTHONPATH, cwd outside the repo.
PROBE = r"""
import json
import os
import sys

import medradar
import medradar.config as config
from medradar.config import (
    CONFIG_DIR,
    CONFIG_ORIGIN,
    DATA_DIR,
    ROOT,
    load_companies,
    load_tracks,
)
from medradar.onboarding import find_demo_metrics, run_demo, run_doctor

companies = load_companies("device")
tracks = load_tracks("device")
snapshot = find_demo_metrics()
demo = run_demo()  # default output: <MEDRADAR_HOME>/out/demo
doctor = run_doctor(network=False)

payload = {
    "package": os.path.dirname(os.path.abspath(medradar.__file__)),
    "python": sys.version.split()[0],
    "cwd": os.getcwd(),
    "config_origin": CONFIG_ORIGIN,
    "config_dir": str(CONFIG_DIR),
    "home": str(ROOT),
    "data_dir": str(DATA_DIR),
    "companies": len(companies.all()),
    "tracks": len(tracks.all()),
    "demo_snapshot": str(snapshot) if snapshot else None,
    "demo": {
        "status": demo.get("status"),
        "out_dir": demo.get("out_dir"),
        "index_html": demo.get("index_html"),
        "html_bytes": demo.get("html_bytes"),
        "elapsed_seconds": demo.get("elapsed_seconds"),
    },
    "doctor": {
        "status": doctor.get("status"),
        "failures": doctor.get("failures"),
        "warnings": doctor.get("warnings"),
    },
}

problems = []
config_norm = os.path.normcase(os.path.abspath(str(CONFIG_DIR)))
package_norm = os.path.normcase(os.path.abspath(payload["package"]))
data_norm = os.path.normcase(os.path.abspath(str(DATA_DIR)))
cwd_norm = os.path.normcase(os.path.abspath(os.getcwd()))
home_norm = os.path.normcase(os.path.abspath(str(ROOT)))

if not CONFIG_DIR.is_dir():
    problems.append("config directory does not exist")
if CONFIG_ORIGIN == "source":
    problems.append("config resolved from a git checkout instead of the wheel data-files")
if CONFIG_ORIGIN == "package":
    problems.append("config fell back to the in-package copy; data-files were not installed")
if len(companies.all()) == 0:
    problems.append("no companies loaded from installed config")
if len(tracks.all()) == 0:
    problems.append("no tracks loaded from installed config")
if data_norm.startswith(package_norm):
    problems.append("data directory resolves inside site-packages")
if config_norm.startswith(cwd_norm):
    problems.append("config directory resolves inside the probe cwd")
if snapshot is None:
    problems.append("demo snapshot not found in the installed copy (medradar demo would fail)")

if demo.get("status") != "ok":
    problems.append(f"run_demo failed from the installed copy: {demo.get('error')}")
else:
    index = os.path.normcase(os.path.abspath(str(demo.get("index_html") or "")))
    if not index:
        problems.append("run_demo reported no index.html")
    elif not index.startswith(home_norm):
        problems.append("demo report escaped MEDRADAR_HOME (wrote outside the data home)")
    elif not os.path.isfile(index):
        problems.append("run_demo reported success but index.html is missing")
    else:
        demo_dir = os.path.dirname(index)
        dashboard = os.path.join(demo_dir, "dashboard.html")
        payload["demo"]["dashboard_html"] = dashboard
        if not os.path.isfile(dashboard):
            problems.append("run_demo succeeded but dashboard.html is missing")
        import re as _re
        with open(index, "r", encoding="utf-8", errors="replace") as _fh:
            _html = _fh.read()
        _hrefs = [h for h in _re.findall(r'href="([^"]+)"', _html)
                  if not h.startswith(("http://", "https://", "#", "mailto:", "data:"))]
        _missing = sorted({h for h in _hrefs if not os.path.exists(os.path.join(demo_dir, h))})
        payload["demo"]["links_checked"] = len(set(_hrefs))
        if _missing:
            problems.append(f"demo report has dead local links: {_missing}")

if doctor.get("status") != "ok":
    problems.append(f"run_doctor failed from the installed copy: {doctor.get('failures')}")

payload["problems"] = problems
print("PROBE " + json.dumps(payload, ensure_ascii=False))
raise SystemExit(1 if problems else 0)
"""


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    print("$ " + " ".join(cmd), flush=True)
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def install_target(site: Path, *, repo: Path, isolation: bool) -> subprocess.CompletedProcess:
    """``pip install --no-deps --target site .`` (the task's canonical check)."""
    cmd = [sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(site)]
    if not isolation:
        cmd.append("--no-build-isolation")
    cmd.append("--upgrade")
    cmd.append(str(repo))
    result = _run(cmd, cwd=repo)
    if result.returncode != 0 and not isolation:
        print("[retry] --no-build-isolation failed, retrying with build isolation")
        return install_target(site, repo=repo, isolation=True)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(REPO_ROOT), help="checkout to install from")
    parser.add_argument("--keep", action="store_true", help="keep the temporary install tree")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    work = Path(tempfile.mkdtemp(prefix="medradar-install-"))
    site = work / "site"
    run_dir = work / "run"
    site.mkdir()
    run_dir.mkdir()

    summary: dict[str, object] = {
        "repo": str(repo),
        "temp": str(work),
        "site": str(site),
        "python": sys.version.split()[0],
        "installed": False,
        "probe": None,
        "problems": [],
    }

    try:
        result = install_target(site, repo=repo, isolation=False)
        print(result.stdout)
        if result.returncode != 0:
            summary["problems"] = [f"pip install --target failed (exit {result.returncode})"]
            summary["pip_output"] = result.stdout[-4000:]
            return _finish(summary, args.keep, work)

        installed = (site / "medradar" / "config.py").is_file()
        summary["config_files"] = sorted(
            p.name for p in (site / "share" / "medradar" / "config").glob("*")
        ) if (site / "share" / "medradar").is_dir() else []
        if not installed:
            summary["problems"] = ["package did not install into the target directory"]
            return _finish(summary, args.keep, work)
        summary["installed"] = True
        if not summary["config_files"]:
            summary["problems"] = [
                "no config data-files installed: no share/medradar/config under the target"
            ]
            return _finish(summary, args.keep, work)

        env = {key: value for key, value in os.environ.items() if key not in {
            "MEDRADAR_CONFIG_DIR",
            "MEDRADAR_HOME",
            "MEDRADAR_DEMO_METRICS",
        }}
        env["PYTHONPATH"] = str(site)
        env["PYTHONIOENCODING"] = "utf-8"
        # Installed-state data home: demo/doctor output must land here, never in
        # the target directory (which stands in for site-packages).
        env["MEDRADAR_HOME"] = str(work / "home")
        print("$ <probe> python -c ... (cwd=%s, PYTHONPATH=%s)" % (run_dir, site))
        probe = _run(
            [sys.executable, "-c", PROBE],
            cwd=run_dir,
            env=env,
        )
        print(probe.stdout)
        probe_line = next(
            (line for line in probe.stdout.splitlines() if line.startswith("PROBE ")),
            None,
        )
        if probe_line is None:
            summary["problems"] = [
                f"probe crashed before reporting (exit {probe.returncode})"
            ]
            return _finish(summary, args.keep, work)
        payload = json.loads(probe_line[len("PROBE "):])
        summary["probe"] = payload
        summary["demo"] = payload.get("demo")
        summary["doctor"] = payload.get("doctor")
        summary["problems"] = list(payload.get("problems") or [])
        if probe.returncode != 0 and not summary["problems"]:
            summary["problems"] = [f"probe exited {probe.returncode}"]
        return _finish(summary, args.keep, work)
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
        else:
            print(f"[keep] install tree kept at {work}")


def _finish(summary: dict[str, object], keep: bool, work: Path) -> int:
    problems = list(summary.get("problems") or [])
    summary["status"] = "ok" if not problems else "failed"
    if not keep:
        summary["temp"] = "(removed)"
    print("\n=== install check ===")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
