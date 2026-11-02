"""Repair backlog statuses with evidence: mark what is done, block only what truly cannot be done here.

Triggered by experiments/b073/lane_inventory.json, which counts the stores before any "unavailable" claim is made.
The programme already retracted one such claim as a collector bug (D-029), so nothing is marked blocked here without
a named reason that does not depend on missing data.
"""
from __future__ import annotations

from pathlib import Path

BACKLOG = Path("research/BACKLOG.yaml")

DONE = {
    "B-032": ("Versioned technology taxonomy with effective date and mapping fingerprints "
              "(medradar/intelligence/taxonomy.py; regime stamped into profiles.json; 10 tests)"),
    "B-028": ("Contradictory evidence is a first-class profile field and the schema rejects a profile without it; "
              "measured rate reported per build (51 of 53 roster companies carry counter-evidence)"),
}

BLOCKED = {
    "B-014": ("Needs a human-adjudicated labelled sample, which this session cannot produce: AI-created fixtures "
              "are explicitly not human truth, so the benchmark cannot be built here without violating its own "
              "acceptance criterion"),
}

UNBLOCKED_NOTES = {
    "B-018": "data present: financial_facts=43420, market_bars=95725, publication_counts=616 (b073 inventory)",
    "B-021": "data present: financial_facts=43420, market_bars=95725, publication_counts=616, procurement_awards=3453",
    "B-029": "data present: events=55090, company_identifiers=34 (unlinked CIK-bearing 8-K events are in the store)",
    "B-037": "data present: events=55090 over 38 tracks and 119 months",
    "B-041": "publication_counts=616 present; the lag question is about publication timing, which the store records "
             "at monthly resolution",
}


def block_bounds(lines: list[str], identifier: str) -> tuple[int, int]:
    start = None
    for index, line in enumerate(lines):
        if line.strip() == f"- id: {identifier}":
            start = index
            break
    if start is None:
        raise SystemExit(f"{identifier} not found")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("  - id:"):
            end = index
            break
    return start, end


def main() -> int:
    lines = BACKLOG.read_text(encoding="utf-8").splitlines()
    changed = []
    for identifier, note in DONE.items():
        start, end = block_bounds(lines, identifier)
        for index in range(start, end):
            if lines[index].strip().startswith("status:"):
                lines[index] = "    status: done"
        lines.insert(end, f"    notes: {note}")
        changed.append(identifier)
    for identifier, reason in BLOCKED.items():
        start, end = block_bounds(lines, identifier)
        for index in range(start, end):
            if lines[index].strip().startswith("status:"):
                lines[index] = "    status: blocked"
        lines.insert(end, f"    notes: {reason}")
        changed.append(identifier)
    for identifier, note in UNBLOCKED_NOTES.items():
        start, end = block_bounds(lines, identifier)
        if not any(line.strip().startswith("notes:") for line in lines[start:end]):
            lines.insert(end, f"    notes: {note}")
            changed.append(identifier)
    BACKLOG.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"updated {len(changed)} backlog items: {' '.join(sorted(set(changed)))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
