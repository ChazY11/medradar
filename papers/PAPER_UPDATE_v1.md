# A marginal entry signal, a closed negative, and a corrected record: results update v1

**MedRadar Foresight Lab** · results update, version 1 draft · 2026-11-03

---

## Abstract

This update reports what the programme learned after `PAPER_v1.md` — seventeen cycles over a frozen 2016–2026 lane
(31,802 submissions), five retractions, one confirmed decision rule. It adds a **full-history panel** (1976–2026), a
pre-registered **successor design** at a coarser unit, the **final adjudication** of the five-firm study, and an
independent audit with its corrections.

Four findings carry it. First, regulatory-sequence signals rank future first clearances better than firm persistence
— per-origin AP **0.1137** vs **0.0553**, Δ **+0.0584**, 95 % CI **[+0.0020, +0.1213]**, permutation p **0.0299** —
but not better than the two-way exposure baseline B3 (Δ **+0.0438**, CI **[−0.0184, +0.0957]**), and the MDE
(0.0896) exceeds the effect. Second, the pre-registered domain-level successor repeats the pattern: ΔAP **+0.0340**
(95 % CI **[+0.0215, +0.0661]**, MDE **0.0316**) over persistence, but **+0.0156** over B3 (CI
**[−0.0107, +0.0445]**, p = **0.212**). Third, the five-firm study closes **negative** under an owner-authorised,
explicitly **non-human** AI adjudication: **0/69** packets are `Confirmed Shift` (0.0 %, one-sided 95 % Wilson upper
bound 5.3 %), and the nine-event lead-time description is withdrawn. Fourth, no cross-source lead is detectable at
company level (MDEs **0.0723**, **0.0513**, **0.0570**), procurement is `NOT_EVALUABLE`, and fusion is invariant to
publication lags of 0/14/30/90 days.

The audit produced three integrity corrections, including a forecast filter that checked the window end rather than
its start (**12 of 25** records affected). This is an update about **public filing behaviour** — not intent,
capability or internal R&D.

---

## 1. Introduction: what changed since PAPER_v1

`PAPER_v1.md` reported a measurement apparatus and a failure ledger: a frozen 2016–2026 lane of 31,802 premarket
submissions, 9,412 legal entities, a controlled-truth detector frontier, a rolling-origin benchmark, five
retractions, and one confirmed rule about promoting alerts. Its conclusion was deliberately narrow: the data support
budget-explicit statements about **public filing rates** and nothing about intent, capability or internal R&D.
Nothing in that ledger is withdrawn here.

Four things changed. **(i) The history is now the dataset.** A panel was rebuilt from the complete openFDA device
record and pre-registered over 53 companies, 38 tracks and 528 pairs. **(ii) The unit changed.** `hist_v1` measured
that its adjacency restriction excluded most milestones and that 38 tracks are too fine for the modern era, so
`hist_v2` pre-registered a **domain-level** successor (22 domains) before any hist_v2 model was fitted. **(iii) The
five-firm study was adjudicated and closed.** **(iv) The record was independently audited**, and three defects became
corrections (Section 4).

The organising question is unchanged: *can publicly observable regulatory activity rank a firm's future entries
better than its own persistence?* The update answers it at three resolutions — a marginal yes, a design-limited no,
a closed negative — and keeps them separate.

---

## 2. Data and Design

### 2.1 The full-history panel (`hist_v1`)

The unit is `company × technology track × quarter` on the grid **1976-Q1 … 2026-Q2** (202 quarters; partial 2026-Q3
excluded). The panel holds **53 companies**, **38 tracks** and **528 observed pairs** with **14,704 material events**
(14,090 510(k) + 614 PMA). The funnel is a result: only 8.2 % of 178,417 material device events enter, because
**55.1 %** have no track mapping and **86.1 %** have no company in the 51-company roster. This is a curated-roster
panel, not an industry panel.

At origin quarter *t* a pair is a candidate if the company has a material event by *t* and the pair has none; on
`R_adj` the company must also have an event in another track of the same category. The label is 1 iff the pair's
first material event falls in `(t, t+8]`. The 15 point-in-time features cover firm, track, adjacency and category
quantities. The model is an L2 logistic regression with training-only standardisation and median imputation, no
tuning. Baselines are prevalence (B0), company rate (B1), track rate (B2) and the two-way product B3 = B1 × B2.
Evaluation is expanding-window walk-forward over **30 origins** (1995-Q1 … 2024-Q1); the primary comparison is
M1C − B1 with a company-clustered paired bootstrap (2,000 resamples). Point-in-time discipline is enforced in code:
every feature uses only events with `available_at ≤` end of *t*, and training rows satisfy `t' + h ≤ t` with the
purge asserted at **0 violations**.

