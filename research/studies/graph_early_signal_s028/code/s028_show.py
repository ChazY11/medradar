"""Print the S-028 result tables from the stored artifacts."""
import json
from pathlib import Path

ART = Path(__file__).resolve().parents[1] / "artifacts"


def show(label: str) -> None:
    path = ART / f"experiment_{label}.json"
    if not path.exists():
        print(f"{label}: artifact missing")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    print("=" * 78)
    print(f"{label}  horizon={data['horizon_months']}m  rows={data['panel']['n_examples']} "
          f"positives={data['panel']['n_positives']} base_rate={data['panel']['base_rate']:.5f}")
    print("holdouts:", data["panel"]["holdouts"])
    print(f"positives_by_origin: {data['panel']['positives_by_origin']}")
    print("\n-- B0 persistence (pooled) --")
    for name, value in data["b0"].items():
        pooled = value["pooled"]
        print(f"  {name:32s} AP={_fmt(pooled.get('pr_auc'))} ROC={_fmt(pooled.get('roc_auc'))} "
              f"Brier={_fmt(pooled.get('brier'))} P@K={_fmt(pooled.get('precision_at_k'))}")
    print("\n-- specs (pooled) --")
    rows = []
    for name, value in data["specs"].items():
        if "summary" not in value:
            continue
        pooled = value["summary"]["pooled"]
        rows.append((name, value["summary"].get("n_features"), pooled))
        print(f"  {name:22s} d={value['summary'].get('n_features')!s:>2s} AP={_fmt(pooled.get('pr_auc'))} "
              f"ROC={_fmt(pooled.get('roc_auc'))} Brier={_fmt(pooled.get('brier'))} "
              f"ECE={_fmt(pooled.get('ece'))} P@K={_fmt(pooled.get('precision_at_k'))} "
              f"R@K={_fmt(pooled.get('recall_at_k'))}")
    print("\n-- per-window AP --")
    windows = data["panel"]["holdouts"]
    print("  spec".ljust(24) + "".join(f"{w:>14s}" for w in windows))
    for name, value in data["specs"].items():
        if "summary" not in value:
            continue
        cells = []
        for w in windows:
            cells.append(_fmt(value["summary"]["per_window"].get(w, {}).get("pr_auc"), 5))
        print("  " + name.ljust(22) + "".join(f"{c:>14s}" for c in cells))
    print("\n-- per-window positives --")
    for w in windows:
        row = data["specs"]["B2_frozen_spec16"]["summary"]["per_window"].get(w, {})
        print(f"  {w}: rows={row.get('n')} pos={row.get('positives')} prevalence={_fmt(row.get('prevalence'))}")

    print("\n-- paired comparisons vs B2 (company clustering) --")
    for name, value in data["comparisons"].items():
        company = value.get("company", {})
        pair = value.get("pair", {})
        print(f"  {name:32s} dAP={_fmt(company.get('delta'))} "
              f"CI=[{_fmt(company.get('ci_low'))},{_fmt(company.get('ci_high'))}] "
              f"MDE={_fmt(company.get('mde_80'))} p={_fmt(company.get('p_one_sided'),3)} "
              f"| pair-CI=[{_fmt(pair.get('ci_low'))},{_fmt(pair.get('ci_high'))}]")

    g2 = data.get("g2", {})
    records = g2.get("randomisations", [])
    deltas = [r["pooled_delta_vs_real"] for r in records if r.get("pooled_delta_vs_real") is not None]
    rand_ap = [r["pooled_ap"] for r in records if r.get("pooled_ap") is not None]
    print("\n-- G2 randomisation distribution --")
    print(f"  real pooled AP = {_fmt(g2.get('real_pooled_ap'), 5)}")
    if rand_ap:
        ordered = sorted(rand_ap)
        print(f"  randomised pooled AP: min={ordered[0]:.5f} median={ordered[len(ordered)//2]:.5f} "
              f"max={ordered[-1]:.5f}")
        print(f"  randomisations with AP >= real: {sum(1 for v in rand_ap if v >= g2.get('real_pooled_ap'))}/{len(rand_ap)}")
    if deltas:
        ordered = sorted(deltas)
        print(f"  delta(randomised - real): min={ordered[0]:.5f} median={ordered[len(ordered)//2]:.5f} "
              f"max={ordered[-1]:.5f}; all_positive={all(d > 0 for d in deltas)}")


def _fmt(value, digits=4):
    if value is None:
        return "na"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


if __name__ == "__main__":
    for label in ("H4q", "H2q"):
        show(label)
