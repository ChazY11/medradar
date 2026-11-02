# Independent audit of the frozen cycle-1 numbers (reverse R&D v2)

**Auditor:** `research-auditor` (independent of the code authors of this branch).
**Date:** 2026-11-02, ~09:50–10:50 Asia/Shanghai.
**Branch / worktree:** `research/cycle2-coverage-power` at
`D:\DEPPSKK\worktrees\integration-v2`; worktree HEAD ref
`1749bd5f3af92519f97f0f4978b209da70e45b7b` (the Lead commits).
**Environment:** Python 3.12.10 (CPython, MSC v.1943 64-bit), Windows,
`$env:PYTHONIOENCODING="utf-8"`.
**Hard rules observed:** no git commands; no writes to `data/`, `experiments/` or any
source file; the SQLite database was opened **read-only** through
`sqlite3.connect("file:///D:/.../data/research.sqlite?mode=ro", uri=True)`.

**Verdict summary: all five claims PASS.** Three audit observations (O1–O3) qualify the
reading of the artifacts without contradicting any audited claim; they are listed in
§7 because the audit's value is in what a clean PASS would hide.

## 1. Inputs and their identity

The database is a 289 MB working copy under `data/` (git-ignored, not committed). To make
this audit reproducible and to make later mutation detectable, the inputs were hashed
(SHA-256) at audit time:

| Input | Bytes | SHA-256 |
|---|---:|---|
| `data/research.sqlite` | 289,443,840 | `dd241bfec138d7977d7eb8f4c1db25119d59b6fe7ff573060b24d14eeeb71e0d` |
| `experiments/reverse_rd_v2/entry_metrics.json` | 137,026 | `1c0c4c3863902acf1a3128537c3b57b3f4a132556f8fda44431ed166141872c2` |
| `experiments/reverse_rd_v2/continuation_metrics.json` | 90,390 | `7c73013859136143b08ce0806f3cfd74985a3444d437d748d98cc9cc4b0e5306` |
| `experiments/reverse_rd_v2/ablation_metrics.json` | 39,467 | `bac1cd08deb22507d4099fbf00b724eac1b97746638c04b5815ace7a7c84d602` |
| `experiments/reverse_rd_v2/config.json` | 5,452 | `1413b048562c23f0b9f774bf565dcd8419fe3c59aa8281342e6081902c0ecd43` |
| `experiments/reverse_rd_v2/data_provenance.json` | 26,678 | `a19bc05d4f2aa7d0f1101e12f581cfa7e4e7c2d905aa904b2409586c3e7d9de0` |
| `experiments/reverse_rd_v2/REPORT.md` | 20,047 | `9d47383ef0cf605059dce634b75fb8aaac8700c8a90b68a6879e53642ebabce7` |
| `docs/REVERSE_RD.md` | 19,642 | `11f8c0737411ccc9c98057b8bb7afd0ea25c4e133444f908a69234ed12fdcd30` |

Note: `data/research.sqlite` mtime (08:36:07) is **later** than the Phase-1 JSON
artifacts (08:34:28) though earlier than the ablation/report edits (08:53:50–08:54:52).
This does not by itself indicate a problem (SQLite side files and copy steps can touch
mtime), but it means the audit can attest "the claims reproduce from this DB state", not
"this DB is byte-identical to the one used at freeze time".
`data_provenance.json` contains no database hash or run id, so that link is
**UNVERIFIABLE from the committed artifacts alone** (see §8).

## 2. Method (independent re-implementation)

I did **not** import or call the repository's research, evaluation, leakage-audit or
feature code. Each claim was recomputed from three sources only:

1. the frozen JSON/Markdown artifacts (claims as stated), and
2. `data/research.sqlite` read-only, using SQL over `events`, `forecast_examples`,
   `financial_facts`, `procurement_awards`, `companies`, `tracks`, and
3. the material-event and feature definitions **as written in `docs/REVERSE_RD.md`**,
   re-implemented from scratch in Python.

Scripts were written to `%TEMP%\rr-audit\*.py` and run with `python <script>`; they are
reproduced in Appendix A so a third party can re-run them from any directory. Where the
claim is a count of rows, I rebuilt the *set* of `(company, track)` pairs, not just the
count, so a cancelling error would still fail the audit.

Claim-specific procedures are given in §3–§6. All numeric outputs below are copied from
the scripts' stdout; none is estimated.

