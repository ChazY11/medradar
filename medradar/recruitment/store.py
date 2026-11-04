"""Append-only observation store for the recruitment lane.

A job posting is not a row that gets overwritten. It is an *observation*: what a
source said, when it said it, and when we first saw it. This store is the smallest
thing that preserves those three facts across repeated collection runs:

  * **append-only** — every run appends; nothing is edited in place, so the history
    of what we saw is recoverable;
  * **write-once identity time** — ``first_seen_at`` is fixed the first time a posting
    is ingested and is never moved by a later run (a re-observation is not a new job);
  * **revision detection** — a content-hash change under the same posting identity is a
    ``REVISION``, not a new posting and not new demand;
  * **removal is a state, not an inference** — a posting absent from a complete
    snapshot becomes ``REMOVED`` with the time it was noticed. It does **not** mean the
    role was filled: the source does not say why a posting disappears;
  * **failure is not absence** — a run that could not read a posting must pass the
    posting id as *unreadable*, not omit it, or the store would record a fetch failure
    as a removal. Callers supply ``seen_ids`` and ``unreadable_ids`` separately.

This deliberately mirrors the semantics of ``medradar.observatory`` (append-only
observations, NEW/UPDATED/REMOVED, write-once first-seen) without touching that
tested schema; migrating this lane onto the shared ledger is a named follow-up
(``docs/NINETY_DAY_PLAN.zh-CN.md``) rather than a half-migration now.

Files under ``root``:

  ``observations.jsonl``  one full record per ingest; the latest line per ``obs_id`` wins
  ``changes.jsonl``       append-only state-transition events
  ``runs.jsonl``          one summary line per collection run
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from . import records as rec

# ---------------------------------------------------------------- closed vocabulary
STATE_NEW = "NEW_POSTING"
STATE_UNCHANGED = "UNCHANGED"
STATE_REVISION = "REVISION"
STATE_REMOVED = "REMOVED"
STATE_REAPPEARED = "REAPPEARED"
STATE_UNREADABLE = "UNREADABLE"
#: The content-hash *rule* changed since the stored record was written, so the two hashes
#: are not comparable. This is recorded as an explicit re-baseline instead of being
#: reported as a REVISION: otherwise a one-line change to the normalisation would look
#: like every posting in the corpus being edited at once.
STATE_HASH_RULE_CHANGED = "HASH_RULE_REBASELINED"
STATES = (STATE_NEW, STATE_UNCHANGED, STATE_REVISION, STATE_REMOVED, STATE_REAPPEARED,
          STATE_UNREADABLE, STATE_HASH_RULE_CHANGED)

STATE_LABELS_ZH = {
    STATE_NEW: "新增观察",
    STATE_UNCHANGED: "无变化",
    STATE_REVISION: "描述修订",
    STATE_REMOVED: "本次未见（下架/关闭/迁移，原因未知）",
    STATE_REAPPEARED: "重新出现",
    STATE_UNREADABLE: "本次无法读取（不是下架）",
    STATE_HASH_RULE_CHANGED: "内容哈希规则变更（重新建立基线，不视为修订）",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a truncated trailing line (crash) must not lose the file
    return out


class ObservationStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.observations_path = self.root / "observations.jsonl"
        self.changes_path = self.root / "changes.jsonl"
        self.runs_path = self.root / "runs.jsonl"

    # ------------------------------------------------------------------- reading
    def current(self) -> dict[str, dict]:
        """Latest stored record per observation id."""
        latest: dict[str, dict] = {}
        for row in _read_jsonl(self.observations_path):
            obs_id = row.get("obs_id")
            if obs_id:
                latest[obs_id] = row
        return latest

    def changes(self) -> list[dict]:
        return _read_jsonl(self.changes_path)

    # ------------------------------------------------------------------- writing
    def ingest(self, observations: Iterable[rec.JobObservation], *,
               complete_snapshot: bool = True,
               unreadable_ids: Iterable[str] = (),
               run_meta: Mapping[str, object] | None = None) -> dict:
        """Merge one collection snapshot into the store.

        ``complete_snapshot`` says whether this snapshot is the *whole* posting
        population that was readable. Only then may absent postings be marked REMOVED —
        a partial page fetch must never look like a wave of job closures. When it is
        False, absence is simply not evaluated.
        """
        observations = list(observations)
        started_at = _now()
        previous = self.current()
        seen: dict[str, rec.JobObservation] = {}
        for obs in observations:
            if obs.obs_id in seen:
                # offset pagination can return the same posting twice in one run
                continue
            seen[obs.obs_id] = obs

        events: list[dict] = []
        written: list[dict] = []
        counts = {state: 0 for state in STATES}

        for obs_id, obs in seen.items():
            prior = previous.get(obs_id)
            payload = obs.to_dict()
            if prior is None:
                payload["first_seen_at"] = obs.first_seen_at or _now()
                state = STATE_NEW
            else:
                payload["first_seen_at"] = prior.get("first_seen_at")  # write-once
                prior_rule = prior.get("hash_rule_version")
                if prior_rule and prior_rule != rec.HASH_RULE_VERSION:
                    state = STATE_HASH_RULE_CHANGED
                elif prior.get("status") == STATE_REMOVED:
                    state = STATE_REAPPEARED
                elif prior.get("content_sha256") != obs.content_sha256:
                    state = STATE_REVISION
                else:
                    state = STATE_UNCHANGED
            payload["status"] = state
            payload["last_checked_at"] = _now()
            written.append(payload)
            counts[state] += 1
            events.append({
                "event_id": f"{obs_id}:{state}:{_now()}",
                "obs_id": obs_id,
                "company_key": obs.company_key,
                "posting_id": obs.posting_id,
                "state": state,
                "detected_at": _now(),
                "first_seen_at": payload["first_seen_at"],
                "content_sha256": obs.content_sha256,
                "previous_content_sha256": (prior or {}).get("content_sha256"),
                "hash_rule_version": obs.hash_rule_version,
                "previous_hash_rule_version": (prior or {}).get("hash_rule_version"),
                "source_url": obs.source_url,
            })

        for obs_id in unreadable_ids:
            if obs_id in seen:
                continue
            counts[STATE_UNREADABLE] += 1
            events.append({"event_id": f"{obs_id}:{STATE_UNREADABLE}:{_now()}", "obs_id": obs_id,
                           "state": STATE_UNREADABLE, "detected_at": _now(),
                           "note": "the source could not be read this run; this is not a removal"})

        if complete_snapshot:
            for obs_id, prior in previous.items():
                if obs_id in seen or obs_id in set(unreadable_ids):
                    continue
                if prior.get("status") == STATE_REMOVED:
                    continue
                counts[STATE_REMOVED] += 1
                payload = dict(prior)
                payload["status"] = STATE_REMOVED
                payload["last_checked_at"] = _now()
                written.append(payload)
                events.append({"event_id": f"{obs_id}:{STATE_REMOVED}:{_now()}", "obs_id": obs_id,
                               "company_key": prior.get("company_key"),
                               "posting_id": prior.get("posting_id"),
                               "state": STATE_REMOVED, "detected_at": _now(),
                               "first_seen_at": prior.get("first_seen_at"),
                               "source_url": prior.get("source_url"),
                               "note": "absent from a complete snapshot; the source does not say why"})

        self._append(self.observations_path, written)
        self._append(self.changes_path, events)
        summary = {
            "run_id": f"run-{started_at}",
            "started_at": started_at,
            "finished_at": _now(),
            "complete_snapshot": complete_snapshot,
            "n_observations_ingested": len(seen),
            "n_events": len(events),
            "counts": counts,
            "meta": dict(run_meta or {}),
            "note": ("UNCHANGED/REVISION are re-observations of a known posting; REMOVED means "
                     "'not seen in a complete snapshot', never 'the role was filled'"),
        }
        self._append(self.runs_path, [summary])
        return summary

    @staticmethod
    def _append(path: Path, rows: list[dict]) -> None:
        if not rows:
            return
        with path.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    # ------------------------------------------------------------------ reporting
    def summary(self) -> dict:
        current = self.current()
        by_status: dict[str, int] = {}
        by_company: dict[str, int] = {}
        for row in current.values():
            status = row.get("status", "UNKNOWN")
            by_status[status] = by_status.get(status, 0) + 1
            company = row.get("company_key", "UNKNOWN")
            by_company[company] = by_company.get(company, 0) + 1
        changes = self.changes()
        by_state: dict[str, int] = {}
        for event in changes:
            state = event.get("state", "UNKNOWN")
            by_state[state] = by_state.get(state, 0) + 1
        return {
            "n_current": len(current),
            "by_status": by_status,
            "by_company": by_company,
            "n_change_events": len(changes),
            "change_events_by_state": by_state,
            "runs": len(_read_jsonl(self.runs_path)),
        }
