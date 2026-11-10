# INDEPENDENT VERIFICATION — MedRadar CONVERGENCE-001

**Role:** independent verifier (task `task-4`). Not a reviewer of intentions — a recomputer of numbers.
**Principle:** every number below was produced by this verifier from raw bytes, raw SQLite pages and
the two published schema documents. No claim is accepted because a developer artifact says so.

**Machine artifact:** `research/convergence/verification/verification_summary.json`
**Console transcript:** `research/convergence/verification/verification_console.txt`
**Harness:** `tools/convergence/verify/verify.py` (stdlib only, `--json`, exit 1 on any FAIL)
**Harness digest:** two consecutive runs produced byte-identical JSON
(`42F25ED9A98A8787F0C8602034E3C198803F4C8E8FE86726EF5A2237BF1F23FE`); the report contains no
wall-clock timestamps for that reason.

```
PASS 72   FAIL 11   UNVERIFIABLE 7   (total 90)
```

---

## 0. Independence protocol actually followed

| Rule | How it was met |
|---|---|
| No application imports | The harness imports only its own `vlib`. `medradar.integration.*`, `tools/convergence/*` (other than `tools/convergence/verify/`) and the HORIZON/ATLAS experiment scripts are never imported or executed. |
| Recompute from first principles | `content_hash`, `dedupe_key`, `evidence_id`, `canonical_key`, GTIN Mod-10, JSONL record counts, SHA-256, SQLite counts, the 220 MB MDALL cache recount and the DOI pair count are all re-implemented inside `tools/convergence/verify/vlib/`. |
| Read the specification | `research/horizon/hz/schema.py`, `medradar/atlas/evidence/schema.py`, `EXP_H2_SELECTION_RULE.md` and the two HORIZON reports were read as *specifications*, then re-implemented — never called. |
| No network | Every input is a local file. |
| Read-only originals | The ATLAS staging database and the MDALL cache are opened with `mode=ro`; the HORIZON-001 worktree is read only. The integration staging database is copied with the SQLite backup API into verifier scope and every V7 verdict is bound to that snapshot digest. |
| No state changes | No git write command was issued. Only `git ls-files`, `git log`, `git branch --contains`, `git cat-file`, `git rev-parse` were used. |

**Where the claims are made.** Claim sources are cited per check in the machine artifact
(`claim_source`) and per row in this document as `path:line`.

---

## 1. Verdict summary

| Group | Checks | PASS | FAIL | UNVERIFIABLE | Verdict |
|---|---:|---:|---:|---:|---|
| V1 export integrity | 18 | 17 | 1 | 0 | PASS with one structural defect |
| V2 EXP-H2 counts | 10 | 7 | 3 | 0 | FAIL — prose contradicts the pair file |
| V3 ATLAS 934 bridge | 20 | 17 | 1 | 2 | PASS — the 934 is fully substantiated |
| V4 cross-source identity | 8 | 8 | 0 | 0 | PASS — HORIZON's 0 is sample coverage |
| V5 time semantics | 10 | 6 | 4 | 0 | FAIL — two of the four clocks are not clocks |
| V6 licence isolation | 8 | 8 | 0 | 0 | PASS at tree/index level, one history exposure |
| V7 adapter fidelity | 16 | 8 | 3 | 5 | FAIL — the frozen import holds zero evidence rows |

Eleven FAILs, nine distinct defects (several checks share one root cause). Defects are enumerated
in §9 with exact numbers and owners.

---

## 2. Inputs and identity of the inputs

| Input | Identity recomputed here |
|---|---|
| `research/horizon/exports/horizon-2026-11-10/` | 23 payload files present, 1 declared-and-absent (`un_comtrade.jsonl`, quarantined). All 23 byte lengths and SHA-256 digests equal the manifest; all 23 `.sha256` sidecars equal both the bytes and the manifest. |
| `MANIFEST.json` | SHA-256 `eaa1cbf5e49db90ba39f938be759c5df3581f4fbbe135cfcd5455622ff6e4d4d`; the adapter's own report records the same digest. |
| Quarantined `un_comtrade.jsonl` | Absent here; present in `worktrees/horizon-001` with SHA-256 `5bbcf42b1ef1…92b33d`, 1,832,311 bytes and 608 records — exactly the manifest entry. The quarantine withholds the *right* file. |
| ATLAS DB `worktrees/atlas-001/research/atlas/staging/atlas.sqlite` | opened `mode=ro`; 7,254 evidence rows, 8,610 relations, 7 collection runs. |
| MDALL cache `mdall_active_deviceidentifier.json` | 219,970,233 bytes, 1,673,926 rows (streamed, not loaded). |
| Integration staging DB | **frozen snapshot** `research/convergence/verification/snapshots/convergence_staging_snapshot.sqlite`, 26,984,448 bytes, SHA-256 `37f2bc35f080a188c879a0998bb63ec93b720f592383544f1c00567a313f782d`. |

