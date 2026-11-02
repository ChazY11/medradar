"""B-049: freeze a dated, hash-verified snapshot of the company profiles.

A profile set is only a point-in-time artifact if a later cycle can prove what it contained. This
script builds the full-roster profiles, writes them to `experiments/b027/snapshots/<as-of>/`, and
records a manifest with:

  * a SHA-256 per artifact (the profile payload and the summary),
  * a SHA-256 per input source (the lane database, the trial database, the configs),
  * the as-of date and evidence window,
  * a manifest hash over all of it.

It then re-reads everything from disk and verifies the manifest, so a snapshot that does not verify
is never left behind silently.

Usage:
    python experiments/b027/freeze_snapshot.py --as-of 2026-11-02
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.intelligence.profile import render_markdown  # noqa: E402
from medradar.intelligence.snapshot import (  # noqa: E402
    build_manifest,
    is_iso_date,
    verify_manifest,
)

BASE = Path("experiments/b027")
SOURCES = (
    Path("data/research.sqlite"),
    Path("data/b040_device_trials.sqlite"),
    Path("config/companies_device.json"),
    Path("config/universe_v1.json"),
    Path("config/product_code_tracks.json"),
    Path("config/tracks_v1.json"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-11-02")
    parser.add_argument("--scope", choices=("focus", "roster"), default="roster")
    args = parser.parse_args(argv)
    if not is_iso_date(args.as_of):
        print(f"invalid --as-of {args.as_of!r}; expected YYYY-MM-DD")
        return 1

    snapshot_dir = BASE / "snapshots" / args.as_of
    if snapshot_dir.exists():
        print(f"snapshot already exists: {snapshot_dir}")
        return 1
    work_dir = BASE / "_build"
    if work_dir.exists():
        shutil.rmtree(work_dir)

    print(f"building {args.scope} profiles into {work_dir}")
    result = subprocess.run([sys.executable, "experiments/b027/build_profiles.py",
                             "--scope", args.scope, "--as-of", args.as_of,
                             "--out", str(work_dir)],
                            text=True)
    if result.returncode != 0:
        print("profile build failed")
        return result.returncode

    profiles_path = work_dir / "profiles.json"
    payload = json.loads(profiles_path.read_text(encoding="utf-8"))
    summary = {
        "as_of": args.as_of,
        "scope": payload.get("scope"),
        "window": payload.get("window"),
        "companies": len(payload["profiles"]),
        "focus_companies": payload.get("focus_companies"),
        "detected_momentum": {key: block["momentum"]["direction"]
                              for key, block in payload["profiles"].items()
                              if block["momentum"].get("detected")},
        "companies_with_contradictions": {
            key: len(block["contradictory_evidence"]["found"])
            for key, block in payload["profiles"].items()
            if block["contradictory_evidence"]["found"]},
        "companies_with_no_events": [key for key, block in payload["profiles"].items()
                                     if block["technology_footprint"]["total_events"] == 0],
        "source_hint": "manifest.json records the SHA-256 of every input source",
    }
    sources = {str(path): sha256_file(path) for path in SOURCES if path.exists()}
    manifest = build_manifest(
        as_of=args.as_of, window=tuple(payload["window"]), artifacts={
            "profiles": payload, "summary": summary},
        sources=sources,
        notes=(f"scope={payload.get('scope')}", f"git_head={git_head()}",
               "frozen by experiments/b027/freeze_snapshot.py"))

    snapshot_dir.mkdir(parents=True, exist_ok=False)
    (snapshot_dir / "markdown").mkdir()
    (snapshot_dir / "profiles.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    for key, profile in payload["profiles"].items():
        (snapshot_dir / "markdown" / f"{key}.md").write_text(
            render_markdown(profile), encoding="utf-8", newline="\n")
    (snapshot_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    (snapshot_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    # verify by re-reading what was written
    reread_profiles = json.loads((snapshot_dir / "profiles.json").read_text(encoding="utf-8"))
    reread_summary = json.loads((snapshot_dir / "summary.json").read_text(encoding="utf-8"))
    reread_manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    problems = verify_manifest(reread_manifest,
                               artifacts={"profiles": reread_profiles,
                                          "summary": reread_summary})
    if problems:
        print("SNAPSHOT FAILED VERIFICATION:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    shutil.rmtree(work_dir)
    print(f"snapshot verified: {snapshot_dir}")
    print(f"  companies={len(payload['profiles'])} "
          f"detected_momentum={len(summary['detected_momentum'])} "
          f"with_contradictions={len(summary['companies_with_contradictions'])} "
          f"no_events={len(summary['companies_with_no_events'])}")
    print(f"  manifest_hash={manifest['manifest_hash'][:16]}... "
          f"sources={len(sources)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
