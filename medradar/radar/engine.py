"""The intelligence pipeline: ingest -> deduplicate -> classify -> resolve -> link -> publish.

Each stage has a different job and a different failure mode, and the separation is what keeps
the system honest:

``ingest``
    Run the source adapters. A source failure is a source failure: it never stops the other
    sources and it never invents an empty result.

``deduplicate``
    Identity is ``(source, source_record_id)`` plus a content hash. The same DOI observed
    through PubMed and through Crossref is *not* a duplicate - it is two independent
    observations that the graph may join with ``OFFICIAL_IDENTIFIER_MATCH``. Deduplication
    never merges two sources into one row; it only prevents the same source row from being
    recorded twice.

``classify``
    The rule layer attaches organisation / product / technology candidates with their method
    and confirmation level. No model runs here.

``resolve``
    Organisation strings resolve through the committed alias table. Below the configured
    confidence the candidate is kept with its score but forms no confirmed edge.

``link``
    Assertions are written to the bitemporal graph, each with its evidence id and rule
    version. Only here does a candidate become an edge, and never above the level its
    evidence supports.

``publish``
    A record becomes visible in the feed and the graph. Nothing is deleted: a removal is a
    state, and a failed fetch is a state.

The pipeline is deliberately restartable at any point. ``advance`` can be run as often as you
like; it picks up whatever is not yet processed, and running it twice changes nothing.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .adapter import CollectContext, run_source
from .classify import RuleMapper
from .graph import GRAPH_VERSION, TechnologyGraph
from .http import PoliteFetcher
from .ledger import ObservationLedger
from .relevance import ADMISSION_VERSION, classify_observation, now_iso
from .records import (
    MAPPING_VERSION,
    PROC_AI_PENDING,
    PROC_LINKED,
    PROC_PUBLISHED,
    PROC_RAW,
    RUN_DEFERRED,
    MappingResult,
)
from .taxonomy import Taxonomy


@dataclass
class IngestReport:
    sources: list[dict[str, Any]] = field(default_factory=list)
    started_at: str = ""
    elapsed_seconds: float = 0.0

    @property
    def new_records(self) -> int:
        return sum(int(item.get("counters", {}).get("records_new") or 0) for item in self.sources)

    @property
    def updated_records(self) -> int:
        return sum(int(item.get("counters", {}).get("records_updated") or 0) for item in self.sources)

    @property
    def failed_sources(self) -> list[str]:
        return [item["source"] for item in self.sources
                if item.get("status") in ("FAILED", "PARTIAL", "INTERRUPTED")]

    @property
    def no_change(self) -> bool:
        return all(
            item.get("status") in ("OK", "DEFERRED")
            and not item.get("counters", {}).get("records_new")
            and not item.get("counters", {}).get("records_updated")
            for item in self.sources
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "elapsed_seconds": self.elapsed_seconds,
            "sources": self.sources,
            "new_records": self.new_records,
            "updated_records": self.updated_records,
            "failed_sources": self.failed_sources,
            "no_change": self.no_change,
            "statement": _ingest_statement(self),
        }


def _ingest_statement(report: IngestReport) -> str:
    if not report.sources:
        return "no source was run"
    if report.failed_sources and not (report.new_records or report.updated_records):
        return (
            "Every attempted source failed or was deferred. MedRadar did not observe a quiet "
            "period - it has no observation for this cycle."
        )
    if report.new_records or report.updated_records:
        return (
            f"{report.new_records} new and {report.updated_records} updated observation(s) were "
            "recorded from the sources that answered."
        )
    return (
        "Every source that answered reported no change. That is a real result: nothing new was "
        "published to the sources MedRadar monitors in this window."
    )


def ingest(
    adapters: Sequence[Any],
    ledger: ObservationLedger,
    taxonomy: Taxonomy,
    *,
    fetcher: PoliteFetcher | None = None,
    trigger: str = "manual",
    limit: int = 0,
    dry_run: bool = False,
    resume: bool = True,
    log: Any = print,
) -> IngestReport:
    """Run each adapter independently. One failure never stops another source."""
    started = time.time()
    report = IngestReport(started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    transport = fetcher or PoliteFetcher()
    for adapter in adapters:
        ctx = CollectContext(
            fetcher=transport,
            ledger=ledger,
            trigger=trigger,
            adapter_version=adapter.adapter_version,
            limit=limit,
            dry_run=dry_run,
            log=log,
        )
        try:
            result = run_source(adapter, ctx, resume=resume)
        except Exception as error:  # noqa: BLE001 - an adapter crash is contained here
            ledger.note_source_failure(
                adapter.source_id, run_id=None,
                message=f"adapter crashed: {type(error).__name__}: {error}",
                kind="ADAPTER_CRASH", retryable=True,
            )
            result = {
                "source": adapter.source_id,
                "status": "FAILED",
                "outcome": "FETCH_FAILED",
                "counters": {},
                "errors": [{"phase": "adapter", "kind": "ADAPTER_CRASH", "message": str(error)[:400]}],
            }
            try:
                log(f"[{adapter.source_id}] adapter crashed: {type(error).__name__}: {error}")
            except Exception:  # pragma: no cover
                pass
        report.sources.append(result)
    report.elapsed_seconds = round(time.time() - started, 2)
    return report


def advance(
    ledger: ObservationLedger,
    graph: TechnologyGraph,
    taxonomy: Taxonomy,
    *,
    limit: int = 400,
    enqueue_ai: bool = True,
    max_batches: int = 60,
    log: Any = print,
) -> dict[str, Any]:
    """Resolve, link and publish whatever is pending. Idempotent.

    Runs in batches so a large first load cannot produce one unbounded transaction, and keeps
    going until nothing is pending (or ``max_batches`` is reached, which is reported).
    """
    reclassified = 0
    published = 0
    queued = 0
    admitted = 0
    materialized = {"pending": 0, "materialized": 0, "assertions_created": 0,
                    "assertions_duplicate": 0, "errors": []}
    mapper = RuleMapper(taxonomy)
    batches = 0
    converged = False
    for _batch in range(max(1, int(max_batches))):
        batches += 1
        batch_work = 0

        pending_mapping = ledger.observations_with_stale_mapping(MAPPING_VERSION, limit=limit)
        for row in pending_mapping:
            observation_id = row["observation_id"]
            record = _rebuild_record(ledger, observation_id, row)
            if record is None:
                ledger.set_processing_state(observation_id, PROC_LINKED)
                continue
            mapping = mapper.map(record)
            ledger.record_observation(
                record, mapping,
                run_id=f"reclassify:{MAPPING_VERSION}",
                adapter_version="classifier",
                mapping_version=MAPPING_VERSION,
            )
            if str(row.get("processing_state") or "") in (PROC_RAW, "CLASSIFIED"):
                ledger.set_processing_state(observation_id, PROC_LINKED)
            # The rule layer changed, so the derived graph projection for this record is stale.
            ledger.invalidate_graph(observation_id)
            reclassified += 1
            batch_work += 1

        step = graph.materialize(ledger, limit=limit, log=log)
        materialized["pending"] += step["pending"]
        materialized["materialized"] += step["materialized"]
        materialized["assertions_created"] += step["assertions_created"]
        materialized["assertions_duplicate"] += step["assertions_duplicate"]
        materialized["errors"].extend(step["errors"])
        del materialized["errors"][20:]
        batch_work += step["materialized"]

        for row in ledger.raw(
            "SELECT observation_id FROM observation WHERE processing_state IN ('RAW','CLASSIFIED','LINKED')"
            " LIMIT ?",
            (int(limit),),
        ):
            ledger.set_processing_state(row["observation_id"], PROC_PUBLISHED)
            published += 1
            batch_work += 1

        if enqueue_ai:
            for row in ledger.raw(
                "SELECT observation_id, latest_version_id FROM observation"
                " WHERE processing_state='PUBLISHED' AND observation_status='ACTIVE' LIMIT ?",
                (int(limit),),
            ):
                ledger.enqueue_task(row["observation_id"], version_id=row["latest_version_id"],
                                    kind="ai_enrichment")
                ledger.set_processing_state(row["observation_id"], PROC_AI_PENDING)
                queued += 1
                batch_work += 1

        admitted += apply_admissions(ledger, limit=limit)
        batch_work += 1 if admitted else 0

        if batch_work == 0:
            converged = True
            break

    return {
        "reclassified": reclassified,
        "graph": materialized,
        "published": published,
        "ai_queued": queued,
        "admitted": admitted,
        "batches": batches,
        "converged": converged,
    }


def apply_admissions(ledger: ObservationLedger, *, limit: int = 500) -> int:
    """Qualify observations that have no decision for the current admission version.

    The decision is a separate append-only projection: the observation, its versions and its
    first-observed time are untouched, and a rejected record stays in the ledger with a reason.
    """
    pending = ledger.admission_pending(ADMISSION_VERSION, limit=limit)
    if not pending:
        return 0
    decided_at = now_iso()
    rows: list[dict[str, Any]] = []
    for row in pending:
        decision = classify_observation(
            {
                "record_type": row.get("record_type"),
                "title": row.get("title"),
                "payload": row.get("payload"),
            },
            mapped_topics=row.get("mapped_topics"),
            mapped_products=row.get("mapped_products"),
        )
        rows.append({
            "observation_id": row["observation_id"],
            "admission_version": ADMISSION_VERSION,
            "tier": decision.tier,
            "category": decision.category,
            "score": decision.score,
            "reasons": json.dumps(decision.reasons, ensure_ascii=False),
            "features": json.dumps(decision.features, ensure_ascii=False),
            "decided_at": decided_at,
        })
    return ledger.record_admissions(rows)


def _rebuild_record(ledger: ObservationLedger, observation_id: str,
                    row: Mapping[str, Any]) -> Any:
    """Reconstruct the RawRecord for a re-classification from its stored version payload."""
    versions = ledger.versions(observation_id)
    if not versions:
        return None
    head = ledger.observation_row(observation_id) or {}
    payload = versions[-1]["payload"] or {}
    from .records import RawRecord

    kind = str(head.get("record_type") or "")
    extra: dict[str, Any] = {"official_identifier": head.get("official_identifier")}
    source = str(head.get("source") or "")
    if source == "openfda_device":
        extra.update({
            "organization_hint": payload.get("applicant"),
            "organization_role": "regulatory_applicant",
            "product_codes": [payload.get("product_code")] if payload.get("product_code") else [],
            "product_hint": payload.get("device_name") or payload.get("trade_name"),
            "product_identifier": head.get("official_identifier"),
        })
    elif source in ("pubmed", "crossref"):
        affiliations = list(payload.get("affiliations") or [])
        extra.update({
            "organization_hint": _vendor(affiliations),
            "organization_role": "publication_affiliation",
            "affiliations": affiliations,
            "product_codes": [],
            "doi": payload.get("doi"),
        })
    elif source in ("philips_official", "draeger_official"):
        from .classify import extract_vendor_product

        extra.update({
            "organization_hint": payload.get("publisher"),
            "organization_role": "official_publisher",
            "publisher_hint": payload.get("publisher"),
            "product_hint": extract_vendor_product(head.get("title")),
            "product_identifier": head.get("official_identifier"),
            "product_codes": [],
        })
    return RawRecord(
        source=source,
        source_record_id=str(head.get("source_record_id") or ""),
        official_identifier=head.get("official_identifier"),
        record_type=kind,
        title=str(head.get("title") or ""),
        url=head.get("source_url"),
        event_at=head.get("event_at"),
        event_at_precision=str(head.get("event_at_precision") or "unknown"),
        published_at=head.get("published_at"),
        published_at_precision=str(head.get("published_at_precision") or "unknown"),
        source_updated_at=head.get("source_updated_at"),
        source_updated_at_precision=str(head.get("source_updated_at_precision") or "unknown"),
        payload=payload,
        text=" ".join(filter(None, [str(head.get("title") or ""), str(payload.get("abstract") or ""),
                                   str(payload.get("description") or "")])),
        extra=extra,
    )


def _vendor(affiliations: Iterable[str]) -> str | None:
    for affiliation in affiliations:
        lowered = str(affiliation).lower()
        if any(term in lowered for term in ("philips", "ge healthcare", "ge medical systems",
                                            "draeger", "dräger")):
            return str(affiliation)
    return None


def dedupe_report(ledger: ObservationLedger, *, limit: int = 50) -> dict[str, Any]:
    """Report cross-source identity matches without merging the underlying observations."""
    rows = ledger.raw(
        "SELECT official_identifier, COUNT(DISTINCT source) AS sources, COUNT(*) AS n"
        " FROM observation WHERE official_identifier IS NOT NULL"
        " GROUP BY official_identifier HAVING sources > 1 ORDER BY n DESC LIMIT ?",
        (int(limit),),
    )
    total = int(ledger.con.execute(
        "SELECT COUNT(*) FROM (SELECT official_identifier FROM observation"
        " WHERE official_identifier IS NOT NULL GROUP BY official_identifier"
        " HAVING COUNT(DISTINCT source) > 1)"
    ).fetchone()[0])
    return {
        "cross_source_identifiers": total,
        "sample": rows,
        "note": (
            "Two sources publishing the same official identifier are kept as two independent "
            "observations and joined by OFFICIAL_IDENTIFIER_MATCH in the graph. They are never "
            "merged into one row, because the second observation is the corroboration."
        ),
    }


def pipeline_report(ledger: ObservationLedger, graph: TechnologyGraph) -> dict[str, Any]:
    counts = ledger.counts()
    states = {
        row["processing_state"]: int(row["n"])
        for row in ledger.raw("SELECT processing_state, COUNT(*) AS n FROM observation GROUP BY 1")
    }
    queue = ledger.queue_summary()
    graph_summary = graph.summary()
    return {
        "counts": {
            "observations": counts.observations,
            "versions": counts.versions,
            "change_events": counts.change_events,
            "sources": counts.sources,
        },
        "processing_state": states,
        "queue": queue,
        "graph": {
            "nodes": graph_summary["nodes"],
            "edges": graph_summary["edges"],
            "edges_by_type": graph_summary["edges_by_type"],
            "confirmations": graph_summary["confirmations"],
            "graph_version": graph_summary["graph_version"],
            "taxonomy_version": graph_summary["taxonomy_version"],
        },
        "change_counts": ledger.change_counts(),
        "dedupe": dedupe_report(ledger, limit=5),
        "flow": ["ingest", "deduplicate", "classify", "resolve", "link", "publish"],
        "note": (
            "A record is deduplicated by (source, source_record_id) plus content hash. Cross-source "
            "identity is a graph relation, not a row merge."
        ),
    }
