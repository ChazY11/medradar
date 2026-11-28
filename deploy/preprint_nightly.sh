#!/bin/sh
# MedRadar nightly acquisition pass. Deployed as /srv/medradar/intel/preprint_nightly.sh and run by
# medradar-preprint.timer (04:20 + up to 15 minutes of jitter).
#
# Preprints: measured 2026-11-24 - 400 records at 1 request/second earned a 429 that escalated to
# 403 and stayed there; the same code at 0.5 requests/second stored 20 of 20 from a residential
# address. This job is slow and small on purpose, and it is idempotent: records already in the
# corpus are skipped, so a blocked night costs nothing but a no-op.
#
# Patents: the Google Patents lane has answered 503 to this host and to a residential line since
# the probing on 2026-11-24, and EPO OPS waits on an administrator (reference 51279). The attempt
# below is deliberately tiny - twelve applicants, one page - so that the day either source opens,
# the patent table starts filling without an operator remembering to run anything.
#
# Exit status is always 0. A blocked night is a normal outcome and must not turn the unit red; what
# happened is in the log and in the corpus itself.
set -u
REL=${MEDRADAR_RELEASE:-/srv/medradar/radar/releases/app-intel}
PY=${MEDRADAR_PYTHON:-/srv/medradar/radar-venv/bin/python}
OUT=${MEDRADAR_PAPERS:-/srv/medradar/intel/papers}

# Every step records what it did, in a file the web process reads. Every failure below is swallowed on
# purpose - a blocked source is a normal night - but a swallowed failure left no trace anyone could see:
# the patent lane returned 503 for a week before a health check noticed, not this pipeline.
LOG="$REL/tools/nightly_log.py"
# Step logs go in a private directory, not fixed names in /tmp: measured during a dry run, the job
# could not create /tmp/step_stats.log at all ("Permission denied") and then reported the numbers from
# a stale file left by an earlier run - a wrong count on the page, produced by a permissions problem.
WORK=$(mktemp -d "${TMPDIR:-/tmp}/medradar-nightly.XXXXXX") || WORK=/tmp
trap 'rm -rf "$WORK"' EXIT INT TERM
# MEDRADAR_NIGHTLY_DRY=1 marks the run as a rehearsal, so the page cannot present it as the night's work.
DRY_FLAG=""
[ "${MEDRADAR_NIGHTLY_DRY:-}" = "1" ] && DRY_FLAG="--dry"
RUN=$(MEDRADAR_RADAR_DIR=${MEDRADAR_RADAR_DIR:-/srv/medradar/data/radar} "$PY" "$LOG" start $DRY_FLAG 2>/dev/null || date -Is)
mark() { MEDRADAR_RADAR_DIR=${MEDRADAR_RADAR_DIR:-/srv/medradar/data/radar} "$PY" "$LOG" mark "$1" "$2" "$RUN" "$3" 2>/dev/null || true; }
grab() { grep -oE "$1" "$2" 2>/dev/null | head -1 | tr -d '\n'; }

# Two crawls must never run at once.
#
# Measured 2026-11-28: a manual backfill was running when the 04:31 timer fired, both wrote paper_pass
# and paper_field, and the ledger's scheduled run recorded one field instead of three because the manual
# loop had already consumed the other two. Worse, when runs are left alive they each trap
# `rm -rf "$WORK"` and delete work directories out from under the live one:
#   cannot create /tmp/medradar-nightly.Jhd8F2/step_patents_1.log: Directory nonexistent
#
# An exclusive create, not flock: flock -n did not block inside this script even though the same lines
# block when run by hand. This form is one syscall and was verified end to end before shipping - the
# isolated block, then the block behind this script's own preamble (mktemp, trap, nightly_log start),
# then this file with a live holder.
#
# No extra trap is installed: the cleanup trap above already owns EXIT, and a second one would replace
# it. A lock left by a killed run is cleared by the pid check on the next start.
LOCK="${MEDRADAR_RADAR_DIR:-/srv/medradar/data/radar}/preprint.lock"
if [ -f "$LOCK" ]; then
  HELD=$(cat "$LOCK" 2>/dev/null || echo "")
  if [ -n "$HELD" ] && kill -0 "$HELD" 2>/dev/null; then
    echo "[$(date -Is)] another run (pid $HELD) holds $LOCK - skipping"
    mark "skipped" ok "another nightly run is in progress (pid $HELD)"
    exit 0
  fi
  echo "[$(date -Is)] clearing stale lock (pid ${HELD:-unknown} is gone)"
  rm -f "$LOCK"
fi
( set -C; echo "$$" > "$LOCK" ) 2>/dev/null || {
  echo "[$(date -Is)] lost the race for $LOCK - skipping"
  mark "skipped" ok "another nightly run won the lock"
  exit 0
}

echo "[$(date -Is)] preprint pass"
"$PY" "$REL/tools/fulltext.py" --source preprints --days 21 --limit 200 --out "$OUT" > $WORK/step_preprints.log 2>&1
tail -12 $WORK/step_preprints.log
mark "preprints" ok "$(grab '"stored": [0-9]+' $WORK/step_preprints.log)"

