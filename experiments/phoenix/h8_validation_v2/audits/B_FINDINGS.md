# Audit B — Historical risk set / point-in-time eligible universe (PHOENIX-002 H8 validation)

Independent audit of the PHOENIX-001 v1 **T-TRACK** and **T-CELL** risk sets.

* Worktree: `D:\DEPPSKK\worktrees\phoenix002` (branch `research/phoenix-002-h8-validation`)
* DB (read-only, `mode=ro&immutable=1`): `data/medradar.sqlite`,
  SHA-256 `445807CAB60DF66E0F0853C973AAF0DAE6065E72B6C9807D5DD5265097002C92` — **matches the frozen
  value**, `pragma integrity_check = ok`, 1,368,469,504 bytes, 375,378 events.
* Command (single runnable command, ~25 s, writes `b_riskset.json` next to itself):
  ```
  python experiments/phoenix/h8_validation_v2/audits/b_riskset.py
  ```
* Reproducibility check: the T-TRACK panel rebuilt from the DB is **bit-identical** to
  `hypotheses/track/cache/track_panel_L090.pkl` (4,904 rows × 59 tracks,
  `max_abs_dev = 0.0` on `n_device / f_n_device / y / f_n_device_sum8 / f_n_device_cum`), and the
  T-CELL panel rebuilt from the DB reproduces `cell/cache/panel_meta.json` **exactly**
  (67,084 rows / 13,205 positives / prevalence 19.6843% / 1,096 cells / 89 companies / 59 tracks).

**Point-in-time rule used everywhere below.**
Feature clock = `available_at + 90 days` (the frozen injected lag; for every 510k/pma/trial/recall
row in the window `available_at == event_date`, so the lag is the only publication delay in the data).
A unit (`track_id`, or `(company_key, track_id)`) is **PIT-eligible at origin quarter q iff at least
one of its events has feature-clock quarter ≤ q**. Origins are decided at the end of q (the frozen
harness convention). This uses only events whose *public availability* was ≤ end of q; it never looks
at q+1 onward. v1 eligibility, by contrast, is "first line of the panel exists from the unit's first
**event** quarter"; the 90-day lag is applied to feature *values* only, never to universe membership.

---

## TL;DR — blunt verdict

1. The v1 risk sets are **not PIT-clean**, but the PIT violation is small and mechanical: the
   90-day availability lag is not applied to universe entry, so every unit's **first observed row**
   (59 T-TRACK rows = 1.20%; 1,086 T-CELL rows = 1.62%) is evaluated with zero publicly-available
   history. At 2004Q1 v1 evaluates **38 track units and 109 cell units, while PIT-eligible = 0**.
2. The **far larger defect is the universe itself, not the clock**: 21 of 59 tracks and 682 of
   1,096 cells (62.2%) contain **zero device events in the entire database** and can never be a
   device-label positive. They are **34.7% of T-TRACK rows / 38.2% of its negative pool** and
   **58.6% of T-CELL rows / 73.0% of its negative pool**. At most **37 tracks** (36 of them actually
   contain a positive) and **414 cells** are *attainable* units; attainable-only prevalence is
   15.15% (on the 36 positive tracks) / 47.55% (cells) versus the published pooled 9.54% / 19.68%.
3. Eligibility is **not decided by future events** in the narrow sense tested by item 5: v1 creates
   no row before a unit's first event (0 rows, 0 negatives), so a PIT rule adds no exclusions there.
   The real look-ahead is *unavoidable hindsight in universe construction*: which units are even
   able to be positive is known only after 2026, and v1 evaluates a risk set in which the majority
   of units can never be positive. Cell prevalence falls monotonically from **52.1% (2004) to 15.8%
   (2025)** partly because of this growing, permanently-negative universe.
4. Company attribution is a **time- and track-dependent filter**, not a random sample: v1 keeps
   **20.80%** of all DB events (78,074/375,378); the attributed share of all in-window device events
   rises from **18.5% (2004) to 36.7% (2017)** then falls to **29.7% (2025)** (early mean 24.2% vs
   late mean 31.9%, Spearman ρ = 0.357, p = 0.102, OLS +0.38 pp/yr — non-monotone). Per track the
   attributed share ranges from **0.24% (aesthetics, 4/1,635) to 93.8% (cardiac_rhythm,
   11,232/11,969)** — the device-positive supply is structurally concentrated.
