# Applicant-entity universe v1 (`universe_v1`)

Deterministic, legal-entity–granular view of the research lane's FDA device
events, built directly from `events.applicant_raw` in `data/research.sqlite`.
It replaces "51 hand-curated parents" as the *only* way to name the firms in the
lane: every applicant string is mapped to exactly one normalised legal entity by
a documented, table-driven rule, and the five mission focus companies are
resolvable whether or not they are in the curated roster.

* Modules: `medradar/intelligence/universe.py` (stdlib only)
* Artifact: `config/universe_v1.json` — **generated, never hand-edited**
* Tests: `tests/test_universe.py` (offline synthetic fixtures)

## TL;DR — numbers from the real run

Everything below was printed by the real build against `data/research.sqlite`
(SHA-256 `dd241bfe…71e0d`, 289,443,840 bytes) with
`config/companies_device.json` SHA-256 `7fd5750a…4820`.

| metric | value |
|---|---|
| lane events (the accounting denominator) | **55,090** (31,219 510(k) + 23,871 PMA) |
| distinct raw applicant strings | **10,309** (10,063 in 510(k), 445 in PMA) |
| legal entities after normalisation | **9,412** |
| entities with a full record (`min_events = 2`, plus pinned curated/focus entities) | **4,632** |
| remainder bucket (single-event entities, aggregate only) | **4,780 entities / 4,780 events (8.68 %)** |
| events in full entity records | **50,310 (91.32 %)** |
| events accounted for (detailed + remainder) | **55,090 (100.00 %)** |
| 510(k) events attributable to a named entity | 26,464 / 31,219 = **84.77 %** |
| PMA events attributable to a named entity | 23,846 / 23,871 = **99.90 %** |
| events inside the 51 curated corporate families | **21,755 (39.49 % of the lane)** |
| distinct legal entities inside those families | 384 |
| curated-family events already linked by the old registry | 21,607 |
| curated-family events the old registry missed | **148** (Cook Medical 126, GE HealthCare 20, Canon Medical 2) |
| focus-company events absent from the curated roster | **120** (Mindray 90, Dräger 30) |
| artifact size | 1,711,167 bytes ≈ 1.63 MiB (limit: 2 MB) |
| artifact SHA-256 (this DB + this config) | `7dc2b9e8…9302` |

Coverage is honest rather than rounded: 91.32 % of events sit in records that
carry dates, tracks and raw variants; the other 8.68 % are exactly 4,780
single-event entities that cannot form a time series and are therefore kept as
an explicit aggregate bucket, not silently dropped (`counts`, `remainder`).

## Construction rules (`applicant_normalise_v1`)

`normalise_applicant(raw)` applies exactly these steps, in this order, and
nothing else. There is **no fuzzy matching, no similarity score, no edit
distance** anywhere in the identity path.

1. **Diacritic fold.** Unicode NFKD decomposition, then drop combining marks.
   `Dräger` → `DRAGER`, `Sàrl` → `SARL`. A deterministic character fold.
2. **Upper-case.**
3. **Table-driven pre-substitutions** (`_PRE_SUBSTITUTIONS`, applied longest
   source first so `S.A.S.` is not clipped by `S.A.`): dotted/slashed legal
   forms become one token — `A/S`→`AS`, `S.A.`→`SA`, `S.A.S.`→`SAS`,
   `S.R.L.`→`SRL`, `S.p.A.`→`SPA`, `B.V.`→`BV`, `K.K.`→`KK`, `L.P.`→`LP`,
   `L.L.C.`→`LLC`, `D.B.A.`/`D/B/A`→`DBA`, etc.
4. **Punctuation → separator.** Every non-alphanumeric character becomes a
   space; whitespace runs collapse. `&`, `+`, `.`, `-`, `_`, `'`, `®` are all
   separators (`Q'Apel` → `Q APEL`, `Bausch + Lomb` → `BAUSCH LOMB`).
5. **Descriptive-clause cut** (`_CLAUSE_MARKERS`). Cut the name at the first
   `FORMERLY`, `DBA`, `DOING BUSINESS AS`, `FKA`, `AKA`, `NKA`; keep the prefix.
   A former or trade name is not the registered applicant name.
   (`…(Formerly Intact)` → the current registered name; `… Also Doing Business
   AS …` → the prefix before `DOING`.)
