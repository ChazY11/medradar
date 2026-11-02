"""End-to-end audit: re-run the record's load-bearing scripts and check every claim-bearing artifact.

The round-end gate checks that the artifacts *verify*. This audit additionally asks whether the record
**reproduces**: three deterministic scripts are re-run into a temporary directory and their output is compared with
the committed JSON, byte for byte after parsing. A mismatch means the committed artifact is stale or the script is not
deterministic — either is a defect in a record that claims reproducibility.

    python tools/final_audit.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "FINAL_AUDIT.json"

#: (label, script, committed artifact, extra args)
REPRODUCIBLE = (
    ("seasonality", "experiments/b074/seasonality.py", "experiments/b074/seasonality.json", []),
    ("density confirmation", "experiments/b026/density_confirm.py",
     "experiments/b026/density_confirm.json", []),
    ("pipeline evaluation", "experiments/b067/promotion_rolling_origin.py",
     "experiments/b067/promotion_rolling_origin.json", []),
    ("track-domain validation", "experiments/b026/validate_track_domain.py",
     "experiments/b026/validate_track_domain.json", []),
)

VERIFIERS = (
    ("test suite", [sys.executable, "-m", "medradar", "selftest"]),
    ("claims", [sys.executable, "papers/verify_claims.py"]),
    ("methods claims", [sys.executable, "papers/verify_claims.py", "--paper",
                        "papers/PAPER_METHODS_v1.md", "--claims", "papers/CLAIMS_METHODS.json"]),
    ("figures", [sys.executable, "papers/verify_figures.py"]),
    ("methods figures", [sys.executable, "papers/verify_figures.py", "--paper",
                         "papers/PAPER_METHODS_v1.md"]),
    ("figure layout", [sys.executable, "papers/check_layout.py"]),
    ("self-check", [sys.executable, "experiments/b027/selfcheck.py"]),
    ("snapshot chain", [sys.executable, "experiments/b027/snapshot_diff.py"]),
    ("forecast scorer", [sys.executable, "experiments/b068/maturate_forecasts.py"]),
    ("objective audit", [sys.executable, "tools/audit_objectives.py"]),
)


def run(command: list[str]) -> tuple[bool, str]:
    result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
    tail = ""
    for line in reversed(((result.stdout or "") + "\n" + (result.stderr or "")).splitlines()):
        if line.strip():
            tail = line.strip()
            break
    return result.returncode == 0, tail


def reproducibility() -> list[dict[str, Any]]:
    rows = []
    with tempfile.TemporaryDirectory() as folder:
        for label, script, committed, extra in REPRODUCIBLE:
            target = Path(folder) / f"{label.replace(' ', '_')}.json"
            ok, tail = run([sys.executable, script, "--out", str(target), *extra])
            row: dict[str, Any] = {"label": label, "script": script, "committed": committed,
                                   "exit_ok": ok, "detail": tail}
            if ok and target.exists():
                produced = json.loads(target.read_text(encoding="utf-8"))
                reference = json.loads((ROOT / committed).read_text(encoding="utf-8"))
                row["identical"] = produced == reference
                if not row["identical"]:
                    differing = [key for key in set(produced) | set(reference)
                                 if produced.get(key) != reference.get(key)]
                    row["differing_top_level_keys"] = sorted(differing)[:6]
            else:
                row["identical"] = False
            rows.append(row)
    return rows


def record_shape() -> dict[str, Any]:
    def count_lines(path: Path) -> int:
        return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0

    decisions = (ROOT / "research" / "DECISIONS.md").read_text(encoding="utf-8")
    results_index = (ROOT / "research" / "RESULTS" / "README.md").read_text(encoding="utf-8")
    snapshots = list((ROOT / "experiments" / "b027" / "snapshots").iterdir())
    forecast_sets = list((ROOT / "research" / "forecasts").glob("*.json"))
    claims = json.loads((ROOT / "papers" / "CLAIMS.json").read_text(encoding="utf-8"))["claims"]
    methods_claims = json.loads((ROOT / "papers" / "CLAIMS_METHODS.json").read_text(
        encoding="utf-8"))["claims"]
    return {
        "decisions": decisions.count("\n## D-"),
        "retraction_decisions": decisions.count("retract"),
        "results_rows": results_index.count("\n| R"),
        "snapshots": len([path for path in snapshots if path.is_dir()]),
        "forecast_sets": len(forecast_sets),
        "claims": len(claims),
        "methods_claims": len(methods_claims),
        "paper_lines": count_lines(ROOT / "papers" / "PAPER_v1.md"),
        "methods_paper_lines": count_lines(ROOT / "papers" / "PAPER_METHODS_v1.md"),
        "results_reports": len(list((ROOT / "research" / "RESULTS").glob("cycle*.md"))),
    }


def git_state() -> dict[str, Any]:
    def out(*args: str) -> str:
        return (subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT).stdout or "").strip()

    return {
        "branch": out("rev-parse", "--abbrev-ref", "HEAD"),
        "head": out("rev-parse", "HEAD"),
        "commits_on_branch": len(out("log", "--oneline").splitlines()),
        "dirty": [line for line in out("status", "--porcelain").splitlines() if line.strip()],
        "main_untouched": out("-C", "D:/DEPPSKK/medradar", "rev-parse", "--short", "HEAD")
        if Path("D:/DEPPSKK/medradar").exists() else "unknown",
    }


def main() -> int:
    verifiers = []
    for label, command in VERIFIERS:
        ok, tail = run(command)
        verifiers.append({"step": label, "ok": ok, "detail": tail})
        print(f"{'PASS' if ok else 'FAIL':4s} {label}: {tail}")

    repro = reproducibility()
    print()
    for row in repro:
        status = "REPRODUCED" if row.get("identical") else "DIFFERS"
        print(f"{status:10s} {row['label']}: {row.get('detail', '')}")

    payload = {
        "schema": "final_audit_v1",
        "git": git_state(),
        "record_shape": record_shape(),
        "verifiers": verifiers,
        "reproducibility": repro,
        "summary": {
            "verifiers_passed": sum(1 for row in verifiers if row["ok"]),
            "verifiers_failed": sum(1 for row in verifiers if not row["ok"]),
            "artifacts_reproduced": sum(1 for row in repro if row.get("identical")),
            "artifacts_differing": sum(1 for row in repro if not row.get("identical")),
        },
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                   newline="\n")
    print(f"\nsummary: {payload['summary']}")
    print(f"wrote {OUT.relative_to(ROOT)}")
    failed = payload["summary"]["verifiers_failed"] or payload["summary"]["artifacts_differing"]
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
