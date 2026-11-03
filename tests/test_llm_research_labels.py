"""Tests for the read-only label registry over the 69 early-signal evidence packets.

These tests do three things:

* prove the **current** data state mechanically (69 packets, zero human-confirmed
  labels, one under-represented deep-case company) instead of asserting it from
  memory;
* prove the loader is genuinely read-only;
* prove that an AI label — whether the existing rubric pre-annotation or the
  separate AI review tier — can never be counted as human ground truth.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from experiments.local_llm_event_extraction import labels
from experiments.local_llm_event_extraction.labels import (
    LabelState,
    PacketLabel,
    assess_data_readiness,
    assess_pit_readiness,
    label_state_report,
    load_label_state,
)

STUDY_DIR = labels.DEFAULT_STUDY_DIR
WORKSHEET_COLUMNS = [
    "packet_id",
    "origin",
    "priority",
    "company",
    "technology_track",
    "stratum",
    "event_or_trial_date",
    "clearance_or_record",
    "product_code",
    "mapped_track",
    "third_source_status",
    "third_source_lead_days",
    "evidence_summary",
    "agent_preliminary_label",
    "rule_fired",
    "human_label",
    "human_reason",
    "independent_confirmation",
    "reviewer",
    "reviewed_at",
]


def _write_worksheet(root: Path, rows: list[dict[str, str]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with (root / "HUMAN_REVIEW_WORKSHEET.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=WORKSHEET_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in WORKSHEET_COLUMNS})


def _write_ai_review(root: Path, records: list[dict[str, object]]) -> None:
    target = root / "ai_review"
    target.mkdir(parents=True, exist_ok=True)
    with (target / "AI_EVIDENCE_REVIEW.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ----------------------------------------------------------------- the real study
@pytest.mark.skipif(not STUDY_DIR.is_dir(), reason="study artifacts not present in this checkout")
def test_real_study_has_69_packets_and_zero_human_labels() -> None:
    state = load_label_state()
    assert state.n_packets == 69
    assert state.human_confirmed == 0
    assert state.counts_by_tier.get("unlabelled", 0) == 69
    assert "ai_preliminary" not in state.counts_by_tier


@pytest.mark.skipif(not STUDY_DIR.is_dir(), reason="study artifacts not present in this checkout")
def test_machine_preannotation_never_counts_as_human_truth() -> None:
    state = load_label_state()
    # The worksheet carries agent rubric labels on most packets; they are machine
    # output, so the human tier stays empty no matter how many exist.
    assert state.machine_preannotated > 0
    assert state.human_confirmed == 0
    for packet in state.packets:
        if packet.label_tier in ("human_confirmed", "expert_adjudicated"):
            assert packet.human_label, "a human-tier packet must have a recorded human label"


@pytest.mark.skipif(not STUDY_DIR.is_dir(), reason="study artifacts not present in this checkout")
def test_data_readiness_is_not_ready_with_explicit_blockers() -> None:
    readiness = assess_data_readiness(load_label_state())
    assert readiness.status == "NOT_READY"
    assert readiness.ready is False
    codes = " ".join(readiness.blockers)
    assert "NO_HUMAN_CONFIRMED_LABELS" in codes
    # Dräger has zero worksheet rows; that is a coverage blocker, not a detail.
    assert "COMPANY_UNDER_REPRESENTED(draeger=0" in codes
    assert readiness.evidence["human_confirmed"] == 0
    assert readiness.evidence["min_human_labels"] >= 1


@pytest.mark.skipif(not STUDY_DIR.is_dir(), reason="study artifacts not present in this checkout")
def test_company_counts_match_the_worksheet() -> None:
    state = load_label_state()
    assert state.counts_by_company.get("medtronic") == 21
    assert state.counts_by_company.get("philips") == 23
    assert state.counts_by_company.get("ge_healthcare") == 16
    assert state.counts_by_company.get("mindray") == 9
    assert "draeger" not in state.counts_by_company


@pytest.mark.skipif(not STUDY_DIR.is_dir(), reason="study artifacts not present in this checkout")
def test_pit_readiness_is_consistent_with_the_audit_artifact() -> None:
    audit = json.loads((STUDY_DIR / "EVIDENCE_TIME_AUDIT.json").read_text(encoding="utf-8"))
    readiness = assess_pit_readiness()
    non_a = [
        name
        for name, info in (audit.get("source_tiers") or {}).items()
        if str((info or {}).get("tier", "")).upper() != "A"
    ]
    unresolved = audit.get("unresolved") or {}
    if non_a or unresolved:
        assert readiness.status == "PARTIAL"
    else:
        assert readiness.status == "READY"
    # Never READY-by-accident: the status must be one of the declared values.
    assert readiness.status in labels.READINESS_STATUSES
    assert readiness.kind == "PIT"


def test_loader_is_read_only() -> None:
    before = {
        path.name: (_sha(path), path.stat().st_mtime_ns)
        for path in STUDY_DIR.glob("*")
        if path.is_file()
    }
    load_label_state()
    label_state_report()
    after = {
        path.name: (_sha(path), path.stat().st_mtime_ns)
        for path in STUDY_DIR.glob("*")
        if path.is_file()
    }
    assert before == after


def test_report_is_json_serialisable_and_marked_read_only() -> None:
    report = label_state_report()
    assert report["read_only"] is True
    assert report["data_readiness"]["status"] in labels.READINESS_STATUSES
    assert report["pit_readiness"]["status"] in labels.READINESS_STATUSES
    # The per-packet detail is deliberately excluded from the report payload.
    assert "packets" not in report["label_state"]
    json.dumps(report)  # must not raise


# ------------------------------------------------------------- synthetic variants
def test_missing_study_directory_yields_an_unready_empty_state(tmp_path: Path) -> None:
    state = load_label_state(tmp_path)
    assert state.n_packets == 0
    assert state.human_confirmed == 0
    assert assess_data_readiness(state).status == "NOT_READY"
    assert assess_pit_readiness(tmp_path).status == "UNKNOWN"
    assert "EVIDENCE_TIME_AUDIT_MISSING" in assess_pit_readiness(tmp_path).blockers


def test_human_labels_are_counted_at_their_tier(tmp_path: Path) -> None:
    _write_worksheet(
        tmp_path,
        [
            {
                "packet_id": "P-1",
                "company": "medtronic",
                "human_label": "Confirmed Shift",
                "human_reason": "reviewed against the clearance record",
                "independent_confirmation": "third source",
                "reviewer": "human-1",
                "reviewed_at": "2026-11-04",
            },
            {"packet_id": "P-2", "company": "philips"},
        ],
    )
    state = load_label_state(tmp_path)
    assert state.n_packets == 2
    assert state.human_confirmed == 1
    first = next(packet for packet in state.packets if packet.packet_id == "P-1")
    assert first.label_tier == "human_confirmed"
    assert first.has_independent_confirmation is True
    second = next(packet for packet in state.packets if packet.packet_id == "P-2")
    assert second.label_tier == "unlabelled"
    assert second.human_status == "PENDING_HUMAN_REVIEW"


def test_ai_review_labels_are_ai_preliminary_and_never_gold(tmp_path: Path) -> None:
    _write_worksheet(
        tmp_path,
        [{"packet_id": "P-1", "company": "medtronic"}, {"packet_id": "P-2", "company": "philips"}],
    )
    _write_ai_review(
        tmp_path,
        [
            {
                "packet_id": "P-1",
                "review": {
                    "label": "False Signal / No Confirmed Shift",
                    "label_authority": "ai_evidence_review_v1",
                    "status": "AI_ADJUDICATED",
                },
            }
        ],
    )
    state = load_label_state(tmp_path)
    assert state.ai_review_present is True
    assert state.ai_review_records == 1
    assert state.ai_preliminary == 1
    assert state.human_confirmed == 0
    readiness = assess_data_readiness(state)
    assert readiness.status == "NOT_READY"
    assert any(
        blocker.startswith("NO_HUMAN_CONFIRMED_LABELS") for blocker in readiness.blockers
    )
    # The AI label must be visible but must not be attributed to a human tier.
    packet = next(item for item in state.packets if item.packet_id == "P-1")
    assert packet.label_tier == "ai_preliminary"
    assert packet.human_label is None


def test_ready_path_is_reachable_with_enough_human_labels() -> None:
    packets = tuple(
        PacketLabel(
            packet_id=f"P-{index}",
            company=company,
            technology_track="patient_monitoring",
            human_status="HUMAN_CONFIRMED",
            human_label="Confirmed Shift",
            ai_label=None,
            label_tier="human_confirmed",
        )
        for index in range(60)
        for company in ("medtronic", "ge_healthcare", "philips", "draeger", "mindray")
    )
    state = LabelState(
        packets=packets,
        counts_by_tier={"human_confirmed": len(packets)},
        counts_by_company={
            company: 60
            for company in ("medtronic", "ge_healthcare", "philips", "draeger", "mindray")
        },
        ai_review_present=False,
        ai_review_records=0,
        study_dir="/synthetic",
    )
    readiness = assess_data_readiness(state)
    assert readiness.status == "READY"
    assert readiness.blockers == ()


def test_path_escape_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(labels, "WORKSHEET_NAME", "../../outside.csv")
    with pytest.raises(ValueError, match="outside the study directory"):
        load_label_state(tmp_path)
