# DOMAIN AMENDMENT 001 — pre-registered revision of the candidate technology domains

**Study:** `early_signal_5firms` · **Status:** **amendment, frozen on human sign-off** ·
**Issued after:** the coverage audit (`COVERAGE_MATRIX.json`) and the entity/domain audit
(`ENTITY_AND_DOMAIN_AUDIT.json`) · **Issued before:** any outcome, label or lead-time measurement

> **Why an amendment exists.** The directive makes the four candidate domains a *candidate list*, not a mandate, and
> requires a recorded reason for any change. This amendment changes the domain set **using coverage evidence only**.
> No outcome, alert or case label was examined to produce it. The numbers below are reproducible with
> `python experiments/b081/entity_and_domain_audit.py`.

---

## 1. Finding that forces the amendment

The five originally proposed domains (patient monitoring, ultrasound imaging, advanced imaging, respiratory &
critical care, medical AI/SaMD) produce **11 evaluable `firm × domain` cells out of 25** at the pre-declared floors
(≥40 observations and ≥12 quarters with observation inside 2018–2025). Two problems are structural, not marginal:

| problem | evidence |
|---|---|
| **Cross-company validation is thin.** The directive's target is 12–18 effective combinations. After the floors, only **2 technology tracks** are shared by **≥3 firms**: `imaging_us` (GE HealthCare, Mindray, Philips) and `respiratory` (GE HealthCare, Medtronic, Philips). That is **6 firm × track cells**, not 12–18. | `ENTITY_AND_DOMAIN_AUDIT.json → domain_sharing.shared_tracks` |
| **The domain list does not match Medtronic's portfolio.** Medtronic has 18,147 events in the store but only **113** inside the five candidate domains; its activity sits in `cardiac_rhythm` (6,881), `neurostimulation` (1,281), `urology` (832), `structural_heart` (801). | `COVERAGE_MATRIX.json`; `experiments/b080/probe_five_firms.py` output |

Of the 42 tracks touched by the five firms in the window, only two survive the cross-company floor.

## 2. The amended design (pre-registered now)

### 2.1 Confirmatory set — the only place cross-company claims may be made

| track | firms meeting floors | observations (quarters) |
|---|---|---|
| `imaging_us` (Ultrasound) | ge_healthcare, mindray, philips | 107 (28) · 48 (26) · 146 (20) |
| `respiratory` | ge_healthcare, medtronic, philips | 61 (13) · 42 (15) · 86 (14) |

**Consequence accepted openly:** RQ4 (cross-firm replication) is answerable on **two domains only**, with three
firms each. Any Phase 1 result on these tracks must state `n_domains = 2`, and leave-one-company-out evaluation is
only possible for the three firms present in each track.

### 2.2 Secondary set — firm-pair replication (exploratory, not confirmatory)

Tracks shared by exactly two firms may be used for **pairwise** replication, reported separately and never pooled
with the confirmatory set. This is a lower bar and is labelled as such.

### 2.3 Exploratory set — per-firm tracks

Per-firm analysis (e.g. Medtronic × `cardiac_rhythm`, Mindray × `patient_monitoring`) may be run for **within-firm**
questions (RQ1, RQ3) and must be reported as **exploratory**: they cannot support a cross-company claim and cannot
enter RQ4.

### 2.4 Domains retained, domains dropped

- **Retained:** `imaging_us`, `respiratory` (confirmatory); `patient_monitoring`, `advanced_imaging`,
  `medical_ai_samd` (exploratory per firm, since each is evaluable for at least one firm).
- **Dropped as a cross-company domain:** `advanced_imaging` — GE HealthCare and Philips only, so no third firm.
- **Dräger:** not evaluable in any domain (6 observations, 4 quarters in respiratory only). Dräger remains in the
  study as a **descriptive** case only, and must be excluded from any claim that requires data.
- **Mindray:** evaluable in `imaging_us` (48 obs / 26 quarters), which is the only reason a non-US-headquartered firm
  appears in the confirmatory set.

## 3. Entity-resolution conditions attached to the amendment

The amendment is conditional on two entity caveats that the audit surfaced:

1. **GE HealthCare continuity is not established.** The roster key `ge_healthcare` matches raw applicants from
   **1969–2026**, spanning `GE MEDICAL SYSTEMS` (1,378 observations) and the current `GE HEALTHCARE` naming (1,543).
   Any firm-level claim must say "the GE imaging business lineage", not "GE HealthCare the post-2023 legal entity",
   unless a human reviewer establishes continuity.
2. **Alias matching has a measured false-positive mode.** Substring matching on `applicant_raw` produced at least one
   confirmed false positive: `Surge Medical Sales, LLC (DBA Surge Cardiovascular)` matches the pattern `GE MEDICAL`
   because the words straddle “SUR**GE MEDICAL**”. Six strings carry suspicion tokens (`SAFETY`, `SERVICE`, `SALES`,
   `DISTRIBUT`) and are listed in the audit for human review. Until they are adjudicated, per-firm counts carry an
   **unquantified upward bias of at most the flagged observations** (Philips 26, Medtronic 6, others 1–2).

## 4. What this amendment does *not* do

- It does not raise or lower the pre-declared floors (40 observations, 12 quarters) to manufacture cells.
- It does not switch the window (2018–2025) or the unit (`company × track × quarter`).
- It does not promote a source's tier; `first_seen_at` remains a collection date, and Tier B remains the ceiling.
- It does not license any claim about Dräger.

## 5. Sign-off

| item | status |
|---|---|
| Domain set, confirmatory/secondary/exploratory split | **PENDING_HUMAN_REVIEW** |
| GE HealthCare lineage treatment | **PENDING_HUMAN_REVIEW** |
| Adjudication of the six flagged raw strings | **PENDING_HUMAN_REVIEW** |
