"""Patent ownership: resolve an assignee string to a labeler DUNS.

The half that works today
-------------------------
A patent states its owner as a string: ``MEDTRONIC SOFAMOR DANEK INC``,
``BOSTON SCIENTIFIC SCIMED, INC.``, ``ABBOTT CARDIOVASCULAR SYSTEMS INC``. A string is not an
entity. The device register, however, is already keyed on a legal-entity identifier the labeler
maintains — ``labeler_duns_number`` — and it carries 12,536 distinct companies with 5,258,157
devices behind them.

So the useful question is not "can we download patents" (see the environment facts below) but
"can an assignee string be resolved to a DUNS". That question is answerable **now**, without any
patent API, because the candidate set is the register we already hold. This module answers it,
records how each resolution was reached, and reports its own confidence.

Matching is deliberately conservative:

1. exact match on the normalised string;
2. token-subset match where one name's tokens contain the other's, at least two tokens are
   shared, and shared/|assignee| is at least 0.75.

Anything weaker is left unresolved. A wrong owner is worse than a missing one: the whole point
of the DUNS spine is that every edge can be audited, and a fuzzy match that happens to be wrong
poisons every downstream join silently.

Environment facts measured 2026-11-21, recorded because they decide what is possible
------------------------------------------------------------------------------------
=============================  ==========================================  ===============
host                           result                                      meaning
=============================  ==========================================  ===============
search.patentsview.org         DNS does not resolve                        unreachable
assignment-api.uspto.gov       DNS does not resolve                        unreachable
assignment.uspto.gov           DNS does not resolve                        unreachable
ped.uspto.gov                  DNS does not resolve                        unreachable
bulkdata.uspto.gov             DNS does not resolve                        unreachable
api.uspto.gov                  HTTP 401 Unauthorized                       needs a key
data.uspto.gov                 HTTP 200, Angular SPA shell only            no data without JS
patents.google.com (xhr)       HTTP 503 bot block                          blocked
patents-public-data (BQ)       no gcloud/bq, no credentials                needs a GCP project
=============================  ==========================================  ===============

So the patent *fetch* lane is credential-gated on this host, and that is stated rather than
worked around: no spoofed identity, no proxy, no scraping of a page that answers 503. The
clients below implement the documented contracts and raise :class:`CredentialMissing` with the
exact environment variable to set.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ENV_USPTO_ODP = "USPTO_ODP_API_KEY"
ENV_PATENTSVIEW = "PATENTSVIEW_API_KEY"
ENV_GOOGLE_PROJECT = "GOOGLE_CLOUD_PROJECT"

#: Legal-form and connective tokens that carry no identity. "MEDICAL" is deliberately absent:
#: dropping it would merge unrelated firms.
_SUFFIX_TOKENS = frozenset({
    "INC", "INCORPORATED", "LLC", "LLLP", "LTD", "LIMITED", "CORP", "CORPORATION", "CO",
    "COMPANY", "GMBH", "AG", "SA", "BV", "NV", "PLC", "LP", "LLP", "PTY", "KG", "SPA",
    "SRL", "AB", "OY", "OYJ", "KK", "SE", "ASA", "APS", "SAS", "SARL", "SGPS", "PTE",
    "HOLDINGS", "HOLDING", "GROUP", "INTERNATIONAL", "INTL", "USA", "AMERICA", "THE",
    "DBA", "AKA", "AND",
})

MIN_TOKENS = 2
MIN_OVERLAP_RATIO = 0.75


@dataclass
class AssigneeResolution:
    assignee_raw: str
    assignee_norm: str
    labeler_duns: str
    company_name: str
    method: str
    confidence: float

    def as_row(self) -> dict[str, Any]:
        return {
            "assignee_raw": self.assignee_raw,
            "assignee_norm": self.assignee_norm,
            "labeler_duns": self.labeler_duns,
            "company_name": self.company_name,
            "method": self.method,
            "confidence": self.confidence,
        }


@dataclass
class ResolveStats:
    tried: int = 0
    exact: int = 0
    token_subset: int = 0
    unresolved: int = 0
    written: int = 0
    samples: list[dict[str, Any]] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return round((self.exact + self.token_subset) / self.tried, 4) if self.tried else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "tried": self.tried,
            "exact": self.exact,
            "token_subset": self.token_subset,
            "unresolved": self.unresolved,
            "written": self.written,
            "resolve_rate": self.rate,
            "samples": self.samples[:12],
        }


def normalise_assignee(raw: str) -> str:
    """Upper-case, strip punctuation and legal-form tokens, normalise ``&`` to ``AND``."""
    text = (raw or "").upper().replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    tokens = text.split()
    while tokens and tokens[-1] in _SUFFIX_TOKENS:
        tokens.pop()
    while tokens and tokens[0] in _SUFFIX_TOKENS:
        tokens.pop(0)
    # A trailing "AND" appears after dropping "& CO": remove it again.
    while tokens and tokens[-1] in _SUFFIX_TOKENS:
        tokens.pop()
    return " ".join(tokens)


#: Suffixes that encode a jurisdiction or legal form rather than a name. Two strings that
#: differ here are *different legal entities that share a name*, which is the exact failure a
#: name-matching resolver must not hide.
_ENTITY_BEARING_SUFFIXES = frozenset({
    "GMBH", "AG", "SA", "BV", "NV", "SPA", "SRL", "AB", "OY", "OYJ", "KK", "SE", "ASA",
    "APS", "SAS", "SARL", "SGPS", "PTE", "PTY", "KG", "PLC", "LTD", "LIMITED",
    "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LLC", "LP", "LLP",
})


def suffix_tokens(raw: str) -> frozenset[str]:
    """The jurisdiction/legal-form tokens present in a name, before they are stripped."""
    text = (raw or "").upper().replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return frozenset(token for token in text.split() if token in _ENTITY_BEARING_SUFFIXES)


class AssigneeResolver:
    """Resolve patent assignee strings against the device register's own company names."""

    def __init__(self, reference, *, max_candidates: int | None = None) -> None:
        self.reference = reference
        self._exact: dict[str, tuple[str, str]] | None = None
        self._tokens: list[tuple[tuple[str, ...], str, str]] | None = None
        self._max_candidates = max_candidates

    def _build(self) -> None:
        pairs = self.reference.company_names(limit=self._max_candidates)
        exact: dict[str, tuple[str, str]] = {}
        tokenised: list[tuple[tuple[str, ...], str, str]] = []
        for name, duns in pairs:
            norm = normalise_assignee(name)
            if not norm:
                continue
            exact.setdefault(norm, (duns, name))
            tokenised.append((tuple(norm.split()), duns, name))
        self._exact = exact
        self._tokens = tokenised

    @property
    def exact_index(self) -> dict[str, tuple[str, str]]:
        if self._exact is None:
            self._build()
        assert self._exact is not None
        return self._exact

    @property
    def token_index(self) -> list[tuple[tuple[str, ...], str, str]]:
        if self._tokens is None:
            self._build()
        assert self._tokens is not None
        return self._tokens

    def resolve(self, raw: str) -> AssigneeResolution | None:
        norm = normalise_assignee(raw)
        if not norm:
            return None
        hit = self.exact_index.get(norm)
        if hit is not None:
            method, confidence = self._grade(raw, hit[1], "exact", 1.0)
            return AssigneeResolution(raw, norm, hit[0], hit[1], method, confidence)

        wanted = norm.split()
        if len(wanted) < MIN_TOKENS:
            return None
        wanted_set = set(wanted)
        best: tuple[float, str, str] | None = None
        for tokens, duns, name in self.token_index:
            if len(tokens) < MIN_TOKENS:
                continue
            shared = wanted_set & set(tokens)
            if len(shared) < MIN_TOKENS:
                continue
            ratio = len(shared) / len(wanted)
            if ratio < MIN_OVERLAP_RATIO:
                continue
            # Prefer the tightest candidate: more overlap, then the shorter company name so
            # "MEDTRONIC VASCULAR" is not swallowed by a longer unrelated sibling.
            score = (ratio, -len(tokens))
            if best is None or score > (best[0], -len(best[1].split())):
                best = (ratio, duns, name)
        if best is None:
            return None
        method, confidence = self._grade(raw, best[2], "token_subset", round(best[0], 3))
        return AssigneeResolution(raw, norm, best[1], best[2], method, confidence)

    @staticmethod
    def _grade(raw: str, candidate: str, method: str, confidence: float) -> tuple[str, float]:
        """Downgrade a name match whose legal form contradicts the candidate's.

        Measured failure this fixes: ``STRYKER CORPORATION`` matched ``Stryker GmbH`` at
        confidence 1.0, because stripping the suffix left ``STRYKER`` and any company called
        Stryker qualified. That is a *different legal entity in a different country*, and
        reporting it as a certain match is exactly the silent corruption the DUNS spine exists
        to prevent. The candidate is still returned - it is usually the right corporate family -
        but the method and the confidence say what actually happened.
        """
        mine = suffix_tokens(raw)
        theirs = suffix_tokens(candidate)
        if mine and theirs and not (mine & theirs):
            return (f"{method}_entity_mismatch", round(min(confidence, 0.55), 3))
        return (method, confidence)


