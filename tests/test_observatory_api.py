"""HTTP tests for the Live Observatory API.

Tier: SYNTHETIC — a deterministic ledger is built in ``tmp_path`` from
``RawRecord`` / ``MappingResult``; no network, no real research data, no real
ledger. The production read path (``open_ledger_readonly(default_ledger_path())``)
is exactly what the tests exercise.

The fixture ledger contains: four ``NEW`` records, one ``UPDATED`` revision of
one of them, one ``REMOVED_OR_UNAVAILABLE``, one ``FETCH_FAILED``, one
``BACKFILLED`` record (origin fields) and a couple of older records so the
24h / 7d / 30d windows differ.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="install the product extra: pip install -e .[web]")
pytest.importorskip("httpx", reason="install the dev extra for TestClient")

from fastapi.testclient import TestClient  # noqa: E402

from medradar.observatory.ledger import (  # noqa: E402
    ObservationLedger,
    default_ledger_path,
    open_ledger_readonly,
)
from medradar.observatory.records import (  # noqa: E402
    ORIGIN_BACKFILLED,
    PRECISION_DATE,
    PRECISION_DATETIME,
    MappingResult,
    RawRecord,
    observation_id,
    utc_now,
)
from medradar.web.app import app  # noqa: E402

COLLECTOR = "live-observatory/1.0.0"
MAPPING = "obs-mapping-v1"
DETAIL_EXTRA = {
    "source_record_id",
    "ingested_at",
    "observation_status",
    "observation_origin",
    "backfill_reason",
    "last_checked_at",
}

ITEM_KEYS = {
    "change_id",
    "observation_id",
    "source",
    "source_label_zh",
    "record_type",
    "record_type_label_zh",
    "change_state",
    "change_label_zh",
    "observed_at",
    "first_seen_at",
    "event_at",
    "event_at_precision",
    "event_at_label_zh",
    "published_at",
    "published_at_precision",
    "source_updated_at",
    "time_basis",
    "title",
    "url",
    "original_url",
    "company",
    "track",
    "changed_fields",
    "version",
    "is_revision",
    "evidence_zh",
    "phase",
    "phase_label_zh",
}
TIME_BASIS_KEYS = {
    "event_to_publish_hours",
    "publish_to_first_seen_hours",
    "event_to_first_seen_hours",
    "measurable",
    "observed_later_than_event",
    "statement_zh",
}
COMPANY_KEYS = {"entity_id", "name_zh", "status", "method", "note_zh"}
TRACK_KEYS = {"track_id", "name_zh", "domain", "status"}
VERSION_KEYS = {"version_seq", "version_count", "version_id"}

client = TestClient(app)


# --------------------------------------------------------------------- fixtures
def _record(
    source: str,
    record_id: str,
    record_type: str,
    title: str,
    *,
    url: str | None = None,
    event_at: str | None = None,
    event_precision: str = "unknown",
    published_at: str | None = None,
    published_precision: str = "unknown",
    payload: dict | None = None,
) -> RawRecord:
    return RawRecord(
        source=source,
        source_record_id=record_id,
        record_type=record_type,
        title=title,
        url=url,
        event_at=event_at,
        event_at_precision=event_precision,
        published_at=published_at,
        published_at_precision=published_precision,
        payload=payload or {"title": title},
    )


def _mapping(entity_id=None, entity_status="UNMAPPED", track_id=None, track_status="UNMAPPED",
             method=None, note=None) -> MappingResult:
    return MappingResult(
        entity_id=entity_id,
        entity_status=entity_status,
        entity_method=method,
        track_id=track_id,
        track_status=track_status,
        note_zh=note,
    )


def _iso(moment) -> str:
    return moment.replace(microsecond=0).isoformat()


def build_synthetic_ledger(path: Path) -> dict:
    """Deterministic synthetic ledger; returns ids/timestamps used by the tests."""
    now = utc_now().replace(microsecond=0)

    def ago(*, days: int = 0, hours: int = 0):
        return now - timedelta(days=days, hours=hours)

    ledger = ObservationLedger(path)
    try:
        ledger.ensure_source(
            "sec_edgar",
            label_zh="SEC EDGAR 公开披露",
            adapter_version="sec-edgar/1.0.0",
            declared_cadence_zh="默认每 6 小时轮询；SEC 受理后通常数分钟即可检索",
        )
        ledger.ensure_source(
            "ctgov",
            label_zh="ClinicalTrials.gov 注册库",
            adapter_version="ctgov/1.0.0",
            declared_cadence_zh="每 12 小时轮询",
        )
        ledger.ensure_source(
            "europepmc",
            label_zh="Europe PMC 文献库",
            adapter_version="europepmc/1.0.0",
            declared_cadence_zh="每 24 小时轮询",
        )
        run_sec = ledger.start_run("sec_edgar", trigger="manual", collector_version=COLLECTOR)
        run_ctgov = ledger.start_run("ctgov", trigger="manual", collector_version=COLLECTOR)

        # A — fresh NEW (24h), measured lag available (published datetime).
        record_a = _record(
            "sec_edgar", "0001-26-000001", "sec_8k",
            "8-K｜Item 8.01（Medtronic plc，2026-10-30 提交）",
            url="https://www.sec.gov/Archives/edgar/data/1/0001-26-000001-index.htm",
            event_at=ago(days=1).date().isoformat(),
            event_precision=PRECISION_DATE,
            published_at=_iso(ago(hours=4)),
            published_precision=PRECISION_DATETIME,
            payload={"form": "8-K", "items": "8.01", "issuer": "Medtronic plc"},
        )
        obs_a = ledger.record_observation(
            record_a,
            _mapping("medtronic", "MAPPED", "patient_monitoring", "MAPPED",
                     "manual_synthetic_track", "合成示例：测试映射"),
            run_id=run_sec, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(hours=2)),
        ).observation_id

        # B — fresh NEW (24h) clinical trial, mapped company + track.
        record_b = _record(
            "ctgov", "NCT00000002", "trial", "Cardiac rhythm trial (Philips)",
            url="https://clinicaltrials.gov/study/NCT00000002",
            event_at=_iso(ago(hours=11)),
            event_precision=PRECISION_DATETIME,
            published_at=_iso(ago(hours=10)),
            published_precision=PRECISION_DATETIME,
            payload={"nct_id": "NCT00000002", "status": "Recruiting"},
        )
        obs_b = ledger.record_observation(
            record_b,
            _mapping("philips", "MAPPED", "cardiac_rhythm", "MAPPED", "ctgov_keyword"),
            run_id=run_ctgov, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(hours=2)),
        ).observation_id

        # C — unmapped, no published/event time: "无法测量" path.
        record_c = _record(
            "ctgov", "NCT00000003", "trial", "Unmapped sponsor trial",
            payload={"nct_id": "NCT00000003"},
        )
        obs_c = ledger.record_observation(
            record_c,
            _mapping(note="申办方未匹配任何已核验企业别名"),
            run_id=run_ctgov, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(hours=5)),
        ).observation_id

        # D — NEW 20 days ago, then UPDATED 3 hours ago (version chain).
        record_d_v1 = _record(
            "sec_edgar", "0001-26-000004", "sec_8k", "8-K｜Medtronic 8-K（初始版本）",
            url="https://www.sec.gov/Archives/edgar/data/1/0001-26-000004-index.htm",
            event_at=ago(days=60).date().isoformat(),
            event_precision=PRECISION_DATE,
            published_at=_iso(ago(days=20, hours=2)),
            published_precision=PRECISION_DATETIME,
            payload={"form": "8-K", "items": "2.02", "title": "Draft"},
        )
        obs_d = ledger.record_observation(
            record_d_v1,
            _mapping("medtronic", "MAPPED", "patient_monitoring", "MAPPED", "sec_cik_exact"),
            run_id=run_sec, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(days=20)),
        ).observation_id
        record_d_v2 = _record(
            "sec_edgar", "0001-26-000004", "sec_8k", "8-K｜Medtronic 8-K（修订版本）",
            url="https://www.sec.gov/Archives/edgar/data/1/0001-26-000004-index.htm",
            event_at=ago(days=60).date().isoformat(),
            event_precision=PRECISION_DATE,
            published_at=_iso(ago(days=20, hours=2)),
            published_precision=PRECISION_DATETIME,
            payload={"form": "8-K", "items": "2.02,9.01", "title": "Revised"},
        )
        ledger.record_observation(
            record_d_v2,
            _mapping("medtronic", "MAPPED", "patient_monitoring", "MAPPED", "sec_cik_exact"),
            run_id=run_sec, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(hours=3)),
        )

        # E — observed 25h ago, then REMOVED 1h ago.
        record_e = _record(
            "ctgov", "NCT00000005", "trial", "Philips respiratory trial (removed at source)",
            url="https://clinicaltrials.gov/study/NCT00000005",
            event_at=ago(days=2).date().isoformat(),
            event_precision=PRECISION_DATE,
            published_at=_iso(ago(hours=30)),
            published_precision=PRECISION_DATETIME,
            payload={"nct_id": "NCT00000005", "status": "Withdrawn"},
        )
        obs_e = ledger.record_observation(
            record_e,
            _mapping("philips", "MAPPED", "respiratory", "MAPPED", "ctgov_keyword"),
            run_id=run_ctgov, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(hours=25)),
        ).observation_id
        ledger.mark_removed(
            obs_e, run_id=run_ctgov, note_zh="来源不再返回该记录（合成演示）",
            seen_at=_iso(ago(hours=1)),
        )

        # F — observed 25h ago, then FETCH_FAILED 1h ago; entity PENDING_REVIEW.
        record_f = _record(
            "sec_edgar", "0001-26-000006", "sec_6k", "6-K｜Medtronic 疑似记录（待人工复核）",
            published_at=_iso(ago(hours=26)),
            published_precision=PRECISION_DATETIME,
            payload={"form": "6-K", "issuer": "Medtronic"},
        )
        obs_f = ledger.record_observation(
            record_f,
            _mapping(
                entity_id=None, entity_status="PENDING_REVIEW", method="sec_issuer_name",
                note="疑似 medtronic（置信度 0.60）；未经人工确认，不升格为企业事实",
            ),
            run_id=run_sec, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(hours=25)),
        ).observation_id
        ledger.mark_fetch_failed(
            obs_f, run_id=run_sec, message="HTTP 503 from data.sec.gov",
            seen_at=_iso(ago(hours=1)),
        )

        # G — BACKFILLED observation (origin fields must be visible and honest).
        record_g = _record(
            "europepmc", "PMC9000001", "publication", "Backfilled publication (synthetic)",
            event_at=ago(days=40).date().isoformat(),
            event_precision=PRECISION_DATE,
            published_at=_iso(ago(days=40)),
            published_precision=PRECISION_DATETIME,
            payload={"pmcid": "PMC9000001", "title": "Synthetic backfill"},
        )
        obs_g = ledger.record_observation(
            record_g,
            _mapping(note="文献未做技术赛道映射"),
            run_id=run_sec, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(days=5)),
            origin=ORIGIN_BACKFILLED,
            backfill_reason="synthetic demo: historical material intentionally ingested into the past",
        ).observation_id

        # H — older NEW (10 days ago): 30d window only.
        record_h = _record(
            "sec_edgar", "0001-26-000008", "sec_10q", "10-Q｜Medtronic 季度报告",
            event_at=ago(days=11).date().isoformat(),
            event_precision=PRECISION_DATE,
            published_at=_iso(ago(days=10, hours=1)),
            published_precision=PRECISION_DATETIME,
            payload={"form": "10-Q"},
        )
        obs_h = ledger.record_observation(
            record_h,
            _mapping("medtronic", "MAPPED", "patient_monitoring", "MAPPED", "sec_cik_exact"),
            run_id=run_sec, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(days=10)),
        ).observation_id

        ledger.finish_run(
            run_sec, status="PARTIAL",
            counters={"requests": 5, "pages": 2, "records_seen": 15, "records_new": 6,
                      "records_updated": 1, "records_unchanged": 8, "records_removed": 1,
                      "records_failed": 1},
        )
        ledger.note_source_success("sec_edgar", run_id=run_sec)
        ledger.set_entity_coverage(
            "sec_edgar",
            [
                {
                    "entity_id": "medtronic",
                    "name": "Medtronic",
                    "ticker": "MDT",
                    "status": "COVERED",
                    "identifier": "CIK 0001613103",
                    "evidence_zh": "SEC 官方 ticker 列表核验 CIK 0001613103，submissions 复核通过",
                },
                {
                    "entity_id": "draeger",
                    "name": "Dräger",
                    "ticker": "DRW3",
                    "status": "NOT_REGISTRANT",
                    "identifier": None,
                    "evidence_zh": "SEC 公司检索返回 0 条记录，该企业不是 SEC 发行人",
                },
            ],
        )
        ledger.finish_run(
            run_ctgov, status="FAILED",
            counters={"requests": 2, "pages": 1, "records_seen": 2, "records_new": 2,
                      "records_failed": 1},
            error_detail="HTTP 503 while fetching study page 2",
        )
        ledger.note_source_failure(
            "ctgov", run_id=run_ctgov, message="HTTP 503 while fetching study page 2",
            degraded=False,
        )
        ledger.record_failure(
            "ctgov", kind="HTTP_ERROR", message="HTTP 503 while fetching study page 2",
            run_id=run_ctgov, http_status=503, retryable=True, attempt=2,
        )

        # Acquisition phases are append-only metadata derived from run history; they
        # never rewrite the observation rows above.
        ledger.reconstruct_phases()

        return {
            "now": now,
            "ago": ago,
            "obs_a": obs_a,
            "obs_b": obs_b,
            "obs_c": obs_c,
            "obs_d": obs_d,
            "obs_e": obs_e,
            "obs_f": obs_f,
            "obs_g": obs_g,
            "obs_h": obs_h,
            "run_sec": run_sec,
            "run_ctgov": run_ctgov,
        }
    finally:
        ledger.close()


@pytest.fixture()
def ledger_env(tmp_path, monkeypatch):
    path = tmp_path / "observatory_test.sqlite"
    monkeypatch.setenv("MEDRADAR_OBSERVATORY_DB", str(path))
    return build_synthetic_ledger(path)


@pytest.fixture()
def missing_ledger_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDRADAR_OBSERVATORY_DB", str(tmp_path / "no_such_ledger.sqlite"))


# ---------------------------------------------------------------- exact shapes
def test_summary_exact_shape(ledger_env):
    """Tier: SYNTHETIC — summary returns exactly the §6 top-level and nested keys."""
    response = client.get("/api/observatory/summary")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "generated_at", "ledger", "windows", "first_observation", "by_source",
        "by_company", "by_track", "unmapped", "phases", "validation", "deployment",
        "empty", "limitations",
    }
    assert set(payload["ledger"]) == {
        "path", "exists", "bytes", "observations", "versions", "changes",
        "live_observations", "backfilled_observations", "sources",
        "first_live_observation_at", "first_run_at", "last_run_at",
        "schema_version", "honesty_zh",
    }
    assert payload["ledger"]["exists"] is True
    assert payload["ledger"]["schema_version"] == "obs-ledger-v1"
    assert payload["ledger"]["observations"] == 8
    assert payload["ledger"]["versions"] == 9
    assert payload["ledger"]["changes"] == 11
    assert payload["ledger"]["live_observations"] == 7
    assert payload["ledger"]["backfilled_observations"] == 1
    assert payload["empty"] is False
    assert not Path(payload["ledger"]["path"]).is_absolute()

    for window_id in ("24h", "7d", "30d"):
        assert set(payload["windows"][window_id]) == {"new", "updated", "removed", "failed", "total"}
    assert payload["windows"]["24h"] == {"new": 3, "updated": 1, "removed": 1, "failed": 1, "total": 6}
    assert payload["windows"]["7d"] == {"new": 6, "updated": 1, "removed": 1, "failed": 1, "total": 9}
    assert payload["windows"]["30d"] == {"new": 8, "updated": 1, "removed": 1, "failed": 1, "total": 11}

    first = payload["first_observation"]
    assert set(first) == {"change_id", "observed_at", "source", "title"}
    assert first["source"] == "sec_edgar"
    # the earliest observation is D's initial NEW (20 days ago)
    assert first["observed_at"].startswith(_iso(ledger_env["ago"](days=20))[:13])

    assert payload["by_source"], "registered sources must be listed"
    for item in payload["by_source"]:
        assert set(item) == {
            "source", "label_zh", "status", "status_label_zh", "last_success_at",
            "last_attempt_at", "declared_cadence_zh", "consecutive_failures",
            "last_outcome", "last_outcome_label_zh", "last_new_records",
            "last_updated_records", "new_24h", "updated_24h", "new_7d", "updated_7d",
            "measured_lag", "coverage_zh", "limitation_zh",
        }
        assert set(item["measured_lag"]) == {
            "measurable", "note_zh", "p50_hours", "p90_hours", "max_hours", "n",
        }
        # never call a polled source "实时"
        assert "轮询" in item["declared_cadence_zh"]
        assert "实时" not in item["declared_cadence_zh"]
    by_source = {item["source"]: item for item in payload["by_source"]}
    assert by_source["sec_edgar"]["status"] == "OK"
    assert by_source["sec_edgar"]["measured_lag"]["measurable"] is True
    assert by_source["sec_edgar"]["measured_lag"]["n"] >= 1
    assert by_source["sec_edgar"]["measured_lag"]["p50_hours"] is not None
    assert by_source["ctgov"]["status"] == "FAILED"
    assert by_source["ctgov"]["consecutive_failures"] == 1
    assert by_source["europepmc"]["status"] == "NEVER_RUN"
    # backfilled records never count as measured latency
    assert by_source["europepmc"]["measured_lag"]["measurable"] is False
    assert by_source["europepmc"]["measured_lag"]["p50_hours"] is None
    assert "无法测量" in by_source["europepmc"]["measured_lag"]["note_zh"]
    assert "已逐家核验" in by_source["sec_edgar"]["coverage_zh"]

    for item in payload["by_company"]:
        assert set(item) == {
            "entity_id", "name_zh", "new_24h", "updated_24h", "new_7d", "updated_7d",
            "total", "status",
        }
    by_company = {item["entity_id"]: item for item in payload["by_company"]}
    assert by_company["medtronic"]["new_7d"] == 1  # A (D updated, H outside 7d)
    assert by_company["medtronic"]["total"] == 3  # A, D, H (F is pending review)
    assert by_company["__unmapped__"]["status"] in {"PENDING_REVIEW", "UNMAPPED"}

    for item in payload["by_track"]:
        assert set(item) == {
            "track_id", "name_zh", "domain", "new_24h", "updated_24h", "new_7d",
            "updated_7d",
        }
    by_track = {item["track_id"]: item for item in payload["by_track"]}
    assert by_track["cardiac_rhythm"]["name_zh"].startswith("心脏节律")
    assert by_track["cardiac_rhythm"]["new_7d"] == 1
    assert by_track["__unmapped__"]["name_zh"] == "未映射"

    assert set(payload["unmapped"]) == {"company", "track", "note_zh"}
    assert payload["unmapped"]["company"] >= 2
    assert payload["unmapped"]["track"] >= 1

    assert set(payload["phases"]) == {
        "counts", "initial", "incremental", "backfill", "unlabelled", "note_zh",
    }
    assert set(payload["phases"]["counts"]) == {
        "INITIAL_DISCOVERY", "INCREMENTAL_DISCOVERY", "HISTORICAL_BACKFILL",
    }
    # 7 LIVE records are INITIAL_DISCOVERY; the BACKFILLED record is HISTORICAL_BACKFILL
    assert payload["phases"]["initial"] == 7
    assert payload["phases"]["incremental"] == 0
    assert payload["phases"]["backfill"] == 1
    assert payload["phases"]["unlabelled"] == 0
    assert "初次发现" in payload["phases"]["note_zh"]
    assert "不等于" in payload["phases"]["note_zh"]

    assert set(payload["validation"]) == {
        "status", "status_label_zh", "started_at", "ends_at", "planned_slots",
        "due_slots", "executed_slots", "missed_slots", "days_elapsed",
        "days_remaining", "scheduler_success_rate", "note_zh",
    }
    assert payload["validation"]["status"] == "VALIDATION_NOT_STARTED"
    assert payload["validation"]["planned_slots"] == 0
    assert "通过" not in payload["validation"]["status_label_zh"].lower()
    assert set(payload["deployment"]) == {
        "status", "status_label_zh", "installed_at", "supervisor", "host", "note_zh",
    }
    assert payload["deployment"]["status"] == "NOT_DEPLOYED"
    assert payload["deployment"]["supervisor"] == "none"

    assert payload["limitations"]
    for item in payload["limitations"]:
        assert set(item) == {"id", "text_zh"}


def test_events_exact_shape_and_facets(ledger_env):
    """Tier: SYNTHETIC — events shape, filters echo, facets and window bounds."""
    response = client.get("/api/observatory/events")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"total", "limit", "offset", "window", "filters", "facets", "items"}
    assert payload["total"] == 9
    assert payload["limit"] == 50 and payload["offset"] == 0
    assert set(payload["window"]) == {"id", "hours", "start", "end"}
    assert payload["window"]["id"] == "7d" and payload["window"]["hours"] == 168
    assert payload["window"]["start"] < payload["window"]["end"]
    assert payload["filters"] == {
        "change": "all", "source": None, "company": None, "track": None, "q": None,
        "phase": None,
    }
    assert set(payload["facets"]) == {"sources", "companies", "tracks", "changes", "phases"}
    for item in payload["facets"]["phases"]:
        assert set(item) == {"phase", "label_zh", "description_zh", "count"}
    phase_facets = {item["phase"]: item["count"] for item in payload["facets"]["phases"]}
    # facet counts are *change* counts within the window (initial 8 changes: the
    # 20d/10d-old NEW rows are outside 7d; backfill 1 change), not observation counts.
    assert phase_facets == {
        "INITIAL_DISCOVERY": 8,
        "INCREMENTAL_DISCOVERY": 0,
        "HISTORICAL_BACKFILL": 1,
    }
    phase_labels = {item["phase"]: item["label_zh"] for item in payload["facets"]["phases"]}
    assert phase_labels == {
        "INITIAL_DISCOVERY": "初次发现",
        "INCREMENTAL_DISCOVERY": "增量发现",
        "HISTORICAL_BACKFILL": "历史回填",
    }
    for item in payload["facets"]["sources"]:
        assert set(item) == {"source", "label_zh", "count"}
    for item in payload["facets"]["companies"]:
        assert set(item) == {"entity_id", "name_zh", "count"}
    for item in payload["facets"]["tracks"]:
        assert set(item) == {"track_id", "name_zh", "count"}
    for item in payload["facets"]["changes"]:
        assert set(item) == {"change_state", "label_zh", "count"}
    changes = {item["change_state"]: item["count"] for item in payload["facets"]["changes"]}
    assert changes == {
        "NEW": 6, "UPDATED": 1, "REMOVED_OR_UNAVAILABLE": 1, "FETCH_FAILED": 1,
    }
    labels = {item["change_state"]: item["label_zh"] for item in payload["facets"]["changes"]}
    assert labels == {
        "NEW": "新增",
        "UPDATED": "修订",
        "REMOVED_OR_UNAVAILABLE": "不再提供",
        "FETCH_FAILED": "采集失败",
    }
    sources = {item["source"]: item["count"] for item in payload["facets"]["sources"]}
    assert sources == {"sec_edgar": 4, "ctgov": 4, "europepmc": 1}
    companies = {item["entity_id"]: item["count"] for item in payload["facets"]["companies"]}
    assert companies["medtronic"] == 2
    assert companies["philips"] == 3
    assert companies["__unmapped__"] == 4
    tracks = {item["track_id"]: item["count"] for item in payload["facets"]["tracks"]}
    assert tracks["patient_monitoring"] == 2
    assert tracks["cardiac_rhythm"] == 1
    assert tracks["respiratory"] == 2
    assert tracks["__unmapped__"] == 4

    for item in payload["items"]:
        assert set(item) == ITEM_KEYS
        assert set(item["time_basis"]) == TIME_BASIS_KEYS
        assert set(item["company"]) == COMPANY_KEYS
        assert set(item["track"]) == TRACK_KEYS
        assert set(item["version"]) == VERSION_KEYS
        assert item["change_state"] in {
            "NEW", "UPDATED", "REMOVED_OR_UNAVAILABLE", "FETCH_FAILED",
        }
        # every row carries its acquisition phase and the short Chinese label; the
        # phase is not the change state and not observation_origin.
        assert item["phase"] in {"INITIAL_DISCOVERY", "HISTORICAL_BACKFILL"}
        assert item["phase_label_zh"] in {"初次发现", "历史回填"}
        # the two time statements are never merged
        assert "该事件发生于" in item["time_basis"]["statement_zh"] or "来源未提供事件发生时间" in item["time_basis"]["statement_zh"]
        assert "首次观察到它" in item["time_basis"]["statement_zh"]


def test_events_window_and_type_filters(ledger_env):
    """Tier: SYNTHETIC — window / change filters narrow the result correctly."""
    for window, expected_total in (("24h", 6), ("7d", 9), ("30d", 11)):
        payload = client.get(
            "/api/observatory/events", params={"window": window}
        ).json()
        assert payload["window"]["id"] == window
        assert payload["total"] == expected_total

    for change, expected in (
        ("new", 6),
        ("updated", 1),
        ("removed", 1),
        ("failed", 1),
    ):
        payload = client.get(
            "/api/observatory/events", params={"window": "7d", "change": change}
        ).json()
        assert payload["total"] == expected
        expected_state = {
            "new": "NEW",
            "updated": "UPDATED",
            "removed": "REMOVED_OR_UNAVAILABLE",
            "failed": "FETCH_FAILED",
        }[change]
        assert all(item["change_state"] == expected_state for item in payload["items"])

    updated = client.get(
        "/api/observatory/events", params={"window": "7d", "change": "updated"}
    ).json()["items"][0]
    assert updated["is_revision"] is True
    assert updated["change_label_zh"] == "修订"
    assert updated["version"]["version_seq"] == 2
    assert updated["version"]["version_count"] == 2
    assert updated["changed_fields"]
    for field in updated["changed_fields"]:
        assert set(field) == {"field", "label_zh", "old", "new"}
        assert field["label_zh"] != field["field"]
    assert {field["field"] for field in updated["changed_fields"]} == {"items", "title"}
    assert updated["evidence_zh"]

    removed = client.get(
        "/api/observatory/events", params={"change": "removed"}
    ).json()["items"][0]
    assert removed["change_label_zh"] == "不再提供"
    assert removed["url"]

    failed = client.get(
        "/api/observatory/events", params={"change": "failed"}
    ).json()["items"][0]
    assert failed["change_label_zh"] == "采集失败"
    assert failed["company"]["status"] == "PENDING_REVIEW"
    assert failed["company"]["note_zh"]
    # a failed fetch is never labelled as "no new events"
    assert "无新事件" not in failed["evidence_zh"]


def test_events_source_company_track_and_search_filters(ledger_env):
    """Tier: SYNTHETIC — source / company / track / q filters and unmapped option."""
    by_source = client.get(
        "/api/observatory/events", params={"window": "7d", "source": "ctgov"}
    ).json()
    assert by_source["total"] == 4
    assert {item["source"] for item in by_source["items"]} == {"ctgov"}
    assert by_source["filters"]["source"] == "ctgov"

    by_company = client.get(
        "/api/observatory/events", params={"window": "30d", "company": "medtronic"}
    ).json()
    assert by_company["total"] == 4
    assert by_company["filters"]["company"] == "medtronic"
    assert all(item["company"]["entity_id"] == "medtronic" for item in by_company["items"])
    assert all(item["company"]["status"] == "MAPPED" for item in by_company["items"])

    unmapped_only = client.get(
        "/api/observatory/events", params={"window": "7d", "company": "__unmapped__"}
    ).json()
    assert unmapped_only["total"] == 4
    assert all(item["company"]["entity_id"] is None for item in unmapped_only["items"])

    by_track = client.get(
        "/api/observatory/events", params={"track": "cardiac_rhythm"}
    ).json()
    assert by_track["total"] == 1
    track = by_track["items"][0]["track"]
    assert track["track_id"] == "cardiac_rhythm"
    assert track["name_zh"].startswith("心脏节律")
    assert track["domain"] == "cardiovascular"
    assert track["status"] == "MAPPED"

    search = client.get("/api/observatory/events", params={"window": "7d", "q": "Medtronic"}).json()
    # A + D's revision + F's NEW + F's FETCH_FAILED (all titles contain the term)
    assert search["total"] == 4
    assert search["filters"]["q"] == "Medtronic"
    assert all("Medtronic" in item["title"] for item in search["items"])

    paged = client.get(
        "/api/observatory/events", params={"window": "30d", "limit": 4, "offset": 2}
    ).json()
    assert paged["limit"] == 4 and paged["offset"] == 2
    assert paged["total"] == 11
    assert len(paged["items"]) == 4


def test_events_time_semantics_are_honest(ledger_env):
    """Tier: SYNTHETIC — measurable lag only when a precise publish time exists."""
    payload = client.get(
        "/api/observatory/events", params={"window": "24h", "change": "new"}
    ).json()
    by_id = {item["observation_id"]: item for item in payload["items"]}

    measured = by_id[ledger_env["obs_a"]]
    assert measured["time_basis"]["measurable"] is True
    assert measured["time_basis"]["publish_to_first_seen_hours"] == pytest.approx(2.0, abs=0.01)
    assert measured["published_at_precision"] == "datetime"
    assert "间隔 2.0 小时" in measured["evidence_zh"]
    assert measured["event_at_precision"] == "date"
    assert "该事件发生于" in measured["time_basis"]["statement_zh"]

    unmeasurable = by_id[ledger_env["obs_c"]]
    assert unmeasurable["published_at"] is None
    assert unmeasurable["event_at"] is None
    assert unmeasurable["time_basis"]["measurable"] is False
    assert unmeasurable["time_basis"]["publish_to_first_seen_hours"] is None
    assert unmeasurable["evidence_zh"].startswith("无法测量")
    # the reason comes from observatory.lag (single source of truth for lag text)
    assert "时间" in unmeasurable["evidence_zh"]
    assert unmeasurable["title"]


def test_event_detail_version_chain_mapping_and_sync_context(ledger_env):
    """Tier: SYNTHETIC — detail shape, version chain, history and sync context."""
    response = client.get(f"/api/observatory/events/{ledger_env['obs_d']}")
    assert response.status_code == 200
    detail = response.json()
    assert set(detail) == {
        "observation", "versions", "changes", "mapping_history", "status_history",
        "sync_context", "limitations",
    }
    observation = detail["observation"]
    assert set(observation) == ITEM_KEYS | DETAIL_EXTRA
    assert observation["observation_id"] == ledger_env["obs_d"]
    assert observation["change_state"] == "UPDATED"
    assert observation["is_revision"] is True
    assert observation["version"]["version_count"] == 2
    assert observation["observation_origin"] == "LIVE"
    assert observation["observation_status"] == "ACTIVE"
    assert observation["source_record_id"] == "0001-26-000004"
    assert observation["last_checked_at"]

    assert len(detail["versions"]) == 2
    assert [version["version_seq"] for version in detail["versions"]] == [1, 2]
    assert [version["change_state"] for version in detail["versions"]] == ["NEW", "UPDATED"]
    for version in detail["versions"]:
        assert set(version) == {
            "version_seq", "version_id", "captured_at", "change_state",
            "payload_hash", "changed_fields", "payload",
        }
        assert isinstance(version["payload"], dict)
    assert detail["versions"][0]["payload"]["title"] == "Draft"
    assert detail["versions"][1]["payload"]["title"] == "Revised"
    assert detail["versions"][1]["changed_fields"] == ["items", "title"]

    assert detail["changes"]
    for change in detail["changes"]:
        assert set(change) == {
            "change_id", "change_state", "observed_at", "version_id", "changed_fields",
        }
    assert {change["change_state"] for change in detail["changes"]} == {"NEW", "UPDATED"}

    assert detail["mapping_history"]
    for row in detail["mapping_history"]:
        assert set(row) == {
            "mapping_version", "mapped_at", "entity_id", "entity_status", "track_id",
            "track_status", "note_zh",
        }
    assert detail["mapping_history"][0]["entity_id"] == "medtronic"

    assert len(detail["status_history"]) == 1
    assert set(detail["status_history"][0]) == {"changed_at", "status", "note"}
    assert detail["status_history"][0]["status"] == "ACTIVE"

    assert set(detail["sync_context"]) == {"first_seen_run_id", "run", "source_state"}
    assert detail["sync_context"]["first_seen_run_id"] == ledger_env["run_sec"]
    assert detail["sync_context"]["run"]["run_id"] == ledger_env["run_sec"]
    assert detail["sync_context"]["source_state"]["source"] == "sec_edgar"

    for item in detail["limitations"]:
        assert set(item) == {"id", "text_zh"}


def test_event_detail_backfilled_origin_is_visible(ledger_env):
    """Tier: SYNTHETIC — BACKFILLED origin and reason are never hidden."""
    detail = client.get(f"/api/observatory/events/{ledger_env['obs_g']}").json()
    observation = detail["observation"]
    assert observation["observation_origin"] == "BACKFILLED"
    assert observation["backfill_reason"]
    limitation_ids = {item["id"] for item in detail["limitations"]}
    assert "backfilled_observation" in limitation_ids
    assert detail["versions"][0]["change_state"] == "NEW"


def test_event_detail_removed_and_failed_states(ledger_env):
    """Tier: SYNTHETIC — REMOVED / FETCH_FAILED are their own claims in detail."""
    removed = client.get(f"/api/observatory/events/{ledger_env['obs_e']}").json()
    assert removed["observation"]["change_state"] == "REMOVED_OR_UNAVAILABLE"
    assert removed["observation"]["observation_status"] == "REMOVED_OR_UNAVAILABLE"
    assert {item["id"] for item in removed["limitations"]} >= {"removed_not_gone"}

    failed = client.get(f"/api/observatory/events/{ledger_env['obs_f']}").json()
    assert failed["observation"]["change_state"] == "FETCH_FAILED"
    assert failed["observation"]["observation_status"] == "ACTIVE"
    # a fetch failure does not invent a version
    assert failed["versions"][0]["change_state"] == "NEW"


def test_event_detail_unknown_id_is_404(ledger_env):
    """Tier: SYNTHETIC — unknown observation_id maps to 404, never a 500."""
    response = client.get("/api/observatory/events/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_sources_exact_shape_and_sync_panel(ledger_env):
    """Tier: SYNTHETIC — per-source sync status, lag, runs, failures, coverage."""
    response = client.get("/api/observatory/sources")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"sources", "generated_at"}
    sources = {item["source"]: item for item in payload["sources"]}
    assert set(sources) == {"sec_edgar", "ctgov", "europepmc"}
    for item in payload["sources"]:
        assert set(item) == {
            "source", "label_zh", "status", "status_label_zh", "declared_cadence_zh",
            "last_attempt_at", "last_success_at", "last_failure_at",
            "consecutive_failures", "watermark", "watermark_updated_at", "structure",
            "counts", "recent_runs", "recent_failures", "entity_coverage",
            "measured_lag", "coverage_note_zh", "limitation_zh",
        }
        assert set(item["structure"]) == {"signature", "changed_at", "note_zh"}
        assert set(item["counts"]) == {
            "runs_total", "runs_ok", "runs_failed", "observations", "new_7d",
            "updated_7d", "records_failed",
        }
        assert "轮询" in item["declared_cadence_zh"]
        assert "实时" not in item["declared_cadence_zh"]

    sec = sources["sec_edgar"]
    assert sec["status"] == "OK"
    assert sec["counts"]["observations"] == 4
    assert sec["counts"]["runs_total"] == 1
    assert sec["counts"]["records_failed"] == 1
    assert sec["measured_lag"]["measurable"] is True
    assert sec["recent_runs"]
    for run in sec["recent_runs"]:
        assert set(run) == {
            "run_id", "started_at", "finished_at", "status", "trigger", "requests",
            "records_seen", "records_new", "records_updated", "records_unchanged",
            "records_removed", "error_detail",
        }
    assert sec["recent_runs"][0]["status"] == "PARTIAL"

    coverage = {row["entity_id"]: row for row in sec["entity_coverage"]}
    assert set(coverage) == {"medtronic", "draeger"}
    for row in sec["entity_coverage"]:
        assert set(row) == {
            "entity_id", "name_zh", "covered", "evidence_zh", "identifier", "status",
        }
        assert row["evidence_zh"]
    assert coverage["medtronic"]["status"] == "COVERED"
    assert coverage["medtronic"]["covered"] is True
    assert coverage["medtronic"]["identifier"] == "CIK 0001613103"
    assert coverage["draeger"]["status"] == "NOT_REGISTRANT"
    assert coverage["draeger"]["covered"] is False
    assert "已逐家核验" in sec["coverage_note_zh"]

    ctgov = sources["ctgov"]
    assert ctgov["status"] == "FAILED"
    assert ctgov["status_label_zh"] == "失败"
    assert ctgov["consecutive_failures"] == 1
    assert ctgov["last_failure_at"]
    assert ctgov["recent_failures"]
    for failure in ctgov["recent_failures"]:
        assert set(failure) == {
            "occurred_at", "kind", "message", "http_status", "retryable",
        }
    assert ctgov["recent_failures"][0]["http_status"] == 503
    assert ctgov["recent_failures"][0]["retryable"] is True

    assert sources["europepmc"]["status"] == "NEVER_RUN"
    assert sources["europepmc"]["counts"]["runs_total"] == 0
    assert sources["europepmc"]["recent_runs"] == []
    assert sources["europepmc"]["measured_lag"]["measurable"] is False


def test_replay_excludes_later_discoveries(ledger_env):
    """Tier: SYNTHETIC — replay uses first_seen_at, not event_at (§3.3)."""
    before_all = client.get(
        "/api/observatory/replay",
        params={"as_of": _iso(ledger_env["ago"](days=40))},
    )
    assert before_all.status_code == 200
    payload = before_all.json()
    assert set(payload) == {
        "as_of", "policy_zh", "total", "excluded_discovered_later", "items",
    }
    assert payload["total"] == 0
    assert payload["items"] == []
    assert payload["excluded_discovered_later"] == 8
    assert "first_seen_at" in payload["policy_zh"]

    after_all = client.get(
        "/api/observatory/replay",
        params={"as_of": _iso(ledger_env["now"])},
    ).json()
    assert after_all["total"] == 8
    assert after_all["excluded_discovered_later"] == 0
    for item in after_all["items"]:
        assert set(item) == {
            "observation_id", "source", "title", "first_seen_at", "event_at",
            "version_seq", "captured_at", "status", "payload_hash",
        }

    # A record whose event is 60 days old but which was first observed 10 days
    # ago must be absent from a replay 40 days ago (knowledge, not event_at).
    week_ago = client.get(
        "/api/observatory/replay",
        params={"as_of": _iso(ledger_env["ago"](days=7))},
    ).json()
    assert week_ago["total"] == 2  # D (20d) and H (10d) were known; A/G/E/F were not
    assert week_ago["excluded_discovered_later"] == 6
    assert {item["observation_id"] for item in week_ago["items"]} == {
        ledger_env["obs_d"], ledger_env["obs_h"],
    }

    filtered = client.get(
        "/api/observatory/replay",
        params={"as_of": _iso(ledger_env["now"]), "source": "ctgov", "limit": 2},
    ).json()
    assert filtered["total"] == 2
    assert all(item["source"] == "ctgov" for item in filtered["items"])
    assert len(filtered["items"]) == 2


# ------------------------------------------------------------- missing ledger
def test_missing_ledger_is_an_honest_empty_state(missing_ledger_env):
    """Tier: SYNTHETIC — no ledger file: HTTP 200, exists false, no fake events."""
    summary = client.get("/api/observatory/summary")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["ledger"]["exists"] is False
    assert payload["ledger"]["observations"] == 0
    assert payload["ledger"]["bytes"] == 0
    assert payload["ledger"]["honesty_zh"]
    assert payload["empty"] is True
    assert payload["first_observation"] is None
    assert payload["by_source"] == [] and payload["by_company"] == [] and payload["by_track"] == []
    for window_id in ("24h", "7d", "30d"):
        assert payload["windows"][window_id] == {
            "new": 0, "updated": 0, "removed": 0, "failed": 0, "total": 0,
        }
    assert any(item["id"] == "ledger_missing" for item in payload["limitations"])
    assert not Path(payload["ledger"]["path"]).is_absolute()

    events = client.get("/api/observatory/events")
    assert events.status_code == 200
    events_payload = events.json()
    assert events_payload["total"] == 0
    assert events_payload["items"] == []
    assert events_payload["facets"]["sources"] == []
    assert events_payload["facets"]["companies"] == []
    assert events_payload["facets"]["tracks"] == []
    assert [item["count"] for item in events_payload["facets"]["changes"]] == [0, 0, 0, 0]
    assert [item["count"] for item in events_payload["facets"]["phases"]] == [0, 0, 0]
    assert events_payload["filters"]["phase"] is None

    assert payload["phases"] == {
        "counts": {
            "INITIAL_DISCOVERY": 0,
            "INCREMENTAL_DISCOVERY": 0,
            "HISTORICAL_BACKFILL": 0,
        },
        "initial": 0,
        "incremental": 0,
        "backfill": 0,
        "unlabelled": 0,
        "note_zh": payload["phases"]["note_zh"],
    }
    assert payload["validation"]["status"] == "VALIDATION_NOT_STARTED"
    assert payload["deployment"]["status"] == "NOT_DEPLOYED"

    # A missing ledger is an honest NOT_DEPLOYED health body, never a green badge
    # and never a 500.
    health = client.get("/api/observatory/health")
    assert health.status_code == 200
    health_payload = health.json()
    assert health_payload["overall"] == "NOT_DEPLOYED"
    assert health_payload["overall_label_zh"] == "未部署"
    assert health_payload["deployment"]["status"] == "NOT_DEPLOYED"
    assert health_payload["validation"]["status"] == "VALIDATION_NOT_STARTED"
    assert health_payload["sources"] == []
    assert any(
        check["id"] == "ledger_exists" and check["ok"] is False
        for check in health_payload["checks"]
    )
    assert health_payload["overall_note_zh"]
    assert not Path(health_payload["persistence"].get("raw_cache_path") or "x").is_absolute()

    sources = client.get("/api/observatory/sources")
    assert sources.status_code == 200
    assert sources.json()["sources"] == []

    replay = client.get(
        "/api/observatory/replay", params={"as_of": _iso(ledger_env_now())}
    )
    assert replay.status_code == 200
    replay_payload = replay.json()
    assert replay_payload["total"] == 0
    assert replay_payload["items"] == []
    assert replay_payload["excluded_discovered_later"] == 0

    detail = client.get("/api/observatory/events/anything")
    assert detail.status_code == 404
    assert detail.json()["error"] == "not_found"


def ledger_env_now():
    return utc_now().replace(microsecond=0)


# --------------------------------------------------------------- validation
def test_endpoint_bounds_and_validation(ledger_env):
    """Tier: SYNTHETIC — bad window/change/as_of are 400; bad limits are 422."""
    assert client.get("/api/observatory/events", params={"window": "99d"}).status_code == 400
    assert client.get("/api/observatory/events", params={"change": "bogus"}).status_code == 400
    assert client.get("/api/observatory/events", params={"limit": 0}).status_code == 422
    assert client.get("/api/observatory/events", params={"limit": 201}).status_code == 422
    assert client.get("/api/observatory/events", params={"offset": -1}).status_code == 422
    assert client.get("/api/observatory/replay").status_code == 422
    assert client.get(
        "/api/observatory/replay", params={"as_of": "not-a-date"}
    ).status_code == 400


def test_ledger_is_opened_readonly_through_the_env_pattern(ledger_env):
    """Tier: SYNTHETIC — the product layer sees the env-selected ledger read-only."""
    assert default_ledger_path().name == "observatory_test.sqlite"
    handle = open_ledger_readonly(default_ledger_path())
    try:
        assert handle.read_only is True
        assert handle.counts()["observations"] == 8
    finally:
        handle.close()

def test_contradictory_publish_time_is_reported_as_unmeasurable(tmp_path, monkeypatch):
    """Tier: SYNTHETIC — publish time later than first-seen is never a measurement."""
    path = tmp_path / "contradictory.sqlite"
    monkeypatch.setenv("MEDRADAR_OBSERVATORY_DB", str(path))
    now = utc_now().replace(microsecond=0)
    ledger = ObservationLedger(path)
    try:
        ledger.ensure_source(
            "sec_edgar", label_zh="SEC EDGAR 公开披露", adapter_version="test/1.0",
            declared_cadence_zh="每 6 小时轮询",
        )
        run = ledger.start_run("sec_edgar", trigger="test", collector_version=COLLECTOR)
        ledger.record_observation(
            _record(
                "sec_edgar", "CONTRADICT-0001", "sec_8k", "Contradictory timestamps",
                published_at=_iso(now - timedelta(hours=5)),
                published_precision=PRECISION_DATETIME,
                payload={"form": "8-K"},
            ),
            _mapping("medtronic", "MAPPED", method="sec_cik_exact"),
            run_id=run, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(now - timedelta(hours=10)),
        )
    finally:
        ledger.close()

    item = client.get("/api/observatory/events").json()["items"][0]
    assert item["time_basis"]["publish_to_first_seen_hours"] < 0
    assert item["time_basis"]["measurable"] is False
    assert item["evidence_zh"].startswith("无法测量")
    assert "矛盾" in item["evidence_zh"]


# ----------------------------------------------------------- observatory health
def test_health_exact_shape_and_honest_overall(ledger_env):
    """Tier: SYNTHETIC — §6 health shape; data without a deployment is NOT_DEPLOYED."""
    response = client.get("/api/observatory/health")
    assert response.status_code == 200
    payload = response.json()
    assert {
        "generated_at", "overall", "overall_label_zh", "overall_note_zh",
        "deployment", "validation", "collector", "persistence", "sources",
        "checks", "unresolved_structure_alerts", "limitations_zh",
    } <= set(payload)
    assert payload["overall"] in {
        "OPERATIONAL", "DEGRADED", "PAUSED", "NOT_DEPLOYED", "VALIDATION_IN_PROGRESS",
    }
    # data exists, but no deployment was ever recorded: NOT_DEPLOYED is the only
    # honest answer (§0 precedence).
    assert payload["overall"] == "NOT_DEPLOYED"
    assert payload["overall_label_zh"] == "未部署"
    assert payload["overall_note_zh"]
    assert payload["deployment"]["status"] == "NOT_DEPLOYED"
    assert payload["deployment"]["supervisor"] == "none"
    assert payload["deployment"]["status_label_zh"]
    assert payload["validation"]["status"] == "VALIDATION_NOT_STARTED"
    assert payload["validation"]["status_label_zh"]
    assert payload["collector"]["running"] is False
    assert {"held", "heartbeat_age_seconds", "holder"} <= set(payload["collector"]["lock"])
    assert {"ledger_bytes", "raw_cache_bytes", "backup", "restore_drill",
            "disk_free_bytes"} <= set(payload["persistence"])
    assert payload["persistence"]["backup"]["status"] == "NEVER"
    assert payload["persistence"]["restore_drill"]["status"] == "NEVER"

    sources = {item["source"]: item for item in payload["sources"]}
    assert set(sources) == {"sec_edgar", "ctgov", "europepmc"}
    for item in payload["sources"]:
        assert {
            "status", "status_label_zh", "last_success_at", "last_attempt_at",
            "last_outcome", "last_outcome_label_zh", "last_outcome_severity",
            "consecutive_failures", "freshness_hours", "stale",
            "stale_after_hours", "structure_alert",
        } <= set(item)
    assert sources["ctgov"]["status"] == "FAILED"
    assert sources["ctgov"]["status_label_zh"] == "失败"
    assert sources["ctgov"]["stale"] is True

    checks = {check["id"]: check for check in payload["checks"]}
    assert checks["sources_healthy"]["ok"] is False
    assert checks["backup"]["ok"] is False
    assert checks["restore_drill"]["ok"] is False
    # never a green overall while a source is failing and backups are missing
    assert payload["overall"] != "OPERATIONAL"
    assert payload["limitations_zh"]


def test_health_outcome_labels_keep_normal_and_failure_distinct(ledger_env):
    """Tier: SYNTHETIC — NO_NEW_RECORDS is normal, FETCH_FAILED is a failure."""
    path = default_ledger_path()
    ledger = ObservationLedger(path)
    try:
        ledger.record_outcome(
            "sec_edgar", run_id="outcome-run",
            outcome="NO_NEW_RECORDS", new=0, updated=0,
        )
        ledger.record_outcome(
            "ctgov", run_id="outcome-run",
            outcome="FETCH_FAILED", new=0, updated=0,
        )
    finally:
        ledger.close()
    payload = client.get("/api/observatory/health").json()
    sources = {item["source"]: item for item in payload["sources"]}
    assert sources["sec_edgar"]["last_outcome"] == "NO_NEW_RECORDS"
    assert sources["sec_edgar"]["last_outcome_severity"] == "normal"
    assert "正常" in sources["sec_edgar"]["last_outcome_label_zh"]
    assert sources["ctgov"]["last_outcome"] == "FETCH_FAILED"
    assert sources["ctgov"]["last_outcome_severity"] == "failure"
    assert sources["ctgov"]["last_outcome_label_zh"] == "采集失败"
    assert sources["sec_edgar"]["last_outcome_label_zh"] != sources["ctgov"]["last_outcome_label_zh"]


def test_events_phase_filter_and_facets(ledger_env):
    """Tier: SYNTHETIC — phase filter narrows rows; facets carry the phase split."""
    initial = client.get(
        "/api/observatory/events",
        params={"window": "7d", "phase": "INITIAL_DISCOVERY"},
    ).json()
    assert initial["total"] == 8
    assert initial["filters"]["phase"] == "INITIAL_DISCOVERY"
    assert initial["items"]
    assert all(item["phase"] == "INITIAL_DISCOVERY" for item in initial["items"])
    assert all(item["phase_label_zh"] == "初次发现" for item in initial["items"])

    backfill = client.get(
        "/api/observatory/events",
        params={"window": "7d", "phase": "HISTORICAL_BACKFILL"},
    ).json()
    assert backfill["total"] == 1
    assert backfill["items"][0]["observation_id"] == ledger_env["obs_g"]
    assert backfill["items"][0]["phase"] == "HISTORICAL_BACKFILL"
    assert backfill["items"][0]["phase_label_zh"] == "历史回填"

    incremental = client.get(
        "/api/observatory/events",
        params={"window": "7d", "phase": "INCREMENTAL_DISCOVERY"},
    ).json()
    assert incremental["total"] == 0
    assert incremental["items"] == []
    # an honest empty phase result, not a fabricated row
    assert incremental["facets"]["phases"]

    # facets ignore the phase filter itself so the chips stay usable
    phase_facets = {
        item["phase"]: item["count"] for item in incremental["facets"]["phases"]
    }
    assert phase_facets == {
        "INITIAL_DISCOVERY": 8,
        "INCREMENTAL_DISCOVERY": 0,
        "HISTORICAL_BACKFILL": 1,
    }

    assert client.get(
        "/api/observatory/events", params={"phase": "BOGUS"}
    ).status_code == 400


def test_events_phase_incremental_filter_works(tmp_path, monkeypatch):
    """Tier: SYNTHETIC — a later run's record is INCREMENTAL_DISCOVERY, not initial."""
    path = tmp_path / "phase_ledger.sqlite"
    monkeypatch.setenv("MEDRADAR_OBSERVATORY_DB", str(path))
    now = utc_now().replace(microsecond=0)
    ledger = ObservationLedger(path)
    try:
        ledger.ensure_source(
            "sec_edgar", label_zh="SEC EDGAR 公开披露",
            adapter_version="test/1.0", declared_cadence_zh="每 6 小时轮询",
        )
        first_run = ledger.start_run("sec_edgar", trigger="test", collector_version=COLLECTOR)
        first = ledger.record_observation(
            _record("sec_edgar", "PHASE-0001", "sec_8k", "first sweep record"),
            _mapping(), run_id=first_run, collector_version=COLLECTOR,
            mapping_version=MAPPING, seen_at=_iso(now - timedelta(hours=5)),
        )
        second_run = ledger.start_run("sec_edgar", trigger="test", collector_version=COLLECTOR)
        second = ledger.record_observation(
            _record("sec_edgar", "PHASE-0002", "sec_8k", "later sweep record"),
            _mapping(), run_id=second_run, collector_version=COLLECTOR,
            mapping_version=MAPPING, seen_at=_iso(now - timedelta(hours=2)),
        )
        # explicit collector assignment: deterministic in the synthetic fixture
        ledger.assign_phase(
            first.observation_id, "INITIAL_DISCOVERY",
            method="collector_assigned", assigned_at=_iso(now - timedelta(hours=5)),
        )
        ledger.assign_phase(
            second.observation_id, "INCREMENTAL_DISCOVERY",
            method="collector_assigned", assigned_at=_iso(now - timedelta(hours=2)),
        )
    finally:
        ledger.close()

    payload = client.get(
        "/api/observatory/events",
        params={"window": "7d", "phase": "INCREMENTAL_DISCOVERY"},
    ).json()
    assert payload["total"] == 1
    assert payload["items"][0]["title"] == "later sweep record"
    assert payload["items"][0]["phase"] == "INCREMENTAL_DISCOVERY"
    assert payload["items"][0]["phase_label_zh"] == "增量发现"

    summary = client.get("/api/observatory/summary").json()
    assert summary["phases"]["initial"] == 1
    assert summary["phases"]["incremental"] == 1
    assert summary["phases"]["backfill"] == 0
    assert summary["phases"]["unlabelled"] == 0
