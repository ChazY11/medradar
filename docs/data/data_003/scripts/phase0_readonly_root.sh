#!/usr/bin/env bash
# DATA-003 Phase 0b: read-only production inventory that needs root (still observational).
set -u
S="sudo -n"
sec() { printf '\n===== %s =====\n' "$1"; }

sec "SUDO"
$S true && echo "sudo ok" || echo "sudo unavailable"

sec "APP_ROOT"
ls -la /srv/medradar
$S git -C /srv/medradar rev-parse HEAD
$S git -C /srv/medradar status --porcelain | head -20
$S git -C /srv/medradar log --oneline -5

sec "DATA_ROOT"
$S ls -la /srv/medradar/data
$S ls -la /srv/medradar/data/fda
$S cat /srv/medradar/data/fda/active.json
$S du -sh /srv/medradar/data /srv/medradar/data/fda /srv/medradar/var 2>/dev/null

sec "SNAPSHOT_DIRS"
$S ls -la /srv/medradar/data/fda/snapshots 2>/dev/null || $S find /srv/medradar/data/fda -maxdepth 2 -name 'snapshot.json' -printf '%h\n'
$S find /srv/medradar/data/fda -name 'snapshot.json' -printf '%T@ %h %s\n' | sort -n

sec "SNAPSHOT_FILES"
ACT=$($S python3 -c "import json,sys;print(json.load(open('/srv/medradar/data/fda/active.json'))['path'])" 2>/dev/null)
echo "active relative path: $ACT"
if [ -n "${ACT:-}" ]; then
  $S ls -la "/srv/medradar/data/fda/$ACT"
  $S du -sh "/srv/medradar/data/fda/$ACT"
fi

sec "REVIEW_DB"
$S find /srv/medradar -maxdepth 3 -name '*.sqlite3' -o -maxdepth 3 -name '*.db' 2>/dev/null | head -20
$S du -sh /srv/medradar/var/lib/* 2>/dev/null

sec "WEB_SMAPS"
P=$(systemctl show medradar-web -p MainPID --value)
echo "pid=$P"
$S cat /proc/$P/smaps_rollup | grep -E '^(Rss|Pss|Pss_Anon|Pss_File|Pss_Shmem|Shared_Clean|Shared_Dirty|Private_Clean|Private_Dirty|Referenced|Anonymous|LazyFree|Swap):'
echo "--- fd count"
$S ls /proc/$P/fd | wc -l
echo "--- proc io"
$S cat /proc/$P/io
echo "--- wchan / sched"
$S cat /proc/$P/wchan; echo
$S cat /proc/$P/stat | awk '{print "utime=" $14, "stime=" $15, "minflt=" $10, "majflt=" $12, "rss_pages=" $24}'
echo "--- per-thread"
for t in /proc/$P/task/*; do echo "thread $(basename $t): $(cat $t/comm) state=$(awk '{print $3}' $t/stat) utime=$(awk '{print $14}' $t/stat)"; done

sec "CGROUP_WEB_STAT"
CG=/sys/fs/cgroup/system.slice/medarar-web.service
CG=/sys/fs/cgroup/system.slice/medradar-web.service
cat "$CG/memory.stat" | grep -E '^(anon|file|kernel|slab|sock|shmem|file_mapped|anon_thp|file_thp|inactive_anon|active_anon|inactive_file|active_file|unevictable|pgfault|pgmajfault|pgrefill|workingset_refault_anon|workingset_refault_file|thp_fault_alloc|thp_collapse_alloc):'
echo "--- memory.numa_stat"
cat "$CG/memory.numa_stat" 2>/dev/null | head -4
echo "--- memory.swap.events"
cat "$CG/memory.swap.events" 2>/dev/null

sec "SYSTEM_UNIT_LIMITS"
$S systemctl cat medradar-data-update.service
$S systemctl cat medradar-data-backup.service
$S systemctl cat medradar-health.service
$S systemctl cat medradar-data-update.timer
$S systemctl cat medradar-data-backup.timer
$S systemctl cat medradar-backup.service 2>/dev/null
$S systemctl cat medradar-backup.timer 2>/dev/null

sec "PIPELINE_ENV"
$S cat /etc/medradar/pipeline.env 2>/dev/null || true
$S ls -la /etc/medradar 2>/dev/null

sec "BACKUPS"
$S ls -la /srv/medradar/var/backup 2>/dev/null | head -40
$S du -sh /srv/medradar/var/backup/* 2>/dev/null | sort -h | tail -25
$S ls -la /srv/medradar/var/lib/medradar-pipeline 2>/dev/null

sec "LEGACY_BACKUP_SCRIPT"
$S cat /usr/local/bin/medradar-backup 2>/dev/null
$S cat /etc/cron.d/medradar* 2>/dev/null
$S crontab -l -u medradar 2>/dev/null

sec "DATA_STATUS_SUMMARY"
curl -sS -m 20 http://127.0.0.1:8787/api/data-status | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('state',d.get('state'))
print('snapshot',(d.get('snapshot') or {}).get('id'))
print('sources',[(s.get('source_id'),s.get('state'),s.get('records')) for s in (d.get('sources') or [])][:8])
print('keys',sorted(d.keys()))
" 2>&1

sec "DEVICE_QUALITY"
curl -sS -m 30 http://127.0.0.1:8787/api/devices/quality | head -c 2000; echo

sec "END"
date -u +%FT%TZ
