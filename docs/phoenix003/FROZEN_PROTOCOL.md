# PHOENIX-003 — FROZEN PROTOCOL

**Regulatory-anchored discovery of pre-milestone public evidence**

| | |
|---|---|
| Experiment | PHOENIX-003 |
| Branch | `research/phoenix-003-early-evidence` |
| Base commit | `b2a14c0` (`main`) |
| Protocol frozen at | see `experiments/phoenix003/FROZEN_RULES.json` → `frozen_at`, digest in `FROZEN_RULES.sha256` |
| Status | pre-registered; anchor set not yet constructed when this file was written |

This document fixes, in advance, the scientific question, the sampling frame, the
measurement, the controls and the stop/verdict rules. It is committed **before** the
regulatory anchor set is built and before any external-source match is inspected.
`experiments/phoenix003/FROZEN_RULES.json` is the machine-readable copy of every numeric
parameter used by the code; the code reads that file and never hard-codes a threshold.
If an amendment is unavoidable, it is appended in §12 with a timestamp, the reason, and
what had and had not been observed at the time — never silently edited in place.

---

## 1. Question

> Before a medical-device firm reaches an important regulatory milestone, does an
> *independent* public source already describe the related technical activity — and if so,
> how early, how reliably, and could an observer have identified it *without knowing the
> future*?

Three sub-questions, each separately falsifiable:

* **Q1 (existence).** How many milestones have at least one *machine-verifiable* earlier
  public record from a source outside the regulatory corpus?
* **Q2 (specificity).** Is that earlier-record rate distinguishable from what the same
  procedure finds for deliberately mismatched (decoy) or time-shifted pairings?
* **Q3 (identifiability).** Using only information available before the milestone, would a
  hindsight-free retrieval rule have surfaced the eventual evidence, and at what observer
  burden?

**What this study does not claim.** Q1 with a hindsight-defined query is *not* a forward
prediction. The device name that anchors a match is taken from the future milestone record.
A positive Q1 says only: "public evidence of related technical work existed earlier and can
be verified after the fact." Only Q3 speaks to identifiability, and only as a bounded
statement about a fixed retrieval rule.

---

## 2. Failure modes this design must survive

Each row is a defect that invalidated previous rounds (PHOENIX-001/002, S-028, S-029). The
corresponding control is named; if the control fails, the study returns the failure, not a
rescue.

| # | Defect | Control in this protocol |
|---|---|---|
| 1 | label maturity / time leakage | §5: evidence must be published strictly **before** the milestone; no models are trained at all |
| 2 | structurally impossible negatives | §4: the sampling frame is *first-in-code* milestones only, every one of which can in principle have earlier evidence |
| 3 | duplicate regulatory records inflating counts | §4.2: canonical key by K-number / original PMA number; supplements counted separately, never as milestones |
| 4 | modern taxonomy back-filled onto history | §4.1: product code is the **record's own** FDA product code, never a 2026 track mapping |
| 5 | missing / back-projected firm attribution | §3: lineage-resolved attribution with explicit `valid_from`; `UNKNOWN` retained, never imputed |
| 6 | features mathematically coupled to the target | §7: there is no model and no feature vector; the only metric is an event-level lead time |
| 7 | simple baselines win | §8.C1: the naive keyword baseline is run and reported as a peer, not a footnote |
| 8 | single snapshot is not point-in-time | §9.4: dual-clock dates, explicit availability-proxy per source, no prospective claim |

---

## 3. Entities: five core firms, lineage-resolved

Core firms (fixed): **Medtronic, GE HealthCare, Philips, Dräger, Mindray**.

A regulatory record is attributed to a firm only if the applicant legal entity belonged to
that firm's **corporate lineage at the record's decision date**. The rule set
(`firm_lineage.json`, frozen) distinguishes:

* **division / subsidiary** (e.g. `Medtronic Sofamor Danek`, `Philips Ultrasound`) → in the
  lineage for the whole period it was a subsidiary; the lineage record states `valid_from`.
* **pre-spin-off parent division** (GE Medical Systems is GE's healthcare division before the
  2023-01-04 GE HealthCare spin-off) → in the GE HealthCare lineage up to the spin-off date,
  with the mapping recorded as `division_until`; records after the spin-off are the new entity.
* **acquired company** → in the lineage **only from the acquisition close date**. A
  `Spectranetics` clearance in 2014 is *not* a Philips milestone; a `Covidien` clearance in
  2014 is *not* a Medtronic milestone.
