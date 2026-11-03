# Observatory Health, Acquisition Phase and Seven-Day Validation

Status: factual companion to `docs/RELIABILITY_DESIGN.md` §0/§5/§6 and
`CONTINUOUS_VALIDATION_PROTOCOL`. It describes what the code actually computes; when a
sentence here and a UI sentence disagree, the code and its tests are authoritative.

Scope: `medradar/observatory/health.py` (computation), `medradar/observatory/validation.py`
(seven-day accounting), `medradar/product/observatory.py` (HTTP projection + display
labels), `web/js/pages/observatory.js` (panel). Everything is read-only over the ledger.

## 1. The five health words

`GET /api/observatory/health` returns exactly one of five words in `overall`.

| word | meaning (Chinese label used by the panel) | when it is chosen |
|---|---|---|
| `NOT_DEPLOYED` | 未部署 | no ledger, or the ledger has no `runtime_state["deployment"]` record with a real supervisor/install evidence. Data in the ledger does **not** change this. |
| `PAUSED` | 已暂停 | a deployment exists and `runtime_state["paused"].paused` is true. An explicit pause always wins over the other component checks. |
| `DEGRADED` | 降级运行 | deployed and not paused, but at least one of the §2 conditions holds (failing/stale source, structure alert, missing/unverified backup or drill, consistency issue). |
| `VALIDATION_IN_PROGRESS` | 验证进行中 | deployed, not paused, no §2 condition holds, and the seven-day validation is running. It can never be reported as passed before the window ends. |
| `OPERATIONAL` | 运行正常 | deployed, not paused, no §2 condition holds, and the validation is `VALIDATION_PASSED`. |

Precedence is fixed and tested: `NOT_DEPLOYED → PAUSED → DEGRADED →
VALIDATION_IN_PROGRESS → OPERATIONAL`. A per-component block (`deployment`,
`validation`, `collector`, `persistence`, `sources`, `checks`,
`unresolved_structure_alerts`) is always returned next to `overall`, so one green badge
can never hide a partially failing source.

Health is derived from the ledger, the filesystem and `runtime_state`; it is **not**
derived from the fact that an HTTP request returned 200.

## 2. When DEGRADED fires

`overall` becomes `DEGRADED` when any of the following is true (each has a `checks[]`
entry with `ok: false` and a Chinese detail):

- any `source_state.status != "OK"` (e.g. `FAILED`, `DEGRADED`, `PAUSED`);
- a source is stale: `freshness_hours > max(3 × declared interval, 12h)`, or the source
  has never succeeded (no `last_success_at`);
- an unresolved structure alert exists (`source_state.structure_changed_at` is set);
- the last backup is missing, `status != "OK"`, or not `verified`;
- the last backup is older than 48 hours (or has no `at` timestamp);
- the last restore drill is missing or `status != "OK"`;
- the ledger consistency check reports any issue.

The panel shows these in the source table itself (status, stale flag, structure alert,
last outcome), not only in the overall badge.

### NO_NEW_RECORDS is normal; FETCH_FAILED is failure

`source_state.last_outcome` is a closed vocabulary. `NEW_RECORDS`, `UPDATED_RECORDS`
and `NO_NEW_RECORDS` are **normal** results; `FETCH_FAILED` is a **failure**;
`PARTIAL` is partial completion; `PAUSED_SKIPPED` / `LOCKED_SKIPPED` mean the run was
deliberately skipped. The API exposes `last_outcome`, `last_outcome_label_zh` and
`last_outcome_severity` (`normal | failure | partial | skipped | unknown`), and the UI
uses different colours/labels. A failed fetch is never rendered as "no new events".

## 3. Acquisition phase vs `observation_origin` vs "event older than observation"

`observation_phase` is append-only metadata answering **"when in MedRadar's life was
this record first observed?"**. It never rewrites the immutable observation rows and its
triggers block UPDATE/DELETE.

| value | meaning |
|---|---|
| `INITIAL_DISCOVERY` (初次发现) | the record was first observed by the source's first observation-producing run — i.e. it already existed publicly when MedRadar went live |
| `INCREMENTAL_DISCOVERY` (增量发现) | first observed by a later live run — a record newly found during continuous monitoring |
| `HISTORICAL_BACKFILL` (历史回填) | deliberately imported historical archive material; such rows require a `backfill_reason` |

Three statements that are **different** and are never substituted for one another:

- `observation_origin` (`LIVE` / `BACKFILLED`) says whether the record was collected
  live or imported; phase is derived from it only for the backfill case.
- `event_at` / `published_at` say when the public event happened/was published; then
  `first_seen_at` says when MedRadar actually observed it. An old event found in a
  first live sweep is `INITIAL_DISCOVERY`, **not** a backfill.