---

## 3. Claim 1 — entry dataset base rate, origins, per-origin counts

**Claim (as frozen in `REPORT.md` §"Data actually used" and `entry_metrics.json`).**
`dataset_version='first_entry_v1'` has **503 positives / 41,003 mature rows**, base rate
**0.012267**, **24 quarterly origins** (2020-01-01…2025-10-01), candidate counts
**1,634–1,730** per origin, positives **10–28** per origin.

**Exact command.**
```powershell
$env:PYTHONIOENCODING="utf-8"
python %TEMP%\rr-audit\audit_core.py      # source in Appendix A.1
python %TEMP%\rr-audit\audit_rebuild.py   # source in Appendix A.4 (independent rebuild)
```

**Observed (from `forecast_examples`):**

| Quantity | Frozen artifact | Rebuilt from DB | Match |
|---|---:|---:|---|
| mature rows | 41,003 | 41,003 | PASS |
| positives | 503 | 503 | PASS |
| base rate | 0.012267395 | 503/41,003 = 0.012267395 | PASS |
| distinct cutoffs | 24 | 24 (2020-01-01…2025-10-01) | PASS |
| non-mature (`pending`) rows | 0 | 0 | PASS |
| candidates/origin | 1,634–1,730 | 1,634–1,730 | PASS |
| positives/origin | 10–28 | 10–28 | PASS |
| per-origin count mismatches vs `candidates_by_origin` / `positives_by_origin` | — | 0 / 0 | PASS |

**Stronger independent rebuild (Appendix A.4).** From `events` alone I rebuilt, for each
of the 24 origins, the full candidate universe: material events with
`event_date <= τ` **and** `available_at <= τ`; active companies = companies with ≥1 such
event; tracks = tracks with ≥1 such event; candidates = active company × observed track
minus pairs with any event in `(τ−36m, τ]` using exact calendar months; positive = a
material event for the pair in `(τ, τ+12m]`.

| Rebuild result | Value |
|---|---|
| derived origins | 24, `2020-01-01`…`2025-10-01`, identical to `entry_metrics.json.origins` |
| candidate pairs rebuilt, all origins | 41,003 |
| positives rebuilt, all origins | 503 |
| pair-set mismatches vs `forecast_examples` | **0 missing, 0 extra, all 24 origins** |
| coverage derived from raw events | `2016-11-01` … `2026-10-15` |

**Verdict: PASS.** Reproduced at the row *and pair* level, and independently of the
stored dataset. The reported 24-origin derivation from the coverage window is also
reproduced (2016-11-01 + 36 m → first quarter-start origin 2020-01-01; last origin with
`τ+12m <= 2026-10-15` → 2025-10-01).

**Note.** `data_provenance.json` has a field named `fda_event_count` equal to **3,833**
— that is the material-event count, not the raw FDA row count (55,090 events in the DB).
The field name is misleading; the value is consistent with claim 3.

---

## 4. Claim 2 — holdout 2025-10-01: 1,716 rows / 26 positives, consistent with the metrics file

**Claim.** The frozen final holdout window (origin `2025-10-01`) contains **1,716 rows**
and **26 positives**, and the rows/prevalence in `entry_metrics.json` are consistent
with it.

**Exact command.** `python %TEMP%\rr-audit\audit_core.py` (Appendix A.1).

**Observed:**

| Source | rows | positives | prevalence |
|---|---:|---:|---:|
| `forecast_examples` where cutoff=`2025-10-01` | 1,716 | 26 | 0.015151515 |
| `entry_metrics.json` → `baselines.holdout_rows` | 1,716 | — | — |
| `entry_metrics.json` → `baselines.predictors.constant_training_prevalence` | 1,716 | 26 | 0.015151515 |
| `entry_metrics.json` → `holdout_windows[origin=2025-10-01]` | 1,716 | 26 | 0.015151515 |

All three independent locations in the metrics file agree with the DB and with each
other. The other two pre-declared windows also reconcile: `2025-04-01` = 1,722 rows / 25
positives, `2025-07-01` = 1,721 rows / 27 positives (matching `REPORT.md` §B).

**Verdict: PASS.**

**Note.** The per-window prevalence (1.45%, 1.57%, 1.52%) differs from the pooled base
rate (1.23%) because the candidate universe has been growing over time; this is expected
and is visible in `candidates_by_origin`, not a defect.