* **not resolvable** → `UNKNOWN`. Never imputed, never dropped silently; the count is reported.

Attribute counts are reported both **lineage-inclusive** and **strict-legal-name-only** so a
reader can see how much of the sample depends on the lineage rules.

---

## 4. Sampling frame and the two targets

### 4.1 Anchor universe (built from `data/medradar.sqlite`, read-only)

Input tables: `events` rows with `kind = '510k'` (payload `k_number`, `decision_date`,
`date_received`, `device_name`, `product_code`, `applicant`) and `kind = 'pma'` (payload
`pma_number`, `supplement_number`, `decision_date`, `trade_name`, `generic_name`,
`product_code`, `applicant`, `ao_statement`).

The **product code is the record's own FDA product code**. No taxonomy table, no track
mapping, no 2026 vocabulary is used anywhere in sampling. The `product_codes` table is used
for exactly one purpose: to look up the *generic device name* of a product code for the
hindsight-free query in Q3, where the lookup is on the official code that already existed at
the milestone date.

### 4.2 Canonical milestone unit

* **510(k)**: key = `K` + the record's `k_number`. One record = one milestone.
* **PMA original approval**: key = `P` + `pma_number`, only when `supplement_number` is empty.
* **PMA supplements** are **not** milestones. They are counted in the inflation audit
  (§6.3) so the reader can see what fraction of raw regulatory rows are supplements.
* Duplicate detection: exact key collisions, and (applicant, device/trade name, decision
  date, product code) collisions across different keys, are both reported.
* A row whose key, decision date, product code or applicant is missing is **excluded and
  counted**, never repaired.

### 4.3 Target A — firm's first observed milestone in a product code

For firm `F` and product code `C`: the anchor is the milestone with the **minimum decision
date** among all canonical milestones of `F` in `C`. It enters the sample iff

1. `date(F,C) ∈ [2015-01-01, 2024-12-31]`;
2. the record's `decision_code` is a *substantive* decision (`SESE` for 510(k), `APPR` for
   PMA) — `NSE`, `DENO`, `WD`, `DENG` etc. are excluded, because a rejection is not a
   technology milestone;
3. attribution to `F` is resolved (§3), not `UNKNOWN`;
4. the device/trade name yields at least one **distinctive token** (§4.5).

Target A is a *regulatory* construct: the first observation of a firm's activity in a
product code. It is **not** asserted to be an invention.

### 4.4 Target B — novel-product milestone

Target B ⊆ Target A, defined mechanically as an anchor whose distinctive token `T`

1. appears in **no earlier canonical regulatory record of that firm** (any product code,
   any applicant variant of the lineage), and
2. appears in **no earlier canonical regulatory record of any applicant at all**

plus, separately reported, the requirement that at least one independent evidence link of
tier `VERIFIED_L1` or `VERIFIED_L2` exists. (1)+(2) define *novelty*; the link condition
defines *independently evidenced*, and is reported as a count, never used to build the
sampling frame.

### 4.5 Distinctive token (frozen tokenizer)

1. Source string: 510(k) `device_name`; PMA `trade_name` (fall back to `generic_name` only if
   `trade_name` is empty — recorded via `name_source`).
2. Uppercase; map every non-`[A-Z0-9]` character to a space; split.
3. A token is *distinctive* iff: length ≥ 4; alphabetic; not in `GENERIC_TOKENS` (frozen
   list, `name_stoplist.txt`, part A: common device/English words such as `SYSTEM`, `DEVICE`,
   `MEDICAL`, `PLUS`, `SERIES`, `MONITOR`, …); not in the frozen **generic vocabulary**
   (part B: tokens occurring in ≥ 20 of the 7,097 `product_codes` `device_name`/`definition`
   strings — computed once from the static catalogue, which is not outcome-dependent); and
   not a pure measure/model pattern (`^\d+$`, `^\d+[A-Z]$`, roman numerals, units).
4. The anchor's **token set** is all distinctive tokens of the name. Tokens are used
   case-insensitively.

The stoplist and the generic vocabulary are generated by `code/freeze_vocab.py` from the
catalogue only, and their digest is recorded in `FROZEN_RULES.json`.

---

## 5. Evidence sources and the evidence window

