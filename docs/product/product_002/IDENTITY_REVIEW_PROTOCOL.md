# IDENTITY_REVIEW_PROTOCOL

MedRadar PRODUCT-002. This is the protocol a reviewer follows, and the definitions the product is
allowed to publish. It is deliberately stricter than the PRODUCT-001 documentation it replaces.

## 1. Why this exists

PRODUCT-001 reported one number: 99.92% of collected records were "attributed". Readers could
reasonably hear that as "MedRadar's company attribution is 99.92% correct". It is not. 99.92% is
**Attributed Share**: the share of the *collected sample* that carries some organization
attribution. It says nothing about correctness, review, or how much of the FDA population was
retrieved.

PRODUCT-002 separates five measurements that must never be merged:

| Metric | Unit | What it measures | What it is NOT |
|---|---|---|---|
| **Attributed Share** | records / applicant strings / organizations | of the collected sample, the share carrying an organization attribution | not match precision, not recall, not FDA coverage |
| **Rule-verified Share** | records | attributed records whose mapping a deterministic, reproducible name rule justifies | not evidence, not human review |
| **Curated Share** | records | attributed records whose mapping is *evidence-verified* or *human-reviewed* | not the same as attributed share (it is far smaller) |
| **Estimated Attribution Precision** | proportion + interval | correctness of attributed mappings, estimated from an independent sample | not derivable from attributed share; UNKNOWN if no sample exists |
| **Retrieval Coverage** | proportion | share of a defined sampling frame that the queries retrieved | UNKNOWN without an independent denominator |

The API, the UI, the CSV and the Markdown exports all compute these from one module
(`medradar/product/metrics.py`) and ship the definitions with the numbers
(`/api/metrics` returns them), so they cannot drift apart.

## 2. Status vocabulary (the only one the product uses)

| Status | Meaning | Counts as curated? |
|---|---|---|
| `proposed` | machine-proposed or authoring-time spelling, no independent verification recorded | no |
| `rule_verified` | a deterministic rule justifies acceptance: name identity (`name_identity_v1`) or lexical equivalence (`lexical_equivalence_v1`) | no |
| `evidence_verified` | an independent documentary source is recorded for this exact decision (URL + access date + reviewer) | **yes** |
| `human_reviewed` | a **named human** made or confirmed the decision (reviewer_kind = human) | **yes** |
| `rejected` | reviewed and determined not to belong to the organization | no |
| `unresolved` | reviewed and not determinable from the recorded evidence | no |

Rules:

1. **A rule is not a reviewer.** `rule_verified` is reported separately and never counted as curated.
2. **An agent cannot award `human_reviewed`.** The ledger rejects the write
   (`ReviewError: human_reviewed requires reviewer_kind=human`), and there is a test for it.
3. **No silent bulk upgrades.** The PRODUCT-001 registry flag (`curated` / `pending_review`) is
   interpreted, not trusted: a `curated` entry whose basis is a corporate relation becomes
   `proposed` until evidence is recorded; a `pending_review` entry can only reach `rule_verified`
   through a named deterministic rule.
4. **Evidence must be documentary.** `evidence_verified` requires an evidence reference whose type is
   a jurisdiction filing, regulator record, corporate document or third-party report **and** a URL.
   An agent's own judgement is not evidence.

## 3. The review workspace

Internal tool. It is not part of the public site and cannot be reached from it.

* **Start:** `python -m medradar.product.review serve --port 8788` (loopback only; refuses other hosts
  unless `--allow-remote` is passed explicitly and the operator provides their own boundary).
* **Token:** generated on first start at `data/identity/review.token` (32 bytes, file mode 600),
  required on every `/api/review/*` request as `X-MedRadar-Review-Token`. The browser keeps it in
  sessionStorage after the operator pastes it once: no cookie, so a cross-site request cannot carry it.
* **Defence in depth:** the service rejects non-loopback clients even when proxied, rejects
  cross-origin writes, and the public application (`create_app`) contains **no write route at all**
  (a test asserts `/api/review/queue` is 404 there).
* **Offline mode:** `python -m medradar.product.review decide|revoke|export|import` appends to the same
  ledger from a terminal, for reviewers who work offline.

### What a reviewer can do

