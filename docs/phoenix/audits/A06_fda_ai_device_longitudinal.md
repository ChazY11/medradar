# A06 — FDA AI/ML medical-device longitudinal study (M6)

Audit of: **Lee Y-S, Youn B-Y. "Clinical Specialty Expansion of AI-Enabled and Machine Learning–Enabled
Medical Devices Authorized by the US Food and Drug Administration From 1995 to 2025: Longitudinal Content
Analysis." J Med Internet Res 2026;28:e103040.** doi:[10.2196/103040](https://doi.org/10.2196/103040)
· [PMC13505343](https://pmc.ncbi.nlm.nih.gov/articles/PMC13505343/)

| Field | Value |
|---|---|
| Name | Clinical Specialty Expansion of AI/ML-Enabled Medical Devices Authorized by FDA, 1995–2025 |
| Official URL | https://pmc.ncbi.nlm.nih.gov/articles/PMC13505343/ (DOI 10.2196/103040) |
| Type | Public paper (open-access journal article, JMIR) |
| Licence / terms | Article published open access by JMIR; PMC record carries the journal's open-access terms. Underlying FDA registry data are US-government public-domain records. Verified by reading the PMC full text; a formal licence string was not read off a licence block. |
| Code public? | **No.** No code-availability statement anywhere in the article. Analyses described only as "performed in Python (version 3.9) using the pandas, SciPy, and statsmodels libraries". |
| Data public? | **Yes.** Data-availability statement: raw data "publicly available at no cost" from the FDA AI-Enabled Medical Devices List, with device-level records via openFDA. |
| Access barrier | None: article and data both free, no registration. Multimedia Appendix 1 (Tables S1–S8) is a journal supplement; the per-panel (17×4) table needed to recompute Era-1 HHI is in Table S2 and was **not** retrieved. |
| GPU / paid needed | No GPU; no paid service. Ordinary CPU + pandas/statsmodels is sufficient. |
| Reproducibility status | **Method independently re-implemented and numerically cross-checked** against the paper's own printed statistics; the study itself was not re-run (the registry is a moving download, and the paper's analysis file was never published). |

---

## 1) What the source actually says

Unit of analysis, cohort and cut-off (Methods, Data Source):

> "The complete registry was downloaded on March 1, 2026, and the analysis was restricted to devices with a
> date of final decision on or before December 31, 2025 … The final analytic dataset consisted of 1430 devices"

> "The unit of analysis was the individual marketing authorization: each row in the registry corresponds to a
> unique submission number … Updated versions of a previously authorized device that received a new marketing
> authorization under a separate submission number were retained as distinct records"

Eras (Methods, Era Classification): Era 1 = Sep 1995–Dec 2015; Era 2 = 2016–2019; Era 3 = 2020–2022;
Era 4 = 2023–2025. Boundaries "specified a priori on the basis of these volume and milestone considerations
rather than to equalize interval length".

Specialty is a **regulatory** attribute, not a clinical one:

> "the term specialty denotes the FDA advisory committee panel designation, which is a regulatory
> classification and does not necessarily correspond to the clinical setting in which a device is ultimately
> deployed"

HHI definition (Methods, Statistical Analysis) — the sentence this whole audit turns on:

> "The Herfindahl-Hirschman Index (HHI), defined as the sum of squared specialty share fractions, was
> calculated for each era to quantify specialty concentration (range: 0-1; higher values indicate greater
> concentration), with 95% CIs obtained from 2000 bootstrap resamples."

> "The change in HHI from Era 3 to Era 4 was assessed by drawing 2000 independent bootstrap resamples of the
> device sets within each of the 2 eras, computing the difference in HHI for each pair of resamples, and
> calculating the 2-sided P value as twice the proportion of resampled differences less than or equal to zero."

Other tests (same section):

> "The Cochran-Armitage test assessed linear trends in the proportion of authorizations by specialty across
> eras, and a 2-proportion z-test compared the radiology share between Era 3 and Era 4. For the trend tests,
> the 4 eras were coded as equally spaced ordinal scores (1-4) in chronological order"

> "the result was therefore verified with a Monte Carlo permutation test (10,000 replicates)"

> "a multivariable logistic regression model was specified with binary specialty classification
> (nonradiology vs radiology) as the outcome and era and manufacturer type as predictors (reference categories:
> Era 1 and large incumbent). An era-by-manufacturer interaction term was added to a second model"

Small-sample handling (Methods + Limitations):

> "51 of the 68 cells had expected counts below 5, violating the conventional rule of thumb" → Monte Carlo
> permutation check; a Firth penalized logistic regression "to address potential small-sample bias arising from
> the small technology-company category (5 manufacturers, 13 devices)"; manufacturer-level cluster-robust SEs
> (576 clusters); Wilson CIs in Figure 3B.

