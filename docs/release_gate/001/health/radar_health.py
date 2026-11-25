#!/usr/bin/env python3
"""MedRadar Radar health probe - candidate monitoring (RELEASE-GATE-001, Phase 4).

Three layers, because "HTTP 200" is not health:

  1. availability - process, port, API answer, ledger readable, SPA asset present;
  2. pipeline     - per-source success/failure, watermark legality, future timestamps,
                    incremental progress, scheduler heartbeat;
  3. product trust- ledger schema, admission projection, recall channel, brief generation,
                    known data anomalies.

Layers 2 and 3 come from the product's own system_status(); this probe adds what the product
cannot see about itself (liveness, the served bundle) and the checks that only make sense from
outside.

Exit code: 0 for HEALTHY/DEGRADED, 1 for UNHEALTHY, 2 for UNKNOWN. It always writes a JSON
snapshot to --state-file so a failure is observable even without a notification channel.
No notification channel is configured; that is reported, not hidden.
"""
from __future__ import annotations

import argparse, base64, json, os, socket, sys, time, urllib.error, urllib.request

BT = chr(96)


def _http(url, timeout=10, headers=None, *, attempts=1, delay=0.0):
    """One HTTP check, optionally retried.

    The probe runs from a five-minute timer, so a single sample decides the light. Measured: every
    deploy restarted the web service for ~18 s and whichever sample landed inside that window marked
    the unit failed - 03:43:17 failed, 03:38 and 03:48 finished - with nothing wrong to report. A
    deployment is not an outage, so availability checks retry across a window wide enough to cover a
    restart; the retry counts are reported so a reader can still see it was not first-try.
    """
    started = time.time()
    last = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            request = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                return {"ok": True, "status": response.status,
                        "ms": round((time.time() - started) * 1000, 1), "bytes": len(body),
                        "attempts": attempt, "body": body}
        except urllib.error.HTTPError as error:
            # A served error is an answer: retrying a 500 five times only delays the report.
            return {"ok": False, "status": error.code, "error": "HTTP " + str(error.code),
                    "ms": round((time.time() - started) * 1000, 1), "attempts": attempt}
        except Exception as error:
            last = {"ok": False, "status": None,
                    "error": type(error).__name__ + ": " + str(error)[:160],
                    "ms": round((time.time() - started) * 1000, 1), "attempts": attempt}
            if attempt < attempts and delay:
                time.sleep(delay)
    return last


def _port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def _worst(checks):
    statuses = {item.get("status") for item in checks}
    if "FAIL" in statuses:
        return "UNHEALTHY"
    if "WARN" in statuses:
        return "DEGRADED"
    if not statuses or statuses == {"UNKNOWN"}:
        return "UNKNOWN"
    return "HEALTHY"