### 2.2 The domain-level successor (`hist_v2`)

`hist_v2` is `company × technology-domain × quarter` over 1976-Q1 … 2026-Q2: 53 companies, **22 domains**, **377
domain pairs**, a domain event aggregating its tracks' material events. Origins are the entry-rich era **1995 … 2015**
(21 annual origins); post-2015 is a **descriptive holdout only**. `R_dom` drops the adjacency restriction by design,
so new-category entries are included. The success criterion was frozen before fitting: the ΔAP(M1−B1) interval
positive, the ΔAP(M1−B3) point estimate positive, at least 60 % of origins positive, **and** a measured MDE
**≤ 0.05** AP points; otherwise the result is declared underpowered in advance.

### 2.3 Target B and the cross-source lanes

The five-firm confirmatory target is 69 candidate packets (60 from the candidate generator, 9 from the small-sample
probe), labelled against a frozen five-label vocabulary. `Dräger` contributes **0** packets, so no equal-depth
five-firm comparison is made.

`b103` tests whether financial R&D, market return or publication activity lead material regulatory events at company
level over **2017-Q1 … 2025-Q4** (36 quarters), with per-company z-scores, lags −8 … +8, a clustered bootstrap, a
circular-shift null and Holm correction across three sources. Procurement is `NOT_EVALUABLE`: 3,453 rows, every
`announcement_date` NULL, `pit_usable=0`, no proxy. `b104` re-runs the `hist_v1` fusion comparison (feature set C
without trial/publication features versus D with them) at publication knowledge lags of **0/14/30/90 days**.

---

## 3. Results

### 3.1 `hist_v1`: the primary test is supported, marginally

On `R_adj` at h=8 the evaluation covers 30 origins, **8,415 candidate cells** and **181 positive cell-rows** — 6.0
positives per origin. Mean per-origin AP is **0.1137** for M1C against **0.0553** for B1: a point ΔAP of **+0.0584**
with 95 % CI **[+0.0020, +0.1213]**, p = 0.045 and MDE **0.0896**. The permutation null (200 permutations) gives
empirical p = **0.0299**; only six scrambles reach the observed Δ. The criterion is met, so H1 is recorded as
**SUPPORTED**.

"Marginally" is doing real work: the CI's lower bound is 0.002, the MDE exceeds the observed effect, and the h=4
bootstrap was unreliable, so no 12-month claim is made. Supported means the pre-registered criterion was met, not
that the signal is practically strong.

### 3.2 `hist_v1`: the decisive comparison is not established

Against the strongest no-feature baseline B3, M1C gains a point ΔAP of **+0.0438** but the 95 % CI is
**[−0.0184, +0.0957]** with p = 0.198 and MDE 0.087: the interval includes zero. The features therefore beat
persistence (+0.0584) and tempo (+0.0669) **separately**, while their incremental value over the **product** of the
two is **not established**. The unrestricted risk set repeats the pattern (+0.0300, CI [+0.0128, +0.0699] against B1;
+0.0210, CI [−0.0087, +0.0565] against B3). Firm-only features fall **below** the company base rate; track features
add about 0.035 and activity in adjacent tracks a further 0.023 — a mechanism hypothesis, not a capability.

### 3.3 `hist_v2`: the successor beats persistence, not two-way exposure

The successor was pre-registered to be able to fail; its primary test passes. On `R_dom` at h=8 over 21 origins the
evaluation has **15,233 candidate cells** and **252 positives** — **725.4 candidates** and **12.0 positives** per
origin. Mean per-origin AP
is **0.0775** for M1C against **0.0435** for B1: Δ **+0.0340**, 95 % CI **[+0.0215, +0.0661]**, **85.7 %** of
origins positive, and MDE **0.0316**, inside the pre-declared 0.05 target, so the protocol records H1 as
**SUPPORTED** and the design as powered. The permutation null agrees: 0 of 200 scrambles reach the observed Δ
(empirical p = **0.0050**, the resolution floor).

The decisive secondary does **not** pass. Against the two-way exposure baseline B3 (mean AP **0.0619**) M1C gains Δ
**+0.0156** with 95 % CI **[−0.0107, +0.0445]** and p = **0.212**: the interval includes zero, so incremental value
over the product of firm persistence and domain tempo is **not established**, even though the criterion's
point-estimate clause is satisfied. The full feature set also adds nothing over the domain-feature set (M1B
**0.0812** vs M1C **0.0775**), so `hist_v1`'s mechanism result does not replicate as an incremental gain at domain
level.

### 3.4 The five-firm Target B closes negative