The staging database is a live development target; it changed between two of this verifier's own
reads (see D3). Binding V7 to a snapshot digest is the only way to keep the verdict reproducible.

---

## 3. V1 — export integrity

**Claims.** Manifest bytes/digests/row counts are true; totals are 24 sources / 6,492 records /
20,335,003 bytes; the absent set is exactly the UN Comtrade pair; rows validate against
`horizon.evidence.v1`.

**Method.** Plain `hashlib`, byte lengths, non-empty line counts, JSON parse of every line,
independent re-implementation of `content_key`/`compute_hash` (`hz/schema.py:146-173`),
`dedupe_key` (`:232-258`), the closed vocabularies (`:28-79`) and the README table parser.

**Results.**

| Check | Result | Recomputed |
|---|---|---|
| declared files present | PASS | absent set = `{un_comtrade.jsonl, un_comtrade.jsonl.sha256}` exactly |
| no undeclared files | PASS | 50 files on disk vs 50 accounted for |
| byte lengths | PASS | 23/23 |
| SHA-256 | PASS | 23/23 |
| record counts | PASS | 23/23, zero blank lines, zero unparseable lines |
| totals | PASS | sources 24, records **6,492**, bytes **20,335,003** |
| `.sha256` sidecars | PASS | 23/23 |
| per-record `content_hash` | PASS | **6,492/6,492** recompute exactly |
| schema conformance | PASS | 6,492/6,492 satisfy the closed vocabularies and ISO clocks |
| per-source counters | PASS | identifiers / public / event counts recompute for all 23 |
| per-source `unique_dedupe_keys` | PASS | all 23, including the collapsing ones (canada_mdall 60, pma 33, reglist 26, nih 9, ted 93, find_a_tender 16) |
| licence agreement | PASS | `per_source` = `licence_summary` = `registry_snapshot` = every row, all 24 |
| README table | PASS | the 23 published rows recompute column by column |
| quarantine provenance | PASS | upstream digest/bytes/records match the manifest entry |
| record content uniqueness | PASS | no duplicate `content_hash` in any source |
| **record identity uniqueness** | **FAIL** | **62 rows share a `source_record_id`** — see D2 |

The export is byte-for-byte the artifact the manifest describes. This is the strongest layer of the
whole deliverable: a reader who trusts only the manifest is not misled about bytes, counts or
licences.

**Finding (FAIL, D2).** `source_record_id` is not unique in 3 of 23 sources, so it is an entity key
rather than a record key:

| Source | Rows | Distinct `source_record_id` | Extra rows sharing an id |
|---|---:|---:|---:|
| `openfda_device_pma` | 60 | 33 | 27 |
| `openfda_device_registrationlisting` | 60 | 26 | 34 |
| `openaire` | 59 | 58 | 1 |
| **total** | | | **62** |