Two independent sources, harvested **firm-anchored**, i.e. with queries that never mention a
device name or a regulatory identifier (`fetch/FETCH_SPEC.md`, frozen before anchors exist):

* **CT.gov** — ClinicalTrials.gov API v2, sponsor queries per firm; public date =
  `first_posted` (`studyFirstPostDateStruct`).
* **EPMC** — Europe PMC REST, `AFF:` affiliation queries per firm, window 2012–2025; public
  date = `firstPublicationDate`, with a frozen fallback chain recorded in `date_basis`.

Evidence window for an anchor `a`: `[a − 5 years, a − 1 day]`. Nothing published on or after
the milestone counts as earlier evidence. A record with no usable public date is
**not** counted as earlier evidence; it is counted as `date_unresolved`.

---

## 6. Measurement

### 6.1 Link tiers (machine-checkable, no LLM judgement in the primary analysis)

| tier | meaning | necessary and sufficient condition |
|---|---|---|
| `VERIFIED_L1` | identifier-verified chain | the evidence record cites an `NCT` identifier that is present in the CT.gov corpus **and** whose sponsor is the firm's lineage **and** the evidence-side name identity of `VERIFIED_L2` also holds |
| `VERIFIED_L2` | verifiable semantic link | same firm lineage on the evidence record (`lead_sponsor` / `firm_affiliations`) **and** exact case-insensitive identity of at least one distinctive token of the milestone name with a whole token of the evidence record's intervention name or title **and** evidence public date < milestone date |
| `CANDIDATE_L3` | AI-proposed candidate | shares a token, but the token is only from the generic vocabulary, or the firm/date condition is only partially met |
| `AMBIGUOUS_L4` | cannot be decided | a distinctive token matches but the record's firm or public date is unresolved |
| `REJECTED_L5` | not supported | token matches but a hard condition fails (later date, different firm, token is a common word, token binds to a different device in the same record); reason recorded |

Only `L1`/`L2` count toward Q1. No human-in-the-loop label is claimed; that limitation is
stated wherever L2 counts are used. `L2` is a *verified semantic link* in the sense of
"the defining condition is machine-checkable and re-derivable from committed data", not
"a human has confirmed the same technology".

### 6.2 Lead time

`lead_days = milestone_date − evidence_public_date`, for `L1`/`L2` links, taken as the
**maximum** over earlier evidence of the same anchor (earliest evidence). Reported:
counts at ≥90 / ≥180 / ≥365 days, median, quartiles, full distribution, per-firm and
per-source coverage, and the rate of `date_unresolved`, `no_evidence`, `match_failure`.

Confidence intervals: exact (Clopper–Pearson) for proportions, bootstrap (10,000 resamples,
seed fixed in `FROZEN_RULES.json`) for medians. Sparse cells are shown with their `n` and no
model-based interval.

### 6.3 Duplicate and inflation accounting

Reported before any statistic: raw rows → canonical milestones → supplementary rows removed
→ attribution losses → decision-code losses → anchors. Each step's count is recomputable by
re-running one command.

---

## 7. Identifiability (Q3) — the hindsight-free test

For each `L1`/`L2` link, ask whether the eventual evidence would have been retrieved by a
**frozen hindsight-free rule** that uses only pre-milestone information:

* query terms = firm lineage name + the **generic device name of the product code**, taken
  from the official `product_codes` catalogue (a code that existed at the milestone date),
  never the milestone's trade name;
* the rule is a fixed token-conjunction over the frozen corpus restricted to records
  published before the milestone;
* two measurements: (a) `hf_recall` — does the eventually-linked evidence appear in the
  hindsight-free result set? (b) `hf_burden` — the size of that result set, i.e. how many
  records an observer would have had to read.

`hf_recall` is a property of the *corpus*; `hf_burden` is the practical cost. A link with
`hf_recall = 0` is reported as **hindsight-only**: evidence exists but was not identifiable
in advance by this rule. Only anchors with `hf_recall = 1` may be described as
"identifiable from earlier public information".

---

## 8. Controls (all pre-registered, all reported whatever they show)

* **C1 keyword baseline.** A link is "found" if the firm has *any* CT.gov/EPMC record in the
  evidence window whose text contains the firm name or a domain keyword. This is the naive
  method the literature usually calls "keyword matching". Expected to link almost every
  anchor; reported as the floor that any real method must beat.