5. The track taxonomy is a **2026 snapshot back-filled onto 1976–2026 events** and cannot be
   de-biased from this DB. Evidence is unambiguous about *when it was made* (all 60 tracks and all
   7,097 product codes carry `updated_at = 2026-10-30`), and about *how completely it covers the
   past*: 38/38 device tracks already have tracked device events before 2004Q1, 18/38 first appear
   in the single quarter 1976Q3, and 92.5% of tracked device events get their track from the current
   `product_codes` table with 100% agreement. What a contemporaneous analyst would have called these
   events is **not measurable** (no taxonomy history, no per-event assignment timestamp, keyword
   rules not stored).

---

## 1. T-TRACK v1 panel composition — 38 / 21 / 59, 60 tracks in table

Panel: 4,904 rows, 59 tracks, 4,255 labelled rows (v1 growth label `y`), 406 positives,
pooled prevalence 9.5417%. The `tracks` table has **60** rows; `t_radiopharma` is the only track
present in the table and absent from the panel (it has no event with both `company_key` and
`track_id`).

| group | tracks | panel rows | labelled rows | positives (growth y) | negatives | mean y |
|---|---|---|---|---|---|---|
| device tracks (≥1 510k/pma event ever, whole DB) | **38** | 3,204 | 2,786 | **406** | 2,380 | 14.57% |
| `t_*` trial-only tracks (zero device events ever) | **21** | 1,700 | 1,469 | **0** | 1,469 | 0.00% |
| **all** | **59** | 4,904 | 4,255 | 406 | 3,849 | 9.54% |

* 38 device tracks = exactly the 38 non-`t_` tracks; 21 `t_*` tracks in the panel = exactly the 21
  `t_*` rows of the tracks table that have attributed events (table has 22 `t_*` ids).
* Stronger attainability bound: 22 tracks **cannot reach the growth label's `min_events = 3`**
  (max 4Q device count < 3 in the whole panel): the 21 `t_*` tracks **plus `aesthetics`**.
  Those 22 tracks contribute 1,742 panel rows / 1,500 labelled rows / **0 positives**.
  The attainable T-TRACK risk set is therefore **at most 37 tracks**, not 59, and empirically only
  **36 tracks contain a positive** (all 406 positives over 2,680 labelled rows = 15.15% prevalence
  on those rows); the 23 tracks with zero positives are the 21 `t_*` tracks plus `aesthetics` and
  **`ortho_joint`** (a real device track whose growth label never fires in the panel).

## 2. T-CELL v1 universe — 1,116 / 411 / 1,096

Cell universe bookkeeping (the three numbers are different universes and must not be conflated):

| quantity | count |
|---|---|
| raw attributed `(company_key, track_id)` pairs in `events` (2004–2026 window) | **1,116** |
| cells in the joint label panel (before trim to 2025Q2) | 1,114 |
| cells in the evaluated v1 panel (origins ≤ 2025Q2) | **1,096** |
| cells with ≥1 device event **at an origin quarter** (label clock) | **411** |
| cells that can ever be hit by the forward label (device event in a label quarter ≤ 2026Q2) | 414 |
| cells that can **never** be positive (1,096 − 414) | **682** |
| cells ever device DB-wide (any date) | 445 |
| cells never device DB-wide (of the 1,096 panel cells) | 651 |
| cells in `t_*` tracks | **552** (50.36% of cells) |

The stated "1,116 cells in panel" is the **pre-panel raw universe**: the actual evaluated panel has
1,096 cells (−20). 411 is the count of cells with a device event in an origin quarter; 414 is the
label-relevant count (3 cells have device events only in the 2025Q3–2026Q2 forward windows, so they
can be positives at the last origins but never have a device event in an origin quarter).
Evaluation of the panel: 67,084 rows, 13,205 positives, prevalence 19.6843%, 53,879 negatives.

