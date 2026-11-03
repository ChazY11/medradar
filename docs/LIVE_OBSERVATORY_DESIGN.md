# MedRadar Live Observatory v1 — Internal Design & Interface Contract

Status: binding for this development round. Branch `feat/live-observatory-v1`.
Base commit: `ee7d011` (accepted MedRadar 2.0 MVP HEAD, PR #12 still DRAFT / not merged).

This document is the coordination contract between the parallel work streams.
Do not rename fields, do not invent data, do not widen the honesty rules below.

---

## 1. Mission and the one question we must be able to answer

> **How do we know what information was actually observable at a given point in time?**

The system must therefore separate, for every public record, four different times
and never substitute one for another:

| field | meaning | who writes it |
|---|---|---|
| `event_at` | when the *event itself* happened according to the source (filing date, trial registration date, publication date) | source |
| `published_at` | when the *source made the record publicly available* (may be unknown) | source, never imputed |
| `first_seen_at` | when **MedRadar's collector first successfully observed** the record. Written exactly once. Immutable. | collector (real wall clock) |
| `last_checked_at` | when the collector last re-checked the record | collector |

Hard rules (enforced in code and in tests):

1. `first_seen_at` is only ever written by the collector on first successful
   fetch. No later sync may change it (SQLite trigger `RAISE(ABORT)`).
2. Historical material ingested on purpose into the past is marked
   `observation_origin = 'BACKFILLED'` with a `backfill_reason`. This round does
   **not** backfill anything into the ledger; the capability is implemented and
   tested synthetically so that a future backfill cannot lie.
3. Missing times stay `NULL`. Never `event_at + 0 days`, never "today".
4. UTC everywhere (`...Z` / `+00:00`); the source's own precision is kept in
   `*_precision` (`datetime | date | year | unknown`).
5. A failed fetch is **not** evidence that nothing happened
   (`FETCH_FAILED` is its own state and never advances a watermark).
6. `REMOVED_OR_UNAVAILABLE` means "the source no longer serves this record",
   never "the real-world thing ceased to exist".
7. The legacy research database `data/medradar.sqlite` is opened **read-only**
   or not at all. The ledger is a separate SQLite file.
8. Existing product numbers, LQ denominators, complete-quarter logic, PMA
   original-vs-supplement classification and unmapped-record disclosure are not
   touched.

---

## 2. Module layout and ownership (disjoint write scopes)

| path | owner | purpose |
|---|---|---|
| `medradar/observatory/records.py` | Lead | `RawRecord`, `MappingResult`, canonical JSON + hashing, change-state constants |
| `medradar/observatory/ledger.py` | Lead | append-only SQLite ledger, triggers, as-of replay, sync status queries |
| `medradar/observatory/adapter.py` | Lead | `SourceAdapter` protocol + generic collection engine (paging, checkpoint, retry, budget, structure detection, failure recording) |
| `medradar/observatory/mapping.py` | Lead | entity/track mapping with explicit status (`MAPPED / PENDING_REVIEW / UNMAPPED / AMBIGUOUS`) and `mapping_version` |
| `medradar/observatory/adapters/__init__.py` | Lead | lazy adapter registry |
| `medradar/observatory/adapters/sec_edgar.py` | Lead | SEC EDGAR adapter |
| `medradar/observatory/adapters/ctgov.py` | **adapters teammate** | ClinicalTrials.gov API v2 adapter |
| `medradar/observatory/adapters/europepmc.py` | **adapters teammate** | Europe PMC adapter |
| `medradar/observatory/runner.py` | Lead | `sync()` orchestration, pause/resume, run lifecycle, sync status, replay, backup |
| `medradar/observatory/lag.py` | Lead | measured publication→observation latency (single source of truth for the UI) |
| `medradar/observatory/scheduler.py` | Lead | local interval loop, heartbeat, pause handling |
| `medradar/observatory/prospective.py` | **prospective teammate** | frozen prospective observation registry |
| `medradar/product/observatory.py` | **web teammate** | read-only product query layer over the ledger |
| `medradar/web/routes_observatory.py` | **web teammate** | `/api/observatory/*` |
| `medradar/web/app.py` | **web teammate** | one added `include_router` only |
| `web/js/pages/observatory.js` | **web teammate** | Live Observatory SPA page |
| `web/js/api.js`, `web/app.js`, `web/index.html`, `web/styles.css` | **web teammate** | additive changes only; existing routes must keep working |
| `medradar/product/prospective.py`, `medradar/web/routes_lab.py`, `medradar/product/lab.py`, `web/js/pages/lab.js` | **prospective teammate** | Research Lab Prospective Observation Registry |
| `medradar/__main__.py` | **Lead only** | CLI; nobody else edits this file |
| `tests/test_observatory_*.py` | per-owner | see §7 |
| `docs/LIVE_OBSERVATORY.md`, `docs/LIVE_OBSERVATORY_ACCEPTANCE.md`, `scripts/observatory_acceptance.py`, `.github/workflows/observatory.yml` | Lead | user docs, acceptance evidence, scheduled runs |

Nobody runs `git add -A`, `git commit`, `git checkout`, `git stash` or `git push`
except the Lead. Teammates write files and report; the Lead reviews and commits.

`HUMAN_REVIEW_WORKSHEET.csv` has an unrelated pre-existing working-tree
modification. Nobody touches, stages or reverts it.

---

## 3. Observation Ledger (SQLite, `data/observatory/observatory.sqlite`)

Path resolution order: `MEDRADAR_OBSERVATORY_DB` env → `$MEDRADAR_HOME/data/observatory/observatory.sqlite`
→ repo `data/observatory/observatory.sqlite`. `data/` is git-ignored, so the
ledger is never committed to Git.

### 3.1 Tables

```sql
-- current state + immutable identity/timing of one source record
CREATE TABLE observation (
  observation_id     TEXT PRIMARY KEY,   -- sha1(source|source_record_id)
  source             TEXT NOT NULL,
  source_record_id   TEXT NOT NULL,
  record_type        TEXT NOT NULL,
  first_seen_at      TEXT NOT NULL,      -- IMMUTABLE (trigger)
  ingested_at        TEXT NOT NULL,
  observation_origin TEXT NOT NULL,      -- LIVE | BACKFILLED
  backfill_reason    TEXT,
  event_at           TEXT, event_at_precision   TEXT,  -- datetime|date|year|unknown|NULL
  published_at       TEXT, published_at_precision TEXT,
  source_updated_at  TEXT,
  last_checked_at    TEXT NOT NULL,
  source_payload_hash TEXT NOT NULL,     -- sha1 of canonical adapter payload
  latest_version_id  TEXT,
  version_count      INTEGER NOT NULL DEFAULT 1,
  observation_status TEXT NOT NULL,      -- ACTIVE | REMOVED_OR_UNAVAILABLE
  current_change_state TEXT NOT NULL,    -- NEW | UPDATED | REMOVED_OR_UNAVAILABLE
  last_change_at     TEXT NOT NULL,
  first_seen_run_id  TEXT NOT NULL,
  last_checked_run_id TEXT NOT NULL,
  -- mutable display cache only (history lives in observation_version)
  title              TEXT,
  original_url       TEXT,
  UNIQUE(source, source_record_id)
);

-- append-only payload history
CREATE TABLE observation_version (
  version_id      TEXT PRIMARY KEY,      -- sha1(observation_id|payload_hash)
  observation_id  TEXT NOT NULL,
  version_seq     INTEGER NOT NULL,      -- 1-based
  captured_at     TEXT NOT NULL,         -- real wall clock
  change_state    TEXT NOT NULL,         -- NEW | UPDATED
  payload_hash    TEXT NOT NULL,
  payload         TEXT NOT NULL,         -- canonical JSON, source-derived only
  payload_bytes   INTEGER NOT NULL,
  changed_fields  TEXT,                  -- JSON array of changed field names (null for NEW)
  source_updated_at TEXT,
  run_id          TEXT NOT NULL,
  collector_version TEXT NOT NULL,
  UNIQUE(observation_id, version_seq),
  UNIQUE(observation_id, payload_hash)
);

-- append-only change log = what the Live Observatory lists
CREATE TABLE observation_change (
  change_id        TEXT PRIMARY KEY,     -- sha1(observation_id|change_state|version_id|observed_at)
  observation_id   TEXT NOT NULL,
  source           TEXT NOT NULL,
  change_state     TEXT NOT NULL,        -- NEW | UPDATED | REMOVED_OR_UNAVAILABLE | FETCH_FAILED
  observed_at      TEXT NOT NULL,        -- real observation time
  version_id       TEXT,                 -- null for REMOVED/FETCH_FAILED
  previous_version_id TEXT,
  changed_fields   TEXT,                 -- JSON array
  first_seen_at    TEXT NOT NULL,
  event_at         TEXT,
  event_at_precision TEXT,
  published_at     TEXT,
  published_at_precision TEXT,
  record_type      TEXT NOT NULL,
  title            TEXT,
  url              TEXT,
  run_id           TEXT NOT NULL
);

-- append-only status history (ACTIVE / REMOVED_OR_UNAVAILABLE) for point-in-time replay
CREATE TABLE observation_status_history (
  observation_id TEXT NOT NULL,
  changed_at     TEXT NOT NULL,
  status         TEXT NOT NULL,
  run_id         TEXT NOT NULL,
  note           TEXT,
  PRIMARY KEY (observation_id, changed_at)
);

-- append-only mapping history: mapping changes never rewrite source history.
-- PK is (observation_id, mapped_at): several mapping revisions for one record are
-- kept (mapped_at is microsecond-ordered so the history can never collide).
CREATE TABLE observation_mapping (
  observation_id TEXT NOT NULL,
  mapped_at      TEXT NOT NULL,
  mapping_version TEXT NOT NULL,
  entity_id      TEXT,
  entity_status  TEXT NOT NULL,          -- MAPPED | PENDING_REVIEW | UNMAPPED | AMBIGUOUS
  entity_method  TEXT,
  entity_confidence REAL,
  track_id       TEXT,
  track_status   TEXT NOT NULL,          -- MAPPED | PENDING_REVIEW | UNMAPPED
  track_method   TEXT,
  note_zh        TEXT,
  PRIMARY KEY (observation_id, mapped_at)
);

-- per-source sync state
CREATE TABLE source_state (
  source TEXT PRIMARY KEY,
  label_zh TEXT,
  adapter_version TEXT,
  declared_cadence_zh TEXT,
  status TEXT NOT NULL,                  -- NEVER_RUN | OK | DEGRADED | FAILED | PAUSED
  last_attempt_at TEXT,
  last_success_at TEXT,
  last_failure_at TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  watermark TEXT,                        -- JSON
  watermark_updated_at TEXT,
  last_run_id TEXT,
  last_status_message TEXT,
  structure_signature TEXT,
  structure_changed_at TEXT,
  structure_note_zh TEXT,
  entity_coverage TEXT                    -- JSON: verified CIK/registrant coverage per company
);

-- append-only run log
CREATE TABLE sync_run (
  run_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  trigger TEXT NOT NULL,                 -- manual | schedule | ci | test
  host TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,                  -- RUNNING | OK | PARTIAL | FAILED | INTERRUPTED | SKIPPED
  collector_version TEXT,
  requests INTEGER DEFAULT 0,
  pages INTEGER DEFAULT 0,
  records_seen INTEGER DEFAULT 0,
  records_new INTEGER DEFAULT 0,
  records_updated INTEGER DEFAULT 0,
  records_unchanged INTEGER DEFAULT 0,
  records_removed INTEGER DEFAULT 0,
  records_failed INTEGER DEFAULT 0,
  watermark_before TEXT,
  watermark_after TEXT,
  error_detail TEXT,
  notes_zh TEXT
);

-- resume checkpoints (one row per scope of the newest run per source)
CREATE TABLE sync_checkpoint (
  source TEXT NOT NULL,
  run_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  cursor TEXT,
  records_seen INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (source, run_id, scope)
);

-- append-only failures: never silently swallowed
CREATE TABLE source_failure (
  failure_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  run_id TEXT,
  occurred_at TEXT NOT NULL,
  kind TEXT NOT NULL,                    -- HTTP_ERROR | TIMEOUT | RATE_LIMIT | PARSE_ERROR | STRUCTURE_CHANGE | BUDGET | SCOPE_ERROR
  url TEXT,
  http_status INTEGER,
  message TEXT,
  retryable INTEGER,
  attempt INTEGER
);

CREATE TABLE runtime_state (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);   -- schema_version, collector_version
```

### 3.2 Enforced invariants (SQLite triggers, tested)

* `observation.first_seen_at` can never be updated → `RAISE(ABORT)`.
* `observation_version` rows can never be updated or deleted.
* `observation_change`, `observation_status_history`, `observation_mapping`,
  `source_failure` are append-only (no UPDATE/DELETE triggers).
* `sync_run` may be updated exactly once, by its own finalisation (identity
  columns and deletes are blocked by triggers); a run row is never removed.
* `observation.observation_id` is deterministic:
  `sha1(source + "|" + source_record_id)`. Re-collecting the same record cannot
  create a duplicate row (also `UNIQUE(source, source_record_id)`).
* Re-collecting an identical payload appends **no** version and **no** change
  row; it only updates `last_checked_at` and increments
  `records_unchanged` on the run.
* A record that re-appears after `REMOVED_OR_UNAVAILABLE` is a `UPDATED` change
  with `changed_fields=["status"]` and **no** new payload version (the bytes did
  not change), so the payload chain stays truthful.

### 3.3 Point-in-time replay

`ledger.snapshot(as_of)` returns the ledger **as a reader would have seen it at
`as_of`**: only observations with `first_seen_at <= as_of`, each with the newest
version whose `captured_at <= as_of`, plus the status in force at that time.
Records discovered after `as_of` are excluded even if their `event_at` is older.

---

## 4. Adapter interface (`medradar/observatory/adapter.py`)

```python
SOURCE id constants in records.py: SEC EDGAR = "sec_edgar",
CLINICALTRIALS.GOV = "ctgov", EUROPE PMC = "europepmc"

@dataclass(frozen=True)
class RawRecord:
    source: str
    source_record_id: str
    record_type: str                 # "sec_8k", "sec_10q", "trial", "publication", ...
    title: str
    url: str | None
    event_at: str | None             # ISO date/datetime exactly as published
    event_at_precision: str          # datetime|date|year|unknown
    published_at: str | None
    published_at_precision: str
    source_updated_at: str | None
    payload: Mapping[str, Any]       # canonical source-derived fields (hashed)
    company_hint: str | None = None  # applicant / sponsor / assignee string
    extra: Mapping[str, Any] = field(default_factory=dict)  # cik, ticker, product codes, ...

@dataclass
class Page:
    records: list[RawRecord]
    next_cursor: str | None          # None => scope complete
    watermark: str | None = None     # committed high-water mark for this scope, if advanced
    structure_sample: Any = None     # small mapping used for structure-change detection
    note_zh: str | None = None

@dataclass
class Scope:
    scope_id: str                    # e.g. CIK number or query term
    params: Mapping[str, Any] = field(default_factory=dict)

class SourceAdapter(Protocol):
    source_id: str
    label_zh: str
    collector_version: str           # bump when parsing/field selection changes
    declared_cadence_zh: str         # honest expected cadence, e.g. "每 6 小时轮询"
    record_type_labels: Mapping[str, str]

    def plan(self, ctx: CollectContext) -> list[Scope]: ...
    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page: ...
    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult: ...
```

`CollectContext` gives the adapter: `fetcher` (the existing polite
`medradar.http.Fetcher`), `limit`, `dry_run`, `now`, `run_id`, and
`structure_signature(scope_id, sample)` helper.

The **generic engine** (`adapter.run_source`) owns, so no adapter re-implements
it: rate limiting/retry/backoff (via `Fetcher`), request budget, pagination loop,
checkpoint write after every page, per-page ledger commit, structure-change
detection, failure rows, run status transitions, `last_checked_at`, counters and
`FETCH_FAILED` marking for failed scopes. Adapters stay small and declarative.

`map_record` returns `MappingResult(entity_id, entity_status, entity_method,
entity_confidence, track_id, track_status, track_method, note_zh)`. Use
`ledger.mapping_version` = `mapping.MAPPING_VERSION` (`obs-mapping-v1`).

---

## 5. CLI (`python -m medradar observatory ...`) — Lead-owned

```
python -m medradar observatory status                 # health + per-source sync status (JSON)
python -m medradar observatory sources                # verified entity coverage per source
python -m medradar observatory sync [--source sec_edgar,ctgov] [--company KEY ...]
                                 [--limit N] [--resume] [--trigger manual]
                                 [--offline --fixtures DIR] [--dry-run] [--json]
python -m medradar observatory watch [--interval-minutes N] [--source ...]
                                     [--max-cycles N] [--json]   # local scheduler
python -m medradar observatory pause | resume          # control the scheduler / cron runs
python -m medradar observatory replay --as-of ISO [--source ...] [--limit N]
python -m medradar observatory reconcile               # data-consistency checks
python -m medradar observatory backup --dest DIR       # consistent ledger + raw-response backup
python -m medradar observatory backfill --source ... --reason TEXT   # marks BACKFILLED
```

---

## 6. HTTP API contract (`/api/observatory/*`) — for the web teammate

All prose is Chinese. Times are UTC ISO strings. `null` means "unknown", never 0.
`window` is `24h | 7d | 30d`. `change` is `new | updated | removed | failed | all`.

### GET /api/observatory/summary

```jsonc
{
  "generated_at": "2026-11-03T14:00:00+00:00",
  "ledger": {
    "path": "data/observatory/observatory.sqlite",   // relative, no absolute host path
    "exists": true, "bytes": 1234567,
    "observations": 412, "versions": 438, "changes": 455,
    "live_observations": 412, "backfilled_observations": 0,
    "sources": 2,
    "first_live_observation_at": "...", "first_run_at": "...", "last_run_at": "...",
    "schema_version": "obs-ledger-v1", "honesty_zh": "..."
  },
  "windows": {
    "24h": {"new": 9, "updated": 2, "removed": 0, "failed": 0, "total": 11},
    "7d":  {"new": 41, "updated": 3, "removed": 0, "failed": 0},
    "30d": {"new": 41, "updated": 3, "removed": 0, "failed": 0}
  },
  "first_observation": {                     // null when nothing observed yet
    "change_id": "...", "observed_at": "...", "source": "sec_edgar", "title": "..."
  },
  "by_source": [{
    "source": "sec_edgar", "label_zh": "SEC EDGAR 公开披露", "status": "OK",
    "status_label_zh": "正常", "last_success_at": "...", "last_attempt_at": "...",
    "declared_cadence_zh": "每 6 小时轮询", "consecutive_failures": 0,
    "new_24h": 3, "updated_24h": 0, "new_7d": 12, "updated_7d": 1,
    "measured_lag": {
      "measurable": true, "note_zh": "SEC 受理时间 → 首次观察",
      "p50_hours": 4.2, "p90_hours": 9.1, "max_hours": 30.0, "n": 12
    },
    "coverage_zh": "...", "limitation_zh": "..."
  }],
  "by_company": [{"entity_id":"medtronic","name_zh":"美敦力","new_24h":1,"updated_24h":0,
                  "new_7d":4,"updated_7d":0,"total":30, "status":"MAPPED"}],
  "by_track": [{"track_id":"cardiac_rhythm","name_zh":"心脏节律","domain":"cardiovascular",
                "new_24h":1,"updated_24h":0,"new_7d":3,"updated_7d":0}],
  "unmapped": {"company": 12, "track": 30, "note_zh": "..."},
  "empty": false,
  "limitations": [{"id": "not_realtime", "text_zh": "..."}]
}
```

### GET /api/observatory/events?window=7d&change=all&source=&company=&track=&q=&limit=50&offset=0

```jsonc
{
  "total": 23, "limit": 50, "offset": 0,
  "window": {"id": "7d", "hours": 168, "start": "...", "end": "..."},
  "filters": {"change": "all", "source": null, "company": null, "track": null, "q": null},
  "facets": {"sources": [{"source","label_zh","count"}],
             "companies": [{"entity_id","name_zh","count"}],
             "tracks": [{"track_id","name_zh","count"}],
             "changes": [{"change_state","label_zh","count"}]},
  "items": [{
    "change_id": "...", "observation_id": "...",
    "source": "sec_edgar", "source_label_zh": "SEC EDGAR", "record_type": "sec_8k",
    "record_type_label_zh": "8-K 重大事件披露",
    "change_state": "NEW", "change_label_zh": "新增",
    "observed_at": "2026-11-03T09:12:00+00:00",
    "first_seen_at": "2026-11-03T09:12:00+00:00",
    "event_at": "2026-11-02", "event_at_precision": "date", "event_at_label_zh": "事件发生",
    "published_at": "2026-11-02T21:18:02+00:00", "published_at_precision": "datetime",
    "source_updated_at": null,
    "time_basis": {
      "event_to_publish_hours": 12.4, "publish_to_first_seen_hours": 11.9,
      "event_to_first_seen_hours": 24.3, "measurable": true,
      "observed_later_than_event": true,
      "statement_zh": "该事件发生于 2026-11-02；MedRadar 于 2026-11-03 首次观察到它。"
    },
    "title": "8-K｜Item 8.01（Medtronic plc，2026-11-02 提交）",
    "url": "https://www.sec.gov/Archives/edgar/data/...",
    "original_url": "...",
    "company": {"entity_id": "medtronic", "name_zh": "美敦力", "status": "MAPPED",
                "method": "sec_cik_exact", "note_zh": null},
    "track": {"track_id": null, "name_zh": null, "domain": null, "status": "UNMAPPED"},
    "changed_fields": [],                     // UPDATED only: [{"field","label_zh","old","new"}]
    "version": {"version_seq": 1, "version_count": 1, "version_id": "..."},
    "is_revision": false,
    "evidence_zh": "..."                      // short honest sentence for the row
  }]
}
```

`change=new` → only `NEW`; `change=updated` → `UPDATED`; `change=removed` →
`REMOVED_OR_UNAVAILABLE`; `change=failed` → `FETCH_FAILED`; `all` → all four.
`observed_at` is when **MedRadar** observed; never re-label it as the event date.

### GET /api/observatory/events/{observation_id}

```jsonc
{
  "observation": { ...same fields as a row above, plus source_record_id, ingested_at,
                   observation_status, observation_origin, backfill_reason, last_checked_at },
  "versions": [{"version_seq":1,"version_id":"...","captured_at":"...","change_state":"NEW",
                "payload_hash":"...","changed_fields":[],
                "payload": {...}}],
  "changes": [{"change_id","change_state","observed_at","version_id","changed_fields"}],
  "mapping_history": [{"mapping_version","mapped_at","entity_id","entity_status","track_id","track_status","note_zh"}],
  "status_history": [{"changed_at","status","note"}],
  "sync_context": {"first_seen_run_id": "...", "run": {...}, "source_state": {...}},
  "limitations": [{"id","text_zh"}]
}
```

### GET /api/observatory/sources

```jsonc
{"sources": [{
  "source": "ctgov", "label_zh": "ClinicalTrials.gov 注册库", "status": "OK",
  "status_label_zh": "正常", "declared_cadence_zh": "每 12 小时轮询",
  "last_attempt_at": "...", "last_success_at": "...", "last_failure_at": null,
  "consecutive_failures": 0, "watermark": {...}, "watermark_updated_at": "...",
  "structure": {"signature": "...", "changed_at": null, "note_zh": null},
  "counts": {"runs_total": 3, "runs_ok": 3, "runs_failed": 0, "observations": 120,
             "new_7d": 20, "updated_7d": 2, "records_failed": 0},
  "recent_runs": [{"run_id","started_at","finished_at","status","trigger","requests",
                   "records_seen","records_new","records_updated","records_unchanged",
                   "records_removed","error_detail"}],
  "recent_failures": [{"occurred_at","kind","message","http_status","retryable"}],
  "entity_coverage": [{"entity_id","name_zh","covered": true, "evidence_zh": "...",
                       "identifier": "CIK 0001613103", "status": "COVERED"}],
  "measured_lag": {...same as summary},
  "coverage_note_zh": "...", "limitation_zh": "..."
}], "generated_at": "..."}
```

Entity coverage must be *verified*, not assumed: e.g. Dräger/Mindray have no SEC
registrant status and must be reported as `NOT_REGISTRANT` with the evidence
that was checked, never as "0 filings".

### GET /api/observatory/replay?as_of=2026-11-03T10:00:00Z&source=&limit=100

```jsonc
{"as_of": "...", "policy_zh": "只包含在该时点之前已被 MedRadar 实际观察到的记录…",
 "total": 8, "excluded_discovered_later": 5,
 "items": [{"observation_id","source","title","first_seen_at","event_at",
            "version_seq","captured_at","status","payload_hash"}]}
```

### Product compatibility

The existing endpoints, the five MVP scenarios and `node scripts/product_e2e.cjs`
must keep passing. The Observatory is **additive**: it must render an honest
empty state when the ledger does not exist (HTTP 200 with `"exists": false`,
never fabricated events), so the CI wheel/demo run stays green.

---

## 7. Testing conventions

Four tiers, never conflated in reports:

1. **Synthetic** (`tests/test_observatory_*.py`, default on, no network):
   deterministic fixtures, fake adapter, fake clock, revision/removal/injection,
   replay exclusion, idempotency, failure recovery, trigger immutability.
2. **Real API connectivity** (`MEDRADAR_LIVE_TESTS=1`): one polite request per
   source, asserts the documented fields exist; skipped by default so CI is
   offline.
3. **Real incremental collection** (`scripts/observatory_acceptance.py run`):
   actually hits SEC EDGAR + ClinicalTrials.gov, writes to a throwaway ledger,
   asserts A–E, and saves raw evidence under `docs/observatory/evidence/`.
4. **Real scheduled run** (`observatory watch --max-cycles 2`): proves the local
   loop performs two real cycles with persisted state; its log is evidence too.

Every test name must say which tier it is in (docstring line 1).

---

## 8. Honesty rules for the UI

* Two different sentences, never merged:
  "该事件发生于 {event_at}" vs "MedRadar 于 {first_seen_at} 首次观察到它".
* Show `published_at` separately; when unknown, say "来源未提供发布时间", not the event date.
* `NEW` / `UPDATED` / `REMOVED_OR_UNAVAILABLE` / `FETCH_FAILED` are four different
  claims; a failed fetch banner never reads as "无新事件".
* Sync status shows declared cadence vs measured lag; if a source cannot measure
  lag, show "无法测量" with the reason.
* Never rank, score or interpret new public activity as a strategic shift.
* The homepage "Newly Observed Evidence" block is driven by the ledger only; with
  no observations it shows an honest empty state.
