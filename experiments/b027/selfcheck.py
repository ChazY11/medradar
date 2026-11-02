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
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
