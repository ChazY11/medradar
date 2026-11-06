#!/usr/bin/env python3
"""Offline PHOENIX-001 structural and behavioural acceptance checks."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHOENIX = ROOT / "experiments" / "phoenix_001"
DOCS = ROOT / "docs"
DECISIONS = {"ADOPT", "ADAPT", "STUDY_ONLY", "REJECT", "BLOCKED"}
PROJECTS = [
    "SciTrends", "PubTrends", "NIH iSearch Analytics", "The Lens", "PTNS",
    "FDA AI 医疗器械纵向研究", "Clarivate DRG Medtech", "MedVantage", "CMOP",
    "NextDevice", "GBI DEVINT", "DevicePro", "众成医械大数据",
]
REQUIRED_PROJECT_FIELDS = {
    "name", "official_url", "type", "license", "permitted_use", "core_methods",
    "data_dependencies", "accessibility", "local_run", "resource_requirements",
    "medradar_overlap", "transferable_methods", "limitations_and_leakage_risks",
    "reproduction_status", "evidence", "decision", "decision_reason",
}
REQUIRED_DOCS = [
    "PHOENIX_SUMMARY.md", "PHOENIX_EXTERNAL_PROJECT_REGISTER.md",
    "PHOENIX_LICENSE_AUDIT.md", "PHOENIX_REPRODUCTION_REPORT.md",
    "PHOENIX_REA_AUDIT.md", "PHOENIX_RESEARCH_PROTOCOL.md",
    "PHOENIX_METHOD_COMPARISON.md", "PHOENIX_INNOVATION_OPPORTUNITIES.md",
    "PHOENIX_NEXT_ROADMAP.md",
]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    checks: dict[str, object] = {"version": "v2"}
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, text=True,
                            capture_output=True, check=False).stdout.strip()
    checks["research_branch"] = branch == "research/phoenix-001-external-methods"
    changed = subprocess.run(["git", "diff", "--name-only", "main"], cwd=ROOT, text=True,
                             capture_output=True, check=False).stdout.splitlines()
    checks["frozen_assets_untouched"] = not any(
        p.endswith((".sqlite", ".sqlite3", ".db"))
        or p.startswith("research/RESULTS/")
        or p.startswith("experiments/reverse_rd_")
        for p in changed
    )

    asset_path = PHOENIX / "asset_audit.json"
    checks["asset_audit_present"] = asset_path.is_file()
    if asset_path.is_file():
        assets = load_json(asset_path)
        checks["asset_runtime_recorded"] = all(k in assets for k in ("captured_at", "python", "node", "npm", "os"))
        expected = {row.get("path"): row for row in assets.get("assets", [])}
        checks["expected_databases_audited"] = all(
            p in expected and "exists" in expected[p] and "sha256" in expected[p]
            for p in ("data/medradar.sqlite", "data/research.sqlite")
        )
        checks["existing_assets_hashed"] = all(
            (not row.get("exists")) or (row.get("sha256") and row.get("read_only_test") is True)
            for row in assets.get("assets", [])
        )
    else:
        checks["asset_runtime_recorded"] = False
        checks["expected_databases_audited"] = False
        checks["existing_assets_hashed"] = False

    checks["required_documents"] = all((DOCS / name).is_file() for name in REQUIRED_DOCS)
    project_path = PHOENIX / "external_projects.json"
    checks["project_register_machine_readable"] = project_path.is_file()
    if project_path.is_file():
        projects = load_json(project_path)
        by_name = {p.get("name"): p for p in projects}
        checks["exactly_13_named_projects"] = len(projects) == 13 and set(by_name) == set(PROJECTS)
        checks["project_fields_complete"] = all(REQUIRED_PROJECT_FIELDS <= set(p) for p in projects)
        checks["project_decisions_justified"] = all(
            p.get("decision") in DECISIONS and bool(p.get("decision_reason")) for p in projects
        )
        checks["project_evidence_present"] = all(
            isinstance(p.get("evidence"), list) and p["evidence"] and all(
                e.get("url") and e.get("accessed_at") and e.get("locator") for e in p["evidence"]
            ) for p in projects
        )
        checks["commercial_claims_not_scientific_validation"] = all(
            p.get("reproduction_status") != "scientifically_validated"
            for p in projects if p.get("type") == "commercial_platform"
        )
    else:
        for key in ("exactly_13_named_projects", "project_fields_complete", "project_decisions_justified",
                    "project_evidence_present", "commercial_claims_not_scientific_validation"):
            checks[key] = False

    rea_path = PHOENIX / "rea_audit.json"
    checks["rea_audit_present"] = rea_path.is_file()
    if rea_path.is_file():
        rea = load_json(rea_path)
        checks["rea_supply_chain_reviewed"] = all(
            rea.get(k) not in (None, "", []) for k in
            ("upstream_repository", "npm_package", "stable_version", "license", "release_evidence",
             "dependency_review", "resource_review", "proposed_mcp_changes", "owner_approval")
        )
        checks["rea_outcome_honest"] = rea.get("status") in {
            "connected_and_tested", "installed_not_connected", "awaiting_owner_approval", "failed", "blocked"
        } and bool(rea.get("status_reason"))
        if rea.get("status") == "connected_and_tested":
            checks["rea_tools_and_smoke_test"] = bool(rea.get("tool_list")) and bool(rea.get("smoke_test_log"))
        else:
            checks["rea_tools_and_smoke_test"] = True
    else:
        checks["rea_supply_chain_reviewed"] = False
        checks["rea_outcome_honest"] = False
        checks["rea_tools_and_smoke_test"] = False

    hypothesis_path = PHOENIX / "hypotheses.json"
    checks["hypotheses_present"] = hypothesis_path.is_file()
    if hypothesis_path.is_file():
        hypotheses = load_json(hypothesis_path)
        checks["all_h1_h10_frozen"] = {h.get("id") for h in hypotheses} == {f"H{i}" for i in range(1, 11)} and all(
            all(h.get(k) not in (None, "", []) for k in
                ("definition", "sample_scope", "information_cutoff", "prediction_window", "baselines",
                 "primary_metrics", "frozen_at")) for h in hypotheses
        )
        checks["all_hypotheses_adjudicated"] = all(
            h.get("status") in {"supported", "refuted", "inconclusive", "blocked", "not_testable"}
            and bool(h.get("status_reason")) for h in hypotheses
        )
    else:
        checks["all_h1_h10_frozen"] = False
        checks["all_hypotheses_adjudicated"] = False

    logs = list((PHOENIX / "logs").glob("*.json")) if (PHOENIX / "logs").is_dir() else []
    checks["run_logs_present"] = bool(logs) and all(
        all(k in load_json(path) for k in ("command", "exit_code", "started_at", "finished_at")) for path in logs
    )
    log_index = PHOENIX / "logs" / "index.json"
    if log_index.is_file():
        indexed_runs = load_json(log_index).get("runs") or []
        checks["indexed_run_logs_complete"] = bool(indexed_runs) and all(
            all(k in row for k in ("command", "exit_code", "started_at", "finished_at", "stdout_tail"))
            for row in indexed_runs
        )
    comparison_path = PHOENIX / "method_comparison.json"
    checks["method_comparison_present"] = comparison_path.is_file()
    if comparison_path.is_file():
        comparison = load_json(comparison_path)
        checks["comparison_categories_explicit"] = comparison.get("evidence_category") in {1, 2, 3, 4}
        checks["comparison_not_prospective_overclaim"] = comparison.get("evidence_category") == 4 or (
            comparison.get("independent_prospective_validation") is False
        )
        checks["s028_s029_risks_addressed"] = all(
            key in (comparison.get("leakage_audit") or {}) for key in
            ("entity_mapping", "left_censoring", "time_proxy", "duplicate_samples", "cross_source_linkage")
        )
    else:
        checks["comparison_categories_explicit"] = False
        checks["comparison_not_prospective_overclaim"] = False
        checks["s028_s029_risks_addressed"] = False

    test = subprocess.run([sys.executable, "-m", "pytest", "tests/test_phoenix_001.py", "-q"], cwd=ROOT,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300, check=False)
    checks["phoenix_tests"] = test.returncode == 0
    checks["phoenix_tests_tail"] = "\n".join(test.stdout.strip().splitlines()[-8:])
    delivery_path = PHOENIX / "delivery.json"
    checks["draft_pr_recorded"] = delivery_path.is_file() and (
        load_json(delivery_path).get("draft") is True
        and load_json(delivery_path).get("merged") is False
        and bool(load_json(delivery_path).get("url"))
    )

    ignored_suffixes = ("_tail",)
    ok = all(value is True for key, value in checks.items()
             if key != "version" and not key.endswith(ignored_suffixes))
    print(json.dumps({"version": "v2", "ok": ok, "checks": checks}, indent=2, sort_keys=True, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