These are *not* duplicates: one PMA number carries several supplements with distinct content
(`P980016`: S514, S136, S413, S837 — four distinct `content_hash`), and one registration number
carries up to nine establishment-type rows. `README.md:14` ("Rows are already deduplicated *within*
a source") is true about content and silent about the key. ATLAS's documented evidence id is a
function of `(source_id, evidence_type, source_record_id)`
(`medradar/atlas/evidence/schema.py:105-113`), so this upstream key choice forces a downstream
collision — quantified in V7.

---

## 4. V2 — HORIZON EXP-H2 counts

**Claims under test.**
`research/horizon/experiments/regulatory/EXP_H2_SUMMARY.json:11-88` (machine artifact) and the prose
in `research/horizon/EXPERIMENT_RESULTS.md:104-137` and
`research/horizon/reports/REGULATORY_FRONTIER_REPORT.md:186-210`.

**Method.** Parse every line of `EXP_H2_PAIRS.jsonl` as JSON; count verdicts, construction rules and
signal flags; rebuild the signal-combination table from the `signals` block; test the verdict rule
from `EXP_H2_SELECTION_RULE.md:41-49`; check that every referenced FDA/Canada record exists in the
frozen export; parse both prose documents with anchored regexes.

**Recomputed truth (726 pairs).**

| Quantity | Recomputed |
|---|---|
| pairs | **726** |
| verdicts | **UNKNOWN 726, REJECTED 0, CONFIRMED 0** |
| construction rules | candidate 700, `HN3_same_family_different_device` 14, `HN4_subsidiary_vs_parent` 12 → **26 hard negatives** |
| signals fired | S1 **0**, S2 **0**, S3 **708**, S4 **0**, S5 **37** |
| combinations | `S3` 689 (all UNKNOWN), `S3+S5` 19 (all UNKNOWN), `S5` 18 (all UNKNOWN) |
| verdict-rule violations | 0 of 726 (CONFIRMED requires S4; no pair could be REJECTED on the stated grounds) |
| pair provenance | every referenced FDA and Canada record is in the frozen export; 320/320 and 174/174 |

`EXP_H2_SUMMARY.json` agrees with all of the above (PASS, `v2.summary_agreement`). The prose does not.

**FAIL — the prose is wrong in 8 of 9 numbers (`v2.doc_experiment_results`).**

| Number | Prose says | Pair file says | Where |
|---|---:|---:|---|
| pairs | 712 | **726** | `EXPERIMENT_RESULTS.md:105,112` |
| REJECTED | 387 | **0** | `EXPERIMENT_RESULTS.md:117` |
| UNKNOWN | 325 | **726** | `EXPERIMENT_RESULTS.md:118` |
| S2 fired | 445 | **0** | `EXPERIMENT_RESULTS.md:132` |
| S2 verdicts (R/U) | 387 / 58 | **0 / 0** | `EXPERIMENT_RESULTS.md:132` |
| S3 fired | 365 | **708** | `EXPERIMENT_RESULTS.md:133` |
| S3 verdicts (R/U) | 40 / 325 | **0 / 708** | `EXPERIMENT_RESULTS.md:133` |
| hard negatives | 12 | **26** | `EXPERIMENT_RESULTS.md:135` |

`REGULATORY_FRONTIER_REPORT.md` repeats the same wrong numbers at `:188,194,195,204,205,208`
(FAIL in 8 of 10 parsed numbers).

Two structural observations, offered as arithmetic, not as a conclusion:

* `712 = 387 + 325`; `726 − 712 = 14`, which is exactly the `HN3` count. The prose is internally
  consistent with a **712-row run in which HN3 did not reject** — i.e. it describes a different
  pair set, not a rounding of this one.
* The prose's own signal table cannot be produced from this pair file: it reports S2 firing 445
  times, while `S2` is false for all 726 pairs.

**FAIL — signal definition drift (`v2.doc_signal_definitions`).**
`EXPERIMENT_RESULTS.md:110` defines **S5** as "multi-field conjunction"; the pre-registration
defines S5 as "name tokens overlap ≥2, not covered by S1"
(`EXP_H2_SELECTION_RULE.md:39`). A reader of the results document cannot know what S5 counts.

**Note (not a failure).** The pre-registration defines four hard-negative rules; only HN3 and HN4
were constructed (HN1/HN2 attempted 0), and `EXP_H2_SUMMARY.json:24-29` says so explicitly. The
experiment therefore cannot speak to HN1/HN2 — it does not claim to.

**Who is wrong:** the two prose documents. `EXP_H2_SUMMARY.json` and `EXP_H2_PAIRS.jsonl` agree
with each other and with an independent recount. The prose is not a stale copy of the artifact — it
describes a 712-pair run with 387 REJECTED that produced no artifact in this worktree.

---

## 5. V3 — the ATLAS 934 bridge, re-derived

**Claim.** `docs/atlas/RESEARCH_VALIDATION.md:32,69` and
`research/atlas/reports/identity_pilot.json`: 1,200 deterministic GTIN candidates → 942 resolved
GUDID records → **934** paired device records, each `SAME_DEVICE_IDENTITY` and `CONFIRMED` by exact
DI equality, none revoked.

**Method.** Read-only SQL; parse `basis_json` for the shared identifier; validate every shared value
as GTIN-14 with an independently written GS1 Mod-10 routine; test that the identifier is physically
stored on *both* sides; reconstruct `evidence_id`, `content_hash` and `canonical_key` from the stored
payload/identifiers using the documented rules; recount the MDALL cache; compare
`identity_pilot.json` and the published relation census against the database.

**Results — the 934 survives every test.**

| Check | Result |
|---|---|
| relation count | **934** `SAME_DEVICE_IDENTITY` / `CONFIRMED` |
| method / authority / confidence | 934/934 `official_identifier` / `source_declared` / 0.99 |
| distinct `(from_ref,to_ref)` pairs | 934 (0 duplicates, 0 duplicate relation ids) |
| distinct shared identifiers | **934** (one GTIN → exactly one pair; no fan-out) |
| GTIN-14 validity | **934/934** pass the Mod-10 check digit |
| revoked | 0 (and 0 revoked relations of any type) |
| runs | all 934 from a single run `bridge_20261110T174101Z` |
| shared DI present on the evidence side | **934/934** |
| shared DI present on the device side | **934/934** |
| cross-market scope | US side = `openfda_device_udi` for 934/934; CA side carries `licence_no` **and** `mdall_device_id` for 934/934; CA devices have `markets_json = ["CA"]` for 934/934 |
| referential integrity | 0 dangling endpoints |
| `evidence_id` recompute | **7,254/7,254** equal `ev_` + `sha256(source_id|evidence_type|source_record_id)[:32]` |
| `content_hash` recompute | **7,254/7,254** equal `sha256(canonical json of payload.normalized)` |
| `canonical_key` recompute | **7,254/7,254** |
| relation census | matches `RESEARCH_VALIDATION.md:69-78` exactly (934/192/2/59/10/1,087/782/5,544) |
| quality findings | 54 rows, 0 error severity (matches `FOUNDATION_AUDIT.md:206-208`) |
| MDALL cache | 1,673,926 rows; 5,477 bare 14-digit; **5,512** normalised; **5,005** unique; 0.329 % |
| bridged GTINs ⊆ MDALL values | yes, 934/934 |

The MDALL recount is worth stating precisely because the normalisation rule is only described as
"when separators were removed": removing **only hyphens and spaces** reproduces 5,512 / 5,005
exactly. A digits-only reading gives 7,919 / 7,303 and an alphanumeric-only reading gives
5,517 / 5,009. The published number is therefore reproducible, but the rule should be written down.

**FAIL — one documentation number (`v3.us_record_count_claim`).**
`RESEARCH_VALIDATION.md:28` says "500 company-page records … + 8 additional records resolved during
the bridge = **508 unique U.S. records**". The database holds **1,440** `openfda_device_udi`
evidence rows: 500 from run `udi_20261110T174016Z` and **940** from run `bridge_20261110T174101Z`.
The same table's bridge row (`:32`) says 942 records resolved. "8 additional" is the *unpaired
remainder* (942 − 934), not a record count, so the sentence understates the U.S. corpus by 932
records and contradicts its own neighbouring line.

**UNVERIFIABLE.**
* The 1,200-row deterministic GTIN sample and the 942 resolutions cannot be replayed offline: the
  sampling rule lives in the ATLAS connector, and no artifact lists the 1,200 candidates. The
  database is *consistent* with 942 (500 + 940 new = 1,440, i.e. two resolutions already existed).
* The 400 sampled negative pairs are not enumerated in any artifact, so `identity_baseline_eval.json`'s
  confusion matrix can only be re-added, not re-derived. Its arithmetic is consistent
  (934 + 400 = 1,334 labelled; tp 934 + fn 0 = 934 positives; fp 0 + tn 400 = 400 negatives), but
  `tp = positives` makes recall 1.000 a tautology and `fp = 0` definitional for a DI-equality rule.
  The report says exactly this at `RESEARCH_VALIDATION.md:45-47`; the finding here is only that the
  labels are not auditable from artifacts.

---

## 6. V4 — cross-source identity on the frozen sample

**Claim.** HORIZON's EXP-H2 finds 0 official-identifier matches; ATLAS finds 934. The reconciliation
hypothesis under test: *"HORIZON's 0 is a sample-coverage result, not a conflict with ATLAS's 934."*

**Method.** Build the official-identifier inventory of both sides from the export rows themselves;
test same-scheme equality, then the only possible shared namespace (14-digit GTIN/UDI-DI); then
intersect HORIZON's sample with ATLAS's bridge set and UDI corpus.

**Results.**

| Check | Result |
|---|---|
| HORIZON US identifier schemes | `udi_di`, `uspto_510k`, `uspto_pma`, `fda_product_code`, `fda_fei`, `fda_registration_number`, `cfr_regulation` |
| HORIZON CA identifier schemes | `hc_device_licence`, `hc_mdall_device_id`, `hc_mdall_device_identifier` |
| shared scheme names | **none** — same-scheme equality is 0 by construction |
| 14-digit values on the US side | 320 (all 320 pass the GTIN-14 check digit) |
| 14-digit values on the CA side | **0** (CA value lengths: 4,5,6,7,10,13) |
| GTIN namespace overlap | **0** |
| ATLAS bridge GTINs found in HORIZON's Canadian sample | **0 of 934** |
| ATLAS bridge GTINs found in HORIZON's GUDID sample | **0 of 934** |
| HORIZON UDI-DIs found among ATLAS's distinct DIs | **5 of 320** (ATLAS has 5,549 distinct DI values) |
| cross-source identity relations in the export | 0 (all 2,228 relations are intra-source structure: `priority_claim`, `application_to_publication`) |

**Verdict on the reconciliation claim: CONFIRMED.** The Canadian side of HORIZON's sample contains
**no 14-digit identifier at all**, and the MDALL table is only 0.33 % GTIN-valued, so a 174-record
MDALL slice is expected to contain zero GTINs. HORIZON's S4 signal could not fire by sampling. The
two results are mechanically compatible; neither one constrains the other. The US samples barely
touch (5 shared UDI-DIs of 320), which shows the two experiments drew almost disjoint firm-scoped
slices.

**Vocabulary note (not a failure).** The export's `identity_status` is `CANDIDATE` 2,604,
`UNKNOWN` 2,391 and **`CONFIRMED` 889**; `evidence_status` is `CONFIRMED` 941. The README's claim
(`README.md:43`) is about a confirmed *cross-source* identity, and no cross-source relation exists,
so the claim holds. But an unqualified `identity_status = CONFIRMED` on 889 rows will be read as a
confirmed identity by most consumers. See D9.

---

## 7. V5 — time semantics

**Claims.** Both schemas promise four separate clocks; HORIZON's `first_observed_at` is "the first
time HORIZON saw the record"; ATLAS's `source_public_at` is when the source published the fact and
its time-leakage control is 1,452 usable / 5,802 unusable.

**Method.** Count each clock per source from the rows; measure equality and day-margins between all
pairs of clocks; attribute each populated clock to the source attribute it copies; run the same audit
over the ATLAS `evidence` table.

**HORIZON (5,884 importable records).**

| Clock | Present | Notes |
|---|---:|---|
| `fetched_at` | 5,884 (100 %) | all 2026-11-09 |
| `first_observed_at` | 4,490 (76 %) | 1,394 null |
| `event_at` | 4,219 (72 %) | |
| `source_public_at` | 3,564 (61 %) | |
| neither event nor public clock | 181 | `eu_cordis` 60, `openfda_device_classification` 60, `openfda_device_registrationlisting` 60, plus 1 |

**FAIL — `first_observed_at` is not an observation clock (`v5.horizon_first_observed_semantics`).**
Three regimes, all quantified:

| Regime | Records | Meaning |
|---|---:|---|
| `first_observed_at == fetched_at` | **4,334** | the field is a copy of the fetch timestamp; it carries no information about when the fact became observable |
| back-dated > 30 days before `fetched_at` | **156** | `crossref` 59 (1,068–2,464 days), `europepmc` 37 (983–2,463), `openalex` 60 (1,067–2,450) — all dated 2019–2023 against a 2026-11-09 acquisition |
| `first_observed_at == event_at` | 16 | copies the event clock |

For `crossref` the mechanism is exact: **59 of 59** records have
`first_observed_at == source_public_at` — the publisher's publication date. HORIZON cannot have
observed those records in 2021; the field has been back-filled from a source date. This matters
because the schema's own rationale (`hz/schema.py:10-12`) is that "when we saw it" must be separate
from "when it was published".

**FAIL — clock collapse (`v5.horizon_clock_collapse`).**
371 records have `event_at == source_public_at`, and in four sources the equality holds for 100 % of
records: `brazil_anvisa` 120/120, `europepmc` 37/37, `openaire` 59/59, `openalex` 60/60. For those
sources `observability_gap_days` is identically 0 and cannot be measured. (For scholarly sources a
publication is legitimately both the event and the public act; the problem is the *claim* of two
independent clocks, not the data.) A further 1,619 records have `event_at` **after**
`source_public_at` — the documented "prospective registration" pattern, which is coherent, not an
error.

**ATLAS (7,254 evidence rows).**

| Clock | Present |
|---|---:|
| `source_public_at` | 7,254 (100 %) |
| `first_observed_at` | 7,254 (100 %) |
| `fetched_at` | 7,254 (100 %) |
| `event_at` | 5,802 (80 %) |

* `first_observed_at == fetched_at` for **7,254/7,254** — on a first collection run these must
  coincide, and the report says `first_observed_at` "is a fetch clock"
  (`RESEARCH_VALIDATION.md:92`). The field therefore carries no observation history at all.
* **FAIL — the public clock is derived from the event clock for 80 % of the corpus
  (`v5.atlas_public_clock_derivation`).** All 5,802 rows with `time_quality = 'derived'` have
  `source_public_at == event_at` **exactly**; the 1,452 `'day'` rows have 0 such equalities. So the
  "publication" clock is the event clock for 5,802 rows, and the observability gap is 0 by
  construction there. The artifact *discloses* this (`time_quality='derived'`, and
  `RESEARCH_VALIDATION.md:92` treats those rows as "no usable date"), so it is not a silent fake —
  but the schema's promise of four separate clocks is met on only 1,452 of 7,254 rows.
* The published control numbers reproduce exactly: 1,452 `'day'` + 5,802 `'derived'` = 7,254.

**PASS — licence vocabulary (`v5.licence_vocabulary_coverage`).** The only HORIZON licence value with
no ATLAS equivalent is `terms_restricted`, which belongs to the quarantined source and never reaches
the importer; the adapter declares `terms_restricted → restricted`
(`medradar/integration/adapter.py:386`), applied to zero records.

---

## 8. V6 — licence isolation

**Claims.** No UN Comtrade payload bytes exist in the integration worktree; the 23 remaining
sources' licence statuses agree with the registry.

**Method.** Worktree filename walk; `git ls-files` / `git cat-file` / `git log` (read-only); a
content scan of 1,823 text files for three payload-distinctive tokens taken from the quarantined
upstream file (one `content_hash`, one `source_record_id`, two numeric trade values — the numeric
tokens are counted but not reproduced in this document or the JSON); registry comparison of all 24
sources.

**Results.**

| Check | Result |
|---|---|
| payload-named files in the worktree | **none** — the 3 `comtrade`-named files are the connector, the registry entry and the licence HTML |
| both upstream copies absent | export copy **and** `experiments/industry/evidence/` copy absent |
| git index | no payload path tracked; 5 tracked paths, all code/metadata/licence text |
| content scan | **0 hits in 1,823 text files** |
| `MANIFEST.json` ⊆ HEAD tree | payload not in the HEAD tree |
| registry agreement | 24/24 sources: registry `licence_status` == manifest `per_source` == `licence_summary` == `registry_snapshot` |
| restricted source with data present | **none** (the only `terms_restricted` source is the absent one) |
| unclear-licence sources with data present | **8**, enumerated below |

**Unclear-licence sources whose data is nevertheless present** (publicly readable, no stated reuse
licence — `open_no_explicit_licence`, 1,104 records, 4,497,107 bytes): `brazil_anvisa` 120,
`crossref` 59, `epo_publication_server` 228, `eu_cordis` 60, `eu_ted` 299, `pubmed_eutils` 37,
`semantic_scholar` 56, `usaspending` 245. Redistribution of these rests on the manifest disclosure,
not on a licence. That is a disclosure, not a defect.

**Exposure finding (reported, not a tree defect; D10).** The quarantined payload blob is still in
this repository's object store. `git log --all` shows commit `18a7580` touching
`research/horizon/exports/horizon-2026-11-10/un_comtrade.jsonl`; the blob is **1,832,311 bytes**
and `git branch -a --contains 18a7580` lists `research/horizon-001` and
`remotes/origin/research/horizon-001`. It is **not** an ancestor of the integration branch
(`git merge-base --is-ancestor` exit 1), so the branch under review is clean — but the bytes exist
locally and on a pushed ref. Remediation is the licence owner's decision (history rewrite vs
private ref vs accept), not a code fix; it is outside this verifier's mandate to change.