---

## 5. Claim 3 — material events: 3,833 over 51 companies / 38 tracks / 322 pairs

**Claim (frozen `REPORT.md`, `entry_metrics.json.dataset`, `data_provenance.json`).**
There are **3,833 material events** over **51 companies**, **38 tracks** and
**322 observed company–track pairs**, coverage `2016-11-01 … 2026-10-15`.

**Exact command.** `python %TEMP%\rr-audit\audit_core.py` + material-rule variants
(Appendix A.2 and A.1).

I re-implemented the documented rule: load `kind IN ('510k','pma')` rows with
`company_key IS NOT NULL`, `track_id IS NOT NULL`, `event_date IS NOT NULL`; keep every
510(k); for PMA keep only rows whose JSON `payload.supplement_number` is one of
`""`, `"0"`, `"S0"` (trim/uppercase) **or** whose `payload.supplement_type` contains
`"PANEL TRACK"`. (Availability normalisation: `available_at` first 10 chars, falling back
to `event_date`; material on `event_date` for the label.)

**Observed:**

| Quantity | Frozen claim | Rebuilt | Match |
|---|---:|---:|---|
| material events | 3,833 | 3,833 | PASS |
| — of which 510(k) | (not stated) | 3,660 | — |
| — of which PMA | (not stated) | 173 | — |
| companies | 51 | 51 | PASS |
| tracks | 38 | 38 | PASS |
| observed pairs | 322 | 322 | PASS |
| coverage start | 2016-11-01 | 2016-11-01 | PASS |
| coverage end | 2026-10-15 | 2026-10-15 | PASS |

**Rule-ambiguity observation (important).** If "any 510(k) **with a company_key**" is
applied literally without also requiring a resolved track, the 510(k) count is **5,287**
and the total is **5,489** (5,287 + 202 PMA that are material with a company key), not
3,833. The frozen number is reproducible **only** under the full documented rule, which
also requires `track_id IS NOT NULL` (3,660 510(k) + 173 PMA = 3,833). The task
description's shorthand omitted the track condition; the artifact itself
(`REPORT.md`: "resolved-company material events over 51 companies and 38 tracks";
`docs/REVERSE_RD.md`: "Any 510(k) resolved to a curated company **and track**") states
the full rule. Under the artifact's own definition the claim is exact.

**Verdict: PASS (with the rule-ambiguity note above).** A reader who uses the shorthand
"any 510(k) with a company_key" will *not* reproduce 3,833.

**Side check.** `tracks` table has 38 rows = 38 tracks with material events;
`companies` table has 51 rows = 51 companies with material events; the DB-wide event
counts (55,090 = 31,219 510(k) + 23,871 PMA) and `financial_facts` (43,420) /
`procurement_awards` (3,453) match `data_provenance.json`.

---

## 6. Claim 4 — purge rule `cutoff + 12m <= origin` for every training row

**Claim.** For every origin evaluated in the frozen run, every training row satisfies
`cutoff + 12 months <= origin`; the reported purged training sets are consistent with
that rule.

**Exact command.** `python %TEMP%\rr-audit\audit_core.py` and
`python %TEMP%\rr-audit\audit_extra.py` (Appendix A.1, A.3).

**Procedure (independent of the code).** The frozen artifacts do not store row-level
training membership, so I reconstructed it from `forecast_examples` alone: at origin `t`,
the admissible training rows are all mature examples of the same `dataset_version` whose
`cutoff` satisfies `add_months(cutoff, 12) <= t`. Calendar-month arithmetic is done on
year·12+month indices, matching the documented "exact calendar months, not 1095 days"
rule. I then compared the reconstructed row counts with
`purge.training_rows_by_origin[*].purged_training_rows` and with
`holdout_windows[*].training_rows`, and verified that no admissible training cutoff has
a label window ending after the origin (i.e. no training label window intersects the
test window `(origin, origin+12m]`).

**Observed (entry target `first_entry_v1`):**

| Check | Result |
|---|---|
| origins present in `purge.training_rows_by_origin` | 21 (2020-10-01…2025-10-01) |
| origins with reconstructed training rows > 0 ("evaluable") | 20 (2021-01-01…2025-10-01) |
| per-origin mismatches, reconstructed vs frozen purged counts | **0 of 21** |
| `holdout_windows` training rows vs reconstruction (2025-04/07/10) | 30,679 / 32,402 / 34,122 — **all match** |
| final-holdout (2025-10-01) last admissible training cutoff | 2024-10-01; its label window ends exactly 2025-10-01 (no overlap) |
| violations: training rows with `cutoff+12m > origin` | **0** |

