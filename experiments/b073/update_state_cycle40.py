"""Update STATE and BACKLOG for cycle 40 (lane inventory, taxonomy versioning, backlog repair)."""
from __future__ import annotations

import json
from pathlib import Path

STATE = Path("research/STATE.json")
BACKLOG = Path("research/BACKLOG.yaml")

TASKS = """  - id: B-073
    layer: govern
    priority: P1
    title: Lane inventory before any "blocked" claim; versioned taxonomy; backlog repair
    status: done
    owner: lead
    depends_on: [B-072]
    acceptance: >
      experiments/b073/inventory_lanes.json counts every table in the frozen stores and maps tables to backlog items.
      Result: financial_facts=43420, market_bars=95725, publication_counts=616, events=55090, procurement_awards=3453
      are all present, so B-018, B-021, B-029, B-037 and B-041 are NOT blocked on data and stay open with the counts
      recorded as notes. Only B-014 is newly blocked, on a human adjudicator rather than on a store. B-028 marked done
      (contradictory evidence is a required profile field). B-032 shipped: medradar/intelligence/taxonomy.py gives the
      taxonomy a version, effective date and fingerprints of both mapping files, stamps profiles.json, detects regime
      change; 10 tests. Backlog parses (60 tasks) and the audit returns 11 PASS / 0 FAIL / 1 N/A.

  - id: B-074
    layer: predict
    priority: P1
    title: 重新点检剩余六项开放任务的数据可得性并排期
    status: todo
    owner: lead
    depends_on: [B-073]
    notes: >
      Six open items now have proven data (B-018, B-021, B-029, B-037, B-041, plus B-017's cohort re-run). Their order
      should be decided by cost and by what the papers still need, not by availability.
"""


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state["updated_at"] = "2026-11-04T03:40:00+08:00"
    state["phase"] = "bancklog_repaired_and_taxonomy_versioned".replace("bancklog", "backlog")
    state["cycle"] = 42
    state["last_completed_cycle"] = {
        "cycle": 40,
        "name": "lane_inventory_taxonomy_backlog",
        "branch": "research/change-detection-v1",
        "report": "experiments/b073/lane_inventory.json",
        "summary": "research/RESULTS/cycle40_inventory_taxonomy_2026-11-03.md",
        "verdict": ("counted the stores before calling anything blocked: financial, market and publication data are "
                    "present, so five 'todo' items stay open with row counts recorded and only B-014 is newly blocked "
                    "(on a human adjudicator). B-032 shipped as a versioned taxonomy with mapping fingerprints; "
                    "backlog parses, 60 tasks, audit 11 PASS"),
    }
    state["data_availability"] = {
        "artifact": "experiments/b073/lane_inventory.json",
        "tables": {"events": 55090, "financial_facts": 43420, "market_bars": 95725,
                   "publication_counts": 616, "procurement_awards": 3453,
                   "company_identifiers": 34, "horizon_forecasts": 25},
        "conclusion": ("five open backlog items that need financial, market or publication data are not blocked; the "
                       "only new block is B-014, which needs a human adjudicator"),
        "warning": ("the programme retracted one 'data unavailable' conclusion as a collector bug (D-029); count the "
                    "store before recording a block"),
    }
    state["publication"]["taxonomy_versioning"] = {
        "module": "medradar/intelligence/taxonomy.py",
        "version": "tracks_device_2026-11", "effective_from": "2026-11-03",
        "fingerprints": "sha256 of config/product_code_tracks.json and config/tracks_list; both stored in profiles.json",
        "tests": "tests/test_taxonomy.py (10)",
        "purpose": "a product-code remap is visible as a regime change rather than as a technology change",
    }
    state["established_findings"] = state["established_findings"] + [
        "GOVERN: the stores were counted before any item was called blocked - financial (43,420), market (95,725) and "
        "publication (616) data are present, so five open items are scheduled work, not blocked work",
        "DETECT: the taxonomy now carries a version, an effective date and fingerprints of both mapping files, so a "
        "code remap is detectable as a regime change (B-032)",
    ]
    state["next_actions"] = [
        "schedule the six open items by cost and by what the papers still need (B-074)",
        "mature the prospective forecast set when the lane advances (earliest 2026-Q4)",
        "keep tools/round_end.py as the gate at the end of every round",
        "schedule a rendered figure review before any submission",
    ]
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = BACKLOG.read_text(encoding="utf-8")
    if "id: B-073" not in text:
        BACKLOG.write_text(text.rstrip("\n") + "\n\n" + TASKS, encoding="utf-8", newline="\n")
        print("B-073 and B-074 appended")
    print("STATE.json updated; phase:", state["phase"], "cycle:", state["cycle"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
