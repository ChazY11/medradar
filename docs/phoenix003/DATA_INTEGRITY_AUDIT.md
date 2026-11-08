# PHOENIX-003 — Data integrity audit

Every number in this file is produced by `experiments/phoenix003/code/a1_anchors.py`,
`code/b_links.py` and `code/b2_novelty.py`, written to `experiments/phoenix003/results/*.json`,
and re-derivable with a single command (§8). Nothing here is copied from an earlier round.

Store audited: `data/medradar.sqlite` (1.37 GB, read-only, single snapshot fetched
2026-10-30/31). Rows used: `events`, `product_codes`. The store is **not** modified.

---

## 1. What the regulatory corpus actually contains

| raw rows | count |
|---|---:|
| `510k` | 176,466 |
| `pma` | 57,372 |
| **total device rows** | **233,838** |

| canonical unit | count |
|---|---:|
| 510(k) milestones (unique `k_number`) | 176,466 |
| PMA **original** approvals (unique `pma_number`, empty supplement) | 1,482 |
| PMA **supplements** — excluded from the milestone definition | 55,890 |
| **canonical milestones** | **177,948** |

**Finding 1 — the dominant duplication in this store is not a duplicate *row*, it is a
duplicate *event*.** `k_number` is unique for all 176,466 510(k) rows and `(pma_number,
supplement_number)` is unique for all 57,372 PMA rows: there are **zero** repeated official
identifiers. But **97.4 % of PMA rows (55,890 / 57,372) are supplements** — a 30-day notice or a
process change is a regulatory action on an already-approved device, not a new milestone. Any
count of "FDA approvals" that includes PMA supplements inflates the PMA series by a factor of
about 39×. PHOENIX-002 found that ~15.9 % of device *events* were duplicates by a different
definition; with the identifier-based definition used here the duplication is 100 % explainable
and removed before any statistic is computed.

**Finding 2 — 162 natural-key collisions survive the identifier dedup** (174 extra rows): the
same (applicant, device/trade name, decision date, product code) recorded under two different
official identifiers. Rate 0.10 % of milestones. They are *reported*, not merged, because a
second K-number is a distinct regulatory object even when the label is identical; all 162 are
outside the anchor window or outside the sampling frame (checked by the funnel, §2), so no
anchor is affected.

| duplicate check | value |
|---|---:|
| repeated `k_number` | 0 |
| repeated `(pma_number, supplement_number)` | 0 |
| natural-key collision groups | 162 |
| natural-key extra rows | 174 (0.10 %) |
| rows with missing official identifier | 0 |

## 2. Attribution — and why it is *not* a random sample of applicants

Attribution rule: token-equality brand lineage (`dataset/firm_lineage.json`, frozen). A record
is attributed only when the applicant string carries the firm's brand token, with two
qualifier rules (`GE` needs a healthcare/medical qualifier; `BOSTON` needs `SCIENTIFIC`).
Acquired companies are **not** attributed before their acquisition, because the store holds no
acquisition close date — they are counted as a coverage loss instead of being guessed.

| | count | share of milestones |
|---|---:|---:|
| attributed to one of the 13 frame firms | 12,230 | 6.87 % |
| UNKNOWN (any other applicant) | 165,718 | 93.13 % |

The 93 % is **not** an attribution failure rate in the sense of lost data: the store contains
the whole US device market, and the sampling frame is 13 firms. Reported as a rate anyway
because a reader must be able to see it. Inside the frame, strict attribution (brand token in
the first two tokens, no parenthetical re-branding) covers **90.7 %** of anchors, and the
lineage-inclusive vs strict counts differ by 627 milestones (5.1 % of attributed milestones) —
that difference is the part of the sample that depends on the lineage rule.

Known lineage hazards, all measured rather than hidden:

* `Melmedtronics, Inc.` is a different company and is **not** attributed (token equality).
* `Spectranetics Corporation` before 2017 is **not** a Philips record; `Spectranetics (Philips)`
  after acquisition is.
* `Covidien`, `Given Imaging`, `Bellco` are **not** Medtronic records in the pre-acquisition
  period even though the store sometimes labels them with the parent.
* `Philips Lighting`, `Philips Consumer Lifestyle`, `Philips Oral Healthcare` and
  `Drager Safety` are retained by the frozen token rule because they *are* the firm's
  subsidiaries, although they are outside the medical-device core. They appear in the audit as
  domain contamination; no anchor in the final sample comes from them.
* `Biomet` is deliberately excluded from the Zimmer lineage (pre-2015 independence).

## 3. Time semantics

| field | value |
|---|---|
| `decision_date` null | 0 |
| `date_received` null | 0 |
| received → decision lag, median | 81 days |
| received → decision lag, p10 / p90 | 22 / 252 days |
| negative lags | 0 |
| `timestamp_quality` values | `date` for 100 % of rows |
| `available_at == event_date` | yes, for every row |

**Finding 3 — the store has no observation clock.** `available_at` equals the event date and
`fetched_at` spans two days, so the store cannot say *when a record became observable*. This
study therefore never uses `available_at`; the only public date it uses on the regulatory side
is the FDA decision date, which is a genuine publication date for a 510(k)/PMA decision.

**Finding 4 — the decision date is late by up to ~8 months relative to the application.** The
received→decision lag has a p90 of 252 days. A milestone dated at the decision is therefore
*conservative* for a pre-milestone claim: the underlying application existed earlier, and any
evidence that predates the decision is even earlier relative to the application. This biases the
measured lead time **downward**, never upward.

