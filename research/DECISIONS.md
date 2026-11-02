# Decision record

ADR-style. Each decision states the alternatives considered and the evidence that
settled it. Superseded decisions stay in the file with a pointer.

---

## D-001 — Build new work on `integration/market-to-rd-v2`, not on `main`

**Date:** 2026-11-02. **Status:** accepted.

`main` is frozen at `7a639f7` (v0.2.2). The audited, integrated research foundation
plus Phases 1–3 live on `integration/market-to-rd-v2` at `1749bd5` (v0.5.0), with
679 offline tests green and all real-data artifacts committed there.

*Alternatives:* merge the integration branch into `main` first (rejected for now —
the branch has an open PR #4 whose CI status is unverified; merging an unverified
head moves the stable reference point); restart from the foundation commit `dedfd68`
(rejected — it would discard Phases 1–3, which are the actual scientific content).

*Consequence:* cycle 2 branches from `1749bd5` as `research/cycle2-coverage-power`.
`main` stays untouched until an independent verification pass on an exact commit.

---

## D-002 — No fuzzy entity matching; deterministic legal-entity universe

**Date:** 2026-11-02. **Status:** accepted.

The 510(k) lane links to a curated company only 16.9% of the time. The tempting fix
is fuzzy name matching to raise recall. Rejected: a false merge silently relabels a
competitor's milestone as the target company's, which poisons *labels* rather than
features, and no amount of leakage auditing detects it.

*Decision:* build a deterministic universe of legal applicant entities via
documented suffix normalisation with **no** cross-name fuzzy merging, then compare
entity granularity explicitly (E12: legal applicant vs corporate parent). Precision
is auditable; recall loss is visible as many small entities instead of silent
contamination.

---

## D-003 — A negative result about added data sources is a result, not a failure

**Date:** 2026-11-02. **Status:** accepted.

E4–E6 found no statistically detectable ranking gain from consolidated SEC
financials, point-in-time market features or OpenAlex publication counts. The
temptation is to keep adding model capacity until something "wins". Rejected as
p-hacking by another name.

*Decision:* publish the nulls, then test whether they are *underpowered* nulls via
minimum detectable effect (E13). "No effect detectable at this power" and "no
effect" are different sentences and must not be conflated.

---

## D-004 — Durability for the 8-K lane until CIK-based linking is verified

**Date:** 2026-11-02. **Status:** provisional.

In the legacy full-history DB, 19,616 of 20,976 `8k_catalyst` events have no
`company_key` even though EDGAR filings carry a CIK and the company registry already
has CIK identifiers. This is a deterministic linking opportunity (not fuzzy), and it
is assigned to a later cycle rather than this one, so that cycle 2 keeps a single
explanatory variable (entity universe size). Recorded so it is not silently forgotten.

---

## D-005 — Frozen artifacts are immutable inputs

**Date:** 2026-11-02. **Status:** accepted.

`experiments/reverse_rd_v1/`, `experiments/reverse_rd_v2/` and the three
`data/*.sqlite` stores are treated as frozen. Cycle 2 writes only new directories and
new tables. Re-running a frozen experiment must reproduce its committed numbers
byte-for-byte; if it does not, that is a defect to report, not a number to update.

---

## D-006 — Pre-register the test windows before modelling

**Date:** 2026-11-02. **Status:** accepted.

The entry target has 24 quarterly origins. Holdout windows and the primary metric
(PR-AUC / average precision) are fixed before any cycle-2 model is fitted. Reporting
the window that "works" (v2 found one of three excludes zero) is exactly the failure
mode this prevents. All windows are reported; the window mean and per-window values
are both published.

---

## D-007 — Cycle-2 primary spec excludes financial features, for both panels

**Date:** 2026-11-02. **Status:** accepted.

The entity cohort is not CIK-mapped, so consolidated SEC features exist for only a
handful of cohort entities. Including them would compare a panel with financial
coverage against one without, confounding the entity-universe change with a feature
change. Both panels therefore run the identical 16-feature R&D+entry specification
(the `rd_only` cycle-1 headline used 10 features; the 16-feature number is therefore
not directly the frozen number and both are reported).

---

## D-008 — Cohort is ranked by material-event count, not all-row activity

**Date:** 2026-11-02. **Status:** accepted, with a documented reproducibility gap.

The committed `config/universe_v1.json` ranks entities by activity over all
510(k)/PMA rows (PMA supplements included), while the cycle-2 panel builds its
universe over the material event set (the same rule the labels use) and ranks by
material count. The two 200-entity cohorts differ by 5 boundary entities (2.5%),
with the same five focus companies pinned and the same minimum material count.

*Why not silently swap to the artifact cohort:* it would substitute a rule that is
inconsistent with the labels for one that is consistent. *Why not silently keep it:*
a reader comparing the panel to the artifact deserves to know they differ. The
discrepancy is stated in `experiments/cycle2_coverage/REPORT.md` §2 and a sensitivity
run on the artifact cohort is backlog item B-017.

---

## D-009 — "Detection at matched FAR" is not "earlier warning"

**Date:** 2026-11-02. **Status:** accepted as a reporting rule.

Cycle 2 found a large matched-FAR detection advantage (+0.30…+0.44 more positives
detected at the same false-alarm budget) but lead-time deltas that are negative in
four of six windows. Future reports must separate these two claims: detecting more
entries and detecting them earlier are different capabilities, and only the first is
supported here.

---

## D-010 — No merge to `main` in cycle 2

**Date:** 2026-11-02. **Status:** accepted.

Cycle 2 ships on `research/cycle2-coverage-power` and a PR. `main` stays at
`7a639f7` pending an independent verification pass on the exact commit; the accepted
run was performed by the same agent that wrote the pipeline, so cross-verification is
still outstanding.
