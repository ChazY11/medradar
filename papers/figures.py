"""Generate the paper's figures as SVG from committed artifacts, with no third-party libraries.

The repository is stdlib-only by policy (`dependencies = []`), so figures are written directly as SVG.
Each figure is derived from an artifact and its plotted values are also dumped to
`papers/figures/figures_data.json`, so `papers/verify_figures.py` can re-derive them and compare.

Figures:
  fig1_frontier.svg          detection sensitivity vs false-alarm rate, four detectors (cycle 3)
  fig2_calibration.svg       rate ratio vs exact p-value across 53 companies, detected marked (cycle 14)
  fig3_rolling_origin.svg    rolling-origin lift with company-clustered CIs (cycle 15)
  fig4_verdict_stability.svg verdict per company across four as-of dates (cycle 16)

    python papers/figures.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Sequence

OUT = Path("papers/figures")
W, H = 760, 460
MARGIN = {"left": 78, "right": 24, "top": 44, "bottom": 62}

DETECTORS = ("naive_multiplier", "poisson_cusum", "poisson_bayes_factor", "rolling_zscore")
DETECTOR_LABELS = {"naive_multiplier": "naive rate multiplier", "poisson_cusum": "Poisson CUSUM",
                   "poisson_bayes_factor": "Poisson Bayes factor", "rolling_zscore": "rolling z-score"}
COLOURS = {"naive_multiplier": "#1f4e79", "poisson_cusum": "#c0392b",
           "poisson_bayes_factor": "#2e7d32", "rolling_zscore": "#8e44ad"}
VERDICT_COLOURS = {"increasing": "#2e7d32", "decreasing": "#c0392b",
                   "no_detectable_change": "#bdbdbd", "estimated": "#f1c40f",
                   "insufficient_window": "#ffffff"}


def esc(text: Any) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def svg_open(title: str, subtitle: str = "") -> list[str]:
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}" font-family="Helvetica, Arial, sans-serif">',
             f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
             f'<text x="{MARGIN["left"]}" y="22" font-size="15" font-weight="bold">{esc(title)}</text>']
    if subtitle:
        lines.append(f'<text x="{MARGIN["left"]}" y="38" font-size="11" fill="#555">'
                     f'{esc(subtitle)}</text>')
    return lines


def svg_close(lines: list[str]) -> str:
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def plot_area(left: float | None = None,
              top: float | None = None) -> tuple[float, float, float, float]:
    left_margin = MARGIN["left"] if left is None else left
    top_margin = MARGIN["top"] if top is None else top
    return (left_margin, top_margin,
            W - left_margin - MARGIN["right"], H - top_margin - MARGIN["bottom"])


def axes(lines: list[str], x_label: str, y_label: str,
         left: float | None = None, top: float | None = None) -> tuple[float, float, float, float]:
    x0, y0, width, height = plot_area(left, top)
    lines.append(f'<rect x="{x0}" y="{y0}" width="{width}" height="{height}" fill="none" '
                 f'stroke="#333" stroke-width="1"/>')
    lines.append(f'<text x="{x0 + width / 2}" y="{y0 + height + 38}" font-size="12" '
                 f'text-anchor="middle">{esc(x_label)}</text>')
    if y_label:
        lines.append(f'<text x="20" y="{y0 + height / 2}" font-size="12" text-anchor="middle" '
                     f'transform="rotate(-90 20 {y0 + height / 2})">{esc(y_label)}</text>')
    return x0, y0, width, height


def line(lines: list[str], x1: float, y1: float, x2: float, y2: float, *,
         colour: str = "#333", width: float = 1.0, dash: str | None = None) -> None:
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    lines.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                 f'stroke="{colour}" stroke-width="{width}"{extra}/>')


def circle(lines: list[str], x: float, y: float, radius: float = 3.5, *,
           colour: str = "#1f4e79", fill: str | None = None) -> None:
    lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" stroke="{colour}" '
                 f'stroke-width="1.2" fill="{fill or colour}"/>')


def label(lines: list[str], x: float, y: float, text: Any, *, size: float = 10,
          anchor: str = "start", colour: str = "#333", weight: str = "normal") -> None:
    lines.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
                 f'fill="{colour}" font-weight="{weight}">{esc(text)}</text>')


# ------------------------------------------------------------------ figure 1
def figure_frontier(benchmark: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    levels = benchmark["levels"]["track"]["frontier_readout"]
    fars = sorted(float(key) for key in levels)
    plotted: list[dict[str, Any]] = []
    max_sensitivity = 0.0
    for far in fars:
        block = levels[f"{far}"]
        for detector in DETECTORS:
            entry = block.get(detector)
            if not entry:
                continue
            plotted.append({"far_target": far, "false_alarm_rate": entry["false_alarm_rate"],
                            "detector": detector,
                            "sensitivity": entry["detection_probability"],
                            "ci": entry["detection_probability_ci"]})
            max_sensitivity = max(max_sensitivity, entry["detection_probability_ci"][1])

    lines = svg_open("Figure 1. Detection sensitivity at a controlled false-alarm rate",
                     "track-level panels, paired common-random-number injections, "
                     "entity-clustered CIs (cycle 3)")
    x0, y0, width, height = axes(lines, "false-alarm rate", "sensitivity (detection probability)")
    x_max = max(plot["false_alarm_rate"] for plot in plotted) or 0.05
    y_max = math.ceil((max_sensitivity + 0.02) * 10) / 10

    for tick in range(0, 6):
        value = x_max * tick / 5
        x = x0 + width * (value / x_max)
        line(lines, x, y0, x, y0 + height, colour="#e5e5e5")
        label(lines, x, y0 + height + 16, f"{value:.3f}", size=9, anchor="middle", colour="#555")
    for tick in range(0, 6):
        value = y_max * tick / 5
        y = y0 + height * (1 - value / y_max)
        line(lines, x0, y, x0 + width, y, colour="#e5e5e5")
        label(lines, x0 - 8, y + 3, f"{value:.2f}", size=9, anchor="end", colour="#555")

    for detector in DETECTORS:
        series = sorted((plot for plot in plotted if plot["detector"] == detector),
                        key=lambda plot: plot["far_target"])
        colour = COLOURS[detector]
        previous = None
        for plot in series:
            x = x0 + width * (plot["far_target"] / x_max)
            y = y0 + height * (1 - plot["sensitivity"] / y_max)
            low, high = plot["ci"]
            y_low = y0 + height * (1 - low / y_max)
            y_high = y0 + height * (1 - high / y_max)
            line(lines, x, y_low, x, y_high, colour=colour, width=1.4)
            line(lines, x - 4, y_low, x + 4, y_low, colour=colour, width=1.4)
            line(lines, x - 4, y_high, x + 4, y_high, colour=colour, width=1.4)
            if previous is not None:
                line(lines, previous[0], previous[1], x, y, colour=colour, width=1.6)
            circle(lines, x, y, colour=colour)
            previous = (x, y)
        legend_y = MARGIN["top"] + 12 + 16 * DETECTORS.index(detector)
        circle(lines, W - MARGIN["right"] - 150, legend_y, 3.5, colour=colour)
        label(lines, W - MARGIN["right"] - 140, legend_y + 3.5, DETECTOR_LABELS[detector], size=10)
    label(lines, x0 + 6, y0 + 14, f"n = {benchmark['levels']['track']['bins']} bins per series",
          size=9, colour="#777")
    return svg_close(lines), plotted


# ------------------------------------------------------------------ figure 2
def figure_calibration(calibration: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    rows = [row for row in calibration["rows"] if row.get("ratio")]
    plotted = [{"company": row["company"], "ratio": row["ratio"], "p": row["p"],
                "detected": bool(row["detected"])} for row in rows]
    lines = svg_open("Figure 2. A ratio is not evidence: rate ratio against exact p-value",
                     f"{len(rows)} companies; two-sided exact binomial test at alpha = 0.05 (cycle 14)")
    x0, y0, width, height = axes(lines, "recent / prior rate ratio (log scale)",
                                 "exact two-sided p-value (log scale)")
    ratios = [plot["ratio"] for plot in plotted]
    x_min, x_max = min(ratios) * 0.8, max(ratios) * 1.25
    y_min, y_max = 1e-5, 1.0

    def sx(value: float) -> float:
        return x0 + width * (math.log10(value) - math.log10(x_min)) / (
            math.log10(x_max) - math.log10(x_min))

    def sy(value: float) -> float:
        value = max(min(value, y_max), y_min)
        return y0 + height * (math.log10(y_max) - math.log10(value)) / (
            math.log10(y_max) - math.log10(y_min))

    for value in (0.5, 1.0, 2.0, 4.0):
        if x_min <= value <= x_max:
            x = sx(value)
            line(lines, x, y0, x, y0 + height, colour="#eeeeee")
            label(lines, x, y0 + height + 16, f"{value:g}x", size=9, anchor="middle", colour="#555")
    for value in (0.001, 0.01, 0.05, 0.5):
        y = sy(value)
        line(lines, x0, y, x0 + width, y, colour="#eeeeee")
        label(lines, x0 - 8, y + 3, f"{value:g}", size=9, anchor="end", colour="#555")
    threshold = sy(0.05)
    line(lines, x0, threshold, x0 + width, threshold, colour="#c0392b", width=1.4, dash="5,4")
    label(lines, x0 + width - 6, threshold - 6, "alpha = 0.05", size=9, anchor="end", colour="#c0392b")

    for plot in plotted:
        colour = "#c0392b" if plot["detected"] else "#95a5a6"
        circle(lines, sx(plot["ratio"]), sy(plot["p"]), 3.6 if plot["detected"] else 3.0,
               colour=colour, fill=colour)
    for plot in sorted(plotted, key=lambda row: row["p"])[:4]:
        x = sx(plot["ratio"])
        text = f"{plot['company']} ({plot['ratio']:.2f}x)"
        if x > x0 + width * 0.72:      # keep the label inside the frame
            label(lines, x - 7, sy(plot["p"]) - 5, text, size=9, anchor="end", colour="#c0392b")
        else:
            label(lines, x + 7, sy(plot["p"]) - 5, text, size=9, colour="#c0392b")
    label(lines, x0 + 8, y0 + height - 10,
          f"{sum(1 for plot in plotted if plot['detected'])} of {len(plotted)} below alpha; "
          "grey markers pass the ratio rule but not the test", size=9, colour="#555")
    return svg_close(lines), plotted


# ------------------------------------------------------------------ figure 3
def figure_rolling(lag: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    predictors = lag["predictors"]
    names = [name for name in predictors if predictors[name].get("lift") is not None]
    names.sort(key=lambda name: predictors[name]["lift"])
    plotted = [{"predictor": name, "lift": predictors[name]["lift"],
                "ci": predictors[name]["lift_ci"], "flags": predictors[name]["flagged"]}
               for name in names]
    lines = svg_open("Figure 3. Rolling-origin lift with company-clustered 95 % intervals",
                     "pre-registered (vs recent) and corrected (vs long-run baseline) outcomes; "
                     "1.0 means no information (cycle 15)")
    x0, y0, width, height = axes(lines, "lift (precision with flag / precision without)", "",
                                 left=268, top=68)
    max_lift = max(max(plot["ci"][1] or 0, plot["lift"] or 0) for plot in plotted) * 1.1
    min_lift = 0.0

    def sx(value: float) -> float:
        return x0 + width * (value - min_lift) / (max_lift - min_lift)

    step = height / max(len(plotted), 1)
    for index, plot in enumerate(plotted):
        y = y0 + step * (index + 0.5)
        low, high = plot["ci"]
        colour = "#c0392b" if "vs_recent" in plot["predictor"] else "#1f4e79"
        if low is not None and high is not None:
            line(lines, sx(low), y, sx(high), y, colour=colour, width=1.6)
            for bound in (low, high):
                line(lines, sx(bound), y - 4, sx(bound), y + 4, colour=colour, width=1.6)
        circle(lines, sx(plot["lift"]), y, 3.4, colour=colour)
        label(lines, x0 - 8, y + 3,
              f"{plot['predictor'].replace('_', ' ')} (n={plot['flags']})",
              size=8.5, anchor="end", colour="#333")
        label(lines, sx(plot["lift"]) + 7, y + 3, f"{plot['lift']:.2f}", size=8.5, colour="#333")
    unity = sx(1.0)
    line(lines, unity, y0, unity, y0 + height, colour="#333", width=1.2, dash="4,4")
    label(lines, unity + 5, y0 + height - 8, "no information (lift = 1)", size=9, colour="#333")
    label(lines, x0 + 6, y0 - 8, f"{len(plotted)} predictor/outcome pairs; n = flagged cells",
          size=9, colour="#777")
    return svg_close(lines), plotted


# ------------------------------------------------------------------ figure 4
def figure_stability(stability: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    detail = stability["detail"]
    dates = stability["as_of_dates"]
    companies = sorted(detail)
    plotted = [{"company": company, "sequence": detail[company]["sequence"],
                "reversed": bool(detail[company]["reversed"])} for company in companies]
    lines = svg_open("Figure 4. Nowcast verdict per company across four as-of dates",
                     "40 stable, 13 changed, 2 reversed of 53 companies (cycle 16)")
    x0, y0, width, height = axes(lines, "as-of date", "", left=196, top=56)
    lines.pop()           # drop the empty y-axis title placeholder
    column_width = width / len(dates)
    row_height = height / len(companies)
    for column, date in enumerate(dates):
        label(lines, x0 + column_width * (column + 0.5), y0 + height + 16, date, size=9,
              anchor="middle", colour="#555")
    for row, row_data in enumerate(plotted):
        for column, verdict in enumerate(row_data["sequence"]):
            colour = VERDICT_COLOURS.get(verdict, "#ffffff")
            lines.append(f'<rect x="{x0 + column_width * column:.1f}" '
                         f'y="{y0 + row_height * row:.1f}" width="{column_width:.1f}" '
                         f'height="{row_height + 0.4:.1f}" fill="{colour}" stroke="#ffffff" '
                         f'stroke-width="0.5"/>')
        if row % 6 == 0:
            label(lines, x0 - 6, y0 + row_height * (row + 0.75), row_data["company"], size=8.5,
                  anchor="end", colour="#333")
        if row_data["reversed"]:
            label(lines, x0 - 100, y0 + row_height * (row + 0.75), "reversed", size=8,
                  anchor="end", colour="#c0392b", weight="bold")
    for legend_index, (verdict, colour) in enumerate(VERDICT_COLOURS.items()):
        y = MARGIN["top"] + 10 + 15 * legend_index
        lines.append(f'<rect x="{W - MARGIN["right"] - 156}" y="{y - 8}" width="12" height="10" '
                     f'fill="{colour}" stroke="#999" stroke-width="0.5"/>')
        label(lines, W - MARGIN["right"] - 138, y, verdict.replace("_", " "), size=9)
    label(lines, x0 + 4, y0 + height + 54,
          "rows are companies, sorted alphabetically; a colour change down a column means the "
          "verdict moved with the evaluation date", size=9, colour="#555")
    return svg_close(lines), plotted


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    benchmark = json.loads(Path("experiments/detect_v1/benchmark.json").read_text(encoding="utf-8"))
    calibration = json.loads(Path("experiments/b027/momentum_calibration.json").read_text(
        encoding="utf-8"))
    rolling = json.loads(Path("experiments/b050/rolling_origin.json").read_text(encoding="utf-8"))
    stability = json.loads(Path("experiments/b027/verdict_stability.json").read_text(
        encoding="utf-8"))

    figures = {}
    for name, (markup, data) in (
        ("fig1_frontier", figure_frontier(benchmark)),
        ("fig2_calibration", figure_calibration(calibration)),
        ("fig3_rolling_origin", figure_rolling(rolling)),
        ("fig4_verdict_stability", figure_stability(stability)),
    ):
        path = OUT / f"{name}.svg"
        path.write_text(markup, encoding="utf-8", newline="\n")
        figures[name] = {"svg": str(path), "points": len(data), "data": data}
        print(f"wrote {path} ({len(markup)} bytes, {len(data)} plotted points)")

    payload = {
        "schema": "figures_v1",
        "sources": {
            "fig1_frontier": "experiments/detect_v1/benchmark.json",
            "fig2_calibration": "experiments/b027/momentum_calibration.json",
            "fig3_rolling_origin": "experiments/b050/rolling_origin.json",
            "fig4_verdict_stability": "experiments/b027/verdict_stability.json",
        },
        "figures": figures,
    }
    (OUT / "figures_data.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT / 'figures_data.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
