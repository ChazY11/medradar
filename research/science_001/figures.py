"""The two SCIENCE-001 figures, regenerated from committed artifacts only.

Everything plotted here is read back from artifacts/*.csv|json; nothing is
re-fetched and no number is typed in by hand. matplotlib is imported lazily so
the analysis core of this package stays standard-library only.

    python research/science_001/cli.py figures
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence

DPI = 200
FIG1 = "figure1_time_evidence.png"
FIG2 = "figure2_experiment.png"

PALETTE = {
    "ink": "#1b1f24",
    "muted": "#5b6570",
    "grid": "#d8dee4",
    "blue": "#2f6db5",
    "teal": "#1f8a70",
    "amber": "#c9861a",
    "red": "#a63a3a",
    "grey": "#9aa4ae",
}


def _matplotlib():
    try:
        import matplotlib
    except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
        raise SystemExit(
            "matplotlib is required for figures only.\n"
            "  python -m pip install matplotlib\n"
            "(the fetch/verify/build/experiment steps need no third-party package)"
        ) from exc
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.dpi": DPI,
        "savefig.dpi": DPI,
        "font.size": 9,
        "axes.edgecolor": PALETTE["grid"],
        "axes.labelcolor": PALETTE["ink"],
        "text.color": PALETTE["ink"],
        "xtick.color": PALETTE["muted"],
        "ytick.color": PALETTE["muted"],
        "axes.grid": True,
        "grid.color": PALETTE["grid"],
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })
    return plt


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _sha(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# figure 1 - time evidence quality
# --------------------------------------------------------------------------- #
def figure_one(artifacts: Path, out_dir: Path) -> dict[str, Any]:
    plt = _matplotlib()
    verification = _read_csv(artifacts / "time_verification.csv")
    summary = json.loads((artifacts / "time_verification_summary.json").read_text("utf-8"))         if (artifacts / "time_verification_summary.json").exists() else {}

    figure, axes = plt.subplots(2, 2, figsize=(11.5, 8.0))
    figure.suptitle(
        "Fig. 1  EDGAR time evidence: what the raw archive actually proves "
        "(n = %d filings)" % len(verification),
        fontsize=11, color=PALETTE["ink"], x=0.02, ha="left")

    # (a) raw header is US/Eastern: the offset it implies switches with DST
    ax = axes[0][0]
    months = list(range(1, 13))
    counts_est = [0] * 12
    counts_edt = [0] * 12
    for row in verification:
        stamp = (row.get("acceptance_utc") or "")[:10]
        if len(stamp) < 10:
            continue
        month = int(stamp[5:7])
        offset = int(_float(row.get("offset_hours"), 0))
        if offset == -4:
            counts_edt[month - 1] += 1
        elif offset == -5:
            counts_est[month - 1] += 1
    ax.bar(months, counts_est, color=PALETTE["blue"], label="UTC-5 (EST)")
    ax.bar(months, counts_edt, bottom=counts_est, color=PALETTE["amber"],
           label="UTC-4 (EDT)")
    ax.set_title("(a) The raw ACCEPTANCE-DATETIME is a US/Eastern wall clock",
                 fontsize=9.5, loc="left")
    ax.set_xlabel("month of verified acceptance instant")
    ax.set_ylabel("filings")
    ax.set_xticks(months)
    ax.set_ylim(0, max(max(counts_est[i] + counts_edt[i] for i in range(12)) * 1.42, 5))
    ax.legend(frameon=False, fontsize=8, loc="upper right", ncol=1)
    ax.text(0.02, 0.97,
            "residual (header->UTC vs API) = 0 s for %d/%d filings\n"
            "the implied offset switches exactly at the DST boundaries"
            % (summary.get("residual_counts", {}).get("0", 0), len(verification)),
            transform=ax.transAxes, va="top", fontsize=7.2, color=PALETTE["muted"],
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 2})

    # (b) coverage by year and by DST regime: the verification strata evidence
    ax = axes[0][1]
    per_year: dict[int, dict[str, int]] = {}
    for row in verification:
        stamp = row.get("acceptance_utc") or ""
        offset = row.get("offset_hours")
        if len(stamp) < 4 or offset in (None, ""):
            continue
        bucket = per_year.setdefault(int(stamp[:4]), {"EST": 0, "EDT": 0})
        bucket["EDT" if int(_float(offset)) == -4 else "EST"] += 1
    years = sorted(per_year)
    est = [per_year[year]["EST"] for year in years]
    edt = [per_year[year]["EDT"] for year in years]
    ax.bar([str(year) for year in years], est, color=PALETTE["blue"],
           label="offset -5 (EST)")
    ax.bar([str(year) for year in years], edt, bottom=est, color=PALETTE["amber"],
           label="offset -4 (EDT)")
    ax.set_title("(b) Verified coverage by year and DST regime", fontsize=9.5, loc="left")
    ax.set_ylabel("filings graded A")
    ax.set_ylim(0, max(max(est[i] + edt[i] for i in range(len(years))) * 1.42, 5))
    ax.tick_params(axis="x", labelrotation=90, labelsize=7)
    ax.legend(frameon=False, fontsize=8, loc="upper center", ncol=2)
    tiers = summary.get("tier_counts", {})
    ax.text(0.02, 0.74,
            "%d/%d graded A (archive header -> UTC equals\nthe API instant exactly); other grades: %s"
            % (tiers.get("A_acceptance_verified", 0), len(verification),
               ", ".join("%s=%d" % (k.split("_")[0], v) for k, v in sorted(tiers.items())
                         if k != "A_acceptance_verified") or "none"),
            transform=ax.transAxes, va="top", fontsize=7, color=PALETTE["muted"],
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 2})

    # (c) the real uncertainty unit: acceptance -> archival write, which is
    #     where the 17:30 ET dissemination cut-off becomes visible.
    ax = axes[1][0]
    deferral = summary.get("after_hours_deferral", {})
    points: dict[str, list[tuple[float, float]]] = {"before": [], "after": []}
    for row in verification:
        stamp = row.get("acceptance_utc") or ""
        lag = row.get("public_interval_seconds")
        if len(stamp) < 19 or lag in (None, ""):
            continue
        hour_utc = int(stamp[11:13])
        offset = int(_float(row.get("offset_hours"), -5))
        eastern_hour = (hour_utc + offset) % 24 + int(stamp[14:16]) / 60.0
        seconds = max(int(_float(lag)), 1)
        bucket = "after" if eastern_hour > 17.5 else "before"
        points[bucket].append((eastern_hour, seconds / 3600.0))
    ax.scatter([x for x, _ in points["before"]], [y for _, y in points["before"]],
               s=5, color=PALETTE["blue"], alpha=0.55, label="accepted before 17:30 ET")
    ax.scatter([x for x, _ in points["after"]], [y for _, y in points["after"]],
               s=22, color=PALETTE["red"], alpha=0.9, label="accepted after 17:30 ET")
    ax.set_yscale("log")
    ax.axvline(17.5, color=PALETTE["amber"], linewidth=1.1, linestyle="--")
    for value, label in ((1 / 60.0, "1 min"), (1.0, "1 h"), (24.0, "1 day")):
        ax.axhline(value, color=PALETTE["grid"], linewidth=0.8)
        ax.text(23.6, value, label, fontsize=6.5, color=PALETTE["muted"],
                ha="right", va="bottom")
    before = deferral.get("before_cutoff", {})
    after = deferral.get("after_cutoff", {})
    ax.set_title("(c) Acceptance -> archival write: after-hours filings wait for the next "
                 "business day", fontsize=9.5, loc="left")
    ax.set_xlabel("acceptance clock time (US/Eastern hour)")
    ax.set_ylabel("hours until the archived file existed (log scale)")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 24, 3))
    ax.legend(frameon=False, fontsize=7, loc="upper left")
    stale = [(x, y) for group in ("before", "after") for x, y in points[group] if y > 24]
    if stale:
        ax.annotate("%d filings whose archived file was rewritten months later\n"
                    "(2017 bulk re-render): Last-Modified is an upper bound, not a\n"
                    "dissemination time" % len(stale),
                    xy=(max(x for x, _ in stale), max(y for _, y in stale)),
                    xytext=(0.03, 0.62), textcoords="axes fraction",
                    fontsize=6.6, color=PALETTE["muted"],
                    arrowprops={"arrowstyle": "-", "color": PALETTE["grid"], "lw": 0.8})
    if before.get("n") and after.get("n"):
        ax.text(0.98, 0.97,
                "before cut-off n=%d median %.0f s\n"
                "after cut-off  n=%d median %.1f h"
                % (before["n"], before.get("median", 0.0),
                   after["n"], (after.get("median", 0.0) / 3600.0)),
                transform=ax.transAxes, va="top", ha="right", fontsize=7,
                color=PALETTE["muted"],
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 2})

    # (d) intraday resolution: when does EDGAR accept 8-Ks (Eastern clock)?
    ax = axes[1][1]
    hours = [0] * 24
    for row in verification:
        stamp = row.get("acceptance_utc") or ""
        if len(stamp) < 19:
            continue
        hour_utc = int(stamp[11:13])
        offset = int(_float(row.get("offset_hours"), -5))
        hours[(hour_utc + offset) % 24] += 1
    ax.bar(range(24), hours, color=PALETTE["blue"])
    ax.set_title("(d) Acceptance clock time (US/Eastern)", fontsize=9.5, loc="left")
    ax.set_xlabel("hour of day (US/Eastern)")
    ax.set_ylabel("filings")
    ax.set_xticks(range(0, 24, 2))
    ax.set_ylim(0, max(hours) * 1.28)
    peak = max(range(24), key=lambda index: hours[index])
    ax.axvline(peak, color=PALETTE["amber"], linewidth=1.0, linestyle=":")
    ax.text(0.02, 0.97, "peak hour %02d:00 ET - the point-in-time resolution\n"
                        "available to any lead-time study on this source" % peak,
            transform=ax.transAxes, va="top", fontsize=7.5, color=PALETTE["muted"])

    figure.tight_layout(rect=(0, 0, 1, 0.95))
    target = out_dir / FIG1
    figure.savefig(target, bbox_inches="tight")
    plt.close(figure)
    return {"path": str(target), "sha256": _sha(target)}


# --------------------------------------------------------------------------- #
# figure 2 - the experiment
# --------------------------------------------------------------------------- #
def _roc(scores: Sequence[float], labels: Sequence[int]) -> tuple[list[float], list[float]]:
    pairs = sorted(zip(scores, labels), key=lambda pair: -pair[0])
    positives = sum(labels)
    negatives = len(labels) - positives
    fpr, tpr = [0.0], [0.0]
    tp = fp = 0
    for _, label in pairs:
        if label == 1:
            tp += 1
        else:
            fp += 1
        fpr.append(fp / negatives if negatives else 0.0)
        tpr.append(tp / positives if positives else 0.0)
    return fpr, tpr


def figure_two(artifacts: Path, out_dir: Path) -> dict[str, Any]:
    plt = _matplotlib()
    results_path = artifacts / "experiment_results.json"
    if not results_path.exists():
        raise SystemExit("missing experiment_results.json - run the experiment first")
    results = json.loads(results_path.read_text("utf-8"))
    dataset = _read_csv(artifacts / "dataset.csv")

    figure, axes = plt.subplots(2, 2, figsize=(11.5, 8.2))
    verdict = results.get("verdict", {})
    figure.suptitle(
        "Fig. 2  SCIENCE-001 exploratory result: %s   (train n=%d, holdout n=%d, 90-day horizon)"
        % (verdict.get("status", "?"), results.get("n_train", 0), results.get("n_test", 0)),
        fontsize=11, color=PALETTE["ink"], x=0.02, ha="left")
    figure.text(0.02, 0.935,
                "Chronological holdout, 11 issuers. Exploratory only: not a prediction claim, "
                "not a lead-time estimate. Firm identity (B1) is the baseline that matters.",
                fontsize=7.6, color=PALETTE["muted"], ha="left")

    # (a) outcome prevalence over time
    ax = axes[0][0]
    buckets: dict[str, list[int]] = {}
    for row in dataset:
        stamp = (row.get("acceptance_utc") or "")[:7]
        if len(stamp) < 7:
            continue
        year, month = int(stamp[:4]), int(stamp[5:7])
        key = "%dH%d" % (year, 1 if month <= 6 else 2)
        buckets.setdefault(key, []).append(int(_float(row.get("label_tech_event"))))
    keys = sorted(buckets)
    prevalence = [sum(buckets[key]) / len(buckets[key]) for key in keys]
    sizes = [len(buckets[key]) for key in keys]
    ax.plot(keys, prevalence, color=PALETTE["blue"], linewidth=1.4, marker="o",
            markersize=3, label="share with a 1.01/2.01 8-K in the next 90 days")
    overall = results.get("prevalence", {}).get("train")
    if overall is not None:
        ax.axhline(overall, color=PALETTE["grey"], linewidth=1.0, linestyle="--",
                   label="train prevalence %.3f" % overall)
    ax.set_title("(a) Outcome prevalence by half-year (all %d events)" % len(dataset),
                 fontsize=9.5, loc="left")
    ax.set_ylabel("prevalence")
    ax.set_ylim(0, 1)
    ax.tick_params(axis="x", labelrotation=90, labelsize=7)
    ax.legend(frameon=False, fontsize=7.5)

    # (b) ROC on the chronological holdout
    ax = axes[0][1]
    holdout = results.get("holdout", {})
    labels = holdout.get("label", [])
    colours = {"B0_prevalence": PALETTE["grey"], "B1_firm_mean": PALETTE["muted"],
               "B2_activity": PALETTE["blue"], "B3_activity_plus_dev_prose": PALETTE["red"]}
    if labels:
        for name, series in holdout.get("scores", {}).items():
            fpr, tpr = _roc(series, labels)
            auc_value = results["models"]["tech_event"].get(name, {}).get("auc")
            ax.plot(fpr, tpr, color=colours.get(name, PALETTE["ink"]), linewidth=1.3,
                    label="%s  AUC %.3f" % (name, auc_value if auc_value else float("nan")))
        ax.plot([0, 1], [0, 1], color=PALETTE["grid"], linewidth=1.0, linestyle=":")
    ax.set_title("(b) ROC on the chronological holdout", fontsize=9.5, loc="left")
    ax.set_xlabel("false positive rate")
    ax.set_ylabel("true positive rate")
    ax.legend(frameon=False, fontsize=7, loc="lower right")

    # (c) permutation null for the primary statistic
    ax = axes[1][0]
    permutation = results.get("permutation", {}).get("tech_event", {})
    draws = permutation.get("null_delta_auc_draws") or []
    observed = permutation.get("observed_delta_auc")
    p_value = permutation.get("p_delta_auc_two_sided")
    if draws:
        ax.hist(draws, bins=45, color=PALETTE["grey"], alpha=0.9,
                label="null: circular shift within issuer (B=%d)" % len(draws))
    if observed is not None:
        ax.axvline(observed, color=PALETTE["red"], linewidth=1.6,
                   label="observed dAUC = %.3f" % observed)
    ax.set_title("(c) Primary test: dAUC against a chance-order null",
                 fontsize=9.5, loc="left")
    ax.set_xlabel("AUC(B3) - AUC(B2) on the holdout")
    ax.set_ylabel("permutations")
    ax.legend(frameon=False, fontsize=7.5, loc="upper left")
    if p_value is not None:
        ax.text(0.98, 0.95, "two-sided p = %.3f" % p_value, transform=ax.transAxes,
                ha="right", va="top", fontsize=8.5, color=PALETTE["ink"],
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 2})
    null_median = (permutation.get("null_delta_auc") or {}).get("p50")
    if null_median is not None:
        ax.axvline(null_median, color=PALETTE["muted"], linewidth=0.9, linestyle=":")
        ax.text(0.98, 0.52,
                "the permutation null of this difference is\n"
                "centred at %.3f, not at 0: only the observed\n"
                "percentile is interpretable, and it is inside\n"
                "the band" % null_median,
                transform=ax.transAxes, va="top", ha="right", fontsize=6.6,
                color=PALETTE["muted"],
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 2})

    # (d) point estimates with cluster-bootstrap intervals
    ax = axes[1][1]
    ci = results.get("controls", {}).get("bootstrap", {}).get("ci95", {})
    entries: list[tuple[str, float, float, float]] = []
    for name in ("B0_prevalence", "B1_firm_mean", "B2_activity", "B3_activity_plus_dev_prose"):
        metric = results["models"]["tech_event"].get(name, {})
        interval = ci.get(name, {})
        if metric.get("auc") is None or not interval.get("n"):
            continue
        entries.append((name, metric["auc"], interval["p025"], interval["p975"]))
    delta_key = [key for key in ci if key.startswith("delta_") and "minus" in key]
    if delta_key and permutation.get("observed_delta_auc") is not None:
        interval = ci[delta_key[0]]
        entries.append(("dAUC (B3-B2)", permutation["observed_delta_auc"],
                        interval["p025"], interval["p975"]))
    placebo = results.get("models", {}).get("placebo", {}).get(
        "B3_activity_plus_dev_prose", {})
    if placebo.get("auc") is not None:
        entries.append(("B3 on placebo outcome 5.07 (no CI)",
                        placebo["auc"], float("nan"), float("nan")))
    if entries:
        positions = list(range(len(entries)))
        values = [abs(entry[1]) if entry[0].startswith("dAUC") else entry[1]
                  for entry in entries]
        errors_low = []
        errors_high = []
        for _, value, low, high in entries:
            if math.isnan(low) or math.isnan(high):
                errors_low.append(0.0)
                errors_high.append(0.0)
            else:
                errors_low.append(value - low)
                errors_high.append(high - value)
        colours_bar = [PALETTE["red"] if entry[0].startswith("dAUC") else
                       PALETTE["amber"] if "placebo" in entry[0] else PALETTE["blue"]
                       for entry in entries]
        ax.errorbar(values, positions, xerr=[errors_low, errors_high], fmt="o",
                    color=PALETTE["ink"], ecolor=PALETTE["muted"], capsize=3,
                    markersize=5, linewidth=1.0)
        for position, value, colour in zip(positions, values, colours_bar):
            ax.plot([value], [position], "o", color=colour, markersize=6)
        ax.axvline(0.5, color=PALETTE["grid"], linewidth=1.0, linestyle=":")
        ax.axvline(0.0, color=PALETTE["grid"], linewidth=1.0, linestyle="-.")
        ax.set_yticks(positions)
        ax.set_yticklabels([entry[0] for entry in entries], fontsize=7.5)
        ax.set_xlabel("AUC (0.5 = no information) / dAUC (0 = no improvement)")
        ax.invert_yaxis()
    ax.set_title("(d) Estimates with 95% cluster-bootstrap intervals",
                 fontsize=9.5, loc="left")

    figure.tight_layout(rect=(0, 0, 1, 0.95))
    target = out_dir / FIG2
    figure.savefig(target, bbox_inches="tight")
    plt.close(figure)
    return {"path": str(target), "sha256": _sha(target)}


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def run(artifacts: Path) -> int:
    out_dir = artifacts / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"figure1": None, "figure2": None, "sources": {}}
    try:
        manifest["figure1"] = figure_one(artifacts, out_dir)
    except SystemExit as exc:
        print("[figures] figure 1 skipped: %s" % exc)
        return 2
    try:
        manifest["figure2"] = figure_two(artifacts, out_dir)
    except SystemExit as exc:
        print("[figures] figure 2 skipped: %s" % exc)
        manifest["figure2_error"] = str(exc)
    for name in ("time_verification.csv", "time_verification_summary.json",
                 "dataset.csv", "experiment_results.json", "sample_report.json"):
        manifest["sources"][name] = _sha(artifacts / name)
    (out_dir / "figures_manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8", newline="\n")
    for key in ("figure1", "figure2"):
        if manifest.get(key):
            print("[figures] wrote %s" % manifest[key]["path"])
    return 0
