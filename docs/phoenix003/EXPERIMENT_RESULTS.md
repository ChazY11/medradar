# PHOENIX-003 — Experiment results

Every number below is from `experiments/phoenix003/results/*.json`, produced by
`code/run_pipeline.py` in one run (196 s, 7 stages) on 2026-11-09, and re-derivable offline.
`INDEPENDENT_VERIFICATION.md` re-derives the mechanical layer with a separate implementation and
lists the defects that its first pass found — all of them are fixed in the numbers below, and the
fix list is in §10.

## Verdict

**`NO-GO`** (mechanical, `results/verdict.json`, frozen gates of protocol §10).

> The anchored method finds earlier public evidence for **69.9 %** of milestones, but the *same*
> procedure finds it for **51.4 %** of deliberately mismatched decoys and for **69.0 %** of
> time-shifted placebos; the keyword baseline finds it for **99.2 %**. Specificity is **1.37**
> (gate 5.0) and the placebo p-value is **0.88** (gate < 0.10). The measured "lead time" is not
> distinguishable from the firm's background publication activity, so the 186 anchors with a
> verified link cannot be called a signal.
>
> What survives is (a) a reusable anchor-and-control instrument that demonstrably destroys naive
> early-signal claims, and (b) a bounded **case series of 28 milestones** where a named product
> appears in a public record before it had any regulatory footprint — 24 of them on unambiguous
> proprietary names.

---

## 1. What ran

| stage | seconds | artefact |
|---|---:|---|
| `freeze_vocab` | 15.0 | `dataset/frozen_vocab.json` |
| `freeze_epmc_df` | 11.1 | `dataset/epmc_rare_tokens.txt`, `dataset/epmc_df_meta.json` |
| `a1_anchors` | 10.9 | `REGULATORY_ANCHORS.jsonl`, `results/a1_canonical.json` |
| `b_links` | 46.1 | `EVIDENCE_LINKS.jsonl`, `results/b_links.json` |
| `b2_novelty` | 8.1 | `results/b2_novelty.json` |
| `c_controls` | 59.7 | `results/c_controls.json` |
| `d_leadtime` | 44.9 | `results/d_leadtime.json`, `results/verdict.json` |

Windows 11, CPython 3.12.10, standard library only, no GPU, no LLM, **no network** (corpora are
committed). Hashes: `results/manifest.json`; run transcript: `results/pipeline.log`.

## 2. Evidence corpus

| source | records | note |
|---|---:|---|
| ClinicalTrials.gov, core 5 firms | 1,802 | 1,073 with a DEVICE intervention |
| ClinicalTrials.gov, extension 8 firms | 3,054 | 1,719 with a DEVICE intervention |
| Europe PMC, core 5 firms | 13,980 | MED 13,661 / PMC 282 / PPR 32 / PAT 5 |
| Europe PMC, extension 8 firms | 22,664 | |
| evidence pool after filters | **41,477** | 23 EPMC patent records excluded; 1,452 records whose firm did not resolve from the record itself excluded from candidacy |

Firm-verified share of the pool: 4,820 / 4,856 (99.3 %) CT.gov, 35,205 / 36,621 (96.2 %) EPMC.
All 266 anchors have at least one firm evidence record inside the 5-year window
(`anchor_coverage_rate = 1.00`), so the §10 scaling condition is met and the verdict is a decision,
not `BLOCKED`.

## 3. Anchors (Target A)

266 anchors — **59 core** (Medtronic 40, Philips 11, GE HealthCare 4, Mindray 3, Dräger 1) and
**207 extension** (Abbott 45, Boston Scientific 41, Stryker 40, Siemens Healthineers 34, Edwards 14,
BD 13, Zimmer Biomet 12, Baxter 8). 2015–2024, 246 distinct product codes, 217 × 510(k) +
49 × original PMA. Target B (globally novel product name): 18 anchors, 7 with a verified link.

## 4. Links by tier

| tier | matches |
|---|---:|
| `VERIFIED_L1` — evidence cites an NCT id belonging to the firm's own trial set **and** carries the token | 76 |
| `VERIFIED_L2` — same firm + exact distinctive-token identity + published before the milestone, inside the window | 5,684 |
| `CANDIDATE_L3` — generic-vocabulary token only | 2 |
| `AMBIGUOUS_L4` — token matched, firm or date unresolved | 552 |
| `REJECTED_L5` — token matched, refused (dated after the milestone, or before the 5-year window) | 12,625 |

Anchors with ≥ 1 verified link: **186 / 266 (69.9 %)**. With ≥ 1 *product-specific* verified link
(token used by ≤ 3 applicants): **60 (22.6 %)**. `EVIDENCE_LINKS.jsonl` contains **every verified
row**; only refused and ambiguous rows are capped per anchor (5,104 rows), and the cap is declared
in `b_links.json`.

