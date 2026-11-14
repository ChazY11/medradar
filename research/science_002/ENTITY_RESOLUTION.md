# ENTITY_RESOLUTION - how an SEC registrant is matched to FDA 510(k) records

**Status:** Phase-A result. Every accepted link is in `artifacts/entity_matches.csv`
with its literal evidence string and tier; every rejection is in
`artifacts/entity_exclusions.csv` with its reason.

## 1. The problem, stated concretely

FDA publishes a 510(k) under the **applicant** name printed on the submission.
That name is a legal entity at the time of submission, not a listed parent. The
same corporate group appears as dozens of applicant strings, and the same string
can survive a change of ownership. Over 2015-01-01..2026-08-31 the cleared 510(k)
database contains **35,680** clearances under **10,093** distinct applicant
strings. Matching those to 10,404 SEC registrants by name similarity would be
both easy and wrong: `BAXTER HEALTHCARE` is not `BAXTER INTERNATIONAL`, and a
company called `APPLE` is not Apple Inc.

So the study does not use similarity at all. It uses **string identity after a
published normalisation**, at a named tier, and it records what it rejects.

## 2. Normalisation (applied identically to both sides)

1. upper-case;
2. `&` -> ` AND `;
3. every non-alphanumeric character -> a space;
4. delete corporate-form and jurisdiction tokens: 
   `INC INCORPORATED CORP CORPORATION CO COMPANY LLC LLP LP LTD LIMITED PLC GMBH MBH
   AG SA SAS SPA NV BV AB ASA OY OYJ KK PTY PTE SARL SRL KG HOLDINGS HOLDING GROUP GRP
   THE USA US NA DE MD NJ PA NY CA MA IL MN IN OH WI MI FL TX GA MO CT`;
5. collapse whitespace.

