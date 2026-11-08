# A_FINDINGS — Audit A: training-label maturity in the PHOENIX-001 walk-forward

**Verdict in one line: the v1 walk-forward violates the required maturity assertion in
every fold at every declared label delay (no purge / no embargo exists anywhere in
PHOENIX-001), the defect is real and quantifiable, and it inflates the published H8
*levels* by ≈0.005 AP without creating the H8 − B1 contrast.**

- Auditor: independent (Audit A), repo worktree `D:\DEPPSKK\worktrees\phoenix002`,
  branch `research/phoenix-002-h8-validation`
- Database: `data/medradar.sqlite`, SQLite URI `mode=ro&immutable=1`,
  SHA-256 `445807CAB60DF66E0F0853C973AAF0DAE6065E72B6C9807D5DD5265097002C92`
  (verified by the script; matches the frozen value in `phoenix_common.py:40`).
- Code audited (read only): `experiments/phoenix/common/phoenix_common.py`,
  `.../hypotheses/track/{track_common.py,run_track.py}`,
  `.../hypotheses/cell/{cell_common.py,run_cell.py}`, and the cached v1 panels
  `track/cache/track_panel_L{000,090,180}.pkl`.
- **Command used (single command, from the repo root, 58.6 s):**
  ```
  python experiments/phoenix/h8_validation_v2/audits/a_maturity.py
  ```
- Machine-readable results: `a_maturity.json` (all per-fold rows, violating origin
  lists, latest admissible origins, both deadline variants, full purged re-run).

---

## 1. Definitions and the executable assertion

| concept | definition used |
|---|---|
| origin | a prediction/row at quarter `q` (features at `q` may include events whose `available_at + injected lag` falls inside `q`) |
| decision time | **end of quarter `q`** (`Period.end_time`), as stated in `phoenix_common.py:359-363` |
| label | growth target and any_activity cell target both read device events with `event_date` in **`(q, q+4]`** (`add_forward_target`, `phoenix_common.py:234-276`) |
| label_observable_at | `end(q+4) + L days`, L ∈ {0, 90, 180} declared publication delay |
| **assertion** | `train_label_observable_at <= test_decision_time` |
| fold test_decision_time (primary) | end of the fold's **first** test origin (2014Q1 → 2014-03-31); the earliest instant at which the fold's single fitted model is used, so the binding deadline |
| fit-time variant (stricter) | end of the fold's **last** training quarter (e.g. 2013Q4 → 2013-12-31), the instant the training set is actually frozen |
| required purge | number of trailing training origin quarters whose `label_observable_at > decision_time` |
| leakage channel | training rows whose label window `(q,q+4]` contains ≥1 quarter **inside the fold's test period** |

`pc.walk_forward_folds(2014, 2025)` (`phoenix_common.py:453-477`) sets
`train_origins = (2004Q1, Y-1Q4)` and `test_origins = (YQ1, YQ4)`; the drivers use
**all** labelled rows in that range (`run_track.py:132-135`, `run_cell.py:51-53`).
A grep for `purge|embargo|maturity` in the v1 harness and both drivers returns
**nothing** — there is no purge, no embargo, no gap at the train/test boundary.

Assumptions are listed verbatim in `a_maturity.json → assumptions`; the material ones:
the end-of-quarter decision convention, `available_at == event_date` for every row
(so L is *declared*, never measured — see §7), training rows = the rows the v1 code
actually used (`y` not NaN), quarter-granular purge, and one model fitted per fold.

---

## 2. Finding A1 — TRACK level: the assertion fails in 11/11 executed folds

### Per-fold table (L090 panel; row counts are labels actually fed to the model)

`vLx` = number of labelled training rows whose label was not observable by the fold's
first test decision at delay `x`; `purge` = required trailing-quarter purge (same for
L=0/90/180 within a column set); `overlap` = rows whose label window contains test-period events.