| group | cells | panel rows | positives | negatives | mean y |
|---|---|---|---|---|---|
| cells ever device (label-relevant, 414) | **414** | 27,771 (41.40%) | **13,205 (100%)** | 14,566 | 47.55% |
| cells never device (682) | **682** | 39,313 (58.60%) | **0** | 39,313 | 0.00% |
| cells in `t_*` tracks | 552 | 33,647 (50.16%) | 0 | 33,647 | 0.00% |
| all | 1,096 | 67,084 | 13,205 | 53,879 | 19.68% |

All 13,205 positives live in 414 of 1,096 cells (37.8%). The other 682 cells (62.2%) exist only as
negatives. `t_*` cells alone are 50.2% of all rows and 62.4% of the negative pool.

## 3. Structurally impossible units: rows and negative-pool share

A unit with **zero device events in the entire database** can never be a device-label positive
(T-TRACK growth label additionally needs ≥3 forward device events; T-CELL any-device label needs 1).

| panel | impossible units | panel rows (share) | labelled rows | positives | negatives (share of neg. pool) |
|---|---|---|---|---|---|
| T-TRACK | 21 tracks | 1,700 (**34.67%**) | 1,469 | 0 | 1,469 (**38.17%** of 3,849) |
| T-CELL | 682 cells | 39,313 (**58.60%**) | 39,313 | 0 | 39,313 (**72.97%** of 53,879) |

Related and larger: **device-naive negatives** — rows where the cell has had zero device events up to
and including the origin — are **40,441 rows = 75.06% of the entire T-CELL negative pool**
(39,313 from never-device cells + 1,128 from cells that only acquire their first device event later).
In other words, three quarters of the T-CELL negative class is "the cell had no device history yet",
and 58% of all cell rows are units that will *never* have any.

Consequence for the metric: pooled prevalence 19.68% is not the prevalence of the task the model is
scored on. On the attainable universe (414 cells) it is **47.55%**; on attainable tracks (37) it is
**14.57%** vs pooled 9.54%. Negatives are dominated by units for which the outcome is structurally
impossible, so AP/precision are measured mostly on unattainable candidates.

## 4. Point-in-time eligible universe (feature clock = `available_at` + 90 d)

For each origin q ∈ 2004Q1…2025Q2, eligible = units with min(feature quarter) ≤ q. The first-event
row of every unit is **not** eligible because the 90-day lag pushes its first availability one quarter
later (T-TRACK: delay is exactly 1 quarter for 59/59 tracks; T-CELL: 1 quarter for 1,086 cells,
0 quarters for 10 cells whose first event falls in the first ~2 days of a quarter).

| panel | units in panel | PIT units min / median / max | v1 rows NOT PIT-eligible | delay per unit |
|---|---|---|---|---|
| T-TRACK | 59 | **0 / 57 / 59** | **59 rows (1.20%)** | 1 quarter (59/59) |
| T-CELL | 1,096 | **0 / 841.5 / 1,093** | **1,086 rows (1.62%)** | 1q (1,086) / 0q (10) |

Per-origin comparison (v1 units with a row at q vs PIT-eligible units at q):

| origin | T-TRACK v1 units | T-TRACK PIT | T-TRACK v1 rows | T-CELL v1 units | T-CELL PIT | T-CELL v1 rows |
|---|---|---|---|---|---|---|
| 2004Q1 | 38 | **0** | 38 | 109 | **0** | 109 |
| 2010Q1 | 57 | 57 | 57 | 663 | 651 | 663 |
| 2014Q1 | 57 | 57 | 57 | 827 | 818 | 827 |
| 2020Q1 | 59 | 59 | 59 | 978 | 973 | 978 |
| 2024Q2 | 59 | 59 | 59 | 1,067 | 1,061 | 1,067 |

Because the delay is one quarter for almost every unit, the PIT violation is exactly **one row per
unit** — but that row is a *zero-information row*: all lagged features are 0 there, so v1 feeds the
model a "no history yet" observation and counts it in validation/training as if it were a normal
zero-history negative. 2004Q1 is the extreme case: the whole first origin (38 track rows / 109 cell
rows) is evaluated with **no PIT-eligible unit at all**.