Reported results (Table 1, Figure 3): radiology share 35.7% → 62.1% → 85.5% → 77.5%; HHI 0.181 → 0.427 →
0.738 → 0.612; Era 3→4 radiology decline 7.9 pp, "2-proportion z test; P=.001"; Era 3→4 HHI fall "bootstrap
P<.001"; χ²₄₈=328.0, Cramér V=0.28. Cochran-Armitage for radiology reported as Z=+5.30, Bonferroni-adjusted
P<.001. Era-4 radiology 95% CI 74.5%–80.3%.

Authors' own bound on interpretation:

> "authorization is not adoption" … "this study characterizes regulatory authorization patterns, not clinical
> implementation"

## 2) What is NOT disclosed

- **The analysis code** — absent. No repository, no Zenodo, no appendix listing script logic.
- **The exact bootstrap implementation**: whether resampling is over devices (multinomial) or over specialty
  cells; whether the two era resamples are independent (they say "independent") and what RNG/seeds. My
  implementation assumes independent device-level resampling.
- **Whether HHI was computed over all 17 panels or over the pooled 9-row table** shown in Table 1. This is not
  cosmetic — see §5, where it is the one published HHI number that does not reproduce.
- **The logistic regression coefficients/SEs** (only ORs with CIs are printed), the fitted Firth estimates, and
  the exact covariate coding for the interaction.
- **Manufacturer classification for lower-volume firms** — the authors state this is a limitation: "classification
  of lower-volume manufacturers as start-ups versus SMEs relied on founding year and naming conventions for the
  large number of single-device companies".
- **Table S2 (17×4 panel counts)**, which is the missing input needed to settle the Era-1 HHI question.

## 3) Method extraction (precise enough to re-implement)

```
Dataset
  rows   : one row per FDA marketing authorisation (submission number), AI/ML-enabled devices
  fields : final decision date, submission number, device name, company, advisory panel, primary product code,
           pathway (510(k) / De Novo / PMA)
  filters: final decision <= cutoff date; no dedup of device families; no other exclusions
  eras   : E1 1995-09-29..2015-12-31, E2 2016..2019, E3 2020..2022, E4 2023..2025

HHI (primary concentration index)
  base      : authorisations within an era, partitioned by advisory-committee panel  <-- NOT firms, NOT product codes
  shares    : s_g = n_g / n_era          (g = specialty, n_era = sum over g)
  index     : HHI = sum_g s_g^2          range (1/G, 1]; 1 = one specialty only
  inference : 2000 bootstrap resamples of the device set within each era -> percentile 95% CI
  change    : independent resamples per era, diff = HHI(E4) - HHI(E3);
              paper's rule: 2 * P(diff <= 0) with the difference taken as (earlier - later),
              i.e. written for a decline; it cannot certify an increase.

Trend tests
  Cochran-Armitage : per specialty, success = devices in that panel, total = devices in era,
                     scores = 1..4 (equally spaced eras); Z from the standard CA variance;
                     family of 17 panels -> Bonferroni x17
  2-proportion z   : radiology share E3 vs E4, pooled-variance z, two-sided
  Wilson CI        : binomial proportion CIs (Figure 3B), no continuity correction implied
  chi-square       : Pearson on 17x4 with Cramer's V; because 51/68 cells have expected <5,
                     verify with margin-conditioned Monte Carlo permutation (10,000 reps)

Manufacturer model
  outcome    : nonradiology (1) vs radiology (0)
  predictors : era (ref E1), manufacturer type (ref large incumbent), interaction term
  hierarchy  : technology company > large incumbent (>1000 employees AND founded <2000)
               > start-up (founded >=2010 and pre-IPO/early) > SME (11-999 employees, residual)
  sensitivities: cluster-robust SEs at manufacturer level; continuous authorization year;
                 Firth penalised logistic regression
```

Base-of-shares, stated unambiguously: **shares are of authorisations by specialty within an era**. The paper does
*not* compute a firm-level HHI, a product-code HHI, or an HHI of authorisations over manufacturers — even though
the implication it draws ("measurable diversification") would be sharpened by them.

## 4) Data requirements, and whether that data exists in a medical-device regulatory setting

Required: (a) authorisation records with decision dates, (b) one categorical specialty per record, (c) optional
firm identifier and firm attributes. All three exist in the US regulatory record and are free.

Measured against MedRadar's own store (read-only profile, `data/medradar.sqlite`, 2026-11-08):