| test year | train rows | vL0 | vL90 | vL180 | purge q (L0 / L90 / L180) | latest admissible origin (L090) | overlap rows | test rows scored |
|---:|---:|---:|---:|---:|:--:|:--|---:|---:|
| 2014 | 1,812 | 171 | 228 | 285 | 3 / 4 / 5 | 2012Q4 | 228 | 228 |
| 2015 | 2,040 | 171 | 228 | 285 | 3 / 4 / 5 | 2013Q4 | 228 | 228 |
| 2016 | 2,268 | 171 | 228 | 285 | 3 / 4 / 5 | 2014Q4 | 228 | 229 |
| 2017 | 2,497 | 172 | 229 | 286 | 3 / 4 / 5 | 2015Q4 | 229 | 232 |
| 2018 | 2,729 | 174 | 232 | 290 | 3 / 4 / 5 | 2016Q4 | 232 | 232 |
| 2019 | 2,961 | 174 | 232 | 290 | 3 / 4 / 5 | 2017Q4 | 232 | 232 |
| 2020 | 3,193 | 174 | 232 | 290 | 3 / 4 / 5 | 2018Q4 | 232 | 236 |
| 2021 | 3,429 | 177 | 236 | 294 | 3 / 4 / 5 | 2019Q4 | 236 | 236 |
| 2022 | 3,665 | 177 | 236 | 295 | 3 / 4 / 5 | 2020Q4 | 236 | 236 |
| 2023 | 3,901 | 177 | 236 | 295 | 3 / 4 / 5 | 2021Q4 | 236 | 236 |
| 2024 | 4,137 | 177 | 236 | 295 | 3 / 4 / 5 | 2022Q4 | 236 | **118** (truncated) |
| 2025 | 4,255 | 59 | 118 | 177 | 3 / 4 / 5 | 2023Q4 | 118 | **0 — fold silently skipped** |

**Which folds are affected:** all 11 folds the v1 code actually executed (2014–2024).
Fold 2025 is never executed (§4). No fold is clean.

### Aggregate (11 executed folds = 32,632 training-row-uses)

| L (days) | violating train rows | share | required purge | vs fit-time: rows | vs fit-time: purge |
|---:|---:|---:|:--:|---:|:--:|
| 0 | **1,915** | **5.87 %** | **3 quarters/fold** | 2,553 (7.82 %) | 4 q |
| 90 (headline) | **2,553** | **7.82 %** | **4 quarters/fold** | 3,190 (9.78 %) | 5 q |
| 180 | **3,190** | **9.78 %** | **5 quarters/fold** | 3,826 (11.72 %) | 6 q |

- The assertion FAILS at every L in every fold; "required purge" is uniform across folds
  because the expanding window always ends at `Y-1Q4` and the decision is always `YQ1`.
- Latest admissible training origin at the headline L=90 is `test_start − 5` (2012Q4 for
  the 2014 fold; 2022Q4 for the 2024 fold); v1 trains through `test_start − 1`.
- At the stricter fit-time deadline (model really frozen at `end(Y-1Q4)`) the L=90 purge
  is 5 quarters / 3,190 rows. PHOENIX-002's frozen rule
  (`h8_validation_v2/protocol.py:73-79`, `purge = HORIZON + ceil(L/91) + 1 = 6`) is one
  quarter stricter still and corresponds to the 6-quarter / 3,826-row case above — i.e.
  the v2 rule is **sufficient, not minimal**, for the assertion audited here.

### The actual leakage channel (counts asked for by the brief)

- **2,553 of 32,632 training-row-uses (7.82 %) at the headline setup have labels that
  depend on events inside the fold's test period** (e.g. fold 2014 trains on origins
  2013Q1–2013Q4, whose labels read 2013Q2–2015Q1 event-clock device events).
- Per-fold share falls monotonically with the expanding window: **12.58 %** (2014) down
  to **5.70 %** (2024) — the leak is largest exactly where the test blocks are earliest.
- At L=0 the minimum decision-time purge (3 quarters) **does not eliminate the channel**:
  638 of those 2,553 rows (origins whose 4-quarter window ends *exactly* at the decision
  instant, i.e. `q = test_start − 4`) still contain test-period events. At L=90 the
  maturity purge and the no-overlap purge coincide (2,553 rows both).

---

## 3. Finding A2 — CELL level (T-CELL): same defect, slightly larger share

Cell panel rebuilt in memory from the frozen harness (no files written): 67,084 rows,
67,084 labelled (y NaN = 0), 1,096 cells, origins 2004Q1–2025Q2; fold train/test row
counts reproduce the archived v1 log (`cell/evidence/02_run_cell_L090.log`) **exactly**
for all 12 folds, so this is the same panel v1 used.