* **C2 anchored method.** §6.1. The object of study.
* **C3 matched decoy pairing.** For each anchor, a decoy is built by replacing its
  distinctive token with a token from another Target-A anchor of the same firm within ±2
  years and a different product code (seeded RNG). The identical linker runs on the decoys.
  **Specificity** = `link_rate(C2 on real) / link_rate(C2 on decoys)`.
* **C4 time placebo.** (a) anchor dates shifted by a seeded offset in ±[90, 1095] days,
  evidence held fixed; (b) evidence records permuted across anchors within firm. Report the
  share of placebo pairings that still yield "earlier evidence", and a permutation p-value
  for the median lead time.
* **C5 concentration.** Per-firm, per-year, per-product-code counts; share of links
  contributed by the top firm and the top product code; a leave-one-firm-out repeat of the
  headline numbers.

---

## 9. Validity conditions stated in advance

1. **No model is trained.** No Precision/Recall/F1 is reported, because there is no
   supervised label set. Only counts, rates, lead times and their intervals.
2. **`L2` ≠ human gold standard.** Every L2 count is accompanied by the audit trail needed to
   re-check the token identity by hand.
3. **Single-snapshot dates.** The EPMC `firstPublicationDate` is a metadata date, not proof of
   when a reader could have seen the paper. §9.4 applies.
4. **Dual-clock sensitivity.** Every headline lead-time number is recomputed with the
   *latest* plausible public date (`firstIndexDate` for EPMC, `lastUpdatePosted` excluded from
   earlier-evidence eligibility) and both are reported. If the lead time survives only on the
   optimistic clock, that is stated as a limitation of the finding.
5. **Retrospective, not prospective.** No claim of having predicted anything in real time.
   The `available_at` column of the store equals the event date and is not usable as an
   observation timestamp; this study therefore never uses it.
6. **Product-code stability.** FDA product codes are stable identifiers published at decision
   time and are not re-derived; the study makes no claim about codes that changed meaning.

## 10. Pilot, scaling and verdict rules

**Pilot** = a deterministic subset of at most 50 Target-A anchors, selected by sorting
`sha256(anchor_id)` — a rule that cannot be influenced by the data. The pilot is run first to
test the instrument (coverage, date resolution, linker behaviour).

**Scaling** happens only if the pilot satisfies: (i) ≥ 80% of anchors have ≥ 1 firm evidence
record in the evidence window; (ii) ≥ 90% of those records have a resolved public date;
(iii) the decoy specificity is measurable (decoy link rate > 0 is not required, but the
denominator must be non-degenerate). Otherwise the study stops at the pilot and reports
`BLOCKED` with the diagnostic.

**Final sample** = all Target-A anchors (no cherry-picking). The pilot subset is reported
separately as a stability check. If fewer than five firms have ≥ 5 anchors each, the
pre-registered extension is: add the eight other `is_major` device firms in the store
(`abbott`, `baxter`, `bd`, `boston_scientific`, `edwards_lifesciences`, `stryker`,
`siemens_healthineers`, `zimmer_biomet`), reported as a **separate** stratum and never pooled
with the core five.

**Verdict (mechanical, from `results/verdict.json`):**

Let `n_anchors` = size of the final Target-A sample, `k` = anchors with ≥ 1 `L1`/`L2` link,
`p90` = share of those `k` with `lead_days ≥ 90`, `spec` = decoy specificity, `p_placebo` =
two-sided permutation p for the median lead time under C4(b).

* **BLOCKED** if the pilot scaling conditions fail, or if > 30% of evidence dates are
  unresolved, or if fewer than 5 anchors survive quality filters.
* **GO** if `k ≥ 20` **and** `p90 ≥ 0.60` **and** `spec ≥ 5.0` **and** `p_placebo < 0.05`
  **and** the `k` links span ≥ 4 of the 5 firms and ≥ 3 distinct anchor years.
* **LIMITED GO** if `k ≥ 5` **and** `p90 ≥ 0.60` **and** `spec ≥ 3.0` **and** `p_placebo < 0.10`
  (but GO not met). Findings are explicitly non-generalisable.
* **NO-GO** otherwise, including the case where C1 (keyword) links at least as often as C2 on
  the decoys, or where the median lead time is not distinguishable from the time placebo.

No threshold may be changed after results are seen. A NO-GO is a deliverable, not a failure
of the study.

## 11. Reproducibility contract

* `python experiments/phoenix003/code/run_pipeline.py --db <path>` reproduces every number
  in `EXPERIMENT_RESULTS.md` from the committed compact corpora, offline.
