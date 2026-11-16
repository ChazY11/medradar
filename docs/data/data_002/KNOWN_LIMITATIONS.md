# DATA-002 — Known Limitations

1. **Production is enabled but not long-soaked.** Fixed SHA `bb1ef34` is live; the first
   systemd-triggered `run` was `NO_CHANGE`. Days/weeks of production behavior are not yet
   observed.
2. **Same-host backup is not disaster recovery.** The host/volume is a single failure domain.
   The two existing cloud snapshots are unchanged and off-host storage was not purchased.
3. **No production soak.** Resource and restart behaviour were measured in isolated runs, not
   over days/weeks under all FDA payload shapes.
4. **Full-source peak is close to the cap.** A manual all-source run peaked at 2.16 GiB under a
   2.4 GiB cgroup. The production one-source recall sync with the new web process peaked at
   1.956 GiB; web RSS was 1.65–1.87 GiB and the host used ~557 MiB swap. One `/api/health`
   request stalled for 8 s during reload, then recovered. The automatic scheduler still uses
   one product source per run; do not raise the default without re-measuring.
5. **Rolling full reconciliation is bounded by request budget.** It may be deferred if the
   remaining daily budget cannot cover the estimate. A deferred sweep is recorded, not
   reported as success.
6. **Official version/total are not per-record revision timestamps.** The full sweep is the
   only way to find a corrected old record when the endpoint announces no version change.
7. **Source scope is the reviewed 59 organizations**, not the entire FDA universe.
8. **No source push/webhook.** Detection is polling; official cadence is monthly/weekly, and
   MedRadar cannot observe a record before FDA publishes it.
9. **API key is optional and absent in this round.** No-key daily budget is 900 requests; the
   client enforces it, and the full-sweep guard reserves capacity for checks.
10. **`/api/health` may return HTTP 200 while `sync` is degraded** because the dataset is still
   readable. Monitoring must use the JSON `checks`; the legacy CLOUD-003 script only checks
   HTTP 200 and is not modified until approval.
11. **No automatic compaction of the SQLite ledger.** The current data volumes are small;
    archival/compaction policy is future work.
12. **No production alert destination.** The health adapter writes a local JSON state and logs
    warnings; external Alertmanager/email is not configured.
13. **Cross-source consistency is version-by-version, not a single global FDA snapshot.**
    A partial snapshot can contain different official versions per source; the manifest states
    exactly which version each source represents.
