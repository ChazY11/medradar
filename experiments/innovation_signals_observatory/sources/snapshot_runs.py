"""Seed / compare full-population snapshot runs for the recruitment lane.

Two jobs, both deterministic and offline:

1. ``--project`` a snapshot file into a small identity projection
   (obs_id, posting_id, content_sha256, first_seen_at, source_posted_at, title) so two
   runs 20 minutes apart can be compared without committing two 9 MB datasets.
2. ``--seed-store`` ingest a snapshot into the append-only observation store, so a later
   collection can be ingested *on top of* it and the store can prove that
   ``first_seen_at`` did not move.
3. ``--compare`` two projections and report identity overlap, content-hash stability,
   and what changed between the two observations of the same population.

Usage:
    python experiments/innovation_signals_observatory/sources/snapshot_runs.py project \
        --jobs run1.jsonl --out results/2026-11-04/snapshot_runs/run1_identity.jsonl
    python ... snapshot_runs.py seed-store --jobs run1.jsonl --store data/recruitment/store
    python ... snapshot_runs.py compare --a .../run1_identity.jsonl --b .../run2_identity.jsonl \
        --out results/2026-11-04/snapshot_stability_full.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from medradar.recruitment import records as rec  # noqa: E402
from medradar.recruitment.store import ObservationStore  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def project(jobs: Path, out: Path) -> int:
    rows = load_jsonl(jobs)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps({
                "obs_id": row.get("obs_id"),
                "posting_id": row.get("posting_id"),
                "content_sha256": row.get("content_sha256"),
                "hash_rule_version": row.get("hash_rule_version"),
                "first_seen_at": row.get("first_seen_at"),
                "source_posted_at": row.get("source_posted_at"),
                "job_title": row.get("job_title"),
                "source_url": row.get("source_url"),
            }, ensure_ascii=False) + "\n")
    print(f"projected {len(rows)} rows -> {out}")
    return 0


def seed_store(jobs: Path, store_dir: Path) -> int:
    observations = [rec.JobObservation.from_dict(row) for row in load_jsonl(jobs)]
    store = ObservationStore(store_dir)
    summary = store.ingest(observations, complete_snapshot=False,
                           run_meta={"phase": "seed", "source": str(jobs.name),
                                     "n_rows": len(observations)})
    print(json.dumps(summary["counts"], ensure_ascii=False))
    return 0


def compare(a: Path, b: Path, out: Path, *, store_dir: str | None = None) -> int:
    rows_a = load_jsonl(a)
    rows_b = load_jsonl(b)
    by_pid_a = {r["posting_id"]: r for r in rows_a}
    by_pid_b = {r["posting_id"]: r for r in rows_b}
    common = set(by_pid_a) & set(by_pid_b)
    hash_stable = sum(1 for pid in common
                      if by_pid_a[pid]["content_sha256"] == by_pid_b[pid]["content_sha256"])
    changed = [pid for pid in common
               if by_pid_a[pid]["content_sha256"] != by_pid_b[pid]["content_sha256"]]
    # A content hash is only comparable when both observations were hashed by the same
    # rule. Comparing across a rule change would report "every posting was edited", which
    # is an artefact of our own code, not a property of the source.
    rules_a = {r.get("hash_rule_version") for r in rows_a}
    rules_b = {r.get("hash_rule_version") for r in rows_b}
    hash_comparable = (rules_a == rules_b) and (None not in rules_a)
    payload = {
        "comparison": "two full-population observations of the same career site",
        "content_hash_comparable": hash_comparable,
        "hash_rule_versions": {"a": sorted(str(x) for x in rules_a), "b": sorted(str(x) for x in rules_b)},
        "run_a": {"file": a.name, "n_rows": len(rows_a), "n_distinct_ids": len(by_pid_a)},
        "run_b": {"file": b.name, "n_rows": len(rows_b), "n_distinct_ids": len(by_pid_b)},
        "identity_overlap_a": round(len(common) / len(by_pid_a), 4) if by_pid_a else None,
        "identity_overlap_b": round(len(common) / len(by_pid_b), 4) if by_pid_b else None,
        "content_hash_stable_among_common": (round(hash_stable / len(common), 4)
                                             if common and hash_comparable else None),
        "n_content_changed": len(changed) if hash_comparable else None,
        "n_content_changed_ignored_due_to_rule_change": (len(changed) if not hash_comparable else 0),
        "content_changed_examples": [
            {"posting_id": pid, "title_a": by_pid_a[pid].get("job_title"),
             "title_b": by_pid_b[pid].get("job_title")} for pid in changed[:10]
        ],
        "only_in_a": sorted(set(by_pid_a) - set(by_pid_b))[:20],
        "only_in_b": sorted(set(by_pid_b) - set(by_pid_a))[:20],
        "n_only_in_a": len(set(by_pid_a) - set(by_pid_b)),
        "n_only_in_b": len(set(by_pid_b) - set(by_pid_a)),
        "note": ("Two consecutive full reads of the same listing. Overlap < 1 means the site's "
                 "listing is not a stable snapshot (postings added/closed between runs, or offset "
                 "pagination drift); content changes mean descriptions are being edited. Both are "
                 "collection properties, not hiring-strategy evidence."),
    }
    if store_dir:
        store = ObservationStore(store_dir)
        payload["store_summary"] = store.summary()
        current = store.current()
        first_seen_pairs = []
        for pid in sorted(common)[:2000]:
            obs_id = by_pid_a[pid]["obs_id"]
            stored = current.get(obs_id) or {}
            first_seen_pairs.append(stored.get("first_seen_at") == by_pid_a[pid]["first_seen_at"])
        payload["first_seen_preserved_for_run_a_rows"] = sum(1 for x in first_seen_pairs if x)
        payload["first_seen_checked"] = len(first_seen_pairs)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("identity_overlap_a", "content_hash_stable_among_common",
                                             "n_only_in_a", "n_only_in_b", "n_content_changed")},
                     ensure_ascii=False))
    print(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("project")
    p1.add_argument("--jobs", required=True)
    p1.add_argument("--out", required=True)
    p2 = sub.add_parser("seed-store")
    p2.add_argument("--jobs", required=True)
    p2.add_argument("--store", required=True)
    p3 = sub.add_parser("compare")
    p3.add_argument("--a", required=True)
    p3.add_argument("--b", required=True)
    p3.add_argument("--out", required=True)
    p3.add_argument("--store", default=None)
    args = ap.parse_args(argv)
    if args.cmd == "project":
        return project(Path(args.jobs), Path(args.out))
    if args.cmd == "seed-store":
        return seed_store(Path(args.jobs), Path(args.store))
    return compare(Path(args.a), Path(args.b), Path(args.out), store_dir=args.store)


if __name__ == "__main__":
    raise SystemExit(main())
