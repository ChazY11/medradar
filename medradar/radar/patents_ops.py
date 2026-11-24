"""EPO Open Patent Services - the patent lane that does not depend on USPTO's broken key page.

Why EPO
-------
The USPTO route is blocked by their own software: the API-key page cannot parse
``/ui/api-keys/is_api_key``, so no key is ever issued, and the bulk download row contains a
single ``<a href="#">`` with no handler (measured: a trusted native click issues zero requests).
EPO answers a different question the same way and issues credentials after a form.

Measured 2026-11-24 from the production host:

    POST /3.2/auth/accesstoken  (Basic key:secret, grant_type=client_credentials)
      no Authorization header -> 401 "Client identifier is required"
      bogus key               -> 401 "ClientId is Invalid"
    GET  /3.2/rest-services/published-data/search  (no token)
                              -> 403 "violation of Fair Use policy"

The endpoint is reachable and speaks ordinary OAuth client credentials, so the only missing
ingredient is a consumer key, which is obtained by the operator at developers.epo.org (that host
answers 403 to non-browser clients, so registration has to happen in a real browser).

Where the rows go
-----------------
Into the same ``bulk_patent`` / ``bulk_patent_assignee`` tables the file importer writes, with the
same ``normalise_assignee`` key. device_view therefore needs no second code path and no knowledge
of which origin filled the table - and an absent table still reads as "never imported" rather than
"this company holds no patents".

Quota
-----
OPS is free with a published fair-use ceiling (4 GB/month, throttled). Each assignee query is one
small JSON page, so a few hundred assignees per day is far inside it. Requests are paced by the
shared PoliteFetcher policy, not by a bespoke counter.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

OPS_BASE = "https://ops.epo.org/3.2"
TOKEN_PATH = "/auth/accesstoken"
SEARCH_PATH = "/rest-services/published-data/search"
KEY_ENV = "EPO_OPS_KEY"
SECRET_ENV = "EPO_OPS_SECRET"
#: OPS rejects ranges beyond 100 per request. One page is enough for "how many, and the newest few".
MAX_RANGE = 100


class OpsError(RuntimeError):
    """A distinct, quotable failure from OPS - never collapsed into an empty result."""


class OpsCredentialMissing(OpsError):
    """No consumer key configured. Reported by name so an operator knows what to supply."""


@dataclass
class OpsPatent:
    publication: str
    title: str
    date: str
    assignee: str

    def to_dict(self) -> dict[str, Any]:
        return {"patent_id": self.publication, "title": self.title,
                "patent_date": self.date, "organization": self.assignee}


@dataclass
class OpsClient:
    """OAuth client-credentials wrapper with a cached token."""

    key: str = ""
    secret: str = ""
    fetcher: Any = None
    base: str = OPS_BASE
    _token: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls, fetcher: Any) -> "OpsClient":
        key = (os.environ.get(KEY_ENV) or "").strip()
        secret = (os.environ.get(SECRET_ENV) or "").strip()
        if not key or not secret:
            raise OpsCredentialMissing(
                f"{KEY_ENV} and {SECRET_ENV} are not set. Register a free consumer key at "
                "https://developers.epo.org (browser required: the host refuses non-browser "
                "clients with 403), then export both values.")
        return cls(key=key, secret=secret, fetcher=fetcher)

    def token(self) -> str:
        if self._token:
            return self._token
        basic = base64.b64encode(f"{self.key}:{self.secret}".encode()).decode()
        # Form-encoded, not JSON: OPS rejects a JSON body on this endpoint without saying why.
        data = self.fetcher.post_form(
            f"{self.base}{TOKEN_PATH}",
            {"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {basic}"},
        ) or {}
        token = str(data.get("access_token") or "").strip()
        if not token:
            raise OpsError(f"no access_token in token response: {data}")
        self._token = token
        return token

    def search(self, cql: str, *, rows: int = MAX_RANGE) -> dict[str, Any]:
        """One page of ``published-data/search`` for a CQL expression such as ``pa="medtronic"``."""
        rows = max(1, min(int(rows), MAX_RANGE))
        return self.fetcher.get_json(
            f"{self.base}{SEARCH_PATH}",
            params={"q": cql, "Range": f"1-{rows}"},
            headers={"Authorization": f"Bearer {self.token()}", "Accept": "application/json"},
        ) or {}


def _walk(node: Any, key: str) -> Iterable[Any]:
    """Yield every value stored under ``key`` at any depth, tolerating list-or-object."""
    if isinstance(node, Mapping):
        for name, value in node.items():
            if name == key:
                if isinstance(value, list):
                    yield from value
                else:
                    yield value
            yield from _walk(value, key)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item, key)


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        for name in ("$", "content", "value"):
            if name in value:
                return _text(value[name])
        for nested in value.values():
            text = _text(nested)
            if text:
                return text
    if isinstance(value, list):
        for item in value:
            text = _text(item)
            if text:
                return text
    return ""


def parse_search(payload: Mapping[str, Any], *, assignee: str = "") -> tuple[int, list[OpsPatent]]:
    """Tolerant read of an OPS search document.

    The envelope is documented but deeply nested and differs between a single hit and a page of
    hits (an object versus a list at the same key), so the walker accepts both instead of assuming
    one. A payload with no recognisable documents is an error, not zero patents.
    """
    total = 0
    for candidate in _walk(payload, "@total-result-count"):
        digits = "".join(ch for ch in str(candidate) if ch.isdigit())
        if digits:
            total = int(digits)
            break
    patents: list[OpsPatent] = []
    for document in _walk(payload, "exchange-document"):
        if not isinstance(document, Mapping):
            continue
        country = str(document.get("@country") or "").strip()
        number = str(document.get("@doc-number") or "").strip()
        kind = str(document.get("@kind") or "").strip()
        publication = f"{country}{number}{kind}".strip()
        if not publication:
            continue
        title = ""
        for found in _walk(document, "invention-title"):
            title = _text(found)
            if title:
                break
        date = ""
        for tag in ("date", "@date"):
            for found in _walk(document, tag):
                text = _text(found)
                if len(text) == 8 and text.isdigit():
                    date = f"{text[:4]}-{text[4:6]}-{text[6:]}"
                    break
            if date:
                break
        patents.append(OpsPatent(publication=publication, title=title[:400],
                                 date=date, assignee=assignee))
    if not patents and not total:
        raise OpsError("OPS answered without a result count or any exchange-document; "
                       "the response shape is not the documented one")
    return total, patents


def cql_for_assignee(name: str) -> str:
    """CQL for one applicant name. Quotes are stripped rather than escaped: OPS rejects a bare
    embedded quote and a mangled query would silently search for something else."""
    cleaned = " ".join(str(name or "").replace('"', " ").split())
    if not cleaned:
        raise ValueError("empty assignee name")
    return f'pa="{cleaned}"'


def import_assignee(reference, name: str, *, client: OpsClient, rows: int = MAX_RANGE
                    ) -> dict[str, Any]:
    """Query one assignee and write the hits into the shared bulk_patent tables."""
    from .patents import normalise_assignee
    from .patents_bulk import ensure_tables

    ensure_tables(reference)
    payload = client.search(cql_for_assignee(name), rows=rows)
    total, patents = parse_search(payload, assignee=name)
    key = normalise_assignee(name)
    written = 0
    for patent in patents:
        if not key:
            break
        reference.conn.execute(
            "INSERT OR REPLACE INTO bulk_patent (patent_id, title, patent_date) VALUES (?,?,?)",
            (patent.publication, patent.title or None, patent.date or None))
        reference.conn.execute(
            "INSERT OR REPLACE INTO bulk_patent_assignee "
            "(patent_id, assignee_id, organization, organization_norm, assignee_type) "
            "VALUES (?,?,?,?,?)",
            (patent.publication, f"ops:{key}", name, key, "applicant"))
        written += 1
    reference.conn.commit()
    return {"assignee": name, "total_reported": total, "rows_written": written,
            "query": cql_for_assignee(name)}


__all__ = [
    "KEY_ENV",
    "MAX_RANGE",
    "OpsClient",
    "OpsCredentialMissing",
    "OpsError",
    "OpsPatent",
    "SECRET_ENV",
    "cql_for_assignee",
    "import_assignee",
    "parse_search",
]
