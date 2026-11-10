#!/usr/bin/env python3
"""Independent recomputation of ATLAS-001 deliverables.

This script is deliberately *not* a wrapper around the ATLAS code.  It opens the
SQLite file read-only and re-derives the numbers with plain SQL and its own
canonical-JSON hash implementation.  If the pipeline and this verifier disagree,
the pipeline is wrong (or the report is stale) and the exit code is non-zero.

Checks
------
1. every ``evidence_head`` row points at an existing latest version;
2. version numbers are contiguous from 1 and the head hash matches the version;
3. every payload hash recomputes from its ``normalized`` block;
4. every CONFIRMED ``SAME_DEVICE_IDENTITY`` pair shares a DI identifier;
5. every REJECTED relation carries a rejection reason;
6. no relation is both live and revoked, and no duplicate live identity pairs;
7. the numbers printed in ``identity_pilot.json`` match independent SQL counts;
8. the arithmetic in the baseline metrics is internally consistent;
9. no restricted-licence source appears in the committed sample directory;
10. no oversized sample files were committed.

Usage::

    python tools/verify_atlas.py --db research/atlas/staging/atlas.sqlite

Exit code 0 means every check passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class Verifier:
    def __init__(self, db_path: Path, report_path: Path) -> None:
        self.db_path = Path(db_path)
        self.report_path = Path(report_path)
        self.conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row
        self.checks: list[dict[str, Any]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # ------------------------------------------------------------------ checks
    def head_versions(self) -> None:
        bad = self.conn.execute(
            "SELECT COUNT(*) FROM evidence_head h LEFT JOIN evidence e"
            " ON e.evidence_id=h.evidence_id AND e.version=h.latest_version"
            " WHERE e.evidence_id IS NULL"
        ).fetchone()[0]
        self.check("head_points_at_existing_version", bad == 0, f"{bad} dangling heads")

        mismatched = self.conn.execute(
            "SELECT COUNT(*) FROM evidence_head h JOIN evidence e"
            " ON e.evidence_id=h.evidence_id AND e.version=h.latest_version"
            " WHERE e.content_hash <> h.latest_hash"
        ).fetchone()[0]
        self.check("head_hash_matches_version", mismatched == 0, f"{mismatched} mismatch(es)")

        gaps = self.conn.execute(
            "SELECT h.evidence_id, h.versions, COUNT(e.version) AS n,"
            " MIN(e.version) AS lo, MAX(e.version) AS hi FROM evidence_head h"
            " JOIN evidence e ON e.evidence_id=h.evidence_id GROUP BY h.evidence_id"
        ).fetchall()
        contiguous = all(
            row["n"] == row["versions"] and row["lo"] == 1 and row["hi"] == row["n"] for row in gaps
        )
        self.check("versions_contiguous", contiguous, f"{len(gaps)} evidence ids checked")

    def payload_hashes(self) -> None:
        bad: list[str] = []
        for row in self.conn.execute(
            "SELECT evidence_id, version, payload_json FROM evidence"
        ):
            payload = json.loads(row["payload_json"])
            recomputed = sha256_json(payload["normalized"])
            if recomputed != payload.get("normalized_content_hash"):
                bad.append(f"{row['evidence_id']} v{row['version']}")
        self.check("normalized_hashes_recompute", not bad, f"{len(bad)} mismatch(es): {bad[:3]}")

    def identity_evidence(self) -> None:
        rows = self.conn.execute(
            "SELECT relation_id, from_ref, to_ref, evidence_ids_json FROM entity_relations"
            " WHERE relation_type='SAME_DEVICE_IDENTITY' AND status='CONFIRMED' AND revoked_at=''"
        ).fetchall()
        missing: list[str] = []
        for row in rows:
            evidence_ids = json.loads(row["evidence_ids_json"] or "[]")
            # A GUDID record can legitimately carry several DIs (primary + package
            # DIs), so the check is that the two sides *share at least one* DI,
            # not that the union has one element.  The shared value is the
            # official-identifier assertion; other DIs on a record do not weaken it.
            per_record: list[set[str]] = []
            for eid in evidence_ids:
                per_record.append(
                    {
                        ident["value"]
                        for ident in self.conn.execute(
                            "SELECT value FROM evidence_identifiers"
                            " WHERE evidence_id=? AND scheme='di'",
                            (eid,),
                        )
                    }
                )
            shared = bool(per_record) and all(
                per_record[0] & other for other in per_record[1:]
            ) if len(per_record) > 1 else False
            if not shared:
                missing.append(row["relation_id"])
        self.check(
            "confirmed_identity_shares_one_di", not missing,
            f"{len(rows)} confirmed relations; {len(missing)} without a shared DI",
        )

        bad = self.conn.execute(
            "SELECT COUNT(*) FROM entity_relations WHERE status='REJECTED'"
            " AND (rejection_reason IS NULL OR rejection_reason='') AND revoked_at=''"
        ).fetchone()[0]
        self.check("rejections_have_reasons", bad == 0, f"{bad} unexplained rejection(s)")

        # Every revoked relation must have a reason and an append-only event.
        # (A check that merely counts revoked rows and asserts ``>= 0`` can never
        # fail — that was a real defect found in independent audit and is fixed.)
        revoked = self.conn.execute(
            "SELECT relation_id FROM entity_relations WHERE revoked_at<>''"
        ).fetchall()
        bad_history = []
        for row in revoked:
            reason = self.conn.execute(
                "SELECT revoked_reason FROM entity_relations WHERE relation_id=?",
                (row["relation_id"],),
            ).fetchone()["revoked_reason"]
            event = self.conn.execute(
                "SELECT COUNT(*) FROM relation_events WHERE relation_id=? AND action='revoked'",
                (row["relation_id"],),
            ).fetchone()[0]
            if not reason or event != 1:
                bad_history.append(row["relation_id"])
        self.check(
            "revoked_relations_have_reason_and_event",
            not bad_history,
            f"{len(revoked)} revoked; {len(bad_history)} without reason or single revoked event",
        )

        # Durable request accounting: every request recorded in a run's counter
        # must exist in request_log, and failures must be visible to checks.
        gap = self.conn.execute(
            "SELECT COUNT(*) FROM (SELECT r.run_id, r.requests,"
            " (SELECT COUNT(*) FROM request_log l WHERE l.run_id=r.run_id) AS logged"
            " FROM collection_runs r WHERE r.status='ok') WHERE logged < requests"
        ).fetchone()[0]
        self.check(
            "request_log_covers_run_counters",
            gap == 0,
            f"{gap} run(s) report more requests than request_log contains",
        )

        duplicates = self.conn.execute(
            "SELECT COUNT(*) FROM (SELECT from_ref, to_ref, relation_type, COUNT(*) n"
            " FROM entity_relations WHERE revoked_at='' GROUP BY 1,2,3 HAVING n > 1)"
        ).fetchone()[0]
        self.check("no_duplicate_live_relations", duplicates == 0, f"{duplicates} duplicate(s)")

    def report_matches_db(self) -> dict[str, Any]:
        if not self.report_path.exists():
            self.check("report_exists", False, str(self.report_path))
            return {}
        report = json.loads(self.report_path.read_text(encoding="utf-8"))
        db_counts = {
            "evidence_ids": self.conn.execute("SELECT COUNT(*) FROM evidence_head").fetchone()[0],
            "evidence_versions": self.conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
            "unique_devices": self.conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0],
            "device_identifiers": self.conn.execute(
                "SELECT COUNT(*) FROM device_identifiers"
            ).fetchone()[0],
            "companies": self.conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
            "bridge_confirmed_identity": self.conn.execute(
                "SELECT COUNT(*) FROM entity_relations WHERE relation_type='SAME_DEVICE_IDENTITY'"
                " AND status='CONFIRMED' AND revoked_at=''"
            ).fetchone()[0],
        }
        mismatches = {
            key: {"report": report.get("counts", {}).get(key), "db": value}
            for key, value in db_counts.items()
            if report.get("counts", {}).get(key) != value
        }
        self.check("report_counts_match_db", not mismatches, json.dumps(mismatches)[:500])

        identity_types = (
            "SAME_DEVICE_IDENTITY", "SAME_MODEL", "SAME_PRODUCT_FAMILY",
            "RELATED_TECHNOLOGY", "POSSIBLE_MATCH", "UNRELATED", "UNKNOWN",
        )
        placeholders = ",".join("?" for _ in identity_types)
        relation_counts = {
            "confirmed": self.conn.execute(
                "SELECT COUNT(*) FROM entity_relations WHERE status='CONFIRMED' AND revoked_at=''"
                f" AND relation_type IN ({placeholders})", identity_types
            ).fetchone()[0],
            "candidate": self.conn.execute(
                "SELECT COUNT(*) FROM entity_relations WHERE status='CANDIDATE' AND revoked_at=''"
                f" AND relation_type IN ({placeholders})", identity_types
            ).fetchone()[0],
            "rejected": self.conn.execute(
                "SELECT COUNT(*) FROM entity_relations WHERE status='REJECTED' AND revoked_at=''"
                f" AND relation_type IN ({placeholders})", identity_types
            ).fetchone()[0],
        }
        report_relations = report.get("relations", {})
        mismatch_rel = {
            k: {"report": report_relations.get(k), "db": v} for k, v in relation_counts.items()
            if report_relations.get(k) != v
        }
        self.check("report_relations_match_db", not mismatch_rel, json.dumps(mismatch_rel)[:400])
        return report

    def baseline_arithmetic(self, report: dict[str, Any]) -> None:
        baseline = report.get("baseline") or {}
        metrics = baseline.get("metrics") or {}
        problems = []
        for name, m in metrics.items():
            if not m:
                continue
            labelled = m.get("labelled_pairs")
            if labelled is not None and labelled != m["tp"] + m["fp"] + m["fn"] + m["tn"]:
                problems.append(f"{name}: labelled_pairs != tp+fp+fn+tn")
            if m.get("precision") is not None and m["tp"] + m["fp"]:
                expected = round(m["tp"] / (m["tp"] + m["fp"]), 4)
                if abs(expected - m["precision"]) > 1e-6:
                    problems.append(f"{name}: precision arithmetic")
            if m.get("recall") is not None and m["tp"] + m["fn"]:
                expected = round(m["tp"] / (m["tp"] + m["fn"]), 4)
                if abs(expected - m["recall"]) > 1e-6:
                    problems.append(f"{name}: recall arithmetic")
            if m.get("f1") is not None and m["precision"] and m["recall"]:
                expected = round(
                    2 * m["precision"] * m["recall"] / (m["precision"] + m["recall"]), 4
                )
                if abs(expected - m["f1"]) > 1e-3:
                    problems.append(f"{name}: f1 arithmetic")
        self.check("baseline_arithmetic_consistent", not problems, "; ".join(problems))

    def samples_safe(self) -> None:
        # Inspect *tracked* sample files, not just whatever is on disk: the
        # question is what the PR publishes, and content matters as much as size.
        tracked = subprocess.run(
            ["git", "ls-files", "research/atlas/samples"], cwd=ROOT,
            capture_output=True, text=True,
        ).stdout.splitlines()
        tracked = [name for name in tracked if name]
        oversize = [
            name for name in tracked if (ROOT / name).stat().st_size > 2 * 1024 * 1024
        ]
        self.check("tracked_sample_files_bounded", not oversize, str(oversize))

        allowed = ("api.fda.gov", "accessgudid.nlm.nih.gov", "health-products.canada.ca")
        bad_origin: list[str] = []
        for name in tracked:
            text = (ROOT / name).read_text(encoding="utf-8", errors="replace")
            if "epo.org" in text or "ops.epo" in text:
                bad_origin.append(name)
        self.check(
            "tracked_samples_use_open_sources_only",
            not bad_origin,
            f"{len(tracked)} tracked sample(s); restricted-origin files: {bad_origin}",
        )
        self.check(
            "sample_citations_are_official",
            all(any(host in (ROOT / n).read_text(encoding="utf-8", errors="ignore") for host in allowed)
                for n in tracked) if tracked else True,
            "each tracked sample names at least one official open source",
        )

        licensed = self.conn.execute(
            "SELECT COUNT(*) FROM evidence WHERE licence_status='restricted'"
        ).fetchone()[0]
        self.check(
            "restricted_evidence_not_used",
            licensed == 0,
            f"{licensed} restricted evidence rows (must be zero for public output)",
        )

    def run(self) -> dict[str, Any]:
        try:
            self.head_versions()
            self.payload_hashes()
            self.identity_evidence()
            report = self.report_matches_db()
            self.baseline_arithmetic(report)
            self.samples_safe()
        finally:
            # Release the read-only handle: on Windows an open SQLite handle
            # blocks temp-directory cleanup and makes CI look broken.
            self.conn.close()
        failures = [c for c in self.checks if not c["ok"]]
        return {
            "schema": "medradar.atlas.verification.v1",
            "db": str(self.db_path),
            "checks_total": len(self.checks),
            "checks_failed": len(failures),
            "ok": not failures,
            "checks": self.checks,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", default=str(ROOT / "research" / "atlas" / "staging" / "atlas.sqlite")
    )
    parser.add_argument(
        "--report", default=str(ROOT / "research" / "atlas" / "reports" / "identity_pilot.json")
    )
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    result = Verifier(Path(args.db), Path(args.report)).run()
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
