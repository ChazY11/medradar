# Cycle 7 — retraction of the entry-wave finding, and a measurement lesson (2026-11-02)

**Status:** completed. **Retracts** the positive finding of cycle 6 (D-024) and replaces it with a
negative result plus a measurement rule. Evidence: `entries_*.json`, `compare_entry_specs.py`.
Decision: D-025.

## What was retracted and why

Cycle 6 scored a cell's **first observed event** as a technology entry. But the risk set used by the
null already required the firm to be an observable filer, so the numerator could contain entries that
were not in the denominator's risk set. In practice **3,804 of 4,814 entries (79 %) were the
first-ever appearance of a legal entity in the lane** — a new small firm registering, or a newly
resolvable applicant string — not an established firm entering a new technology area.

The control (`--require-prior-filer`) counts an entry only when the entity already had an event in
another track before the entry month. It drops 79 % of entries and removes the inconsistency.

## Result across four specifications

| track | all events | churn controlled | prior-filer | prior-filer + churn |
|---|---|---|---|---|
| `ivd_immuno` | n=49, p=0.0055 | n=40, **p=0.0010** | n=8, **p=1.0000** | n=5, p=1.0 |
| `ivd_molecular` | n=68, p=0.69 | n=61, p=0.56 | n=5, **p=0.0025** | n=5, p=0.0005 |
| `aesthetics` | n=197, p=0.015 | n=195, p=0.0070 | n=27, p=0.0135 | n=27, p=0.0085 |
| `medical_ai` | n=464, p=0.0040 | n=418, p=0.0365 | n=144, p=0.0525 | n=135, p=0.0815 |
| `cardiac_rhythm` | n=21, p=0.0155 | n=18, p=0.0275 | n=3, p=0.0275 | n=3, p=0.0235 |

1. **`ivd_immuno` collapses** (40 → 8 entries, p = 1.0): the cycle-6 "wave" was entity appearance.
2. **The surviving track changes identity with the specification** (`ivd_immuno` → `ivd_molecular`),
   and `ivd_molecular` rejects on **five entries** after being p = 0.69 with 68. Specification noise.
3. **`aesthetics` is the only consistently small nominal p** (0.007–0.015 across all four specs) and it
   **fails FDR in every one**.
4. **Firm-level bursts remain null** everywhere (0 of 46–60).

## What this establishes

- **Negative result:** no device technology track has a specification-stable industry entry wave in
  this lane.
- **Measurement rule (the durable output):** in this data most "entries" are first appearances of
  legal entities, not established firms entering new areas. Any entry study must say which of the two
  it measures; they are not interchangeable, and mixing them manufactures waves.

## What would make `aesthetics` evidence rather than a candidate

It was selected by looking at p-values, so re-testing it on the same window is circular. The remedy is
split-sample pre-registration: fix the track now, estimate on a predetermined early window, and test
on a held-out later window with the threshold untouched (B-046). Until that runs, `aesthetics` is a
candidate and must not be cited as a finding.

## Pattern across six cycles

| cycle | tempting result | outcome |
|---|---|---|
| 1 | continuation model skill | baseline explained it |
| 2 | entry signal resolvable | monthly-only; reversed at other resolutions |
| 4 | competitors move together | track growth, not synchronisation |
| 5 | trials confirm clearances | no detectable association |
| 6 | ivd_immuno entry wave | **entity appearance, not firm entry** |
| 7 | (this) → candidate `aesthetics`, awaiting a split-sample test | pending |

Six cycles, zero surviving positive claims, and one increasingly precise map of what this data cannot
support. That map is the deliverable; the retraction discipline is what makes it worth anything.
