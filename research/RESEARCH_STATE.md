# RESEARCH_STATE — the live state of the MedRadar research programme

**Last updated:** 2026-11-03 · **Branch:** `research/full-history-v1` · **Worktree:** `D:/DEPPSKK/worktrees/hist-v1`
**Supersedes as "current state":** `research/STATE.json` remains the machine-readable record; this file is the
human-readable entry point required by the research directive. Where they disagree, this file's *numbers* were
re-derived from artifacts at the date above; `STATE.json` is updated in the same commit.

---

## 1. Where the programme actually is

The programme has a verified temporal foundation, a validated change detector with measured operating characteristics,
a working UNDERSTAND layer (firm profiles), two papers, and an independent audit of its own record. Its forward-looking
(ANTICIPATE) layer has produced **one pre-registered, marginally supported positive result** in this round and **zero
certified prospective evidence**. The binding constraint has moved: not "the store only has 10 years" (false — it has
50), but the **taxonomy's resolution (55.1 % of material events have no track)**, the **roster's coverage (86.1 % of
material events belong to no roster company)**, and the **small number of entry milestones per origin**.

## 2. Latest verified results (this round, hist_v1)

All from `experiments/hist_v1/results.json`; report: `experiments/hist_v1/REPORT.md`; numbers re-checked by
`experiments/hist_v1/verify_report_numbers.py` (**155 checks, 0 failed**). The external-AI-review rows H-14–H-16 are
from `research/studies/early_signal_5firms/AI_REVIEW_ADJUDICATION_V1.json` and its ingester tests (7 tests).

