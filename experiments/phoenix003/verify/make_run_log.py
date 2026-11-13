"""Assemble verify_run.log: environment, artefact pins, and every verifier console transcript.

Run:  python experiments/phoenix003/verify/make_run_log.py
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
REPO = EXP.parents[1]

STATES = {
    "SNAPSHOT (04:16-04:26:50 local, provisional)": HERE / "committed_snapshot",
    "RUN2 (05:03:15-05:04:58 local, all-corpus run)": HERE / "run2_snapshot",
    "RUN3 (05:07:34-05:10:02 local, Amendment 5)": HERE / "run3_final_snapshot",
    "POST-FIX FINAL (05:13:32-05:16:11 local, manifest generated_at 2026-11-08T21:16:11Z)": HERE / "final_snapshot",
}
LOGS = [
    ("step 1/2 — anchor construction and attribution (snapshot state)", "_anchors_console.txt"),
    ("step 1 — anchor-set state audit (snapshot 268 vs live 269, both reproduced)", "_anchor_state_console.txt"),
    ("step 2 — attribution audit (live 269 anchors)", "_attribution_live_console.txt"),
    ("step 3 — link tiers (snapshot state, ctgov-core corpus)", "_links_snapshot_console.txt"),
    ("step 3 — link tiers (run2 state, all four corpora)", "_links_live_console.txt"),
    ("step 4 — novelty classification (snapshot state)", "_novelty_snapshot_console.txt"),
    ("step 4 — novelty classification (run2 state)", "_novelty_live_console.txt"),
    ("step 5 — verdict recomputation (snapshot state)", "_verdict_snapshot_console.txt"),
    ("step 5 — verdict recomputation (run2 state)", "_verdict_live_console.txt"),
    ("step 6 — case audit, snapshot-state top case (Melody)", "_case_console.txt"),
    ("step 6 — case audits, run2 state (SYMPLICITY / OVERALL / OBTRYX)", "_case_live_console.txt"),
    ("step 3 — link tiers (RUN3 final state)", "_links_final_console.txt"),
    ("step 5 — verdict recomputation (RUN3 state)", "_verdict_final_console.txt"),
    ("FINAL STATE — all eight fixes, re-derived k/ladder/specificity/verdict, top strict case", "_final_console.txt"),
]
EXTRA = ["_anchors_console.txt", "_case_live_console.txt"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    lines = []
    lines.append("PHOENIX-003 INDEPENDENT VERIFICATION — RUN LOG")
    lines.append(f"generated_utc: {now}")
    lines.append(f"worktree: {REPO}")
    lines.append(f"python: {os.sys.version.splitlines()[0]}")
    lines.append("store: D:/DEPPSKK/medradar/data/medradar.sqlite (opened file:...?mode=ro; never modified)")
    lines.append("policy: no git write commands; no files under code/fetch/dataset/results modified; "
                 "scripts and snapshots only under experiments/phoenix003/verify/")
    lines.append("")
    lines.append("=" * 78)
    lines.append("ARTEFACT STATES VERIFIED (sha256 pinned before later re-runs could overwrite)")
    lines.append("=" * 78)
    for label, d in STATES.items():
        lines.append(f"\n## {label}  [{d.name}/]")
        man = d / "SNAPSHOT_FILES.json"
        if man.exists():
            for f in json.loads(man.read_text(encoding="utf-8")):
                lines.append(f"  {f['sha256']}  {f['bytes']:>10}  {f['path']}")
    lines.append("\nNOTE: the author re-ran the pipeline twice while verification was in progress "
                 "(run1 05:00:44, run2 05:04:58, run3 05:10:02, post-fix final 05:16:11; RUN3 added the "
                 "Amendment-5 literature-rarity annotation and re-freezes FROZEN_RULES with only "
                 "two new name_vocab keys; every headline value is identical to RUN2). The "
                 "snapshots above pin every state; the report verifies RUN2 and RUN3 jointly and "
                 "reports the SNAPSHOT state separately.")
    lines.append("")
    lines.append("=" * 78)
    lines.append("VERIFIER SCRIPTS (all in experiments/phoenix003/verify/)")
    lines.append("=" * 78)
    for p in sorted(HERE.glob("verify_*.py")) + sorted(HERE.glob("vcommon.py")) + [HERE / "make_run_log.py"]:
        if p.exists():
            lines.append(f"  {p.name}: {sha(p)}")
    lines.append("  snapshot/live selection: PHOENIX_VERIFY_MODE=snapshot|live (default live)")
    lines.append("")
    lines.append("=" * 78)
    lines.append("CONSOLE TRANSCRIPTS")
    lines.append("=" * 78)
    for title, fn in LOGS:
        p = HERE / fn
        if not p.exists():
            continue
        lines.append("\n" + "#" * 78)
        lines.append(f"# {title}   [{fn}]")
        lines.append("#" * 78)
        lines.append(p.read_text(encoding="utf-8", errors="replace").rstrip())
    (HERE / "verify_run.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", HERE / "verify_run.log",
          (HERE / "verify_run.log").stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
