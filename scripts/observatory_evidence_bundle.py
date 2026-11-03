"""Generate the final Live Observatory evidence bundle (UTF-8 JSON, no shell pipes)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from medradar.observatory.lag import measure_lag, observation_lag  # noqa: E402
from medradar.observatory.ledger import ObservationLedger  # noqa: E402
from medradar.observatory.runner import reconcile, status_report  # noqa: E402

EVIDENCE = ROOT / "docs" / "observatory" / "evidence"
EVIDENCE.mkdir(parents=True, exist_ok=True)
LEDGER_PATH = ROOT / "data" / "observatory" / "observatory.sqlite"


def run_cli(args: list[str]) -> dict:
    proc = subprocess.run([sys.executable, "-m", "medradar", *args], cwd=ROOT,
                          capture_output=True, text=True)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"returncode": proc.returncode, "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-2000:]}


def write(name: str, payload) -> str:
    path = EVIDENCE / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return str(path.relative_to(ROOT))


def main() -> int:
    ledger = ObservationLedger(LEDGER_PATH, read_only=True)

    observations = []
    for row in ledger.con.execute(
        "SELECT o.observation_id, o.source, o.source_record_id, o.record_type, o.title,"
        " o.event_at, o.event_at_precision, o.published_at, o.published_at_precision,"
        " o.first_seen_at, o.last_checked_at, o.observation_origin, o.source_payload_hash,"
        " o.version_count, o.original_url,"
        " m.entity_id, m.entity_status, m.entity_method, m.track_id, m.track_status"
        " FROM observation o"
        " LEFT JOIN observation_mapping m ON m.observation_id=o.observation_id"
        " AND m.mapped_at=(SELECT MAX(mapped_at) FROM observation_mapping m2"
        "                  WHERE m2.observation_id=o.observation_id)"
        " ORDER BY o.first_seen_at, o.source"
    ).fetchall():
        item = dict(row)
        item["title"] = (item["title"] or "")[:160]
        lag = observation_lag(item)
        item["lag"] = {
            "measurable": lag["measurable"],
            "publish_to_first_seen_hours": lag["publish_to_first_seen_hours"],
            "event_to_first_seen_hours": lag["event_to_first_seen_hours"],
            "observed_later_than_event": lag["observed_later_than_event"],
        }
        observations.append(item)

    runs = [dict(row) for row in ledger.con.execute(
        "SELECT * FROM sync_run ORDER BY started_at").fetchall()]
    source_states = [dict(row) for row in ledger.con.execute(
        "SELECT * FROM source_state ORDER BY source").fetchall()]
    changes = [dict(row) for row in ledger.con.execute(
        "SELECT change_state, COUNT(*) AS n FROM observation_change GROUP BY change_state").fetchall()]

    counts = ledger.counts()
    lags = {source: measure_lag(ledger, source)
            for source in ("sec_edgar", "ctgov", "europepmc")}
    ledger.close()

    status = run_cli(["observatory", "status", "--json"])
    consistency = reconcile(ledger_path=LEDGER_PATH)

    bundle = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "ledger_path": str(LEDGER_PATH.relative_to(ROOT)),
        "counts": counts,
        "change_state_counts": {row["change_state"]: row["n"] for row in changes},
        "first_live_observation_at": counts.get("first_observation_at"),
        "measured_lag_by_source": lags,
        "run_history": runs,
        "source_states": source_states,
        "observations": observations,
        "status_report": status,
        "reconcile": consistency,
    }
    bundle_path = write("09_final_ledger_evidence.json", bundle)

    # replay demo: before the first observation and at the end of the collection
    before = run_cli(["observatory", "replay", "--as-of", "2026-11-03T14:00:00Z", "--json"])
    after = run_cli(["observatory", "replay", "--as-of", "2026-11-03T23:00:00Z", "--json"])

    def _compact_replay(payload: dict) -> dict:
        return {
            "as_of": payload.get("as_of"),
            "policy_zh": payload.get("policy_zh"),
            "total": payload.get("total"),
            "excluded_discovered_later": payload.get("excluded_discovered_later"),
            "items": [
                {
                    "observation_id": item.get("observation_id"),
                    "source": item.get("source"),
                    "title": (item.get("title") or "")[:120],
                    "event_at": item.get("event_at"),
                    "first_seen_at": item.get("first_seen_at"),
                    "version_seq": item.get("version_seq"),
                    "captured_at": item.get("captured_at"),
                    "payload_hash": item.get("payload_hash"),
                }
                for item in (payload.get("items") or [])[:5]
            ],
        }

    replay_path = write("10_replay_demo.json", {
        "before_first_observation": _compact_replay(before),
        "after_all_observation": _compact_replay(after),
    })

    # per-record lag evidence for the SEC records (the only hour-precise source)
    sec = [item for item in observations if item["source"] == "sec_edgar"]
    sec_path = write("11_sec_observation_timeline.json", sec)

    print(json.dumps({
        "bundle": bundle_path,
        "replay": replay_path,
        "sec_timeline": sec_path,
        "counts": counts,
        "change_states": bundle["change_state_counts"],
        "sec_lag": lags["sec_edgar"],
        "consistency_ok": consistency["ok"],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
