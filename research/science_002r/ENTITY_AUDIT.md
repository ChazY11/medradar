# ENTITY_AUDIT - what the cross-source links do and do not establish

**Scope.** 62 candidate registrants, 189 accepted links, 48 firms in the universe,
14 excluded candidates. This file re-derives the four quantities that the
SCIENCE-002 text ran together, audits each attribution tier, and records one
measured negative result that changes the next phase of the project.

Evidence: `artifacts/entity_audit.json`, `artifacts/establishment_extract.json`.

---

## 1. Four quantities, four different defensible statements

| id | quantity | value | interpretation |
|---|---|---|---|
| **C1** | share of *all* cleared 510(k)s in 2015-2026 attributable to the 48 firms | **3,143 / 35,680 = 8.81%** | a property of the universe: these 48 firms are 8.8% of FDA's device-filing population by volume |
| **C2** | recall of the 48 firms' own FDA activity | **unknown** | no public source publishes a firm's true clearance total at legal-entity level, so the denominator does not exist |
| **C3** | links that contradict an independent FDA statement about the same establishment | **1 / 148** | strong: only one, and it is an acquisition artefact |
| **C4** | links whose applicant string is also a plausible match for another universe firm | **0** (the frozen rule drops exact double claims) | the ambiguity rule fired zero times |

SCIENCE-002 called C1 "attribution coverage" and discussed it as if it were C2.
Corrected in ERRATA.md (E4). The distinction is not pedantic: C1 says nothing about
how much of Stryker's own activity the study sees, and that is the number a reader
needs in order to judge the label.

## 2. Recall is unknown, but the misses are not invisible

Without a denominator, recall cannot be computed. The audit therefore enumerates
**candidate misses**: applicant strings that carry a universe firm's brand token but
were not attributed to it. 167 strings, 444 clearances.

They are **unadjudicated**: some are the same group under a 'dba' name, some are
different companies that share a word. They are reported because they demonstrate
that the name channel has structural blind spots, not because their count is a
recall estimate. The largest:

| firm | unattributed applicant string | clearances | plausible reason |
|---|---|---|---|
| SYK | HOWMEDICA OSTEONICS DBA STRYKER ORTHOPAEDICS | 28 | dba name, not an FDA registration name |
| SYK | STRYKER ORTHOPAEDICS | 9 | division name |
| GEHC | GE HUALUN MEDICAL SYSTEMS | 12 | joint-venture naming |
| TFX | ARROW INTERNATIONAL SUBSIDIARY OF TELEFLEX | 9 | acquired brand, dba |
| MMM | 3M HEALTHCARE | 6 | division name pre-spin-off |
| STE | STERIS CORPORATIONS | 7 | **plural defeats exact-root equality** |
| BLCO | BAUSCH LOMB | 6 | **'&' -> 'AND' normalisation mismatch** |

## 3. The normalisation rule creates real recall holes

Two of the examples above are defects of the rule rather than of the world:

1. **Ampersand.** `normalise_name` maps `&` to `AND`, so `Bausch & Lomb`
   becomes `BAUSCH AND LOMB` while an applicant writing `Bausch Lomb` becomes
   `BAUSCH LOMB`. Exact equality then fails between two spellings of the same
   company.
2. **Plurals and typos.** `STERIS CORPORATIONS` vs `STERIS` (the suffix list
   strips `CORPORATION`, not `CORPORATIONS`).

Neither is a similarity-matching argument: they are deterministic variants that a
production rule would enumerate (singular/plural on the suffix list, and treating
`AND` as removable when it came from `&`). The audit does **not** change the
rule - the frozen experiment must stay as it ran - but records it as a specific,
cheap improvement for the next version, with the affected strings named.

## 4. Tier-by-tier audit

