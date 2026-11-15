#!/usr/bin/env bash
# MedRadar health adapter for the DATA-002 layered health contract.
# Proposal only; replacing /usr/local/bin/medradar-health requires deployment approval.
set -u
APP="${MEDRADAR_HEALTH_URL:-http://127.0.0.1:8787}"
STATE="${MEDRADAR_HEALTH_STATE:-/var/lib/medradar-health}"
mkdir -p "$STATE"
ts=$(date -Is)
live_code=$(curl -s -o /tmp/medradar-livez.$$ -m 5 -w '%{http_code}' "$APP/api/livez" 2>/dev/null || echo 000)
ready_code=$(curl -s -o /tmp/medradar-readyz.$$ -m 8 -w '%{http_code}' "$APP/api/readyz" 2>/dev/null || echo 000)
health_code=$(curl -s -o /tmp/medradar-health.$$ -m 8 -w '%{http_code}' "$APP/api/health" 2>/dev/null || echo 000)
parse=$(python3 - "$APP" "$live_code" "$ready_code" "$health_code" "$STATE/last.json" <<'PY'
import json, sys, urllib.request
app, live_code, ready_code, health_code, out = sys.argv[1:6]
def load(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, json.loads(response.read().decode())
    except Exception as error:
        return 0, {"error": str(error)}
_, ready = load(app + "/api/readyz")
_, health = load(app + "/api/health")
checks = health.get("checks") or {}
sync = checks.get("sync") or {}
fresh = checks.get("freshness") or {}
data = checks.get("data") or {}
status = health.get("status") or "unavailable"
if status == "not_ready" or ready_code != "200":
    exit_code = 2
elif status in ("degraded", "unknown"):
    exit_code = 1
else:
    exit_code = 0
payload = {
    "ts": health.get("generated_at"),
    "status": status,
    "http": {"livez": live_code, "readyz": ready_code, "health": health_code},
    "ready": ready.get("ready"),
    "data_state": data.get("state"),
    "using_fallback": data.get("using_fallback"),
    "sync_state": sync.get("state"),
    "latest_run_status": sync.get("latest_run_status"),
    "failed_sources": sync.get("failed_sources", []),
    "pending_sources": sync.get("pending_sources", []),
    "freshness_state": fresh.get("state"),
    "latest_official_version": fresh.get("latest_official_version"),
}
with open(out, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
    handle.write("\n")
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
sys.exit(exit_code)
PY
)
rc=$?
rm -f /tmp/medradar-livez.$$ /tmp/medradar-readyz.$$ /tmp/medradar-health.$$
echo "$parse"
if [ "$rc" -ne 0 ]; then
  logger -t medradar-health -p user.warning "medradar health layered state rc=$rc"
fi
exit "$rc"