| Action | Effect on the ledger | Effect on the product |
|---|---|---|
| Approve a mapping | appends a decision with status `rule_verified`/`evidence_verified`/`human_reviewed` | the applicant string is attributed to that organization |
| Reassign | appends a decision with a new `organization_key` | records move to the new organization on the next request |
| Reject | appends a rejection | the string stops being attributed; records are counted as rejected |
| Mark unresolved | appends an `unresolved` decision | the string appears in the queue as reviewed; it is not counted as verified |
| Withdraw | appends a revocation of a decision uid | the previous state is restored; both decisions stay in the history |

The ledger is append-only at the database level: SQLite triggers raise on `UPDATE` and `DELETE` of
`review_decisions`, so even a bug cannot rewrite history. Every write also appends to `review_audit`.

The product reloads its dataset when the ledger changes (fingerprint check in `DatasetHolder`), so
the very next page load reflects the decision — no restart, no stale cache.

## 4. UI of the workspace

`/review` in the built workbench, served by the review service:

* queue ordered by **number of records affected**, filterable by status, organization, risk flag and
  applicant string, sortable four ways;
* per case: verbatim applicant string, record count, collection scope, current mapping, why it was
  proposed, risk flags (hypotheses, never conclusions), candidate organizations, the FDA records that
  depend on the mapping with links to the official pages, ownership relations that mention the string,
  the decision form (action, resulting status, evidence type/URL/title/quote, reviewer, reviewer kind,
  note) and the full decision history with a Withdraw button;
* an impact banner showing **which organizations changed and how many did not** (see §6).

## 5. Independent validation protocol (pre-registered)

**Sample frame:** every applicant string in the committed snapshot (1,563 strings; 1,491 with
records). **Strata** (fixed before scoring, in `tools/validation/validate_attribution.py::SAMPLE_DESIGN`):

| Stratum | Definition | Population |
|---|---|---|
| S1 high volume | attributed spelling with >= 1000 records | 6 |
| S2 mid volume | attributed spelling with 100-999 records | 75 |
| S3 low volume | attributed spelling with 1-99 records | 1101 |
| S4 lexical rule | status came from lexical equivalence | 146 |
| S5 ownership evidence | already evidence-verified through an ownership relation | 176 |
| S6 corporate relation | subsidiary/division/historical-name basis with no evidence | 49 |
| S7 ambiguous scope | retrieved under more than one organization's collection scope | 2 |

**Selection:** 6 per stratum (all cases in S1), deterministic `random.Random(20261115)` over a
name-sorted population. The sample file is committed (`validation/sample.json`) and cannot be
redrawn after seeing results.

**Decision rule** (pre-registered, quoted verbatim in `validation/precision.json`):

> SUPPORTED when the applicant spelling matches an entity name in the collected jurisdiction filing
> of the attributed organization (exact match after NFC+casefold+punctuation collapse, or the entity
> name contains the spelling's distinctive token sequence as whole words), or when a verified
> ownership relation covers the spelling for that organization. CONTRADICTED only when the collected
> filing shows a different organization owns that exact entity name. UNDECIDABLE when no collected
> documentary source names the spelling: the case is excluded from the precision numerator and
> denominator and reported separately. No case is scored correct on the basis of the registry's own
> claim.

**Evidence base:** SEC EDGAR annual-filing Exhibit 21 / 20-F group-company tables for the US-listed
tracked organizations (downloaded with a contact User-Agent; the filing URL, accession and filing
date are recorded in `validation/sec_entity_lists.json`, so any reader can re-fetch and re-extract).
Adding filings after the sample was drawn is allowed (it adds independent documents to fixed cases);
changing the sample or the rule is not.

**Estimate:** Wilson 95% interval over decidable cases; the undecidable share is reported as a
first-class result. Result: see `ATTRIBUTION_VALIDATION.md`.

## 6. Provenance of a review decision and its blast radius

Every decision records: applicant string + normalised key, action, resulting status, basis, evidence
(type, URL, title, quote, access date), note, reviewer identity, **reviewer kind**, timestamp,
snapshot id, and the decision it supersedes. `GET /api/review/impact` computes, from the baseline
registry and the current dataset, exactly which organizations changed and how many did not — the
product's own proof that a correction did not leak into unrelated organizations.

## 7. What a reviewer must not do

* Score a case as supported only because the registry already says so.
* Mark `human_reviewed` from a machine's judgement.
* Use a search engine snippet as the only evidence when a primary filing is available.
* Edit the ledger database directly.
