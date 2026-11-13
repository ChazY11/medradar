"""Read-only adapter over MedRadar's existing early-signal evidence packets.

Why this module exists
----------------------
The local-LLM experiment needs labelled documents.  MedRadar has 69 evidence
packets, and they are exactly the wrong thing to reach for carelessly:

* they are a **convenience sample** selected for study feasibility, not a random
  sample of documents;
* every one of them is ``PENDING_HUMAN_REVIEW``; the ``agent_preliminary_label``
  column is a machine rubric output, and the separate AI review tier is an
  ``AI_ADJUDICATED`` label — neither is human truth;
* they are *case packets* (a company x track x later clearance), not raw
  documents waiting for an extractor, so they cannot be dropped into an extraction
  benchmark without a document-level derivation step that does not exist yet.

So this module answers exactly one question, mechanically and reproducibly:

    How many labels are research-grade *today*, and what is missing?

The answer is currently **zero human-confirmed labels**, and that fact must be
derived from the files rather than remembered.  Everything here is read-only:
it opens files for reading, never writes, never migrates, never "cleans up" an
artifact, and never promotes an AI label to a human tier.

Two separate readiness questions are answered, and both matter:

``DATA_READY``  do human-confirmed labels exist in enough quantity and variety to
                train and to evaluate an extractor?
``PIT_READY``   is the *availability* time of each source reconstructed well
                enough that a document could have been observed at a historical
                decision time?  Event dates are not publication dates.

Both are reported as ``NOT_READY``/``PARTIAL`` with their evidence, and a caller
may not silently upgrade them.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STUDY_DIR = REPO_ROOT / "research" / "studies" / "early_signal_5firms"

WORKSHEET_NAME = "HUMAN_REVIEW_WORKSHEET.csv"
CASE_CANDIDATES_NAME = "CASE_CANDIDATES.json"
SMALL_SAMPLE_NAME = "CASE_PACKETS_SMALL_SAMPLE_V2.json"
EVIDENCE_TIME_AUDIT_NAME = "EVIDENCE_TIME_AUDIT.json"
AI_REVIEW_NAME = Path("ai_review") / "AI_EVIDENCE_REVIEW.jsonl"

HUMAN_STATES = frozenset({"HUMAN_CONFIRMED", "EXPERT_ADJUDICATED"})
AI_STATES = frozenset({"AI_ADJUDICATED", "AI_PRELIMINARY", "AGENT_PRELIMINARY"})
PENDING_STATES = frozenset({"PENDING_HUMAN_REVIEW", ""})

READINESS_STATUSES = ("READY", "PARTIAL", "NOT_READY", "UNKNOWN")


def _tier_from_human_status(status: str | None) -> str:
    """Map a recorded human-review state to a contract label tier (fail closed)."""
    value = (status or "").strip().upper()
    if value in HUMAN_STATES:
        return "human_confirmed" if value == "HUMAN_CONFIRMED" else "expert_adjudicated"
    if value in AI_STATES:
        # An AI label is a weak prior, never ground truth.
        return "ai_preliminary"
    return "unlabelled"


def _contained(path: Path, root: Path) -> Path:
    """Refuse to follow a path that escapes the study directory."""
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"refusing to read outside the study directory: {resolved}")
    return resolved


# ----------------------------------------------------------------------- records
@dataclass(frozen=True)
class PacketLabel:
    """One packet's label state, as recorded on disk (never interpreted upward)."""

    packet_id: str
    company: str | None
    technology_track: str | None
    human_status: str | None
    human_label: str | None
    ai_label: str | None
    label_tier: str
    origin: str | None = None
    stratum: str | None = None
    has_independent_confirmation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "packet_id": self.packet_id,
            "company": self.company,
            "technology_track": self.technology_track,
            "human_status": self.human_status,
            "human_label": self.human_label,
            "ai_label": self.ai_label,
            "label_tier": self.label_tier,
            "origin": self.origin,
            "stratum": self.stratum,
            "has_independent_confirmation": self.has_independent_confirmation,
        }


@dataclass(frozen=True)
class DataReadiness:
    """Structured readiness verdict; blockers are stable codes, not prose."""

    kind: str
    status: str
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.status == "READY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "status": self.status,
            "ready": self.ready,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "evidence": dict(self.evidence),
        }


