# DATA-003 — Resource guards: calibration, behaviour and limits

## 1. Why a per-unit `MemoryMax` is not enough

The host has 3.72 GiB RAM and 1.99 GiB swap. The DATA-002 units are:

| Unit | MemoryHigh | MemoryMax | CPUQuota |
|---|---|---|---|
| `medradar-web.service` | infinity | **infinity** | — |
| `medradar-data-update.service` | 2200 M | 2400 M | 150 % |
| `medradar-data-backup.service` | 512 M | 768 M | 50 % |

`MemoryMax=2400M` on the pipeline is a *per-unit* ceiling. It says nothing about the web's
1.6 GiB: the kernel is happy to run 1.6 + 2.4 GiB on a 3.7 GiB host and let swap absorb the
difference. That is exactly what happened during DATA-002. The guard therefore looks at **host
headroom**, not at a unit's own cap.

## 2. Measured inputs

| Quantity | Measurement | Source |
|---|---|---|
| recall reconciliation peak | **1,827.9 MB** (this host), 1,956 MB observed on production | `evidence/recall-sync.json`, DATA-002 report |
| 510(k) reconciliation peak | 1,533.2 MB | `evidence/510k-during-web.json` |
| web steady state, optimized | 336 MB + interpreter (Windows probe); production expected ~0.45–0.6 GB | `MEMORY_PROFILE.md` |
| web steady state, DATA-002 | 1,610–1,645 MB | production Phase 0 |
| web activation extra | +163 MB (dataset) / +283 MB with index | reload probe |
| host memory | 3,724 MB total, 1,598 MB available at the Phase 0 sample, swap 538 MB used of 1,987 MB | Phase 0 |
| current PSI memory | 0.00 / 0.00 | Phase 0 |

## 3. Chosen thresholds

### Pipeline (`PIPELINE_GUARD`)

| Knob | Default | Why |
|---|---|---|
| `MEDRADAR_PIPELINE_MIN_AVAILABLE_MB` | **1200** | The measured sync peak is 1.5–1.9 GB. The guard is a *go/no-go at start*: the host must have at least 1.2 GB free so the pipeline does not start from an already-full host. With the optimized web (~0.5 GB) and no other work, `MemAvailable` is ~2.5 GB, so a normal hourly run passes; during an activation (or with the old 1.6 GB web) it defers. |
| `MEDRADAR_PIPELINE_MIN_SWAP_FREE_MB` | **384** | Swap is the last buffer for a 1.8 GB peak. Below ~384 MB free, a sync can trigger a swap storm instead of a slow page. |
| `MEDRADAR_PIPELINE_MAX_PSI_SOME` | **8.0** | PSI `some avg10` above 8 % means tasks are already stalling on memory; starting a 1.8 GB job then is reckless. Production measured 0.00. |
| `MEDRADAR_PIPELINE_MIN_DISK_FREE_MB` | **2048** | A new snapshot is ~26 MB, but staging + backup + journal need room; the existing `min_free_bytes` is 2 GiB. |
| `MEDRADAR_PIPELINE_RESOURCE_GUARD` | on | Kill switch for a miscalibrated host. |

### Web activation (`ACTIVATION_GUARD`)

| Knob | Default | Why |
|---|---|---|
| `min_available_mb` | 384 | floor for the kernel to keep working |
| `required_mb` | `0.95 × RssAnon + 128` | the second dataset is roughly the live dataset minus the index; measured +163 MB dataset / +283 MB with index against a 336 MB process. Using 95 % of our own anonymous RSS is deliberately conservative. |
| `min_swap_free_mb` | 192 | activation must not be the reason swap is exhausted |
| `max_psi_some_avg10` | 6.0 | tighter than the pipeline: activation is optional and can wait |
| pipeline lock | checked | never activate while a sync is writing/publishing |

With the optimized web (~350–500 MB RSS) activation requires ~0.8–1.0 GB free — available on
production (~2.5 GB). With the old 1.6 GB process it would require ~2.0 GB free and therefore
*defer* rather than double-buffer into swap. That is the intended behaviour change.

## 4. Behaviour when the guard fires

### Web

`DatasetHolder` sets `state=deferred`, records `deferrals`, `guard.reasons`, `pending_snapshot`,
and retries every 15 s. `/api/health` shows `checks.activation.state=degraded` with
`guard_reasons`; `/api/data-status` shows `dataset_activation`. The active snapshot keeps
serving. Nothing is dropped and no request waits.

### Pipeline

`Pipeline.run()`/`sync()` returns before any source check (so an update cannot be "seen and
then refused"):

```json
{
  "status": "DEFERRED",
  "deferral": {
    "reason": "DEFERRED_RESOURCE_PRESSURE",
    "reasons": ["mem_available_below_floor"],
    "guard": {"memory": {...}, "reasons": [...]},
    "retry": "the next scheduled run retries; no source state was advanced"
  }
}
```

* run ledger row: `status=DEFERRED`, `error=DEFERRED_RESOURCE_PRESSURE`, guard snapshot in
  `metrics_json`;
* exit code **0** (the job ran; it deliberately did not start work) so systemd does not raise a
  false failure;
* `/api/data-status`: `state=deferred`, `synchronization.deferral{...}`;
* third consecutive deferral → incident `sync_deferred_resource_pressure` and
  `deferral.escalated=true`;
* `--allow-resource-pressure` is the manual override (operator-only, documented in the CLI).

## 5. The two guards close a race

| While… | the other process sees | and |
|---|---|---|
| the pipeline is running | web activation probes `pipeline.lock` (`flock`) → defers | the web does not add a second dataset |
| the web is activating | pipeline reads `activation.json` (`state=loading`, fresh < 30 min) → defers | the pipeline does not add 1.8 GB |

The activation marker is written best-effort (a read-only data dir never breaks an activation)
and becomes stale after 30 minutes, so a crashed web cannot block the pipeline forever.

## 6. Observed guard behaviour (not just unit tests)

* Real CLI with an impossible floor (`MEDRADAR_PIPELINE_MIN_AVAILABLE_MB=999999`): status
  `DEFERRED`, peak **30.9 MB**, pointer unchanged, run row recorded, exit 0
  (`evidence/guard-defer.json`).
* Three consecutive deferrals in the pipeline tests produce the incident row and
  `escalated=true`.
* Web activation deferral: old dataset keeps serving, reasons in `reload_status()`, retry
  succeeds after the guard is satisfied (`test_activation_is_deferred_under_memory_pressure_and_retried`).

## 7. What these thresholds do *not* guarantee

1. They do not cap the web. `medradar-web.service` still has no `MemoryMax`; the guard prevents
   the *known* doubling, not an unexpected leak. A `MemoryHigh` for the web (e.g. 1200 M) would
   throttle the web instead of protecting it and is not proposed for a 4 GB host.
2. They do not make 1.8 GB + 0.5 GB fit *without* swap during a sync; the sum is ~2.3 GB on a
   3.7 GB host, which is fine, but other services (~0.3 GB) and page cache make it tight. Swap
   is expected to be touched; the guard's job is to prevent the *storm*, not the use.
3. They are calibrated from one snapshot and one week of data. `OPERATIONS.md` defines how to
   re-calibrate from `memory.peak`, deferral counts and PSI over time.
4. The pipeline peak itself was not reduced (that is a separate project): a recall
   reconciliation still needs ~1.8 GB. Reducing it further would require streaming the
   change-set build and validation, which is out of DATA-003's minimal-change scope.