* `python experiments/phoenix003/code/selftest_offline.py` runs deterministic unit tests on
  synthetic fixtures (no network, no database).
* All randomness from `numpy.random.default_rng` / `random.Random` seeded from
  `FROZEN_RULES.json`; no other entropy source.
* Every artefact carries a sha256 in `results/manifest.json`; `docs/phoenix003/…` quotes only
  numbers present in those artefacts.

## 12. Amendments

**Amendment 1 — 2026-11-09T04:5x +08:00 — brand tokens are not distinctive; specificity banding added.**

*Observed before the amendment:* the anchor builder (A1) was run for the first time and its
token lists were inspected. Company brand tokens (`MEDTRONIC`, `PHILIPS`, …) appear inside
FDA trade names, so they were being carried as "distinctive tokens". A brand token cannot
discriminate a product, and it would match every paper the firm ever published.

*Observed after the amendment, before linking:* nothing. No external-source record had been
matched to an anchor, no link tier had been computed, and the external corpora were still
being downloaded. The amendment therefore cannot be outcome-driven.

*Change:* (a) tokens that are brand tokens of any core firm are excluded from the distinctive
set; (b) each remaining token is banded by its document frequency across all 177,948
regulatory device names (a vocabulary property, computed from names only): `high` ≤ 10,
`medium` ≤ 100, `low` > 100; links are reported by band, and the headline count is reported
both pooled and restricted to the `high` band, decided in advance of any link being seen.

*Effect:* both changes **tighten** the rule (they can only remove token matches), and both
were fixed before the link step existed.

**Amendment 2 — 2026-11-09T04:5x +08:00 — token specificity is measured by applicant document
frequency, not by name document frequency.**

*Observed before the amendment:* the first linker run (ClinicalTrials.gov corpus only, no Europe
PMC yet) produced links such as "Micra" ← a CoreValve transcatheter-valve trial, joined by the
token `TRANSCATHETER`. The token was banded `low` by name frequency (>100 device names) — and
so was `MICRA`, because Medtronic's own supplements repeat the product name more than 100 times.
Name frequency therefore measures *how often a product line is re-filed*, not whether a token
discriminates one firm's product from another's clinical vocabulary. The wrong quantity.

*Change:* the specificity band is recomputed on **distinct-applicant document frequency** — how
many different applicants use the token in a device name. A token used by one applicant cannot
distinguish two firms' vocabularies; a token used by very many applicants distinguishes nothing.
A second, stricter flag `product_specific` is pre-registered at `applicant_df ≤ 3`
(`FROZEN_RULES.json → name_vocab.product_specific_max_applicant_df`) and both the pooled and the
product-specific counts are reported.

*What was and was not observed:* only the pooled link list and its tokens had been looked at.
No lead-time statistic, no control, no verdict had been computed. The amendment can only remove
matches (`TRANSCATHETER` survives the token rule either way; it merely stops counting as
evidence of the same product). It is a **tightening**.

**Amendment 3 — 2026-11-09T05:1x +08:00 — split earlier evidence by whether the product was
already regulated.**

*Observed before the amendment:* of 213 `VERIFIED_L2` links produced by the ClinicalTrials.gov
corpus alone, the great majority were trials of a device that **already had an FDA record** at
the time of the trial — the Melody post-approval study, the Resolute Integrate registry, a
PillCam performance study. Calling those "early evidence of a technology" would repeat exactly
the error this study is meant to avoid: a trial can precede a *later* milestone while the
product itself is already public.

*Change:* every verified link is classified by a computed, non-judgemental question: at the
evidence record's publication date, did **any** canonical regulatory record of **any** applicant
already carry this distinctive token?

* `PRE_EXISTING_PRODUCT` — yes. The evidence is follow-up/surveillance/extension of an already
  regulated device. **Not** early evidence.
* `PRE_REGULATORY` — no. The information existed before the product had any regulatory
  footprint. The only class that may be called early evidence.

The pooled class remains fully reported. The verdict keeps its frozen definition (`k` = anchors
with any L1/L2 link, §10) and is *not* recomputed on the stricter class; the stricter class is
reported as an additional, more demanding descriptive level ("validity ladder") with its own
counts and intervals.

*Why this is not a threshold change:* no gate, window, seed or threshold in §10 is altered. The
new classification adds a **descriptive** split that can only reduce what may be claimed.