# ------------------------------------------------------------------------ loading
def _read_worksheet(study_dir: Path) -> list[dict[str, str]]:
    path = _contained(study_dir / WORKSHEET_NAME, study_dir)
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_json(study_dir: Path, name: str | Path) -> dict[str, Any] | None:
    path = _contained(study_dir / name, study_dir)
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else None


def _read_ai_review(study_dir: Path) -> list[dict[str, Any]]:
    """Read the AI review tier if it exists locally.

    On this branch it does not (the AI review is committed on a separate branch by
    another agent); the loader reports its absence instead of guessing.  When it
    does exist, its labels are recorded as ``ai_preliminary`` and never used as
    gold.
    """
    path = _contained(study_dir / AI_REVIEW_NAME, study_dir)
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
    return records


def _read_packets(study_dir: Path) -> dict[str, dict[str, Any]]:
    """Merge the case-packet files; V2 wins where both describe a packet."""
    packets: dict[str, dict[str, Any]] = {}
    candidates = _read_json(study_dir, CASE_CANDIDATES_NAME) or {}
    for case in candidates.get("cases") or []:
        if isinstance(case, dict) and case.get("packet_id"):
            packets[str(case["packet_id"])] = dict(case)
    for name in ("CASE_PACKETS_SMALL_SAMPLE.json", SMALL_SAMPLE_NAME):
        payload = _read_json(study_dir, name) or {}
        for packet in payload.get("packets") or []:
            if isinstance(packet, dict):
                key = str(packet.get("event_id") or packet.get("packet_id") or "")
                if key:
                    merged = dict(packets.get(key, {}))
                    merged.update(packet)
                    packets[key] = merged
    return packets


# ------------------------------------------------------------------------ public
@dataclass(frozen=True)
class LabelState:
    """Everything derivable today about the 69 packets' label tiers."""

    packets: tuple[PacketLabel, ...]
    counts_by_tier: Mapping[str, int]
    counts_by_company: Mapping[str, int]
    ai_review_present: bool
    ai_review_records: int
    study_dir: str

    @property
    def n_packets(self) -> int:
        return len(self.packets)

    @property
    def human_confirmed(self) -> int:
        return self.counts_by_tier.get("human_confirmed", 0) + self.counts_by_tier.get(
            "expert_adjudicated", 0
        )

    @property
    def ai_preliminary(self) -> int:
        return self.counts_by_tier.get("ai_preliminary", 0)

    @property
    def unlabelled(self) -> int:
        return self.counts_by_tier.get("unlabelled", 0)

    @property
    def machine_preannotated(self) -> int:
        """Packets carrying some machine label (rubric or AI review), of any kind.

        Reported separately from :attr:`ai_preliminary` because a triage rubric text
        such as *"Uncertain (agent-preliminary)"* is not an event label and must not
        be counted as one.
        """
        return sum(1 for packet in self.packets if packet.ai_label)

    def to_dict(self) -> dict[str, Any]:
        return {
            "study_dir": self.study_dir,
            "n_packets": self.n_packets,
            "counts_by_tier": dict(self.counts_by_tier),
            "counts_by_company": dict(self.counts_by_company),
            "human_confirmed": self.human_confirmed,
            "ai_preliminary": self.ai_preliminary,
            "unlabelled": self.unlabelled,
            "machine_preannotated": self.machine_preannotated,
            "ai_review_present": self.ai_review_present,
            "ai_review_records": self.ai_review_records,
            "packets": [packet.to_dict() for packet in self.packets],
        }


