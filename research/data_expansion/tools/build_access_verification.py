#!/usr/bin/env python
"""Generate ACCESS_VERIFICATION.json from the probe evidence on disk.

This is the machine-readable counterpart of the narrative report: for every
source it records what was actually requested, what came back, and what the
resulting verdict was — including the failures, which are the part that makes
the successes meaningful.

Nothing here is written by hand, and nothing here can claim more than the probe
directory contains.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources import timeq  # noqa: E402

OUT = ROOT / "ACCESS_VERIFICATION.json"

STATUS_ORDER = {
    "VERIFIED_API": 0,
    "VERIFIED_BULK_DOWNLOAD": 1,
    "VERIFIED_PUBLIC_QUERY": 2,
    "REQUIRES_REGISTRATION": 3,
    "PAID_ONLY": 4,
    "BLOCKED_BY_POLICY": 5,
    "UNAVAILABLE": 6,
    "NOT_TESTED": 7,
}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"unparsable_line": line[:200]})
    return rows


def summarise_requests(entries: list[dict]) -> dict:
    statuses = [e.get("status") for e in entries]
    return {
        "requests": len(entries),
        "http_2xx": sum(1 for s in statuses if isinstance(s, int) and 200 <= s < 300),
        "http_4xx": sum(1 for s in statuses if isinstance(s, int) and 400 <= s < 500),
        "http_5xx": sum(1 for s in statuses if isinstance(s, int) and 500 <= s < 600),
        "transport_errors": sum(1 for s in statuses if s is None),
        "with_error_text": sum(1 for e in entries if e.get("error")),
        "total_bytes": sum(int(e.get("bytes", 0) or 0) for e in entries),
        "max_elapsed_ms": max((int(e.get("elapsed_ms", 0) or 0) for e in entries), default=0),
    }


def build() -> dict:
    probes_dir = ROOT / "probes"
    sources: list[dict] = []
    for directory in sorted(p for p in probes_dir.glob("*") if p.is_dir()):
        result_path = directory / "PROBE_RESULT.json"
        entries = read_jsonl(directory / "requests.jsonl")
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
        else:
            result = {
                "source_id": directory.name,
                "status": "NOT_TESTED",
                "verified_at": "",
                "notes": "probe directory exists but no PROBE_RESULT.json was written",
                "evidence_urls": [],
                "probes": [],
                "error": "",
            }
        notes_path = directory / "NOTES.md"
        sources.append(
            {
                "source_id": result.get("source_id", directory.name),
                "status": result.get("status", "NOT_TESTED"),
                "verified_at": result.get("verified_at", ""),
                "probe_count": len(result.get("probes", []) or []),
                "evidence_urls": result.get("evidence_urls", []) or [],
                "notes": result.get("notes", ""),
                "error": result.get("error", ""),
                "has_noted_md": notes_path.exists(),
                "request_summary": summarise_requests(entries),
                "request_log": str((directory / "requests.jsonl").relative_to(ROOT)),
                "probe_result": str(result_path.relative_to(ROOT)) if result_path.exists() else "",
                "probes": [
                    {
                        "name": p.get("name", ""),
                        "url": p.get("url", ""),
                        "status": p.get("status"),
                        "ok": p.get("ok"),
                        "bytes": p.get("bytes", 0),
                        "elapsed_ms": p.get("elapsed_ms", 0),
                        "error": p.get("error", ""),
                        # response structure, when the probe recorded one: this is
                        # what makes "the fields match the documentation" checkable
                        # without storing the payload itself
                        "structure": p.get("structure"),
                        "sample": p.get("sample"),
                        "findings": p.get("findings"),
                    }
                    for p in (result.get("probes", []) or [])
                ],
            }
        )

    sources.sort(key=lambda s: (STATUS_ORDER.get(s["status"], 99), s["source_id"]))
    totals = {
        "sources_with_probe_directory": len(sources),
        "requests": sum(s["request_summary"]["requests"] for s in sources),
        "bytes": sum(s["request_summary"]["total_bytes"] for s in sources),
        "by_status": {},
        "failed_requests": sum(
            s["request_summary"]["http_4xx"]
            + s["request_summary"]["http_5xx"]
            + s["request_summary"]["transport_errors"]
            for s in sources
        ),
    }
    for source in sources:
        totals["by_status"][source["status"]] = totals["by_status"].get(source["status"], 0) + 1
    return {
        "schema": "medradar.external.access_verification.v1",
        "generated_at": timeq.utc_iso(),
        "policy": {
            "single_user_agent": "MedRadar-Research/1.0 (academic, non-commercial)",
            "per_source_request_budget": "<= 20 requests per source per probe (protocol)",
            "no_registration": True,
            "no_payment": True,
            "no_access_control_bypass": True,
            "retries": "bounded (max 2) and only for 429/5xx/transport errors",
            "failure_logging": "every request, including failures, is in requests.jsonl",
        },
        "totals": totals,
        "sources": sources,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    payload = build()
    out = Path(args.out)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print(json.dumps(payload["totals"]["by_status"], indent=2))
    print(f"requests={payload['totals']['requests']} bytes={payload['totals']['bytes']} "
          f"failed_requests={payload['totals']['failed_requests']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
