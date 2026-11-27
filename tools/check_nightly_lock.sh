#!/bin/sh
# Prove the nightly guard does what it claims, on the machine that runs it at 04:31.
#
# Round 57 shipped a lock that blocked when run by hand and did not block inside the script, so it was
# reverted. This is the check that would have caught it: it extracts the guard from the script that
# actually runs and exercises the three states.
#
#   1. a live holder      -> the run must not proceed
#   2. a dead holder's pid -> the lock is stale and must be cleared
#   3. no lock             -> acquire it, and the file must name this run
#
# Usage: sh tools/check_nightly_lock.sh [path-to-preprint_nightly.sh]
# Exit 0 when all three hold; 1 with a message naming the case that failed.
set -u

SCRIPT=${1:-/srv/medradar/intel/preprint_nightly.sh}
[ -f "$SCRIPT" ] || { echo "no such script: $SCRIPT"; exit 1; }

START=$(grep -n '# Two crawls must never run at once' "$SCRIPT" | head -1 | cut -d: -f1)
END=$(grep -n 'preprint pass' "$SCRIPT" | head -1 | cut -d: -f1)
[ -n "$START" ] && [ -n "$END" ] || { echo "the guard block is not in $SCRIPT"; exit 1; }

WORK=$(mktemp -d "${TMPDIR:-/tmp}/lockcheck.XXXXXX") || exit 1
trap 'rm -rf "$WORK"' EXIT INT TERM

{
  echo '#!/bin/sh'
  echo 'set -u'
  echo 'mark() { :; }'
  sed -n "${START},$((END - 1))p" "$SCRIPT"
  echo 'echo PROCEEDED'
} > "$WORK/guard.sh"
chmod +x "$WORK/guard.sh"

run_guard() {
  MEDRADAR_RADAR_DIR="$WORK" sh "$WORK/guard.sh" 2>&1
}

# 1. live holder
echo "case 1: live holder"
sleep 30 &
HOLDER=$!
echo "$HOLDER" > "$WORK/preprint.lock"
OUT=$(run_guard)
echo "$OUT" | sed 's/^/  /'
echo "$OUT" | grep -q 'skipping' || { echo "FAIL: a live holder did not block the run"; kill $HOLDER; exit 1; }
echo "$OUT" | grep -q 'PROCEEDED' && { echo "FAIL: the run proceeded past a live holder"; kill $HOLDER; exit 1; }
kill $HOLDER 2>/dev/null
wait $HOLDER 2>/dev/null

# 2. stale lock
echo "case 2: stale lock"
echo 999999 > "$WORK/preprint.lock"
OUT=$(run_guard)
echo "$OUT" | sed 's/^/  /'
echo "$OUT" | grep -q 'clearing stale lock' || { echo "FAIL: a dead pid was not treated as stale"; exit 1; }
echo "$OUT" | grep -q 'PROCEEDED' || { echo "FAIL: the run did not proceed after a stale lock"; exit 1; }

# 3. no lock
echo "case 3: no lock"
rm -f "$WORK/preprint.lock"
OUT=$(run_guard)
echo "$OUT" | sed 's/^/  /'
echo "$OUT" | grep -q 'PROCEEDED' || { echo "FAIL: the run did not start with no lock"; exit 1; }
[ -s "$WORK/preprint.lock" ] || { echo "FAIL: no lock file was written"; exit 1; }
echo "  lock now holds $(cat "$WORK/preprint.lock")"

echo "PASS: the guard blocks a live run, clears a stale one, and acquires when free"
