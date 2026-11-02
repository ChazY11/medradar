# Roadmap

**Status as of 2026-11-03, after 36 cycles.** This file is the plan of record; it is rewritten when the
programme's state changes materially, and every claim in it points at a committed artifact. The charter lives in
`MISSION.md`; the machine-readable state lives in `STATE.json`; the decision log in `DECISIONS.md`.

## 1. Where the programme actually stands

| Layer | Capability | State | Evidence |
|---|---|---|---|
| Foundation | bitemporal store, PIT export, immutable forecast registry, leakage audit | **done and audited** | cycle 1, `verifier/v1` |
| Observe | deterministic entity universe (9,412 entities, no fuzzy matching) | **done** | `config/universe_v1.json` |
| Observe | change detection with controlled false-alarm rate | **done, with a named limit** | `experiments/detect_v1/benchmark.json`; winner not identifiable across resolutions (D-018) |
| Observe | deployment resolution and detector chosen | **done** (quarterly, rolling z-score) | D-044/D-045; `experiments/b039/` |
| Observe | independent lanes: device trials, archival hiring | **done, coverage-limited** | `experiments/b040/`, `experiments/b030/` |
| Observe | patents, hiring beyond the archive | **blocked on access** | 403 (PatentsView), 504 (Common Crawl), D-029/D-031 |
| Understand | seven-field company profiles with mandatory contradictory evidence | **done for the full roster** | `medradar/intelligence/profile.py`, `experiments/b027/` |
| Understand | profiles carry the validated detector and the promotion policy | **done** | `experiments/b027/profiles/*.md`, D-046/D-061 |
| Understand | promotion from alert to "technology change" | **done, gated, mostly unsigned** | `research/RESULTS/PROMOTIONS.md`, D-049/D-054 |
| Anticipate (A) | emerging-trend identification from multiple lanes | **partly done, honestly negative** | co-movement null (D-021); entry-wave retractions (D-025, D-027) |
| Anticipate (B) | rolling-origin benchmarking | **done, null** | `experiments/b050/` (D-036) |
| Anticipate (B) | frozen prospective forecasts and maturation | **done; 25 pending to 2028** | `research/forecasts/`, D-066 |
| Anticipate (B) | matured forecast calibration | **blocked on wall clock** | registry matures 2027-10 (B-015) |
| Publish | empirical paper + methods paper, both with claim maps | **done (drafts)** | `papers/`, D-038/D-067 |
| Governance | objective audit and round-end gate | **done** | `tools/audit_objectives.py`, `tools/round_end.py` |
| P4 | advanced temporal/graph methods | **not started, correctly** | no baseline gap that simpler methods fail to close |

## 2. Phases, and what each one actually produced

**Phase A — reliability floor (P0). Done, continuous.** Every reported number is re-derivable; profiles are frozen
with manifests; snapshots are audited for leakage. Continuous obligation: every module ships with tests (currently
910), every claim carries a source, and nulls carry MDEs.

**Phase B — OBSERVE detection (P1). Done, with a limit that is reported rather than hidden.** Four detectors on a
controlled-truth benchmark; a frontier rather than a winner; a crossover at two months; and the finding that at
this sample size **the best detector is not identifiable across resolutions** (D-018). Deployment then chose a
resolution and, at that resolution only, a detector (D-044/D-045).

**Phase C — coverage (P1). Partly blocked, partly resolved.** Entity universe done; trial lane collected and shown
to be too sparse at cell level for confirmation (D-023); hiring lane collected from a public archive and shown to
cover 2 of 16 firms at the usability floor, then 11 of 16 after the collector bug was fixed, and structurally unable
to cover four of the five mandated deep cases (D-030/D-031); patents and broader hiring blocked on access.

**Phase D — UNDERSTAND (P2). Done.** Seven-field profiles with a schema that rejects any profile lacking
contradictory evidence; the validated detector inside each profile with its measured error rates; a promotion policy
in code with mandatory human sign-off; three backdated snapshots plus two policy-labelled snapshots so a nowcast's
provenance is auditable to a date.

**Phase E — ANTICIPATE Level A (P3). Attempted four times, negative each time.** Co-movement vanished under a
track-growth null; entry waves were an entity-appearance artefact; the surviving candidate failed a clean split-sample
design; cross-lane association was null. Reported with the design flaw that produced each (D-021, D-025, D-027, D-023).

**Phase F — ANTICIPATE Level B (P3). Benchmarked, null, and now prospective.** Rolling-origin benchmark found no
predictability above baseline, and its own outcome definition was biased (corrected 0.49 → 1.22; D-036). One
confirmed decision rule emerged from injected-shape work instead (D-043, replicated D-048, twice extended D-057/D-061).
13 genuinely prospective forecasts are frozen and mature 2027-Q3 … 2028-Q1 (corrected after the 2026-11-03
audit found 12 of the original 25 had partially observed outcome windows; D-075).

**Phase G — P4 advanced methods. Not started, on purpose.** No baseline gap exists that simpler methods demonstrably
fail to close; the programme's bottleneck is data density and access, not model capacity.

## 3. What remains before the objective can be called complete

The objective's deliverable list is satisfied and machine-checked (see `research/AUDIT.md`). What remains is not
code, and should not be simulated:

1. **Prospective forecast maturation.** 13 corrected prospective forecasts mature between 2027-Q3 and 2028-Q1.
   Until then no prospective calibration claim can be made. Command:
   `python experiments/b068/maturate_forecasts.py`.
2. **Registry calibration.** The 25 legacy nowcasts mature 2027-10 (B-015).
3. **Human sign-off on the one pending promotion** (`medtronic:insulin_delivery:2025-Q3`). The programme can prepare
   it but cannot sign for a person; the ledger shows it as `PENDING_SIGNOFF`.
4. **Access-dependent lanes** (patents, broader hiring) — blocked on credentials or service availability, not on work
   the programme can do alone.
5. **Deep-case coverage** for Dräger, Mindray and GE HealthCare in the hiring lane is structurally unavailable;
   their profiles rest on filings, trials and publications.

## 4. Standing constraints

- One workstation; deterministic, resumable pipelines; no hyperparameter sweeps for their own sake.
- Every round ends with `python tools/round_end.py` exiting 0; a claim the gate cannot verify is not a claim.
- No merge to `main` without independent verification of the exact commit.
- Scope discipline: no global-industry prediction, no cross-industry digital twin, no macro forecasting, no large
  model training, no unverifiable speculation about internal R&D.
- Rules learned from failure are enforced in code or schema, not in prose (`papers/PAPER_METHODS_v1.md` §3).

## 5. Next 30 days of work (indicative, not binding)

Either mature data (prospective forecasts, registry, human sign-off) or strengthen what exists with material that
already exists: a figure mapping each retraction to the rule it produced; a second-domain replication of the profile
engine on the trial lane; and a review pass that prunes backlog items whose data is structurally unavailable rather
than leaving them to look open.
