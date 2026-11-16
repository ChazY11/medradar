#!/usr/bin/env bash
# MedRadar health adapter for the DATA-003 layered health contract.
#
# Proposal only. Installing this over /usr/local/bin/medradar-health is a production change
# that requires the approval in docs/data/data_003/DEPLOYMENT_CHANGE_REQUEST.md.
#
# Why v3: CLOUD-003's adapter treated HTTP 200 as "ok" and had no concept of a deferred sync or
# an in-flight snapshot activation. It could therefore report status=ok while the pipeline was
# deliberately not syncing, and it could not distinguish "serving the previous snapshot" from
# "healthy on the current snapshot".
#
# Exit codes: 0 ok, 1 warning (degraded/deferred/unknown/fallback), 2 critical (not ready or the
# web does not answer). The systemd timer keeps running (exit code is informational), but the
# status line, the JSON state file and the journal show the layering.
set -u
APP="${MEDRADAR_HEALTH_URL:-http://127.0.0.1:8787}"
STATE="${MEDRADAR_HEALTH_STATE:-/var/lib/medradar-health}"
mkdir -p "$STATE" 2>/dev/null || true
ts=$(date -Is)
live_code=$(curl -s -o /dev/null -m 5 -w '%{http_code}' "$APP/api/livez" 2>/dev/null || echo 000)
ready_code=$(curl -s -o /dev/null -m 8 -w '%{http_code}' "$APP/api/readyz" 2>/dev/null || echo 000)
health_code=$(curl -s -o /dev/null -m 8 -w '%{http_code}' "$APP/api/health" 2>/dev/null || echo 000)
data_code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$APP/api/data-status" 2>/dev/null || echo 000)

python3 - "$APP" "$STATE" "$ts" "$live_code" "$ready_code" "$health_code" "$data_code" <<'PY'
import json
import os
import sys
import urllib.request

app, state_dir, ts, live_code, ready_code, health_code, data_code = sys.argv[1:8]


def fetch(path, timeout=8):
    try:
        with urllib.request.urlopen(app + path, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except Exception as error:  # noqa: BLE001 - a probe must never crash the timer
        return 0, {"error": type(error).__name__ + ": " + str(error)}


_, ready = fetch("/api/readyz")
_, health = fetch("/api/health")
_, status = fetch("/api/data-status", timeout=15)

checks = (health.get("checks") or {}) if isinstance(health, dict) else {}
data = checks.get("data") or {}
activation = checks.get("activation") or {}
sync = checks.get("sync") or {}
fresh = checks.get("freshness") or {}
deferral = (status.get("synchronization") or {}).get("deferral") if isinstance(status, dict) else None
activation_detail = health.get("activation") if isinstance(health, dict) else None

# Host facts that HTTP cannot express.
mem = {}
try:
    with open("/proc/meminfo", "r", encoding="utf-8") as handle:
        for line in handle:
            key, _, rest = line.partition(":")
            if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                mem[key] = int(rest.strip().split()[0]) // 1024
except OSError:
    pass
psi = None
try:
    with open("/proc/pressure/memory", "r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("some "):
                for part in line.split()[1:]:
                    key, _, value = part.partition("=")
                    if key == "avg10":
                        psi = float(value)
except OSError:
    pass

issues = []
if live_code != "200":
    issues.append("livez:" + str(live_code))
if ready_code != "200":
    issues.append("readyz:" + str(ready_code))
if health_code != "200":
    issues.append("health:" + str(health_code))
if data.get("state") == "degraded":
    issues.append("dataset:degraded")
if data.get("using_fallback"):
    issues.append("dataset:fallback")
activation_state = str(activation.get("state") or "ok")
if activation_state == "degraded":
    detail = activation_detail.get("detail") if isinstance(activation_detail, dict) else None
    issues.append("activation:degraded" + (":" + str(detail) if detail else ""))
sync_state = str(sync.get("state") or "unknown")
if sync_state == "deferred":
    reasons = ",".join((deferral or {}).get("reasons") or [])
    issues.append("sync:deferred" + (":" + reasons if reasons else ""))
elif sync_state in ("degraded", "stale"):
    issues.append("sync:" + sync_state)
if fresh.get("state") in ("degraded", "stale"):
    issues.append("freshness:" + str(fresh.get("state")))
if mem.get("MemAvailable", 10**9) < 300:
    issues.append("mem_available:" + str(mem.get("MemAvailable")) + "MB")
if psi is not None and psi >= 10.0:
    issues.append("psi_mem:" + str(psi))

# Severity: critical when the web cannot serve a dataset; warning for a real but survivable
# state (fallback, deferred sync, stale source, activation failed).
critical = ready_code != "200" or live_code != "200" or data.get("state") in ("unavailable",)
warning = any(item for item in issues if not item.startswith("livez:"))
if critical:
    overall = "critical"
    exit_code = 2
elif warning:
    overall = "warn"
    exit_code = 1
else:
    overall = "ok"
    exit_code = 0

payload = {
    "ts": ts,
    "status": overall,
    "http": {"livez": live_code, "readyz": ready_code, "health": health_code, "data_status": data_code},
    "snapshot": ((health.get("snapshot") or {}).get("id") if isinstance(health, dict) else None),
    "data_state": data.get("state"),
    "using_fallback": bool(data.get("using_fallback")),
    "dataset_error": data.get("error"),
    "activation_state": activation_state,
    "activation_detail": activation_detail,
    "pending_snapshot": (activation_detail or {}).get("pending_snapshot") if isinstance(activation_detail, dict) else None,
    "sync_state": sync_state,
    "sync_latest_run": sync.get("latest_run_status"),
    "sync_deferral": deferral,
    "freshness_state": fresh.get("state"),
    "latest_official_version": fresh.get("latest_official_version"),
    "mem_total_mb": mem.get("MemTotal"),
    "mem_available_mb": mem.get("MemAvailable"),
    "swap_total_mb": mem.get("SwapTotal"),
    "swap_free_mb": mem.get("SwapFree"),
    "psi_mem_some_avg10": psi,
    "issues": issues,
}
try:
    with open(os.path.join(state_dir, "last.json"), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
except OSError:
    pass

print(
    "%s status=%s http=%s/%s/%s data=%s fallback=%s activation=%s sync=%s mem_avail=%sMB swap_free=%sMB psi=%s issues=%s"
    % (
        ts,
        overall,
        live_code,
        ready_code,
        health_code,
        data.get("state"),
        "yes" if data.get("using_fallback") else "no",
        activation_state,
        sync_state,
        mem.get("MemAvailable", "?"),
        mem.get("SwapFree", "?"),
        "?" if psi is None else psi,
        ",".join(issues) or "none",
    )
)
sys.exit(exit_code)
PY
rc=$?
if [ "$rc" -ne 0 ]; then
  logger -t medradar-health -p user.warning "medradar health state rc=$rc"
fi
exit 0