def resolve_assignees(reference, assignees: Iterable[str], *,
                      write: bool = True) -> ResolveStats:
    """Resolve a batch of assignee strings and (optionally) persist the resolutions."""
    resolver = AssigneeResolver(reference)
    stats = ResolveStats()
    seen: set[str] = set()
    for raw in assignees:
        text = (raw or "").strip()
        if not text:
            continue
        key = normalise_assignee(text)
        if not key or key in seen:
            continue
        seen.add(key)
        stats.tried += 1
        resolution = resolver.resolve(text)
        if resolution is None:
            stats.unresolved += 1
            continue
        if resolution.method == "exact":
            stats.exact += 1
        else:
            stats.token_subset += 1
        if len(stats.samples) < 12:
            stats.samples.append(resolution.as_row())
        if write:
            existing = reference.resolve_assignee(resolution.assignee_norm)
            if existing is None or existing["confidence"] <= resolution.confidence:
                reference.record_assignee_resolution(**resolution.as_row())
                stats.written += 1
    return stats


# --------------------------------------------------------------------- gated clients
class CredentialMissing(RuntimeError):
    """A source needs a credential that is not configured. Never faked, never worked around."""

    def __init__(self, message: str, *, env_var: str) -> None:
        super().__init__(message)
        self.env_var = env_var


