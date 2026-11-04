"""Offline tests for job identity, versioning and duplicate rules (WP2b, deliverable 1).

The rules under test are the mission's: a re-post is not new demand, a
disappearance is not a hire, a title-bearing slug is not identity, a description
edit is a revision, and ``first_seen_at`` is ours and write-once.

All tests are offline. The real collected sample is read (never modified) for the
in-sample duplicate check; every other case is synthetic.
"""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

import pytest

from medradar.recruitment import identity, records as rec

ROOT = Path(__file__).resolve().parents[1]
REAL_SAMPLE = ROOT / "experiments" / "innovation_signals_observatory" / "results" / "2026-11-04" / "jobs_medtronic.jsonl"


# --------------------------------------------------------------------- helpers
def make_obs(
    posting_id: str,
    *,
    title: str = "R&D Engineer I",
    description: str = "Design and development of surgical instruments for minimally invasive surgery.",
    location: str = "Galway, Ireland",
    first_seen_at: str = "2026-01-01T00:00:00+00:00",
    req: str | None = "R81338",
    slug: str | None = None,
    platform: str = rec.PLATFORM_WORKDAY,
    additional_locations: list[str] | None = None,
    content_sha256: str | None = None,
) -> rec.JobObservation:
    """A valid ``JobObservation`` built through the real contract (not a loose dict)."""
    obs = rec.JobObservation(
        company_key="medtronic",
        posting_id=posting_id,
        source_platform=platform,
        source_url=f"https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers/job/{posting_id}",
        job_title=title,
        job_description=description,
        job_location=location,
        additional_locations=list(additional_locations or []),
        source_posted_at="2026-01-01",
        source_posted_quality=rec.QUALITY_SOURCE_DATE,
        first_seen_at=first_seen_at,
        collection_status=rec.STATUS_COMPLETE,
        content_sha256=content_sha256,
        raw={
            "job_req_id": req,
            "job_posting_id_slug": slug or (title.replace(" ", "-") + f"_R{req}" if req else title.replace(" ", "-")),
            "opaque_posting_id": posting_id,
            "posting_id_kind": "id",
        },
    )
    return obs.finalise(fetched_at=first_seen_at, first_seen_at=first_seen_at)


@lru_cache(maxsize=1)
def _real_rows_cached() -> tuple[dict, ...]:
    if not REAL_SAMPLE.exists():
        return ()
    with REAL_SAMPLE.open(encoding="utf-8") as handle:
        return tuple(json.loads(line) for line in handle if line.strip())


def real_rows() -> list[dict]:
    return list(_real_rows_cached())


@lru_cache(maxsize=1)
def real_clusters() -> list[dict]:
    return identity.duplicate_clusters(real_rows())


@lru_cache(maxsize=1)
def real_dedup() -> dict:
    return identity.deduplicated_count(real_rows())


#: The superseded ``content_hash`` rule that run 1 of the collection used: it
#: preserved newlines (``normalise_text``), whereas the current rule collapses all
#: whitespace (``canonical_ws``). Only used to *prove provenance* of a snapshot.
_LEGACY_WS = re.compile(r"[ \t\u00a0]+")
_LEGACY_NL = re.compile(r"\n{3,}")


def legacy_content_hash(*, title, location, description) -> str:
    def legacy_normalise(text):
        if not text:
            return ""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = _LEGACY_WS.sub(" ", text)
        text = "\n".join(line.strip() for line in text.split("\n"))
        text = _LEGACY_NL.sub("\n\n", text)
        return text.strip()

    payload = {"title": legacy_normalise(title), "location": legacy_normalise(location),
               "description": legacy_normalise(description)}
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def states(result: dict) -> list[str]:
    return [event["state"] for event in result["events"]]


