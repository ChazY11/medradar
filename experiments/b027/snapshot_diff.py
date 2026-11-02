"""B-051: verify point-in-time integrity of every snapshot, and diff consecutive snapshots.

Two jobs in one pass:

  1. **Leakage audit.** For every frozen snapshot, check that nothing in it comes from after its
     as-of date: the window must end on or before the as-of month, and both the latest regulatory
     event and the latest trial event recorded per profile must be <= the as-of date. This is the
     property that makes the snapshot a point-in-time artifact rather than a reconstruction.
  2. **Snapshot diff.** Compare consecutive snapshots and report what changed between them: event
     totals, momentum classifications, track counts, contradictions, and which companies moved.

Usage:
    python experiments/b027/snapshot_diff.py
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE = Path("experiments/b027")
SNAPSHOTS = BASE / "snapshots"
OUT = BASE / "snapshot_diff.json"


def load(snapshot: Path) -> dict[str, Any]:
    return {
        "profiles": json.loads((snapshot / "profiles.json").read_text(encoding="utf-8")),
        "summary": json.loads((snapshot / "summary.json").read_text(encoding="utf-8")),
        "manifest": json.loads((snapshot / "manifest.json").read_text(encoding="utf-8")),
    }


def audit_leakage(as_of: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Check point-in-time integrity.

    Returns ``problems`` (evidence from after the as-of date, which is a defect) and
    ``unauditable`` (profiles without a ``leakage_audit`` block). The two are different: the first
    snapshot was frozen before the audit existed, so it is *not auditable*, which is not the same as
    *leaky*. Conflating them would either hide a real problem or invent one.
    """
    problems: list[str] = []
    unauditable = 0
    window_end = payload.get("window", ["", ""])[1]
    if window_end > as_of[:7]:
        problems.append(f"window ends {window_end}, after the as-of month {as_of[:7]}")
    for key, profile in payload["profiles"].items():
        audit = profile.get("leakage_audit")
        if not audit:
            unauditable += 1
            continue
        for field_name in ("latest_regulatory_event", "latest_trial_event"):
            value = audit.get(field_name)
            if value is not None and value > as_of:
                problems.append(f"{key}: {field_name}={value} is after as-of {as_of}")
        latest_code = audit.get("latest_code_first_seen")
        if latest_code is not None and latest_code > as_of[:7]:
            problems.append(f"{key}: code first seen {latest_code} is after as-of month {as_of[:7]}")
    return {"problems": problems, "unauditable": unauditable,
            "profiles": len(payload["profiles"]),
            "auditable": len(payload["profiles"]) - unauditable}


def compare(older: dict[str, Any], newer: dict[str, Any]) -> dict[str, Any]:
    old_profiles = older["profiles"]["profiles"]
    new_profiles = newer["profiles"]["profiles"]
    momentum_changes: list[dict[str, Any]] = []
    event_changes: list[dict[str, Any]] = []
    track_changes: list[dict[str, Any]] = []
    for key in sorted(set(old_profiles) & set(new_profiles)):
        old = old_profiles[key]
        new = new_profiles[key]
        old_momentum = old["momentum"].get("direction", old["momentum"].get("status"))
        new_momentum = new["momentum"].get("direction", new["momentum"].get("status"))
        if old_momentum != new_momentum:
            momentum_changes.append({"company": key, "from": old_momentum, "to": new_momentum})
        old_events = old["technology_footprint"]["total_events"]
        new_events = new["technology_footprint"]["total_events"]
        if old_events != new_events:
            event_changes.append({"company": key, "from": old_events, "to": new_events,
                                  "delta": new_events - old_events})
        old_tracks = {row["track"] for row in old["technology_footprint"]["rows"]}
        new_tracks = {row["track"] for row in new["technology_footprint"]["rows"]}
        if old_tracks != new_tracks:
            track_changes.append({"company": key,
                                  "entered": sorted(new_tracks - old_tracks),
                                  "dropped": sorted(old_tracks - new_tracks)})
    return {
        "from": older["profiles"]["as_of"],
        "to": newer["profiles"]["as_of"],
        "momentum_changes": momentum_changes,
        "event_changes": event_changes,
        "track_changes": track_changes,
        "detected_before": older["summary"].get("detected_momentum", {}),
        "detected_after": newer["summary"].get("detected_momentum", {}),
        "total_events_before": sum(block["technology_footprint"]["total_events"]
                                   for block in old_profiles.values()),
        "total_events_after": sum(block["technology_footprint"]["total_events"]
                                  for block in new_profiles.values()),
    }


def main() -> int:
    directories = sorted(path for path in SNAPSHOTS.iterdir() if path.is_dir())
    if len(directories) < 2:
        print("need at least two snapshots")
        return 1
    report: dict[str, Any] = {"snapshots": [path.name for path in directories],
                              "leakage_audit": {}, "diffs": []}
    failures = 0
    for directory in directories:
        loaded = load(directory)
        audit = audit_leakage(directory.name, loaded["profiles"])
        report["leakage_audit"][directory.name] = audit
        if audit["problems"]:
            failures += len(audit["problems"])
            print(f"{directory.name}: {len(audit['problems'])} leakage problem(s)")
            for problem in audit["problems"][:5]:
                print(f"   - {problem}")
        elif audit["unauditable"]:
            print(f"{directory.name}: no leakage found, but {audit['unauditable']} of "
                  f"{audit['profiles']} profiles predate the audit block "
                  f"(not auditable, which is not the same as leaky)")
        else:
            print(f"{directory.name}: point-in-time clean "
                  f"(window ends {loaded['profiles']['window'][1]}, "
                  f"{audit['auditable']} auditable profiles)")
    for older_dir, newer_dir in zip(directories, directories[1:]):
        diff = compare(load(older_dir), load(newer_dir))
        report["diffs"].append(diff)
        print(f"\n{diff['from']} -> {diff['to']}: events {diff['total_events_before']} -> "
              f"{diff['total_events_after']}; momentum changes {len(diff['momentum_changes'])}; "
              f"track changes {len(diff['track_changes'])}")
        for change in diff["momentum_changes"][:6]:
            print(f"   momentum {change['company']}: {change['from']} -> {change['to']}")
        for change in diff["track_changes"][:4]:
            print(f"   tracks {change['company']}: entered={change['entered'][:3]} "
                  f"dropped={change['dropped'][:3]}")
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"\nwrote {OUT}")
    print(f"leakage problems: {failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
