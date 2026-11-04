"""Synthetic tier — append-only recruitment observation store (Phase 4).

The store is where the programme's time discipline is actually enforced. These tests
pin the four rules that a later analysis would otherwise silently violate:

1. `first_seen_at` is write-once (a re-observation is not a new posting);
2. a content-hash change under the same identity is a REVISION, not a new posting;
3. absence from a *complete* snapshot is REMOVED — and REMOVED never means "filled";
4. a posting that could not be read is UNREADABLE, never REMOVED, and absence is not
   evaluated at all for a partial snapshot.
"""
from __future__ import annotations

import json

from medradar.recruitment import records as rec
from medradar.recruitment.store import ObservationStore


def _obs(pid: str, *, title="R&D Engineer I", description="Design catheters.", fetched_at="2026-11-04T10:00:00+00:00"):
    return rec.JobObservation(
        company_key="medtronic",
        posting_id=pid,
        source_platform=rec.PLATFORM_WORKDAY,
        source_url=f"https://example.invalid/{pid}",
        job_title=title,
        job_description=description,
        job_location="Galway, Ireland",
        source_posted_at="2026-11-01",
        source_posted_quality=rec.QUALITY_SOURCE_DATE,
    ).finalise(fetched_at=fetched_at)


def test_first_seen_at_is_never_moved_by_a_later_run(tmp_path):
    store = ObservationStore(tmp_path)
    first = store.ingest([_obs("p1", fetched_at="2026-11-04T10:00:00+00:00")])
    assert first["counts"]["NEW_POSTING"] == 1

    second = store.ingest([_obs("p1", fetched_at="2026-11-05T10:00:00+00:00")])
    assert second["counts"]["UNCHANGED"] == 1
    row = store.current()[_obs("p1").obs_id]
    assert row["first_seen_at"] == "2026-11-04T10:00:00+00:00"   # not the second run's clock
    assert row["last_checked_at"].startswith("2026-11-05") or row["last_checked_at"] > "2026-11-04"


def test_a_description_edit_is_a_revision_not_a_new_posting(tmp_path):
    store = ObservationStore(tmp_path)
    store.ingest([_obs("p1", description="Design catheters.")])
    summary = store.ingest([_obs("p1", description="Design catheters. Must hold ISO 13485 experience.")])
    assert summary["counts"]["REVISION"] == 1
    assert summary["counts"]["NEW_POSTING"] == 0
    events = [e for e in store.changes() if e["state"] == "REVISION"]
    assert len(events) == 1
    assert events[0]["content_sha256"] != events[0]["previous_content_sha256"]
    # identity is unchanged across the revision
    assert len(store.current()) == 1


def test_absence_from_a_complete_snapshot_is_removed_and_the_note_says_why_it_is_not_a_hire(tmp_path):
    store = ObservationStore(tmp_path)
    store.ingest([_obs("p1"), _obs("p2")])
    summary = store.ingest([_obs("p1")], complete_snapshot=True)
    assert summary["counts"]["REMOVED"] == 1
    removed = [e for e in store.changes() if e["state"] == "REMOVED"]
    assert len(removed) == 1
    assert "does not say why" in removed[0]["note"]
    assert store.current()[_obs("p2").obs_id]["status"] == "REMOVED"


def test_partial_snapshot_never_marks_removals(tmp_path):
    store = ObservationStore(tmp_path)
    store.ingest([_obs("p1"), _obs("p2"), _obs("p3")])
    summary = store.ingest([_obs("p1")], complete_snapshot=False)
    assert summary["counts"]["REMOVED"] == 0
    # p2's *last observed* state stays what it was; absence was not evaluated
    assert store.current()[_obs("p2").obs_id]["status"] == "NEW_POSTING"


def test_unreadable_is_not_a_removal(tmp_path):
    store = ObservationStore(tmp_path)
    store.ingest([_obs("p1"), _obs("p2")])
    summary = store.ingest([_obs("p1")], complete_snapshot=True,
                           unreadable_ids=[_obs("p2").obs_id])
    assert summary["counts"]["REMOVED"] == 0
    assert summary["counts"]["UNREADABLE"] == 1
    # the stored state is untouched: a failed read is not evidence about the posting
    assert store.current()[_obs("p2").obs_id]["status"] == "NEW_POSTING"


def test_reappearance_after_removal_is_flagged(tmp_path):
    store = ObservationStore(tmp_path)
    store.ingest([_obs("p1")])
    store.ingest([], complete_snapshot=True)          # p1 disappeared
    assert store.current()[_obs("p1").obs_id]["status"] == "REMOVED"
    summary = store.ingest([_obs("p1")], complete_snapshot=True)   # came back
    assert summary["counts"]["REAPPEARED"] == 1


def test_duplicate_rows_inside_one_run_are_collapsed(tmp_path):
    store = ObservationStore(tmp_path)
    summary = store.ingest([_obs("p1"), _obs("p1")])
    assert summary["n_observations_ingested"] == 1
    assert summary["counts"]["NEW_POSTING"] == 1


def test_a_content_hash_rule_change_is_a_rebaseline_not_a_corpus_wide_revision(tmp_path):
    """A one-line change to the hash rule must not look like every posting being edited.

    This is not hypothetical: during Phase 4 the canonicalisation was tightened
    (`normalise_text` -> `canonical_ws`) *while a collection was running*, and the store
    would otherwise have reported 992 simultaneous REVISIONs.
    """
    store = ObservationStore(tmp_path)
    old = _obs("p1")
    old.hash_rule_version = "content_sha256_normalise_text_v1"
    store.ingest([old])
    summary = store.ingest([_obs("p1")])          # current rule
    assert summary["counts"]["REVISION"] == 0
    assert summary["counts"]["HASH_RULE_REBASELINED"] == 1
    events = [e for e in store.changes() if e["state"] == "HASH_RULE_REBASELINED"]
    assert events and events[0]["previous_hash_rule_version"] == "content_sha256_normalise_text_v1"


def test_store_is_append_only_on_disk(tmp_path):
    store = ObservationStore(tmp_path)
    store.ingest([_obs("p1")])
    store.ingest([_obs("p1", description="changed")])
    lines = store.observations_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2                       # both observations remain on disk
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["first_seen_at"] == second["first_seen_at"]
    assert first["content_sha256"] != second["content_sha256"]
    assert store.summary()["n_current"] == 1