def secret_path(env_var: str) -> Path:
    """Where a credential may also live as a file.

    Needed because a Windows user environment variable written by one process is **not** visible
    to already-running shells: their environment block is fixed at start. Measured: the setup
    tool wrote ``USPTO_ODP_API_KEY`` to ``HKCU\\Environment`` and the very next command still
    reported it unset. A key file read at call time closes that gap without forcing a terminal
    restart, and it also keeps the key out of shell history.
    """
    base = os.environ.get("MEDRADAR_SECRETS_DIR")
    root = Path(base) if base else Path.home() / ".medradar"
    return root / f"{env_var}.key"


def _credential(env_var: str) -> str:
    value = str(os.environ.get(env_var) or "").strip()
    if value:
        return value
    path = secret_path(env_var)
    try:
        file_value = path.read_text(encoding="utf-8").strip()
    except OSError:
        file_value = ""
    if file_value:
        return file_value
    raise CredentialMissing(
        f"{env_var} is not set (checked the environment and {path}). This source cannot be "
        "read without it, and this project does not spoof an identity to get around a 401.",
        env_var=env_var,
    )


def credential_status() -> dict[str, Any]:
    """Which patent credentials exist, and where each was found.

    Reported in the UI and by the setup tool so a gap is never mistaken for zero patents.
    """
    def locate(env_var: str) -> str | None:
        if str(os.environ.get(env_var) or "").strip():
            return "environment"
        path = secret_path(env_var)
        try:
            if path.read_text(encoding="utf-8").strip():
                return f"file:{path}"
        except OSError:
            return None
        return None

    sources = {name: locate(name) for name in
               (ENV_USPTO_ODP, ENV_PATENTSVIEW, ENV_GOOGLE_PROJECT)}
    return {
        "uspto_odp": bool(sources[ENV_USPTO_ODP]),
        "patentsview": bool(sources[ENV_PATENTSVIEW]),
        "google_bigquery": bool(sources[ENV_GOOGLE_PROJECT]),
        "found_in": {name: where for name, where in sources.items() if where},
        "env_vars": [ENV_USPTO_ODP, ENV_PATENTSVIEW, ENV_GOOGLE_PROJECT],
    }