| tier | links, all 62 candidates | links among the 48 | clearances among the 48 | what it asserts |
|---|---|---|---|---|
| T_A | 59 | 46 | 1,945 | applicant string == SEC title |
| T_A2 | 4 | 4 | 88 | applicant string == an SEC-published former name |
| T_B | 126 | 98 | 1,110 | applicant string == an FDA establishment name whose FDA owner/operator == SEC title |
| total | **189** | **148** | **3,143** | |

(Clearances are the 2015-2026 window. T_B carries **35%** of all attributed
clearances, which is why the S1 sensitivity - which removes it entirely - is the
most important robustness check in the study, and why its undated-snapshot caveat
is load-bearing rather than cosmetic.)

**T_A / T_A2** are assertions by SEC: the registrant's own current or former name.
The only external check possible is FDA's owner/operator record, and 1 of 44
conflicts (Teleflex -> Vascular Solutions).

**T_B** is the tier that needs the most care, because the ownership snapshot is
**undated** and belongs to 2026. Two things were verified:

* the link does not change over time inside a panel (the applicant set of every firm
  is fixed), so no firm's event stream has a discontinuity at an acquisition date;
* the sensitivity that removes T_B entirely (S1 in SCIENCE-002, re-derived here)
  keeps the verdict: 45 firms, delta -0.043, p = 0.047, still NULL.

What cannot be verified is the *historical* truth of the ownership relation, because
no dated public source for it is in the evidence. That limitation is correctly
disclosed by SCIENCE-002 and is not a defect introduced by this audit.

## 5. The measured negative result for SCIENCE-003: establishment identifiers are not filing-level

SCIENCE-002's NEXT_STEPS proposed to re-derive attribution through
`openfda.registration_number` / `fei_number`. The audit tested that
assumption on the real data instead of adopting it. **It fails.**

| property | measured |
|---|---|
| 510(k) records with any registration number | 173,426 / 176,625 (98.2%) |
| records with exactly one | 1,299 (0.74%) |
| median per record | **104** |
| 90th percentile | 431 |
| maximum | 1,438 |
| distinct registration-number sets | 4,049 |
| sets shared by >1 distinct applicant | **3,282** |
| applicants sharing the largest single set | **1,104** |

Individual examples: K210001 (Shanghai United Imaging) carries 86 registration
numbers; K190001 (Togo Medikit) carries 202; K230001 (Guangdong Prestige) carries 75.

The field is the **set of establishments that list a device with the submission's
product code** - an aggregate inherited from the device-listing join - not the
establishment that filed the 510(k). It cannot attach a submission to a parent
company. Using it would attach each filing to hundreds of unrelated establishments,
with a bias toward whichever product codes are crowded.

**Consequence for SCIENCE-003:** the proposed measurement fix does not exist in the
form proposed. What would be needed instead is set out in
SCIENCE003_READINESS.md, together with the small-scale checks that were run.

## 6. Precision and the one conflict in detail

The conflicting link: applicant `TELEFLEX` (T_A, 3 clearances) is registered in
FDA's establishment file under owner **VASCULAR SOLUTIONS**. Teleflex acquired
Vascular Solutions in 2017, so the establishment kept the acquired entity's name
while the 510(k) applicant uses the acquirer's name. This is the *expected* failure
mode of a 2026 snapshot, and finding exactly one instance in 148 is a good result
for the layer: it says the snapshot is broadly consistent with the historical
applicant names, not that it is historically correct in every case.

Three links have no registration record at all and therefore cannot be checked this
way. They are listed in the artifact.

## 7. What an external reviewer should conclude

* The links are **not** similarity matches: each is exact string equality at a named
  tier, with the evidence string stored, and the ambiguity rule was tested with a
  synthetic collision in the test suite.
* The links are **not** complete: recall is unknown, the visible blind spots are
  enumerated, and two of them are fixable rule defects rather than limitations of
  the world.
* The label therefore means *clearances filed under the establishment names
  attributable to this group*, **not** *all clearances of the group*. Every
  conclusion in SCIENCE-002 is conditional on that sentence.