The five-firm candidate generator is **not validated**: under the owner-authorised AI adjudication, **0** of **69**
packets are `Confirmed Shift` (0.0 %, one-sided 95 % Wilson upper bound 5.3 %); 8 false signals, 52 routine iterations
and 9 uncertain. The 8 false signals are all in the 9 small-sample pairs, and **8/9** of those
pairs are device/project mismatches, so the nine-event lead-time description is **withdrawn**. The pre-registered
halt rule fires; fusion and lead time are `NOT_EVALUABLE`, heterogeneity is descriptive only, and no recall,
precision, calibration or lead-time claim is made.

This closure is about **the candidate generator**, not the firms: the adjudication asks whether these packets'
evidence chains support a technology shift, not whether the companies innovate. It is also not a human judgement.
The labels were produced by an AI review under an explicit owner authorisation that waived human sign-off **for this
study only**; `human_truth` is false, no human worksheet field was filled, and the labels may not be pooled with
human-labelled benchmark sets.

### 3.5 No cross-source lead is detectable at company level

The frozen `b103` rule requires a positive lead lag, Holm-adjusted p < 0.05, and era stability. No source meets it.
Financial R&D: k* = 1, r = **−0.0441**, 95 % CI [−0.1193, 0.0366], permutation p = **0.683**, Holm p = 1.000, not
era-stable, MDE **0.0723**. Market return: r = **−0.0278**, p = **0.967**, MDE **0.0513**. Publication: r =
**−0.0387**, p = **0.614**, era-stable, MDE **0.0570**. All three are **well-powered negatives**: the MDEs bound |r|
near 0.05–0.07, so a lead of that size is excluded, not "no relationship". Procurement is `NOT_EVALUABLE`; market
volatility (r = 0.0420, p = 0.754, MDE 0.0568) is descriptive only, outside the Holm family.

### 3.6 Fusion is invariant to publication knowledge lags

At lags of **0/14/30/90 days** the fusion comparison is unchanged. At 0, 14 and 30 days the run reproduces `hist_v1`
exactly — publication join 0.786, AP(C) 0.0401, AP(D) 0.0348, Δ **−0.0053** — and at 90 days the lag removes
prior-year publications at first-quarter origins in non-leap years (join falls to **0.200**) and Δ becomes
**−0.0017**, still negative. No lag produces a positive Δ, so the frozen rule returns "unchanged": adding trial and
publication features does not improve ranking, at 90 days on about 20 % join coverage.

---

## 4. Corrections and audit

An independent audit re-checked 33 load-bearing rows against artifacts at HEAD rather than prose: **21** verified,
8 partially, 2 failed, 2 unverified. Three defects were integrity defects and are now corrections.

**D-075 — the forecast filter tested the wrong property.** The rule was "register only alerts whose outcome window is
entirely in the future"; the code tested the window **end** only, so **12 of the 25** "genuinely prospective"
forecasts had outcome windows beginning at or before the 2026-Q3 lane cutoff. The filter now also requires the window
start to be after the cutoff; the re-registered set has **13 forecasts**, earliest maturation **2027-Q3**. No
forecast had matured, so no calibration claim existed and none is retracted.

**D-076 — a flagship script could not be re-run.** `rolling_origin.py` crashed at HEAD because one module emitted a
date as an ISO string while another expected a `date` object. The fix accepts both types, and re-running writes a JSON
object **identical** to the committed benchmark. That the defect survived is the point: no gate step ran the script,
so "every reported number is re-derivable" was false for a load-bearing result.

**D-077 — a leak-audit defect voided one full-history run.** The first execution of the frozen `hist_v1` protocol
produced 110 positive cells and an unreliable bootstrap. The pre-registered leak audit then found **184/300**
feature-replay mismatches: an index was built in pair-record order rather than sorted order, so a binary search
returned wrong adjacency counts and the same unsorted index corrupted the risk-set predicate — **7,556** candidates
instead of 8,415. After the sort fix, replay mismatches fall to **0/300**, positives rise from 110 to **181**, the
bootstrap becomes reliable, and the verdict changes from unreliable to supported. The void result was never
published — the clearest case of a code path deciding a verdict.

Two further corrections complete the record. The audit's own limits are recorded: the claim map is a **text matcher**
(**61/88** claims in `PAPER_v1.md` cite the decision log), and a clean clone cannot regenerate event-lane results
because the stores are not committed — "verified" is not "reproduced". `D-080` records a falsified premise: 19,616
unlinked 8-K events were said to carry a resolvable CIK, but only **826** equal exactly one curated-company CIK and
**all 826** were already linked; the rest belong to 1,530 non-roster registrants. The lesson — **count before
concluding unavailable** — matches `PAPER_v1`'s rule.

---

## 5. Limitations

1. **The primary result is marginal and the decisive one is null.** The lower CI bound is 0.002, the MDE (0.0896)
   exceeds the observed effect (0.0584), and the advantage over B3 is not established. No product, detector or
   taxonomy change was made on it.
