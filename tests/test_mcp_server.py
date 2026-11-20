"""The MCP server: the same evidence, reachable by an agent.

The claim: an MCP client can ask what is worth reading, search, open one record, and read source
status - and gets bounded, checkable answers, with no way to write.
"""
from __future__ import annotations

import datetime as dt
import io
import json
from pathlib import Path

import pytest

from medradar.mcp_server import handle, serve
from medradar.radar.classify import RuleMapper
from medradar.radar.engine import apply_admissions
from medradar.radar.ledger import ObservationLedger
from medradar.radar.records import MAPPING_VERSION, RawRecord
from medradar.radar.taxonomy import load_taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"
_NOW = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
_TODAY = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def _seed(radar_dir: Path) -> str:
    radar_dir.mkdir(parents=True, exist_ok=True)
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    mapper = RuleMapper(taxonomy)
    ledger = ObservationLedger(radar_dir / "radar.db")
    ledger.ensure_source("crossref", label="Crossref", adapter_version="a1", cadence_hours=6)
    record = RawRecord(
        source="crossref", source_record_id="crossref:10.1/mcp",
        official_identifier="10.1/mcp",
        record_type="publication",
        title="Patient monitor SpO2 algorithm accuracy in critical care",
        url="https://example.invalid/10.1/mcp",
        published_at=_TODAY, published_at_precision="date",
        payload={"id": "10.1/mcp", "title": "Patient monitor SpO2 algorithm accuracy",
                 "abstract": "Monitoring study."},
        text="Patient monitor SpO2 algorithm accuracy in critical care Monitoring study.",
        extra={"organization_hint": "Philips Medical Systems", "product_codes": ["MHX"],
               "product_hint": "Patient monitor"},
    )
    outcome = ledger.record_observation(
        record, mapper.map(record), run_id="r-mcp", adapter_version="a1",
        mapping_version=MAPPING_VERSION, seen_at=_NOW)
    apply_admissions(ledger, limit=50)
    ledger.close()
    return outcome.observation_id


def _call(root: Path, method: str, params: dict | None = None, request_id: int = 1):
    return handle({"jsonrpc": "2.0", "id": request_id, "method": method,
                   "params": params or {}}, root=str(root))


def test_initialize_reports_the_server_and_echoes_the_client_version(tmp_path: Path):
    response = _call(tmp_path, "initialize", {"protocolVersion": "2024-11-05"})
    assert response["result"]["protocolVersion"] == "2024-11-05"
    assert response["result"]["serverInfo"]["name"] == "medradar-radar"
    assert "tools" in response["result"]["capabilities"]


def test_tools_list_is_bounded_and_read_only(tmp_path: Path):
    tools = _call(tmp_path, "tools/list")["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert names == {"radar_digest", "radar_search", "radar_record", "radar_company",
                     "radar_sources"}
    for tool in tools:
        assert tool["inputSchema"]["type"] == "object"
        assert tool.get("description")
    assert not any("write" in tool["name"] or "review" in tool["name"] for tool in tools)


def test_digest_and_search_and_record_work_over_the_protocol(tmp_path: Path):
    observation_id = _seed(tmp_path)
    digest = _call(tmp_path, "tools/call", {"name": "radar_digest",
                                            "arguments": {"hours": 24}})
    payload = json.loads(digest["result"]["content"][0]["text"])
    assert payload["totals"]["arrived"] >= 1
    assert digest["result"]["isError"] is False

    search = _call(tmp_path, "tools/call", {"name": "radar_search",
                                            "arguments": {"query": "SpO2"}})
    found = json.loads(search["result"]["content"][0]["text"])
    assert found["total"] >= 1
    assert any(item["observation_id"] == observation_id for item in found["items"])

    record = _call(tmp_path, "tools/call", {"name": "radar_record",
                                            "arguments": {"observation_id": observation_id}})
    detail = json.loads(record["result"]["content"][0]["text"])
    assert detail["observation_id"] == observation_id
    assert detail["decision"], "the record carries its admission decision"
    assert detail["source_url"].startswith("https://")


def test_a_bad_tool_or_missing_argument_is_a_tool_error_not_a_dead_server(tmp_path: Path):
    unknown = _call(tmp_path, "tools/call", {"name": "radar_delete_everything", "arguments": {}})
    assert unknown["result"]["isError"] is True
    missing = _call(tmp_path, "tools/call", {"name": "radar_record", "arguments": {}})
    assert missing["result"]["isError"] is True
    method = _call(tmp_path, "does/not/exist")
    assert method["error"]["code"] == -32601


def test_the_stdio_loop_round_trips_lines(tmp_path: Path):
    _seed(tmp_path)
    stdin = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n"
    )
    stdout = io.StringIO()
    serve(str(tmp_path), stdin=stdin, stdout=stdout)
    lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
    assert len(lines) == 2, "a notification produces no response"
    assert json.loads(lines[0])["id"] == 1
    assert len(json.loads(lines[1])["result"]["tools"]) == 5