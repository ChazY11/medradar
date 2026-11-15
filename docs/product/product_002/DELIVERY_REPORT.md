# PRODUCT-002 DELIVERY REPORT - Trusted Intelligence & Private Alpha

Branch: `feat/product-002-trusted-intelligence`, stacked draft PR with base
`feat/product-001-core-workbench` (PRODUCT-001, PR #46, still open at the time of writing).
Nothing in this delivery treats PR #46 code as merged or as `main`.

## 1. What actually changed

### Product data trust (Phase A)

* **Re-defined attribution metrics.** A single module (`medradar/product/metrics.py`) now computes
  Attributed Share, Rule-verified Share, Curated Share, Estimated Attribution Precision and Retrieval
  Coverage at record, applicant-string and organization level, and returns UNKNOWN where the data
  cannot support a claim. Definitions ship with the numbers (`GET /api/metrics`) so the API, the UI,
  the CSV and the Markdown exports cannot disagree.
* **Real status vocabulary.** 1,590 accepted spellings are now classified as `proposed` (1,199),
  `rule_verified` (221), `evidence_verified` (170), `human_reviewed` (0), `rejected` (9). The
  PRODUCT-001 "curated" flag is interpreted, never trusted: a corporate-relation spelling stays
  provisional until documentary evidence exists. A rule is reported separately and is never called
  review.
* **Identity review workspace.** Loopback-only admin service with a token boundary, an append-only
  SQLite ledger (UPDATE/DELETE blocked by triggers), a queue ordered by records affected, per-case
  evidence (verbatim string, FDA records with official links, candidate organizations, risk flags,
  ownership relations), decision form, history and withdrawal, offline CLI, JSON export/import, and
  an impact report that proves which organizations changed and that all others did not.
* **Historical ownership.** Eight ownership relations, four evidence-verified with filing URLs and
  effective dates, four explicitly UNRESOLVED. Organization pages show the counting basis, the
  before/after split of predecessor-entity records, and the uncertainty. The comparison and the
  exports support an explicit original-registrant basis.
* **Independent validation.** Pre-registered stratified sample (38 cases, fixed seed), documentary
  decision rule, SEC Exhibit 21 evidence for 16 organizations, Wilson interval over decidable cases,
  and an honest statement that human review is still required.

### Engineering (Phase C)

* **Playwright in CI** (`.github/workflows/e2e.yml`): 16 real-browser checks against a real backend,
  fresh Chromium in CI, artefacts uploaded, failures fail the job.
* **Data invariants** (`tests/product/test_invariants.py`): unique record ids, organization counts sum
  to the attributed total, PMA originals vs supplements, recalls counted as records, untrusted
  mappings filterable, pagination equals totals, CSV equals the filtered set, comparison uses one
  window/unit, missing snapshot is an error not zero activity, review decisions do not leak.
* **Governance hardening** (`GOV-0005`/`RC-0005`): the derived-binary exception is now limited to
  `openfda_device` files under `medradar/product/snapshot/*.gz`, gzip only, <= 32 MiB, SHA-256 bound,
  fail-closed on any missing key, with counter-example tests (sha mismatch, unregistered gzip, other
  GREEN source, ELF/ZIP/SQLite/Parquet, path escape, disabled allowlist, AMBER/RED unchanged).
* Product tests: **47 -> 96**, all passing. Governance tests: 43 -> 71, all passing.

### Product experience (Phase D) and alpha (Phase E)

* Overview, organization page, comparison, sources page and evidence drawer now show the verification
  split, the counting basis, the metric definitions and a glossary; the comparison gained ownership
  basis and verified-only filters plus a comparability verdict and an explicit "what this does not
  show" list.
* Chinese now covers the metric definitions, status meanings, warnings, risk flags and the review
  workspace (not only navigation).
* `ALPHA_RELEASE_GUIDE.md` (install, start, demo, rollback, troubleshooting, disclaimer),
  `USER_TEST_TASKS.md` (three tasks + feedback template), `KNOWN_LIMITATIONS.md`,
  `scripts/alpha_smoke.py` (16/16 checks).

## 2. Real problems fixed (not features)

1. **A number that read as accuracy was not accuracy.** 99.92% -> Attributed Share, with Curated
   Share (9.85%) and Precision (UNKNOWN) reported separately everywhere.
2. **"Curated" in the registry was not evidence.** It is now derived: 221 rule-verified, 170
   evidence-verified, 1,199 proposed, 0 human-reviewed - and the pending-proposal share is visible
   per organization instead of being a footnote.
3. **The gzip exception was too broad.** Any GREEN hash-declared binary (including ELF/ZIP/SQLite)
   anywhere could pass. Now scoped by source, path, kind, size and hash, with counter-examples.
4. **A group's current ownership silently rewrote its history.** GE HealthCare's entire 5-year window
   was filed by General Electric; the product now states it, splits before/after the spin-off, and
   offers the original-registrant basis (which returns 0 records for that window).
5. **An attribution error had no correction path.** Now there is one: append-only, evidenced,
   reversible, with an impact statement and 58 unchanged organizations.
6. **The untrusted-mapping filter was ambiguous.** `review=curated` meant "the registry said so". It
   now means evidence-verified or human-reviewed, with explicit `rule_verified` / `provisional`
   filters.

## 3. Identity review coverage and validation result

| Item | Value |
|---|---|
| Accepted spellings | 1,590 |
| Status split | proposed 1,199 / rule_verified 221 / evidence_verified 170 / human_reviewed 0 / rejected 9 |
| Attributed records | 91,384 of 91,457 (99.92%) |
| Evidence-verified or human-reviewed records | 8,998 (**9.85%**) |
| Rule-verified records | 40,339 (**44.14%**) |
| Provisional records | 42,047 (**46.01%**) |
| Queue awaiting review | 1,172 strings / 42,050 records |
| Pre-registered validation sample | 38 cases, 13 decidable, 13 supported, 0 contradicted, 25 undecidable |
| Precision estimate (decidable only) | 100%, 95% CI **0.772-1.000**, reviewer = agent |
| Human review completed | **no** |

Honest headline: **the product can now prove how much of its attribution is verified (9.85%) and it
cannot yet claim an accuracy figure; a human sample review is the next step, and the protocol,
sample and worksheet are ready.**

## 4. CI and browser acceptance status

* `python -m pytest tests/product -q`: **96 passed**.
* `python -m pytest tests/governance -q`: **71 passed, 28 subtests**.
* Browser suite: **16/16 passed**, executed twice locally against the real backend.
* Governance gates: `check_licence`, `check_rule_audit`, `check_frozen`, `check_state` all PASS.
* GitHub Actions: `ci`, `governance` and the new `e2e` workflow run on the PR; see the PR checks for
  the authoritative result (this report does not claim green before the run).

## 5. Data governance review result

* GOV-0004/RC-0004 independently re-reviewed; the exception was too broad (source, path, kind, size
  were unconstrained). Narrowed under GOV-0005/RC-0005 with ten counter-example tests.
* Inventory regenerated; the three snapshot gzip files are the only hash-declared binaries and their
  SHA-256 values match the snapshot manifest and the bytes.
* openFDA redistribution: public domain / U.S. Government work, attribution present, no endorsement
  claimed. Residual risk: this is a repository consistency control, **not a legal opinion**; a human
  owns the licence judgement.
* RED/AMBER sources remain protected: the policy entries for the Internet Archive lane are unchanged
  and a test asserts AMBER/RED failures still occur.

## 6. Alpha availability

Verified locally end to end: install (`pip install -e ".[product]"`), start
(`python -m medradar.product.web`, `python -m medradar.product.review serve`), and the three user
tasks (16/16 alpha checks) including CSV and Markdown export. It is a **local, controlled alpha**;
there is no hosted deployment and no external participant. Rollback, troubleshooting and the
snapshot identity are documented in `ALPHA_RELEASE_GUIDE.md`.

## 7. Gate verdicts

| Gate | Verdict | Evidence | Open issues |
|---|---|---|---|
| **G1 ATTRIBUTION HONESTY** | **PASS** | `/api/metrics`, UI blocks, exports and `tests/product/test_attribution_status.py` + `test_metrics.py`; attributed vs rule vs curated vs precision vs retrieval are distinct in code, API, UI and CSV/MD; 0 human-reviewed | Definition might still be misread without the in-UI banner; keep it |
| **G2 REVIEW WORKFLOW** | **PASS** | `/review` workspace, append-only ledger with DB triggers, token + loopback boundary (E2E-16), impact report; real correction changed only Abbott (+17) and 58 organizations did not move; withdrawal preserved history | Token is a single shared secret; no per-user identity yet (P1 for a larger team) |
| **G3 VALIDATION** | **PARTIAL** | Pre-registered 38-case sample, documentary rule, SEC evidence for 16 organizations, Wilson CI, undecidable share reported; no contradicted case | 66% undecidable; reviewer is an agent; human sample review not done - precision stays a provisional, caveated estimate |
| **G4 ENGINEERING** | **PASS** | 96 product tests, 71 governance tests, new `e2e` workflow with 16/16 browser checks and artefact upload, failing checks fail the job | Chromium-only matrix; no visual-regression baseline |
| **G5 GOVERNANCE** | **PASS** | GOV-0005 tightening + 10 counter-example tests + hash-bound inventory + all four gates PASS | Human licence judgement still required; not a legal opinion |
| **G6 ALPHA READY** | **PARTIAL** | Alpha guide executed; 16/16 alpha smoke checks; export/basis/rollback documented | No external user test; no hosted deployment; Docker flow not verified in CI |

No gate was lowered to reach a PASS. G3 and G6 stay PARTIAL deliberately.

## 8. Status by item

**Completed and verified:** metric separation (API/UI/exports/tests), status derivation, review ledger
+ workspace + permissions + impact, historical ownership for 3 companies with filings + 4 explicit
UNKNOWNs, comparison basis/review filters, governance narrowing, E2E in CI, invariants, alpha smoke,
documentation set.

**Partially completed:** independent validation (evidence-limited; agent reviewer), Chinese coverage
(menu + the pages listed above, not every string), ownership coverage (3 of 59 organizations).

**Not started:** external alpha participants, human review of the sample, hosted deployment, Docker
image verified in CI, accessibility audit, Firefox/WebKit matrix, historical group structure beyond
the four verified relations.

## 9. P0 / P1 issues

**P0 (blocking a trustworthy claim, not the build):**
1. Attribution precision cannot be stated until a human sample review is completed. Any external
   communication must use "9.85% evidence-verified" and never a % accuracy figure.

**P1:**
1. 46% of attributed records rest on no rule and no evidence; the review queue is the path out and it
   is large (1,172 strings / 42,050 records).
2. Corporate-relation mappings (subsidiary/division/historical) have no evidence for 49 spellings;
   they are invisible to a user unless they read the verification block.
3. Review service authentication is a single shared token; fine for a local alpha, not for a team.
4. Retrieval coverage remains UNKNOWN - the product cannot say what it missed.

## 10. The next three product capabilities worth building

1. **Evidence pipeline for corporate relations.** Automate the jurisdiction-filing extraction
   (already a script) into a reviewed registry so the 49 corporate-relation spellings and the other 54
   organizations become decidable; this is the highest-leverage path from 9.85% toward a defensible
   curated share.
2. **Human review round on the fixed sample.** The protocol, sample file, decision rule and UI exist;
   one analyst-day of review turns G3 from PARTIAL into a real, quoted precision estimate (and the
   same workflow then scales to the queue).
3. **Retrieval-coverage measurement.** Enumerate official identifiers per source and date window,
   then measure presence/absence against the retrieved set - the only way to say what MedRadar is
   missing instead of reporting UNKNOWN.