def load_label_state(study_dir: str | Path | None = None) -> LabelState:
    """Read the label tiers without modifying anything.

    Raises :class:`ValueError` only for a path that escapes the resolved study
    directory; a missing packet file yields an empty state rather than an
    exception, because "the artifact is not here" is itself information.
    """
    root = Path(study_dir) if study_dir is not None else DEFAULT_STUDY_DIR
    rows = _read_worksheet(root)
    packets = _read_packets(root)
    ai_records = _read_ai_review(root)

    ai_by_packet: dict[str, str] = {}
    for record in ai_records:
        review = record.get("review") or {}
        label = review.get("label") if isinstance(review, dict) else None
        packet_id = str(record.get("packet_id") or "")
        if packet_id and label:
            ai_by_packet[packet_id] = str(label)

    records: list[PacketLabel] = []
    for row in rows:
        packet_id = (row.get("packet_id") or "").strip()
        if not packet_id:
            continue
        human_label = (row.get("human_label") or "").strip()
        # The worksheet records a human decision only when `human_label` is filled;
        # an empty cell is the literal on-disk state PENDING_HUMAN_REVIEW.
        human_status = "HUMAN_CONFIRMED" if human_label else "PENDING_HUMAN_REVIEW"
        tier = _tier_from_human_status(human_status)
        agent_preliminary = (row.get("agent_preliminary_label") or "").strip()
        if tier == "unlabelled" and packet_id in ai_by_packet:
            tier = "ai_preliminary"
        packet_meta = packets.get(packet_id, {})
        records.append(
            PacketLabel(
                packet_id=packet_id,
                company=(row.get("company") or packet_meta.get("company") or None),
                technology_track=(
                    row.get("technology_track") or packet_meta.get("technology_track") or None
                ),
                human_status="PENDING_HUMAN_REVIEW" if not human_label else "HUMAN_CONFIRMED",
                human_label=human_label or None,
                ai_label=ai_by_packet.get(packet_id) or (agent_preliminary or None),
                label_tier=tier,
                origin=(row.get("origin") or None),
                stratum=(row.get("stratum") or None),
                has_independent_confirmation=bool(
                    (row.get("independent_confirmation") or "").strip()
                ),
            )
        )
    # A packet that exists only in the case files still contributes an unlabelled row.
    known = {record.packet_id for record in records}
    for packet_id, meta in packets.items():
        if packet_id in known:
            continue
        status = str(meta.get("human_review_status") or "PENDING_HUMAN_REVIEW")
        tier = _tier_from_human_status(status)
        records.append(
            PacketLabel(
                packet_id=packet_id,
                company=meta.get("company"),
                technology_track=meta.get("technology_track"),
                human_status=status,
                human_label=None,
                ai_label=ai_by_packet.get(packet_id),
                label_tier=tier,
            )
        )

    counts_by_tier: dict[str, int] = {}
    counts_by_company: dict[str, int] = {}
    for record in records:
        counts_by_tier[record.label_tier] = counts_by_tier.get(record.label_tier, 0) + 1
        company = record.company or "unknown"
        counts_by_company[company] = counts_by_company.get(company, 0) + 1

    return LabelState(
        packets=tuple(records),
        counts_by_tier=counts_by_tier,
        counts_by_company=counts_by_company,
        ai_review_present=bool(ai_records),
        ai_review_records=len(ai_records),
        study_dir=str(root),
    )


def assess_data_readiness(
    state: LabelState,
    *,
    min_human_labels: int = 60,
    min_per_company: int = 6,
    required_companies: Iterable[str] = ("medtronic", "ge_healthcare", "philips", "draeger", "mindray"),
) -> DataReadiness:
    """Decide whether extraction research may start on human labels.

    Thresholds are deliberately demanding and pre-registered in ``docs/PROTOCOL.md``.
    A smaller pilot is allowed later, but it must be declared as a pilot; the
    default here answers "is the full study feasible?".
    """
    blockers: list[str] = []
    warnings: list[str] = []
    if state.human_confirmed == 0:
        blockers.append("NO_HUMAN_CONFIRMED_LABELS")
    elif state.human_confirmed < min_human_labels:
        blockers.append(f"INSUFFICIENT_HUMAN_LABELS({state.human_confirmed}<{min_human_labels})")
    if state.ai_preliminary and state.human_confirmed == 0:
        warnings.append(
            "AI_PRELIMINARY_LABELS_EXIST_BUT_CANNOT_BE_GOLD"
            f"({state.ai_preliminary} packets)"
        )
    for company in required_companies:
        count = state.counts_by_company.get(company, 0)
        if count < min_per_company:
            blockers.append(f"COMPANY_UNDER_REPRESENTED({company}={count}<{min_per_company})")
    if state.n_packets < min_human_labels:
        blockers.append(f"TOO_FEW_PACKETS({state.n_packets}<{min_human_labels})")
    status = "READY" if not blockers else "NOT_READY"
    return DataReadiness(
        kind="DATA",
        status=status,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        evidence={
            "n_packets": state.n_packets,
            "human_confirmed": state.human_confirmed,
            "ai_preliminary": state.ai_preliminary,
            "unlabelled": state.unlabelled,
            "counts_by_company": dict(state.counts_by_company),
            "counts_by_tier": dict(state.counts_by_tier),
            "min_human_labels": min_human_labels,
            "min_per_company": min_per_company,
            "ai_review_present": state.ai_review_present,
        },
    )