**Observed (continuation target `reverse_rd_v1`, same check):**

| Check | Result |
|---|---|
| origins in purge table | 22 (2020-07-01…2025-10-01) |
| origins with training rows > 0 | 21 |
| per-origin mismatches | **0 of 22** |
| holdout training rows vs reconstruction | 4,905 / 5,197 / 5,491 — **all match** |

**Verdict: PASS** for both targets. Under the reconstructed definition the purge rule
holds by construction for every training row, and — the non-trivial part — the frozen
per-origin training row counts match that reconstruction exactly, so the artifacts were
produced with this rule and not a different one.

**Note.** The first purge-table row (`2020-10-01`, 0 training rows) is listed even though
it is not an evaluable origin; that is an origin-index artefact (see O2) and is
consistent with the frozen `purge` table. The frozen `min_train_origins=3` does **not**
mean "at least 3 matured training origins" (see O2).

---

## 7. Claim 5 — leakage replay on ≥200 sampled rows: 0 mismatches

**Claim (frozen `entry_metrics.json.leakage_audit`, `REPORT.md`).** An independent as-of
replay recomputes the stored entry features from raw events restricted to
`event_date <= cutoff AND available_at <= cutoff`, over 41,003 examples / 24 cutoffs /
1,107,081 feature values, with **0 mismatches and 0 unreplayable**.

**Exact command.**
```powershell
$env:PYTHONIOENCODING="utf-8"
python %TEMP%\rr-audit\audit_leakage.py       # 416-row stratified sample
python %TEMP%\rr-audit\audit_leakage_full.py  # full 41,003-row replay (source in Appendix A.5)
```

**Procedure.** Re-implemented from the definitions in `docs/REVERSE_RD.md` §Entry
(reproduced in Appendix A.5): the 10 shared R&D-history features plus the 6 entry-specific
features. History for cutoff `τ` = material events with `event_date <= τ` **and**
`available_at <= τ` (availability parsed from the first 10 characters, falling back to
`event_date`). Window boundaries use **days** exactly as documented
(`τ−365`, `τ−730`, `τ−1095`; dormancy uses `τ−36` exact calendar months and
`days / 30.4375`, capped at 120). Then compared with the stored `features` JSON with
relative tolerance 1e-9. I also replayed the label (`event_date` in `(τ, τ+12m]`) and the
stored `first_target_event_date`.

**Observed:**

| Replay scope | rows | feature values compared | mismatches | unreplayable |
|---|---:|---:|---:|---:|
| stratified sample (24 cutoffs; includes 352 never-observed pairs, 45 positives) | 416 | 6,656 | **0** | 0 |
| **full replay, all examples** | **41,003** | **656,048** | **0** | **0** |
| label replay (all rows) | 41,003 | — | **0** label mismatches; 0 `first_target_event_date` mismatches; 503 positives reproduced | — |
| `feature_available_at == cutoff` (sample) | 416 | — | 0 violations | — |

Per-feature mismatch counts were zero for all 16 features: `rd_count_12m`,
`rd_count_previous_12m`, `rd_momentum`, `rd_count_36m`, `rd_recency_years`,
`rd_company_count_12m`, `rd_track_count_12m`, `rd_company_track_share`,
`rd_pair_active_years`, `rd_company_total_36m`, `rd_pair_inactive_months`,
`rd_company_active_tracks_12m`, `rd_company_active_tracks_delta`,
`rd_track_active_companies_12m`, `rd_track_active_companies_delta`,
`rd_company_track_novelty_share`.

**Verdict: PASS.** The sampled requirement (≥200 rows) is exceeded, and the full-row
replay is stronger than the frozen audit's own sample-free claim for the 16 R&D features.