---

## 9. V7 — adapter fidelity

**Claims.** Import preserves record identity, all four clocks, identifiers, licence status and
quality flags; nothing is promoted from `UNKNOWN`/candidate to confirmed; importing twice is
idempotent; rejections are logged, not dropped.

**Method.** No adapter module is imported. The staging database was copied with the SQLite backup
API (`…/snapshots/convergence_staging_snapshot.sqlite`, SHA-256 `37f2bc35…f782d`) and every verdict
below is bound to that snapshot. Per-source evidence counts and the licence distribution were
recomputed from the export and compared with the adapter's own report
(`research/convergence/reports/integration_conv_smoke_001.json`); the `SAME_WORK` relation count was
recomputed from cross-source DOI pairs.

**FAIL (D3) — the frozen snapshot contains zero evidence rows
(`v7.run_state`).** Run `conv_run_002` reports `records_seen 5884, converted 0, degraded 0,
rejected 5884, evidence_inserted 0, status 'complete'`, with `policy_id = NULL`. All 5,884
rejections carry reason `licence_blocked:'<status>' under policy None` for every licence class —
including `open_licence` (3,892) and `public_domain` (888). Two defects in one:

1. a missing licence policy silently becomes **reject everything**, including the 888
   `public_domain` records that need no licence decision at all;