| # | result | value | status |
|---|---|---|---|
| H-1 | full-history panel built, audited, deterministic | 1976-Q1…2026-Q2; 53 firms; 38 tracks; 528 pairs; 14,704 material events; panel SHA-256 `10f8c00a…` | artifact |
| H-2 | **pre-registered primary test** (R_adj, h=8, M1C−B1) | 30 origins, 8,415 candidates, 181 positives; AP **0.1137 vs 0.0553**; Δ **+0.0584**, 95 % CI **[+0.0020, +0.1213]**, p 0.045, MDE 0.0896 | **SUPPORTED (marginal)** |
| H-3 | against the two-way exposure baseline B3 | Δ +0.0438, CI [−0.0184, +0.0957], p 0.198 | **not established** |
| H-4 | label-permutation null (200 perms, R_adj, h=8) | observed +0.0584 vs null mean +0.0239 (sd 0.0129, max 0.0667); **p = 0.0299** (6/200), floor 0.005 | **positive robustness** |
| H-5 | ablation: where the signal is | firm-only **below B1** (−0.0064); +industry/track +0.0352; +adjacency **+0.0584**; eras +0.0879/+0.0634/+0.0239 | **mechanism result** |
| H-6 | unrestricted risk set (R_full) | h=8: AP 0.0607 vs 0.0307; point Δ +0.0300, CI [+0.0128, +0.0699]; vs B3 +0.0210, CI [−0.0087, +0.0565] | supported vs persistence only |
| H-7 | fusion (H2) | on 2016+ origins: C 0.0401 → D 0.0348, Δ **−0.0053**, bootstrap UNRELIABLE | **not supported / negative** |
| H-8 | H5 lead-time frontier | 94 in-scope entries of 255; 1 % budget: 9/94, precision 0.206, median lead 5 q, 5.9 FA/1,000; 10 %: 24/94, 0.094, 6 q, 50.6; 20 %: 38/94, 0.073, 98.3 | **descriptive, quantified** |
| H-9 | five-firm saturation | no new track after 2012 (MDT), 2000 (GEHC), 2014 (Dräger), 2011 (Mindray); Philips +4 in 2016–2025; 161/255 entries are new-category | **descriptive finding** |
| H-10 | audit of the record (independent) | 33 claims: **21 verified, 8 partial, 2 unverified, 2 failed**; 12 defects, 5 ranked threats | `research/audits/initial_research_audit.md` |
| H-11 | prospective-set correction (defect found by audit) | 25 → **13** genuinely prospective forecasts (12 had partially observed outcome windows); 19 excluded; new hash `8ac0b8df…` | **corrected (D-075)** |
| H-12 | rolling-origin reproducibility (defect found by audit) | `b050/rolling_origin.py` fixed and now reproduces committed JSON **identically** | **fixed (D-076)** |
| H-13 | leak-audit defect in this study's own first run | unsorted company-category index corrupted risk set (7,556 vs 8,415 candidates) and features (184/300 replay mismatches); after fix 0/300 and verdict UNRELIABLE → SUPPORTED; void result not published | **defect found and fixed (D-077, R167)** |
| H-14 | external AI review of the 69 five-firm packets ingested | 69/69 labelled with evidence locators; human fields empty; reviewer "Codex AI (not a human reviewer)"; authority `AI_ONLY_NOT_HUMAN_GOLD_STANDARD`, `blind_review=false`; registered as tier `EXTERNAL_AI_REVIEW` with `can_count_as_human_truth=false` by a validating ingester | **deliverable (non-human tier, D-078)** |
| H-15 | the five-firm halt rule fires | labels Routine 52 / Uncertain 9 / False Signal 8 / **Confirmed Shift 0**; pre-registered rule (<10 confirmed ⇒ descriptive design) triggers; **Target B stays unlabelled** and no Target B metric may be computed from this tier | **decision (negative for Target B)** |
| H-16 | the nine-event lead-time description is withdrawn | 8/9 small-sample pairs (`LT-02…LT-09`) are device/project mismatches and `LT-01` is Uncertain, so the 3.3-quarter median lead is not a lead-time estimate of anything; 13 novel-entry packets are left-censored, 5 are manufacturing notices, 1 is a De Novo misrecorded as a 510(k); packet set is Philips 23 / Medtronic 21 / GEHC 16 / Mindray 9 / Dräger 0 | **retraction + packet-defect failure analysis (R170/R171)** |
| H-17 | **owner authorises the AI review as final; human sign-off waived for this study** | new tier `FINAL_ADJUDICATION_AI_OWNER_AUTHORISED` (dated authorisation required; fabricated `Confirmed Shift` refused; no overwrite of existing human/final labels; human columns stay empty; `human_truth = false`); scope limited to this study — the promotion policy's human gate is untouched | **protocol amendment (D-079, S-035, R172)** |
| H-18 | **Target B closes as a negative** | **0/69** confirmed shifts (0.0 %; one-sided 95 % Wilson upper bound **5.3 %**), 8 false signals (all 8 in the 9 small-sample pairs), 52 routine iterations, 9 uncertain; H1 fusion and H2 lead time `NOT_EVALUABLE`, H3 descriptive only, H4 untestable | **final negative result (R173/R174)** |
| H-19 | **B-029: the CIK join finds nothing left to link** | 20,976 8-K events all carry payload CIKs, but only **826** equal exactly one curated-company CIK and **all are already linked**; the 19,616 unlinked are 1,530 non-roster registrants. `companies.cik` is empty in every store; the corpus ticker field would have manufactured 58 bogus links (excluded). Precision sample 60/60; 0 contradicted | **measurement closes the item (D-080, R178)** |
| H-20 | **B-021: no cross-source lead is detectable at company level** | 2017-Q1…2025-Q4, lags −8…+8: financial R&D k*=1 r −0.0441 (p 0.683, MDE 0.072), market return k*=5 r −0.0278 (p 0.967, MDE 0.051), publications k*=1 r −0.0387 (p 0.614, MDE 0.057); Holm 1.000; era-stable only for publications; procurement NOT_EVALUABLE | **well-powered negatives (D-081, R179)** |
| H-21 | **B-041: the fusion conclusion is lag-invariant** | 0/14/30-day publication lags reproduce hist_v1 exactly (join 0.786, AP(C) 0.0401, AP(D) 0.0348, Δ −0.0053); 90-day lag removes year−1 for non-leap first quarters (join 0.200) and Δ is −0.0017 — still negative | **negative robustness (D-082, R180)** |
| H-22 | **hist_v2: the domain-level replication** | 22 domains, 21 origins 1995–2015, 15,233 cells, 252 positives (12.0/origin); M1C mean AP **0.0775** vs B1 0.0435, Δ **+0.0340**, CI **[+0.0215, +0.0661]**, MDE **0.0316** (pre-declared ≤0.05), 85.7 % origins positive, permutation p at the 200-draw floor | **positive, powered (D-083, R181)** |
| H-23 | **but the decisive B3 comparison fails again, and the mechanism is unit-dependent** | Δ(M1C−B3) = +0.0156, CI **[−0.0107, +0.0445]**, p 0.212 — the incremental value over firm×domain exposure is not established, replicating hist_v1; at domain level the domain-tempo features carry the signal (M1B 0.0812) and adjacency slightly hurts (M1C 0.0775), the opposite of hist_v1's track-level result | **replicated partial negative + mechanism finding (D-083, R182/R183)** |

