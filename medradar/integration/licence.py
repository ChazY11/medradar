"""Licence gating for imported evidence.

Three different rights are routinely conflated, and conflating them is how a
project ends up redistributing data it was only allowed to query:

* **query** — may we call the API?
* **analyse** — may we compute over the records locally?
* **redistribute** — may the records (or a derived export) be published?

This module tracks all three.  A record may be *ingested* for analysis while
being *non-redistributable*; that is the normal case for
``open_no_explicit_licence`` sources.  A record with no confirmed redistribution
right is never written into a public artefact, and a ``terms_restricted`` record
is never ingested at all without an explicit, recorded human decision.

The authoritative policy lives in ``config/convergence/licence_policy.json``.
:data:`DEFAULT_POLICY` is the fail-closed fallback used when that file is absent,
so a missing policy can never silently widen access.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

#: ATLAS licence statuses that may be ingested for local analysis.
INGESTIBLE_LICENCE_STATUSES: frozenset[str] = frozenset(
    {"public_domain", "open_licence", "open_no_explicit_licence"}
)
#: ATLAS licence statuses that may appear in a redistributable artefact.
REDISTRIBUTABLE_LICENCE_STATUSES: frozenset[str] = frozenset(
    {"public_domain", "open_licence"}
)
#: Never ingested without an explicit policy override.
FORBIDDEN_LICENCE_STATUSES: frozenset[str] = frozenset({"restricted", "terms_restricted"})

DEFAULT_POLICY: dict[str, Any] = {
    "policy_id": "convergence.licence.default.failclosed",
    "version": "1.0.0",
    "defaults": {
        "may_query": True,
        "may_ingest": False,
        "may_redistribute": False,
        "attribution_required": True,
        "unknown_is_quarantine": True,
    },
    "status_rules": {
        "public_domain": {
            "may_query": True,
            "may_ingest": True,
            "may_redistribute": True,
            "attribution_required": False,
        },
        "open_licence": {
            "may_query": True,
            "may_ingest": True,
            "may_redistribute": True,
            "attribution_required": True,
        },
        "open_no_explicit_licence": {
            "may_query": True,
            "may_ingest": True,
            "may_redistribute": False,
            "attribution_required": True,
            "note": "Query and local analysis permitted by circumstance; no explicit "
            "redistribution grant, so records stay out of published artefacts.",
        },
        "terms_restricted": {
            "may_query": True,
            "may_ingest": False,
            "may_redistribute": False,
            "attribution_required": True,
        },
        "restricted": {
            "may_query": False,
            "may_ingest": False,
            "may_redistribute": False,
            "attribution_required": True,
        },
        "unknown": {
            "may_query": False,
            "may_ingest": False,
            "may_redistribute": False,
            "attribution_required": True,
        },
    },
    "source_overrides": {},
    "quarantined_sources": ["un_comtrade"],
}

POLICY_PATH = Path("config/convergence/licence_policy.json")


class LicenceError(RuntimeError):
    """Raised when a record may not be ingested under the active policy."""


class LicencePolicy:
    """Loaded licence policy, with per-source overrides.

    Two on-disk schemas are understood:

    ``medradar.licence_policy.v1``
        The audited policy produced by ``tools/convergence/licence/``.  It is a
        per-source table (``sources.<id>.{may_query, may_ingest,
        may_redistribute, attribution_required, licence_status}``) plus an
        explicit ``quarantine.source_ids`` list.  This is the authoritative
        format.
    ``convergence.licence.default``
        The compact fallback in :data:`DEFAULT_POLICY`, used when the audited
        file is absent.  It classifies by licence status only.
    """

    def __init__(self, payload: Mapping[str, Any] | None = None, *, origin: str = "default") -> None:
        payload = dict(payload or DEFAULT_POLICY)
        self.payload: dict[str, Any] = json.loads(json.dumps(payload))
        self.origin = origin
        self.schema = str(self.payload.get("schema") or "convergence.licence.default")

        self._defaults: dict[str, Any] = {
            "may_query": False,
            "may_ingest": False,
            "may_analyse_locally": False,
            "may_redistribute": False,
            "attribution_required": True,
        }
        self._status_rules: dict[str, dict[str, Any]] = {}
        self._overrides: dict[str, dict[str, Any]] = {}
        self._quarantined: set[str] = set()

        if "sources" in self.payload and isinstance(self.payload["sources"], Mapping):
            # Audited per-source policy (authoritative).
            self._overrides = {
                str(k): dict(v) for k, v in self.payload["sources"].items()
            }
            quarantine = self.payload.get("quarantine") or {}
            self._quarantined = set(quarantine.get("source_ids") or [])
            self._quarantine_paths = list(quarantine.get("paths") or [])
            self._defaults.update(
                {
                    "may_query": False,
                    "may_ingest": False,
                    "may_redistribute": False,
                    "attribution_required": True,
                }
            )
        else:
            # Compact fallback keyed by licence status.
            self._defaults.update(dict(self.payload.get("defaults", {})))
            self._status_rules = {
                str(k): dict(v)
                for k, v in (self.payload.get("status_rules") or {}).items()
            }
            self._overrides = {
                str(k): dict(v)
                for k, v in (self.payload.get("source_overrides") or {}).items()
            }
            self._quarantined = set(self.payload.get("quarantined_sources") or [])
            self._quarantine_paths = []

    # ---------------------------------------------------------------- loading
    @classmethod
    def load(cls, path: Path | str | None = None) -> "LicencePolicy":
        target = Path(path) if path else POLICY_PATH
        if not target.exists():
            return cls(None, origin="default:missing_policy_file")
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:  # fail closed, loudly
            raise LicenceError(f"licence policy is not valid JSON: {exc}") from exc
        return cls(payload, origin=str(target))

    # ------------------------------------------------------------- decisions
    def rule_for(self, source_id: str, licence_status: str) -> dict[str, Any]:
        """Resolve the effective rule for one (source, status) pair."""
        merged: dict[str, Any] = dict(self._defaults)
        merged.update(self._status_rules.get(licence_status, {}))
        override = self._overrides.get(source_id)
        if override:
            merged.update(override)
        merged["_source_id"] = source_id
        merged["_licence_status"] = licence_status
        merged["_quarantined"] = source_id in self._quarantined
        merged["_known_source"] = override is not None
        if merged["_quarantined"]:
            merged["may_ingest"] = False
            merged["may_redistribute"] = False
        if licence_status in FORBIDDEN_LICENCE_STATUSES:
            merged["may_redistribute"] = False
            merged["may_ingest"] = False
        return merged

    def may_ingest(self, source_id: str, licence_status: str) -> bool:
        if source_id in self._quarantined:
            return False
        if licence_status in FORBIDDEN_LICENCE_STATUSES:
            return False
        return bool(self.rule_for(source_id, licence_status).get("may_ingest", False))

    def may_redistribute(self, source_id: str, licence_status: str) -> bool:
        if source_id in self._quarantined:
            return False
        if licence_status in FORBIDDEN_LICENCE_STATUSES:
            return False
        return bool(self.rule_for(source_id, licence_status).get("may_redistribute", False))

    def may_analyse_locally(self, source_id: str, licence_status: str) -> bool:
        if source_id in self._quarantined:
            return False
        return bool(self.rule_for(source_id, licence_status).get("may_analyse_locally", True))

    def attribution_required(self, source_id: str, licence_status: str) -> bool:
        return bool(self.rule_for(source_id, licence_status).get("attribution_required", True))

    def redistribution_condition(self, source_id: str, licence_status: str) -> Any:
        return self.rule_for(source_id, licence_status).get("redistribution_condition")

    def quarantined_sources(self) -> set[str]:
        return set(self._quarantined)

    def quarantined_paths(self) -> list[str]:
        return list(getattr(self, "_quarantine_paths", []) or [])

    def is_known_source(self, source_id: str) -> bool:
        return source_id in self._overrides

    def summary(self) -> dict[str, Any]:
        return {
            "policy_id": self.payload.get("policy_id")
            or self.payload.get("schema")
            or "convergence.licence.default",
            "schema": self.schema,
            "version": self.payload.get("version") or self.payload.get("policy_version"),
            "origin": self.origin,
            "known_sources": len(self._overrides),
            "quarantined_sources": sorted(self._quarantined),
            "statuses": sorted(self._status_rules) or sorted(
                (self.payload.get("status_definitions") or {}).keys()
            ),
        }


def check_ingestible(
    policy: LicencePolicy, *, source_id: str, licence_status: str, source_record_id: str = ""
) -> None:
    """Raise :class:`LicenceError` when a record may not enter staging."""
    if policy.may_ingest(source_id, licence_status):
        return
    raise LicenceError(
        f"{source_id}/{source_record_id}: licence_status={licence_status!r} may not be "
        f"ingested under policy {policy.payload.get('policy_id')!r}"
    )


__all__ = [
    "DEFAULT_POLICY",
    "FORBIDDEN_LICENCE_STATUSES",
    "INGESTIBLE_LICENCE_STATUSES",
    "LicenceError",
    "LicencePolicy",
    "POLICY_PATH",
    "REDISTRIBUTABLE_LICENCE_STATUSES",
    "check_ingestible",
]
