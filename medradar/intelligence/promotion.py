"""Promotion of a detected change to "technology change" status: policy as code.

The programme has one confirmed decision rule (DECISIONS D-043, replicated D-048): an alert followed by a
**two-month confirmation window that excludes the alert month** separates a transient spike from a sustained
change with measured precision 0.914–0.917 against a base rate of about 0.70. That rule classifies the time
series; it does not decide policy.

This module makes the policy explicit and testable rather than leaving it to prose:

  1. **Only a calibrated alert can be promoted.** The alert must come from the deployed detector at the
     validated resolution (3 months, rolling z-score, threshold 3.5), with its measured false-alarm rate
     carried along.
  2. **The confirmed rule must classify it as sustained.** Using only the two quarters after the alert.
  3. **A human sign-off is required and recorded.** The function can only ever return
     ``requires_signoff: True``; there is no automated promotion path, by design (D-046/D-049).
  4. **Promotion is a statement about filing rate, never about technology.** Every decision carries the
     wording to that effect so downstream text cannot upgrade it silently.

    python -m medradar.intelligence.promotion   # prints the policy and its provenance
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

POLICY_VERSION = "promotion_policy_v1"

#: the confirmed rule, fixed by D-043 and replicated at the entity unit in D-048
CONFIRMATION_QUARTERS = 2
RATE_FLOOR = 1.5          # below this multiple of the baseline the change is a spike
MIN_ALERT_EVENTS = 1

REQUIRED_EVIDENCE = (
    "calibrated_alert",
    "confirmation_window",
    "contradiction_check",
    "human_signoff",
)

STATEMENT = ("promotion marks a sustained change in PUBLIC FILING RATE; it is not evidence of "
             "intent, capability, internal R&D or technological significance")


def classify_shape(following_counts: Sequence[int], baseline_rate: float, *,
                   quarters: int = CONFIRMATION_QUARTERS,
                   floor: float = RATE_FLOOR) -> dict[str, Any]:
    """Apply the confirmed rule to the quarters after an alert (alert quarter excluded)."""
    window = [int(count) for count in list(following_counts)[:quarters]]
    if not window:
        return {"shape": "unknown", "reason": "no confirmation quarters available",
                "post_rate": None, "relative": None}
    post_rate = sum(window) / len(window)
    if baseline_rate <= 0:
        return {"shape": "unknown", "reason": "baseline rate is zero", "post_rate": post_rate,
                "relative": None}
    relative = post_rate / baseline_rate
    if relative < floor:
        return {"shape": "spike", "reason": f"post-alert rate {relative:.2f}x baseline is below the "
                                            f"{floor:g}x floor", "post_rate": post_rate,
                "relative": round(relative, 3)}
    if len(window) >= 2 and window[-1] > window[0]:
        return {"shape": "ramp", "reason": "post-alert rate is elevated and still rising",
                "post_rate": post_rate, "relative": round(relative, 3)}
    return {"shape": "level", "reason": "post-alert rate is elevated and flat", "post_rate": post_rate,
            "relative": round(relative, 3)}


def decide_promotion(alert: Mapping[str, Any], following_counts: Sequence[int] | None,
                     *, policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the promotion decision for one alert, with its evidence and its gate failures.

    ``alert`` must carry the calibrated detector fields produced by the profile engine
    (``track``, ``quarter``, ``events``, ``baseline_mean``, ``z``) plus the detector provenance
    (``detector``, ``resolution_months``, ``threshold``, ``false_alarm_rate``).
    """
    active = dict(policy or DEFAULT_POLICY)
    problems: list[str] = []

    if alert.get("detector") != active["detector"]:
        problems.append(f"alert detector {alert.get('detector')!r} is not the validated one")
    if alert.get("resolution_months") != active["resolution_months"]:
        problems.append(f"alert resolution {alert.get('resolution_months')!r} is not the validated one")
    if (alert.get("threshold") or 0) != active["threshold"]:
        problems.append("alert threshold is not the validated one")
    if (alert.get("events") or 0) < MIN_ALERT_EVENTS:
        problems.append("alert has no events")
    if (alert.get("z") or 0) < (alert.get("threshold") or active["threshold"]):
        problems.append("alert does not clear its own threshold")

    classification = classify_shape(following_counts or [], float(alert.get("baseline_mean") or 0.0))
    if classification["shape"] in ("spike", "unknown"):
        problems.append(f"shape classified as {classification['shape']}: {classification['reason']}")

    if problems:
        verdict = "reject"
    else:
        verdict = "promote_pending_signoff"

    return {
        "policy_version": active["version"],
        "track": alert.get("track"),
        "quarter": alert.get("quarter"),
        "verdict": verdict,
        "requires_signoff": True,
        "shape": classification["shape"],
        "shape_reason": classification["reason"],
        "relative_post_rate": classification["relative"],
        "gate_failures": problems,
        "evidence_required": list(REQUIRED_EVIDENCE),
        "detector_provenance": {
            "detector": active["detector"],
            "resolution_months": active["resolution_months"],
            "threshold": active["threshold"],
            "false_alarm_rate": active["false_alarm_rate"],
            "rule": active["rule"],
        },
        "statement": STATEMENT,
    }


DEFAULT_POLICY: dict[str, Any] = {
    "version": POLICY_VERSION,
    "detector": "rolling_zscore",
    "resolution_months": 3,
    "threshold": 3.5,
    "false_alarm_rate": 0.0179,
    "rule": "two-month post-alert window excluding the alert month (D-043, replicated D-048)",
    "human_signoff_required": True,
    "automated_promotion_allowed": False,
}


def render_policy(policy: Mapping[str, Any] | None = None) -> str:
    active = dict(policy or DEFAULT_POLICY)
    return "\n".join([
        f"Promotion policy {active['version']}",
        f"  detector              {active['detector']} at {active['resolution_months']}-month resolution",
        f"  threshold             z >= {active['threshold']} (measured false-alarm rate "
        f"{active['false_alarm_rate']:.4f})",
        f"  rule                  {active['rule']}",
        f"  gates                 {'; '.join(REQUIRED_EVIDENCE)}",
        f"  automated promotion   {active['automated_promotion_allowed']}",
        "",
    ])


def main() -> int:
    import sys
    sys.stdout.write(render_policy())
    sys.stdout.write(json.dumps({"statement": STATEMENT}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
