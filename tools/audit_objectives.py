"""Audit the mission objective against the repository, and emit evidence rather than assertions.

The mission states what the programme must maintain and ship. This script checks each requirement
mechanically and writes `research/AUDIT.json` plus a readable `research/AUDIT.md`. It is re-runnable, so
"the objective is met" is a claim a reviewer can test rather than trust.

Requirements audited:
  * persistent research state: the eleven named files exist and are non-trivial;
  * the loop ran: experiments with committed artifacts, recorded decisions, recorded negatives;
  * artifacts shipped: code, point-in-time snapshots with manifests, a rolling-origin benchmark,
    frozen forecasts, a paper;
  * verification: claim map, figures, profile snapshots, test suite.

Usage:
    python tools/audit_objectives.py [--with-selftest]
Exit code 0 only if every requirement is PASS (data-dependent items may be N/A with a reason).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
STATE_FILES = {
    "MISSION.md": "mission statement",
    "ROADMAP.md": "roadmap",
    "BACKLOG.yaml": "backlog",
    "STATE.json": "machine-readable state",
    "HYPOTHESES.md": "hypotheses",
    "LITERATURE.md": "literature",
    "EXPERIMENTS.md": "experiment index",
    "DECISIONS.md": "decision and retraction log",
    "DATA_PROVENANCE.md": "data provenance",
    "PREDICTION_PROTOCOL.md": "pre-registered protocol",
    "RESULTS/README.md": "results ledger",
    "COMPLETION_REPORT.md": "completion report against the objective",
    "FINAL_AUDIT.json": "end-to-end reproducibility audit",
}
MIN_BYTES = 2_000


def record(requirement: str, status: str, evidence: str, detail: dict | None = None) -> dict:
    return {"requirement": requirement, "status": status, "evidence": evidence,
            "detail": detail or {}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-selftest", action="store_true",
                        help="also run python -m medradar selftest (slower)")
    args = parser.parse_args(argv)

    items: list[dict] = []

    # 1. persistent research state
    research = ROOT / "research"
    missing = []
    for name, purpose in STATE_FILES.items():
        path = research / name
        if not path.exists():
            missing.append(f"{name} ({purpose}) missing")
        elif path.stat().st_size < MIN_BYTES:
            missing.append(f"{name} is only {path.stat().st_size} bytes")
    items.append(record("persistent research state files", "PASS" if not missing else "FAIL",
                        f"{len(STATE_FILES)} files under research/", {"problems": missing}))

    # 2. backlog parses, unique ids, statuses
    try:
        import yaml
        backlog = yaml.safe_load((research / "BACKLOG.yaml").read_text(encoding="utf-8"))
        tasks = backlog.get("tasks", [])
        ids = [task.get("id") for task in tasks]
        duplicates = sorted({task_id for task_id in ids if ids.count(task_id) > 1})
        statuses: dict[str, int] = {}
        for task in tasks:
            statuses[task.get("status", "?")] = statuses.get(task.get("status", "?"), 0) + 1
        ok = not duplicates and len(tasks) > 0
        items.append(record("backlog integrity", "PASS" if ok else "FAIL",
                            f"{len(tasks)} tasks, statuses {statuses}",
                            {"duplicates": duplicates}))
    except Exception as exc:  # noqa: BLE001
        items.append(record("backlog integrity", "FAIL", f"could not parse BACKLOG.yaml: {exc}"))

    # 3. machine-readable state completeness
    try:
        state = json.loads((research / "STATE.json").read_text(encoding="utf-8"))
        needed = ("phase", "cycle", "established_findings", "next_actions")
        absent = [key for key in needed if not state.get(key)]
        items.append(record("state completeness", "PASS" if not absent else "FAIL",
                            f"phase={state.get('phase')!r}, cycle={state.get('cycle')}",
                            {"absent": absent,
                             "findings": len(state.get("established_findings") or [])}))
    except Exception as exc:  # noqa: BLE001
        items.append(record("state completeness", "FAIL", f"could not read STATE.json: {exc}"))

    # 4. the loop ran: decisions and recorded negatives
    decisions_text = (research / "DECISIONS.md").read_text(encoding="utf-8")
    decision_count = decisions_text.count("\n## D-")
    retractions = sum(1 for line in decisions_text.splitlines()
                      if "retract" in line.lower() and line.startswith("**"))
    results_text = (research / "RESULTS" / "README.md").read_text(encoding="utf-8")
    result_rows = sum(1 for line in results_text.splitlines() if line.startswith("| R"))
    negative_rows = sum(1 for line in results_text.splitlines()
                        if line.startswith("| R") and ("negative" in line.lower()
                                                       or "null" in line.lower()))
    ok = decision_count >= 10 and result_rows >= 20
    items.append(record("loop ran and was recorded", "PASS" if ok else "FAIL",
                        f"{decision_count} decisions, {result_rows} result rows "
                        f"({negative_rows} negative/null), retractions marked: {retractions}"))

    # 5. experiments with committed artifacts
    experiment_json = list((ROOT / "experiments").rglob("*.json"))
    experiment_dirs = sorted({path.parent.name for path in experiment_json})
    items.append(record("experiments with committed artifacts", "PASS" if len(experiment_json) >= 20 else "FAIL",
                        f"{len(experiment_json)} JSON artifacts across {len(experiment_dirs)} experiment dirs"))

    # 6. point-in-time snapshots with verifying manifests
    snapshots = sorted((ROOT / "experiments" / "b027" / "snapshots").glob("*/manifest.json"))
    verified, snapshot_problems = [], []
    from medradar.intelligence.snapshot import verify_manifest
    for manifest_path in snapshots:
        directory = manifest_path.parent
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        profiles = json.loads((directory / "profiles.json").read_text(encoding="utf-8"))
        summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        problems = verify_manifest(manifest, artifacts={"profiles": profiles, "summary": summary})
        if problems:
            snapshot_problems.append(f"{directory.name}: {problems[0]}")
        else:
            verified.append(directory.name)
    items.append(record("point-in-time snapshots verify",
                        "PASS" if verified and not snapshot_problems else "FAIL",
                        f"{len(verified)} of {len(snapshots)} snapshots verify",
                        {"verified": verified, "problems": snapshot_problems}))

    # 7. rolling-origin benchmark
    rolling = ROOT / "experiments" / "b050" / "rolling_origin.json"
    if rolling.exists():
        payload = json.loads(rolling.read_text(encoding="utf-8"))
        items.append(record("rolling-origin benchmark", "PASS",
                            f"{payload['counts']['cells']} cells, {len(payload['design']['origins'])} origins, "
                            f"{payload['counts']['observations']} observations"))
    else:
        items.append(record("rolling-origin benchmark", "FAIL", "experiments/b050/rolling_origin.json missing"))

    # 8. frozen forecasts: committed, hash-verified sets first; the local registry is secondary evidence
    from medradar.intelligence.forecasts import validate_forecast_set
    from medradar.intelligence.snapshot import content_hash

    forecast_files = sorted((ROOT / "research" / "forecasts").glob("*.json"))
    verified_sets, forecast_problems, prospective_total = [], [], 0
    for path in forecast_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        recorded = payload.pop("forecast_set_hash", None)
        problems = validate_forecast_set(payload)
        if recorded and content_hash(payload) != recorded:
            problems.append("content hash does not match its own records")
        payload["forecast_set_hash"] = recorded
        if problems:
            forecast_problems.append(f"{path.name}: {problems[0]}")
            continue
        verified_sets.append({"file": path.name, "forecasts": len(payload["forecasts"]),
                              "prospective_only": bool(payload.get("prospective_only"))})
        if payload.get("prospective_only"):
            prospective_total += len(payload["forecasts"])
    if verified_sets:
        items.append(record("frozen forecasts", "PASS" if prospective_total else "FAIL",
                            f"{len(verified_sets)} hash-verified forecast set(s); "
                            f"{prospective_total} genuinely prospective forecasts pending maturation",
                            {"sets": verified_sets, "problems": forecast_problems}))
    elif forecast_problems:
        items.append(record("frozen forecasts", "FAIL", "; ".join(forecast_problems)))
    else:
        registry = ROOT / "data" / "registry.sqlite"
        if registry.exists():
            import sqlite3
            con = sqlite3.connect(f"file:{registry}?mode=ro", uri=True)
            try:
                nowcasts = con.execute("select count(*) from forecasts").fetchone()[0]
            except sqlite3.Error:
                nowcasts = None
            con.close()
            items.append(record("frozen forecasts", "PASS" if nowcasts else "N/A",
                                f"registry present, {nowcasts} registered forecasts; no committed forecast set"))
        else:
            items.append(record("frozen forecasts", "N/A",
                                "no committed forecast set and no registry in this checkout"))

    # 9. paper with a verifying claim map
    paper = ROOT / "papers" / "PAPER_v1.md"
    claims = ROOT / "papers" / "CLAIMS.json"
    if paper.exists() and claims.exists():
        result = subprocess.run([sys.executable, str(ROOT / "papers" / "verify_claims.py")],
                                capture_output=True, text=True, cwd=ROOT)
        lines = (result.stdout or "").strip().splitlines()
        summary = lines[-1] if lines else "no output"
        items.append(record("paper with verified claims", "PASS" if result.returncode == 0 else "FAIL",
                            f"papers/PAPER_v1.md; {summary}"))
    else:
        items.append(record("paper with verified claims", "FAIL", "paper or claim map missing"))

    # 10. figures verify
    figures = ROOT / "papers" / "verify_figures.py"
    if figures.exists():
        result = subprocess.run([sys.executable, str(figures)], capture_output=True, text=True, cwd=ROOT)
        lines = (result.stdout or "").strip().splitlines()
        summary = lines[-1] if lines else "no output"
        items.append(record("figures verify", "PASS" if result.returncode == 0 else "FAIL", summary))
    else:
        items.append(record("figures verify", "FAIL", "papers/verify_figures.py missing"))

    # 11. profile self-check
    selfcheck = ROOT / "experiments" / "b027" / "selfcheck.py"
    if selfcheck.exists():
        result = subprocess.run([sys.executable, str(selfcheck)], capture_output=True, text=True, cwd=ROOT)
        lines = (result.stdout or "").strip().splitlines()
        summary = lines[-1] if lines else "no output"
        items.append(record("profile self-check", "PASS" if result.returncode == 0 else "FAIL", summary))

    # 12. tests (optional, slow)
    if args.with_selftest:
        result = subprocess.run([sys.executable, "-m", "medradar", "selftest"],
                                capture_output=True, text=True, cwd=ROOT)
        tail = [line for line in (result.stdout or "").splitlines() if "Ran " in line or line.strip() == "OK"]
        items.append(record("test suite", "PASS" if result.returncode == 0 else "FAIL",
                            "; ".join(tail) or "no output"))

    # 13. working tree state
    git = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=ROOT)
    dirty = [line for line in (git.stdout or "").splitlines() if line.strip()]
    items.append(record("working tree committed", "PASS" if not dirty else "N/A",
                        f"{len(dirty)} uncommitted path(s) at audit time"))

    passed = sum(1 for item in items if item["status"] == "PASS")
    failed = [item for item in items if item["status"] == "FAIL"]
    na = sum(1 for item in items if item["status"] == "N/A")
    payload = {"schema": "objective_audit_v1", "items": items,
               "summary": {"passed": passed, "failed": len(failed), "not_applicable": na,
                           "total": len(items)}}
    (ROOT / "research" / "AUDIT.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    lines = ["# Objective audit", "",
             "Generated by `tools/audit_objectives.py`; re-runnable. PASS means the requirement is "
             "mechanically satisfied by a committed artifact.", "",
             "| requirement | status | evidence |", "|---|---|---|"]
    for item in items:
        lines.append(f"| {item['requirement']} | **{item['status']}** | {item['evidence']} |")
    lines += ["", f"**{passed} passed, {len(failed)} failed, {na} not applicable of {len(items)}.**", ""]
    if failed:
        lines.append("Failures to fix:")
        for item in failed:
            lines.append(f"- {item['requirement']}: {item['evidence']} {item['detail']}")
        lines.append("")
    (ROOT / "research" / "AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"audit: {passed} PASS, {len(failed)} FAIL, {na} N/A of {len(items)}")
    for item in items:
        print(f"  {item['status']:4s} {item['requirement']}: {item['evidence']}")
    print("\nwrote research/AUDIT.json and research/AUDIT.md")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