# ---------------------------------------------------------------- identity rules
class TestIdentity:
    def test_identity_is_the_opaque_posting_id_not_the_title_slug(self):
        renamed = make_obs(
            "opaque-1",
            title="Principal R&D Engineer",
            slug="Principal-R-D-Engineer_R81338-2",
        )
        original = make_obs("opaque-1", title="R&D Engineer I", slug="R-D-Engineer-I_R81338-1")

        # The title-bearing slug changed with the title; identity did not.
        assert identity.slug_title(original) != identity.slug_title(renamed)
        assert identity.canonical_posting_key(original) == identity.canonical_posting_key(renamed)

        basis = identity.identity_basis(renamed)
        assert basis["field"] == "posting_id"
        assert basis["fallback_used"] is False
        assert basis["source"] .startswith("opaque source id")

    def test_missing_posting_id_is_not_given_a_synthetic_identity(self):
        broken = rec.JobObservation(
            company_key="medtronic",
            posting_id="",
            source_platform=rec.PLATFORM_WORKDAY,
            source_url="https://example.invalid/1",
            job_title="Engineer",
        )
        with pytest.raises(ValueError, match="posting_id"):
            identity.canonical_posting_key(broken)

    def test_requisition_falls_back_to_the_slug_suffix(self):
        obs = make_obs("p1", req=None, slug="R-D-Engineer-I_R77874-2")
        obs.raw.pop("job_req_id", None)
        requisition = identity.requisition_key(obs)
        assert requisition["key"] == "R77874"
        assert requisition["source"] == "slug_suffix:job_posting_id_slug"

    def test_version_signature_uses_records_content_hash(self):
        obs = make_obs("p1")
        expected = rec.content_hash(title=obs.job_title, location=obs.job_location,
                                    description=obs.job_description)
        assert identity.version_signature(obs) == expected
        assert identity.version_evidence(obs)["recorded_agrees"] is True


# ----------------------------------------------------------------- versioning
class TestRevisions:
    def test_title_rename_is_a_revision_not_a_new_posting(self):
        before = make_obs("p1", title="R&D Engineer I", slug="R-D-Engineer-I_R81338-1")
        after = make_obs(
            "p1",
            title="Senior R&D Engineer",
            description="Design and development of surgical instruments. Five years experience required.",
            first_seen_at="2026-02-01T00:00:00+00:00",
            slug="Senior-R-D-Engineer_R81338-1",
        )

        result = identity.diff_snapshots([before], [after], observed_at="2026-02-01T00:00:00+00:00")

        assert states(result) == [identity.STATE_REVISION]
        event = result["events"][0]
        assert "title" in event["changed_fields"]
        assert "job_posting_id_slug" in event["changed_fields"]
        assert event["counts_as_new_demand"] is False
        assert result["demand"]["new_demand_events"] == 0
        assert result["counters"][identity.STATE_NEW] == 0

    def test_whitespace_only_rerender_is_unchanged(self):
        before = make_obs("p1")
        after = make_obs("p1",
                         description="Design  and development of surgical   instruments for minimally "
                                     "invasive surgery.",
                         first_seen_at="2026-02-01T00:00:00+00:00")
        # normalise_text collapses the whitespace runs, so the content hash is stable
        assert rec.normalise_text(before.job_description) == rec.normalise_text(after.job_description)
        result = identity.diff_snapshots([before], [after], observed_at="2026-02-01T00:00:00+00:00")
        assert states(result) == [identity.STATE_UNCHANGED]
        assert result["changed_event_count"] == 0

    def test_description_edit_is_a_revision(self):
        before = make_obs("p1")
        after = make_obs("p1", description="Design, develop and validate surgical instruments.",
                         first_seen_at="2026-02-01T00:00:00+00:00")
        result = identity.diff_snapshots([before], [after], observed_at="2026-02-01T00:00:00+00:00")
        event = result["events"][0]
        assert event["state"] == identity.STATE_REVISION
        assert "description" in event["changed_fields"]
        assert event["previous_version_signature"] != event["version_signature"]


