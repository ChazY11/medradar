"""S-028-CORRECTION-1 audit 24: provenance, freeze chain and evidence immutability.

Three questions, answered with hashes rather than assertions:

1. **Was the original evidence altered during the correction round?**  Re-hash every
   Phase 0-3 file listed in ``ORIGINAL_EVIDENCE_MANIFEST.json`` and compare.  The
   correction round is only allowed to touch documents that carry an explicit
   correction note; every file under ``artifacts/`` and every original ``code/*.py``
   must be byte-identical.
2. **Does the pre-registration hash chain verify?**  Re-compute the SHA-256 of the
   documents recorded in ``artifacts/prereg_freeze.json`` and
   ``artifacts/prereg_freeze_amendment1.json`` and compare with the recorded values.
   A mismatch is not automatically misconduct - it may be a protocol document that
   was extended after the freeze - but it must be reported, because it means the
   frozen content cannot be byte-verified from the repository.
3. **Is the frozen database still the frozen database?**

Writes only ``artifacts/correction_round_1/provenance_verification.json``.

Usage
-----
    python audit_24_provenance_and_freeze.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s028_lib import FROZEN_DB_SHA256, FROZEN_DB_SIZE, verify_frozen_db  # noqa: E402

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[2]
CORRECTION = STUDY / "artifacts" / "correction_round_1"
DB = Path(r"D:\DEPPSKK\worktrees\integration-v2\data\research.sqlite")
MANIFEST = CORRECTION / "ORIGINAL_EVIDENCE_MANIFEST.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def git_blob_sha1(path: Path) -> str:
    result = subprocess.run(["git", "hash-object", str(path)], capture_output=True, text=True,
                            check=False)
    return result.stdout.strip()


def main() -> int:
    report: dict[str, Any] = {"study": "S-028", "correction": "S-028-CORRECTION-1",
                              "audit": "provenance, freeze chain, evidence immutability"}
    manifest = load(MANIFEST)
    report["manifest_head"] = manifest.get("git_head")
    report["manifest_branch"] = manifest.get("git_branch")
    report["manifest_baseline_clean"] = manifest.get("baseline_worktree_clean_for_study")

    # -- 1. immutability of the original evidence -------------------------
    allowed_document_edits = {
        "LITERATURE_REVIEW.md", "PHASE_REPORT_ZH.md", "GRAPH_RESULTS.md",
        "REPRODUCE.md", "PAPER_DRAFT.md", "NEGATIVE_RESULTS.md", "LIMITATIONS.md",
        "HYPOTHESIS_REGISTRY.md", "EXPERIMENT_PROTOCOL.md",
    }
    allowed_artifact_edits = {
        # literature metadata only: the correction round is allowed to add the
        # verified reference R45 and the PC-01 correction block.  The edit carries
        # its own correction record and is schema-validated by the literature task.
        # NO experimental artifact, prediction file, log, freeze record or
        # validation output may change.
        "artifacts/literature_refs.json",
    }
    unchanged: list[str] = []
    changed_artifacts: list[str] = []
    allowed_artifact_edits_seen: list[str] = []
    changed_code: list[str] = []
    changed_documents: list[str] = []
    missing: list[str] = []
    for path, record in manifest["files"].items():
        absolute = REPO / path
        if not absolute.exists():
            missing.append(path)
            continue
        current = sha256(absolute)
        same = current == record["worktree_sha256"]
        relative = path[len("research/studies/graph_early_signal_s028/"):]
        if same:
            unchanged.append(relative)
            continue
        if relative.startswith("artifacts/"):
            if relative in allowed_artifact_edits:
                allowed_artifact_edits_seen.append(relative)
            else:
                changed_artifacts.append(relative)
        elif relative.endswith(".py"):
            changed_code.append(relative)
        else:
            changed_documents.append(relative)
    unexpected_document_edits = [name for name in changed_documents
                                 if Path(name).name not in allowed_document_edits]
    report["evidence_immutability"] = {
        "files_checked": len(manifest["files"]),
        "unchanged": len(unchanged),
        "changed_artifacts": changed_artifacts,
        "allowed_artifact_edits": allowed_artifact_edits_seen,
        "changed_original_code": changed_code,
        "changed_documents": changed_documents,
        "unexpected_document_edits": unexpected_document_edits,
        "missing": missing,
        "verdict": ("PASS" if not changed_artifacts and not changed_code
                    and not missing and not unexpected_document_edits else "FAIL"),
    }

    # -- 2. pre-registration hash chain ------------------------------------
    freeze_checks = []
    for name in ("prereg_freeze.json", "prereg_freeze_amendment1.json"):
        path = STUDY / "artifacts" / name
        if not path.exists():
            continue
        payload = load(path)
        entry = {"freeze_artifact": name, "frozen_at_utc": payload.get("frozen_at_utc"),
                 "documents": {}}
        for document, record in payload.get("files", {}).items():
            target = STUDY / document
            current = sha256(target) if target.exists() else None
            blob = git_blob_sha1(target) if target.exists() else None
            entry["documents"][document] = {
                "recorded_sha256": record.get("sha256"),
                "recorded_size_bytes": record.get("size_bytes"),
                "current_sha256": current,
                "matches": current == record.get("sha256"),
                "current_size_bytes": target.stat().st_size if target.exists() else None,
                "git_blob_sha1": blob,
                "present_in_git_head": blob is not None,
            }
        entry["all_match"] = all(value["matches"] for value in entry["documents"].values())
        freeze_checks.append(entry)
    report["preregistration_freeze_chain"] = {
        "checks": freeze_checks,
        "all_match": all(entry["all_match"] for entry in freeze_checks) if freeze_checks else None,
        "latest_freeze_matches": ({document: value["matches"]
                                   for document, value in freeze_checks[-1]["documents"].items()}
                                  if freeze_checks else None),
        "interpretation": (
            "A mismatch means the document recorded at freeze time is not the document in the "
            "repository now; the frozen bytes are then not recoverable from the repo and the "
            "pre-registered content cannot be byte-verified.  This is reported, not 'fixed', "
            "because rewriting a protocol document after the fact would be worse."),
    }

    # -- 3. frozen database ------------------------------------------------
    database = verify_frozen_db(DB, strict=False)
    report["frozen_database"] = {**database,
                                 "expected": {"sha256": FROZEN_DB_SHA256,
                                              "size_bytes": FROZEN_DB_SIZE}}

    # -- 4. unrelated working-tree file must stay untouched ----------------
    result = subprocess.run(
        ["git", "-C", str(REPO), "status", "--porcelain", "--",
         "research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv"],
        capture_output=True, text=True, check=False)
    report["human_review_worksheet"] = {
        "git_status_line": result.stdout.strip(),
        "note": ("This file had an unrelated pre-existing uncommitted modification when the "
                 "correction round started.  It is reported, never staged or committed."),
    }

    latest = report["preregistration_freeze_chain"]["latest_freeze_matches"] or {}
    latest_ok = all(latest.values()) if latest else False
    report["overall"] = {
        "evidence_immutability": report["evidence_immutability"]["verdict"],
        "preregistration_latest_freeze_verifies": latest_ok,
        "frozen_database": "PASS" if database["ok"] else "FAIL",
        "verdict": ("PASS" if report["evidence_immutability"]["verdict"] == "PASS"
                    and latest_ok and database["ok"] else "REVIEW"),
        "note": ("The original freeze of PRE_REGISTRATION.md legitimately differs because "
                 "Amendment 1 superseded it; the amendment freeze must verify. "
                 "HYPOTHESIS_REGISTRY.md misses BOTH freeze hashes - reported as a provenance "
                 "limitation in the correction report, not silently repaired."),
    }
    out = CORRECTION / "provenance_verification.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
                   encoding="utf-8")
    print(json.dumps({"evidence_immutability": report["evidence_immutability"],
                      "preregistration_freeze_chain": {
                          "all_match": report["preregistration_freeze_chain"]["all_match"],
                          "checks": [{document: value["matches"]
                                      for document, value in entry["documents"].items()}
                                     for entry in freeze_checks]},
                      "frozen_database_ok": database["ok"],
                      "human_review_worksheet": report["human_review_worksheet"]["git_status_line"],
                      "overall": report["overall"]}, indent=2, default=str))
    print("\nwrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