| Need | MedRadar column | Observed |
|---|---|---|
| authorisation events | `events(source, kind, event_date)` | 375,378 events; `openfda_device_510k` 176,466; `openfda_device_pma` 57,372; date range 1966-12-14 → 2026-10-30 |
| specialty (panel) | `product_codes.specialty` | 7,097 product-code rows; panels present include Radiology-adjacent set: Gastroenterology/Urology 564, General/Plastic Surgery 554, Clinical Chemistry 528, Microbiology 511, Hematology 387, Cardiovascular 349, Dental 329, Ophthalmic 310, Orthopedic 278, … |
| product code | `events.product_code` | 5,624 distinct codes on events |
| firm | `events.company_key`, `companies` | 89 distinct `company_key` (narrow universe — not the paper's 576 manufacturers) |
| technology track | `events.track_id`, `tracks` | 60 distinct tracks |

Gaps versus M6: (i) MedRadar has **no De Novo event kind** (only 510(k), PMA, recall, trial, 8-K, drug approval),
so pathway composition cannot be replicated exactly; (ii) there is **no AI/ML flag** — the paper's cohort is the
FDA AI-enabled device list, which MedRadar would have to ingest as a separate source; (iii) firm coverage is
partial (89 keys vs 576 manufacturers), so the manufacturer-type model is not currently estimable inside MedRadar.

## 5) My independent implementation and its self-test result

Files: `experiments/phoenix/external/methods/hhi.py`, `era_stats.py`, `selftest_synthetic.py`
(no original code existed to copy; written from the Methods text above).

`python selftest_synthetic.py` → **56/56 checks passed** (exit 0). This proves the implementations run and are
arithmetically correct on synthetic data. Separately, where the paper prints both its inputs and its outputs, the
formulas were cross-checked against its own printed values (this validates the *formulas*, not the study):

| Cross-check | Implementation | Paper | Verdict |
|---|---|---|---|
| HHI Era 2 from Table 1 counts | 0.4325 | 0.427 | reproduces (Δ+0.0055) |
| HHI Era 3 | 0.7381 | 0.738 | reproduces (Δ+0.0001) |
| HHI Era 4 | 0.6122 | 0.612 | reproduces (Δ+0.0002) |
| **HHI Era 1** | **0.2234** | **0.181** | **does NOT reproduce** |
| Wilson 95% CI, radiology Era 4 (614/792) | 74.49%–80.30% | 74.5%–80.3% | reproduces exactly |
| 2-proportion z, E3 vs E4 radiology | z=-3.267, p=0.0011 | P=.001 | reproduces |
| Cochran-Armitage Z, radiology | Z=+5.300 | Z=+5.30 | reproduces exactly |
| Bootstrap decline test (planted synthetic decline) | p<0.001, CI excludes 0 | — | behaves correctly |
| No-change null (synthetic) | p=0.81 | — | does not over-flag |

**The Era-1 divergence is a real, reportable finding, not an implementation error.** With n=42 and a pooled
"Other (n=9 specialties)" row of 10 devices, the pooled table cannot give 0.181: pooling *raises* HHI because the
10 devices are merged into one share (0.238²) instead of being split across nine shares. Splitting that bucket
9 ways (2,2,1,1,1,1,1,1) gives HHI 0.1746 — i.e. the published 0.181 is consistent with a 17-panel
computation, while Eras 2–4 are consistent with the pooled table (where the difference is below 3-dp rounding).
`hhi.share_base_sensitivity()` exists to make exactly this base-of-shares artefact measurable rather than hidden.
Also documented in code: the paper's two-sided bootstrap rule is direction-dependent and cannot certify a HHI
*increase*; `p_symmetric` is supplied alongside `p_paper_rule_decline`.

What was **not** done and is not claimed: no re-run of the study, no reproduction of the 1430-device cohort, no
manufacturer logistic regression on real data.

## 6) Applicability to MedRadar

This is the only one of the four audited methods that is directly implementable on data MedRadar already holds,
and it is the only one where I recommend adoption.

1. **Concentration/diversification monitor.** `hhi.py` + `era_stats.py` can be pointed at
   `events ⋈ product_codes.specialty` (or `.track_id`) for any window/era split, producing per-period HHI with
   bootstrap CIs and a change test. Directly answers "is MedRadar's technology-track mix concentrating or
   diversifying" — the exact question M6 asks about FDA authorisations.
2. **Trend discipline worth copying.** Equal-spaced era scores, Bonferroni across all panels, a permutation
   check when expected counts are small, Wilson rather than Wald intervals at small n.
3. **Era boundaries as a design artefact.** M6 chooses volume/milestone-based eras and then states the choice
   as a priori. MedRadar needs its own pre-registered boundary rule for any era-based claim, or the result is
   an artefact of where the analyst cut.
4. **Firm-level extension M6 did not do.** Because MedRadar has `company_key`, `events.product_code` and
   `tracks`, a *firm-level* HHI (authorisations per manufacturer) and a per-track firm-count concentration are
   both cheap. That is a genuine addition, not a replication.
5. **What must change.** Use `specialty` only where non-null (899 product codes are `Unknown`), keep `as_of` /
   `available_at` semantics so that "era" is defined by decision date and not by ingestion date, and treat the
   unit (authorisation, not product) explicitly — M6's own limitation #6.

## 7) Limitations, bias and leakage risks

- **Right-censoring / moving registry.** The registry is a live download; a "complete calendar-year total" claim
  is only valid relative to a stated download date. MedRadar's `as_of`/`available_at` fields already encode this
  discipline; any M6-style study must carry the same.
- **Unit inflation.** Authorisations, not products: multiple submissions per product family inflate counts and
  induce within-firm correlation. M6 patches the regression with cluster-robust SEs but its *descriptive* counts
  and shares remain authorisation-based — the same caveat applies to any HHI MedRadar computes.
- **Classification leakage.** Specialty comes from a regulatory panel, not from the intended clinical use; the
  paper concedes this. Mapping panel → "specialty growth" is a category error risk.
- **Small-n instability is the dominant threat for Era 1.** HHI at n=42 with a pooled small-category bucket is
  base-sensitive by ±0.05, which is larger than the Era 3→Era 4 change M6 headlines (−0.126). Any MedRadar claim
  on a small period must report k (number of categories), n, and a base-sensitivity figure.
- **Multiple comparisons.** 17 panels × 4 eras invites false positives; M6 corrects with Bonferroni (conservative,
  ignores correlation between shares). MedRadar should prefer a proper compositional method (e.g. Dirichlet /
  log-ratio) if it wants per-track inference.
- **No causal content.** "Diversification associated with start-ups" is an association from a model with a
  13-device cell; M6 says so itself ("highly imprecise"). Nothing here supports forecasting from firm type.
- **Leakage to avoid in MedRadar.** Era assignment must use the event's decision date (`event_date`), never
  `first_seen_at`/`fetched_at`; and bootstrap resampling must resample the unit actually analysed.

## 8) Decision

**ADOPT** — for the concentration/trend engine, with the adaptations in §6.

Reasoning: the HHI definition is stated exactly and unambiguously ("sum of squared specialty share fractions"
over authorisations by specialty per era); the accompanying tests are standard and fully specified; my
independent implementation reproduces four of the paper's five printed statistics exactly and reproduces the
fifth once the category granularity is disaggregated; the required data is already present in MedRadar's store
at meaningful scale; and no licence, paywall, or compute barrier applies. The one thing I explicitly do **not**
adopt is the paper's HHI *values* as a benchmark — its Era-1 value is base-sensitive and its cohort (AI/ML
devices only) is not MedRadar's cohort.