**Scope limitation (stated so the PASS is not over-read).** This replay covers the **16
R&D-history/entry features** (656,048 comparisons), not the 11 consolidated financial
features. The frozen `leakage_audit` reports 1,107,081 values = 27 features × 41,003
rows, i.e. it also includes the financial block; I did not independently replay the
financial block (outside this task's stated scope: "recompute … a sample … of the entry
features"). Financial-feature leakage therefore remains **audited only by the original
implementation**, not by this audit. Like the frozen audit, this is an as-of
*consistency* replay: it cannot detect semantic leakage from the unversioned current
product-code→track mapping, nor re-verify the provenance of the dates themselves.

---

## 8. Additional observations (qualifications, not claim failures)

These are issues I found while auditing. None contradicts a frozen number; all affect
how the numbers should be read.

**O1 — The material-event shorthand is ambiguous (see §5).** "Resolved-company 510(k)"
means company **and track** (`track_id IS NOT NULL`) in the code and in
`docs/REVERSE_RD.md`; reading it as "company_key only" gives 5,489 instead of 3,833.
Recommendation: state the full predicate in every report, not the shorthand.

**O2 — `min_train_origins = 3` is an origin-index offset, not a minimum training-origin
count.** In `backtesting.py`, the evaluation loop starts at position `min_train_origins`
of the sorted origin list; it does not check how many training origins have matured.
Consequently the first two evaluated entry origins train on **1** and **2** matured
training origins:
`2021-01-01` — 1 training origin, 1,634 rows; `2021-04-01` — 2 training origins, 3,270
rows (continuation: `2020-10-01` 1 origin / 226 rows, `2021-01-01` 2 / 456).
These origins feed `development_metrics` and the per-origin AP stability series, not the
holdout windows. The label `min_train_origins` is therefore misleading; a reader may
believe a 3-origin minimum was enforced. Recommendation: rename to
`min_origin_index` or enforce a true minimum matured-origin count and report it.

**O3 — Frozen entry subgroup metrics are degenerate and must not be cited as
heterogeneity evidence.** With 1,716 holdout rows / 26 positives spread over 51
companies and 38 tracks, most company/track subgroups have 0–2 positives: the stored
`holdout_subgroups` contain `pr_auc = null` for groups with zero positives and
`pr_auc = 1.0` for groups with exactly one positive (e.g. `orthofix` n=34, 1 positive;
`stryker` n=24, 1 positive; `teleflex` n=35, 1 positive). Any "subgroup effect" read off
this block is noise. This is exactly why the cycle-2 heterogeneity card (H-C2-3) is
`PARTIAL`, not supported.

**O4 — FPR@0.5 is structurally uninformative for the entry target (confirmed).** The
frozen reports say FPR@0.5 = 0 exactly, because no predicted probability reaches 0.5 at
a 1.5% base rate. The audit confirms this is a property of the data/threshold, not a good
result; matched-FAR quantile thresholds are required for any operational claim.

**O5 — The committed artifacts contain no run id or DB hash.** `data_provenance.json`
records sources and row counts but not the database identity; the audit therefore
verifies "this DB state reproduces the claims", not "the freeze-time DB was this exact
file". Recommendation for cycle 2: write a `run_id` + SHA-256 of the input DB and of the
dataset rows into every artifact.

**O6 — Continuation reproduction confirmed incidentally.** The same purge reconstruction
was run on `reverse_rd_v1` (22 purge-table rows, 21 evaluable origins, holdout training
rows 4,905 / 5,197 / 5,491) and matched exactly, supporting the frozen claim that v1/v2
share one protocol.

---

## 9. What this audit does NOT establish

- It does **not** prove absence of semantic leakage. The track taxonomy is the current
  curated product-code mapping applied to history (documented in
  `docs/REVERSE_RD.md`); an as-of SQL replay cannot detect that channel.
- It does **not** re-verify the provenance of `event_date`/`available_at` values
  (decision date + assumed 14-day publication lag). The database is an input assumption,
  not an audited source.
- It does **not** audit the 11 financial features (see §7 scope limitation) or the
  market/publication features used in the ablation (those were not in the audited claim
  set).
- It does **not** validate the statistical inference (bootstrap, CIs, AP differences).
  Those are metrics-level claims owned by the evaluation task; this audit is confined to
  the five numbers listed in the task.
- It does **not** establish that the committed artifacts are byte-identical to the ones
  reported in `REPORT.md` — the REPORT is a prose rendering of the JSON, and I only
  spot-checked that its headline numbers (e.g. final-holdout entry AP 0.113927, Brier
  0.014298, rows 1,716 / 26) equal the JSON values.

## 10. PASS/FAIL table

| # | Claim | Observed by audit | Verdict |
|---|---|---|---|
| 1 | entry base rate 503/41,003; 24 origins; candidates 1,634–1,730; positives 10–28 | 41,003 / 503 / 24 / 1,634–1,730 / 10–28; independent pair-set rebuild identical | **PASS** |
| 2 | holdout 2025-10-01 = 1,716 rows / 26 positives, consistent with metrics | 1,716 / 26 / 0.015151515 in DB and in all three metrics locations | **PASS** |
| 3 | 3,833 material events / 51 companies / 38 tracks / 322 pairs | 3,833 (3,660 510(k) + 173 PMA) / 51 / 38 / 322; coverage 2016-11-01…2026-10-15 | **PASS** (rule shorthand ambiguous, O1) |
| 4 | purge `cutoff + 12m <= origin` for every training row | 0 violations; 0 count mismatches across 21 entry + 22 continuation purge rows; holdout train rows match exactly | **PASS** |
| 5 | leakage replay ≥200 rows, 0 mismatches | 416-row sample: 0/6,656 mismatches; full 41,003-row replay: 0/656,048 mismatches; 0 label/date mismatches | **PASS** |

---

## Appendix A — reproduction scripts

Written for Windows PowerShell (`$env:PYTHONIOENCODING="utf-8"`, `python <script>`). All
scripts are read-only. Set `DB` to the local read-only database path.

### A.1 Claims 1, 2, 4 and material-event count (`audit_core.py`)

```python
import sqlite3, json, os
from datetime import date, timedelta

DB = r"D:\DEPPSKK\worktrees\integration-v2\data\research.sqlite"
EXP = r"D:\DEPPSKK\worktrees\integration-v2\experiments\reverse_rd_v2"
HORIZON = 12

def connect():
    return sqlite3.connect("file:///" + DB.replace("\\", "/") + "?mode=ro", uri=True)

def add_months_str(s, n):
    y, m = int(s[:4]), int(s[5:7])
    idx = y * 12 + (m - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}-01"

def quarter_start(s):
    y, m = int(s[:4]), int(s[5:7])
    return f"{y:04d}-{((m - 1) // 3) * 3 + 1:02d}-01"

def material_pma(payload):
    try:
        row = json.loads(payload or "{}")
    except (TypeError, ValueError):
        return False
    supp = str(row.get("supplement_number") or "").strip().upper()
    kind = str(row.get("supplement_type") or "").strip().upper()
    return supp in ("", "0", "S0") or "PANEL TRACK" in kind

con = connect(); con.row_factory = sqlite3.Row; cur = con.cursor()

# material events (claim 3)
rows = cur.execute(
    "SELECT kind, event_date, available_at, company_key, track_id, payload FROM events "
    "WHERE kind IN ('510k','pma') AND company_key IS NOT NULL AND track_id IS NOT NULL "
    "AND event_date IS NOT NULL").fetchall()
material = [r for r in rows if r["kind"] != "pma" or material_pma(r["payload"])]
print("material events:", len(material), "510k:", sum(r["kind"] == "510k" for r in material),
      "pma:", sum(r["kind"] == "pma" for r in material),
      "companies:", len({r["company_key"] for r in material}),
      "tracks:", len({r["track_id"] for r in material}),
      "pairs:", len({(r["company_key"], r["track_id"]) for r in material}),
      "coverage:", min(r["event_date"] for r in material), max(r["event_date"] for r in material))

# claims 1 + 2
db_counts = {}
for r in cur.execute("SELECT cutoff, COUNT(*) n, SUM(label) pos, SUM(maturity='mature') mat "
                     "FROM forecast_examples WHERE dataset_version='first_entry_v1' "
                     "GROUP BY cutoff ORDER BY cutoff"):
    db_counts[r["cutoff"]] = {"rows": r["n"], "positives": r["pos"], "mature": r["mat"]}
metrics = json.load(open(os.path.join(EXP, "entry_metrics.json"), encoding="utf-8"))
cand, pos = metrics["dataset"]["candidates_by_origin"], metrics["dataset"]["positives_by_origin"]
print("rows:", sum(v["rows"] for v in db_counts.values()),
      "positives:", sum(v["positives"] for v in db_counts.values()),
      "origins:", len(db_counts))
print("count mismatches:", {c: (db_counts.get(c, {}).get("rows"), cand.get(c))
      for c in set(db_counts) | set(cand) if db_counts.get(c, {}).get("rows") != cand.get(c)})
print("positive mismatches:", {c: (db_counts.get(c, {}).get("positives"), pos.get(c))
      for c in set(db_counts) | set(pos) if db_counts.get(c, {}).get("positives") != pos.get(c)})
print("holdout 2025-10-01:", db_counts["2025-10-01"],
      "metrics holdout_rows:", metrics["baselines"]["holdout_rows"],
      "metrics positives:", metrics["baselines"]["predictors"]["constant_training_prevalence"]["positives"])

# claim 4: rebuild purged training sets from stored cutoffs
purge = {r["cutoff"]: r for r in metrics["purge"]["training_rows_by_origin"]}
viol, recon = [], {}
for origin in sorted(db_counts):
    train_cut = [c for c in sorted(db_counts) if add_months_str(c, HORIZON) <= quarter_start(origin)]
    n = sum(db_counts[c]["rows"] for c in train_cut)
    recon[origin] = n
    if origin in purge and purge[origin]["purged_training_rows"] != n:
        viol.append({"origin": origin, "recon": n, "frozen": purge[origin]["purged_training_rows"]})
    if [c for c in train_cut if add_months_str(c, HORIZON) > quarter_start(origin)]:
        viol.append({"origin": origin, "bad_train_cutoffs": True})
print("entry purge mismatches:", viol, "evaluable origins:", sum(1 for v in recon.values() if v > 0))
print("holdout training rows:",
      {w["origin"]: (w["training_rows"], recon[w["origin"]]) for w in metrics["holdout_windows"]})
```

### A.2 Material-event rule variants (`audit_material_variants.py`, key output)

`510k` with `company_key` only: **5,287**; `510k` with `company_key AND track_id`:
**3,660**; PMA material with company only: **202**; PMA material with company and track:
**173**; literal-shorthand total **5,489**; documented-rule total **3,833**. (Code is the
same rule as A.1 applied in four combinations; reproduce by counting each subset.)

### A.3 Continuation purge recheck (`audit_extra.py`, key output)

Repeats A.1's claim-4 reconstruction with `dataset_version='reverse_rd_v1'` and
`continuation_metrics.json`: 22 purge rows, 0 mismatches, 21 evaluable origins, holdout
training rows 4,905 / 5,197 / 5,491. Also cross-checks `data_provenance.json`
`financial_fact_rows` = 43,420 and `procurement_award_rows` = 3,453 against the DB.

### A.4 Independent candidate-universe rebuild (`audit_rebuild.py`)

```python
import sqlite3, json
from datetime import date

DB = r"D:\DEPPSKK\worktrees\integration-v2\data\research.sqlite"
HORIZON = 12

def connect():
    return sqlite3.connect("file:///" + DB.replace("\\", "/") + "?mode=ro", uri=True)

def parse_day(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None

def add_months(d, n):
    idx = d.year * 12 + (d.month - 1) + n
    return date(idx // 12, idx % 12 + 1, 1)

def material_pma(payload):
    try:
        row = json.loads(payload or "{}")
    except (TypeError, ValueError):
        return False
    supp = str(row.get("supplement_number") or "").strip().upper()
    kind = str(row.get("supplement_type") or "").strip().upper()
    return supp in ("", "0", "S0") or "PANEL TRACK" in kind

con = connect(); con.row_factory = sqlite3.Row; cur = con.cursor()
events = []
for r in cur.execute("SELECT kind, event_date, available_at, company_key, track_id, payload "
                     "FROM events WHERE kind IN ('510k','pma') AND company_key IS NOT NULL "
                     "AND track_id IS NOT NULL AND event_date IS NOT NULL"):
    if r["kind"] == "pma" and not material_pma(r["payload"]):
        continue
    day = parse_day(r["event_date"])
    avail = parse_day(str(r["available_at"] or "")[:10]) or day
    if day and avail:
        events.append((day, avail, r["company_key"], r["track_id"]))
coverage_start = min(d for d, _, _, _ in events)
coverage_end = max(d for d, _, _, _ in events)
# derive origins: t-36m >= coverage_start and t+12m <= coverage_end
earliest = add_months(coverage_start, 36)
q = date(earliest.year, ((earliest.month - 1) // 3) * 3 + 1, 1)
if q < earliest:
    q = add_months(q, 3)
origins = []
c = q
while add_months(c, HORIZON) <= coverage_end:
    origins.append(c); c = add_months(c, 3)
db = {}
for r in cur.execute("SELECT cutoff, company_key, track_id, label FROM forecast_examples "
                     "WHERE dataset_version='first_entry_v1'"):
    db.setdefault(r["cutoff"], {})[(r["company_key"], r["track_id"])] = r["label"]
tot_c = tot_p = 0
for cutoff in origins:
    cs = cutoff.isoformat()
    history = [(d, c, t) for (d, a, c, t) in events if d <= cutoff and a <= cutoff]
    active = {c for _, c, _ in history}; tracks = {t for _, _, t in history}
    pair_days = {}
    for d, c, t in history:
        pair_days.setdefault((c, t), []).append(d)
    dormancy_cut = add_months(cutoff, -36)
    cand = {(c, t) for c in active for t in tracks
            if (c, t) not in pair_days or max(pair_days[(c, t)]) <= dormancy_cut}
    future = {(c, t) for (d, a, c, t) in events if cutoff < d <= add_months(cutoff, HORIZON)}
    pos = len(cand & future); tot_c += len(cand); tot_p += pos
    stored = set(db.get(cs, {}))
    assert stored == cand, (cs, len(cand), len(stored))
    assert sum(1 for p in stored if db[cs][p] == 1) == pos
print("origins:", len(origins), "candidates:", tot_c, "positives:", tot_p)
```

### A.5 Full as-of leakage replay (`audit_leakage_full.py`, condensed)

Implements, for every stored `first_entry_v1` row, the 10 base features and 6 entry
features exactly as defined in `docs/REVERSE_RD.md` §Entry, from material events with
`event_date <= cutoff AND available_at <= cutoff`, then compares with the stored JSON:

```python
# FEATURES = [...16 names...]
# per cutoff, build: by_pair[(c,t)] = [days]; pair_first; by_company/by_track (d12, d24);
#   by_company36; company_tracks / company_tracks_prev (sets); track_companies / _prev;
#   company_events24; novel_events24 (events in (d24,cutoff] whose pair_first > d24);
#   future_by_pair (cutoff < day <= add_months(cutoff,12)).
# expected = {  # see docs/REVERSE_RD.md §Entry table and research_features.py definitions
#   rd_count_12m:         len([d for d in pair_days if d12 < d <= cutoff]),
#   rd_count_previous_12m:len([d for d in pair_days if d24 < d <= d12]),
#   rd_momentum:          log1p(recent) - log1p(previous),
#   rd_count_36m:         len([d for d in pair_days if d36 < d <= cutoff]),
#   rd_recency_years:     20.0 if no pair_days else min(20, max(0, (cutoff-max(pair_days)).days/365.25)),
#   rd_company_count_12m: by_company[c],
#   rd_track_count_12m:   by_track[t],
#   rd_company_track_share: len(recent) / max(by_company[c], 1),
#   rd_pair_active_years: 0.0 if no pair_days else max(0, (cutoff-min(pair_days)).days/365.25),
#   rd_company_total_36m: by_company36[c],
#   rd_pair_inactive_months: 120.0 if no pair_days else min(120.0, (cutoff-max(pair_days)).days/30.4375),
#   rd_company_active_tracks_12m: len(company_tracks[c]),
#   rd_company_active_tracks_delta: len(company_tracks[c]) - len(company_tracks_prev[c]),
#   rd_track_active_companies_12m: len(track_companies[t]),
#   rd_track_active_companies_delta: len(track_companies[t]) - len(track_companies_prev[t]),
#   rd_company_track_novelty_share: novel_events24[c] / company_events24[c] if company_events24[c] else 0.0,
# }
# compare each float with stored[f] at rel tol 1e-9; also replay label and first date.
```

Output: 41,003 rows / 656,048 values / 0 mismatches / 0 unreplayable; labels 0
mismatches; 503 positives reproduced. (The full source is the script named above in
`%TEMP%\rr-audit\`; it is deterministic and takes ~1.5 s.)

---

*Independence statement: I did not run, import or read-trust the frozen leakage-audit or
feature-builder code for these results; my implementations were written from
`docs/REVERSE_RD.md` and compared against the stored artifacts. Number provenance: every
value in this document was printed by a script listed above, run on 2026-11-02 against
the hashed inputs in §1.*