# ------------------------------------------------------------------ duplicates
class TestDuplicates:
    def test_multi_city_copy_of_one_requisition_is_detected_and_not_demand(self):
        galway = make_obs("p1", req="R1", location="Galway, Ireland")
        phoenix = make_obs("p2", req="R1", location="Phoenix, Arizona, United States of America",
                           first_seen_at="2026-02-01T00:00:00+00:00")

        clusters = identity.duplicate_clusters([galway, phoenix])
        assert [cluster["cluster_kind"] for cluster in clusters] == [identity.CLUSTER_MULTI_CITY]
        cluster = clusters[0]
        assert set(cluster["posting_ids"]) == {"p1", "p2"}
        assert cluster["counts_as_new_demand"] is False
        assert cluster["same_requisition"] is True
        assert {member["job_location"] for member in cluster["members"]} == {
            "Galway, Ireland", "Phoenix, Arizona, United States of America"
        }

        result = identity.diff_snapshots([galway], [galway, phoenix],
                                         observed_at="2026-02-01T00:00:00+00:00")
        assert identity.STATE_MULTI_CITY in states(result)
        multi = next(event for event in result["events"] if event["state"] == identity.STATE_MULTI_CITY)
        assert multi["duplicate"]["location_comparison"] == "different"
        assert multi["counts_as_new_demand"] is False
        assert result["demand"]["new_demand_events"] == 0

    def test_same_city_repost_of_a_requisition_is_a_repost_not_demand(self):
        first = make_obs("p1", req="R1")
        second = make_obs("p2", req="R1", first_seen_at="2026-02-01T00:00:00+00:00")
        result = identity.diff_snapshots([first], [first, second], observed_at="2026-02-01T00:00:00+00:00")
        assert identity.STATE_REPOST in states(result)
        assert result["demand"]["new_demand_events"] == 0
        assert result["counters"][identity.STATE_REPOST] == 1

    def test_identical_content_under_two_ids_is_duplicate_republication(self):
        one = make_obs("p1", req="R1")
        two = make_obs("p2", req="R2", first_seen_at="2026-02-01T00:00:00+00:00")
        assert identity.version_signature(one) == identity.version_signature(two)

        clusters = identity.duplicate_clusters([one, two])
        assert [cluster["cluster_kind"] for cluster in clusters] == [identity.CLUSTER_DUPLICATE]

        result = identity.diff_snapshots([one], [one, two], observed_at="2026-02-01T00:00:00+00:00")
        assert identity.STATE_DUPLICATE in states(result)
        assert result["demand"]["new_demand_events"] == 0

    def test_identical_advert_with_a_different_requisition_is_flagged_undecidable(self):
        # Byte-identical advert under two requisitions: it may be a duplicated advert
        # or several simultaneous openings for the same role (multiple headcount).
        # The source cannot tell us, so it is not new demand and the ambiguity is kept.
        one = make_obs("p1", req="R1")
        two = make_obs("p2", req="R2", first_seen_at="2026-02-01T00:00:00+00:00")

        cluster = identity.duplicate_clusters([one, two])[0]
        assert cluster["cluster_kind"] == identity.CLUSTER_DUPLICATE
        assert cluster["same_requisition"] is False
        assert "multiple headcount" in cluster["ambiguity"]
        assert cluster["requisitions"] == ["R1", "R2"]

        result = identity.diff_snapshots([one], [one, two], observed_at="2026-02-01T00:00:00+00:00")
        event = next(event for event in result["events"] if event["state"] == identity.STATE_DUPLICATE)
        assert event["duplicate"]["same_requisition"] is False
        assert any("different requisition" in note for note in event["notes"])
        assert event["counts_as_new_demand"] is False

    def test_same_posting_on_two_platforms_is_a_multi_site_copy(self):
        workday = make_obs("p1", req="R1")
        phenom = make_obs("p9", req="R1", platform=rec.PLATFORM_PHENOM,
                          first_seen_at="2026-02-01T00:00:00+00:00")
        clusters = identity.duplicate_clusters([workday, phenom])
        assert identity.CLUSTER_MULTI_SITE in {cluster["cluster_kind"] for cluster in clusters}

        result = identity.diff_snapshots([workday], [workday, phenom],
                                         observed_at="2026-02-01T00:00:00+00:00")
        multi_site = [event for event in result["events"] if event["state"] == identity.STATE_MULTI_SITE]
        assert multi_site, states(result)
        assert multi_site[0]["duplicate"]["multi_site"] is True
        assert result["demand"]["new_demand_events"] == 0

    def test_same_posting_id_twice_in_one_snapshot_is_a_cluster_not_two_postings(self):
        first = make_obs("p1", req="R1")
        second = make_obs("p1", title="Something else", location="Elsewhere", req="R2")
        clusters = identity.duplicate_clusters([first, second])
        assert [cluster["cluster_kind"] for cluster in clusters] == [identity.CLUSTER_SAME_POSTING_ID]
        # the diff keeps the first and warns instead of inventing two postings
        result = identity.diff_snapshots([first], [first, second], observed_at="2026-02-01T00:00:00+00:00")
        assert any("duplicate identity" in warning for warning in result["warnings"])


