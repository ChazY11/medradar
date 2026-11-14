# SCIENCE003_READINESS - what the measurement fix would have to be

SCIENCE-002's next-step proposal was: re-derive attribution through FDA establishment
numbers instead of company names. The audit tested that proposal on the data.
**It does not work as stated.** This file records the evidence and what would have to
be true instead.

---

## 1. What was proposed

> "re-derive the attribution through FDA establishment numbers instead of names
> (`openfda.registration_number`, `openfda.fei_number`, then the owner/operator
> number)"

The premise is reasonable: a number cannot be a dba, a plural or an ampersand, so a
number-based channel would remove exactly the failure modes ENTITY_AUDIT.md section 3
found.

## 2. What the data actually contains

Measured on all 176,625 records of the 510(k) bulk export
(`research/science_002r/artifacts/entity_audit.json`,
`establishment_identifiers`):

| property | measured | what it implies |
|---|---|---|
| records with any `registration_number` | 173,426 (98.2%) | coverage is not the problem |
| records with exactly one | 1,299 (0.74%) | a filing-level key does not exist in this field |
| median numbers per record | **104** | the field is a set, not an identifier |
| p90 / max | 431 / 1,438 | large product codes swamp the record |
| distinct registration-number sets | 4,049 | the sets are shared, not per-filing |
| sets used by more than one applicant | **3,282** | one set is used by up to **1,104** different applicants |

Concretely: K190001 (Togo Medikit, 2019) carries 202 registration numbers; K210001
(Shanghai United Imaging, 2021) carries 86; K230001 (Guangdong Prestige, 2023) carries
75. The numbers are the establishments that list a device with the submission's
**product code** - an aggregate inherited from the device-listing join - not the
establishment that filed the submission.

**Conclusion.** This field cannot attach a 510(k) to a parent company. Using it would
attach each filing to hundreds of unrelated establishments, with a bias toward
crowded product codes (the largest set alone spans 1,104 applicants in the
radiation-therapy/imaging space). The proposed fix is a NO-GO in its current form.

## 3. What would have to be true instead

| candidate route | what it would need | status |
|---|---|---|
| **FDA 510(k) cover sheet / clearance letter** | the filing establishment is printed on the cover sheet; FDA publishes the letter PDF per K-number at `accessdata.fda.gov/cdrh_docs/pdf*/K######.ptf` | **untested here** - would require ~35k document fetches; a 50-document pilot would settle whether the establishment name is extractable |
| **FDA device listing (not registration)** | listing rows carry a `k_number` field (`device/registrationlisting` has a `k_number` column, empty in the sample rows seen) | **needs a targeted check**: if any listing rows carry a non-empty `k_number`, that is a true filing-level establishment link |
| **SEC Exhibit 21** | a dated, per-registrant subsidiary list | plausible but Exhibit 21 is filed inconsistently and only annually; it would give ownership **dates**, which the current snapshot lacks |
| **Better name normalisation** | singular/plural suffixes, `&`/`AND` equivalence, a per-firm alias list built only from FDA-published records | **cheap and immediately actionable**; would recover the STERIS/BAUSCH class of misses without any new data |

## 4. Entry conditions for SCIENCE-003

A SCIENCE-003 that proposes to *measure* attribution more accurately must satisfy:

1. **A filing-level parent link exists and is demonstrated on a pilot.** At minimum,
   extract the establishment from 50 clearance letters spanning 2015-2025 and show
   that (a) the field is present, (b) it maps to a registration/owner number, and
   (c) the map is stable over time. Without this, the programme is repeating the
   name problem with extra steps.
2. **Recall becomes measurable.** Either a denominator exists (a firm-level FDA
   activity total) or the study reports recall as unknown and bounds it with an
   adjudicated sample of candidate misses. The current 8.8% figure must not be
   reused as if it were recall.
3. **Ownership is dated.** An undated 2026 snapshot cannot support a historical
   attribution claim; a dated source (Exhibit 21, or the registration history if FDA
   publishes it) is required before acquisition-era activity can be attributed.
4. **The sample rule is as-of-prediction.** No eligibility decision may use events
   after the prediction instant (SELECTION_BIAS.md).
5. **The outcome stays independent of the features.** A clearance label built from
   an FDA source is acceptable only while no feature is derived from FDA data; the
   current design satisfies this and it must survive the redesign.

## 5. What the audit recommends for the next phase

1. **Do not start with a data rebuild.** Start with the 50-document clearance-letter
   pilot (route 1). It costs hours, and it decides whether the whole number-based
   approach is possible.
2. **In parallel, ship the cheap normalisation fixes** (route 4). They are
   deterministic, testable, and they recover real clearances for BLCO, STE and
   similar firms without touching the attribution architecture.
3. **Re-freeze the universe rule** before any new model is fitted; otherwise the
   selection defect in E7 is inherited by every downstream result.
4. **Keep the outcome definition.** A 90-day clearance indicator is saturated for
   large firms; if a new phase wants more power, the honest options are a
   novel-product-code outcome or a count model on non-overlapping quarters
   (STATISTICAL_REVIEW.md section 2), both of which are *new* pre-registrations.

## 6. Readiness verdict

**SCIENCE-003 is NOT ready to start as designed.** The one measurement fix it
proposed is unavailable in the public data in the form assumed, and the audit found
it by measurement rather than by argument. It becomes ready when the clearance-letter
pilot answers the filing-level question - a small, bounded, cheap experiment - and
not before.