## 4. Taxonomy — no back-filled tracks anywhere

The sampling frame uses the **record's own FDA product code** (4796 distinct codes appear in the
510(k) rows; the `product_codes` catalogue has 7,097). The store's 60 `track_id` values are
*not* used for sampling, labelling or matching, because their `updated_at` is a single 2026
snapshot and PHOENIX-002 showed 18/38 device tracks "first appear" in 1976Q3 — the signature of
a modern taxonomy projected backwards. The only use of the `product_codes` table is to look up
the **generic device name of the official code** for the hindsight-free query (protocol §7).
That lookup uses the code as it exists in the catalogue, and is applied identically to every
anchor.

## 5. Sampling funnel (re-computable)

```
milestones loaded                        177,948
  attributed to frame firms               12,230
  excluded: non-substantive decision         393   (NSE / DENO / SESU / WD …)
  excluded: missing product code              59
  excluded: no distinctive token             796
  (firm, product code) pairs               2,249
  first-in-code inside 2015-2024             268   <- anchor sample
```

Anchor sample composition:

| | anchors |
|---|---:|
| core stratum (Medtronic, GE HealthCare, Philips, Dräger, Mindray) | **59** |
| extension stratum (8 other registered device firms, protocol §10 rule) | **209** |
| total | 268 |
| 510(k) / PMA-original | 219 / 49 |
| distinct product codes | 248 |
| strict attribution share | 90.7 % |

Per firm: medtronic 40, abbott 45, boston_scientific 41, stryker 38, siemens_healthineers 34,
edwards_lifesciences 15, zimmer_biomet 15, bd 13, philips 11, baxter 8, ge_healthcare 4,
mindray 3, draeger 1.

**Finding 5 — the extension rule fired.** Only **two** core firms reach the pre-registered
5-anchor floor (Medtronic 40, Philips 11). GE HealthCare has 4, Mindray 3, Dräger 1. The
pre-registered extension to eight further registered device firms was therefore triggered, and
the 209 extension anchors are reported **separately** everywhere; they are never pooled with the
core five in a headline number.

**Finding 6 — first-in-code is a genuinely different construct from "a lot of clearances".**
The 268 anchors are, by construction, *new* product codes for their firm. Medtronic has 1,707
attributed milestones but only 40 new codes in the window; the remaining 1,667 are repeat
activity in codes the firm already occupied. This is the sampling frame PHOENIX-002 lacked: every
anchor can in principle have earlier evidence, and none of them is a structurally impossible
negative.

## 6. External corpora (harvested independently of the anchors)

Harvest queries are firm-anchored and were frozen in `fetch/FETCH_SPEC.md` before the anchor set
existed, so no retrieval choice can be influenced by which milestones look interesting.

### 6.1 ClinicalTrials.gov

| firm | retained studies |
|---|---:|
| medtronic | 1,215 |
| philips | 316 |
| ge_healthcare | 258 |
| draeger | 8 |
| mindray | 5 |
| **total** | **1,802** |

* raw rows fetched 2,412 → 2,407 unique → 1,802 retained by the frozen `first_posted` window;
  605 dropped as pre-2010 or post-2025 (one study reports a 2026 first-posted date).
* `first_posted` null: 0. `lead_sponsor` null: 0. 1,073 retained studies carry at least one
  `DEVICE` intervention.
* 3 studies were returned by two different sponsor queries.
* **Coverage limit, stated in advance and now measured:** ClinicalTrials.gov is a poor source
  for Dräger and Mindray (8 and 5 studies). Trial registration is largely a US/academic practice;
  a European ventilator firm and a Chinese monitoring firm register almost nothing. Any conclusion
  about "trial evidence" for those two firms is unsupported by construction.
* Contamination measured: the `Draeger` sponsor query returns a German health insurer
  ("Draeger and Hanse BKK") and, under the umlaut spelling, a physician surname. These records do
  not resolve to the firm under the lineage rule and cannot enter a link.

### 6.2 Europe PMC

*(populated from `fetch/EPMC_FETCH_MANIFEST.json` after the harvest completes — see
`EXPERIMENT_RESULTS.md` §2 for the final counts; the numbers are not typed by hand.)*

## 7. Defects this audit closes, and the ones it does not

| PHOENIX-002 defect | status in PHOENIX-003 |
|---|---|
| label-maturity / time leakage | **closed by construction**: no model, no label; evidence must be published strictly before the milestone |
| structurally impossible negatives | **closed**: every anchor is a new product code and can in principle have earlier evidence |
| duplicate regulatory records | **closed and quantified**: identifier dedup, PMA supplements excluded, 0 duplicate keys, 162 natural-key collisions reported |
| modern taxonomy back-filled | **closed**: the record's own product code is used; the 2026 `track_id` layer is never used |
| missing firm attribution | **partly closed**: `UNKNOWN` is retained and reported, acquisition back-projection is refused, strict vs inclusive lineage reported |
| feature/target coupling | **not applicable**: there are no features and no target |
| simple trends beat complex models | **not applicable**, but the naive keyword baseline is run as a peer (C1) |
| single snapshot not point-in-time | **NOT closed, and cannot be** with this store: the study is a retrospective evidence study and says so in every claim |

## 8. Re-derivation

```bash
python experiments/phoenix003/code/run_pipeline.py --db data/medradar.sqlite
python experiments/phoenix003/code/selftest_offline.py
```

`results/manifest.json` records the sha256 of every artefact this audit cites.