- `HISTORICAL_BACKFILL` therefore means "intentionally imported archive", not "the
  event is old". This branch performs no backfill.

Phase is assigned by the collector from run context (first successful live run →
initial, later live runs → incremental, backfilled origin → historical). Pre-existing
rows are labelled by `reconstruct_phases()` from `sync_run` history with
`method=reconstructed_from_run_history`, as new rows — never an UPDATE. Rows without a
label are reported as `__unlabelled__` / "未标注" rather than guessed.

API: `GET /api/observatory/events?phase=INITIAL_DISCOVERY|INCREMENTAL_DISCOVERY|HISTORICAL_BACKFILL`
plus a `phase` and `phase_label_zh` on every row and a `facets.phases` block. Summary
adds `phases` (`counts`, `initial`, `incremental`, `backfill`, `unlabelled`, `note_zh`).

## 4. How the seven-day validation metrics are computed

Protocol `obs-validation-v1`: interval 6h, 7 days, `planned_slots = round(7×24/6) = 28`,
stored with a real wall-clock `started_at` / `ends_at` in `runtime_state["validation"]`.

- **due slots** = planned slot instants `started_at + k·interval` with
  `slot <= min(now, ends_at)`.
- **executed slot** = at least one `sync_run.started_at` inside
  `[slot − tolerance, slot + interval)`, where
  `tolerance = min(60 min, interval / 2)` (`slot_tolerance()` in `validation.py`;
  for the 6-hourly protocol this is 60 minutes). Each run can satisfy at most one
  slot, so a burst of manual runs cannot paper over missed slots. Runs outside the
  window, or fabricated rows, do not count.
- **missed** = due − executed. Missed is never counted as success.
- **scheduler success rate** = `ok runs / due slots`. It is deliberately 0 (not
  `None`) when slots were due and no run happened; `None` only when no slot was due.
- **attempt success rate** = `ok runs / launched runs`; per-source rates are
  `ok / attempts` for each source in the window.
- **duplicates** = duplicate `(source, source_record_id)` observations +
  replayed `(observation_id, payload_hash)` versions, over observations in the window;
  `rate` target is 0.
- **integrity** = `consistency_check()` issue count (target 0) and presence of the three
  immutability triggers; non-zero → failure.
- **latency** is measured only where the source provided a precise timestamp
  (`published_at_precision == "datetime"`); date/year precision records are reported as
  unmeasurable ("无法测量"), never converted to a fake midnight.
- **recovery** = interrupted runs in the window vs runs that completed after resuming
  from a checkpoint (`OK` run whose `notes_zh` mentions 检查点继续); `None` when no run
  was interrupted (absence is not proof of recovery).
- **storage** = ledger bytes and observations/day, plus the daily `ops_metric` snapshots.

Status transitions are explicit only. `VALIDATION_IN_PROGRESS` remains in progress when
the window elapses; it does not become passed by the passage of time. `validate stop
--outcome passed` is refused while `now < ends_at`; even after the window, recorded
duplicates or integrity violations downgrade the outcome to `VALIDATION_FAILED`. The
health panel therefore shows `VALIDATION_IN_PROGRESS` with remaining days until an
operator records the end of the experiment.

## 5. What the panel intentionally does not claim

- It is not a real-time feed. All sources are polled; cadence is declared per source.
- A missing observation is not evidence that nothing happened somewhere, and
  `NO_NEW_RECORDS` is not a failure.
- A `FETCH_FAILED` row says this fetch failed; it does not say the source has no new
  records, and it is never labelled `NO_NEW_RECORDS`.
- `NOT_DEPLOYED` stays `NOT_DEPLOYED` even when the ledger contains data: manual runs,
  local backups and local drills are not a production service.
- `backup.status == "OK"` alone is not enough: it must also be `verified` and recent.
  A never-run restore drill is shown as `NEVER`, not as "restorable".
- It never reports a seven-day validation as passed before its real window ended; a run
  of a few hours is always `VALIDATION_IN_PROGRESS`.
- Phase labels are descriptive metadata, not evidence grades or weights; unlabelled
  records are counted, not silently assigned.
- Health is not HTTP availability; the page renders the computed verdict and its
  component evidence rather than assuming the API being reachable means the system is
  healthy.

## 6. Verification

- `tests/test_observatory_health.py` (synthetic, offline) pins the five words, the
  precedence, `DEGRADED` for failed/stale sources, `DEGRADED` for missing
  backup/drill, `OPERATIONAL` only with passed validation, phase append-only triggers,
  and the validation window/metric rules.
- `tests/test_observatory_api.py` pins the `/api/observatory/health` shape, the missing
  ledger `NOT_DEPLOYED` body, the phase filter/facets and the row phase labels.