2. **The panel is a curated roster.** 53 companies, **86.1 %** of material events outside the roster, **55.1 %** of
   material events untracked, a current-corporate-group entity mapping, and an unversioned taxonomy.
3. **Target B labels are AI-adjudicated, not human.** `human_truth` is false, the adaptation is owner-authorised for
   one study, and the packet set is unbalanced (Dräger 0 of 69). The negative is about the candidate generator under
   that adjudication, not about the firms.
4. **No prospective calibration exists.** The corrected set has 13 records, none matured, earliest 2027-Q3. Every
   number here is retrospective walk-forward, not live forecasting.
5. **The successor passed its power gate without resolving the decisive question.** Its measured MDE (0.0316) met the
   pre-declared 0.05 target, but the ΔAP(M1−B3) interval includes zero, so incremental value over two-way exposure
   remains not established. The protocol's `pairs_no_acquired` attribution sensitivity was then run: removing 217
   acquired-brand events (**14,487 of 14,704** retained) leaves the primary pattern intact, with
   ΔAP(M1−B1) = **+0.0361** and a reliable bootstrap (0 % degenerate resamples). It is a descriptive sensitivity, not
   a second confirmatory test.
6. **Correlation, prediction and causation are kept separate.** A leading correlation does not establish that a
   source causes or predicts an event; a ranked entry probability is not strategic intent; and nothing here observes
   internal R&D, pipelines or budgets. The data record that a firm asked for permission to market a device — not why.

---

## 6. Discussion: what the programme can and cannot claim

**Can claim.** A reproducible, audited full-history panel with a source-hash manifest. A pre-registered entry-ranking
test that is supported marginally, with the mechanism located in track tempo and adjacency rather than firm momentum.
Three well-powered null tests bounding any company-level cross-source lead. A negative fusion result invariant to the
tested publication lags. A closed negative on a candidate generator: 0/69 confirmed.

**Cannot claim.** That the marginal ranking advantage has practical early-warning value — the CI reaches 0.002 and
the MDE exceeds the effect. That the time-varying features add value over two-way exposure — they do not,
statistically. That the five-firm study found nothing to find — it found that its candidate generator produced no
confirmed shifts under a non-human adjudication. That procurement can answer the lead question — it is
`NOT_EVALUABLE`. And that any of this sees inside a firm: public filing behaviour is an output, and the programme's
claims stop at the output.

The pattern is consistent with `PAPER_v1`: the durable products are measurement decisions and negatives, and the one
positive is thin. What changed is the scale of what can be tested — a 50-year panel and a pre-registered successor
unit — and an audit that found three defects the programme's own gate had not.

---

## 7. Reproducibility

```bash
python experiments/hist_v1/build_panel.py
python experiments/hist_v1/eval.py --panel out/hist_v1/panel.json --out experiments/hist_v1/results.json --workers 12
python experiments/hist_v2/build_domain_panel.py
python experiments/hist_v2/eval.py --panel out/hist_v2/domain_panel.json --workers 12
python experiments/b103_leadlag/leadlag.py
python experiments/b104_publag/publag.py
python papers/verify_claims.py --paper papers/PAPER_UPDATE_v1.md --claims papers/CLAIMS_UPDATE.json
```

All analysis code is standard-library Python; the `hist_v1` evaluator fixes all seeds, and its panel is byte-identical
across two runs. `verify_claims.py` checks both directions for every claim in `CLAIMS_UPDATE.json` — the named source
must literally contain the needle and this paper the value — and exits non-zero on any mismatch. The event-lane
stores are not committed, bounding what a clean clone can regenerate (Section 4).

---

## References

**Data sources.** U.S. FDA premarket notification (510(k)) and premarket approval (PMA) datasets. ClinicalTrials.gov
API v2, U.S. National Library of Medicine. Internet Archive Common Crawl CDX / Wayback CDX index, Internet Archive.

**Methods.** Benjamini, Y. and Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful
approach to multiple testing. *Journal of the Royal Statistical Society B* 57(1), 289–300. Page, E. S. (1954).
Continuous inspection schemes. *Biometrika* 41(1/2), 100–115. Wald, A. (1945). Sequential tests of statistical
hypotheses. *Annals of Mathematical Statistics* 16(2), 117–186.

**Programme record.** `research/DECISIONS.md`, `research/protocols/`, `experiments/hist_v1/`,
`experiments/hist_v2/`, `research/studies/early_signal_5firms/` and
`research/audits/initial_research_audit.md`.

---

## Appendix A — claim map

`papers/CLAIMS_UPDATE.json` lists every claim with its artifact and exact source substring; `verify_claims.py`
re-checks both directions and exits non-zero on any mismatch.