2. the run still reports `status = 'complete'`, so a pipeline driver sees success after importing
   nothing.

The live database changed twice under this verifier (a 58 MB state with 5,884 evidence rows was
replaced by the 26 MB rejected state mid-audit), so this is a statement about the frozen snapshot,
not about the developer's final intent. **V7 must be re-run after the adapter settles.**

**FAIL (D4) — the smoke report contradicts itself (`v7.smoke_report_internal_consistency`).** The
same report gives `import.seen 5884 / degraded 4918` and `run.records_seen 5822 / degraded 4856`
for what its field names imply is the same quantity. Both are internally correct for different
units (records vs distinct evidence ids — the difference is exactly the 62 collisions of D2) but the
report does not say so.

**PASS — the parts that can be verified and do hold.**

| Check | Result |
|---|---|
| manifest digest recorded by the adapter | equals the actual `MANIFEST.json` SHA-256 |
| records seen | 5,884 = 6,492 declared − 608 quarantined (quarantine respected) |
| per-source evidence ids | all 23 equal the independently computed distinct `(source_id, entity_type, source_record_id)` triples — including the collapsing 33 / 26 / 58 |
| licence distribution after collapsing | 3,891 `open_licence` + 1,104 `open_no_explicit_licence` + 827 `public_domain` = 5,822; recomputed exactly, no class change |
| identity upgrade | 0 confirmed relations in the graph layer; all records `not_attempted` |
| rejections logged | 5,884 rejection rows with reason and payload = `conv_runs.rejected` (nothing silently dropped) |
| `SAME_WORK` relations | 672 recomputed from cross-source DOI pairs (the graph's own claim reproduced) |

**FAIL (D2, downstream) — 62 distinct records are stored as versions of one evidence id
(`v7.record_identity_collisions`).** The adapter's report calls them "record identity duplicates";
they are not duplicates. `openfda_device_pma` collapses 60 rows into 33 evidence ids (e.g. four
distinct supplements of `P980016`), `openfda_device_registrationlisting` 60 rows into 26 (e.g. nine
distinct establishment-type rows for registration `1824199`), `openaire` 59 into 58. Because the
collision is resolved as *versions*, the current-entity view (`evidence_head`, 5,822 rows) hides 62
records and implicitly labels the older ones superseded. S136 is not superseded by S514.

**UNVERIFIABLE (5 checks).** With zero evidence rows in the snapshot, per-record equality of the four
clocks, of identifier sets, and of quality flags cannot be tested; idempotency needs two completed
runs; and ATLAS's 934 relations are absent from the integration store entirely (its
`entity_relations` holds only `SAME_WORK`). All five become testable the moment an import run
actually inserts records — the harness needs no change.

