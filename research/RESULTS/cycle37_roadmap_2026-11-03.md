# Cycle 37 — the roadmap is rewritten from what exists; the mission states today's position (2026-11-03)

**Status:** completed. Closes B-070. Decision: D-068.
Artifacts: `research/ROADMAP.md` (rewritten), `research/MISSION.md` §10 (added; §9 preserved).

## Why this is a research act rather than housekeeping

The roadmap was written on 2026-11-02, before the detector was validated, before the promotion rule existed, before
four anticipations failed and before either paper. Left alone it would describe a programme that no longer exists,
and a reader would have to reconstruct the real state from 37 results files. **A plan of record that is stale is
worse than none, because it invites the reader to trust it.**

## What ROADMAP.md now says

A single status table where **every capability cites its evidence**: foundation, entity universe, detection with its
named non-identifiability limit, the deployment choice, independent lanes with coverage limits, the access-blocked
patent and broad-hiring lanes, seven-field profiles, the promotion policy with its sign-off gate, one confirmed
decision rule, four failed anticipations each with the design flaw that produced it, the rolling-origin null, 25
frozen prospective forecasts, two papers with claim maps, and the governance tooling. **P4 is recorded as not started
on purpose**, with the reason: no baseline gap exists, and the bottleneck is information rather than model capacity.

Section 3 is the completion-relevant part: it states **what remains and why it cannot be simulated** —

1. 25 prospective forecasts mature **2026-Q4 … 2028-Q1**;
2. 25 legacy nowcasts mature **2027-10**;
3. one promotion awaits a **human signature** the session cannot give;
4. patents and broad hiring are **access-blocked**;
5. hiring coverage for three deep-case companies is **structurally unavailable**.

## What MISSION.md now says

§9 is preserved **unchanged** as the record of the 2026-11-02 position. A new §10 states today's position with the
same discipline: what is now established (detector at a chosen resolution, one confirmed rule, the seven-field
instrument, four diagnosed failures, frozen prospective machinery, two papers) and what has **not** changed (zero
prospective calibration evidence; no visibility into intent, capability or internal R&D; information as the binding
constraint; five retractions).

The roadmap is edited because a plan of record must read as current state; the mission keeps its history because a
charter must.

## Verification

- `python tools/audit_objectives.py` → **11 PASS / 0 FAIL / 1 N/A** (state files, backlog 57 tasks, 67 decisions,
  136 result rows, 6 snapshots, 25 prospective forecasts).
- `python tools/round_end.py` → gate run for this round.

## Next

1. A retraction-to-rule figure for the methods paper (the material already exists).
2. Mature the prospective set when the lane advances.
3. Review backlog items whose data is structurally unavailable and mark them blocked rather than open.
