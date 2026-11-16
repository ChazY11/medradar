# DATA-003 — Root cause of the Web RSS growth and the 8 s stall

Status: measured on the production snapshot and reproduced in isolated processes.
Production was not modified. The production reading in §1 is read-only; everything else ran
against copies of the same immutable snapshot.

## 1. What production actually looked like (2026-11-17 01:17 CST)

Host: Tencent Lighthouse, Ubuntu 24.04, 2 vCPU, 3.72 GiB RAM, 1.99 GiB swap.
Service: `medradar-web.service`, one Uvicorn worker, running since 2026-11-16 11:17:48 CST
(14 h), `NRestarts=0`, `MemoryPeak=1,871,839,232`, `MemorySwapPeak=402,341,888`.

| Signal | Value | Reading |
|---|---|---|
| `VmRSS` / `RssAnon` | 1,609,660 KiB / 1,594,228 KiB | 99 % of the resident set is anonymous Python heap, not mapped files |
| cgroup `memory.current` | 1,645,375,488 | matches RSS within allocator slack |
| cgroup `memory.peak` | 1,871,839,232 | the peak is **286 MiB above** the steady state |
| `VmSwap` / cgroup `memory.swap.current` | 277,552 KiB / 348,069,888 | swapped-out pages are old, cold dataset pages |
| `systemd` `MemoryMax` / `MemoryHigh` | infinity / infinity | the web is unbounded; the pipeline is capped at 2.4 GiB |
| PSI memory `some/full avg10` | 0.00 / 0.00 | **no ongoing memory pressure at the sample time** |
| `vmstat si/so` (3 × 1 s) | 5/14, 0/0, 0/0 | no sustained swap storm at the sample time |
| `pgmajfault` (cumulative) | 74,565 | major faults happened in the past (the reload), not continuously |
| `oom_kill` | 0 | no OOM |
| load average | 0.08 | the process is idle; the resident 1.6 GiB is *data*, not compute |

Conclusion of §1: the host was **not** under current memory pressure at 01:17. The 1.6 GiB is
resident data. The 1.87 GiB peak is a **transient allocation** that happened earlier, most
plausibly the snapshot switch performed during the DATA-002 deployment at 11:26–11:27 CST.

## 2. The snapshot is 181 MB of JSON that becomes a 670 MB object graph

`fda-snapshot-20261116T032632Z-18ce4d0cbbe4`:

| File | Size |
|---|---|
| `events.jsonl.gz` | 25,007,667 B compressed / **181,405,988 B of JSON text** |
| `applicants.jsonl.gz` | 22 KB |
| `classifications.jsonl.gz` | 158 KB |
| `snapshot.json` | 400 KB |
| events | 91,457 |
| device index (built lazily) | 61,632 applications, 23,974 devices, 630 families, 29,825 recalls, 77,823 relations |

Heap breakdown of the *old* loader (identity-deduplicated `sys.getsizeof`, lower bound):

| Structure | Bytes | Note |
|---|---|---|
| `Event` instance + `__dict__` | **142.3 MB** | 41 attributes → 1,584 B of instance dict per event |
| `raw` dict **keys** | **97.2 MB** | 20 keys × 91,457 rows; `json` does **not** share key strings |
| `raw` dict values | 136.9 MB | the evidence payload, dominated by repeated applicant/device/address strings |
| `raw` dict containers | 49.8 MB | 20-slot dict object per event |
| other `Event` fields | ~110 MB | summary 13.9, device_name 13.4, official_url 10.9, … |
| device index | 106.1 MB | application/relation/recall objects plus indexes |

The JSON text is 181 MB; the parsed Python object graph is ~670 MB *live* (before the index).
That is a normal parse amplification (~3.7×), not a leak. The same strings (applicant names,
device names, status flags, raw keys) are re-created per record: 51.7 MB of raw string
characters are only 20.3 MB distinct, and the 1.8 M raw key strings are 57 distinct keys.

## 3. Where the extra ~800 MiB came from: the reload was double-buffered

`DatasetHolder.get()` in DATA-002 kept the old dataset referenced while it loaded the new one
("so a bad pointer degrades the service, not blank it"). That is the right *availability* rule
and the wrong *memory* rule: during the switch the process holds **old dataset + new dataset**
at the same time, then the old one becomes garbage but the allocator does not return all of it.

Isolated reproduction of the old loader on the production snapshot (same snapshot, Windows
benchmark host, allocator behaviour labelled):

| Stage | RSS | Δ |
|---|---|---|
| dataset loaded | 866 MB | — |
| device index built | 956 MB | +90 MB |
| new snapshot loading (old still referenced) | 1,624 MB | +668 MB |
| new index built (old still present) | 1,714 MB | +758 MB (peak) |
| old dataset released + `gc.collect()` | 1,491 MB | only 223 MB returned |