def assess_pit_readiness(study_dir: str | Path | None = None) -> DataReadiness:
    """Decide whether source availability times support point-in-time claims.

    Tier A sources record both ``published_at`` and ``available_at``; Tier B
    sources need an assumed lag.  Any source that is Tier B or unresolved keeps the
    status at best ``PARTIAL``, because an assumed publication lag is a modelling
    assumption, not a measurement.
    """
    root = Path(study_dir) if study_dir is not None else DEFAULT_STUDY_DIR
    audit = _read_json(root, EVIDENCE_TIME_AUDIT_NAME)
    if audit is None:
        return DataReadiness(
            kind="PIT",
            status="UNKNOWN",
            blockers=("EVIDENCE_TIME_AUDIT_MISSING",),
            evidence={"study_dir": str(root)},
        )
    tiers = audit.get("source_tiers") or {}
    tier_counts: dict[str, int] = {}
    non_a: list[str] = []
    for source, info in sorted(tiers.items()):
        tier = str((info or {}).get("tier", "?")).upper() if isinstance(info, dict) else "?"
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        if tier not in ("A",):
            non_a.append(f"{source}:{tier}")
    unresolved = audit.get("unresolved") or {}
    assumptions = audit.get("tier_b_assumptions_days") or {}
    blockers: list[str] = []
    if non_a:
        blockers.append("NON_TIER_A_SOURCES(" + ",".join(non_a) + ")")
    unresolved_reasons: list[str] = []
    if isinstance(unresolved, Mapping):
        unresolved_reasons = [str(key) for key in unresolved]
    elif isinstance(unresolved, list):
        unresolved_reasons = [str(item) for item in unresolved]
    if unresolved_reasons:
        blockers.append(f"UNRESOLVED_AVAILABILITY_COUNT({len(unresolved_reasons)})")
    warnings: tuple[str, ...] = ()
    if assumptions:
        lags = ", ".join(f"{key}={value}d" for key, value in sorted(assumptions.items()))
        warnings = (f"TIER_B_LAGS_ARE_ASSUMPTIONS({lags})",)
    status = "READY" if not blockers else "PARTIAL"
    return DataReadiness(
        kind="PIT",
        status=status,
        blockers=tuple(blockers),
        warnings=warnings,
        evidence={
            "source_tier_counts": tier_counts,
            "unresolved_count": len(unresolved_reasons),
            "unresolved_reasons": unresolved_reasons,
            "assumed_lags_days": dict(assumptions) if isinstance(assumptions, dict) else {},
            "clock_note": audit.get("first_seen_at_semantics"),
            "generated_at_utc": audit.get("generated_at_utc"),
        },
    )


def label_state_report(study_dir: str | Path | None = None) -> dict[str, Any]:
    """One JSON-serialisable readiness summary for docs, manifests and the CLI."""
    state = load_label_state(study_dir)
    return {
        "generated_by": "experiments.local_llm_event_extraction.labels",
        "read_only": True,
        "label_state": {
            key: value
            for key, value in state.to_dict().items()
            if key != "packets"
        },
        "data_readiness": assess_data_readiness(state).to_dict(),
        "pit_readiness": assess_pit_readiness(study_dir).to_dict(),
    }


def main(argv: list[str] | None = None) -> int:
    """``python -m experiments.local_llm_event_extraction.labels`` -> readiness JSON.

    Read-only by construction: there is no option that writes, and the only path
    effect is printing to stdout.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--study-dir", default=None, help="evidence-packet directory to read")
    parser.add_argument("--pretty", action="store_true", help="indent the JSON output")
    args = parser.parse_args(argv)
    report = label_state_report(args.study_dir)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess in docs
    raise SystemExit(main())
