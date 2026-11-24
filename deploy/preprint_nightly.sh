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

echo "[$(date -Is)] preprint pass"
"$PY" "$REL/tools/fulltext.py" --source preprints --days 21 --limit 200 --out "$OUT" 2>&1 | tail -12

echo "[$(date -Is)] re-index papers"
"$PY" "$REL/tools/papers_index.py" --corpus "$OUT" 2>&1 | tail -4

echo "[$(date -Is)] patent probe (google)"
"$PY" "$REL/tools/google_patents.py" --top-companies 12 --pages 1 2>&1 | tail -6 || true

# The technology-map page is served from this snapshot. Measured: computing it live over 122k nodes
# took longer than two minutes, and the answer cannot change faster than the 300 s scheduler cycle.
echo "[$(date -Is)] technology map snapshot"
"$PY" "$REL/tools/build_map.py" --radar "${MEDRADAR_RADAR_DIR:-/srv/medradar/data/radar}" \
  --out "${MEDRADAR_RADAR_DIR:-/srv/medradar/data/radar}/map_page.json" 2>&1 | tail -3 || true

echo "[$(date -Is)] done: $(ls "$OUT"/*.json 2>/dev/null | wc -l) records"
exit 0
