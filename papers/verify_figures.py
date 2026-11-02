"""Verify the paper's figures: valid SVG, values re-derived from the source artifacts, paper links.

Three checks per figure:
  1. the SVG parses as XML and contains no NaN/inf coordinates;
  2. the values recorded in figures/figures_data.json are re-derived here from the source artifact and
     must match exactly;
  3. the paper links the figure file.

    python papers/verify_figures.py [--paper papers/PAPER_v1.md]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path

FIGURES = Path("papers/figures")

DETECTORS = ("naive_multiplier", "poisson_cusum", "poisson_bayes_factor", "rolling_zscore")


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def expected_frontier() -> list[dict]:
    benchmark = load("experiments/detect_v1/benchmark.json")
    levels = benchmark["levels"]["track"]["frontier_readout"]
    rows = []
    for key in sorted(levels, key=float):
        for detector in DETECTORS:
            entry = levels[key].get(detector)
            if not entry:
                continue
            rows.append({"far_target": float(key), "detector": detector,
                         "false_alarm_rate": entry["false_alarm_rate"],
                         "sensitivity": entry["detection_probability"],
                         "ci": entry["detection_probability_ci"]})
    return rows


def expected_calibration() -> list[dict]:
    calibration = load("experiments/b027/momentum_calibration.json")
    return [{"company": row["company"], "ratio": row["ratio"], "p": row["p"],
             "detected": bool(row["detected"])}
            for row in calibration["rows"] if row.get("ratio")]


def expected_rolling() -> list[dict]:
    rolling = load("experiments/b050/rolling_origin.json")
    predictors = rolling["predictors"]
    names = sorted((name for name in predictors if predictors[name].get("lift") is not None),
                   key=lambda name: predictors[name]["lift"])
    return [{"predictor": name, "lift": predictors[name]["lift"],
             "ci": predictors[name]["lift_ci"], "flags": predictors[name]["flagged"]}
            for name in names]


def expected_stability() -> list[dict]:
    stability = load("experiments/b027/verdict_stability.json")
    detail = stability["detail"]
    return [{"company": company, "sequence": detail[company]["sequence"],
             "reversed": bool(detail[company]["reversed"])} for company in sorted(detail)]


EXPECTED = {
    "fig1_frontier": expected_frontier,
    "fig2_calibration": expected_calibration,
    "fig3_rolling_origin": expected_rolling,
    "fig4_verdict_stability": expected_stability,
}


def check_svg(path: Path) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    # numeric artefacts only: 'inf' appears inside ordinary words such as "information"
    for token in (r"(?<![A-Za-z])NaN(?![A-Za-z])", r"(?<![A-Za-z])(?:-?inf)(?![A-Za-z])",
                  r"(?<![A-Za-z])None(?![A-Za-z])"):
        if re.search(token, text):
            problems.append(f"SVG contains a non-numeric artefact matching {token}")
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        return problems + [f"SVG does not parse: {exc}"]
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        problems.append(f"unexpected root element {root.tag}")
    circles = sum(1 for _ in root.iter("{http://www.w3.org/2000/svg}circle"))
    rects = sum(1 for _ in root.iter("{http://www.w3.org/2000/svg}rect"))
    lines = sum(1 for _ in root.iter("{http://www.w3.org/2000/svg}line"))
    if circles + rects + lines < 10:
        problems.append("SVG has too few drawn elements to be a figure")
    return problems


def coords_valid(value: float) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper", default="papers/PAPER_v1.md")
    args = parser.parse_args(argv)

    payload = load(str(FIGURES / "figures_data.json"))
    paper = Path(args.paper).read_text(encoding="utf-8")
    failures: list[str] = []
    for name, builder in EXPECTED.items():
        svg_path = FIGURES / f"{name}.svg"
        if not svg_path.exists():
            failures.append(f"{name}: missing {svg_path}")
            continue
        failures.extend(f"{name}: {problem}" for problem in check_svg(svg_path))
        expected = builder()
        recorded = payload["figures"][name]["data"]
        if len(expected) != len(recorded):
            failures.append(f"{name}: {len(expected)} expected points vs {len(recorded)} recorded")
            continue
        for index, (want, got) in enumerate(zip(expected, recorded)):
            if json.dumps(want, sort_keys=True) != json.dumps(got, sort_keys=True):
                failures.append(f"{name}: point {index} differs from source artifact")
                break
        if name not in paper:
            failures.append(f"{name}: figure not referenced in the paper")
        if f"{name}.svg" not in paper:
            failures.append(f"{name}: paper does not link the SVG file")
        print(f"{name}: {len(recorded)} points re-derived from source, SVG valid")
    print(f"\nfigures checked: {len(EXPECTED)}; failures: {len(failures)}")
    for failure in failures:
        print(f"  - {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
