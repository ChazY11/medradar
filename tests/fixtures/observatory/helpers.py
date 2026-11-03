"""Shared synthetic harness for the Live Observatory adapter tests.

Tier: **synthetic** — nothing here touches the network. ``FakeFetcher`` has the
same call contract as :class:`medradar.http.Fetcher` (``get_json(url, params,
refresh=...)``, a ``.stats`` dict and ``.max_requests``) but answers from canned
payloads, so the real collection engine (``adapter.run_source``) can be driven
end-to-end against a throwaway SQLite ledger in ``tmp_path``.

The canned payloads used by the tests are obviously synthetic (``NCT00000001``,
``"Synthetic pacemaker trial"``, ids like ``MED:90000001``); this module only
provides the plumbing so no test has to re-implement it.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Callable, Mapping

from medradar.http import BudgetExceeded
from medradar.observatory import records
from medradar.observatory.adapter import CollectContext
from medradar.observatory.ledger import ObservationLedger

#: Fixed collector clock for run 1; run 2 uses the later one so first_seen_at
#: being preserved is observable.
FIXED_NOW = "2026-11-03T12:00:00+00:00"
LATER_NOW = "2026-11-03T18:30:00+00:00"

Router = Callable[[str, dict[str, Any]], Any]


class FakeFetcher:
    """Deterministic stand-in for ``medradar.http.Fetcher`` (no network)."""

    def __init__(self, router: Router, *, max_requests: int = 40) -> None:
        self.router = router
        self.max_requests = int(max_requests)
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0, "errors": 0}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *_args: Any,
        refresh: bool = False,  # noqa: ARG002 - kept for API parity
    ) -> Any:
        query = dict(params or {})
        self.calls.append((url, query))
        if int(self.stats["requests"]) >= self.max_requests:
            raise BudgetExceeded(f"fake request budget {self.max_requests} exhausted")
        self.stats["requests"] += 1
        payload = self.router(url, query)
        if isinstance(payload, BaseException):
            self.stats["errors"] += 1
            raise payload
        return copy.deepcopy(payload)


def make_ledger(tmp_path: Any) -> ObservationLedger:
    """Throwaway ledger in ``tmp_path`` (never the real observatory database)."""
    return ObservationLedger(tmp_path / "observatory-test.sqlite")


def make_ctx(
    ledger: ObservationLedger,
    fetcher: FakeFetcher,
    *,
    now: str = FIXED_NOW,
    trigger: str = "test",
    **kwargs: Any,
) -> CollectContext:
    """A context with a silent logger and a fixed clock."""
    return CollectContext(
        fetcher=fetcher,
        ledger=ledger,
        run_id="test-context",
        trigger=trigger,
        now=now,
        log=lambda message: None,
        **kwargs,
    )


# ------------------------------------------------------------------ ledger reads
def observation(ledger: ObservationLedger, source: str, source_record_id: str) -> dict[str, Any]:
    row = ledger.observation_row(records.observation_id(source, source_record_id))
    assert row is not None, f"no observation for {source}:{source_record_id}"
    return row


def changes_for(ledger: ObservationLedger, source: str, source_record_id: str) -> list[dict[str, Any]]:
    return ledger.changes_for(records.observation_id(source, source_record_id))


def versions_for(ledger: ObservationLedger, source: str, source_record_id: str) -> list[dict[str, Any]]:
    return ledger.versions(records.observation_id(source, source_record_id))


def payload_of(version: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(str(version["payload"]))


def source_state(ledger: ObservationLedger, source: str) -> dict[str, Any]:
    return ledger.get_source_state(source) or {}


def committed_watermark(ledger: ObservationLedger, source: str) -> dict[str, Any]:
    raw = source_state(ledger, source).get("watermark")
    if not raw:
        return {}
    decoded = json.loads(raw) if isinstance(raw, str) else raw
    return decoded if isinstance(decoded, dict) else {}


def checkpoints_for(ledger: ObservationLedger, source: str, run_id: str) -> dict[str, str]:
    rows = ledger.con.execute(
        "SELECT scope, cursor FROM sync_checkpoint WHERE source=? AND run_id=?", (source, run_id)
    ).fetchall()
    return {str(row["scope"]): str(row["cursor"]) for row in rows}


def failures_for(ledger: ObservationLedger, source: str, run_id: str) -> list[dict[str, Any]]:
    rows = ledger.con.execute(
        "SELECT * FROM source_failure WHERE source=? AND run_id=?", (source, run_id)
    ).fetchall()
    return [dict(row) for row in rows]