6. **Drop a leading article** `THE`.
7. **Strip trailing corporate-suffix tokens** from `CORPORATE_SUFFIX_TOKENS`
   (`INC`, `INCORPORATED`, `LLC`, `LTD`, `LIMITED`, `CORP`, `CORPORATION`,
   `CO`, `COMPANY`, `GMBH`, `AG`, `SA`, `SAS`, `SARL`, `SPA`, `BV`, `NV`, `AB`,
   `AS`, `OY`, `PTY`, `LP`, `LLP`, `KG`, `KK`, `PTE`, `SDN`, `BHD`, `SRL`,
   `SL`, `SE`, `KGAA`, `LTDA`, `PLC`, …). Repeatedly, so `AG & CO. KGAA` and
   `PTY LTD` fully collapse. **Only tokens at the very end are removed**, so a
   suffix used inside a registered name survives (`ACME INC MEDICAL`).
8. **Never-empty fallback.** If steps 5–7 would consume the whole name (raw
   `"Ltd."`), keep the punctuation-normalised form. A blank/`None` raw string
   normalises to `""` and is bucketed as `UNKNOWN APPLICANT` at build time, so
   no event is ever lost.

Properties (all pinned by tests): deterministic, idempotent
(`normalise(normalise(x)) == normalise(x)`), table-driven, and **no fuzzy
merge**.

### Entity identity and keys

* One entity per distinct normalised name. `entity_key` = ASCII slug of the
  normalised name (≤ 40 chars) + `-` + first 8 hex of `sha1(normalised)`.
  Stable across runs and independent of input event order.
* `members` = every raw applicant string that normalises to the entity
  (sorted). 770 entities have more than one raw variant; the largest has 8.
* `display_name` = the most frequent raw string (ties → lexicographically
  smallest).
* `n_events`, `n_510k`, `n_pma`, `n_material`, `first_date`, `last_date`,
  `active_years` (distinct calendar years with events), `tracks` (per-track
  counts), `evidence` (`applicant_normalise_v1|<kinds present>`).
* **Material event** = a 510(k) clearance or an *original* PMA approval.
  PMA supplements (`payload.supplement_number` non-empty) are administrative
  follow-ups: counted in `n_events`, excluded from `n_material`. This matters —
  Medtronic has 6,281 events but only 423 material events, because 5,873 are
  PMA supplements (process-change notices), not new approvals.
* Entities are sorted by `(-n_events, entity_key)`; all inner lists and maps
  are sorted; the JSON is key-sorted with compact separators.

### Corporate-family view (reporting only, never identity)

`resolve_normalised(names, aliases)` resolves curated aliases to entities by
**token containment**: every token of the normalised alias must appear as a
token of the entity's normalised name (exact equality is the one-token case).
This is the same deterministic rule the existing `CompanyRegistry` uses for its
"all alias tokens present" tier. It never rewrites or merges entity records; it
only produces the family-level counts in `curated_coverage` and
`focus_companies`. Japanese/Chinese subsidiaries therefore stay distinct legal
entities *and* roll up to their parent family for reporting.

## Artifact layout (`config/universe_v1.json`)

| key | content |
|---|---|
| `schema_version`, `normalisation_version` | `universe_v1`, `applicant_normalise_v1` |
| `normalisation_rules` | every suffix token, pre-substitution and clause marker used |
| `source` | DB path/bytes/SHA-256, curated config path/SHA-256, `"sqlite3 read-only (mode=ro)"` |
| `counts` | the accounting table above, including per-kind splits and percentages |
| `material_event_rule`, `selection_rule` | human-readable rule statements |
| `focus_companies` | the five mission companies: family entities + counts + roster status + canonical entity |
| `curated_coverage` | per-curated-company entity/event/`unlinked_events` audit |
| `entities` | 4,632 full legal-entity records |
| `remainder` | the 4,780 single-event entities (aggregate counts + definition) |
| `cohort` | the deterministic 200-entity comparison pool selected from `entities` |

## Curated roster coverage (51 companies)

All **51/51** curated companies resolve to at least one legal entity and 51/51
have events. The family view covers 384 distinct entities and 21,755 events.

Only three curated families contain events the old `company_key` linkage had
missed — this is the recall gap the universe exposes:

| curated company | family events | curated-linked | **unlinked** |
|---|---|---|---|
| Cook Medical | 313 | 187 | **126** |
| GE HealthCare | 297 | 277 | **20** |
| Canon Medical | 108 | 106 | **2** |

The build's audit therefore reports **148** curated-family events without a
`company_key` label, plus **120** events belonging to Mindray (90) and Dräger
(30), which were unlinked *by construction* because neither company was in the
roster. The earlier lane investigation quoted 284 unlinked rows that "name a
curated company"; that exact figure is not reproduced here because entity-family
resolution is token containment over normalised names rather than the
registry's similarity tiers (and the quote likely folds the two roster-absent
focus companies in differently). Treat **148** (curated families) and **120**
(roster-absent focus companies) as `universe_v1`'s auditable numbers; exact
reconciliation with 284 is a documented follow-up.

## The five focus companies

All five are resolvable from raw applicant strings. `roster_status` records
whether the company is in the hand-curated roster, i.e. whether the gap is
closed at the universe level only (Mindray, Dräger) or already curated.

| focus company | in roster | family entities | events | 510(k) | PMA | material | already curated-linked | largest entity (events) |
|---|---|---|---|---|---|---|---|---|
| Medtronic | yes | 30 | **6,281** | 408 | 5,873 | 423 | 6,281 | `MEDTRONIC` 3,140 |
| GE HealthCare | yes | 24 | **297** | 287 | 10 | 287 | 277 | `GE MEDICAL SYSTEMS ULTRASOUND AND PRIMARY CARE DIAGNOSTICS` 66 |
| Philips | yes | 36 | **349** | 256 | 93 | 262 | 349 | `PHILIPS MEDICAL SYSTEMS NEDERLAND` 76 |
| Dräger | **no** | 5 | **30** | 30 | 0 | 30 | 0 | `DRAEGER MEDICAL SYSTEMS` 12 |
| Mindray | **no** | 2 | **90** | 90 | 0 | 90 | 0 | `SHENZHEN MINDRAY BIO MEDICAL ELECTRONICS` 84 |

Notes:

* **Mindray**: the 90 rows are 84 × `Shenzhen Mindray Bio-Medical Electronics
  Co., Ltd.` + 6 × the FDA typo `Shenzhen Mindray Bio-Meidcal Electronics Co.,
  Ltd.`. Under the no-fuzzy rule these are **two legal entities**; the
  `MINDRAY` alias family resolves both, so the focus count is complete (90).
* **Dräger**: the DB contains **30**, not 25, Dräger-family 510(k) rows —
  12 × `Draeger Medical Systems, Inc.`, 1 × `Draeger Medical Sytems, Inc.`
  (typo), 3 × `Shanghai Draeger Medical Instrument Co., Ltd.`,
  7 × `Draegerwerk AG & CO Kgaa`, and 7 × `Drägerwerk AG …` / `Dragerwerk AG …`
  (5 umlaut + 2 ASCII spellings). A plain case-insensitive ASCII `LIKE
  '%DRAEGER%'` sees only 23 of them and cannot see the 5 umlaut spellings; the
  normaliser folds `ä`→`A`, so the family view catches all 30.
* Canonical single-entity counts are also reported (`canonical_entity_key` /
  `canonical_entity_events`). For Dräger and Mindray there is no exact
  "`DRAGER`"/"`MINDRAY`" entity, so the canonical fields are `null`/`0` by
  design — the family counts are the authoritative focus numbers.

## Top 20 legal entities by activity

`n_events` ranks regulatory activity; `n_material` ranks actual approvals. Note
how PMA-supplement-heavy entities (Medtronic CRDM, Merz) rank high on events but
low on material events.