Two names match only if the surviving token strings are **identical**. There is no
ratio threshold, no token-subset rule, no manual override, and no LLM in the loop.
This is why `Medtronic plc` and `Medtronic, Inc.` agree (both normalise to
`MEDTRONIC`), and why `LIFECORE BIOMEDICAL, INC. \DE\` and `Lifecore Biomedical,
Inc.` agree.

## 3. Tiers

| tier | rule | accepted links |
|---|---|---|
| **T_A** | applicant root == registrant's current SEC title root | **59** |
| **T_A2** | applicant root == a former name SEC publishes in the registrant's own submissions record | **4** |
| **T_B** | applicant root == an FDA establishment-registration name whose FDA-published **owner/operator firm name** root == the registrant's SEC title root | **126** |
| **T_C** | rejected: root claimed by more than one registrant | 0 |

**Total accepted: 189 links over 62 candidate registrants -> 48 firms in the
universe.** Note that the *count* of links is not the count of firms: 126 of the
links are subsidiary establishments hanging off 20 firms.

T_A2 uses SEC's own `formerNames` array (with its rename dates), so the identity
claim is SEC's, not ours.

### Why T_B exists

Without T_B the panel would silently lose most of the large-cap activity, because
large groups file through subsidiaries. Examples of what T_B adds, all with the
FDA-stated owner/operator relation:

| applicant string | FDA owner/operator | attributed to |
|---|---|---|
| `GE MEDICAL SYSTEMS` | GE HealthCare Technologies Inc. | GEHC |
| `MEDTRONIC SOFAMOR DANEK` | Medtronic, Inc. | MDT |
| `ABBOTT MEDICAL` | Abbott Laboratories | ABT (then excluded on SIC) |
| `INARI MEDICAL` | Stryker | SYK |
| `TELEFLEX MEDICAL` | Teleflex | TFX |
| `KCI` | Solventum | SOLV |

### The T_B limitation, stated once

The registration/listing export is an **undated 2026 snapshot**. It says who owns
an establishment *now*, not who owned it in 2015. Two consequences:

* the attribution is held **constant across the whole panel**, so no firm's event
  stream changes at an acquisition date; there is no attribution discontinuity to
  be mistaken for a signal;
* the group composition is the 2026 one. A pre-acquisition clearance of an acquired
  subsidiary is credited to the acquirer.

A concrete case shows the rule working in both directions: `STRYKER SPINE`, an
establishment FDA now lists under **VB Spine, LLC** (spun off in 2024), is **not**
attributed to Stryker, while Stryker's own `STRYKER` applicant string is. Had the
map been built from brand knowledge instead of the FDA record, Stryker's event
stream would contain a spurious structural break.

Sensitivity **S1** removes T_B entirely and reruns the primary analysis.

## 4. Ambiguity

An applicant root claimed by two registrants is dropped from **both** and written
to the ledger. The rule fired **zero** times: exact root equality is close to
injective over this candidate set, because company titles that differ only by the
stripped tokens are rare among SEC registrants that also hold 510(k)s.

The rule is still enforced, and `tests/test_science_002.py` pins it with a
synthetic collision (`Alpha Medical Inc` / `Alpha Medical Corp`), because a silent
double count is exactly the failure mode this study must not have.

## 5. Exclusions (14 candidate registrants, outcome-blind)

| ticker | why it is out |
|---|---|
| ABT | SEC SIC **2834 Pharmaceutical Preparations**. Abbott is a large device maker, but SEC's own classification is pharmaceutical and we do not override the registrant's official sector with our own opinion. |
| SNN | SIC 3842 is fine, but the registrant files IFRS 20-F and has **no US-GAAP `ResearchAndDevelopmentExpense` facts**, so B3 cannot be built. |
| TMO | SIC **3829** Measuring & Controlling Devices NEC - outside the pre-declared device set. |
| QDEL | SIC **2835** In Vitro & In Vivo Diagnostic Substances - outside the set (see S2 below). |
| MTLS, DDD, TEM | SIC **7372 / 7370** software and data services. |
| CAJPY | SIC **3861** photographic equipment. |
| CHD | SIC **2840** soap and cosmetics. |
| FMS | SIC **8090** health services. |
| PFE | SIC **2834** pharmaceuticals (its 11 attributable clearances are Hospira's). |
| BWAY | no XBRL R&D facts. |
| INMD | an Israeli foreign private issuer: files **6-K, not 8-K**, so no acceptance-instant activity series exists. |
| AAPL | SIC **3571** electronic computers. This is the clearest illustration of why the SIC gate exists: exact root matching had attached a `APPLE` applicant string with 9 clearances to Apple Inc. |

Two boundary decisions are visible here and are both declared in advance:

* **SIC 3826** (laboratory analytical instruments, i.e. IVD analysers) **is**
  included, which is what puts Bio-Rad in the universe. S2 removes it.
* **2835/2836** diagnostics-substance SIC codes are **excluded**, which removes
  QuidelOrtho. They classify the reagent, not the instrument.

## 6. What the resolution does *not* capture

**8.8%.** Only 3,143 of the 35,680 cleared 510(k)s filed in 2015-2026 are
attributed to the 48 universe firms. This is not a rounding issue, it is the
central measurement limitation of the study:

* the FDA applicant space is dominated by small and foreign manufacturers;
* a listed group's clearances are spread over establishments whose 510(k) applicant
  string is often not a registration name at all, so T_B cannot see them
  (`BOSTON SCIENTIFIC SCIMED` has no matching registration record);
* consequently each firm's outcome series undercounts its true regulatory activity,
  and the undercount is firm-specific.

The undercount is *time-consistent within a firm* (the same applicant roots are
used in every month, past and future), so it does not create a within-firm trend
artefact by itself. It does mean the label means *clearances filed under the
establishment names attributable to this group*, not *all clearances of the group*.
This is stated in DATASET_CARD.md and RESULTS.md rather than corrected, because no
correction would be evidence-based.

## 7. Verification performed

| check | where | result |
|---|---|---|
| no applicant string attributed to two firms | audit A4 | 0 collisions |
| no FDA k_number attributed to two firms | audit A4 | 0 collisions |
| every accepted link carries its literal evidence string | `artifacts/entity_matches.csv` | 189/189 |
| owner/operator relation re-read from the raw FDA file, not from a cached mapping | `pipeline.load_owner_map` reads the CSV built by the fetch step from the hashed ZIPs | yes |
| ambiguity rule works | `tests/test_science_002.py::EntityResolutionTests` | passes |
| no similarity matching anywhere in the code path | `entity.normalise_name` is the only comparator; no difflib, no ratio, no embeddings | verified by inspection and test |