## 5. Future-first company × track cells (> 2014Q1)

* **269 of 1,096 cells (24.5%)** first appear (any event) after 2014Q1.
* **98 cells (8.9%)** get their first **device** event after 2014Q1.
* v1 panel rows at origins **before a cell's first event: 0**; of those, negative rows: **0**.
  v1's `exposure_q ≥ 0` filter is causal in this narrow sense: a cell never appears before its own
  first event, so a PIT rule adds no exclusions there. Future-first cells therefore do **not**
  contaminate earlier origins with rows.
* However, v1 does include **1,352 rows (1,128 of them negatives)** for cells *before their first
  device event* (the cell exists via trial history). For the 98 cells whose first device event is
  after 2014Q1, **931 negative rows** precede their own first device event. Those rows are legitimate
  PIT negatives (the cell genuinely had no device history then); excluding them would require knowing
  the future, i.e. it is a **hindsight universe rule, not a PIT rule**. The defect they represent is
  the mixed-attainability universe of §3, not look-ahead.

## 6. Zero-history / emerging tracks

Trailing-8Q device count (`f_n_device_sum8`, feature clock, includes current quarter) == 0:

| stratum | rows | labelled | positives | mean y | tracks |
|---|---|---|---|---|---|
| all zero-history | **1,907 (38.89% of 4,904)** | 1,602 (37.65% of 4,255) | 5 | 0.312% | — |
| previously active, currently **dormant** (cum−sum8 > 0) | 126 | 110 | **3** | 2.73% | 7 |
| **never yet active** (cum == 0) | 1,781 | 1,492 | **2** | 0.134% | 24 have labelled rows |
| non-zero history | 2,997 | 2,653 | 401 | **15.11%** | — |

* The 2 positives in the never-yet-active stratum are the label's **burst artefact**: the growth
  label uses `forward_total ≥ 3 AND forward_rate ≥ 1.5 × trailing_mean`; when the trailing mean is 0
  the second condition is automatically satisfied, so a totally dormant/never-active track is labelled
  positive on its first device burst.
* The never-yet-active stratum is 1,781 rows, of which **1,700 rows are the 21 `t_*` tracks** (zero
  device activity for their whole lives, 1,469 labelled, 0 positives) and only 81 rows are device
  tracks' warm-up (23 labelled, 2 positives). So "emerging" is almost entirely a *permanently dead*
  stratum, not an emergence process.
* Zero-history rows are **41.49% of the T-TRACK negative pool**; their label rate is 0.312% versus
  15.11% for rows with device history. A model cannot learn from them and they swamp the negatives.

## 7. Company-attribution coverage (a data-structure / time-bias risk)

`load_events(require_company_track=True)` keeps only events with **both** `company_key` and
`track_id`.

Aggregate loss:
* v1 keeps **78,074 / 375,378 = 20.80%** of all DB events (the "~20.8%" figure is confirmed) and
  30.76% of in-window events (78,074 / 253,836).
* Device events (510k+pma), whole DB: **233,838**; with a track_id: 124,628; attributed: **46,509 =
  19.89%** of all device events (37.32% of tracked).
* Device events in the 2004–2026 window: **116,804**; attributed **37,062 = 31.73%** (47.67% of the
  77,749 tracked ones).
* **117,034 device events (50.1% of all device events)** lie before `PANEL_START=2004-01-01`; only
  9,447 of them are attributed. The window choice and the attribution filter together discard ~80%
  of the raw device record.

Per year (in-window device events; A = attributed/tracked, B = attributed/all):