| L (days) | violating train rows / total | share | required purge | test-period events in train labels | share |
|---:|---:|---:|:--:|---:|---:|
| 0 | 34,388 / 514,149 | 6.69 % | 3 q/fold | 45,704 | 8.89 % |
| 90 | **45,704 / 514,149** | **8.89 %** | **4 q/fold** | 45,704 | 8.89 % |
| 180 | 56,932 / 514,149 | 11.07 % | 5 q/fold | 45,704 | 8.89 % |

Per-fold L=90 violations: 3,227 | 3,364 | 3,498 | 3,618 | 3,727 | 3,801 | 3,868 | 3,950 |
4,037 | 4,121 | 4,202 | 4,291 (2014…2025); shares 14.39 % → 6.61 %. All **12/12** folds
affected, including 2025 (which v1 does execute at cell level). Latest admissible origin
for fold 2014 is 2012Q4 (L=90) vs v1's 2013Q4. **The cell walk-forward has the identical
defect** — by construction, since both drivers call the same `walk_forward_folds` /
`split_by_origin` with no purge.

---

## 4. Finding A3 — second maturity problem: the cached v1 TRACK panel truncates labels

Measured on `track_panel_L090.pkl` (identical for L000/L180; label column is
bit-identical across lags — label uses the event clock only):

| fact | value |
|---|---|
| rows / labelled / unlabelled | 4,904 / 4,255 / 649 |
| last labelable origin | **2024Q2** |
| rows after last labelable origin | 236 (2024Q3, 2024Q4, 2025Q1, 2025Q2 × 59 tracks), 100 % NaN |
| left-side NaNs | 413 = 59 tracks × exactly **7** leading NaN quarters each (growth target needs an 8-quarter trailing mean); no interior gaps |
| exclusion consistent? | **Yes within the panel** — every track has exactly 7 warm-up NaNs, zero interior gaps, all 4 tail quarters NaN |
| fold 2025 labelled test rows | **0 → `continue` in `run_track.py:136-137`; fold silently dropped** |
| fold 2024 labelled test rows | **118 instead of 236** (half the test year lost) |
| executed folds | **11, not the 12 claimed** in `run_track.py:7` |
| published sample | n = 2,443 = test origins **2014Q1–2024Q2 only**; 236 labelable rows (2024Q3–2025Q2, 8.81 % of the 2,679-row labelable test span) were never scored |

Root cause: `pc.build_joint_panel` trims to `ORIGIN_END` **before** `add_forward_target`
(`phoenix_common.py:336-339`), so the last 4 origins never get a forward window. The
cell layer already documents and fixes this by building out to `origin_end+4`
(`cell_common.py:240-250, 258-266`) — the **track layer does not**, hence the asymmetry.
This is a coverage/truncation defect, not leakage, but it belongs in any H8 restatement:
the v1 H8 number is frozen at 2024Q2 and cannot speak to 2024Q3–2025Q2.

---

## 5. Finding A4 — what this does to the published H8 numbers

Same code path, same features, same folds, same seed; only the training-row mask is
purged. The un-purged replicate reproduces the published APs and diff **exactly**
(≤1e-9), so the comparison is valid.

| variant | purge | AP(B1) | AP(H8) | ΔAP | 95 % CI | bootstrap p | n / pos |
|---|:--:|---:|---:|---:|---|---:|---:|
| v1 published / replicated (no purge) | 0 q | 0.123410 | 0.161314 | **+0.037904** | [+0.0115, +0.0618] | 0.004 | 2,443 / 155 |
| purge L=0 (decision-time min) | 3 q | 0.120840 | 0.156195 | +0.035355 | [+0.0150, +0.0588] | <0.001 | 2,443 / 155 |
| **purge L=90 (headline, removes overlap channel)** | **4 q** | **0.120666** | **0.156695** | **+0.036029** | **[+0.0158, +0.0595]** | **<0.001** | 2,443 / 155 |
| purge L=180 (stress) | 5 q | 0.119786 | 0.156609 | +0.036823 | [+0.0175, +0.0619] | <0.001 | 2,443 / 155 |

- **Is the published estimate contaminated? YES.** 2,553 of the 32,632 training-row-uses
  (7.82 %) behind the published models were labelled with events from the fold's own test
  period; 11/11 folds affected; 3–4 quarters must be purged per fold.
- **Direction of bias: upward (optimistic) for both arms.** Removing immature labels
  lowers AP(H8) by 0.0046–0.0052 and AP(B1) by 0.0027–0.0036. Published `AP=0.1613`
  overstates H8 at the headline scenario by **≈0.005 AP (~3 % relative)**.