# Patents: Google Patents answers in bursts - 12 companies filled 263 patents at 0.5 req/s, and the
# next batch thirty minutes later returned 503 to every company (measured 2026-11-25). So the job
# advances by a handful of NEW companies per night (--skip-covered) instead of retrying the same
# twelve forever. EPO OPS is still waiting on an administrator (reference 51279).
# Google Patents answers in windows rather than at a rate: measured one window where 2 of 3 companies
# answered and wrote 20 rows each, and then four consecutive rounds where 12 of 12 returned 503. One
# attempt a night therefore catches a window only by luck. Three attempts spread over half an hour,
# each aborting after two consecutive refusals, costs about a minute in total when the window is shut
# and seizes it when it is open.
for attempt in 1 2 3; do
  echo "[$(date -Is)] patent batch (google, skip covered) attempt $attempt"
  "$PY" "$REL/tools/google_patents.py" --top-companies 6 --pages 2 --skip-covered \
    --stop-after-failures 2 > $WORK/step_patents_$attempt.log 2>&1 || true
  tail -8 $WORK/step_patents_$attempt.log
  mark "patents:$attempt" ok "rows $(grep -c rows_written $WORK/step_patents_$attempt.log) · 503 $(grep -c TransientHttpError $WORK/step_patents_$attempt.log)"
  [ "$attempt" -lt 3 ] && sleep 600
done

# europepmc answered 200 while the preprint host and Google were both refusing this address, so it
# is the lane that actually adds papers on a blocked night: 20 candidates stored 9 new full texts.
# One fixed query saturated: on 2026-11-27 it drew 120 candidates of which 112 were cached, and it only
# ever covered orthopaedics while the register holds devices in twenty-one fields. Three fields a night,
# chosen by paper_passes.next_queries() - never-run fields first, then the ones yielding least.
# Measured: one field costs about two minutes at 120 candidates, so three keeps the night short.
echo "[$(date -Is)] paper pass (europepmc, rotating)"
"$PY" - <<'PICK' > "$WORK/paper_picks.txt" 2>/dev/null || true
from medradar.radar.paper_passes import next_queries
from medradar.radar.reference import UdiReference
import os
store = UdiReference(os.environ["MEDRADAR_REFERENCE_DB"])
try:
    for specialty, query in next_queries(store, count=3):
        print(f"{specialty}\t{query}")
finally:
    store.close()
PICK
# $'\t' is a bashism: under /bin/sh (dash) it is the literal three characters $\t, so the line was never
# split and the whole "Specialty<TAB>query" string became the specialty key. Measured in a dry run:
# paper_field gained rows keyed "Cardiovascular<TAB>cardiac implant OR vascular stent".
TAB=$(printf '\t')
while IFS="$TAB" read -r spec query; do
  [ -z "$spec" ] && continue
  echo "[$(date -Is)]   field: $spec"
  "$PY" "$REL/tools/fulltext.py" --source europepmc --query "$query" --limit 120 --out "$OUT" \
    --reference "${MEDRADAR_REFERENCE_DB}" --specialty "$spec" > "$WORK/step_papers_$spec.log" 2>&1 || true
  tail -6 "$WORK/step_papers_$spec.log"
  mark "papers:$spec" ok "$(grab '"stored": [0-9]+' "$WORK/step_papers_$spec.log")"
done < "$WORK/paper_picks.txt"

echo "[$(date -Is)] re-index papers"
"$PY" "$REL/tools/papers_index.py" --corpus "$OUT" > $WORK/step_index.log 2>&1 || true
tail -4 $WORK/step_index.log
# The count alone hid 270 files that could not be indexed; the note now carries why.
mark "papers:index" ok "$(grab '"papers_indexed": [0-9]+' $WORK/step_index.log) / files $(grab '"files_seen": [0-9]+' $WORK/step_index.log) / no-title $(grab '"skipped_no_title": [0-9]+' $WORK/step_index.log)"

# The technology-map page is served from this snapshot. Measured: computing it live over 122k nodes
# took longer than two minutes, and the answer cannot change faster than the 300 s scheduler cycle.
echo "[$(date -Is)] technology map snapshot"
"$PY" "$REL/tools/build_map.py" --radar "${MEDRADAR_RADAR_DIR:-/srv/medradar/data/radar}" \
  --out "${MEDRADAR_RADAR_DIR:-/srv/medradar/data/radar}/map_page.json" > $WORK/step_map.log 2>&1 || true
tail -3 $WORK/step_map.log
mark "map" ok "$(grab '"nodes": [0-9]+' $WORK/step_map.log)"

# The landing page reads these instead of counting 5.2M device rows and 785k paper rows on every
# visit. Measured: 1.8 s cold locally, 6.5 s through the tunnel, became 0.35 s. The page prints the
# timestamp this writes, so a stale set is visible.
echo "[$(date -Is)] materialised counts"
"$PY" "$REL/tools/store_stats.py" \
  --reference "${MEDRADAR_REFERENCE_DB:-/srv/medradar/reference_slim.db}" \
  --corpus "${MEDRADAR_CORPUS_DIR:-/srv/medradar/intel/corpus510k}" --refresh > $WORK/step_stats.log 2>&1 || true