## 3. Hypotheses and their current status

| hypothesis | status after this round |
|---|---|
| **H1** early research/clinical/regulatory signals precede verifiable milestones | **supported, marginally, at 24 months** on the pre-registered primary risk set (CI [+0.0020, +0.1213], permutation p 0.030) — **not** against the two-way baseline; the 12-month horizon is not quotable (bootstrap UNRELIABLE) |
| **H2** multi-source fusion adds information | **not supported**: trial+publication features reduced AP (Δ −0.0053, unreliable); consistent with the earlier annual-publication ablation |
| **H3** firm heterogeneity | **descriptive only**: 3 firms with ≥10 positives (Abbott +0.192, B. Braun +0.397, Medtronic +0.286); deep-case vs auxiliary −0.038 (CI −0.168…+0.093); Kendall τ −0.333 (n=3) |
| **H4** technology-domain heterogeneity | **hypothesis only**: orthopedics +0.342 / diabetes +0.308 / neuroscience +0.144 vs monitoring −0.077 / IVD −0.099; orthopedics−specialty +0.335 (CI −0.010…+0.634) does not exclude zero |
| **H5** earlier warning trades against reliability | **quantified**: recall 0.072→0.359 as precision 0.206→0.073 over alert budgets 1 %→20 %; 56–85 of 94 entries are silently missed |
| programme's confirmed decision rule (D-043) | stands: two-quarter confirmation window, precision 0.914–0.917; unaffected by this round |
| prospective calibration | **zero**: corrected set matures 2027-Q3…2028-Q1 |

## 4. Experiments run this round

| id | what | artifact |
|---|---|---|
| `hist_v1/panel` | full-history panel builder + entity/track/date audits | `experiments/hist_v1/build_panel.py`, `audits.json`, `manifest.json` |
| `hist_v1/primary` | R_adj, h=8 walk-forward, 30 origins, M1A/B/C + baselines + bootstrap + permutation | `results.json` §primary, §robustness |
| `hist_v1/secondary` | R_full and h=4 cells | `results.json` §secondary |
| `hist_v1/fusion` | feature set D on 2016+ origins | `results.json` §fusion_h2 |
| `hist_v1/lead-time` | 1/5/10/20 % alert-budget frontier, missed entries | `results.json` §lead_time |
| `hist_v1/case-studies` | five-firm entry timelines, descriptive | `five_firm_timeline.json`, `FIVE_FIRM_TIMELINE.md` |
| `hist_v1/verification` | 155 checks report vs artifacts; 43 unit tests; leak replay | `verify_report_numbers.py`, `tests/test_hist_eval.py` |
| `audit/record` | independent verification of 33 claim rows + clean-clone reproducibility | `research/audits/initial_research_audit.md` |
| `audit/prospective` | found the forecast window-start defect; corrected set re-registered | D-075, R156 |
| `audit/rolling-origin` | fixed the date-type crash; reproduction verified | D-076, R157 |

## 5. Failed, negative or unsatisfied results (not hidden)

1. **No advantage over the two-way exposure baseline B3** (H-3): the incremental value of the time-varying features is
   not established, even though the pre-registered primary comparison (vs B1) is supported.
2. **The primary result is marginal**: lower CI bound 0.002; MDE 0.090 > observed 0.058.
3. **Fusion is negative** (H-7).
4. **Firm-momentum features are below persistence** (H-5 group A, Δ −0.0064).
5. **The 12-month horizon is not quotable** (bootstrap UNRELIABLE; 6 of 31 origins have zero positive test cells).
6. **The taxonomy costs 55.1 % of material events**; the protocol's product-code fallback rescued nothing.
7. **161 of 255 entry events are new-category entries**, excluded by the primary risk set by construction.
8. **A leak-audit defect voided this study's first full run** (H-13); the void result was not published.
9. **The 12 partially backfilled forecasts were a false "prospective" claim in four documents**; corrected, not
   excused (D-075).