Three consecutive switches peaked at **1,930 MB** and the post-release floor drifted upward
(1,491 → 1,561 → 1,631 MB). The production `memory.peak` of 1.871 GB matches this shape
exactly: the service was switched from the old snapshot to the new one while the old dataset
was still serving. The 1.61 GB steady state is the live dataset (~0.85–1.0 GB with FastAPI,
metrics, and review overlay on Linux) plus allocator high-water retained from that peak.

**This is not a reference leak.** The old dataset objects are collected (post-release RSS falls
when the probe's references are actually dropped), but freed arenas/pages are not all returned
to the OS, and CPython's `pymalloc` keeps partially-used arenas. The production process was
started before the switch and never restarted, so it carries that high-water mark forever.

## 4. Why `/api/health` timed out for 8 s

Sequence in DATA-002 during the recall sync:

1. the pipeline publishes a new snapshot and atomically replaces `active.json`;
2. the next request calls `DatasetHolder.get()`, which takes the **global `_lock`** and starts
   `load_dataset()` **inside the request** — a CPU-bound, 6–10 s pure-Python parse;
3. every other request blocks on that same lock, including `/api/health` and `/api/readyz`;
4. the host is simultaneously running the pipeline (measured peak ~2.0 GiB), so part of the
   web's old dataset is in swap; the loader touches it to build the new dataset, which adds
   major faults and more swap;
5. a health check that arrives in that window waits for the whole load → 8 s timeout.

Three mechanisms contributed, in this order:

| Mechanism | Contribution | Evidence |
|---|---|---|
| `DatasetHolder._lock` held for the entire load | **dominant**: all requests queue behind one request | code path; baseline benchmark §6 |
| double-buffered dataset | +650–760 MB transient, pushes the host into swap | reload probe §3 |
| GIL contention while the loader runs | requests that are *not* blocked still slow down; activation can be starved under saturating CPU load | §6, `MEMORY_PROFILE.md` §5 |

Swap and CPU were amplifiers, not the primary cause. With no lock, the same load under the
same load average stops causing multi-second request stalls.

## 5. Answers to the ten engineering questions

1. **Is 800 MB → 1.61 GB normal?** No single cause is "normal": the live dataset is ~0.85–1.0 GB
   (legitimate for 91 k evidence records parsed into Python), and the remaining ~0.6 GB is the
   reload high-water that the process never released. A restart would have returned it.
2. **How much does the device index cost?** 90 MB RSS (+106 MB of objects measured), built in
   ~5.7 s. It is *not* the cause of the growth.
3. **Does `DatasetHolder` prevent the old dataset from being freed?** Not permanently, but it
   holds both datasets during the switch, which is what sets the high-water mark.
4. **How much memory does a switch need?** Old implementation: +758 MB at peak.
   New implementation: +285 MB (`MEMORY_PROFILE.md`).
5. **Direct cause of the 8 s timeout?** The global holder lock held across the in-request load,
   with swap as amplifier.
6. **GIL vs CPU vs locks vs swap?** Lock queueing → seconds-to-minutes; swap → hundreds of ms
   per fault burst; GIL → proportional slowdown of continuous work (measured 10–40× under a
   *saturating* synthetic CPU client, far less at production traffic levels).
7. **Can the 4 GB host still support automatic updates?** Yes, with the new activation path and
   a host-level guard that prevents a sync and an activation from overlapping. See
   `RESOURCE_GUARDS.md`.
8. **Minimal reliable change?** (a) stop holding the lock across the load, (b) shrink the
   dataset (slots, string sharing, streaming parse), (c) guard activation and syncs by host
   headroom. All three are implemented; no architecture rewrite.
9. **Is the improvement repeatable?** Yes: four independent measurement setups (isolated probe,
   three reload cycles, web benchmark baseline/new, fingerprint equality) are recorded in
   `BENCHMARK.md`.
10. **Do we need 8 GB?** Not demonstrated. The hosted configuration now runs the web at
    ~0.4 GB after a switch, and a sync and an activation are mutually excluded. 8 GB would add
    headroom for concurrent heavy queries, not correctness. Recommendation is to keep 4 GB and
    re-evaluate after a week of `memory.peak` and deferral data (see `OPERATIONS.md`).

## 6. Reproduce

```bash
# 1. copy a snapshot (read-only) from production, or use any snapshot directory
python tools/data003/memory_probe.py --data-dir <snapshot> --mode reload --reloads 3
# 2. prove the optimisation is behaviour-preserving
python tools/data003/dataset_fingerprint.py --data-dir <snapshot>
# 3. compare request availability under load and a switch
python tools/data003/bench_web.py --repo-root <tree> --data-root <root> \
    --duration 30 --concurrency 2 --think-ms 100 --switch-at 6 --json-out out.json
```

Evidence files: `evidence/phase0-baseline-20261116T0117Z.txt`,
`evidence/phase0-inventory-20261116T0120Z.txt`, `evidence/*.json`.