| year | device ev. | tracked | attributed | B | A |
|---|---|---|---|---|---|
| 2004 | 3,997 | 2,209 | 740 | 18.51% | 33.50% |
| 2005 | 3,899 | 2,227 | 848 | 21.75% | 38.08% |
| 2006 | 4,291 | 2,510 | 1,117 | 26.03% | 44.50% |
| 2007 | 4,103 | 2,476 | 1,044 | 25.44% | 42.16% |
| 2008 | 4,544 | 3,012 | 1,324 | 29.14% | 43.96% |
| 2009 | 4,500 | 2,845 | 1,311 | 29.13% | 46.08% |
| 2010 | 4,652 | 3,038 | 1,534 | 32.98% | 50.49% |
| 2011 | 5,348 | 3,615 | 1,918 | 35.86% | 53.06% |
| 2012 | 5,546 | 3,825 | 2,000 | 36.06% | 52.29% |
| 2013 | 5,394 | 3,651 | 1,911 | 35.43% | 52.34% |
| 2014 | 5,687 | 3,832 | 1,976 | 34.75% | 51.57% |
| 2015 | 5,189 | 3,514 | 1,643 | 31.66% | 46.76% |
| 2016 | 5,520 | 3,869 | 2,009 | 36.39% | 51.93% |
| 2017 | 5,917 | 4,097 | 2,169 | **36.66% (max B)** | 52.94% |
| 2018 | 5,852 | 4,065 | 2,091 | 35.73% | 51.44% |
| 2019 | 5,556 | 3,778 | 1,893 | 34.07% | 50.11% |
| 2020 | 5,426 | 3,779 | 1,952 | 35.97% | 51.65% |
| 2021 | 5,227 | 3,430 | 1,700 | 32.52% | 49.56% |
| 2022 | 5,301 | 3,475 | 1,637 | 30.88% | 47.11% |
| 2023 | 5,531 | 3,754 | 1,603 | 28.98% | 42.70% |
| 2024 | 5,359 | 3,730 | 1,651 | 30.81% | 44.26% |
| 2025 | 5,447 | 3,822 | 1,619 | 29.72% | 42.36% |

Trend: **not monotone**. Early mean (2004–2008, B) = 24.18%, late mean (2019–2025) = 31.85%
(ratio 1.32); OLS +0.378 pp/year (B) and +0.262 pp/year (A); Spearman(year, B) ρ = 0.357,
p = 0.102; Spearman(year, A) ρ = 0.188, p = 0.402. The rate rises to a 2017 peak and then declines —
so attribution coverage is **unstable over calendar time**, which is exactly the time-bias risk: the
model's device-signal supply in 2004 rows is ~half of what it is in 2017 rows, and the decline after
2017 coincides with the cell risk set growing (more cells, fewer positives: cell prevalence 52.1% in
2004 → 15.8% in 2025; rows 720 → 4,291).

Per track (in-window, tracked device events, attributed / tracked / rate): median **28.05%**,
IQR 15.42%–58.77%, range **0.24%–93.84%**. Extremes: `aesthetics` 4/1,635 = 0.24%, `ent` 27/800 =
3.4%, `rehab_exo` 31/790 = 3.9%, `ivd_poct` 19/200 = 9.5%; vs `cardiac_rhythm` 11,232/11,969 =
93.84%, `neurostimulation` 1,988/2,167 = 91.7%, `structural_heart` 2,486/2,735 = 90.9%,
`surgical_robotics` 140/166 = 84.3%. The full 38-row table is in `b_riskset.json`
(`attribution_by_track`). Device positives are therefore supplied by a handful of cardiology/ortho
tracks; most tracks are effectively device-invisible.

## 8. Frozen current taxonomy back-filled onto historical events (anachronism)

What the DB *does* let us bound:

* **When the taxonomy was made**: `tracks` = 60 rows, `updated_at` = `2026-10-30T19:56:45Z` (38
  non-`t_` tracks) and `2026-10-30T19:19:19Z` (22 `t_*` tracks); `product_codes` = 7,097 rows, all
  `updated_at = 2026-10-30T19:02:40Z`. The whole taxonomy is a **single 2026-10-30 snapshot**, i.e.
  created at/after the end of the data, not maintained historically.
* **How far back it reaches**: 38/38 device tracks already contain tracked device events **before
  2004Q1** (earliest: `ophthalmology` 1971Q1; `ivd_immuno` 1976Q2); **18/38 tracks first appear in
  the single quarter 1976Q3** and 27/38 before 1977Q1 — a mass simultaneous first appearance at the
  start of the 510(k) archive, not a product-emergence process. 35/38 device tracks are active
  already in 2004Q1 (37/38 in 2010Q1–2025Q2). **46,879 pre-2004 device events (37.62% of all tracked
  device events) already carry a `track_id`.**
