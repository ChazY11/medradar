from __future__ import annotations

import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from medradar.data_pipeline.config import Settings
from medradar.data_pipeline.normalize import content_hash, normalise_510k
from medradar.data_pipeline.openfda import FetchResult, OpenFDAError
from medradar.data_pipeline.pipeline import Pipeline
from medradar.data_pipeline.snapshot import write_jsonl_gz


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def make_legacy_snapshot(path: Path, raw_records: list[dict]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    # Emulate the legacy collector's display projection: it did not keep every source field
    # and already truncated long text. DATA-001's first reconciliation must not interpret
    # that schema migration as a revision of every record.
    legacy_raw_keys = {
        "k_number", "applicant", "decision_date", "date_received", "device_name",
        "product_code", "decision_code", "decision_description", "advisory_committee",
        "advisory_committee_description", "country_code", "clearance_type",
        "expedited_review_flag", "statement_or_summary",
    }
    events = []
    for record in raw_records:
        event = normalise_510k(record)
        event["raw"] = {key: value for key, value in event["raw"].items() if key in legacy_raw_keys}
        event["content_hash"] = content_hash(event)
        events.append(event)
    write_jsonl_gz(path / "events.jsonl.gz", events)
    write_jsonl_gz(path / "applicants.jsonl.gz", [])
    write_jsonl_gz(
        path / "classifications.jsonl.gz",
        [{
            "product_code": "ABC",
            "device_name": "Test device",
            "specialty": "Gastroenterology",
            "device_class": "2",
            "regulation_number": "876.1000",
        }],
    )
    write_json(path / "snapshot.json", {
        "id": "legacy-2026-01-01T00:00:00Z-openfda",
        "schema": "medradar.snapshot.v1",
        "collected_at": "2026-01-01T00:00:00Z",
        "collection_started_at": "2026-01-01T00:00:00Z",
        "request_count": 0,
        "response_bytes": 0,
        "organizations": [],
    })
    return path


def make_registry(path: Path) -> Path:
    write_json(path, {
        "schema": "medradar.organizations.v1",
        "matching_rule": "exact applicant string after case folding and whitespace collapse",
        "organizations": [{
            "key": "acme",
            "display_name": "Acme Medical",
            "search_tokens": ["ACME"],
        }],
    })
    return path


class FakeOpenFDA:
    def __init__(self, records: list[dict]):
        self.records = list(records)
        self.source_records: dict[str, list[dict]] = {"openfda_510k": self.records}
        self.version = "2026-11-02"
        self.versions: dict[str, str] = {}
        self.total = len(self.records)
        self.classification_rows = [{
            "product_code": "ABC",
            "device_name": "Test device",
            "medical_specialty_description": "Gastroenterology",
            "device_class": "2",
            "regulation_number": "876.1000",
        }]
        self.fail_probe = False
        self.fail_fetch = False
        self.fail_sources: set[str] = set()
        self.fail_fetch_sources: set[str] = set()
        self.calls: list[tuple[str, str]] = []

    def _rows(self, source_id: str) -> list[dict]:
        if source_id == "openfda_510k":
            return list(self.records)
        return list(self.source_records.get(source_id) or [])

    def probe(self, source):
        self.calls.append(("probe", source.source_id))
        if self.fail_probe or source.source_id in self.fail_sources:
            raise OpenFDAError("simulated probe failure", status=500, url="http://fake")
        if source.source_id == "openfda_510k":
            total = self.total
        elif source.source_id == "openfda_classification":
            total = len(self.classification_rows)
        else:
            total = len(self._rows(source.source_id))
        return {
            "source_id": source.source_id,
            "checked_at": "2026-11-16T00:00:00Z",
            "http_status": 200,
            "url": "http://fake" + source.endpoint,
            "bytes": 10,
            "elapsed_ms": 1.0,
            "last_updated": self.versions.get(source.source_id, self.version),
            "total": total,
            "meta": {},
        }

    def fetch_page(self, path, params, *, source_id, context):
        self.calls.append(("fetch", source_id))
        if self.fail_fetch or source_id in self.fail_sources or source_id in self.fail_fetch_sources:
            raise OpenFDAError("simulated fetch failure", status=503, url="http://fake" + path)
        values = dict(params)
        if source_id == "openfda_classification":
            rows = list(self.classification_rows)
            total = len(rows)
        elif source_id == "openfda_510k":
            rows = list(self.records)
            search = str(values.get("search") or "")
            if "NOTAREAL" in search:
                rows = []
            if 'k_number:"' in search:
                official = search.split('k_number:"', 1)[1].split('"', 1)[0]
                rows = [row for row in rows if row.get("k_number") == official]
            total = len(rows)
        else:
            rows = self._rows(source_id)
            total = len(rows)
        skip = int(values.get("skip", 0) or 0)
        limit = int(values.get("limit", 1000) or 1000)
        page = rows[skip:skip + limit]
        return FetchResult(
            data={"meta": {"last_updated": self.versions.get(source_id, self.version), "results": {"total": total, "skip": skip, "limit": limit}}, "results": page},
            http_status=200,
            url="http://fake" + path,
            bytes=100,
            elapsed_ms=1.0,
        )


def make_multi_source_records() -> tuple[list[dict], list[dict], list[dict]]:
    k510 = [{
        "k_number": "K000001", "applicant": "ACME", "decision_date": "2026-01-01",
        "device_name": "Widget A", "product_code": "ABC", "date_received": "2025-12-01",
    }]
    pma = [{
        "pma_number": "P000001", "supplement_number": "0", "applicant": "ACME",
        "decision_date": "2026-01-15", "device_name": "PMA Widget", "product_code": "ABC",
        "supplement_type": "",
    }]
    recall = [{
        "product_res_number": "Z-0001-2026", "res_event_number": "12345",
        "recalling_firm": "ACME", "event_date_posted": "2026-01-20",
        "event_date_initiated": "2026-01-10", "product_description": "Recall Widget",
        "reason_for_recall": "Test reason", "action": "Test action", "product_code": "ABC",
    }]
    return k510, pma, recall


@pytest.fixture()
def multi_source_env(tmp_path: Path):
    k510, pma, recall = make_multi_source_records()
    legacy = make_legacy_snapshot(tmp_path / "legacy", k510)
    registry = make_registry(tmp_path / "registry.json")
    settings = Settings(root=tmp_path / "state")
    settings.registry_path = registry
    settings.review_db = tmp_path / "no-review.db"
    settings.min_free_bytes = 0
    settings.full_reconciliation_interval_hours = 168
    # The combined-snapshot acceptance test explicitly opts into two product sources;
    # the production default is one for the 4 GB host.
    settings.max_product_sources_per_run = 3
    fake = FakeOpenFDA(k510)
    fake.source_records = {
        "openfda_510k": k510,
        "openfda_pma": pma,
        "openfda_recall": recall,
    }
    pipeline = Pipeline(settings, client=fake)
    pipeline.bootstrap(legacy)
    return SimpleNamespace(
        tmp_path=tmp_path, settings=settings, fake=fake, pipeline=pipeline,
        legacy=legacy, k510=k510, pma=pma, recall=recall,
    )


@pytest.fixture()
def pipeline_env(tmp_path: Path):
    raw = [
        {
            "k_number": "K000001", "applicant": "ACME", "decision_date": "2026-01-01",
            "device_name": "Widget A", "product_code": "ABC", "date_received": "2025-12-01",
            "address_1": "1 Main Street", "city": "Testville",
        },
        {
            "k_number": "K000002", "applicant": "ACME", "decision_date": "2026-02-01",
            "device_name": "Widget B", "product_code": "ABC", "date_received": "2026-01-01",
        },
    ]
    legacy = make_legacy_snapshot(tmp_path / "legacy", raw)
    registry = make_registry(tmp_path / "registry.json")
    settings = Settings(root=tmp_path / "state")
    settings.registry_path = registry
    settings.review_db = tmp_path / "no-review.db"
    settings.min_free_bytes = 0
    fake = FakeOpenFDA(raw)
    pipeline = Pipeline(settings, client=fake)
    boot = pipeline.bootstrap(legacy)
    return SimpleNamespace(
        tmp_path=tmp_path, settings=settings, fake=fake, pipeline=pipeline,
        legacy=legacy, raw=raw, bootstrap=boot,
    )
