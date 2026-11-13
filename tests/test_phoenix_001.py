from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "experiments" / "phoenix_001" / "audit_assets.py"
SPEC = importlib.util.spec_from_file_location("phoenix_asset_audit", MODULE_PATH)
assert SPEC and SPEC.loader
ASSETS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ASSETS)


def test_missing_sqlite_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite"
    result = ASSETS.audit_sqlite(path)
    assert result["exists"] is False
    assert result["sha256"] is None
    assert result["integrity_check"] == "not_run_missing"
    assert not path.exists()


def test_existing_sqlite_is_hashed_and_read_only(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "frozen.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE example (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO example VALUES (1)")
    before = path.read_bytes()
    result = ASSETS.audit_sqlite(path)
    assert result["exists"] is True
    assert result["read_only_test"] is True
    assert result["integrity_check"] == "ok"
    assert result["sha256"] == ASSETS.sha256(path)
    assert path.read_bytes() == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM example").fetchone()[0] == 1


def test_current_asset_audit_has_no_invented_hash() -> None:
    output = ROOT / "experiments" / "phoenix_001" / "asset_audit.json"
    if not output.exists():
        return
    payload = json.loads(output.read_text(encoding="utf-8"))
    for row in payload["assets"]:
        assert (row["sha256"] is not None) == row["exists"]