---

## 10. Defects found

Severity is about the *claim*, not about how hard the fix is.

| # | Defect | Exact numbers | Where the claim lives | Owner |
|---|---|---|---|---|
| **D1** | EXP-H2 prose contradicts the pair file in 8 of 9 and 8 of 10 numbers; signal S5 is redefined in the prose | prose 712/387/325 vs pair file **726/0/726**; S2 445 fired vs **0**; S3 365 vs **708**; hard negatives 12 vs **26** | `EXPERIMENT_RESULTS.md:105-135`, `reports/REGULATORY_FRONTIER_REPORT.md:188-208` | h2-auditor |
| **D2** | `source_record_id` is not unique in 3/23 sources (62 extra rows), so the documented ATLAS evidence id merges distinct records; 62 records end up as versions and are hidden from `evidence_head` | pma 60→33 ids, reglist 60→26, openaire 59→58; 62 extra rows | `research/horizon/exports/…/README.md:14`; `medradar/atlas/evidence/schema.py:105-113` | HORIZON owner + integration owner |
| **D3** | Frozen import rejects 100 % of the export and still reports `complete`; a missing licence policy blocks `public_domain` too | 5,884 seen, 5,884 rejected, **0 evidence**; reasons: `open_licence` 3,892, `open_no_explicit_licence` 1,104, `public_domain` 888 | `conv_run_002` in the frozen snapshot | integration owner |
| **D4** | The import report states two different record counts under the same field names | `import.seen 5884` vs `run.records_seen 5822`; `degraded 4918` vs `4856` | `research/convergence/reports/integration_conv_smoke_001.json` | integration owner |
| **D5** | Stated U.S. corpus size is wrong and contradicts the neighbouring row | **508** claimed vs **1,440** in the DB (500 + 940 bridge additions); same table says 942 resolved | `RESEARCH_VALIDATION.md:28` vs `:32` | ATLAS owner |
| **D6** | `first_observed_at` is not an observation clock | 4,334 = fetch time; **156 back-dated 983–2,464 days**; 59/59 `crossref` records equal the publication date; 16 = `event_at`; 1,394 null | `hz/schema.py:126`; export rows | HORIZON owner |
| **D7** | Clock collapse: `event_at == source_public_at` for all records of 4 sources | 371 records overall; brazil_anvisa 120/120, europepmc 37/37, openaire 59/59, openalex 60/60 | `hz/timeq.py` two-clock model | HORIZON owner |
| **D8** | ATLAS's public clock is the event clock for 80 % of rows (disclosed as `time_quality='derived'`) | 5,802/7,254 `source_public_at == event_at`; only 1,452 rows have an independent public date | `medradar/atlas/evidence/schema.py:10-12`; `RESEARCH_VALIDATION.md:92` | ATLAS owner |
| **D9** | `identity_status = CONFIRMED` on 889 export rows (941 `evidence_status`), and the importer flattens all 5,822 to `not_attempted` | 889 / 941 / 5,822 | `README.md:43`; adapter output | HORIZON owner + integration owner |
| **D10** | Quarantined UN Comtrade payload blob still in the repository object store on a pushed ref | blob 1,832,311 bytes at `18a7580`; refs `research/horizon-001`, `origin/research/horizon-001`; **not** in HEAD history | quarantine policy | licence owner |

