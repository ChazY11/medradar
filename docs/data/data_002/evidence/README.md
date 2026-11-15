# DATA-002 Evidence

Isolated on the production-class server (`/tmp/data002`) unless a filename says otherwise.
No production data directory, service unit or timer was changed.

| File | Proves |
|---|---|
| `server-bootstrap.json` | Bootstrap of the 91,457-record package snapshot into the pipeline |
| `server-full-all-sync.json`, `.time.txt` | Real 510(k)+PMA+recall sync: 241 requests, 1.236 GB, 8:32, 2.16 GiB peak, 0 fake changes |
| `classification-sync.json`, `.time.txt` | Support dictionary version recorded correctly after the classification audit fix |
| `full-one.json`, `.time.txt` | Rolling full-content reconciliation of one source: 3:11, 1.84 GiB |
| `check-failure.json`, `status-failure.json` | Real unreachable-source check: `CHECK_FAILED`, active snapshot unchanged |
| `backup.json`, `backup.time.txt` | Consistent SQLite/pointer/snapshot/review backup |
| `restore.json`, `restore.time.txt` | Restore into an empty isolated directory with product/device validation |
| `status-after-old.json`, `status-after-new.json` | Real rollback A→B→A; publication journal retained |
| `data-status-isolated.png` | Real Data Status page served from the isolated state after the full run |
| `server-production-after-tests.txt` | Production still `1bdb1c3`, old snapshot, no DATA-002 timer |

Raw FDA responses and full snapshots are not committed. The commands and state root are in
`../PRODUCTION_ACCEPTANCE.md`, `../RESOURCE_VALIDATION.md` and `../BACKUP_RECOVERY.md`.

Same-host limitation: these backups are on the same host/volume as the source state. They are
not off-host disaster recovery.