## 6. Unfinished / blocked

| item | status | why |
|---|---|---|
| prospective calibration | **blocked on wall clock** | corrected set matures 2027-Q3…2028-Q1; zero matured |
| human adjudication of the 69 five-firm packets | **resolved by owner waiver (2026-11-03)** | the owner authorised the external AI review as the study's **final** Target B adjudication and waived human sign-off for this study (D-079/S-035). The labels remain `human_truth = false`; the human worksheet columns stay empty by decision, not by omission |
| patents lane | **blocked on access** | PatentsView 403; USPTO ODP needs a key |
| broad hiring lane | **structurally unavailable** for Dräger/Mindray/GEHC | archive coverage; see D-031 |
| a design that can beat B3 / new-category entries | **open work** | needs a coarser taxonomy, larger roster, or a new pre-registration |
| stale summary numbers in historical documents | **partially fixed** | `COMPLETION_REPORT.md` / `MISSION §10` / R155 are point-in-time records; `RESEARCH_STATE.md` (this file) is the live state of record |
| remaining audit defects | **open** | summary-number drift, gate self-dirtying, momentum multiplicity, dead evidence pointers (R19/R151), taxonomy stamp in frozen snapshots |

## 7. Next tasks (priority order)

1. **Run the frozen hist_v2 design**: the pre-registration is frozen (`research/protocols/hist_v2_preregistration.md`) and feasibility is measured (domain unit: **12.0 positives per origin** vs 6.0 in hist_v1; `experiments/hist_v2/feasibility.json`). Next round writes `build_domain_panel.py` and `eval.py` and reports M1−B1 plus the decisive M1−B3 against the pre-declared MDE ≤ 0.05 target.
2. **Resolve the entity-mapping limitation** for the 48 roster companies (current-group attribution; unaudited).
3. **Fix the remaining audit defects** (summary-number drift, round-end-writes-its-own-dirt, momentum multiplicity,
   taxonomy stamp, dead evidence pointers).
4. **Only then**: revisit advanced methods (this round shows the bottleneck is design/data, not model capacity).

## 8. Important commands

```bash
python -m medradar selftest                        # 1,117+ tests (1,074 base + 43 hist_v1)
python tools/round_end.py                          # completion gate; exit code is the claim
python tools/final_audit.py                        # re-derives four artifacts (needs data/)
python experiments/hist_v1/build_panel.py          # panel (deterministic; out/hist_v1/panel.json)
python experiments/hist_v1/eval.py --panel out/hist_v1/panel.json --out experiments/hist_v1/results.json --workers 12
python experiments/hist_v1/five_firm_timeline.py
python experiments/hist_v1/verify_report_numbers.py # 155 checks: REPORT numbers vs artifacts
python experiments/b068/maturate_forecasts.py      # only when the lane advances past 2027-Q3
```

## 9. Data sources and versions (this round)

| source | version / hash | rows used |
|---|---|---|
| `data/medradar.sqlite` | SHA-256 `445807ca…2c92` | openFDA 510(k) 176,466 (1976-07-15…2026-10-18); PMA 57,372 (1968-10-09…2026-10-16) |
| `data/research.sqlite` | SHA-256 `dd241bfe…71e0d` | 51-company roster; publication_counts 616 |
| `data/b040_device_trials.sqlite` | SHA-256 `46e51490…` | 2,663 device-trial events (fusion only) |
| `config/product_code_tracks.json` | 1,958 code→track entries | fallback (rescued 0) |
| `config/tracks_device.json` | 50 tracks (38 observed in `events.track_id`) | categories/domains |
| `config/hist_entity_aliases.json` | new, 21 Dräger + 10 Mindray exact strings | deep-case resolution |

## 10. How to check this state

`python tools/round_end.py` (gate), `python experiments/hist_v1/verify_report_numbers.py` (this round's numbers, 155
checks), `research/audits/initial_research_audit.md` (independent verification of the prior record), and
`research/RESULTS/README.md` rows R1–R167 (the full result index).