# ------------------------------------------------------------- removal semantics
class TestRemovalIsNotAHire:
    def test_removal_is_recorded_and_never_inferred_as_a_hire(self):
        posted = make_obs("p1")
        result = identity.diff_snapshots([posted], [], observed_at="2026-03-01T00:00:00+00:00")
        assert states(result) == [identity.STATE_REMOVAL]
        event = result["events"][0]
        assert event["counts_as_new_demand"] is False
        assert "not a hire" in event["interpretation"].lower()
        assert result["demand"]["removal_events"] == 1
        assert result["demand"]["new_demand_events"] == 0

    def test_absence_from_an_incomplete_snapshot_is_not_a_removal(self):
        posted = make_obs("p1")
        result = identity.diff_snapshots([posted], [], observed_at="2026-03-01T00:00:00+00:00",
                                         current_complete=False)
        assert states(result) == [identity.STATE_ABSENCE_UNATTRIBUTED]
        assert result["counters"][identity.STATE_REMOVAL] == 0
        assert result["demand"]["removal_events"] == 0

    def test_removal_then_reappearance_of_the_same_identity_is_not_new_demand(self):
        posted = make_obs("p1", first_seen_at="2026-01-01T00:00:00+00:00")
        history = [{"observed_at": "2026-01-01T00:00:00+00:00", "observations": [posted]}]
        result = identity.diff_snapshots([], [posted], observed_at="2026-03-01T00:00:00+00:00",
                                         history=history)
        assert states(result) == [identity.STATE_REAPPEARANCE]
        event = result["events"][0]
        assert event["first_seen_at"] == "2026-01-01T00:00:00+00:00"
        assert event["first_seen_at_source"] == "history"
        assert event["counts_as_new_demand"] is False

    def test_repost_after_removal_under_a_new_id_is_flagged_as_repost(self):
        posted = make_obs("p1", req="R1", first_seen_at="2026-01-01T00:00:00+00:00")
        reposted = make_obs("p2", req="R1", first_seen_at="2026-03-01T00:00:00+00:00")
        history = [{"observed_at": "2026-01-01T00:00:00+00:00", "observations": [posted]}]
        result = identity.diff_snapshots([], [reposted], observed_at="2026-03-01T00:00:00+00:00",
                                         history=history)
        assert states(result) == [identity.STATE_REPOST]
        event = result["events"][0]
        assert event["duplicate"]["repost_after_removal"] is True
        assert event["counts_as_new_demand"] is False
        assert result["demand"]["new_demand_events"] == 0


# -------------------------------------------------------------- new demand rules
class TestNewDemand:
    def test_only_a_genuinely_new_posting_counts_as_demand(self):
        result = identity.diff_snapshots([], [make_obs("p1")], observed_at="2026-01-01T00:00:00+00:00")
        assert states(result) == [identity.STATE_NEW]
        assert result["events"][0]["counts_as_new_demand"] is True
        assert result["demand"]["new_demand_events"] == 1

    def test_new_posting_against_an_incomplete_previous_snapshot_is_not_demand(self):
        result = identity.diff_snapshots([], [make_obs("p1")], observed_at="2026-01-01T00:00:00+00:00",
                                         previous_complete=False)
        assert states(result) == [identity.STATE_NEW]
        assert result["events"][0]["counts_as_new_demand"] is False
        assert result["demand"]["new_demand_events"] == 0

    def test_new_posting_against_an_incomplete_current_snapshot_is_still_new(self):
        # completeness of the *current* snapshot governs removals, not additions
        result = identity.diff_snapshots([], [make_obs("p1")], observed_at="2026-01-01T00:00:00+00:00",
                                         current_complete=False)
        assert states(result) == [identity.STATE_NEW]
        assert result["events"][0]["counts_as_new_demand"] is True


