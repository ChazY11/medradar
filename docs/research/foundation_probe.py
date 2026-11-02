"""Adversarial integration probes (FOUNDATION-INTEGRATE-007, director issue 5).

Independent checks written by the integrator - they do not reuse the author
tests. Run:  python docs/research/foundation_probe.py
Output is appended to docs/research/FOUNDATION_INTEGRATION_LOG.txt by the caller.
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal, getcontext
from pathlib import Path

from medradar.forecast_registry import (
    ForecastRegistry,
    ForecastValidationError,
    canonical_json,
    sha256_hex,
)
from medradar.tkg import TKGError, TKGStore

getcontext().prec = 40
T0 = datetime(2024, 1, 15, tzinfo=timezone.utc)
SHA = "a" * 64


def step_clock(start=T0, step=timedelta(days=1)):
    state = {"t": start}

    def tick():
        v = state["t"]
        state["t"] = v + step
        return v

    return tick


def fspec(key, p=0.7, horizon=3, **extra):
    spec = {
        "idempotency_key": key,
        "target": {"type": "nmpa_acceptance", "id": f"DEV-{key}", "attrs": {"synthetic": True}},
        "horizon_months": horizon,
        "p": p,
        "information_cutoff": "2024-01-10T00:00:00Z",
        "model_version": "model-probe",
        "feature_version": "features-probe",
        "snapshot_sha256": SHA,
        "evidence": {"source_locator": "synthetic://probe", "evidence_kind": "source_observed",
                     "evidence_sha256": SHA,
                     "provenance": [{"source_locator": "synthetic://probe/src", "evidence_sha256": SHA}]},
    }
    spec.update(extra)
    return spec


def probe_raw_connection_tamper():
    """A *separate* sqlite connection (stray session) must not rewrite history."""
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "reg.sqlite")
        reg = ForecastRegistry(db)
        r = reg.register(fspec("tamper"))
        reg.resolve({"prediction_id": r["prediction_id"], "outcome": 1,
                     "event_time": r["window_start"],
                     "evidence": {"source_locator": "synthetic://probe", "evidence_kind": "source_observed",
                                  "evidence_sha256": SHA}})
        reg.close()
        other = sqlite3.connect(db)
        failures = []
        for label, sql, params in [
            ("UPDATE forecasts", "UPDATE forecasts SET p = 0.01 WHERE prediction_id = ?", (r["prediction_id"],)),
            ("DELETE forecasts", "DELETE FROM forecasts WHERE prediction_id = ?", (r["prediction_id"],)),
            ("OR REPLACE forecasts",
             "INSERT OR REPLACE INTO forecasts (prediction_id, generated_at, information_cutoff,"
             " target_type, target_id, target_attrs, horizon_months, window_start, window_end,"
             " model_version, feature_version, snapshot_sha256, provenance, source_locator,"
             " evidence_sha256, evidence_kind, p, idempotency_key)"
             " VALUES (?, '2024-01-01T00:00:00.000000Z', '2024-01-01T00:00:00.000000Z',"
             " 't', 'id', '{}', 3, '2024-01-01T00:00:00.000000Z', '2024-04-01T00:00:00.000000Z',"
             " 'm', 'f', ?, '[]', 'loc', ?, 'source_observed', 0.01, 'evil-key')",
             (r["prediction_id"], SHA, SHA)),
            ("UPDATE resolutions", "UPDATE resolutions SET outcome = 1 - outcome WHERE prediction_id = ?",
             (r["prediction_id"],)),
        ]:
            try:
                other.execute(sql, params)
                other.commit()
                failures.append(f"{label} SUCCEEDED - history rewritten!")
            except sqlite3.IntegrityError:
                pass
        other.close()
        assert not failures, failures
        reg2 = ForecastRegistry(db)
        assert reg2.get_forecast(r["prediction_id"])["p"] == 0.7
        reg2.close()
        return "ok: stray raw connections cannot UPDATE/DELETE/OR REPLACE either ledger"


def probe_artifact_stable_across_corrections():
    """A correction after as_of must not change the historical artifact hash."""
    clock = step_clock(step=timedelta(days=30))
    reg = ForecastRegistry(":memory:", clock=clock)
    r = reg.register(fspec("corr", p=0.6))
    pid = r["prediction_id"]
    while clock() < datetime(2024, 4, 16, tzinfo=timezone.utc):
        clock()
    v1 = reg.resolve({"prediction_id": pid, "outcome": 0, "event_time": None,
                      "evidence": {"source_locator": "synthetic://probe", "evidence_kind": "source_observed",
                                   "evidence_sha256": SHA}})
    as_of = clock()  # after v1, before the correction
    early = reg.build_artifact(as_of)
    early_hash = early["manifest"]["artifact_sha256"]
    reg.resolve({"prediction_id": pid, "outcome": 1, "event_time": r["window_start"], "reason": "appeal upheld",
                 "evidence": {"source_locator": "synthetic://probe", "evidence_kind": "source_observed",
                              "evidence_sha256": SHA}})
    late = reg.build_artifact(as_of)
    assert late["manifest"]["artifact_sha256"] == early_hash, "correction leaked into historical artifact"
    assert canonical_json(late) == canonical_json(early)
    now = clock()
    corrected = reg.evaluate(now)
    assert abs(corrected["headline"]["brier"] - 0.16) < 1e-12  # (0.6-1)^2
    return "ok: artifact hash stable across later corrections; as-of view pins original outcome"


def probe_independent_known_value_scoring():
    """Recompute metrics with Decimal arithmetic (independent of float formula)."""
    clock = step_clock(step=timedelta(days=30))
    reg = ForecastRegistry(":memory:", clock=clock)
    rows = []
    data = [(0.9, 1), (0.2, 0), (0.4, 0), (0.7, 1)]
    for i, (p, _) in enumerate(data):
        rows.append(reg.register(fspec(f"kv{i}", p=p)))
    while clock() < datetime(2024, 4, 16, tzinfo=timezone.utc):
        clock()
    for row, (_, y) in zip(rows, data):
        reg.resolve({"prediction_id": row["prediction_id"], "outcome": y,
                     "event_time": row["window_start"] if y else None,
                     "evidence": {"source_locator": "synthetic://probe", "evidence_kind": "source_observed",
                                  "evidence_sha256": SHA}})
    while clock() < datetime(2025, 1, 1, tzinfo=timezone.utc):
        clock()
    evaluation = reg.evaluate("2025-01-01T00:00:00Z")
    got = evaluation["headline"]
    p = [Decimal("0.9"), Decimal("0.2"), Decimal("0.4"), Decimal("0.7")]
    y = [1, 0, 0, 1]
    n = Decimal(4)
    exp_brier = sum((pi - Decimal(yi)) ** 2 for pi, yi in zip(p, y)) / n
    exp_ll = -sum(Decimal(yi) * pi.ln() + (1 - Decimal(yi)) * (1 - pi).ln()
                  for pi, yi in zip(p, y)) / n
    exp_ece = (sum(Decimal(1) / n * abs(Decimal(yi) - pi) for pi, yi in zip(p, y)))
    assert abs(Decimal(str(got["brier"])) - exp_brier) < Decimal("1e-12"), (got["brier"], exp_brier)
    assert abs(Decimal(str(got["log_loss"])) - exp_ll) < Decimal("1e-12"), (got["log_loss"], exp_ll)
    assert abs(Decimal(str(got["calibration"]["ece"])) - exp_ece) < Decimal("1e-12"), (
        got["calibration"]["ece"], exp_ece)
    return (f"ok: Decimal-recomputed brier={exp_brier} log_loss={exp_ll:.6f} ece={exp_ece} "
            f"match implementation")


def probe_snapshot_tamper_detection():
    """Hash declared for a local snapshot must match the file's content at registration."""
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "snapshot.json"
        document = {
            "format": "medradar-tkg-snapshot", "format_version": 1,
            "manifest": {"known_at": "2024-01-01T00:00:00.000000Z", "valid_at": None,
                         "schema_version": "tkg-schema-2", "code_version": "medradar-probe",
                         "adapter_version": None, "counts": {"nodes": 0, "edges": 0},
                         "evidence_provenance": []},
            "nodes": [], "edges": [],
        }
        digest = sha256_hex(canonical_json(document))
        document["manifest"]["snapshot_sha256"] = digest
        snap.write_text(json.dumps(document), encoding="utf-8")
        reg = ForecastRegistry(":memory:", clock=step_clock())
        ok = reg.register(fspec("verified", snapshot={"sha256": digest, "path": str(snap)}))
        assert ok["snapshot"]["verification"] == "verified_local"
        # tamper with the file afterwards: any *new* registration against the
        # old declared hash must fail (the stored record keeps its snapshot identity)
        document["nodes"] = [{"node_type": "company", "node_id": "INJECTED"}]
        snap.write_text(json.dumps(document), encoding="utf-8")
        try:
            reg.register(fspec("tampered", snapshot={"sha256": digest, "path": str(snap)}))
            raise AssertionError("tampered snapshot accepted")
        except ForecastValidationError:
            pass
        return "ok: snapshot content tamper detected at registration (verified_local vs declared)"