| # | entity (display name) | events | 510(k) | PMA | material | active years |
|---|---|---|---|---|---|---|
| 1 | Medtronic, Inc. | 3,140 | 118 | 3,022 | 127 | 11 |
| 2 | Boston Scientific Corp | 2,881 | 189 | 2,692 | 202 | 11 |
| 3 | ABBOTT MEDICAL | 1,830 | 60 | 1,770 | 70 | 11 |
| 4 | Medtronic Cardiac Rhythm Disease Management | 984 | 0 | 984 | 0 | 11 |
| 5 | Medtronic Neuromodulation | 762 | 1 | 761 | 2 | 11 |
| 6 | Edwards Lifesciences, LLC | 687 | 67 | 620 | 73 | 11 |
| 7 | Biotronik, Inc. | 645 | 21 | 624 | 24 | 11 |
| 8 | W. L. Gore & Associates, Inc. | 514 | 11 | 503 | 16 | 11 |
| 9 | Medtronic Vascular | 466 | 12 | 454 | 15 | 11 |
| 10 | Roche Molecular Systems, Inc. | 401 | 38 | 363 | 40 | 11 |
| 11 | Medtronic Minimed | 394 | 11 | 383 | 13 | 11 |
| 12 | Alcon Laboratories, Inc. | 296 | 32 | 264 | 34 | 11 |
| 13 | DiaSorin, Inc. | 294 | 22 | 272 | 32 | 10 |
| 14 | Biosense Webster, Inc. | 280 | 26 | 254 | 28 | 11 |
| 15 | Siemens Healthcare Diagnostics, Inc. | 253 | 63 | 190 | 67 | 11 |
| 16 | Roche Diagnostics Corp. | 250 | 69 | 181 | 72 | 11 |
| 17 | Merz North America, Inc. | 247 | 1 | 246 | 3 | 10 |
| 18 | Integra LifeSciences Corporation | 245 | 27 | 218 | 27 | 11 |
| 19 | CooperVision, Inc. | 243 | 7 | 236 | 8 | 11 |
| 20 | Siemens Medical Solutions USA, Inc. | 243 | 237 | 6 | 237 | 11 |

## Comparison-pool selection (`select_cohort`)

Documented deterministic rule:

1. **Eligible**: `n_material >= 3` and `active_years >= 2` (a minimum-history
   filter; a firm needs at least two distinct calendar years and three
   approvals).
2. **Rank**: `(n_material desc, n_events desc, entity_key asc)`.
3. **Required pins**: the highest-material eligible entity of each of the five
   focus companies is always included (they must be in the panel even if their
   legal entity falls below the rank cut-off). Pins appear first, in rank order.
4. Take the first `max_entities = 200` of `required + ranked`.

Result of the real run: **200 entities**, material-event range **19 … 127**,
largest `MEDTRONIC` (127 material events). All five focus companies are
represented: `DRAEGER MEDICAL SYSTEMS` (12 material), `GE MEDICAL SYSTEMS
ULTRASOUND AND PRIMARY CARE DIAGNOSTICS` (66), `MEDTRONIC` (127),
`PHILIPS MEDICAL SYSTEMS NEDERLAND` (76), `SHENZHEN MINDRAY BIO MEDICAL
ELECTRONICS` (84). The rule is reproducible from `entities` alone
(`cohort.entity_keys`), so downstream experiments can re-derive the pool.

## Limitations (read before using this for science)

1. **Legal-entity granularity, not corporate parents.** The universe is what
   the FDA application says, not ownership. Medtronic is 30 entities, Philips
   36, GE HealthCare 24. Parent-level series must come from the
   `curated_coverage`/`focus_companies` family view (token containment against
   curated aliases) or from a future explicit entity-granularity comparison;
   do not sum `entities` and call it a parent.
2. **No acquisition chains are resolved.** `COVIDIEN` only joins Medtronic
   because the curated alias list says so; `BELLCO SRL NOW PART OF MEDTRONIC` is
   matched to the Medtronic family only because its name contains the token.
   Firms whose acquired brand does not repeat the parent token in the applicant
   string stay separate legal entities.
3. **Suffix-only merges are possible across legal forms.** Stripping `INC`,
   `GMBH`, `AG`, … means `ACME MEDICAL INC` and `ACME MEDICAL GMBH` become one
   entity (`ACME MEDICAL`). This is the documented cost of the suffix table; it
   is tested. Substantive differences (`ACME MEDICAL` vs `ACME SURGICAL`,
   `MINDRAY` vs `MINDRAYX`) never merge.
4. **No fuzzy matching, so FDA transcription typos stay distinct entities.**
   Mindray has 84 + 6 rows in two entities; Dräger's `Draegerwerk` (7) and
   `Drägerwerk` (7) are two entities, and `Draeger Medical Sytems` is its own
   one-event entity. Entity-level panels see these as separate firms; only the
   family view (and the remainder bucket) hides the split. This is deliberate:
   silently merging typos would silently merge genuinely distinct firms too.