# --------------------------------------------------------------- first_seen rules
class TestFirstSeen:
    def test_first_seen_at_is_preserved_and_a_rewrite_is_reported_not_applied(self):
        posted = make_obs("p1", first_seen_at="2026-01-01T00:00:00+00:00")
        reobserved = make_obs("p1", first_seen_at="2026-09-09T00:00:00+00:00")

        result = identity.diff_snapshots([posted], [reobserved],
                                         observed_at="2026-09-09T00:00:00+00:00")
        event = result["events"][0]
        assert event["first_seen_at"] == "2026-01-01T00:00:00+00:00"
        assert event["first_seen_at_conflict"] == {
            "canonical_posting_key": identity.canonical_posting_key(posted),
            "previous_first_seen_at": "2026-01-01T00:00:00+00:00",
            "current_first_seen_at": "2026-09-09T00:00:00+00:00",
        }
        assert result["first_seen_conflicts"]

    def test_reconcile_first_seen_carries_the_original_value_forward(self):
        posted = make_obs("p1", first_seen_at="2026-01-01T00:00:00+00:00")
        reobserved = make_obs("p1", first_seen_at="2026-09-09T00:00:00+00:00")
        reconciled = identity.reconcile_first_seen([posted], [reobserved])
        assert reconciled[0]["first_seen_at"] == "2026-01-01T00:00:00+00:00"
        # the input object is not mutated
        assert reobserved.first_seen_at == "2026-09-09T00:00:00+00:00"


# ---------------------------------------------------------------- vocabulary rules
class TestVocabulary:
    def test_change_vocabulary_is_closed_and_only_new_posting_is_demand(self):
        assert set(identity.DEDUP_VOCABULARY) == set(identity.CHANGE_STATES)
        demand_states = {state for state, entry in identity.DEDUP_VOCABULARY.items()
                         if entry["counts_as_new_demand"]}
        assert demand_states == {identity.STATE_NEW}
        assert "not a hire" in identity.INTERPRETATIONS[identity.STATE_REMOVAL].lower()
        assert "not new demand" in identity.INTERPRETATIONS[identity.STATE_REPOST].lower()

    def test_store_state_map_does_not_invent_a_second_vocabulary(self):
        assert set(identity.STORE_STATE_MAP) == set(identity.CHANGE_STATES)
        assert set(identity.STORE_STATE_MAP.values()) == {
            "NEW_POSTING", "UNCHANGED", "REVISION", "REMOVED", "REAPPEARED", "UNREADABLE"
        }

    def test_identity_rule_table_has_exactly_one_identity_field(self):
        identity_fields = [rule["field"] for rule in identity.IDENTITY_RULE_TABLE if rule["is_identity"]]
        assert identity_fields == ["posting_id"]

    def test_report_helpers_are_markdown(self):
        assert identity.IDENTITY_RULE_TABLE[-1]["field"] == "source_posted_at"
        assert "| state |" in identity.change_vocabulary_markdown()
        assert "posting_id" in identity.identity_rule_table_markdown()


# ------------------------------------------------------ content-hash provenance
class TestContentHashIntegrity:
    def test_agreement_detects_uniform_and_mixed_snapshots(self):
        good = make_obs("p1")
        assert identity.content_hash_agreement([good])["agree"] == 1
        assert identity.content_hash_agreement([good])["uniform"] is True

        stale = make_obs("p2")
        stale.content_sha256 = "0" * 64
        stale_report = identity.content_hash_agreement([stale])
        assert stale_report["disagree"] == 1 and stale_report["uniform"] is True

        mixed = identity.content_hash_agreement([good, stale])
        assert (mixed["agree"], mixed["disagree"]) == (1, 1)
        assert mixed["uniform"] is False

    def test_stored_hash_mismatch_does_not_create_a_false_revision(self):
        # The version signature is recomputed from the fields, so a snapshot hashed
        # under a superseded records.content_hash cannot turn every posting into a
        # revision; the mismatch is surfaced as provenance instead.
        before = make_obs("p1")
        after = make_obs("p1", first_seen_at="2026-02-01T00:00:00+00:00")
        after.content_sha256 = "0" * 64
        result = identity.diff_snapshots([before], [after], observed_at="2026-02-01T00:00:00+00:00")
        assert states(result) == [identity.STATE_UNCHANGED]
        assert result["content_hash_integrity"]["disagree"] >= 1
        assert result["content_hash_integrity"]["uniform"] is False