def load_phoenix_module(filename: str, name: str):
    path = ROOT / "experiments" / "phoenix_001" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_regression_metrics_are_recomputed() -> None:
    module = load_phoenix_module("scitreands_reproduce.py", "phoenix_scitreands")
    result = module.regression_metrics([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert result["rows"] == 3
    assert result["r2"] == 1.0
    assert result["mae"] == 0.0
    assert result["rmse"] == 0.0


def test_external_reproduction_artifacts_are_honest_when_present() -> None:
    scitreands = ROOT / "experiments" / "phoenix_001" / "scitreands_results.json"
    if scitreands.exists():
        payload = json.loads(scitreands.read_text(encoding="utf-8"))
        assert payload["status"] == "completed_author_no_dl_core"
        assert payload["configuration"]["GET_DL_EMBEDS"] is False
        assert payload["dataset"]["evaluated_rows"] == payload["metrics"]["catboost_all_features"]["rows"]
        assert payload["temporal_audit"]["folds_with_shared_train_test_years"] == 30
    pubtrends = ROOT / "experiments" / "phoenix_001" / "pubtrends_smoke_results.json"
    if pubtrends.exists():
        payload = json.loads(pubtrends.read_text(encoding="utf-8"))
        assert payload["status"] == "passed"
        assert payload["license"] == "Apache-2.0"
        assert "no PostgreSQL" in payload["scope"]
    crispr = ROOT / "experiments" / "phoenix_001" / "scitreands_crispr_lags.json"
    if crispr.exists():
        payload = json.loads(crispr.read_text(encoding="utf-8"))
        assert payload["rows"] == 19
        assert payload["evidence_category"] == 2
        assert "not a trained or prospectively validated" in payload["warning"]


def test_fda_independent_statistics_functions() -> None:
    module = load_phoenix_module("fda_ai_longitudinal.py", "phoenix_fda_ai")
    assert module.hhi([50, 50]) == 0.5
    assert module.hhi([100, 0]) == 1.0
    z = module.cochran_armitage([15, 118, 347, 614], [42, 190, 406, 792])
    assert abs(z - 5.300240938614455) < 1e-10
    result = ROOT / "experiments" / "phoenix_001" / "fda_ai_longitudinal_results.json"
    if result.exists():
        payload = json.loads(result.read_text(encoding="utf-8"))
        assert payload["status"] == "completed_independent_aggregate_reproduction"
        assert payload["specialty_era_association"]["expected_cells_below_5"] == 51
        assert abs(payload["hhi"]["independent_point_estimates"][2] - 0.7381275934868596) < 1e-12
        assert payload["scope_limit"].startswith("Independent recomputation from published aggregate counts")


def test_external_register_has_all_13_projects_with_decisions() -> None:
    payload = json.loads((ROOT / "experiments" / "phoenix_001" / "external_projects.json").read_text(encoding="utf-8"))
    assert len(payload) == 13
    assert {p["decision"] for p in payload} <= {"ADOPT", "ADAPT", "STUDY_ONLY", "REJECT", "BLOCKED"}
    assert all(p["evidence"] and p["decision_reason"] for p in payload)
    commercial = [p for p in payload if p["type"] == "commercial_platform"]
    assert len(commercial) == 7
    assert all(p["reproduction_status"] != "scientifically_validated" for p in commercial)
    devicepro = next(p for p in payload if p["name"] == "DevicePro")
    assert "unreconciled" in devicepro["accessibility"]


def test_frozen_hypotheses_and_method_comparison() -> None:
    hypotheses = json.loads((ROOT / "experiments" / "phoenix_001" / "hypotheses.json").read_text(encoding="utf-8"))
    assert len(hypotheses) == 10
    statuses = {h["id"]: h["status"] for h in hypotheses}
    assert statuses == {
        "H1": "supported", "H2": "inconclusive", "H3": "inconclusive", "H4": "inconclusive",
        "H5": "blocked", "H6": "blocked", "H7": "inconclusive", "H8": "inconclusive",
        "H9": "refuted", "H10": "inconclusive",
    }
    comparison = json.loads((ROOT / "experiments" / "phoenix_001" / "method_comparison.json").read_text(encoding="utf-8"))
    assert comparison["evidence_category"] == 3
    assert comparison["independent_prospective_validation"] is False
    assert len(comparison["methods"]) == 20
    assert len(comparison["source_artifacts"]) == 6
    assert all(len(row["sha256"]) == 64 for row in comparison["source_artifacts"])
    for method in comparison["methods"]:
        row = method["final_origin_metrics"]
        assert 0 <= row["recall_at_k"] <= 1
        assert row["true_positives_at_k"] == round(row["precision_at_k"] * row["k"])
        assert row["mean_lead_time_days"] is not None
    risks = comparison["leakage_audit"]
    assert {"entity_mapping", "left_censoring", "time_proxy", "duplicate_samples", "cross_source_linkage"} <= set(risks)
    assert risks["duplicate_samples"]["status"] == "not_independently_recomputable_here"


def phoenix_event(**overrides):
    event = {
        "source_event_id": "K123", "source_locator": "openfda://510k/K123", "lineage_id": "K123",
        "event_date": "2024-01-01", "available_at": "2024-01-15", "timestamp_quality": "estimated",
        "company_key": "example", "matched_alias": "Example Subsidiary", "match_rule": "alias-v1",
        "confidence": 0.95, "ownership_valid_from": "2020-01-01", "ownership_valid_to": "2025-01-01",
        "track_id": "imaging", "taxonomy_version": "tracks-2024-01",
    }
    event.update(overrides)
    return event


def test_evidence_contract_accepts_auditable_historical_event() -> None:
    module = load_phoenix_module("evidence_contract.py", "phoenix_evidence")
    module.validate_event(phoenix_event(), "2024-02-01")
    try:
        module.validate_event(phoenix_event(), "2024-02-01", prospective=True)
        assert False, "estimated time must fail the prospective gate"
    except ValueError as exc:
        assert "observed" in str(exc)
    module.validate_event(phoenix_event(timestamp_quality="observed"), "2024-02-01", prospective=True)


def test_evidence_contract_releases_no_future_or_anachronistic_event() -> None:
    module = load_phoenix_module("evidence_contract.py", "phoenix_evidence")
    for bad, expected in [
        ({"available_at": "2024-03-01"}, "cutoff"),
        ({"event_date": "2019-01-01", "ownership_valid_to": None}, "predates"),
        ({"taxonomy_version": None}, "taxonomy_version"),
        ({"confidence": 1.2}, "confidence"),
    ]:
        try:
            module.validate_event(phoenix_event(**bad), "2024-02-01")
            assert False, f"invalid event accepted: {bad}"
        except ValueError as exc:
            assert expected in str(exc)


def test_evidence_contract_blocks_lineage_leakage_and_counts_coverage() -> None:
    module = load_phoenix_module("evidence_contract.py", "phoenix_evidence")
    first = phoenix_event()
    derived = phoenix_event(source_event_id="K123-summary", source_locator="file://summary")
    module.assert_lineage_disjoint([first], [phoenix_event(source_event_id="K999", lineage_id="K999")])
    try:
        module.assert_lineage_disjoint([first], [derived])
        assert False, "shared lineage was accepted"
    except ValueError as exc:
        assert "K123" in str(exc)
    counts = module.coverage_counts([first, derived])
    assert counts == {
        "event_rows": 2, "independent_lineages": 1, "company_linked_rows": 2,
        "track_linked_rows": 2, "fully_linked_rows": 2, "observed_time_rows": 0,
    }