5. **PMA supplements are not material events.** 23,871 PMA rows are dominated by
   supplements: only **344** are original PMA approvals, while 23,527
   supplements are spread over just 445 distinct applicant strings. `n_events`
   is therefore a *regulatory activity* measure, not an innovation/approval
   measure; use `n_material` for approval intensity and say which one a model
   consumes.
6. **The PMA lane is concentrated; the 510(k) lane is long-tailed.** Most of the
   event volume in several curated families is PMA supplements rather than
   510(k)s (Abbott 2,581 of 2,784 family events; Boston Scientific 2,858 of
   3,061; Medtronic 5,873 of 6,281), while the 510(k) lane spans ~10k raw
   applicant strings. Absence of a small firm from the PMA lane says nothing
   about its device activity; comparisons across lanes must stratify by kind.
7. **Remainder is not entity-level usable.** The 4,780 remainder entities each
   have exactly one event (4,755 510(k) + 25 PMA) — counted honestly in
   `counts`/`remainder`, but they cannot support time-series features. If a
   future question needs them, raise `min_events` or materialise them from the
   DB with the documented query.
8. **Track coverage is partial.** 17,308 lane events (12,765 510(k) + 4,543
   PMA) have no `track_id`, and 1,333 of the 4,632 detailed entities have an
   empty `tracks` map. Track distributions are only as good as the curated
   product-code dictionary (`config/product_code_tracks.json`).
9. **Window and provenance.** Events are `event_date` 2016-11-01 … 2026-10-18
   (510(k)) and 2016-11-01 … 2026-10-16 (PMA), lane `as_of` 2026-11-01. The
   artifact records the exact DB SHA-256 and curated-config SHA-256; if either
   changes, the artifact must be regenerated (and its SHA-256 will change —
   byte-identical determinism is defined over a fixed (DB, config) pair).
10. **The curated-audit number differs from the earlier reconnaissance.** This
    document reports 148 unlinked curated-family events + 120 events for the two
    roster-absent focus companies; the brief's 284 was produced by an earlier,
    differently-defined match. The two are not reconciled here; the universe's
    numbers are the reproducible ones because the rule is printed in
    `normalisation_rules` and test-pinned.

## Regenerating

The database is opened read-only (`sqlite3.connect("file:…?mode=ro", uri=True)`)
and `data/` is never written; the build hashes the DB and the curated config and
embeds both hashes. The run takes ~5 s (most of it the 289 MB SHA-256).

```powershell
cd D:\DEPPSKK\worktrees\integration-v2
$env:PYTHONIOENCODING = "utf-8"

# regenerate config/universe_v1.json from the read-only research DB
python -m medradar.intelligence.universe `
    --db data/research.sqlite `
    --out config/universe_v1.json

# pin the rules
python -m pytest tests/test_universe.py -q
```

Two consecutive runs over the same (DB, config) produce byte-identical output
(verified: `7dc2b9e8…9302` twice). No timestamps are embedded precisely so that
this holds.

If the Lead adds Mindray/Dräger to `config/companies_device.json`, just re-run
the command: `focus_companies.draeger.roster_status` /
`focus_companies.mindray.roster_status` flip to `in_curated_roster`, their
curated aliases are unioned with the fallback spellings, and the counts stay
stable unless the alias list itself changes family membership.

### Reproducing the focus counts without the module

```sql
-- 510(k) rows are the whole focus story for Dräger and Mindray (no PMA rows)
SELECT applicant_raw, COUNT(*) AS n
FROM events
WHERE upper(applicant_raw) LIKE '%MINDRAY%'
GROUP BY applicant_raw;
-- Shenzhen Mindray Bio-Medical Electronics Co., Ltd.  84
-- Shenzhen Mindray Bio-Meidcal Electronics Co., Ltd.   6

SELECT applicant_raw, COUNT(*) AS n
FROM events
WHERE upper(applicant_raw) LIKE '%DRAEGER%' OR upper(applicant_raw) LIKE '%DRÄGER%'
GROUP BY applicant_raw;
```

The second query needs the umlaut spelling (`Drägerwerk`) because SQLite's
`upper()` does not fold `ä`; the Python normaliser does, which is why the module
reports 30 Dräger-family events.
