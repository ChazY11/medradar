#!/usr/bin/env bash
# DATA-003 Phase 0: read-only production baseline capture.
# Runs only observational commands. No writes, no restarts, no config changes.
set -u

SUDO=""
if sudo -n true 2>/dev/null; then SUDO="sudo -n"; fi

sec() { printf '\n===== %s =====\n' "$1"; }

sec "META"
date -u +%FT%TZ
date
hostname
uptime
cat /proc/loadavg

sec "KERNEL"
uname -a
cat /etc/os-release | head -4

sec "CPU"
nproc
grep -m1 'model name' /proc/cpuinfo
vmstat 1 3

sec "MEMORY_FREE"
free -m
free -h

sec "MEMINFO"
grep -E '^(MemTotal|MemFree|MemAvailable|Buffers|Cached|SwapTotal|SwapFree|SwapCached|Dirty|Writeback|AnonPages|Mapped|Shmem|Slab|SReclaimable|SUnreclaim|PageTables|Committed_AS|CommitLimit|Active|Inactive):' /proc/meminfo

sec "MEMORY_PRESSURE"
cat /proc/pressure/memory 2>/dev/null || echo "no PSI"

sec "VMSTAT_COUNTERS"
grep -E '^(pswpin|pswpout|pgmajfault|pgfault|pgscan_direct|pgscan_kswapd|allocstall|oom_kill)' /proc/vmstat

sec "PSI_CPU_IO"
cat /proc/pressure/cpu 2>/dev/null
cat /proc/pressure/io 2>/dev/null

sec "DISK"
df -h /
df -i / | tail -2

sec "SYSTEMD_UNITS"
systemctl is-active medradar-web.service
systemctl show medradar-web.service -p ActiveState -p SubState -p MainPID -p NRestarts -p ExecMainStartTimestamp -p ExecMainStartTimestampMonotonic -p MemoryCurrent -p MemoryPeak -p MemoryMax -p MemoryHigh -p MemorySwapCurrent -p MemorySwapMax -p MemoryAccounting -p TasksCurrent -p CPUUsageNSec

sec "SYSTEMD_CAT"
systemctl cat medradar-web.service 2>/dev/null

sec "TIMERS"
systemctl list-timers --all --no-pager | head -25
for u in medradar-data-update.timer medradar-data-backup.timer medradar-health.timer; do
  echo "--- $u"
  systemctl is-enabled "$u" 2>&1
  systemctl is-active "$u" 2>&1
  systemctl show "$u" -p NextElapseUSecRealtime -p LastTriggerUSec -p Result
done

sec "TIMER_SERVICES"
for u in medradar-data-update.service medradar-data-backup.service medradar-health.service; do
  echo "--- $u"
  systemctl show "$u" -p ActiveState -p SubState -p Result -p ExecMainStatus -p ExecMainExitTimestamp -p ExecMainStartTimestamp
done

sec "PS_TOP_RSS"
ps -eo pid,ppid,rss,vsz,etime,pcpu,pmem,cmd --sort=-rss | head -15

sec "WEB_PROC_DETAIL"
MAINPID=$(systemctl show medradar-web.service -p MainPID --value)
echo "MainPID=$MAINPID"
if [ -n "${MAINPID:-}" ] && [ "$MAINPID" != "0" ]; then
  ps -o pid,ppid,rss,vsz,etime,nlwp,cmd -p "$MAINPID"
  echo "--- children"
  ps --ppid "$MAINPID" -o pid,rss,etime,cmd || true
  echo "--- smaps_rollup"
  cat "/proc/$MAINPID/smaps_rollup" 2>/dev/null | grep -E '^(Rss|Pss|Pss_Anon|Pss_File|Pss_Shmem|Shared_Clean|Shared_Dirty|Private_Clean|Private_Dirty|Referenced|Anonymous|LazyFree|Swap):'
  echo "--- status"
  grep -E '^(VmPeak|VmSize|VmHWM|VmRSS|RssAnon|RssFile|RssShmem|VmSwap|Threads):' "/proc/$MAINPID/status"
  echo "--- limits"
  grep -E 'open files|max processes|locked memory' "/proc/$MAINPID/limits"
  echo "--- fd count"
  ls "/proc/$MAINPID/fd" 2>/dev/null | wc -l
  echo "--- cpu affinity"
  taskset -pc "$MAINPID" 2>/dev/null
  echo "--- started"
  ps -o lstart= -p "$MAINPID"
fi

