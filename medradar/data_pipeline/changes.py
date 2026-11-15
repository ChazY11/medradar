"""Record-level change detection and the removal policy.

A record is identified by ``source_id + official_record_identity``. The content hash is
computed before display truncation. Therefore:

* a new official identity is ADDED;
* the same identity with a different content hash is UPDATED (not a second event);
* an identity absent from one complete sweep is MISSING_ON_RECHECK, not deleted;
* it becomes REMOVED_CONFIRMED only after repeated complete sweeps plus an exact-ID
  recheck, unless the query scope changed, in which case the state is
  QUERY_SCOPE_CHANGED and nothing is deleted.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .model import ChangeType, RecordState
from .normalize import canonical_json, compact_event, content_hash, snapshot_hash

METADATA_FIELDS = {
    "first_observed_at",
    "last_synced_at",
    "source_updated_at",
    "record_state",
    "missing_count",
    "collection_scopes",
    "content_hash",
    "snapshot_hash",
}
DISPLAY_ONLY_FIELDS = {"title", "official_url"}
MAX_DIFF_VALUE = 400


@dataclass
class ChangeSet:
    changes: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    events: dict[str, dict[str, Any]] = field(default_factory=dict)


def _truncate(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_DIFF_VALUE:
        return value[: MAX_DIFF_VALUE - 1] + "…"
    if isinstance(value, list) and len(value) > 30:
        return [ _truncate(item) for item in value[:30] ] + ["…"]
    if isinstance(value, dict):
        return {str(key): _truncate(item) for key, item in list(value.items())[:30]}
    return value


def _comparable(value: Any) -> str:
    # FDA list fields such as recall k_numbers have no meaningful display order. Compare
    # them as sets; a reorder is not a content revision.
    if isinstance(value, list):
        return canonical_json(sorted(str(item) for item in value))
    return canonical_json(value)


def _legacy_equivalent(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    """Compare only the fields that existed in a legacy compact snapshot.

    A legacy snapshot stored a *display projection*, not the full source record: selected
    raw fields, already truncated. It cannot be compared to a newly collected full-record
    hash without claiming every record changed. On the first reconciliation we therefore
    compare the previous visible projection to the new visible projection and establish the
    full hash without inventing 91,457 revisions. Subsequent reconciliations use full hashes.
    """
    old_compact, _ = compact_event(previous)
    new_compact, _ = compact_event(current)
    old_raw = old_compact.get("raw") or {}
    new_raw = new_compact.get("raw") or {}
    for key in old_compact:
        if key in METADATA_FIELDS or key in DISPLAY_ONLY_FIELDS or key in ("raw", "snapshot_hash"):
            continue
        if _comparable(old_compact.get(key)) != _comparable(new_compact.get(key)):
            return False
    for key in old_raw:
        if key == "event_date_as_published":
            continue
        if key not in new_raw:
            return False
        old_value = old_raw.get(key)
        new_value = new_raw.get(key)
        if key == "k_numbers" and isinstance(old_value, list) and isinstance(new_value, list):
            # The legacy collector capped this list at five entries (`k_numbers[:5]`).
            # Extra official K references are a display-projection upgrade, not proof of a
            # source revision on the first reconciliation. Full hashes handle later edits.
            if set(old_value).issubset(set(new_value)):
                continue
            return False
        if _comparable(old_value) != _comparable(new_value):
            return False
    return True


def changed_fields(
    previous: dict[str, Any], current: dict[str, Any], *, legacy_projection: bool = False
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if legacy_projection:
        previous, _ = compact_event(previous)
        current, _ = compact_event(current)
    previous_raw = previous.get("raw") or {}
    current_raw = current.get("raw") or {}
    if legacy_projection:
        keys = set(previous) - METADATA_FIELDS - DISPLAY_ONLY_FIELDS - {"raw", "snapshot_hash"}
        raw_keys = set(previous_raw) - {"event_date_as_published"}
    else:
        keys = (set(previous) | set(current)) - METADATA_FIELDS - DISPLAY_ONLY_FIELDS
        raw_keys = (set(previous_raw) | set(current_raw)) - {"event_date_as_published"}
    for key in sorted(keys):
        if key == "raw":
            continue
        old = previous.get(key)
        new = current.get(key)
        if _comparable(old) != _comparable(new):
            fields[key] = {"previous": _truncate(old), "current": _truncate(new)}
    for key in sorted(raw_keys):
        old = previous_raw.get(key)
        new = current_raw.get(key)
        if (
            legacy_projection and key == "k_numbers" and isinstance(old, list) and isinstance(new, list)
            and set(old).issubset(set(new))
        ):
            continue
        if _comparable(old) != _comparable(new):
            fields["raw." + key] = {"previous": _truncate(old), "current": _truncate(new)}
    return fields


def change_id(
    source_id: str, event_id: str, change_type: str, previous_hash: str | None,
    new_hash: str | None,
) -> str:
    payload = "|".join([
        source_id, event_id, change_type, previous_hash or "", new_hash or "",
    ])
    return "chg_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _change_row(
    *,
    source_id: str,
    event: dict[str, Any],
    change_type: ChangeType,
    detected_at: str,
    source_updated_at: str | None,
    previous_hash: str | None,
    new_hash: str | None,
    previous_snapshot_id: str | None,
    candidate_snapshot_id: str,
    fields: dict[str, Any],
    evidence: dict[str, Any],
    organization_key: str | None = None,
) -> dict[str, Any]:
    compact, _flags = compact_event(event)
    return {
        "change_id": change_id(source_id, event["event_id"], change_type.value, previous_hash, new_hash),
        "source_id": source_id,
        "official_record_id": str(event.get("official_id") or ""),
        "event_id": event["event_id"],
        "change_type": change_type.value,
        "detected_at": detected_at,
        "source_updated_at": source_updated_at,
        "previous_content_hash": previous_hash,
        "new_content_hash": new_hash,
        "previous_snapshot_id": previous_snapshot_id,
        "candidate_snapshot_id": candidate_snapshot_id,
        "changed_fields": fields,
        "evidence": evidence,
        "organization_key": organization_key,
        "applicant_name": event.get("applicant_name"),
        "event_type": event.get("event_type"),
        "event_date": event.get("event_date"),
        "record": compact,
        "content_hash": new_hash,
    }


def _first_seen(
    event: dict[str, Any],
    previous: dict[str, Any] | None,
    observation: dict[str, Any] | None,
    previous_collected_at: str | None,
    now: str,
) -> str:
    if observation and observation.get("first_observed_at"):
        return str(observation["first_observed_at"])
    if previous and previous.get("first_observed_at"):
        return str(previous["first_observed_at"])
    if previous and previous_collected_at:
        return previous_collected_at
    return now


def build_change_set(
    *,
    previous_events: Mapping[str, dict[str, Any]],
    candidate_events: dict[str, dict[str, Any]],
    changed_sources: Sequence[str],
    previous_snapshot_id: str | None,
    candidate_snapshot_id: str,
    detected_at: str,
    source_versions: Mapping[str, dict[str, Any]],
    observations: Mapping[str, dict[str, Any]],
    previous_collected_at: str | None,
    scope_changed: bool,
    recheck_found: Mapping[str, dict[str, Any]],
    removal_confirmations: int,
    unresolved_reason: str | None = None,
    rebaseline: bool = False,
) -> ChangeSet:
    """Compare, apply the removal policy, and return a candidate + staged ledger rows.

    ``candidate_events`` is mutated for missing records that are deliberately retained.
    It is never mutated for a confirmed removal (the record leaves the candidate).
    """
    source_set = set(changed_sources)
    result = ChangeSet(events=dict(candidate_events))
    summary = {
        "added": 0,
        "updated": 0,
        "removed_confirmed": 0,
        "unchanged": 0,
        "missing_on_recheck": 0,
        "unresolved": 0,
        "records_seen": 0,
        "rebaselined": 0,
    }
    candidate = result.events
    previous = dict(previous_events)

    for source_id in sorted(source_set):
        source_events = [event_id for event_id, event in candidate.items() if event.get("source_id") == source_id]
        source_previous = [event_id for event_id, event in previous.items() if event.get("source_id") == source_id]
        candidate_ids = set(source_events)
        previous_ids = set(source_previous)
        source_version = source_versions.get(source_id) or {}
        source_updated_at = source_version.get("official_last_updated")

        for event_id in sorted(candidate_ids):
            event = candidate[event_id]
            old = previous.get(event_id)
            observation = observations.get(event_id)
            first_seen = _first_seen(event, old, observation, previous_collected_at, detected_at)
            new_hash = str(event.get("content_hash") or content_hash(event))
            event["content_hash"] = new_hash
            event["first_observed_at"] = first_seen
            event["last_synced_at"] = detected_at
            event["source_updated_at"] = source_updated_at
            event["record_state"] = RecordState.ACTIVE.value
            event["missing_count"] = 0
            snapshot_payload, _flags = compact_event(event)
            event["snapshot_hash"] = snapshot_hash(snapshot_payload)
            summary["records_seen"] += 1

            if old is None:
                summary["added"] += 1
                result.changes.append(_change_row(
                    source_id=source_id, event=event, change_type=ChangeType.ADDED,
                    detected_at=detected_at, source_updated_at=source_updated_at,
                    previous_hash=None, new_hash=new_hash, previous_snapshot_id=previous_snapshot_id,
                    candidate_snapshot_id=candidate_snapshot_id, fields={},
                    evidence={
                        "official_url": event.get("official_url"),
                        "endpoint": source_version.get("endpoint"),
                        "collection_scopes": event.get("collection_scopes") or [],
                        "previous_snapshot_id": previous_snapshot_id,
                        "candidate_snapshot_id": candidate_snapshot_id,
                    },
                    organization_key=None,
                ))
            else:
                old_hash = str(old.get("content_hash") or content_hash(old))
                if rebaseline:
                    unchanged = _legacy_equivalent(old, event)
                    summary["rebaselined"] += 1
                else:
                    unchanged = old_hash == new_hash
                if not unchanged:
                    fields = changed_fields(old, event, legacy_projection=rebaseline)
                    summary["updated"] += 1
                    result.changes.append(_change_row(
                        source_id=source_id, event=event, change_type=ChangeType.UPDATED,
                        detected_at=detected_at, source_updated_at=source_updated_at,
                        previous_hash=old_hash, new_hash=new_hash,
                        previous_snapshot_id=previous_snapshot_id,
                        candidate_snapshot_id=candidate_snapshot_id, fields=fields,
                        evidence={
                            "official_url": event.get("official_url"),
                            "endpoint": source_version.get("endpoint"),
                            "collection_scopes": event.get("collection_scopes") or [],
                            "previous_snapshot_id": previous_snapshot_id,
                            "candidate_snapshot_id": candidate_snapshot_id,
                            "field_count": len(fields),
                        },
                        organization_key=None,
                    ))
                else:
                    summary["unchanged"] += 1

            result.observations.append({
                "source_id": source_id,
                "event_id": event_id,
                "official_record_id": str(event.get("official_id") or ""),
                "first_observed_at": first_seen,
                "last_seen_at": detected_at,
                "last_seen_snapshot_id": candidate_snapshot_id,
                "last_content_hash": new_hash,
                "state": RecordState.ACTIVE.value,
                "missing_count": 0,
                "last_missing_at": None,
                "organization_key": None,
                "applicant_name": event.get("applicant_name"),
                "event_type": event.get("event_type"),
                "event_date": event.get("event_date"),
            })

        missing_ids = sorted(previous_ids - candidate_ids)
        for event_id in missing_ids:
            old = previous[event_id]
            observation = observations.get(event_id) or {}
            old_hash = str(old.get("content_hash") or content_hash(old))
            first_seen = _first_seen(old, old, observation, previous_collected_at, detected_at)
            if event_id in recheck_found:
                reappeared = dict(recheck_found[event_id])
                reappeared["first_observed_at"] = first_seen
                reappeared["last_synced_at"] = detected_at
                reappeared["source_updated_at"] = source_updated_at
                reappeared["record_state"] = RecordState.ACTIVE.value
                reappeared["missing_count"] = 0
                reappeared["collection_scopes"] = old.get("collection_scopes") or []
                reappeared["content_hash"] = str(reappeared.get("content_hash") or content_hash(reappeared))
                snapshot_payload, _flags = compact_event(reappeared)
                reappeared["snapshot_hash"] = snapshot_hash(snapshot_payload)
                candidate[event_id] = reappeared
                fields = changed_fields(old, reappeared, legacy_projection=rebaseline)
                if rebaseline and _legacy_equivalent(old, reappeared):
                    summary["unchanged"] += 1
                    summary["rebaselined"] += 1
                else:
                    summary["updated"] += 1
                    result.changes.append(_change_row(
                        source_id=source_id, event=reappeared, change_type=ChangeType.UPDATED,
                        detected_at=detected_at, source_updated_at=source_updated_at,
                        previous_hash=old_hash, new_hash=reappeared["content_hash"],
                        previous_snapshot_id=previous_snapshot_id,
                        candidate_snapshot_id=candidate_snapshot_id, fields=fields,
                        evidence={"official_url": reappeared.get("official_url"), "reason": "reappeared_on_exact_recheck",
                                  "previous_snapshot_id": previous_snapshot_id, "candidate_snapshot_id": candidate_snapshot_id},
                    ))
                result.observations.append({
                    "source_id": source_id, "event_id": event_id,
                    "official_record_id": str(reappeared.get("official_id") or ""),
                    "first_observed_at": first_seen, "last_seen_at": detected_at,
                    "last_seen_snapshot_id": candidate_snapshot_id,
                    "last_content_hash": reappeared["content_hash"], "state": RecordState.ACTIVE.value,
                    "missing_count": 0, "last_missing_at": None, "organization_key": None,
                    "applicant_name": reappeared.get("applicant_name"),
                    "event_type": reappeared.get("event_type"), "event_date": reappeared.get("event_date"),
                })
                continue

            if scope_changed or unresolved_reason:
                reason = "query_scope_changed" if scope_changed else unresolved_reason
                retained = dict(old)
                retained["first_observed_at"] = first_seen
                retained["last_synced_at"] = detected_at
                retained["source_updated_at"] = source_updated_at
                retained["record_state"] = (
                    RecordState.QUERY_SCOPE_CHANGED.value if scope_changed else RecordState.UNKNOWN.value
                )
                retained["missing_count"] = int(observation.get("missing_count") or 0) + 1
                candidate[event_id] = retained
                summary["unresolved"] += 1
                result.changes.append(_change_row(
                    source_id=source_id, event=retained, change_type=ChangeType.UNRESOLVED,
                    detected_at=detected_at, source_updated_at=source_updated_at,
                    previous_hash=old_hash, new_hash=old_hash,
                    previous_snapshot_id=previous_snapshot_id,
                    candidate_snapshot_id=candidate_snapshot_id,
                    fields={}, evidence={
                        "reason": reason,
                        "official_url": retained.get("official_url"),
                        "previous_snapshot_id": previous_snapshot_id,
                        "candidate_snapshot_id": candidate_snapshot_id,
                        "missing_count": retained["missing_count"],
                    },
                ))
                result.observations.append({
                    "source_id": source_id, "event_id": event_id,
                    "official_record_id": str(retained.get("official_id") or ""),
                    "first_observed_at": first_seen, "last_seen_at": observation.get("last_seen_at") or detected_at,
                    "last_seen_snapshot_id": observation.get("last_seen_snapshot_id") or previous_snapshot_id,
                    "last_content_hash": old_hash, "state": retained["record_state"],
                    "missing_count": retained["missing_count"], "last_missing_at": detected_at,
                    "organization_key": None, "applicant_name": retained.get("applicant_name"),
                    "event_type": retained.get("event_type"), "event_date": retained.get("event_date"),
                })
                continue

            missing_count = int(observation.get("missing_count") or 0) + 1
            if missing_count >= max(1, int(removal_confirmations)):
                summary["removed_confirmed"] += 1
                candidate.pop(event_id, None)
                result.changes.append(_change_row(
                    source_id=source_id, event=old, change_type=ChangeType.REMOVED_CONFIRMED,
                    detected_at=detected_at, source_updated_at=source_updated_at,
                    previous_hash=old_hash, new_hash=None,
                    previous_snapshot_id=previous_snapshot_id,
                    candidate_snapshot_id=candidate_snapshot_id,
                    fields={}, evidence={
                        "reason": "absent_from_complete_scoped_sweep_and_exact_recheck",
                        "missing_count": missing_count,
                        "official_url": old.get("official_url"),
                        "previous_snapshot_id": previous_snapshot_id,
                        "candidate_snapshot_id": candidate_snapshot_id,
                    },
                ))
                result.observations.append({
                    "source_id": source_id, "event_id": event_id,
                    "official_record_id": str(old.get("official_id") or ""),
                    "first_observed_at": first_seen, "last_seen_at": observation.get("last_seen_at") or detected_at,
                    "last_seen_snapshot_id": observation.get("last_seen_snapshot_id") or previous_snapshot_id,
                    "last_content_hash": old_hash, "state": RecordState.CONFIRMED_REMOVED.value,
                    "missing_count": missing_count, "last_missing_at": detected_at,
                    "organization_key": None, "applicant_name": old.get("applicant_name"),
                    "event_type": old.get("event_type"), "event_date": old.get("event_date"),
                })
            else:
                retained = dict(old)
                retained["first_observed_at"] = first_seen
                retained["last_synced_at"] = detected_at
                retained["source_updated_at"] = source_updated_at
                retained["record_state"] = RecordState.MISSING_ON_RECHECK.value
                retained["missing_count"] = missing_count
                candidate[event_id] = retained
                summary["missing_on_recheck"] += 1
                result.changes.append(_change_row(
                    source_id=source_id, event=retained, change_type=ChangeType.MISSING_ON_RECHECK,
                    detected_at=detected_at, source_updated_at=source_updated_at,
                    previous_hash=old_hash, new_hash=old_hash,
                    previous_snapshot_id=previous_snapshot_id,
                    candidate_snapshot_id=candidate_snapshot_id,
                    fields={}, evidence={
                        "reason": "absent_from_one_complete_scoped_sweep; retained pending a second confirmation",
                        "missing_count": missing_count,
                        "official_url": retained.get("official_url"),
                        "previous_snapshot_id": previous_snapshot_id,
                        "candidate_snapshot_id": candidate_snapshot_id,
                    },
                ))
                result.observations.append({
                    "source_id": source_id, "event_id": event_id,
                    "official_record_id": str(retained.get("official_id") or ""),
                    "first_observed_at": first_seen,
                    "last_seen_at": observation.get("last_seen_at") or detected_at,
                    "last_seen_snapshot_id": observation.get("last_seen_snapshot_id") or previous_snapshot_id,
                    "last_content_hash": old_hash, "state": RecordState.MISSING_ON_RECHECK.value,
                    "missing_count": missing_count, "last_missing_at": detected_at,
                    "organization_key": None, "applicant_name": retained.get("applicant_name"),
                    "event_type": retained.get("event_type"), "event_date": retained.get("event_date"),
                })

    result.summary = summary
    return result
