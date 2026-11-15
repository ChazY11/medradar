# DATA-001 — Source Update Policy

## Official sources

| MedRadar source | Endpoint | Official update marker | Declared frequency | MedRadar check |
|---|---|---|---|---|
| `openfda_510k` | `/device/510k.json` | `meta.last_updated`, `meta.results.total` | Monthly | every 24 h |
| `openfda_pma` | `/device/pma.json` | `meta.last_updated`, `meta.results.total` | Monthly | every 24 h |
| `openfda_recall` | `/device/recall.json` | `meta.last_updated`, `meta.results.total` | Weekly | every 6 h |
| `openfda_classification` | `/device/classification.json` | `meta.last_updated`, `meta.results.total` | Monthly | every 24 h |

PMA originals and PMA supplements are **one official source** (`openfda_pma`) and one
official update version. They are separated only in the product event model (`pma` vs
`pma_supplement`). A product-level split must never be mistaken for an independent official
feed.

The endpoint-level `meta.last_updated` was verified live before the real reconciliation:

| Source | `meta.last_updated` | reported total | checked at |
|---|---:|---:|---|
| 510(k) | 2026-11-02 | 176,625 | 2026-11-15T20:46:30Z |
| PMA | 2026-11-02 | 57,487 | 2026-11-15T20:46:31Z |
| Recall | 2026-11-12 | 59,705 | 2026-11-15T20:46:33Z |
| Classification | 2026-11-02 | 7,098 | 2026-11-15T20:46:34Z |

These are source markers, not the "latest FDA event". The full evidence JSON is under
`evidence/`.

## State machine

```text
                     probe success, version == baseline, total == baseline
        ┌───────────────────────────────────────────────────────────────┐
        │                                                               ▼
    [UNKNOWN] ── version/total known, no baseline ──► [UPDATE_AVAILABLE] ──► sync
        ▲                                                               │
        │                                                               ▼
        │                                                        [NO_CHANGE]
        │
        └── probe failure 1–2 ──► [CHECK_FAILED] ── 3rd consecutive ──► [SOURCE_DEGRADED]
```

| Status | Meaning | Automatic sync? |
|---|---|---|
| `NO_CHANGE` | The official version and total exactly match the active snapshot. | no |
| `UPDATE_AVAILABLE` | Official version advanced; or the total changed without a version change. | yes |
| `CHECK_FAILED` | Network/HTTP/parse failure. Never interpreted as "no new data". | no |
| `SOURCE_DEGRADED` | Three consecutive check failures, a backwards version, a missing/invalid version marker, or a ≥5% drop in the official reported total. | blocked; explicit operator override required |
| `UNKNOWN` | No per-source baseline is recorded (for example after adopting a legacy snapshot). One reconciliation is required. | yes, once |

## Rules

1. **HTTP failure is not absence.** A 429, 5xx, timeout or malformed JSON never produces
   `NO_CHANGE`.
2. **404 is empty only for a filtered search.** An unfiltered source probe that returns 404
   is a failed check. A 404 with an explicit `search` and openFDA's `NOT_FOUND` body may be
   a legitimate empty result.
3. **Version regression is degraded.** If the official marker moves backwards, the run is
   blocked rather than silently accepting an older index.
4. **Sudden total drop is degraded.** A drop of ≥5% in the endpoint's reported total blocks
   automatic sync for review. This is a global endpoint total, not the scoped record count.
5. **Total change without version change is an update.** It may be an index correction;
   treating it as `NO_CHANGE` would hide it.
6. **PMA is one source.** No separate version is invented for originals and supplements.
7. **No real-time claim.** The declared frequencies are monthly/weekly. MedRadar checks more
   often so it notices a publication promptly; it cannot see a record before FDA publishes
   it.
8. **Retry policy.** Failed/degraded checks are retried hourly (capped by the normal
   interval), not once per full interval. HTTP retries use bounded exponential backoff and
   honour `Retry-After` for 429.
9. **Request budget.** The default is 900 requests/day without an API key (openFDA's
   unauthenticated limit is 1,000/day); with a key the default is 100,000/day (official
   limit 120,000). Budget consumption is persisted before each attempt.

## What the check frequency means

The product may say:

* "Continuously Monitored" — the scheduler checks the source on the intervals above.
* "Last Successful Sync" — the last time MedRadar collected and published a validated
  snapshot.
* "Official Source Version" — the endpoint's `meta.last_updated`.

It may not say "real-time", and it may not call the discovery date an event date.