Not defects, recorded so they are not later mistaken for findings:

* EP-H2's 0 REJECTED is *correct* under the pre-registered rule — name evidence can neither confirm
  nor refute, and no official field contradicts any pair (`EXP_H2_SUMMARY.json` says this).
* The 934 bridge is a consistency check, not a discovery: the method *is* the label
  (`RESEARCH_VALIDATION.md:45-47`). Its precision of 1.000 and recall of 1.000 are tautological, and
  the report says so.
* The `terms_restricted → restricted` licence mapping is declared and applied to zero records.

---

## 11. What this verification cannot see

1. **The developer's adapter logic.** V7 verifies output data, never behaviour on inputs that did
   not occur. A code path that mishandles a record type absent from this sample is invisible.
2. **Anything behind the quarantine.** The 608 UN Comtrade records are absent by design, so the
   manifest's counts for that source are verified only against the upstream worktree copy, not
   against local bytes.
3. **The 1,200-row ATLAS GTIN sample and the 400 negative pairs.** Neither is an artifact, so the
   bridge's denominator and the baseline's true negatives cannot be re-derived, only re-added.
4. **Per-record import fidelity.** The frozen snapshot has zero evidence rows, so clock, identifier
   and quality-flag preservation, and idempotency, are untested. The harness already contains the
   checks; they need a successful run.