`REJECTED_L5` is large on purpose: it is the record of every match the rule refused, and it is what
makes the rule auditable.

## 5. Controls — the part that decides the study

### C1 keyword baseline

Firm brand token **or** any ≥ 4-character token of the product code's generic device name, in any
firm record inside the window.

| | value |
|---|---:|
| link rate | **99.2 %** (264 / 266) |
| median apparent "lead" | **1,821 days** |
| per-firm rate | 1.00 for 12 of 13 firms (Mindray 0.33) |

**The single most important number in the round.** Keyword co-occurrence "finds" earlier evidence
for essentially every milestone of a large device firm, with a *longer* median lead than the
anchored method. A lead-time claim published without this baseline measures the firm's publication
rate.

### C2 anchored method

| | value |
|---|---:|
| link rate | 69.9 % (186 / 266) |
| median lead (earliest verified evidence) | **1,620 days** [1,550, 1,679] |
| ≥ 90 / 180 / 365 days | 184 / 181 / 176 (98.9 % / 97.3 % / 94.6 %) |
| ≥ 90 days on the latest-plausible clock | 87.6 %, median 1,421 days |
| Q1 / median / Q3 | 1,254 / 1,620 / 1,769 days |
| minimum / maximum | 16 / **1,826 days** (the frozen 5-year window) |

### C3 matched decoy — specificity

For 249 anchors a decoy was built from another anchor of the *same firm* within ±730 days with a
*different product code*; the donor's distinctive token replaced the milestone's token, and the
identical linker ran on the anchor's own date. Real and decoy rates use the **same denominator**
(anchors that received a decoy).

| level | real rate | decoy rate | specificity |
|---|---:|---:|---:|
| pooled (any distinctive token) | 69.9 % | **51.4 %** | **1.37** |
| product-specific token | 22.5 % | 10.0 % | **2.24** |
| product-specific + pre-regulatory | 11.6 % | 6.4 % | **1.81** |

**Reading:** even at its strictest the procedure is under 2.3× better than a knowingly wrong
pairing. A usable early-warning instrument should be an order of magnitude better. The decoy is an
*easy* null (different product code), so these are upper bounds on specificity.

### C4 time placebo

* **C4a — anchor date shifted by a random ±[90, 1095] days** (2,000 draws; evidence and tokens
  fixed, window recomputed): null link rate **69.0 %** vs observed **69.9 %**, **p = 0.510**; null
  median lead 1,605 days vs observed 1,620, **p = 0.530**.
* **C4b — anchor dates permuted among same-firm same-year anchors** (2,000 draws): null link rate
  **70.0 %**, **p = 0.723**; median lead **p = 0.881**.

**Reading:** the lead time is not a property of the milestone date. Move the milestone by up to
three years and the measured lead barely changes, because a large firm's evidence pool is dense
enough that something product-named is almost always earlier.

### C5 concentration

Leave-one-firm-out link rate 65 %–71 %; the top product code carries ~2 % of verified links; yearly
rates 44 %–91 % with no monotone trend. The result is **stable and negative**.

## 6. Validity ladder — what survives the controls

| level | anchors | ≥ 90 d | median lead |
|---|---:|---:|---:|
| any distinctive token (frozen headline definition) | 186 | 98.9 % | 1,620 d |
| + product-specific token (used by ≤ 3 applicants) | 60 | 96.7 % | 1,351 d |
| + pre-regulatory (no regulatory record of that name existed yet) | 34 | 97.1 % | 1,341 d |
| + both | 31 | 96.8 % | 1,311 d |
| + literature-rare token (not an ordinary word of the field, Amendment 5) | **28** | 96.4 % | **1,317 d** |

The collapse from 186 to 28 has one dominant cause: **5,312 of 5,760 verified rows (92.2 %) are
about a product that already had an FDA record when the evidence was published**
(`PRE_EXISTING_PRODUCT`), against 448 genuinely pre-regulatory rows. That includes **203 rows
reclassified because the record itself says it is a post-approval / post-market / continued-access
study** (Amendment 6). A trial published before a *later* milestone is usually a trial of a device
already on the market — the exact trap this protocol was built to avoid.

### The 28 strict cases

Machine-verified at every level. `CAPTURING`, `TETHERING`, `POLYSACCHARIDE` are ordinary words that
only one applicant happens to use, and `MELODY` is a proprietary name whose device had an earlier
**HDE** approval absent from this corpus (see §8.7). Those four are for human adjudication, not
results. The other 24 rest on unambiguous proprietary names.