# ------------------------------------------------------------------ real sample
class TestRealSample:
    def test_real_sample_duplicate_clusters_collapse_the_raw_count(self):
        rows = real_rows()
        if not rows:
            pytest.skip("real sample not present in this checkout")
        clusters = real_clusters()
        dedup = real_dedup()
        assert dedup["raw_observations"] == len(rows)
        assert dedup["distinct_posting_ids"] == len({identity.canonical_posting_key(row) for row in rows})
        assert dedup["distinct_after_dedup"] <= dedup["distinct_posting_ids"]
        assert dedup["duplicate_observations"] == dedup["distinct_posting_ids"] - dedup["distinct_after_dedup"]
        assert dedup["duplicate_clusters"] == len(clusters)
        assert all(cluster["counts_as_new_demand"] is False for cluster in clusters)
        assert all(cluster["posting_ids"] for cluster in clusters)
        # the newest-40 subset had a multi-city copy; the full population must too
        kinds = {cluster["cluster_kind"] for cluster in clusters}
        assert kinds <= set(identity.CLUSTER_KINDS)
        assert identity.CLUSTER_MULTI_CITY in kinds or identity.CLUSTER_DUPLICATE in kinds

    def test_real_offset_pagination_duplicates_are_identical_reobservations(self):
        # Offset pagination is not a snapshot: a posting can be returned twice. That
        # must be the same posting observed twice, never one posting id reused for
        # different content.
        rows = real_rows()
        if not rows:
            pytest.skip("real sample not present in this checkout")
        groups: dict[str, list[dict]] = {}
        for row in rows:
            groups.setdefault(identity.canonical_posting_key(row), []).append(row)
        pagination_duplicates = {key: members for key, members in groups.items() if len(members) > 1}
        for key, members in pagination_duplicates.items():
            version_signatures = {identity.version_signature(member) for member in members}
            body_signatures = {identity.body_signature(member) for member in members}
            titles = {member.get("job_title") for member in members}
            assert len(version_signatures) == 1, f"posting id reused with different content: {key}"
            assert len(body_signatures) == 1
            assert len(titles) == 1
        assert len({identity.canonical_posting_key(row) for row in rows}) <= len(rows)
        assert all(identity.identity_basis(row)["fallback_used"] is False for row in rows)

    def test_real_duplicate_clusters_are_identical_adverts_with_audit_evidence(self):
        rows = real_rows()
        if not rows:
            pytest.skip("real sample not present in this checkout")
        duplicates = [cluster for cluster in real_clusters()
                      if cluster["cluster_kind"] == identity.CLUSTER_DUPLICATE]
        if not duplicates:
            pytest.skip("no duplicate-republication cluster in the current snapshot")
        for cluster in duplicates:
            assert len({member["posting_id"] for member in cluster["members"]}) == len(cluster["members"])
            # identical advert text, identical location; the ids differ
            assert len({member["body_signature"] for member in cluster["members"]}) == 1
            assert len({tuple(sorted(member["location_set"])) for member in cluster["members"]}) == 1
            assert cluster["same_requisition"] == (len(cluster["requisitions"]) == 1)
            if not cluster["same_requisition"]:
                assert "multiple headcount" in cluster["ambiguity"]
            assert cluster["counts_as_new_demand"] is False

    def test_real_content_hashes_are_uniformly_from_one_records_rule(self):
        # Provenance check: the committed snapshot must be hashed either entirely
        # under the current records.content_hash rule or entirely under the superseded
        # normalise_text rule (run 1 of the collection). A mixture is corruption.
        rows = real_rows()
        if not rows:
            pytest.skip("real sample not present in this checkout")
        current_flags = []
        legacy_flags = []
        for row in rows:
            stored = row["content_sha256"]
            current_flags.append(
                stored == rec.content_hash(title=row["job_title"], location=row["job_location"],
                                           description=row["job_description"])
            )
            legacy_flags.append(
                stored == legacy_content_hash(title=row["job_title"], location=row["job_location"],
                                              description=row["job_description"])
            )
        assert all(current_flags) or all(legacy_flags), (
            "mixed content-hash provenance: "
            f"current-rule {sum(current_flags)}/{len(rows)}, legacy-rule {sum(legacy_flags)}/{len(rows)}"
        )
        report = identity.content_hash_agreement(rows)
        assert report["checked"] == len(rows)
        assert report["missing"] == 0
        assert report["uniform"] is True
        assert report["agreement_rate"] in (0.0, 1.0)

    def test_real_sample_dedup_is_deterministic_and_json_serialisable(self):
        rows = real_rows()
        if not rows:
            pytest.skip("real sample not present in this checkout")
        first = identity.deduplicated_count(rows)
        second = identity.deduplicated_count(rows)
        assert first == second
        assert json.dumps(first, sort_keys=True)
