"""Self-check for the generated company profiles.

Verifies, for every profile in experiments/b027/profiles.json:

  1. the seven required fields exist and validate;
  2. the rendered Markdown contains all seven section headings;
  3. every number the Markdown states about the footprint is the number in the JSON;
  4. the contradiction count in the prose equals the number of recorded findings;
  5. rendering is deterministic (same JSON, same Markdown);
  6. the identity statement's entity count matches the recorded entity set.

Exit code 0 means every check passed; any failure prints the profile and the mismatch.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.intelligence.profile import (  # noqa: E402
    SEVEN_FIELDS,
    render_markdown,
    validate_profile,
)
from medradar.intelligence.snapshot import verify_manifest  # noqa: E402

BASE = Path("experiments/b027")
HEADINGS = (
    "## 1. Identity",
    "## 2. Technology footprint",
    "## 3. Momentum",
    "## 4. Concentration",
    "## 5. Independent corroboration",
    "## 6. Contradictory evidence",
    "## 7. Limits and provenance",
)


def check_profile(key: str, profile: dict, markdown: str) -> list[str]:
    problems: list[str] = []
    for field in SEVEN_FIELDS:
        if field not in profile:
            problems.append(f"missing field {field}")
    problems.extend(validate_profile(profile))
    for heading in HEADINGS:
        if heading not in markdown:
            problems.append(f"missing heading {heading}")

    footprint = profile["technology_footprint"]
    if f"{footprint['total_events']} material events" not in markdown:
        problems.append("footprint total not found in markdown")
    if f"across {footprint['tracks']} technology tracks" not in markdown:
        problems.append("footprint track count not found in markdown")
    for row in footprint["rows"]:
        expected = f"| {row['track']} | {row['events']} | {row['first']} | {row['last']} |"
        if expected not in markdown:
            problems.append(f"footprint row not reproduced: {row['track']}")

    contradictions = profile["contradictory_evidence"]
    if contradictions["found"]:
        expected_count = (f"{len(contradictions['found'])} contradictory observation(s) out of "
                          f"{len(contradictions['checks'])} checks")
    else:
        expected_count = (f"no contradictory observation found across the "
                          f"{len(contradictions['checks'])} checks run")
    if expected_count not in markdown:
        problems.append("contradiction statement does not match the recorded findings")

    identity = profile["identity"]
    if f"{identity['entity_count']} resolved legal entities" not in markdown:
        problems.append("entity count not found in markdown")

    # momentum must carry its test, not just a ratio
    momentum = profile["momentum"]
    if momentum.get("status") == "estimated" and momentum.get("p_value") is not None:
        if f"p={momentum['p_value']:.3f}" not in markdown:
            problems.append("momentum p-value not found in markdown")
        if "minimum detectable ratio at 80 % power" not in markdown:
            problems.append("momentum MDE not found in markdown")
        if f"detected={momentum.get('detected')}" not in markdown:
            problems.append("momentum detected flag not found in markdown")
        if momentum.get("detected") and momentum.get("direction") == "no_detectable_change":
            problems.append("momentum reports no detectable change but is marked detected")
        if not momentum.get("detected") and momentum.get("direction") != "no_detectable_change":
            problems.append("momentum direction contradicts the detected flag")

    # deployment block: the detector must be the one fixed by D-045, and every alert must clear its
    # own threshold, otherwise the profile would be reporting a detection the calibration does not
    # support
    deployment = momentum.get("deployment_alerts")
    if deployment:
        if deployment.get("resolution_months") != 3:
            problems.append("deployment resolution is not the quarterly one fixed by D-045")
        if deployment.get("detector") != "rolling_zscore":
            problems.append("deployment detector is not the one fixed by D-045")
        for alert in deployment.get("flagged", []):
            if alert.get("z", 0) < deployment.get("threshold", 0):
                problems.append(f"alert {alert.get('track')} does not clear its own threshold")
        marker = f"Deployment detector: {deployment.get('detector')} at " \
                 f"{deployment.get('resolution_months')}-month resolution"
        if marker not in markdown:
            problems.append("deployment detector line not found in markdown")
        if f"{deployment.get('false_alarm_rate'):.3f}" not in markdown:
            problems.append("deployment false-alarm rate not found in markdown")

    if render_markdown(profile) != markdown:
        problems.append("rendering is not deterministic")
    return problems


def main() -> int:
    path = BASE / "profiles.json"
    if not path.exists():
        print(f"missing {path}; run build_profiles.py first")
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    failures = 0
    for key, profile in payload["profiles"].items():
        markdown_path = BASE / "profiles" / f"{key}.md"
        if not markdown_path.exists():
            print(f"{key}: missing markdown file")
            failures += 1
            continue
        markdown = markdown_path.read_text(encoding="utf-8")
        problems = check_profile(key, profile, markdown)
        if problems:
            failures += 1
            print(f"{key}: {len(problems)} problem(s)")
            for problem in problems:
                print(f"   - {problem}")
        else:
            print(f"{key}: OK ({profile['technology_footprint']['total_events']} events, "
                  f"{len(profile['contradictory_evidence']['found'])} contradictions)")
    print(f"\nchecked {len(payload['profiles'])} profiles; failures={failures}")
    snapshot_failures = check_snapshots()
    return 0 if failures == 0 and snapshot_failures == 0 else 1


def check_snapshots() -> int:
    """Verify every frozen snapshot: manifest hashes, markdown reproduction, as-of consistency."""
    snapshot_root = BASE / "snapshots"
    if not snapshot_root.exists():
        print("\nno snapshots to verify")
        return 0
    failures = 0
    for directory in sorted(path for path in snapshot_root.iterdir() if path.is_dir()):
        manifest_path = directory / "manifest.json"
        profiles_path = directory / "profiles.json"
        summary_path = directory / "summary.json"
        if not (manifest_path.exists() and profiles_path.exists() and summary_path.exists()):
            print(f"snapshot {directory.name}: missing manifest/profiles/summary")
            failures += 1
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        problems = verify_manifest(manifest, artifacts={"profiles": profiles,
                                                        "summary": summary})
        if manifest.get("as_of") != directory.name:
            problems.append("manifest as_of does not match the snapshot directory name")
        if summary.get("companies") != len(profiles["profiles"]):
            problems.append("summary company count does not match profiles.json")
        markdown_dir = directory / "markdown"
        missing = [key for key in profiles["profiles"]
                   if not (markdown_dir / f"{key}.md").exists()]
        if missing:
            problems.append(f"{len(missing)} profiles have no frozen markdown")
        mismatched = [key for key, profile in profiles["profiles"].items()
                      if (markdown_dir / f"{key}.md").exists()
                      and (markdown_dir / f"{key}.md").read_text(encoding="utf-8")
                      != render_markdown(profile)]
        if mismatched:
            problems.append(f"{len(mismatched)} frozen markdown files do not reproduce from JSON")
        if problems:
            failures += 1
            print(f"snapshot {directory.name}: {len(problems)} problem(s)")
            for problem in problems:
                print(f"   - {problem}")
        else:
            print(f"snapshot {directory.name}: OK ({summary['companies']} companies, "
                  f"manifest {manifest['manifest_hash'][:12]}...)")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