* **How the assignment is made**: 231,622 device events have a `product_code`, and 231,393 (99.9%)
  of those codes exist in `product_codes`; of the 115,329 events where the current
  `product_codes.track_id` is non-null, the event's `track_id` **equals the current table's value in
  100.0% of cases**. So the historical `track_id` is (at least for these 92.5% of tracked device
  events) a direct lookup against a table snapshotted on 2026-10-30. 9,022 tracked events have a
  product-code row whose `track_id` is NULL (5,139 of 7,097 product codes have NULL `track_id`) and
  277 have no product-code row — these were assigned by some other, **unstored** keyword/title rule.
* `t_*` tracks enter the panel between 2004Q1 and 2006Q4 (one at 2018Q2) — i.e. the trial-only
  taxonomy appears as a block at the start of the window, not through an observable entry process.

What **cannot** be measured from this DB (mark as untestable):
1. Whether an event dated 1976–2013 would have been assigned to the same track by a contemporaneous
   analyst. There is **no taxonomy version history** (`tracks` has exactly one row per track with one
   `updated_at`), no per-event assignment timestamp, and no assignment reason.
2. The counterfactual assignment of the 9,299 tracked events not explained by the current
   product-code table (9,022 NULL-`track_id` codes + 277 no row): their keyword rules are not stored.
3. Whether the 22 `t_*`/39 device tracks existed as concepts before 2026 — the category names are
   2026 labels.
4. Any "track emergence" claim: because the taxonomy is applied back to 1976 and 35/38 tracks are
   active at the first panel quarter, the DB cannot distinguish taxonomy coverage from real market
   emergence. Any apparent emergence in the panel is an artefact of the panel window and the
   taxonomy back-fill, not evidence of new technology tracks.
5. `available_at`: for 510k/pma/trial/recall rows `available_at == event_date` exactly (the 20,976
   string-level mismatches are all `8k_catalyst`, parsed timestamps identical, 0-day difference; 8k
   has zero `track_id` anyway), so the injected 90-day lag is the **only** representation of
   publication delay. True historical openFDA publication lag is not in the DB and cannot be
   reconstructed.

## 9. What a PHOENIX-002-era risk set must fix (from these numbers)

1. Apply the availability lag to **universe entry**, not only to feature values: drop each unit's
   first row (59 track rows / 1,086 cell rows) and never evaluate an origin with zero PIT-eligible
   units (2004Q1: 38/109 v1 rows, 0 eligible).
2. Report metrics on an **attainable universe** (≤37 tracks, of which 36 actually contain a
   positive; 414 cells) in addition to the v1 universe, and report the suppression explicitly
   (T-TRACK: 1,700 rows / 1,469 negatives = 34.7% / 38.2%; T-CELL: 39,313 / 72.97%). The published pooled prevalence understates attainable
   prevalence by 1.5× (tracks) and 2.4× (cells).
3. Stratify or exclude zero-history rows (38.9% of T-TRACK rows, 41.5% of its negative pool; 0.31%
   vs 15.11% label rate) and handle the growth label's 1.5×0 burst artefact.
4. Treat attribution coverage as a time-varying filter: report per-year and per-track attributed
   shares next to every metric; the 2004 rows carry ~half the attributed device signal of 2017 rows,
   and per-track rates span 0.24%–93.84%.
5. Treat taxonomy assignment as post-hoc: no result that depends on track identity as a *historical*
   concept is identifiable with this DB; at most it is a 2026 re-labelling of the past.

## Files

* `experiments/phoenix/h8_validation_v2/audits/b_riskset.py` — single runnable audit, prints every
  fact and writes the JSON.
* `experiments/phoenix/h8_validation_v2/audits/b_riskset.json` — full machine-readable facts,
  including per-origin tables (86 origins), the 38-track attribution table, and per-year counts.
* `experiments/phoenix/h8_validation_v2/audits/B_FINDINGS.md` — this document.
