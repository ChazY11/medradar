# DATA-001 — Known Limitations

## Source and scope

1. **Scoped, not global.** The collector monitors the 59 reviewed organizations and their
   search tokens. It does not hold all FDA applicants or all device records. The product's
   "records" counts are counts of the scoped snapshot, not the FDA universe.
2. **openFDA update frequency is monthly/weekly.** The scheduler checks more often, but no
   system can read a record before FDA publishes it. "Continuously Monitored" does not mean
   real-time.
3. **No per-record revision timestamp.** 510(k)/PMA records expose no "last modified" field.
   Revisions are found by re-collecting the complete scoped set and comparing hashes. Recall
   `event_date_posted` is a posting date, not a revision time.
4. **Endpoint-level version.** `meta.last_updated` is one value for the endpoint. It cannot
   identify which records changed; only reconciliation can.
5. **PMA originals and supplements share one endpoint/version.** The product separates them;
   the source does not.
6. **Total-drop heuristic.** A ≥5% drop in the endpoint's global reported total marks the
   source degraded. It does not prove that records disappeared; it is a review trigger.
7. **Missing-record policy.** One complete sweep without a record is not deletion. The
   pipeline requires a second complete sweep plus an exact-ID recheck, and even then the
   record-count drop gate can block the publication. Records missing due to a query-scope
   change are retained indefinitely until an operator resolves the scope.
8. **First reconciliation accuracy.** A legacy snapshot's projection omitted some raw
   fields and truncated long text. On the first reconciliation, only fields present in that
   projection can be compared. Hidden-field changes from that one interval are not
   retroactively detectable.

## Operational

9. **Full scoped re-collection cost.** A complete recall/510(k)/PMA reconciliation transfers
   roughly 1.2 GB of openFDA responses and takes minutes on the current network. It is
   scheduled only when the source version changes, not every check.
10. **No API key required, but quota is lower.** Without a key, the default daily budget is
    900 requests (official limit 1,000/day). With a key, the default is 100,000/day. A key is
    optional and is never stored in artifacts.
11. **One writer.** The process lock prevents two local pipeline operations. It is not a
    distributed lock; do not run the same state root from two hosts.
12. **No automatic source rollback.** A backwards official version is `SOURCE_DEGRADED`.
    Recovery requires an operator; the pipeline does not guess that older is correct.
13. **No automatic deployment.** This task did not install the systemd timer, modify the
    production service unit, switch the production data directory, or enable a cloud job.
    The deployment plan requires explicit approval.
14. **No external alerting.** The status API and journal are the alert surface. No email,
    Slack, or paging integration exists.
15. **No device-index persistence cache.** The legacy docs mentioned a pickle cache that was
    never implemented. DATA-001 does not add unsafe deserialization. The index is rebuilt
    deterministically per process; this was measured in the real reconciliation.
16. **Device relations are not re-derived as a separate graph database.** The index is
    rebuilt from the validated snapshot. Confirmed relations remain confirmed; candidates
    remain candidates. No candidate is promoted by this pipeline.
17. **Change Feed is not a news feed.** It reports MedRadar-detected source changes. It does
    not assert that a company had a new regulatory event today, and it has no AI summary or
    prediction.
18. **SQLite is a single-host store.** It is appropriate for the 2 vCPU/4 GB deployment. It
    is not a multi-writer or high-availability database.
19. **Snapshot retention.** Old full snapshots are prunable, but the change ledger is small
    and retained. The identity review database is independent and must not be pruned with
    data snapshots.

## Empty or unavailable states

20. If the pipeline is not configured, `/api/data-status` says so and does not invent dates,
    zero changes, or a successful sync. Source freshness is `UNKNOWN`.
21. If the active dataset cannot load, the web app returns a dataset error, not zeros.
22. If an official query returns no records, that is a legitimate empty scoped result only
    when the HTTP semantics and the search filter say so. An unfiltered 404 is a failed
    check.

## Not in scope for DATA-001

* De Novo, UDI, establishment registration, EU MDR, NMPA.
* Global FDA bulk archive or every applicant.
* Auto-merge of the pull request or auto-enablement of production timers.
* Buying a larger server or introducing PostgreSQL/Kafka/Redis/Kubernetes.
* Automatically promoting AI-generated associations to confirmed facts.
