"""Robots.txt and rate discipline for the recruitment lane.

The recruitment collector must be able to *prove* it was allowed to read a path,
not merely claim it in a doc. Two things are enforced here:

* ``robots_allows()`` — a longest-match Robots Exclusion Protocol reading for a
  generic user agent, with wildcard patterns handled explicitly;
* ``CollectionPolicy`` — the per-host interval and per-run request ceiling that a
  collection run may not exceed, plus the verbatim robots rule that authorised
  each host, so the authorisation is stored next to the data.

This is deliberately small and does not try to be a general crawler: it answers
one question ("may I GET this path once?") for hosts we have already identified
as public career sites.
"""
from __future__ import annotations

import fnmatch
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

#: Default UA. We identify the client honestly in the `From` header; career sites
#: serve browsers, so the UA is a browser string for rendering correctness.
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
FROM_HEADER = "MedRadar recruitment research (academic; contact: repository owner)"


def parse_robots(text: str) -> list[dict[str, Any]]:
    """Parse robots.txt into groups. Unknown directives are ignored."""
    groups: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    last_was_agent = False
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if current is None or not last_was_agent:
                current = {"agents": [], "allow": [], "disallow": []}
                groups.append(current)
            current["agents"].append(value.lower())
            last_was_agent = True
        elif key == "allow" and current is not None:
            current["allow"].append(value)
            last_was_agent = False
        elif key == "disallow" and current is not None:
            current["disallow"].append(value)
            last_was_agent = False
        else:
            last_was_agent = False
    return groups


def _rule_matches(rule: str, path: str) -> bool:
    if not rule:
        return False  # an empty Disallow means "allow everything"
    if "*" in rule or "$" in rule:
        pattern = rule[:-1] if rule.endswith("$") else rule
        return fnmatch.fnmatch(path, pattern)
    return path.startswith(rule)


def robots_allows(groups: list[dict[str, Any]], path: str, agent: str = "*") -> dict[str, Any]:
    """Longest-match decision for one path, with the winning rule returned."""
    applicable = [g for g in groups if agent.lower() in g["agents"]]
    if not applicable:
        applicable = [g for g in groups if "*" in g["agents"]]
    if not applicable:
        return {"allowed": True, "rule": None, "reason": "no group applies; robots leaves the path unrestricted"}
    candidates: list[tuple[int, str, str]] = []
    for g in applicable:
        for rule in g["allow"]:
            if _rule_matches(rule, path):
                candidates.append((len(rule), "allow", rule))
        for rule in g["disallow"]:
            if _rule_matches(rule, path):
                candidates.append((len(rule), "disallow", rule))
    if not candidates:
        return {"allowed": True, "rule": None, "reason": "no matching rule"}
    candidates.sort(key=lambda c: (c[0], c[1] == "allow"), reverse=True)
    _, kind, rule = candidates[0]
    return {"allowed": kind == "allow", "rule": rule, "reason": f"{kind} rule {rule!r} is the longest match"}


@dataclass
class CollectionPolicy:
    """Bound every collection run: politeness, ceilings, and the rules that allowed it."""

    min_interval_s: float = 1.0
    max_requests: int = 1500
    max_postings: int = 400
    timeout_s: float = 45.0
    #: host -> {"robots_url":..., "status":..., "rules": {...}, "raw_head":...}
    robots_evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def record_robots(self, url: str, status: int | None, text: str) -> dict[str, Any]:
        host = urllib.parse.urlsplit(url).netloc.lower()
        groups = parse_robots(text)
        evidence = {
            "robots_url": url,
            "status": status,
            "n_groups": len(groups),
            "raw_head": (text or "")[:800],
            "groups": groups,
        }
        self.robots_evidence[host] = evidence
        return evidence

    def assert_allowed(self, url: str, path: str) -> dict[str, Any]:
        host = urllib.parse.urlsplit(url).netloc.lower()
        evidence = self.robots_evidence.get(host)
        if evidence is None:
            raise PermissionError(f"no robots.txt evidence recorded for {host}; refusing to collect")
        decision = robots_allows(evidence["groups"], path)
        if not decision["allowed"]:
            raise PermissionError(f"robots.txt disallows {path} on {host}: {decision['reason']}")
        return decision

    def as_dict(self) -> dict[str, Any]:
        return {
            "min_interval_s": self.min_interval_s,
            "max_requests": self.max_requests,
            "max_postings": self.max_postings,
            "timeout_s": self.timeout_s,
            "robots_evidence": self.robots_evidence,
            "notes": self.notes,
        }
