"""hist_v2 feasibility — can a coarser, domain-level entry target be powered where the 38-track target was not?

hist_v1's primary risk set (company x track, adjacency-restricted) had 6.0 positives per origin and an MDE of 0.090.
161 of 255 entry events were new-category entries that the adjacency restriction excluded by construction.  This
script measures, before any model is fitted, whether the same panel aggregated to the 22 technology *domains* (coarser
unit) supports a design that can include those new-category entries and still have positives to evaluate.

It reads the frozen hist_v1 panel only (no network, no model).  Output: experiments/hist_v2/feasibility.json
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "out" / "hist_v1" / "panel.json"
TRACKS = ROOT / "config" / "tracks_device.json"
OUT = ROOT / "experiments" / "hist_v2" / "feasibility.json"


def main() -> int:
    panel = json.loads(PANEL.read_text(encoding="utf-8"))
    tracks_cfg = json.loads(TRACKS.read_text(encoding="utf-8"))
    track_domain = {t["id"]: t.get("domain") for t in tracks_cfg["tracks"]}
    quarters = panel["quarters"]
    qidx = {q: i for i, q in enumerate(quarters)}

    # ---- aggregate the panel from track level to domain level ----
    domain_events: dict[tuple[str, str], list[int]] = defaultdict(list)
    for pair in panel["pairs"]:
        domain = track_domain.get(pair["track_id"])
        if not domain:
            continue
        for quarter, count in zip(pair["event_qidx"], pair["event_counts"]):
            domain_events[(pair["company_key"], domain)].extend([quarter] * count)
    for key in domain_events:
        domain_events[key].sort()

    def counts_at(events: list[int], t: int) -> int:
        import bisect

        return bisect.bisect_right(events, t)

    firms = sorted({company for company, _ in domain_events})
    domains = sorted({domain for _, domain in domain_events})
    firm_events: dict[str, list[int]] = defaultdict(list)
    for (company, _), events in domain_events.items():
        firm_events[company].extend(events)
    for company in firm_events:
        firm_events[company].sort()

    def measure(t_level: str, origins: list[int], horizon: int = 8) -> dict:
        rows = []
        for t in origins:
            if t + horizon > panel["quarters"].__len__() - 1:
                continue
            candidates = 0
            positives = 0
            entered_by_t: set[tuple[str, str]] = set()
            if t_level == "domain":
                universe = [(c, d) for c in firms for d in domains]
                for (c, d), events in domain_events.items():
                    if events and events[0] <= t:
                        entered_by_t.add((c, d))
            else:  # track level, for comparison
                universe = [(p["company_key"], p["track_id"]) for p in panel["pairs"]]
                for p in panel["pairs"]:
                    if p["event_qidx"] and p["event_qidx"][0] <= t:
                        entered_by_t.add((p["company_key"], p["track_id"]))
            for company, unit in universe:
                if (company, unit) in entered_by_t:
                    continue
                firm_q = firm_events[company]
                if not firm_q or firm_q[0] > t:
                    continue
                candidates += 1
                if t_level == "domain":
                    events = domain_events.get((company, unit), [])
                    first = events[0] if events else None
                else:
                    pair = next((p for p in panel["pairs"]
                                 if p["company_key"] == company and p["track_id"] == unit), None)
                    first = pair["event_qidx"][0] if pair and pair["event_qidx"] else None
                if first is not None and t < first <= t + horizon:
                    positives += 1
            rows.append({"origin": quarters[t], "candidates": candidates, "positives": positives,
                         "base_rate": (positives / candidates) if candidates else None})
        measurable = [r for r in rows if r["candidates"]]
        return {
            "origins": len(rows),
            "mean_candidates": sum(r["candidates"] for r in measurable) / len(measurable),
            "mean_positives": sum(r["positives"] for r in measurable) / len(measurable),
            "total_positives": sum(r["positives"] for r in rows),
            "mean_base_rate": sum(r["base_rate"] for r in measurable) / len(measurable),
            "per_origin": rows,
        }

    origins_primary = [qidx[f"{year}-Q1"] for year in range(1995, 2016)]   # entry-rich era
    origins_full = [qidx[f"{year}-Q1"] for year in range(1995, 2025)]
    feasibility = {
        "schema": "hist_v2.feasibility.v1",
        "panel": {"path": "out/hist_v1/panel.json", "sha256_note": "see experiments/hist_v1/manifest.json",
                  "quarters": len(quarters), "companies": len(firms), "domains": len(domains)},
        "domain_entries_ever": len(domain_events),
        "track_entries_ever": sum(1 for p in panel["pairs"] if p["event_qidx"]),
        "domain_vs_track": {
            "domain": measure("domain", origins_primary),
            "track": measure("track", origins_primary),
        },
        "domain_full_window": measure("domain", origins_full),
        "entries_by_decade_domain": dict(sorted(Counter(
            int(quarters[min(events)][:4]) // 10 * 10 for events in domain_events.values() if events).items())),
        "notes": [
            "domain level aggregates the 38 tracks into 22 technology domains (config/tracks_device.json `domain`)",
            "candidates are established firms x domains never entered by t; positives are first domain entries in (t, t+8]",
            "the entry-rich era 1995-2015 is used because hist_v1 showed almost no entries after 2015",
            "no model is fitted here; this is a feasibility measurement only",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(feasibility, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    dom = feasibility["domain_vs_track"]["domain"]
    trk = feasibility["domain_vs_track"]["track"]
    print(f"domain level, 1995-2015, h=8: origins={dom['origins']} "
          f"mean candidates={dom['mean_candidates']:.1f} mean positives={dom['mean_positives']:.2f} "
          f"base rate={dom['mean_base_rate']:.3f} total positives={dom['total_positives']}")
    print(f"track  level, 1995-2015, h=8: origins={trk['origins']} "
          f"mean candidates={trk['mean_candidates']:.1f} mean positives={trk['mean_positives']:.2f} "
          f"base rate={trk['mean_base_rate']:.3f} total positives={trk['total_positives']}")
    print(f"domain pairs ever={feasibility['domain_entries_ever']} (track pairs={feasibility['track_entries_ever']})")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