class OdpShapeError(RuntimeError):
    """The response envelope was not recognised.

    Raised instead of returning an empty list, because "we did not understand the envelope" and
    "there are no matching patents" must never look the same. The message carries the top-level
    keys that were actually present, which is the only way to extend the parser without guessing.
    """


#: Envelope keys seen in USPTO-family APIs, in the order worth trying. This is a *tolerance*
#: list, not a specification: the ODP publishes no OpenAPI document (every spec path answers
#: 403 "Missing Authentication Token"), so the parser recognises several shapes and refuses to
#: invent one when none match.
_RECORD_KEYS = ("results", "patentDataBag", "data", "items", "records", "docs", "patentBag")
_COUNT_KEYS = ("count", "total", "totalCount", "totalNumFound", "numFound")


def unwrap_records(payload: Any) -> list[Any]:
    """Return the record list from a USPTO-family response envelope."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise OdpShapeError(f"expected an object or list, got {type(payload).__name__}")
    for key in _RECORD_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for inner in _RECORD_KEYS:
                nested = value.get(inner)
                if isinstance(nested, list):
                    return nested
    raise OdpShapeError(
        "unrecognised envelope; top-level keys were " + ", ".join(sorted(payload)[:20])
    )


def unwrap_count(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in _COUNT_KEYS:
        value = payload.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


class UsptoAssignmentClient:
    """USPTO Patent Assignment Search - the ownership chain (assignor -> assignee).

    **Measured 2026-11-21: this endpoint does not exist on ODP.** ``api.uspto.gov`` answers
    ``403 {"message":"Missing Authentication Token"}`` for ``/api/v1/patent/assignments/search``,
    ``/api/v1/patent/assignment/`` and every other assignment path tried, which is AWS API
    Gateway's signal for *no route here*. The two live routes answer ``401`` instead. The
    historical ``assignment-api.uspto.gov`` and ``assignment.uspto.gov`` hosts do not resolve
    from this network at all.

    So the ownership chain is not reachable through ODP. What is reachable is the assignee name
    on each application record, and that is what :class:`AssigneeResolver` turns into a DUNS.
    """

    LIVE_ON_ODP = False

    def __init__(self, fetcher) -> None:
        self.fetcher = fetcher

    def lookup(self, query: str, *, rows: int = 100) -> Any:
        raise OdpShapeError(
            "no assignment endpoint exists on api.uspto.gov (measured 403 'Missing "
            "Authentication Token' on every assignment path); resolve ownership through the "
            "assignee name on application records instead"
        )


class UsptoOdpClient:
    """USPTO Open Data Portal. Free key, sent as ``X-API-KEY``.

    Verified route table (measured 2026-11-21, keyless - ``401`` means the route exists and
    wants a credential, ``403 Missing Authentication Token`` means it does not exist):

    ==============================================  ======  ====================
    path                                            status  meaning
    ==============================================  ======  ====================
    /api/v1/patent/applications/search              401     live, needs a key
    /api/v1/datasets/products/search                401     live, needs a key
    /api/v1/patent/assignments/search               403     no such route
    /api/v1/patent/assignments                      403     no such route
    /api/v1/ptab/, /api/v1/trademarks/, /api/v1/bulk/ 403   no such route
    ==============================================  ======  ====================

    The dataset catalogue route matters more than it looks: if it lists a bulk
    patent-assignment product, ownership chains become a file download rather than an API
    problem.
    """

    BASE = "https://api.uspto.gov"
    APPLICATIONS = "/api/v1/patent/applications/search"
    DATASETS = "/api/v1/datasets/products/search"

    def __init__(self, fetcher, api_key: str | None = None) -> None:
        self.fetcher = fetcher
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"X-API-KEY": self.api_key or _credential(ENV_USPTO_ODP)}

    def raw(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        """Call any ODP route and return the parsed body untouched."""
        return self.fetcher.get_json(
            self.BASE + path, params=dict(params or {}), headers=self._headers(),
            allow_not_found=True,
        )

    def search_applications(self, query: str, *, limit: int = 25, offset: int = 0) -> dict[str, Any]:
        payload = self.raw(self.APPLICATIONS, {"q": query, "limit": min(int(limit), 500),
                                               "offset": int(offset)})
        return {
            "records": unwrap_records(payload),
            "count": unwrap_count(payload),
            "raw_keys": sorted(payload) if isinstance(payload, dict) else [],
        }

    def datasets(self, query: str = "*", *, limit: int = 100) -> dict[str, Any]:
        payload = self.raw(self.DATASETS, {"q": query, "limit": min(int(limit), 500)})
        return {
            "records": unwrap_records(payload),
            "count": unwrap_count(payload),
            "raw_keys": sorted(payload) if isinstance(payload, dict) else [],
        }

    def doctor(self) -> dict[str, Any]:
        """One call that answers: is the key valid, what does the envelope look like, what is
        actually in the catalogue. Written so the first run with a key produces a usable report
        instead of a stack trace.
        """
        report: dict[str, Any] = {"base": self.BASE, "credential": bool(
            self.api_key or os.environ.get(ENV_USPTO_ODP))}
        try:
            catalogue = self.datasets()
            report["datasets_ok"] = True
            report["datasets_count"] = catalogue["count"]
            report["datasets_envelope_keys"] = catalogue["raw_keys"]
            report["dataset_names"] = _dataset_names(catalogue["records"])
        except Exception as error:  # noqa: BLE001 - the report must survive any failure
            report["datasets_ok"] = False
            report["datasets_error"] = f"{type(error).__name__}: {error}"
        try:
            found = self.search_applications("catheter", limit=2)
            report["applications_ok"] = True
            report["applications_count"] = found["count"]
            report["applications_envelope_keys"] = found["raw_keys"]
            report["sample_record_keys"] = (
                sorted(found["records"][0]) if found["records"]
                and isinstance(found["records"][0], dict) else []
            )
        except Exception as error:  # noqa: BLE001
            report["applications_ok"] = False
            report["applications_error"] = f"{type(error).__name__}: {error}"
        return report


def _dataset_names(records: Sequence[Any]) -> list[str]:
    names: list[str] = []
    for record in records[:200]:
        if not isinstance(record, Mapping):
            continue
        for key in ("productTitle", "title", "name", "datasetName", "productDescription"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                names.append(value.strip()[:90])
                break
    return names


class PatentsViewClient:
    """PatentsView: disambiguated inventors and assignees. New host requires a key."""

    BASE = "https://search.patentsview.org/api/v1/patent/"

    def __init__(self, fetcher, api_key: str | None = None) -> None:
        self.fetcher = fetcher
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.api_key or _credential(ENV_PATENTSVIEW)}

    def search(self, query: Mapping[str, Any], *, fields: Sequence[str],
               per_page: int = 25) -> Any:
        return self.fetcher.get_json(
            self.BASE,
            params={"q": _compact_json(query), "f": _compact_json(list(fields)),
                    "o": _compact_json({"per_page": min(int(per_page), 1000)})},
            headers=self._headers(), allow_not_found=True,
        )


def _compact_json(value: Any) -> str:
    import json

    return json.dumps(value, separators=(",", ":"), ensure_ascii=True)





__all__ = [
    "AssigneeResolution",
    "AssigneeResolver",
    "CredentialMissing",
    "ENV_GOOGLE_PROJECT",
    "ENV_PATENTSVIEW",
    "ENV_USPTO_ODP",
    "OdpShapeError",
    "PatentsViewClient",
    "ResolveStats",
    "UsptoAssignmentClient",
    "UsptoOdpClient",
    "credential_status",
    "normalise_assignee",
    "resolve_assignees",
    "suffix_tokens",
    "unwrap_count",
    "unwrap_records",
]
