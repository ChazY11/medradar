"""Build a **clearly-labelled synthetic** demo ledger for local Live Observatory UI checks.

WARNING — this script must never touch the real observation ledger. It only runs
when ``MEDRADAR_OBSERVATORY_DB`` points at a file whose name contains ``demo``,
and every record it writes says "合成演示" in its title. The real ledger
(``data/observatory/observatory.sqlite``) is only ever written by the collector;
demo data must never be seeded into it.

Usage (PowerShell, from the repository root)::

    $env:MEDRADAR_OBSERVATORY_DB='data\\observatory\\demo_observatory.sqlite'
    python tests\\fixtures\\observatory\\seed_demo_ledger.py

The ledger path resolution is the production one
(``medradar.observatory.ledger.default_ledger_path``), so the running web server
sees the demo data only when it is started with the same environment variable.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from medradar.observatory.ledger import (  # noqa: E402
    DEFAULT_LEDGER_RELATIVE,
    ObservationLedger,
)
from medradar.config import DATA_DIR  # noqa: E402
from medradar.observatory.records import (  # noqa: E402
    ORIGIN_BACKFILLED,
    PRECISION_DATE,
    PRECISION_DATETIME,
    MappingResult,
    RawRecord,
    utc_now,
)

COLLECTOR = "live-observatory/1.0.0"
MAPPING = "obs-mapping-v1"
DEMO_TAG = "合成演示"


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
        title=f"{title}（{DEMO_TAG}）",
        url=url,
        event_at=event_at,
        event_at_precision=event_precision,
        published_at=published_at,
        published_at_precision=published_precision,
        payload=payload or {"demo": True, "title": title},
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


def build_demo_ledger(path: Path) -> dict[str, int]:
    """Write the synthetic demo ledger at ``path`` (caller must check the name)."""
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
        run_sec = ledger.start_run("sec_edgar", trigger="schedule", collector_version=COLLECTOR)
        run_ctgov = ledger.start_run("ctgov", trigger="schedule", collector_version=COLLECTOR)

        # 1) Fresh SEC 8-K for Medtronic (24h window, publish latency measurable).
        ledger.record_observation(
            _record(
                "sec_edgar", "DEMO-0001-26-000001", "sec_8k",
                "8-K｜Item 8.01 战略合作披露 · Medtronic plc",
                url="https://www.sec.gov/Archives/edgar/data/0001613103/DEMO-0001-26-000001-index.htm",
                event_at=ago(days=1).date().isoformat(),
                event_precision=PRECISION_DATE,
                published_at=_iso(ago(hours=5)),
                published_precision=PRECISION_DATETIME,
                payload={"form": "8-K", "items": "8.01", "issuer": "Medtronic plc"},
            ),
            _mapping("medtronic", "MAPPED", "patient_monitoring", "MAPPED", "sec_cik_exact"),
            run_id=run_sec, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(hours=3)),
        )

        # 2) Fresh trial for Philips (mapped company + track).
        ledger.record_observation(
            _record(
                "ctgov", "NCT0000DEMO2", "trial",
                "心脏节律起搏器前瞻性注册研究 · Philips",
                url="https://clinicaltrials.gov/study/NCT0000DEMO2",
                event_at=_iso(ago(hours=20)),
                event_precision=PRECISION_DATETIME,
                published_at=_iso(ago(hours=19)),
                published_precision=PRECISION_DATETIME,
                payload={"nct_id": "NCT0000DEMO2", "status": "Recruiting"},
            ),
            _mapping("philips", "MAPPED", "cardiac_rhythm", "MAPPED", "ctgov_keyword"),
            run_id=run_ctgov, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(hours=2)),
        )

        # 3) Unmapped sponsor trial (未映射 option in the UI filters).
        ledger.record_observation(
            _record(
                "ctgov", "NCT0000DEMO3", "trial",
                "未映射申办方的呼吸支持器械研究",
                payload={"nct_id": "NCT0000DEMO3"},
            ),
            _mapping(note="申办方名称未匹配任何已核验企业别名"),
            run_id=run_ctgov, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(hours=6)),
        )

        # 4) A revision: v1 NEW 12 days ago, v2 UPDATED 4 hours ago.
        ledger.record_observation(
            _record(
                "sec_edgar", "DEMO-0001-26-000004", "sec_8k",
                "8-K｜Item 2.02 业绩披露 · Medtronic plc（初始版本）",
                url="https://www.sec.gov/Archives/edgar/data/0001613103/DEMO-0001-26-000004-index.htm",
                event_at=ago(days=14).date().isoformat(),
                event_precision=PRECISION_DATE,
                published_at=_iso(ago(days=12, hours=2)),
                published_precision=PRECISION_DATETIME,
                payload={"form": "8-K", "items": "2.02", "title": "Draft release"},
            ),
            _mapping("medtronic", "MAPPED", "patient_monitoring", "MAPPED", "sec_cik_exact"),
            run_id=run_sec, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(days=12)),
        )
        ledger.record_observation(
            _record(
                "sec_edgar", "DEMO-0001-26-000004", "sec_8k",
                "8-K｜Item 2.02,9.01 业绩与附件披露 · Medtronic plc（修订版本）",
                url="https://www.sec.gov/Archives/edgar/data/0001613103/DEMO-0001-26-000004-index.htm",
                event_at=ago(days=14).date().isoformat(),
                event_precision=PRECISION_DATE,
                published_at=_iso(ago(days=12, hours=2)),
                published_precision=PRECISION_DATETIME,
                payload={"form": "8-K", "items": "2.02,9.01", "title": "Revised release with exhibit"},
            ),
            _mapping("medtronic", "MAPPED", "patient_monitoring", "MAPPED", "sec_cik_exact"),
            run_id=run_sec, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(hours=4)),
        )

        # 5) Record the source no longer serves (REMOVED, 2 hours ago).
        removed_id = ledger.record_observation(
            _record(
                "ctgov", "NCT0000DEMO5", "trial",
                "呼吸机相关研究（来源已不再提供）",
                url="https://clinicaltrials.gov/study/NCT0000DEMO5",
                event_at=ago(days=3).date().isoformat(),
                event_precision=PRECISION_DATE,
                published_at=_iso(ago(hours=40)),
                published_precision=PRECISION_DATETIME,
                payload={"nct_id": "NCT0000DEMO5", "status": "Withdrawn"},
            ),
            _mapping("philips", "MAPPED", "respiratory", "MAPPED", "ctgov_keyword"),
            run_id=run_ctgov, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(hours=38)),
        ).observation_id
        ledger.mark_removed(
            removed_id, run_id=run_ctgov,
            note_zh="来源不再返回该记录（合成演示，不代表真实世界的事物消失）",
            seen_at=_iso(ago(hours=2)),
        )

        # 6) A failed re-check (FETCH_FAILED, 1 hour ago), pending-review entity.
        failed_id = ledger.record_observation(
            _record(
                "sec_edgar", "DEMO-0001-26-000006", "sec_6k",
                "6-K｜疑似 Medtronic 发行人披露（待人工复核）",
                published_at=_iso(ago(hours=30)),
                published_precision=PRECISION_DATETIME,
                payload={"form": "6-K", "issuer": "Medtronic"},
            ),
            _mapping(
                entity_id=None, entity_status="PENDING_REVIEW", method="sec_issuer_name",
                note="疑似 medtronic（置信度 0.60）；未经人工确认，不升格为企业事实",
            ),
            run_id=run_sec, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(hours=28)),
        ).observation_id
        ledger.mark_fetch_failed(
            failed_id, run_id=run_sec, message="HTTP 503 from data.sec.gov（合成演示）",
            seen_at=_iso(ago(hours=1)),
        )

        # 7) A backfilled historical record (origin fields must stay visible).
        ledger.record_observation(
            _record(
                "europepmc", "PMC9000001", "publication",
                "历史回填文献：患者监护中的可穿戴监测综述",
                event_at=ago(days=90).date().isoformat(),
                event_precision=PRECISION_DATE,
                published_at=_iso(ago(days=90)),
                published_precision=PRECISION_DATETIME,
                payload={"pmcid": "PMC9000001", "title": "Wearable monitoring review"},
            ),
            _mapping(
                entity_id=None, entity_status="PENDING_REVIEW",
                method="europepmc_affiliation_query",
                note="单位署名检索命中企业名称，待人工复核；不代表经核实的法人归属",
            ),
            run_id=run_sec, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(days=20)),
            origin=ORIGIN_BACKFILLED,
            backfill_reason="合成演示：历史材料被有意导入到过去，用于检查 origin 字段",
        )

        # 8) An older SEC filing (30d window only).
        ledger.record_observation(
            _record(
                "sec_edgar", "DEMO-0001-26-000008", "sec_10q",
                "10-Q｜季度报告 · Medtronic plc",
                event_at=ago(days=25).date().isoformat(),
                event_precision=PRECISION_DATE,
                published_at=_iso(ago(days=25, hours=1)),
                published_precision=PRECISION_DATETIME,
                payload={"form": "10-Q"},
            ),
            _mapping("medtronic", "MAPPED", None, "UNMAPPED", "sec_cik_exact"),
            run_id=run_sec, collector_version=COLLECTOR, mapping_version=MAPPING,
            seen_at=_iso(ago(days=25)),
        )

        ledger.finish_run(
            run_sec, status="PARTIAL",
            counters={"requests": 7, "pages": 3, "records_seen": 21, "records_new": 5,
                      "records_updated": 1, "records_unchanged": 14, "records_removed": 0,
                      "records_failed": 1},
            error_detail="1 个 scope 返回 HTTP 503（合成演示）",
        )
        ledger.note_source_success("sec_edgar", run_id=run_sec, status="DEGRADED",
                                   message="部分 scope 失败（合成演示）")
        ledger.set_entity_coverage(
            "sec_edgar",
            [
                {
                    "entity_id": "medtronic",
                    "name": "Medtronic",
                    "ticker": "MDT",
                    "status": "COVERED",
                    "identifier": "CIK 0001613103",
                    "evidence_zh": "SEC 官方 ticker 列表核验 CIK 0001613103，submissions 复核通过（合成演示）",
                },
                {
                    "entity_id": "draeger",
                    "name": "Dräger",
                    "ticker": "DRW3",
                    "status": "NOT_REGISTRANT",
                    "identifier": None,
                    "evidence_zh": "SEC 公司检索返回 0 条记录，该企业不是 SEC 发行人（合成演示）",
                },
                {
                    "entity_id": "mindray",
                    "name": "Mindray",
                    "ticker": "300760",
                    "status": "NOT_CURRENT_REGISTRANT",
                    "identifier": None,
                    "evidence_zh": "仅有 2016 年以前的 ADR 时代历史披露，当前无持续 SEC 披露（合成演示）",
                },
            ],
        )
        ledger.finish_run(
            run_ctgov, status="FAILED",
            counters={"requests": 3, "pages": 1, "records_seen": 2, "records_new": 2,
                      "records_failed": 1},
            error_detail="HTTP 503 while fetching study page 2（合成演示）",
        )
        ledger.note_source_failure(
            "ctgov", run_id=run_ctgov,
            message="HTTP 503 while fetching study page 2（合成演示）", degraded=False,
        )
        ledger.record_failure(
            "ctgov", kind="HTTP_ERROR",
            message="HTTP 503 while fetching study page 2（合成演示）",
            run_id=run_ctgov, http_status=503, retryable=True, attempt=2,
        )

        counts = ledger.counts()
        return {
            "observations": int(counts["observations"]),
            "versions": int(counts["versions"]),
            "changes": int(counts["changes"]),
            "sources": int(counts["sources"]),
            "runs": int(counts["runs"]),
        }
    finally:
        ledger.close()


def main() -> int:
    import os

    target = os.environ.get("MEDRADAR_OBSERVATORY_DB")
    if not target:
        print(
            "refusing to seed: MEDRADAR_OBSERVATORY_DB is not set.\n"
            "Point it at a demo file, e.g. "
            "$env:MEDRADAR_OBSERVATORY_DB='data\\\\observatory\\\\demo_observatory.sqlite'",
            file=sys.stderr,
        )
        return 2
    path = Path(target).expanduser()
    if "demo" not in path.name.lower():
        print(
            f"refusing to seed {path}: the filename must contain 'demo'. "
            "This script must never write the real observation ledger.",
            file=sys.stderr,
        )
        return 3
    real_ledger = (DATA_DIR / DEFAULT_LEDGER_RELATIVE).resolve()
    if path.resolve() == real_ledger:
        print(
            f"refusing to seed {path}: that is the collector's real ledger path.",
            file=sys.stderr,
        )
        return 4
    if path.exists():
        print(f"removing previous synthetic demo ledger: {path}")
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    print("=" * 78)
    print("SYNTHETIC DEMO DATA — 合成演示数据，不是真实观察记录")
    print("Only for local UI checks. The real ledger is never seeded with fakes.")
    print(f"target: {path}")
    print("=" * 78)
    counts = build_demo_ledger(path)
    print(
        "built demo ledger: "
        + ", ".join(f"{key}={value}" for key, value in counts.items())
    )
    print("restart the web server with the same MEDRADAR_OBSERVATORY_DB to see it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
