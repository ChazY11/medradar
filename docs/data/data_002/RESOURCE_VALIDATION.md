# DATA-002 — Resource Validation

Host: Tencent Cloud Lighthouse, 2 vCPU, 3.6 GiB visible RAM, 1.9 GiB swap, Ubuntu 24.04.
Production `medradar-web` remains on `127.0.0.1:8787` throughout. All measurements below are
isolated under `/tmp/data002`; no production data or unit was changed.

## Measurements

| Operation | Requests | Response bytes | Wall clock | Peak RSS | Result |
|---|---:|---:|---:|---:|---|
| Bootstrap from the live package snapshot | 0 | 0 | 47.2 s | 1,466,380 KiB (1.40 GiB) | success |
| **All-source scoped reconciliation** (510(k) + PMA + recall) under `MemoryMax=2400M` | 241 | 1,236,019,586 | **8:32.57** | **2,261,840 KiB (2.16 GiB)** | success, 0 added/updated |
| One-source full-content reconciliation (PMA) | 241 snapshot-audit total | 1,236,019,586 audit total | 3:11.29 | 1,843,172 KiB (1.76 GiB) | success, 38,232 records unchanged |

The all-source run is the worst-case count in this release. It completed **inside the 2.4 GiB
cgroup cap** with 0 swap during the run. The live web service remained `ok` on the old snapshot;
after the run the host had ~2.28 GiB available and ~122 MiB swap used.

## Decision

* The production automatic `run` keeps `MEDRADAR_PIPELINE_MAX_PRODUCT_SOURCES_PER_RUN=1`.
  This is deliberately below the measured full-all ceiling: a 4 GB host must also serve web
  traffic, and the next update can arrive while the previous one is still being validated.
* A combined all-source run is supported for controlled/manual purposes and has been measured
  at 2.16 GiB. It is not the default scheduler behaviour.
* `MemoryHigh=2200M`, `MemoryMax=2400M` are retained for the update unit. A `1800M` cap would
  have killed the full-source run; the old documentation is corrected.
* Full reconciliation is also one product source per run (rolling weekly), not a second full
  sweep.
* Validation was **not** weakened to fit memory. The process still loads the product dataset
  and builds the full device index for every candidate. The memory release changes only drop
  representations that are already persisted to disk.

## Caveat

Peak RSS is the process high-water mark, not a guarantee for an arbitrary future FDA response
size. The daily request budget, record-drop gate, source cap and cgroup limit remain in place.
If a future source produces materially larger pages or candidate sets, the cap should be
re-measured before raising `max_product_sources_per_run`.
