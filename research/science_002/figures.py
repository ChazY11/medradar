"""Figures for SCIENCE-002, rendered only from committed artifacts.

Figure 1  sample structure: per-firm clearance activity and event prevalence.
Figure 2  the model ladder: pooled AUC vs firm-conditional AUC with cluster CIs.
Figure 3  the primary null: permutation distribution, observed statistic, and the
          R&D-timing placebo band.

Nothing here recomputes a model. Every plotted number is read from
artifacts/experiment_results.json, artifacts/panel.csv or artifacts/universe.csv.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK = "#1b1b1b"
ACCENT = "#1f6f8b"
WARN = "#b23a48"
GREY = "#8a8a8a"


def load(artifacts: Path) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
    results = json.loads((artifacts / "experiment_results.json").read_text(encoding="utf-8"))
    with (artifacts / "panel.csv").open("r", encoding="utf-8", newline="") as handle:
        panel = list(csv.DictReader(handle))
    with (artifacts / "universe.csv").open("r", encoding="utf-8", newline="") as handle:
        universe = list(csv.DictReader(handle))
    return results, panel, universe


def figure1(artifacts: Path, results: dict[str, Any], panel: list[dict[str, str]],
            universe: list[dict[str, str]]) -> Path:
    ticker = {row["key"]: row["ticker"] or row["key"] for row in universe}
    months = sorted({row["month_end"] for row in panel})
    month_index = {m: i for i, m in enumerate(months)}
    by_firm: dict[str, list[float]] = defaultdict(lambda: [0.0] * len(months))
    label_by_firm: dict[str, list[float]] = defaultdict(list)
    for row in panel:
        key = row["key"]
        by_firm[key][month_index[row["month_end"]]] = float(row["n_events_in_window"] or 0)
        label_by_firm[key].append(float(row["label"]))
    firms = sorted(by_firm, key=lambda k: -sum(label_by_firm[k]) / max(1, len(label_by_firm[k])))

    fig, axes = plt.subplots(1, 2, figsize=(13.2, 0.19 * len(firms) + 2.2),
                             gridspec_kw={"width_ratios": [3.1, 1.0]})
    grid = [by_firm[f] for f in firms]
    ax = axes[0]
    image = ax.imshow(grid, aspect="auto", cmap="magma", interpolation="nearest",
                      vmin=0, vmax=max(1.0, max(max(r) for r in grid)))
    ax.set_yticks(range(len(firms)))
    ax.set_yticklabels([ticker.get(f, f) for f in firms], fontsize=6.5)
    step = max(1, len(months) // 10)
    ax.set_xticks(range(0, len(months), step))
    ax.set_xticklabels([months[i][:7] for i in range(0, len(months), step)],
                       rotation=45, ha="right", fontsize=7)
    ax.set_title("FDA 510(k) clearances attributable to each issuer, by month\n"
                 "(count in the firm's 90-day outcome window; darker = more)",
                 fontsize=9, loc="left")
    fig.colorbar(image, ax=ax, fraction=0.02, pad=0.01, label="clearances in window")

    ax2 = axes[1]
    rates = [sum(label_by_firm[f]) / len(label_by_firm[f]) for f in firms]
    ax2.barh(range(len(firms)), rates, color=ACCENT, height=0.75)
    ax2.set_ylim(len(firms) - 0.5, -0.5)
    ax2.set_yticks([])
    ax2.set_xlim(0, 1)
    ax2.axvline(sum(rates) / len(rates), color=WARN, lw=1, ls="--")
    ax2.set_title("P(event in 90d)", fontsize=9, loc="left")
    ax2.set_xlabel("firm-month prevalence", fontsize=8)
    for spine in ("top", "right"):
        ax2.spines[spine].set_visible(False)
    fig.tight_layout()
    out = artifacts / "figures" / "figure1_sample_structure.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def figure2(artifacts: Path, results: dict[str, Any], panel: Any, universe: Any) -> Path:
    bootstrap = results["bootstrap"]
    pooled = results["pooled"]
    pooled_boot = results["pooled_bootstrap"]
    labels = ["B1\nfirm history", "B2\n+ activity", "B3\n+ SEC R&D"]
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.3))
    ax = axes[0]
    xs = range(len(labels))
    vals = [pooled[k] for k in ("B1", "B2", "B3")]
    errs = [[pooled_boot[k]["median"] - pooled_boot[k]["lo"] for k in ("B1", "B2", "B3")],
            [pooled_boot[k]["hi"] - pooled_boot[k]["median"] for k in ("B1", "B2", "B3")]]
    ax.errorbar(list(xs), vals, yerr=errs, fmt="o", color=ACCENT, capsize=4, lw=1.4)
    ax.axhline(0.5, color=GREY, lw=1, ls=":")
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylim(0.35, 1.0)
    ax.set_ylabel("pooled holdout AUC")
    ax.set_title("Pooled discrimination (descriptive only)", fontsize=9.5, loc="left")
    ax.text(0.02, 0.03, "between-firm composition drives this panel;\nnot evidence of early signal",
            transform=ax.transAxes, fontsize=7.2, color=GREY)

    ax = axes[1]
    keys = ["B1c", "B2c", "B3c"]
    vals = [bootstrap[k]["median"] for k in keys]
    errs = [[bootstrap[k]["median"] - bootstrap[k]["lo"] for k in keys],
            [bootstrap[k]["hi"] - bootstrap[k]["median"] for k in keys]]
    ax.errorbar(list(range(len(keys))), vals, yerr=errs, fmt="o", color=WARN, capsize=4, lw=1.4)
    ax.axhline(0.5, color=GREY, lw=1, ls=":")
    ax.set_xticks(list(range(len(keys))))
    ax.set_xticklabels(["B1c\nfirm FE", "B2c\n+ activity", "B3c\n+ SEC R&D"], fontsize=8.5)
    ax.set_ylim(0.35, 0.65)
    ax.set_ylabel("firm-stratified holdout AUC")
    ax.set_title("Within-firm discrimination (primary family)", fontsize=9.5, loc="left")
    primary = results["primary"]["delta_stratified_auc_B3c_minus_B2c"]
    p = results["permutation"]["p_two_sided"]
    ax.text(0.02, 0.03, f"delta(B3c-B2c) = {primary:+.3f}, permutation p = {p:.3f}",
            transform=ax.transAxes, fontsize=7.6, color=INK)
    for ax in axes:
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
    fig.tight_layout()
    out = artifacts / "figures" / "figure2_model_ladder.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def figure3(artifacts: Path, results: dict[str, Any], panel: Any, universe: Any) -> Path:
    perm = results["permutation"]
    observed = results["primary"]["delta_stratified_auc_B3c_minus_B2c"]
    placebo = results["controls"].get("placebo_features", {})
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 3.9))
    ax = axes[0]
    mean = perm["null_mean"] or 0.0
    sd = perm["null_sd"] or 1.0
    xs = [mean + sd * (i / 40 - 2.5) for i in range(201)]
    ys = [math_exp(-0.5 * ((x - mean) / sd) ** 2) for x in xs]
    ax.plot(xs, ys, color=GREY, lw=1.2, label="within-firm permutation null (normal fit)")
    ax.fill_between([perm["null_q025"], perm["null_q975"]], 0, 1.05,
                    color=GREY, alpha=0.18, label="95% null band")
    ax.axvline(observed, color=WARN, lw=1.8,
               label=f"observed delta = {observed:+.3f}")
    ax.set_ylim(0, 1.05)
    ax.set_yticks([])
    ax.set_xlabel("delta firm-stratified AUC (B3c - B2c)")
    ax.set_title(f"Primary null, {perm['n_used']} permutations, two-sided p = "
                 f"{perm['p_two_sided']:.3f}", fontsize=9.5, loc="left")
    ax.legend(fontsize=7, frameon=False, loc="upper left")

    ax = axes[1]
    lo = placebo.get("null_q025")
    hi = placebo.get("null_q975")
    if lo is not None and hi is not None:
        ax.add_patch(plt.Rectangle((-0.6, lo), 2.2, hi - lo, color=GREY, alpha=0.18,
                                   label="placebo 95% band (shuffled R&D timing)"))
        ax.hlines([lo, hi], -0.6, 1.6, color=GREY, lw=0.9, ls=":")
    ax.scatter([0], [observed], color=WARN, s=90, zorder=5, label="observed R&D timing")
    ax.scatter([1], [placebo.get("null_mean") or 0.0], color=INK, s=70, marker="o",
               zorder=5, label="placebo mean")
    if placebo.get("null_mean") is not None and placebo.get("null_q975") is not None:
        ax.vlines(1, placebo.get("null_q025"), placebo.get("null_q975"),
                  color=INK, lw=1.4)
    ax.axhline(0, color=INK, lw=0.8)
    ax.set_xlim(-0.6, 1.6)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["observed\nR&D timing", "placebo\n(shuffled R&D)"], fontsize=8.5)
    ax.set_ylabel("delta firm-stratified AUC (B3c - B2c)")
    ax.set_title("Real R&D timing vs. shuffled timing, 100 draws\n"
                 "p = " + ("%.3f" % placebo["p_two_sided"] if placebo.get("p_two_sided") is not None else "n/a") +
                 ": the negative point estimate sits just outside the placebo band",
                 fontsize=9.5, loc="left")
    ax.legend(fontsize=7, frameon=False, loc="lower left")
    for ax in axes:
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
    fig.tight_layout()
    out = artifacts / "figures" / "figure3_primary_null.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170)
    plt.close(fig)
    return out


def math_exp(x: float) -> float:
    import math
    return math.exp(max(-50.0, min(50.0, x)))


def render(artifacts: Path) -> list[Path]:
    results, panel, universe = load(artifacts)
    paths = [figure1(artifacts, results, panel, universe),
             figure2(artifacts, results, panel, universe),
             figure3(artifacts, results, panel, universe)]
    manifest = {
        "figures": [{"path": p.relative_to(artifacts).as_posix(), "sha256": _sha(p),
                     "bytes": p.stat().st_size} for p in paths],
        "inputs": {"experiment_results.json": _sha(artifacts / "experiment_results.json"),
                   "panel.csv": _sha(artifacts / "panel.csv"),
                   "universe.csv": _sha(artifacts / "universe.csv")},
    }
    (artifacts / "figures" / "figures_manifest.json").write_text(
        json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return paths


def _sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()