- **But the contrast is not an artefact of the leak.** ΔAP moves from +0.03790 to
  **+0.03603** (−0.0019, −5 %) and stays far above the pre-registered τ = 0.03 with
  p < 0.001 (0/1000 paired cluster-bootstrap resamples at or below 0). Per-fold ΔAP also
  keeps the same sign pattern (only fold 2019 is negative, in both versions). The
  published H8 *verdict* survives a correct purge; its *level* and its p-value do not
  survive verbatim.
- **Can this be assessed without re-running? No** — AP is a nonlinear functional of the
  fitted coefficients, so the size/direction of the contamination bias cannot be derived
  from the row counts; it needs a re-fit. The re-fit is cheap (~2–3 s per variant after
  the panel load) and is included in `a_maturity.json → h8_rerun`.
- Caveat that changes the interpretation: purging also removes training information
  (32,632 → 30,079 row-uses at L=90), so the purged numbers measure the **net** effect of
  removing leakage and fitting on less data. The net is still SUPPORTED, therefore the
  leak is **not** what produces the H8 result.
- Second caveat: the published p = 0.004 comes from the same bootstrap with 1,000
  resamples and the same seed but a different (immature) training set; the purged p
  hitting the 0.001 floor is a resolution artefact, not a claim of p = 0. Report purged
  results as p < 0.001.

### Dependence vs leakage (explicitly kept separate)

97.58 % of the 2,443 scored track rows share an entity with another scored row whose
4-quarter label window overlaps (rows within 3 quarters). That is **temporal dependence**
— it makes the effective sample smaller than n and is the reason the cluster bootstrap is
by `track_id` — but **no future information enters training through it**. Leakage in this
audit means only: training labels computed from event-clock data that post-dates the
fold's decision time. Only §2/A1 counts are leakage.

---

## 6. What is NOT testable here

1. **The true publication delay.** `available_at == event_date` for every event in this
   database (frozen protocol §0.3), so no real lag can be estimated from the data. L = 0,
   90, 180 are **declared** scenarios; L=0 is the optimistic control and is already in
   violation, so no choice of L rescues maturity.
2. **Whether a human analyst "had" the data.** Only the arithmetic assertion is testable,
   not a counterfactual information set.
3. **The cell-level model result magnitude.** The cell walk-forward was not re-run here
   (structure and row counts are audited: 12/12 folds, 8.89 % violating rows). The defect
   is identical by construction; its AP impact would need a separate cell re-run.
4. **External truth of the H8 claim.** This audit says nothing about whether SciTrends
   growth features are genuinely predictive beyond the leak; it only removes the leak.

---

## 7. Blunt conclusion (5 lines)

1. **The required assertion fails everywhere:** 11/11 executed v1 track folds and 12/12
   cell folds train on labels that were not observable at the fold's decision time; no
   purge or embargo exists in PHOENIX-001.
2. **The minimal fix is a 3-quarter purge at L=0, 4 quarters at the headline L=90 and
   5 quarters at L=180** (5 / 6 quarters at the stricter fit-time reading), i.e. the v1
   training windows are 3–5 quarters too long in every fold.
3. **The leakage is real but modest:** 2,553 / 32,632 (7.82 %) track training-row-uses
   and 45,704 / 514,149 (8.89 %) cell training-row-uses carry test-period events in their
   labels, with the largest per-fold share 12.58 % (2014) / 14.39 % (cell 2014).
4. **The published H8 level is contaminated and optimistically biased** (AP 0.1613 →
   0.1567 at L=90; B1 0.1234 → 0.1207), **but the H8 − B1 contrast survives** the purge:
   +0.0360 [+0.0158, +0.0595] vs published +0.0379 [+0.0115, +0.0618] — so the H8 verdict
   is not caused by the leak, while the published AP/p values must be replaced.
5. **Separate bookkeeping defect:** the cached v1 track panel labels only through 2024Q2,
   so fold 2025 silently disappears and fold 2024 is half-tested (11/12 folds, 236
   labelable test rows never scored); every republished H8 number must disclose that it
   is frozen at 2024Q2.

---

*Files produced by this audit (nothing else written):*
`experiments/phoenix/h8_validation_v2/audits/a_maturity.py`,
`a_maturity.json`, `A_FINDINGS.md`.
