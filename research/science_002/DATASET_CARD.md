# DATASET_CARD - SCIENCE-002 issuer-month panel

**Version:** 1.0, built 2026-11-14 from sources retrieved 2026-11-14.
**Licence of the sources:** SEC EDGAR and openFDA are US-government public data,
public domain in the United States; see `docs/governance/DATA_LICENSES.yaml` in the
repository and the source notes in `evidence/SOURCES.md`.

## 1. What is in the dataset

| table | rows | key | committed |
|---|---|---|---|
| `artifacts/universe.csv` | **48** | one SEC registrant | yes |
| `artifacts/entity_matches.csv` | **189** | (cik, applicant string) attribution | yes |
| `artifacts/entity_exclusions.csv` | **14** | excluded candidate registrant | yes |
| `artifacts/panel.csv` | **2,771** | (cik, month_end) | yes |
| `artifacts/experiment_results.json` | 1 | frozen experiment payload | yes |
| raw openFDA bulk | 176,625 510(k) records + 336,932 registration rows | - | **no** (URL + SHA-256 recorded) |
| raw SEC JSON | 62 submissions documents + 62 companyfacts documents | - | **no** (URL + SHA-256 recorded in the cache sidecars) |

The raw sources are not committed because of size (the 510(k) ZIP alone is
249,963,096 bytes). Every raw byte has a URL and a SHA-256 in
`artifacts/source_manifest.json`; re-running `cli.py fetch` reproduces them.

## 2. Population

**Candidate space.** 62 SEC registrants were investigated: registrants whose
normalised title (or an FDA owner/operator relation) could account for at least 8
cleared 510(k)s in 2015-01-01..2026-08-31.

**Final universe.** 48 registrants pass all four pre-declared inclusion rules
(SIC in the device set; >= 8 attributable clearances; XBRL R&D available; at least
one 8-K with a verified acceptance instant). 14 are excluded with a recorded
reason (see ENTITY_RESOLUTION.md section 5).

**Sector distribution (SEC SIC):** 3841 surgical/medical instruments **33** firms,
3845 electromedical **7**, 3842 orthopaedic **4**, 3844 X-ray **1**, 3843 dental
**1**, 3851 ophthalmic **1**, 3826 laboratory analytical **1** - exactly 48.

## 3. Panel geometry

| quantity | value |
|---|---|
| months per firm | 66 (2021-01 .. 2026-06) |
| firm-month rows | **2,771** |
| rows dropped for insufficient SEC coverage | **397** |
| rows with any missing R&D feature | **78** |
| complete-case rows used by the model ladder | **2,554** |
| train (month_end <= 2024-12-31) | **1,772** |
| holdout (month_end >= 2025-01-01) | **782** |
| firms represented in the holdout | **44** |
| firms with both classes in the holdout (used by the stratified AUC) | **31** |
| holdout prevalence | **53.1%** |
| train prevalence | **49.9%** |
| attributable cleared 510(k)s in 2015-2026 | **3,143** |

## 4. Outcome distribution - and why it matters

The 90-day clearance indicator is **saturated for large firms and empty for small
ones**. Holdout prevalence by firm ranges from 1.00 (SYK, MMSI, MDT, ISRG, GEHC,
BSX, CBLL) to 0.00 (STIM, MMM, LNSR, LMAT, IRIX, CLPT, BIO, ARAY). Fifteen of 46
holdout firms have a single class and therefore contribute nothing to a within-firm
ranking.

That is not a defect to be fixed by reshuffling the sample: it is the substantive
fact that FDA 510(k) clearance is a routine, firm-level process. It is also why the
primary statistic is firm-stratified rather than pooled, and why the pooled AUC
(0.83) is reported but never used as evidence of signal.

Two structural breaks are visible in the holdout and are documented rather than
removed:

* **MMM (3M)** has zero attributable clearances after 2024 because its device
  business was spun off into Solventum (SOLV), which is separately in the universe;
* **CBLL** (IPO 2021) and **SOLV** (spin-off 2023) have shorter SEC histories and
  therefore fewer usable months.

## 5. Feature availability

| family | share of total variance that is *within* firm |
|---|---|
| `rd_yoy` (R&D TTM growth) | **0.94** |
| `rd_growth_vol` | 0.50 |
| `rd_ttm_log` (R&D level) | **0.02** |
| `rd_to_sales` (R&D intensity) | **0.04** |
| `n_8k_90` | 0.79 |
| `clr_rate_365` | **0.09** |

Read this table before reading any within-firm result: the R&D *level* and
*intensity* are firm characteristics, not monthly signals. A firm-fixed-effects
model can only use their small within-firm variation, so **the within-firm test is
essentially a test of R&D growth timing** (`rd_yoy`), which is the scientifically
interesting part anyway. The history baseline `clr_rate_365` is likewise mostly a
firm characteristic, which is precisely why it is a strong *between-firm* predictor
and a weak *within-firm* one.

## 6. Known limitations (do not remove before citing)

1. **8.8% attribution coverage.** Only 3,143 of 35,680 cleared 510(k)s in the
   window are attributed to the 48 firms. The outcome series undercounts each
   group's regulatory activity, firm-specifically.
2. **2026 ownership snapshot.** Tier-B attribution uses the current FDA
   owner/operator map for the whole panel. Sensitivity S1 removes it.
3. **One chronological split.** 44 holdout firms; 31 enter the stratified statistic.
4. **Label saturation.** Prevalence 53% with 15 single-class firms; the effective
   within-firm sample is 31 firms, not 782 rows.
5. **Event != technology.** A 510(k) clearance is a permission, not a technical
   advance; some are for modified existing devices.
6. **SIC-based population.** Firms whose SEC SIC is outside the device set are
   excluded even when they are large device makers (Abbott is the clearest case).
7. **Day-granularity XBRL.** A fact filed on the last day of the month is treated
   as known at that month's end.
8. **No publication timestamp exists for FDA data.** The 30-day availability lag is
   a conservative stand-in, not a measurement (TIME_SEMANTICS.md section 3).

## 7. Ethical and legal notes

* No personal data. The FDA 510(k)/registration fields used here describe companies
  and establishments; the registration file also carries a US-agent contact block,
  which this study **does not read or store** (`fda.py` keeps only establishment
  name, owner/operator name, owner number, country and expiry).
* No paid, private or credentialled data source is used.
* No scraping beyond the two documented bulk exports and the SEC JSON APIs, all
  rate-limited and cached.
* The dataset is a research derivative of public records; it is not a medical,
  regulatory or investment decision tool. The openFDA disclaimer applies:
  *"Do not rely on openFDA to make decisions regarding medical care."*