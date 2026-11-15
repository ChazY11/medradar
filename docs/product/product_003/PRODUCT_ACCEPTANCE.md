# PRODUCT_ACCEPTANCE

Three user scenarios, executed against the committed real data, through the real Web product.
Every identifier below is a real FDA identifier in the snapshot; no fabricated positive case is used.

## Scenario A - PMA regulatory history (the minimum core capability)

**User task:** "Show me a PMA device with a long regulatory history."

**Path:** Devices -> search `P980016` -> open the device -> read the family, versions and timeline.

**What the product does (measured):**

| Step | Result |
|---|---|
| Find the application | `P980016` resolves to device `device:openfda_pma:P980016` |
| Original approval | shown with its decision date, trade/generic name and the official FDA PMA page |
| Supplements | **934** versions listed, ordered by decision date, each with supplement type/reason and its own official URL |
| Hierarchy evidence | every version relation is confirmed by the official PMA number on both records (37,038 such relations in the snapshot) |
| Timeline | original approval + 934 supplements, each marked with event date and first-observed date |
| Family honesty | the page states that the family is the FDA application hierarchy, not a commercial brand family |

**Order-level detail:** supplements with type "30-Day Notice" (21,465 in the snapshot), "Normal 180 Day
Track" (5,251), "Real-Time Process" (4,988) are all visible with their own official pages.

**Known limit:** the original `trade_name` field of a PMA is a list of model names, so the family page
shows model names as recorded rather than a curated product line.

## Scenario B - 510(k) device query

**User task:** "What is this clearance, and is there anything else known about the device?"

**Path:** Devices -> filter 510(k) + candidate relations -> open a device (example: `K132673`).

**What the product does (measured):**

| Step | Result |
|---|---|
| Locate the record | `K132673` resolves to its device identity and official FDA 510(k) page |
| Device name and applicant | shown verbatim from the FDA fields |
| Product code and specialty | shown (with the FDA classification dictionary category) |
| Official material | official record link on the page and in the exported brief |
| Product family | **none claimed**: the page states that no evidenced family exists for 510(k), and why |
| Candidate relations | 22 candidates for this device, each with rule, product code, applicant, normalised name and the label "candidate only - not established" |

**Known limit:** a 510(k) page cannot promise a family. It remains useful without one: identity,
applicant attribution, product code, official record, related recalls (when the official K reference
exists) and candidates are all actionable.

## Scenario C - recall link and evidence verification

**User task:** "Which approved device does this recall concern, and how do you know?"

**Path:** Devices -> open a device with a confirmed recall reference (example: `K000001`), or the
unlinked-record browser for recalls with no reference.

**What the product does (measured):**

| Case | Behaviour |
|---|---|
| Recall whose official `k_numbers` field names a 510(k) in the snapshot | shown as a **confirmed** related recall, with the K-number value as evidence and a link to the official recall page (15,022 recalls, 18,832 confirmed relations) |
| Recall whose K number is outside the snapshot | counted as an external reference (6,227 recalls / 8,457 edges); no edge is drawn to a record that does not exist |
| Recall with no `k_numbers` field | listed in the unlinked browser with the reason "the record has no official K-number reference" (8,576 recalls) |
| Recall sharing only the product code / similar name | shown as a **candidate** (20,227 candidates), labelled "not established"; never counted as a related recall |
| Date proximity | not used as evidence anywhere; a recall near a supplement date is not linked because of the date |

## Cross-scenario guarantees (asserted by tests and browser checks)

* A PMA supplement can never attach to a different PMA number (`test_a_supplement_never_attaches_to_a_different_pma`).
* Two clearances with the same product code, applicant and device name stay two devices and produce a
  candidate only (`test_no_device_merge_from_a_similar_name`).
* A recall creates no device identity and is linked only through its official field
  (`test_recall_links_come_only_from_the_official_k_number_field`).
* Unknown identity is labelled, not disguised (`test_device_detail_reports_identity_disclosures_and_evidence`,
  E2E-22 for the unknown-device error state).
* The name is not treated as unique: 446 shared normalised names are reported and never merged.

## Executed evidence

* Browser acceptance: **22/22 checks** (E2E-18 PMA scenario, E2E-19 510(k) scenario, E2E-20 recall +
  unlinked scenario, E2E-21 organization integration, E2E-22 unknown device), executed against the real
  backend and the committed snapshot.
* Product tests: **215 passed** including 24 device-model/API tests.
* Screenshots: `screenshots/01-device-explorer.png` ... `06-devices-zh.png`.