**Amendment 4 — 2026-11-09T05:1x +08:00 — extension stratum triggered.**

The pre-registered rule in §10 fired: only two of the five core firms reach 5 anchors
(Medtronic 40, Philips 11; GE HealthCare 4, Mindray 3, Dräger 1). The eight listed extension
firms were added as a **separate stratum**, harvested with the identical query template, and are
never pooled with the core five in a headline number.

**Amendment 5 — 2026-11-09T05:4x +08:00 — a product token must also be rare in the literature.**

*Observed before the amendment:* the strict class (product-specific ∧ pre-regulatory) contained
links carried by ordinary English words that happen to be used by only one applicant —
`OVERALL` (from a 510(k) device name that is a multi-product laundry list), `EFFICIENT`, `ORGANS`,
`CAPTURING`. A token used by one applicant is not necessarily a product name.

*Change:* a frozen **literature-rarity** test: a token is literature-rare iff it appears in at most
`literature_rare_max_epmc_df = 200` of the 36,621 firm-anchored Europe PMC documents (title +
abstract + keywords, patent records excluded). The threshold is 0.55 % of the corpus. This is a
vocabulary property computed from the frozen corpus only, before any link is formed — the same kind
of object as a stopword list. The strictest reported level becomes
`product-specific ∧ literature-rare ∧ pre-regulatory`; all looser levels remain reported.

*Effect:* removing 4 of 32 strict cases (`OVERALL`, `EFFICIENT`, `ORGANS`, and a `BULK`-token
variant of the same long device name). It can only remove matches; the pooled and product-specific
counts are unchanged. Known residual weakness, stated in the results: rare ordinary words
(`TETHERING` 13 documents, `CAPTURING` 83, `POLYSACCHARIDE` 81) survive the filter and are handled
by human adjudication rather than by another automatic rule.

**Amendment 6 — 2026-11-09T05:5x +08:00 — a record that declares a prior approval is not
pre-regulatory.**

*Observed before the amendment:* independent verification found that several rows in the
`PRE_REGULATORY` class are *post-approval / post-market / continued-access* studies — the record's
own title says the device was already approved. The store contains no HDE or IDE event kind, so the
token-history rule cannot see the earlier approval (the `MELODY` valve's 2006 HDE is the clearest
example). A record that describes itself as post-approval cannot be evidence that the product was
unknown.

*Change:* a frozen marker list (`FROZEN_RULES.json → novelty.post_approval_markers`: post-approval,
post-marketing, post-market, continued access, product surveillance registry, …) is applied to the
evidence record's own title and abstract. A hit reclassifies the link as `PRE_EXISTING_PRODUCT`
with reason `self_declared_post_approval:<marker>`. 211 rows were reclassified; with Amendment 5 running in parallel the strict class is 28 and the `MELODY` case dropped from 1,618
to 393 days on the surviving non-registry record.

*Effect:* a **tightening** that can only move links out of the pre-regulatory class. It does not
touch any gate, window, seed or threshold in §10.

## 13. Conformance corrections found by independent verification

Recorded for the same reason as the amendments: they changed the numbers, and the reader must be
able to see that they were corrections to conformance with §5/§6.1, not threshold changes.

| correction | what was wrong | effect |
|---|---|---|
| L1 window | `VERIFIED_L1` was assigned before the §5 five-year window test; 28 L1 rows lay outside the window and the maximum lead was 3,512 days | window test moved before tier assignment; max lead is now 1,826 days; L1 matches 108 → 76 |
| EPMC match field | matching used title + abstract + **keywords + MeSH** where §6.1 says "intervention name or title" | matching uses title + abstract; keywords/MeSH feed only the C1 baseline |
| emission cap | the deliverable omitted 1,606 of 6,532 verified rows | verified rows are never capped; only refused/ambiguous rows are |
| specificity denominator | real rate used 269 anchors, decoy rate 256 | both use the anchors that received a decoy; `specificity_matched_denominator` reported |
| C4b draws | 500 permutations where `FROZEN_RULES` fixes 2,000 | 2,000 |
| `specificity_note` | claimed "decoy rate is zero" while reporting 0.535 | corrected |
| `ZIMMER` | `Zimmer Medizinsysteme GmbH` (an independent company) was attributed to Zimmer Biomet | `exclude_if_contains`; three anchors removed (269 → 266) |




