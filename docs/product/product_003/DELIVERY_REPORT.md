# PRODUCT-003 DELIVERY REPORT - Device Intelligence & Product Lineage

Branch: `feat/product-003-device-intelligence`, stacked draft PR with base
`fix/product-003-p0` (PR #48), which is itself stacked on `feat/product-002-trusted-intelligence`
(PR #47) and `feat/product-001-core-workbench` (PR #46). None of the upstream PRs is merged; nothing
in this branch treats them as released.

## 1. What was built

### Phase 0 - the two PRODUCT-002 P0 defects (PR #48, prerequisite)

* **P0-A reviewer authority.** The review API no longer accepts a client-supplied `reviewer_kind`;
  the actor kind is server-derived, `human_reviewed` is refused by the store and the API (403), the
  capability is reported via `GET /api/review/capabilities`, and legacy human claims are downgraded
  at read time without rewriting history. 11 tests, browser check E2E-17.
* **P0-B owner at event time.** Every attributed record now carries
  `attribution.historical_owner` derived from verified relations with effective dates compared to the
  event date. The misleading `original_registrant` basis is retired (400 with a hint); the new
  `historical_owner_verified` basis reports exactly which records it excluded (predecessor-owned and
  unknown-owner) instead of showing a lower number. 12 tests, 3 browser checks.

### Device model (Phase 1-3)

* Entities with stable identifiers: regulatory record, regulatory application, device identity,
  product family, recall record, organization, evidence reference. MedRadar ids are prefixed and never
  impersonate FDA identifiers.
* **23,974 device identities** (23,400 510(k) clearances + 574 PMA approvals), **61,632 applications**
  (incl. 37,658 PMA supplements), **630 PMA families** (574 with original, 56 supplement-only).
* **77,751 relations**: 55,870 confirmed (37,038 official PMA hierarchy + 18,832 recall-to-application
  from the official `k_numbers` field) and 21,881 candidates (20,227 recall candidates + 1,654
  same-name device clusters). Every confirmed relation cites the official field and URL; every
  candidate cites its rule; no candidate is ever presented as established.
* Explicitly not modelled: predicate relations, `record_mentions_device` tautologies,
  `manufacturer_of_device` claims, UDI/GUDID, cross-pathway equivalence - each with a documented reason.

### Web product (Phase 4)

* **Device Explorer** (`/devices`): name / trade-name / applicant / official-number search, organization,
  pathway, product-code, medical-specialty and relation filters, sorting, pagination, CSV export, and a
  separate unlinked-records browser.
* **Device Detail** (`/devices/{id}`): identity statement ("what this page represents"), applicant with
  its PRODUCT-002 attribution status, product code/specialty/class, **regulatory timeline** (event date
  vs first-observed date, chronological-not-causal), **product family view** (PMT hierarchy + versions
  ordered by decision date + recorded model names), confirmed relations with evidence, candidate
  relations labelled "not established", related recalls linked only by official K number, official
  evidence list, and a Markdown brief export.
* **Organization integration**: a Devices tab on the existing organization page (same workspace, not a
  separate tool), linking to the explorer with the organization filter.
* Chinese labels throughout the new surfaces; unknown-device error states.

## 2. Measured numbers

| | |
|---|---|
| Applications | 61,632 (510(k) 23,400 / PMA 574 / supplements 37,658) |
| Device identities | 23,974 |
| PMA families | 630 (574 complete, 56 supplement-only, largest 934 supplements) |
| Relations | 77,751 total: 55,870 confirmed / 21,881 candidate |
| Confirmed relations with official evidence + URL | 55,870 / 55,870 (100%) |
| Recalls linked by official K number | 15,022 (50.4%) |
| Recalls referencing only absent applications | 6,227 (8,457 external edges) |
| Recalls with no official reference (unlinked browser) | 8,576 |
| Devices with a confirmed relation | 4,496 |
| Devices with no relation | 14,742 (a property of the source, reported) |
| Ambiguity reported | 2,079 product-code mismatches, 2,291 multi-application recalls, 446 shared names |
| Device index build | ~4.7 s once per process (lazy); explorer query ~90 ms, detail ~10 ms |
| Human review of device relations | **0** |
| Device relation accuracy estimate | **UNKNOWN** |

## 3. Acceptance gates

| Gate | Verdict | Evidence | Open issues |
|---|---|---|---|
| **G0 UPSTREAM SAFETY** | **PASS** | PR #48: 11 authority tests + 12 historical-ownership tests + E2E-17 + historical basis tests across API/CSV/Markdown; PRODUCT-001/002 suites still green (215 product+governance tests) | Single shared token: human review remains unavailable by design |
| **G1 DEVICE IDENTITY** | **PASS** | model.py/build.py: application vs device vs family vs record; ids prefixed and deterministic; 510(k)=clearance identity, PMA=approval identity, supplements=versions; recall creates no identity; predicate/UDI explicitly not modelled | commercial SKU/UDI identity not covered |
| **G2 RELATIONSHIP EVIDENCE** | **PASS** | 55,870 confirmed relations all cite an official field + URL (100%); candidates 21,881 labelled and never confirmed; tests assert status==type mapping, evidence presence, no merge from similar names | no independent sample review of the device relations yet (accuracy UNKNOWN) |
| **G3 WORKING PRODUCT** | **PASS** | E2E-18 PMA scenario (P980016, 934 versions), E2E-19 510(k) scenario (K132673), E2E-20 recall + unlinked scenario, E2E-21 organization integration, E2E-22 unknown device; 22/22 browser checks | Chromium only |
| **G4 TRUSTWORTHY DATA** | **PASS** | identity/disclosure blocks, family basis, candidate labelling, unlinked browser with reasons, quality report with four separate verification levels and UNKNOWN accuracy, exports carry the same semantics | unlinked recall share 28.8% is a real gap |
| **G5 ENGINEERING QUALITY** | **PASS** | product+governance tests **215 passed** (24 new device tests), browser suite **22/22**, governance gates (licence/rule-audit/frozen/state/links) pass, PRODUCT-001/002 features unchanged | first device request builds the index (~4.7 s) |

No gate was lowered. The one honest PARTIAL/UNKNOWN is *device-relation accuracy*, reported as UNKNOWN
in the product itself rather than invented.

## 4. Status by item

**Completed and verified:** P0-A, P0-B, device identity model, PMA hierarchy, recall linkage via
official field, candidate system with rules and labels, device explorer, device detail with timeline
and family view, organization integration, device CSV + Markdown exports, quality report, unlinked
browser, 24 device tests, 5 browser checks, Chinese labels, screenshots.

**Partially completed:** relation coverage (4,496 of 23,974 devices have a confirmed relation - source
limited, reported), 510(k) family identification (no identifier exists; candidates only).

**Not started:** device-relation human/independent review, UDI/GUDID linkage, device-level snapshot
diffing, cross-regulator expansion, hosted alpha deployment.

## 5. P0 / P1

**P0:** none outstanding for this branch. (The PRODUCT-002 P0s are fixed in PR #48; human review
authority remains unavailable until server-side operator authentication exists - that is the fixed
state, not a regression.)

**P1:**
1. Relation accuracy is UNKNOWN: an independent review of a sample of the 55,870 confirmed relations
   (especially the interpretation of PMA families as one device) is the next credibility step.
2. 28.8% of recalls remain unlinked; the unlinked browser makes the gap visible but does not close it.
3. The device index is rebuilt per process (~4.7 s first request); a compact cache keyed by snapshot
   id would improve cold-start latency.
4. Device names are not unique and the explorer relies on substring matching; no fuzzy ranking yet.

## 6. How to verify

```bash
python -m pytest tests/product tests/governance -q        # 215 passed
python -m pytest tests/product/test_device_model.py -q     # 24 device tests
python -m pytest tests/product/test_reviewer_authority.py -q  # P0-A
python -m pytest tests/product/test_historical_ownership.py -q # P0-B
# browser acceptance (see tests/e2e/README.md) -> 22/22 checks
python -m medradar.product.web --port 8787     # public product, read-only
```

Then open `/devices`, search `P980016` (PMA family), `K132673` (510(k) with candidates), open a device
with a confirmed recall reference, and open `/devices?view=unlinked`.

## 7. The next three product capabilities

1. Independent review round on device relations (reuse the PRODUCT-002 ledger + sample protocol).
2. Device-level snapshot diff ("what changed for these devices since the last collection").
3. Recall-to-device identity for the unlinked 28.8% through an approved UDI source or reviewed links -
   never through product-code guessing.