| milestone | firm | product (milestone) | token | public record | lead |
|---|---|---|---|---:|---:|
| 2021-08-14 | Abbott | Amplatzer Amulet LAA occluder | `AMULET` | CT.gov 2016-08-25 | 1,815 d |
| 2016-08-12 | Edwards | Intuity Elite valve system | `INTUITY` | CT.gov 2011-10-03 | 1,775 d |
| 2021-11-03 | BD | BD Kiestra IdentifA | `KIESTRA` | EPMC 2017-01-01 | 1,767 d |
| 2023-11-17 | Medtronic | Symplicity Spyral renal denervation | `SYMPLICITY` | EPMC 2019-12-10 | 1,738 d |
| 2021-09-17 | Abbott | Portico TAVI system | `PORTICO` | CT.gov 2017-02-17 | 1,673 d |
| 2015-03-13 | Boston Scientific | Watchman LAA closure | `WATCHMAN` | CT.gov 2010-08-16 | 1,670 d |
| 2017-12-18 | Zimmer Biomet | Sidus stem-free shoulder | `SIDUS` | CT.gov 2013-06-14 | 1,648 d |
| 2017-12-08 | Boston Scientific | Vercise DBS system | `VERCISE` | CT.gov 2013-07-11 | 1,611 d |
| 2024-04-01 | Abbott | TriClip G4 | `TRICLIP` | EPMC 2019-11-07 | 1,607 d |
| 2019-05-16 | Stryker | Neuroform Atlas stent | `NEUROFORM` | CT.gov 2015-01-16 | 1,581 d |
| 2023-12-13 | Medtronic | PulseSelect PFA system | `PULSESELECT` | CT.gov 2019-12-13 | 1,461 d |
| 2020-10-21 | Medtronic | Abre venous self-expanding stent | `ABRE` | CT.gov 2017-01-31 | 1,359 d |
| 2018-02-12 | BD | BD Onclarity HPV assay | `ONCLARITY` | EPMC 2014-07-01 | 1,322 d |
| 2023-05-04 | BD | BD Kiestra MRSA application | `KIESTRA` | EPMC 2019-10-01 | 1,311 d |
| 2024-02-01 | Edwards | Evoque tricuspid valve | `EVOQUE` | CT.gov 2020-07-22 | 1,289 d |
| 2021-03-17 | Boston Scientific | TheraSphere | `THERASPHERE` | CT.gov 2017-09-27 | 1,267 d |
| 2023-05-18 | Abbott | TactiFlex ablation catheter | `TACTIFLEX` | CT.gov 2020-04-21 | 1,122 d |
| 2018-09-18 | Boston Scientific | Eluvia drug-eluting stent | `ELUVIA` | CT.gov 2015-10-14 | 1,070 d |
| 2019-06-10 | Zimmer Biomet | AccuFill bone substitute | `ACCUFILL` | CT.gov 2017-04-12 | 789 d |
| 2015-02-20 | Medtronic | VenaSeal closure system | `VENASEAL` | CT.gov 2013-03-08 | 714 d |
| 2022-04-01 | Abbott | Aveir retrieval catheter | `AVEIR` | CT.gov 2020-09-23 | 555 d |
| 2022-03-31 | Abbott | Aveir VR leadless system | `AVEIR` | CT.gov 2020-09-23 | 554 d |
| 2015-01-27 | Medtronic | Melody TPV *(HDE caveat)* | `MELODY` | CT.gov 2014-12-30 | 393 d |
| 2015-12-17 | BD | BD FACSPresto system | `FACSPRESTO` | CT.gov 2015-03-24 | 268 d |
| 2023-08-08 | Boston Scientific | PolarX cryoablation catheter | `POLARX` | EPMC 2023-02-23 | 166 d |
| 2017-05-16 | Medtronic | TranSlaCe spinal tethering | `TETHERING` | EPMC 2017-01-09 | 127 d |
| 2017-11-03 | Boston Scientific | Capio SLIM suture capturing device | `CAPTURING` | CT.gov 2013-04-04 | 1,674 d |
| 2023-05-19 | Baxter | PerClot polysaccharide hemostat | `POLYSACCHARIDE` | EPMC 2023-04-21 | 28 d |

**Why this is a case series and not a finding.** Two numbers forbid a rate claim: the decoy rate for
this same strict class is 6.4 % against a real rate of 11.6 % (specificity 1.81), and the time
placebo cannot separate the observed rate from the null. The cases are *existence facts a human can
check*; they are not evidence that the procedure can find them in advance. The distribution of leads
(28–1,815 days) is itself informative: a real lead time is not one number.

## 7. Identifiability (Q3, hindsight-free)