sec "CGROUP_WEB"
CGP=$(systemctl show medradar-web.service -p ControlGroup --value)
echo "ControlGroup=$CGP"
CG="/sys/fs/cgroup${CGP}"
if [ -d "$CG" ]; then
  for f in memory.current memory.peak memory.max memory.high memory.swap.current memory.swap.peak memory.swap.max memory.events memory.pressure; do
    [ -f "$CG/$f" ] && { echo "--- $f"; cat "$CG/$f"; }
  done
  echo "--- memory.stat (selected)"
  grep -E '^(anon|file|kernel|slab|sock|shmem|file_mapped|anon_thp|file_thp|inactive_anon|active_anon|inactive_file|active_file|unevictable|pgfault|pgmajfault|pgrefill|workingset_refault_anon|workingset_refault_file|thp_fault_alloc):' "$CG/memory.stat"
else
  echo "cgroup path missing: $CG"
fi

sec "CGROUP_ROOT"
for f in memory.current memory.peak memory.events memory.pressure; do
  [ -f "/sys/fs/cgroup/$f" ] && { echo "--- /sys/fs/cgroup/$f"; cat "/sys/fs/cgroup/$f"; }
done

sec "APP_GIT"
ls -la /srv/medradar 2>/dev/null
git -C /srv/medradar/app rev-parse HEAD 2>&1
git -C /srv/medradar/app log --oneline -3 2>&1
git -C /srv/medradar/app status --porcelain 2>&1 | head -20

sec "APP_VERSIONS"
cat /srv/medradar/app/medradar/VERSION 2>/dev/null || true
ls /srv/medradar/data 2>/dev/null

sec "HTTP_PROBE"
PORT=$(systemctl cat medradar-web.service 2>/dev/null | grep -oE '(--port[= ]+|--bind[= ]+[0-9.]+:)[0-9]+' | grep -oE '[0-9]+$' | head -1)
[ -z "${PORT:-}" ] && PORT=8000
echo "PORT=$PORT"
for p in /api/livez /api/readyz /api/health /api/data-status /api/meta / /organizations /events /devices /compare /data-status; do
  echo "--- $p"
  curl -sS -o /tmp/d3_probe.out -w 'http=%{http_code} dns=%{time_namelookup} conn=%{time_connect} start=%{time_starttransfer} total=%{time_total} size=%{size_download}\n' --max-time 15 "http://127.0.0.1:${PORT}${p}" 2>&1
  head -c 600 /tmp/d3_probe.out 2>/dev/null; echo
done
rm -f /tmp/d3_probe.out

sec "JOURNAL_WEB_RECENT"
${SUDO} journalctl -u medradar-web.service --since '-3 hours' --no-pager 2>&1 | tail -40 || echo "journal unavailable"

sec "JOURNAL_OOM"
${SUDO} journalctl -k --since '-14 days' --no-pager 2>&1 | grep -iE 'out of memory|oom-kill|killed process' | tail -20 || echo "no oom lines or unavailable"
dmesg 2>/dev/null | grep -iE 'oom|killed process' | tail -10 || true

sec "JOURNAL_TIMERS"
for u in medradar-data-update.service medradar-data-backup.service medradar-health.service; do
  echo "--- $u"
  ${SUDO} journalctl -u "$u" --since '-24 hours' --no-pager 2>&1 | tail -12 || echo "unavailable"
done

sec "BOOTS"
who -b 2>/dev/null
last -x reboot 2>/dev/null | head -5
last -x shutdown 2>/dev/null | head -5

sec "BACKUP_DIRS"
ls -la /srv/medradar/var/backup 2>/dev/null | head -30
du -sh /srv/medradar/var/backup/* 2>/dev/null | sort -h | tail -20
ls -la /srv/medradar/data/fda 2>/dev/null | head -20

sec "SNAPSHOTS"
ls -la /srv/medradar/data/fda/snapshots 2>/dev/null | tail -20

sec "PIPELINE_STATUS"
cat /srv/medradar/var/lib/medradar-pipeline/pipeline.sqlite3 2>/dev/null | head -c 0
ls -la /srv/medradar/var/lib 2>/dev/null
ls -la /srv/medradar/var/lib/medradar-pipeline 2>/dev/null | head

sec "HEALTH_SCRIPT"
ls -la /usr/local/bin/medradar-health /usr/local/bin/medradar-backup 2>/dev/null
head -60 /usr/local/bin/medradar-health 2>/dev/null

sec "END"
date -u +%FT%TZ