5. **Registry coverage claims.** "GUDID October 2026 release", "1,673,926 active MDALL rows" and the
   firm-scoped sampling rules are taken from the artifacts; the upstream sources are not re-fetched
   (no network, by instruction).
6. **The relationship between the two experiments' samples beyond the GTIN universe.** 5 of 320
   HORIZON UDI-DIs appear in ATLAS's DI set, which bounds the overlap but does not explain the
   differing firm-scoped selection rules.
7. **Which prose or artifact is the intended record.** D1 and D5 are documentation/artifact
   divergences; deciding which side was "the real" run is an audit decision, not a recomputation.
8. **Git history beyond reachable refs.** `git log --all` was used; dangling/unreachable objects were
   not enumerated (`git fsck` was deliberately not run — it is a repository-wide operation on a
   worktree owned by the Lead).

---

## 12. Reproduction

```bash
# full run (recounts the 220 MB MDALL cache; ~6 s on this host)
python tools/convergence/verify/verify.py \
  --json research/convergence/verification/verification_summary.json

# fast subset, no MDALL recount
python tools/convergence/verify/verify.py --skip-heavy --groups V1,V2,V6

# freeze a fresh snapshot of the integration staging database before a V7 run
python tools/convergence/verify/_snapshot_staging.py
```

Exit status is 1 when any check FAILs. Defaults discover the sibling worktrees
(`../horizon-001`, `../atlas-001`); every path is overridable (`--root`, `--export-dir`,
`--horizon-root`, `--atlas-root`, `--atlas-db`, `--mdall-cache`, `--staging-snapshot`).

**Check inventory (90).** Every check carries `claim`, `claim_source`, `expected`, `actual`, `detail`
and `evidence` in the JSON artifact, so each row of this document can be traced to a machine record
by `check_id`.

| Prefix | Checks | What it recomputes |
|---|---|---|
| `v1.` | 18 | bytes, digests, rows, totals, sidecars, per-record hashes, schema, per-source counters, dedupe keys, licence agreement, README table, record identity |
| `v2.` | 10 | pair count, verdicts, rules, signal fires, combinations, rule conformance, provenance, both prose documents |
| `v3.` | 20 | relation count/status/uniqueness/GTIN validity/revocation/runs, both-sides identifier presence, referential integrity, evidence-id/hash/canonical-key recompute, census, pilot agreement, MDALL cache, bridge subset |
| `v4.` | 8 | scheme inventory, same-scheme and GTIN-namespace matches, ATLAS↔HORIZON sample overlap, identity-status distribution, reconciliation verdict |
| `v5.` | 10 | four clocks per source in both schemas, manifest agreement, first-observed regimes, clock collapse, derivation audit, leakage control, vocabulary coverage |
| `v6.` | 8 | payload filenames, both copies, git index, git history, content scan, registry agreement, restricted/unclear inventory |
| `v7.` | 16 | adapter presence, manifest digest, run state, rejection logging, report consistency/counts/licences, record-identity collisions, SAME_WORK recompute, five unverifiable gaps |