For each of the 186 anchors with a verified link, a frozen query was run that uses only
pre-milestone information: firm + the official **generic** device name of the product code (never the
milestone's trade name).

| | value |
|---|---:|
| linked evidence such a query would have surfaced | **153 / 186 = 82.3 %** |
| records an observer would have had to read (median burden) | **124** (IQR 54–357) |
| anchors where the evidence is **hindsight-only** | 33 |

**Reading:** when early evidence exists, a name-free query usually reaches it — at a cost of ~120
records per milestone. That is a screening-workload measurement, not an early-warning capability; it
says nothing about whether a reader would have known which record mattered.

## 8. Failure analysis

1. **The lead time is a base rate.** C3 and C4 cannot separate the method from a wrong pairing or a
   shifted date. A firm with 2,892 indexed papers and 1,215 registered trials will have something
   product-named before any date chosen for it.
2. **Trials before approval are the norm.** 92 % of verified links are follow-up studies of
   already-regulated devices; 203 rows declare it in their own title. Removing them is the most
   important methodological step of the round.
3. **Good evidence lives where firms publish.** Medtronic, Abbott, Boston Scientific, Edwards and BD
   dominate the strict cases. Dräger (1 anchor, 42 EPMC records, 8 trials) and Mindray (3 anchors,
   234 EPMC records, 5 trials) supply none: for a European ventilator firm and a Chinese monitoring
   firm this instrument is structurally silent — a coverage fact, not a signal.
4. **The identifier chain almost never closes.** Only 7 product-specific L1 links exist: a paper
   citing the registry number of the very trial that names the device is rare. Cross-source
   identifier linkage is not available at scale, so verification rests on token identity.
5. **Date semantics dominate the precision.** The latest-plausible clock cuts the ≥ 90-day share
   from 98.9 % to 87.6 % and the median from 1,620 to 1,421 days. Direction survives; precision does
   not.
6. **No human gold standard for "same technology".** The machine proves token identity and date
   order; it cannot prove that a `TRICLIP` trial is about the device cleared under that trade name.
   That judgement is queued (`HUMAN_REVIEW_QUEUE.csv`), not claimed.
7. **HDE and other pathways are missing from the store.** A Humanitarian Device Exemption approval
   is neither a 510(k) nor a PMA, so a product with an earlier HDE looks new. That is the `MELODY`
   caveat above and an upper bound on how wrong the pre-regulatory class can be for small-volume
   devices.
8. **Token identity is not meaning.** `CAPTURING`, `TETHERING`, `POLYSACCHARIDE` are rare in the
   literature yet are ordinary English words; `product_specific` means "used by ≤ 3 applicants", not
   "identifies a product". Amendment 5 removes the worst of them; the rest need eyes.

## 9. Reproduce

```bash
python experiments/phoenix003/code/run_pipeline.py --db data/medradar.sqlite   # 196 s, offline
python experiments/phoenix003/code/selftest_offline.py                        # 26 tests, no DB
python experiments/phoenix003/code/e_review_queue.py --limit 40
```

## 10. Defects found by independent verification, and what changed

The first verification pass reproduced the mechanical layer exactly and then found eight defects.
All are fixed in the numbers above; `INDEPENDENT_VERIFICATION.md` keeps the original findings.

| # | defect | fix |
|---|---|---|
| 1 | `VERIFIED_L1` was assigned before the 5-year window test; 28 L1 rows lay outside the window and the max lead (3,512 d) was not protocol-legal | window test moved before tier assignment; max lead is now 1,826 d |
| 2 | EPMC matching used keywords + MeSH, not title + abstract (§6.1) | matching now uses `match_tokens` = title + abstract; keywords/MeSH only feed the C1 baseline |
| 3 | "pre-regulatory" included self-declared post-approval / post-market studies | Amendment 6: marker rule reclassifies them (`PRE_EXISTING_PRODUCT`, 203 rows) |
| 4 | ordinary English words (`OVERALL`, `EFFICIENT`, `ORGANS`) were treated as product tokens | Amendment 5: literature-rarity test (EPMC df ≤ 200 of 36,621); 4 strict cases removed |
| 5 | `Zimmer Medizinsysteme GmbH` (an independent company) was attributed to Zimmer Biomet | explicit `exclude_if_contains`; 3 anchors removed (269 → 266) |
| 6 | the deliverable omitted 1,606 of 6,532 verified rows | verified rows are never capped; only refused/ambiguous rows are |
| 7 | `specificity_note` contradicted its own values; C4b used 500 draws where the frozen rule fixes 2,000; the specificity ratio mixed denominators | note corrected, C4b uses 2,000, rates use a matched denominator |
| 8 | the tree was mid-run during verification (two intermediate states, one aborted stage) | the run is now the single state pinned by `results/manifest.json` |