## 9) Open questions

1. Was HHI computed over all 17 panels or the pooled 9-row table for Era 1? (Table S2 would settle it; not retrieved.)
2. Does the bootstrap resample devices (multinomial) or specialty cells, and are the two era resamples truly
   independent given that Era 4 overlaps no Era 3 device? (Code not published.)
3. What exactly is the Firth/penalised estimate for the technology-company OR, and how wide does it become?
4. Is the Era 3→4 "decline" robust to using product families rather than authorisations as the unit?
5. Would a firm-level HHI reverse any of the conclusions (the paper never computes one)?
6. Is `product_codes.specialty` in MedRadar identical in provenance to the FDA registry's advisory-panel field,
   or is it a derived/normalised mapping? (Mapping provenance not asserted in the inventory read.)

## Evidence paths

- `experiments/phoenix/external/methods/hhi.py` — HHI, bootstrap CI, decline test, share-base sensitivity
- `experiments/phoenix/external/methods/era_stats.py` — Cochran-Armitage, 2-prop z, Wilson, χ²+permutation, Bonferroni
- `experiments/phoenix/external/methods/selftest_synthetic.py` — 56 checks, incl. the cross-checks in §5
- `experiments/phoenix/external/methods/evidence.json` — machine-readable verification record
- `experiments/phoenix/external/methods_audit_summary.json` — all four methods, one record each

## Citations

- Lee Y-S, Youn B-Y. J Med Internet Res 2026;28:e103040. https://doi.org/10.2196/103040 ·
  https://pmc.ncbi.nlm.nih.gov/articles/PMC13505343/
- FDA AI-Enabled Medical Devices list (data source, free): referenced by the paper via openFDA endpoints.