def layer_availability(args):
    checks = []
    # A deploy restarts the web service for about eighteen seconds. Retrying across thirty covers
    # that without hiding a genuine outage: an app that is really down still fails all five attempts
    # and the recorded error names the connection failure.
    attempts = int(getattr(args, "retry_attempts", 5) or 1)
    delay = float(getattr(args, "retry_delay", 6.0) or 0.0)
    checks.append({"id": "port", "ok": _port_open("127.0.0.1", args.port),
                   "detail": "127.0.0.1:" + str(args.port)})
    healthz = _http(args.healthz_url, attempts=attempts, delay=delay)
    checks.append({"id": "healthz", "ok": healthz["ok"] and healthz.get("status") == 200,
                   "detail": (healthz.get("error") or ("200 in " + str(healthz["ms"]) + " ms"))
                             + (" (after " + str(healthz.get("attempts")) + " attempts)"
                                if (healthz.get("attempts") or 1) > 1 else "")})
    # The alpha gate protects the API on loopback too, and it counts every unauthenticated call as
    # a failed credential: a probe that calls the gated API every few minutes eventually locks the
    # loopback address out (measured: HTTP 429 after a handful of runs), which then looks exactly
    # like an outage. Liveness is therefore verified through /healthz, which the gate leaves open
    # on purpose, and correctness through the ledger the API reads. An authenticated probe is
    # opt-in, for manual runs, so no credential is ever needed by the timer.
    if args.api_probe:
        basic = base64.b64encode(args.api_probe.encode("utf-8")).decode("ascii")
        health = _http(args.base_url + "/api/radar/health", timeout=60,
                       headers={"Authorization": "Basic " + basic})
        checks.append({"id": "api_health", "ok": health["ok"] and health.get("status") == 200,
                       "detail": health.get("error") or "200"})
    else:
        checks.append({"id": "api_probe", "ok": True,
                       "detail": ("skipped: the alpha gate protects the API and counts"
                                  " unauthenticated calls as failed credentials; liveness is"
                                  " verified through /healthz and the ledger is read directly")})
    if args.web_dir:
        index = os.path.join(args.web_dir, "index.html")
        checks.append({"id": "spa_index", "ok": os.path.isfile(index),
                       "detail": index if os.path.isfile(index) else "missing " + index})
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--radar-dir", required=True)
    parser.add_argument("--port", type=int, default=8792)
    parser.add_argument("--base-url", default="http://127.0.0.1:8792")
    parser.add_argument("--healthz-url", default="http://127.0.0.1:8792/healthz")
    parser.add_argument("--retry-attempts", type=int, default=5,
                        help="availability attempts; 5 x 6 s covers a service restart on deploy")
    parser.add_argument("--retry-delay", type=float, default=6.0)
    parser.add_argument("--web-dir", default=None)
    parser.add_argument("--api-probe", default=None,
                        help="user:password for an authenticated API probe (manual runs only)")
    parser.add_argument("--state-file", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, os.environ.get("MEDRADAR_CODE_ROOT", ""))
    availability = layer_availability(args)

    pipeline = {"checks": [], "state": "UNKNOWN"}
    product = {"checks": [], "state": "UNKNOWN"}
    ledger = None
    try:
        from medradar.radar.health import system_status
        from medradar.radar.ledger import ObservationLedger
        from medradar.radar.paths import radar_paths
        from medradar.radar.taxonomy import load_taxonomy

        paths = radar_paths(args.radar_dir)
        ledger = ObservationLedger(paths.ledger, create=False, read_only=True)
        payload = system_status(ledger, None, load_taxonomy())
        by_id = {item["id"]: item for item in payload["verdict"]["checks"]}
        pipeline["checks"] = [by_id[key] for key in
                              ("critical_sources", "watermark_legal", "scheduler_heartbeat",
                               "acquisition_progress") if key in by_id]
        pipeline["state"] = _worst(pipeline["checks"])
        product["checks"] = [by_id[key] for key in
                             ("ledger_integrity", "ledger_writable") if key in by_id]
        product["state"] = payload["state"]
        product["source_states"] = [
            {"source_id": row["source_id"], "status": row["status"],
             "watermark": row["watermark"], "last_success": row["last_success_check_at"],
             "failures": row["consecutive_failures"]}
            for row in payload["sources"]]

        # Recall channel: the product's first promise. Presence and freshness are separate.
        recall = [row for row in payload["sources"] if row["source_id"] == "openfda_recall"]
        recall_total = 0
        if ledger is not None:
            try:
                recall_total = int(ledger.con.execute(
                    "SELECT COUNT(*) FROM observation WHERE source='openfda_recall'").fetchone()[0])
            except Exception:
                recall_total = 0
        product["checks"].append({
            "id": "recall_channel", "status": "PASS" if recall and recall_total else "FAIL",
            "severity": "CRITICAL",
            "detail": ("recall channel present with " + str(recall_total) + " records")
                      if recall and recall_total
                      else "the recall channel has never collected a record",
            "observed": {"source_rows": len(recall), "records": recall_total}})

        # Brief generation is the product surface; it must still work.
        started = time.time()
        try:
            from medradar.radar.intelligence import build_brief
            import datetime as dt
            today = dt.date.today()
            brief = build_brief(ledger, start=(today - dt.timedelta(days=7)).isoformat(),
                                end=today.isoformat(),
                                generated_at=dt.datetime.now(dt.timezone.utc).replace(
                                    microsecond=0).isoformat())
            product["checks"].append({
                "id": "brief_generation", "status": "PASS", "severity": "CRITICAL",
                "detail": "generated in " + str(round(time.time() - started, 2)) + " s",
                "observed": {"items": len(brief.as_dict().get("intelligence") or [])}})
        except Exception as error:
            product["checks"].append({
                "id": "brief_generation", "status": "FAIL", "severity": "CRITICAL",
                "detail": type(error).__name__ + ": " + str(error)[:200]})
    except Exception as error:
        product["checks"].append({
            "id": "ledger_open", "status": "FAIL", "severity": "CRITICAL",
            "detail": type(error).__name__ + ": " + str(error)[:200]})
    finally:
        if ledger is not None:
            ledger.close()

    # The product's own verdict covers its six checks. The checks added here (recall channel, brief
    # generation) are extra critical ones, so the overall verdict must re-derive from all of them
    # rather than trust the product's state - otherwise a missing safety channel would be reported
    # next to a green light, which is the exact defect this monitoring exists to prevent.
    failed_availability = [c for c in availability if not c["ok"]]
    if failed_availability:
        overall = "UNHEALTHY"
    elif any(c["status"] == "FAIL" and c.get("severity") == "CRITICAL"
             for c in product["checks"]):
        overall = "UNHEALTHY"
    elif any(c["status"] == "FAIL" for c in product["checks"]):
        overall = "DEGRADED"
    elif product["state"] in ("UNHEALTHY", "DEGRADED"):
        overall = product["state"]
    elif any(c["status"] == "WARN" and c.get("severity") in ("CRITICAL", "MAJOR")
             for c in product["checks"]):
        overall = "DEGRADED"
    elif product["state"] == "UNKNOWN":
        overall = "UNKNOWN"
    else:
        overall = "HEALTHY"
    product["state"] = overall if overall in ("UNHEALTHY", "DEGRADED") else product["state"]

    payload = {
        "state": overall,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "radar_dir": args.radar_dir,
        "layers": {"availability": availability, "pipeline": pipeline, "product": product},
        "notification_channel": "none configured - failures are recorded here and in the journal",
    }
    if args.state_file:
        with open(args.state_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str)
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(overall, "-", "; ".join(
            [c["id"] + ":" + ("ok" if c["ok"] else "failed") for c in availability]))
    return 0 if overall in ("HEALTHY", "DEGRADED") else (1 if overall == "UNHEALTHY" else 2)


def _crash_report(error, args):
    """A probe that dies must not leave the previous verdict on disk."""
    payload = {
        "state": "UNKNOWN",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "radar_dir": getattr(args, "radar_dir", None),
        "probe_error": type(error).__name__ + ": " + str(error)[:400],
        "layers": {"availability": [], "pipeline": {"checks": []}, "product": {"checks": []}},
        "notification_channel": "none configured",
    }
    state_file = getattr(args, "state_file", None)
    if state_file:
        try:
            with open(state_file, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, default=str)
        except Exception:
            pass
    print(json.dumps(payload, indent=2, default=str))
    return 2


if __name__ == "__main__":
    import sys as _sys
    _args = None
    try:
        _sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _error:  # noqa: BLE001 - the probe must report its own failure
        _crash_report(_error, _args)
        raise SystemExit(2)