tail -2 $WORK/step_stats.log
mark "counts" ok "$(grab '"papers": [0-9]+' $WORK/step_stats.log)"

echo "[$(date -Is)] done: $(ls "$OUT"/*.json 2>/dev/null | wc -l) records"
# Coverage has to advance or the caveat on /sources becomes a standing apology: the failure
# index covered 838 of 5,229 product codes and nothing in the deployment moved that number.
# Forty codes a night, lowest volume first by device count order, at 2 req/s.
# Two performance defects so far were a query keyed on a column without an index, both found by a page
# feeling slow. This asks SQLite for the plan of every statement the pages run and records how many scan
# a big table, so the next one is visible the night it appears instead of the month someone notices.
echo "[$(date -Is)] query audit"
"$PY" "$REL/tools/query_audit.py" \
  --db "${MEDRADAR_REFERENCE_DB:-/srv/medradar/reference_slim.db}" \
  --json > "$WORK/step_query.json" 2>&1 || true
FINDINGS=$("$PY" -c 'import json,sys;print(len(json.load(open(sys.argv[1])).get("findings",[])))' "$WORK/step_query.json" 2>/dev/null || echo "?")
mark "query audit" ok "findings $FINDINGS"

echo "$(date -Is) failure sweep"
"$PY" /srv/medradar/ops/sweep_failures.py \
  --db "${MEDRADAR_REFERENCE_DB:-/srv/medradar/reference_slim.db}" \
  --codes 40 --pages-per-code 2 --rate 2 --json > $WORK/step_sweep.log 2>&1 \
  || echo "$(date -Is) failure sweep failed"
tail -2 $WORK/step_sweep.log
mark "failure sweep" ok "$(grab '"swept": [0-9]+' $WORK/step_sweep.log)"

# The radar lane and the field index are two pipelines that only met by hand until round 98: `radar run`
# recorded papers into the ledger, the field pages read this directory, and nothing carried one into the
# other. Measured 2026-11-28: 190 observed records carried a PMCID and none was in the corpus.
#
# The chain is now a step: collect, fetch the full text of what was observed, index it, and link each paper
# to the field whose query found it. Every part is bounded and idempotent - a paper already in the corpus
# is skipped, and a link is a no-op the second time.
echo "[$(date -Is)] radar observation pass"
"$PY" -m medradar radar run --source europepmc --no-ai > $WORK/step_radar.log 2>&1 || true
tail -2 $WORK/step_radar.log
mark "radar run" ok "$(grep -cE '^europepmc' $WORK/step_radar.log 2>/dev/null || echo 0) source line(s)"

# Which PMCIDs the ledger has observed but the corpus does not hold. Capped at forty: the Open Access
# mirror is fast but this runs on the same night as everything else.
echo "[$(date -Is)] observed full text"
OBSERVED=$(MEDRADAR_RADAR_DIR=${MEDRADAR_RADAR_DIR:-/srv/medradar/data/radar} "$PY" - "$OUT" <<'PYEOF' 2>/dev/null
import sys
from pathlib import Path
from tools.link_observed import observed_papers

out = Path(sys.argv[1])
ids = [pmcid for group in observed_papers(Path(
    "/srv/medradar/data/radar/radar.db")).values() for pmcid in group]
missing = [pmcid for pmcid in dict.fromkeys(ids) if not (out / f"paper_{pmcid}.json").exists()]
print(",".join(missing[:40]))
PYEOF
)
if [ -n "$OBSERVED" ]; then
  "$PY" "$REL/tools/fulltext.py" --pmcids "$OBSERVED" --limit 40 --out "$OUT" \
    > $WORK/step_observed.log 2>&1 || true
  mark "observed full text" ok "$(grab '"stored":[ ]*[0-9]+' $WORK/step_observed.log) stored"
else
  mark "observed full text" ok "nothing new observed"
fi

echo "[$(date -Is)] index papers"
"$PY" "$REL/tools/papers_index.py" --corpus "$OUT" \
  --reference "${MEDRADAR_REFERENCE_DB:-/srv/medradar/reference_slim.db}" \
  > $WORK/step_index.log 2>&1 || true
tail -2 $WORK/step_index.log
mark "paper index" ok "$(grab '"papers_indexed":[ ]*[0-9]+' $WORK/step_index.log) indexed"

echo "[$(date -Is)] link observed papers to fields"
"$PY" "$REL/tools/link_observed.py" \
  --radar "${MEDRADAR_RADAR_DIR:-/srv/medradar/data/radar}/radar.db" \
  --reference "${MEDRADAR_REFERENCE_DB:-/srv/medradar/reference_slim.db}" \
  > $WORK/step_link.log 2>&1 || true
tail -2 $WORK/step_link.log
mark "field links" ok "$(grab 'linked [0-9]+ observations' $WORK/step_link.log) linked"

mark "done" ok "$(ls "$OUT"/*.json 2>/dev/null | wc -l) records"
exit 0
