"""A read-only MCP server over the radar ledger.

The scanner in docs/research/001 found that by 2026 every mature intelligence platform ships an
agent entry point. This one exposes the radar to any MCP client (Claude Desktop, an IDE agent, a
local script) using only the pieces that already exist: the ledger, the graph and the digest.

Design rules, in the same spirit as the HTTP API:

* **read-only.** Every tool opens the ledger with mode=ro. Nothing here can advance a cursor,
  write an observation or record a review.
* **no network.** JSON-RPC over stdio, so the client owns the process and the data never leaves
  the machine it asked from.
* **answers, not dumps.** Each tool returns a bounded projection; a tool that returned 17k rows
  would be useless to an agent with a context window.

Usage (any MCP client):

    python -m medradar.mcp_server --radar-dir /srv/medradar/data/radar
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable

from medradar.radar.digest import digest as build_digest
from medradar.radar.ledger import ObservationLedger
from medradar.radar.paths import radar_paths
from medradar.radar.relevance import ADMISSION_VERSION
from medradar.radar.taxonomy import load_taxonomy

SERVER_NAME = "medradar-radar"
SERVER_VERSION = "1.0.0"
#: Newest protocol this server implements; the client's own version is echoed back when it is
#: older, because the tool surface here uses nothing version-specific.
PROTOCOL_VERSION = "2025-06-18"


def _ledger(root: str | None) -> ObservationLedger:
    path = radar_paths(root).ledger
    return ObservationLedger(str(path), create=False, read_only=True)


def _record(ledger: ObservationLedger, observation_id: str) -> dict[str, Any] | None:
    row = ledger.raw(
        "SELECT o.observation_id, o.source, o.record_type, o.title, o.source_url, o.published_at,"
        " o.published_at_precision, o.event_at, o.event_at_precision, o.first_observed_at,"
        " o.official_identifier, o.observation_origin, o.discovery_phase, o.version_count,"
        " o.content_hash, a.decision, a.tier, a.score, a.dimensions, a.reasons"
        " FROM observation o LEFT JOIN admission_current a ON a.observation_id = o.observation_id"
        " WHERE o.observation_id = ?", (observation_id,))
    if not row:
        return None
    item = dict(row[0])
    for key in ("dimensions", "reasons"):
        try:
            item[key] = json.loads(item[key]) if item.get(key) else None
        except (TypeError, ValueError):
            item[key] = None
    return item


def _search(ledger: ObservationLedger, query: str | None, *, limit: int, source: str | None,
            scope: str) -> dict[str, Any]:
    args: dict[str, Any] = {"limit": limit, "offset": 0, "search": query, "order": "observed"}
    if source:
        args["sources"] = [source]
    # The tier filter joins admission_current, so the version must come with it; passing a tier
    # without the version produced "no such column: adm.tier".
    if scope in ("latest", "observed", "archive", "review"):
        args["scope"] = scope
        args["admission_version"] = ADMISSION_VERSION
        args["tiers"] = {"latest": ["HIGH_RELEVANCE"],
                         "observed": ["HIGH_RELEVANCE", "NEEDS_REVIEW"],
                         "archive": ["HIGH_RELEVANCE"],
                         "review": ["NEEDS_REVIEW"]}[scope]
    rows, total = ledger.feed(**args)
    return {
        "total": total,
        "items": [{"observation_id": r["observation_id"], "title": r.get("title"),
                   "source": r.get("source"), "published_at": r.get("published_at"),
                   "first_observed_at": r.get("first_observed_at"),
                   "source_url": r.get("source_url")} for r in rows],
    }


def _company(ledger: ObservationLedger, organization_id: str, *, limit: int) -> dict[str, Any]:
    rows = [dict(r) for r in ledger.raw(
        "SELECT o.observation_id, o.source, o.title, o.published_at, o.event_at, o.source_url,"
        " o.official_identifier, a.decision, a.tier"
        " FROM observation_facet f JOIN observation o ON o.observation_id = f.observation_id"
        " LEFT JOIN admission_current a ON a.observation_id = o.observation_id"
        " WHERE f.kind = 'organization' AND f.value = ?"
        " ORDER BY o.first_observed_at DESC LIMIT ?", (organization_id, limit))]
    taxonomy = load_taxonomy()
    org = next((o for o in getattr(taxonomy, "organizations", ()) if o.id == organization_id), None)
    return {
        "organization_id": organization_id,
        "display_name": getattr(org, "display_name", None) or organization_id,
        "label_zh": getattr(org, "label_zh", None),
        "country": getattr(org, "country", None),
        "count": len(rows),
        "records": rows,
    }


TOOLS: list[dict[str, Any]] = [
    {
        "name": "radar_digest",
        "description": ("What arrived in the last N hours, ranked by the admission decision, with "
                        "an explicit statement when nothing did. Start here."),
        "inputSchema": {"type": "object", "properties": {
            "hours": {"type": "integer", "minimum": 1, "maximum": 168, "default": 24},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5}}},
    },
    {
        "name": "radar_search",
        "description": "Search admitted records. Returns ids and titles; use radar_record for detail.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string"},
            "source": {"type": "string"},
            "scope": {"type": "string", "enum": ["latest", "observed", "archive", "review"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}}},
    },
    {
        "name": "radar_record",
        "description": ("One record with its admission decision, dimensions, reasons and official "
                        "URL, so a claim can be checked."),
        "inputSchema": {"type": "object", "required": ["observation_id"], "properties": {
            "observation_id": {"type": "string"}}},
    },
    {
        "name": "radar_company",
        "description": "What the product holds about one company, most recent first.",
        "inputSchema": {"type": "object", "required": ["organization_id"], "properties": {
            "organization_id": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}}},
    },
    {
        "name": "radar_sources",
        "description": "Source status: what ran, what is blocked by policy, what is failing.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _call_tool(name: str, arguments: dict[str, Any], root: str | None) -> dict[str, Any]:
    if name == "radar_digest":
        ledger = _ledger(root)
        try:
            return build_digest(ledger, hours=int(arguments.get("hours") or 24),
                                limit=int(arguments.get("limit") or 5))
        finally:
            ledger.close()
    if name == "radar_search":
        ledger = _ledger(root)
        try:
            return _search(ledger, arguments.get("query"),
                           limit=int(arguments.get("limit") or 10),
                           source=arguments.get("source"),
                           scope=str(arguments.get("scope") or "observed"))
        finally:
            ledger.close()
    if name == "radar_record":
        observation_id = str(arguments.get("observation_id") or "").strip()
        if not observation_id:
            raise ValueError("observation_id is required")
        ledger = _ledger(root)
        try:
            record = _record(ledger, observation_id)
        finally:
            ledger.close()
        if record is None:
            raise ValueError("no record with that id")
        return record
    if name == "radar_company":
        organization_id = str(arguments.get("organization_id") or "").strip()
        if not organization_id:
            raise ValueError("organization_id is required")
        ledger = _ledger(root)
        try:
            return _company(ledger, organization_id, limit=int(arguments.get("limit") or 10))
        finally:
            ledger.close()
    if name == "radar_sources":
        ledger = _ledger(root)
        try:
            rows = [dict(r) for r in ledger.raw(
                "SELECT source_id, access_state, consecutive_failures, last_success_check_at,"
                " watermark FROM source_state ORDER BY source_id")]
        finally:
            ledger.close()
        return {"count": len(rows), "sources": rows}
    raise ValueError(f"unknown tool: {name}")


def handle(request: dict[str, Any], *, root: str | None) -> dict[str, Any] | None:
    """One JSON-RPC request in, one response out (or None for a notification)."""
    method = request.get("method")
    request_id = request.get("id")
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "initialize":
        client_version = str((request.get("params") or {}).get("protocolVersion") or PROTOCOL_VERSION)
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "protocolVersion": client_version if client_version else PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": ("Read-only MedRadar radar. Start with radar_digest; every answer "
                             "points at records that carry an official source URL."),
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params") or {}
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        try:
            payload = _call_tool(name, arguments, root)
        except Exception as error:  # the client must see a tool error, not a dead server
            return {"jsonrpc": "2.0", "id": request_id,
                    "result": {"isError": True,
                               "content": [{"type": "text",
                                            "text": f"{type(error).__name__}: {error}"}]}}
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            "isError": False}}
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(root: str | None = None, stdin=None, stdout=None) -> None:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                     "error": {"code": -32700, "message": "parse error"}}) + "\n")
            stdout.flush()
            continue
        response = handle(request, root=root)
        if response is None:
            continue
        stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="medradar.mcp_server",
                                     description="Read-only MCP server over the radar ledger.")
    parser.add_argument("--radar-dir", default=None)
    args = parser.parse_args(argv)
    serve(args.radar_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())