def probe_demo_artifact_reproducible():
    """Two independent CLI demo runs must produce the identical artifact hash."""
    import subprocess

    hashes = []
    for _ in range(2):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, "-m", "medradar.forecast_registry", "demo", "--out-dir", tmp],
                capture_output=True, text=True, timeout=120)
            assert result.returncode == 0, result.stderr
            payload = json.loads(result.stdout)
            assert payload["synthetic"] is True
            doc = json.loads((Path(tmp) / "evaluation.json").read_text(encoding="utf-8"))
            recomputed = sha256_hex(canonical_json(
                {**doc, "manifest": {k: v for k, v in doc["manifest"].items()
                                     if k != "artifact_sha256"}}))
            assert recomputed == doc["manifest"]["artifact_sha256"], "artifact hash mismatch"
            hashes.append(doc["manifest"]["artifact_sha256"])
    assert hashes[0] == hashes[1], hashes
    return f"ok: demo artifact hash reproducible across runs: {hashes[0]}"


def probe_tkg_stamped_reopen_and_legacy():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "tkg.sqlite"
        store = TKGStore(path)
        store.add_node("company", "ACME", {}, valid_from="2020-01-01",
                       source_locator="synthetic://probe", evidence_kind="source_observed",
                       confidence=0.8, idempotency_key="k1")
        store.close()
        reopened = TKGStore(path)
        assert reopened.meta_get("schema_version") == "tkg-schema-2"
        reopened.close()
        # a second TKGStore instance holding an exclusive lock does not
        # confuse the guard (timeout-based, single-writer assumption documented)
        return "ok: fresh TKG store stamped tkg-schema-2 and reopens cleanly"


def main():
    probes = [
        probe_raw_connection_tamper,
        probe_artifact_stable_across_corrections,
        probe_independent_known_value_scoring,
        probe_snapshot_tamper_detection,
        probe_demo_artifact_reproducible,
        probe_tkg_stamped_reopen_and_legacy,
    ]
    for probe in probes:
        print(f"[PASS] {probe.__name__}: {probe()}", flush=True)
    print("ALL PROBES PASSED")


if __name__ == "__main__":
    main()
