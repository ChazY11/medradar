"""Source register.

One JSON file per source under ``registry/sources/``. The register is the
authoritative statement of *what we are allowed to do* with a source and *what
stopped us when we could not*. Probe results and exports must cite it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from typing import Any

ACCESS_STATES = {
    "OPEN",                 # no key, no registration, machine readable
    "OPEN_DOCUMENTED",      # no key, machine readable, published format/licence
    "REQUIRES_REGISTRATION",  # free account / API key needed
    "REQUIRES_LICENCE",     # paid or contractual
    "BLOCKED_TECHNICAL",    # WAF / anti-automation / retired endpoint
    "BLOCKED_LEGAL",        # terms forbid automated collection
    "MANUAL_ONLY",          # human search interface only
    "UNKNOWN",
}


@dataclass
class SourceEntry:
    source_id: str
    name: str
    operator: str
    domain: str
    access_state: str
    access_evidence: str = ""
    machine_interface: str = ""      # e.g. "REST JSON", "gzip sitemap + HTML"
    auth_required: bool = False
    registration_url: str | None = None
    rate_policy: str = ""
    licence_status: str = "unknown"
    licence_url: str | None = None
    licence_note: str = ""
    robots_url: str | None = None
    robots_summary: str = ""
    bulk_available: bool = False
    historical_depth: str = ""
    first_verified_at: str = ""
    what_is_new: str = ""            # what this adds that we did not have
    id_schemes: list[str] = field(default_factory=list)
    entity_types: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    unlock_route: str = ""
    probe_suite: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> None:
        if self.access_state not in ACCESS_STATES:
            raise ValueError(f"{self.source_id}: bad access_state {self.access_state!r}")
        if self.auth_required and self.access_state == "OPEN":
            raise ValueError(
                f"{self.source_id}: auth_required=True contradicts access_state=OPEN"
            )


def write_entry(root: str, entry: SourceEntry) -> str:
    entry.validate()
    d = os.path.join(root, "registry", "sources")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{entry.source_id}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(entry.to_dict(), fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    return path


def load_all(root: str) -> list[dict]:
    d = os.path.join(root, "registry", "sources")
    out = []
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            with open(os.path.join(d, fn), "r", encoding="utf-8") as fh:
                out.append(json.load(fh))
    return out


def index(root: str) -> dict:
    entries = load_all(root)
    by_state: dict[str, int] = {}
    for e in entries:
        by_state[e["access_state"]] = by_state.get(e["access_state"], 0) + 1
    return {
        "total_sources": len(entries),
        "by_access_state": dict(sorted(by_state.items())),
        "sources": [
            {
                "source_id": e["source_id"],
                "access_state": e["access_state"],
                "licence_status": e["licence_status"],
                "bulk_available": e["bulk_available"],
                "entity_types": e["entity_types"],
            }
            for e in entries
        ],
    }
