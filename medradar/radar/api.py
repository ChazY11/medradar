"""Read-only HTTP surface for the Live Intelligence Radar and the Technology Graph.

Design rules:

* **read-only.** The serving process opens the ledger and the graph with ``mode=ro``. It cannot
  advance a cursor, write an observation or mutate an assertion, so a compromised or buggy web
  request can never corrupt the record.
* **honest 503.** If the radar database does not exist, the endpoints say ``available: false``
  with the reason. They never return an empty list that looks like "no intelligence found".
* **two clocks in the query string.** ``at`` with ``mode=public`` asks what was publicly true at
  that date (a reconstruction, labelled as such). ``at`` with ``mode=knowledge`` asks what
  MedRadar had recorded by then. Defaults are explicit, not implicit.
"""

from __future__ import annotations

import csv
import html
import io
import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, JSONResponse

from .graph import (
    EDGE_TYPES,
    NODE_COMPANY,
    NODE_PRODUCT,
    NODE_PUBLICATION,
    NODE_REGULATORY,
    NODE_TOPIC,
    TechnologyGraph,
    open_graph,
)
from .digest import digest as build_digest
from .human import REVIEW_STATES, HumanStore
from .health import change_stream, detection_latency, source_status, system_status
from .ledger import ObservationLedger
from .paths import radar_paths
from .records import CHANGE_STATES, PHASE_LABELS_EN, PHASES, effective_precision
from .relevance import ADMISSION_VERSION, HIGH_RELEVANCE, NEEDS_REVIEW, TIER_ORDER
from .taxonomy import Taxonomy, TaxonomyError, load_taxonomy

SCHEMA = "medradar.radar.api.v1"

#: The one page that exposes the device view. Deliberately hand-written and dependency-free:
#: the workbench UI is a built React bundle, and rebuilding it to show a text answer would cost
#: more than it returns. ``{{BODY}}`` is the single substitution point.
_DEVICE_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MedRadar · device</title>
<style>
 :root { color-scheme: light dark; }
 body { font: 14px/1.55 ui-sans-serif, system-ui, sans-serif; margin: 0; padding: 24px 20px 60px;
        max-width: 78ch; }
 h1 { font-size: 15px; font-weight: 600; margin: 0 0 4px; letter-spacing: .01em; }
 p.note { color: #6b7280; margin: 0 0 18px; font-size: 12.5px; }
 form { display: flex; gap: 8px; margin-bottom: 22px; }
 input[type=search] { flex: 1; padding: 8px 10px; border: 1px solid #9ca3af; border-radius: 6px;
                       font: inherit; background: transparent; color: inherit; }
 button { padding: 8px 14px; border: 1px solid #9ca3af; border-radius: 6px; background: #f3f4f6;
          font: inherit; cursor: pointer; color: #111; }
 pre { white-space: pre-wrap; word-break: break-word; background: #f9fafb; border: 1px solid #e5e7eb;
       border-radius: 8px; padding: 14px 16px; font: 12.5px/1.5 ui-monospace, monospace; margin: 0; }
 pre.err { background: #fef2f2; border-color: #fecaca; color: #991b1b; }
</style></head><body>
<h1>One device, its whole public life</h1>
<p class="note">K number · DI · DUNS · model · catalog number · brand · company.
Answers come from the local device register, the 510(k) document store and the failure index;
nothing is fetched while you wait.</p>
<form method="get" action="/api/radar/device/view">
  <input type="search" name="query" placeholder="e.g. X1209255, K210313, 830350380" autofocus>
  <button type="submit">Describe</button>
</form>
{{BODY}}
</body></html>
"""

#: Whether the ledger carries admission decisions for this version. Before the projection is
#: applied the feed keeps its historic behaviour instead of silently going empty.
def _admissions_present(ledger: ObservationLedger) -> bool:
    # One indexed EXISTS per request, not a cached flag: a projection applied by the operator
    # must take effect on the next request, not up to 30 seconds later.
    row = ledger.con.execute(
        "SELECT 1 FROM observation_admission WHERE admission_version=? LIMIT 1",
        (ADMISSION_VERSION,),
    ).fetchone()
    return row is not None

#: A tiny TTL cache for the two expensive graph views. They are read-only projections of a graph
#: that changes when the scheduler materialises a cycle, so serving a 60-second-old copy is
#: honest and keeps a phone from waiting on a 17k-edge snapshot for every navigation.
_VIEW_CACHE: dict[tuple, tuple[float, dict[str, Any]]] = {}
_VIEW_CACHE_TTL_SECONDS = 60.0
_VIEW_CACHE_MAX_ENTRIES = 16
#: One heavy view build at a time. Concurrent first requests for the same (or different) views
#: otherwise stampede the two CPU cores; the waiters then read the cache this lock populates.
_VIEW_BUILD_LOCK = threading.Lock()


def _cached_view(key: tuple, compute, *, ttl: float | None = None) -> dict[str, Any]:
    import time as _time

    window = _VIEW_CACHE_TTL_SECONDS if ttl is None else float(ttl)
    now = _time.monotonic()
    hit = _VIEW_CACHE.get(key)
    if hit is not None and now - hit[0] < window:
        return hit[1]
    with _VIEW_BUILD_LOCK:
        now = _time.monotonic()
        hit = _VIEW_CACHE.get(key)
        if hit is not None and now - hit[0] < window:
            return hit[1]
        value = compute()
        if len(_VIEW_CACHE) >= _VIEW_CACHE_MAX_ENTRIES:
            oldest = min(_VIEW_CACHE, key=lambda item: _VIEW_CACHE[item][0])
            _VIEW_CACHE.pop(oldest, None)
        _VIEW_CACHE[key] = (now, value)
        return value


def _csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


class RadarService:
    """Opens the radar stores read-only, one connection per request."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else None

    @property
    def paths(self):
        return radar_paths(self.data_dir)

    def available(self) -> bool:
        return self.paths.ledger.is_file()

    def taxonomy(self) -> Taxonomy:
        return load_taxonomy()

    @contextmanager
    def human(self) -> Iterator[HumanStore]:
        """The side store of human judgement.

        Unlike the ledger this one is opened read-write, because saving a filter or recording a
        review is a write. It is a separate file precisely so that no web request can ever touch
        the evidence.
        """
        path = self.paths.human
        path.parent.mkdir(parents=True, exist_ok=True)
        store = HumanStore(str(path))
        try:
            yield store
        finally:
            store.close()

    @contextmanager
    def ledger(self) -> Iterator[ObservationLedger]:
        path = self.paths.ledger
        if not path.is_file():
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "radar_not_configured",
                    "message": (
                        "The radar ledger does not exist yet. Run `python -m medradar radar run` "
                        "to perform a real source check; this endpoint does not invent data."
                    ),
                    "path": str(path),
                },
            )
        handle = ObservationLedger(path, create=False, read_only=True)
        try:
            yield handle
        finally:
            handle.close()

    @contextmanager
    def graph(self) -> Iterator[TechnologyGraph]:
        taxonomy = self.taxonomy()
        path = self.paths.graph
        if not path.is_file():
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "graph_not_built",
                    "message": (
                        "The technology graph has not been built yet. Run "
                        "`python -m medradar radar advance` after collecting observations."
                    ),
                    "path": str(path),
                },
            )
        graph = open_graph(path, taxonomy, read_only=True)
        try:
            yield graph
        finally:
            try:
                graph.store.close()
            except Exception:  # pragma: no cover
                pass


def _cut(mode: str, at: str | None) -> tuple[str | None, str | None, str]:
    """Translate ``(mode, at)`` into the TKG ``(known_at, valid_at)`` pair."""
    if not at:
        return None, None, "now"
    if mode == "knowledge":
        return at, None, "knowledge_time"
    return None, at, "public_time_reconstruction"


def build_router(service: RadarService | None = None) -> APIRouter:
    svc = service or RadarService()
    router = APIRouter(prefix="/api/radar", tags=["radar"])

    #: The module-level view cache is shared by every service in the process, so its keys carry this
    #: service's graph location. Without that, two services - a test fixture and the real store, or
    #: two test fixtures - answered each other's questions. Measured as four tests failing only
    #: under a particular random ordering, and passing whenever they ran alone.
    view_scope = ("store", str(getattr(svc.paths, "root", "")))

    def view(key: tuple, compute, *, ttl: float | None = None):
        return _cached_view(view_scope + tuple(key), compute, ttl=ttl)

    # ------------------------------------------------------------------ meta
    @router.get("/meta")
    def meta() -> dict[str, Any]:
        taxonomy = svc.taxonomy()
        paths = svc.paths
        public_alpha = os.environ.get("MEDRADAR_PUBLIC_ALPHA") == "1"
        return {
            "schema": SCHEMA,
            "available": paths.ledger.is_file(),
            "graph_available": paths.graph.is_file(),
            # Absolute server paths are an internal detail; a public deployment does not need
            # to tell an anonymous reader where its databases live.
            "paths": {"redacted": "public alpha"} if public_alpha else paths.describe(),
            "taxonomy": {
                "version": taxonomy.version,
                "fingerprint": taxonomy.fingerprint,
                "topics": len(taxonomy.topics),
                "organizations": len(taxonomy.organizations),
            },
            "sources": [
                {
                    "source_id": source.get("id"),
                    "display_name": source.get("display_name"),
                    "kind": source.get("kind"),
                    "enabled": bool(source.get("enabled")),
                    "access": (source.get("access") or {}).get("verification"),
                    "cadence_hours": source.get("cadence_hours"),
                    "licence": (source.get("licence") or {}).get("name"),
                }
                for source in taxonomy.sources()
            ],
            # What a reader can actually ask for, and whether the data behind each answer is
            # loaded. Advertising a capability whose table is empty would send a tester to a
            # dead end, so the flags are read from the stores rather than hard-coded.
            "capabilities": _capabilities(svc),
        }

    def _capabilities(service: RadarService) -> dict[str, Any]:
        capabilities: dict[str, Any] = {
            "device_view": {
                "query": "/api/radar/device?query=<K number|DI|DUNS|model|brand|company>",
                "page": "/api/radar/device/view?query=<same>",
                "sources": ["udi_register", "510k_documents", "maude_failure_index"],
            }
        }
        reference_path = service.paths.reference
        if not reference_path.is_file():
            capabilities["device_view"]["available"] = False
            capabilities["device_view"]["why"] = "device register absent"
            return capabilities
        capabilities["device_view"]["available"] = True
        try:
            from .failure_index import index_summary
            from .papers_index import summary as papers_summary
            from .patents_bulk import bulk_summary, tables_present as patents_present
            from .reference import UdiReference
            from .trials import tables_present as trials_present
            from .trials import trials_summary

            store = UdiReference(str(reference_path))
            try:
                capabilities["device_view"]["failures"] = index_summary(store)
                capabilities["device_view"]["trials"] = (
                    trials_summary(store) if trials_present(store) else None)
                capabilities["device_view"]["patents"] = (
                    bulk_summary(store) if patents_present(store) else None)
                capabilities["device_view"]["papers"] = papers_summary(store)
            finally:
                store.close()
        except Exception as error:  # noqa: BLE001 - meta must never fail a reader
            capabilities["device_view"]["diagnostics_error"] = f"{type(error).__name__}: {error}"
        return capabilities

    @router.get("/taxonomy")
    def taxonomy_catalog() -> dict[str, Any]:
        return svc.taxonomy().public_catalog()

    # ---------------------------------------------------------------- health
    @router.get("/health")
    def health() -> Any:
        if not svc.available():
            return JSONResponse(status_code=200, content={
                "schema": SCHEMA, "available": False, "state": "not_configured",
                "message": (
                    "No radar ledger exists on this deployment. Monitoring has not started, so "
                    "there is no source status, no latency and no backlog to report."
                ),
                "sources": [], "paths": svc.paths.describe(),
            })
        taxonomy = svc.taxonomy()

        def compute() -> dict[str, Any]:
            with svc.ledger() as ledger:
                graph = None
                if svc.paths.graph.is_file():
                    graph = open_graph(svc.paths.graph, taxonomy, read_only=True)
                try:
                    return system_status(ledger, graph, taxonomy, data_dir=str(svc.paths.root))
                finally:
                    if graph is not None:
                        graph.store.close()

        # The status view is the most expensive read on the feed page (source state, latency
        # distribution, graph summary, resources). It only changes when a cycle or a source check
        # finishes, so a short TTL keeps the first paint off a two-second query.
        payload = dict(view(("health",), compute, ttl=15.0))
        payload["schema"] = SCHEMA
        payload["available"] = True
        payload["cache_ttl_seconds"] = 15
        return payload

    @router.get("/sources")
    def sources() -> dict[str, Any]:
        taxonomy = svc.taxonomy()
        if not svc.available():
            return {"available": False, "sources": []}
        with svc.ledger() as ledger:
            rows = source_status(ledger, taxonomy)
        return {"available": True, "count": len(rows), "sources": rows}

    # ------------------------------------------------------------------ feed
    @router.get("/feed")
    def feed(
        limit: int = Query(30, ge=1, le=200),
        offset: int = Query(0, ge=0),
        source: str | None = None,
        organization: str | None = None,
        topic: str | None = None,
        change_state: str | None = None,
        confirmation: str | None = None,
        record_type: str | None = None,
        phase: str | None = None,
        published_from: str | None = None,
        published_to: str | None = None,
        observed_from: str | None = None,
        observed_to: str | None = None,
        q: str | None = None,
        order: str | None = Query(None, pattern="^(observed|published|event)$"),
        since: str | None = None,
        scope: str = Query("latest", pattern="^(latest|observed|archive|review)$"),
        admission_days: int = Query(30, ge=1, le=3650),
        tier: str | None = None,
    ) -> dict[str, Any]:
        states = _csv(change_state)
        invalid = [state for state in (states or []) if state not in (
            "NEW", "UPDATED", "UNCHANGED", "REMOVED_OR_UNAVAILABLE", "FETCH_FAILED")]
        if invalid:
            raise HTTPException(400, detail={"code": "bad_change_state", "values": invalid})
        phases = _csv(phase)
        bad_phases = [value for value in (phases or []) if value not in PHASES]
        if bad_phases:
            raise HTTPException(400, detail={"code": "bad_phase", "values": bad_phases,
                                            "allowed": list(PHASES)})
        default_tiers = {
            "latest": [HIGH_RELEVANCE],
            "observed": [HIGH_RELEVANCE, NEEDS_REVIEW],
            "archive": [HIGH_RELEVANCE],
            "review": [NEEDS_REVIEW],
        }[scope]
        tiers = _csv(tier) or default_tiers
        bad_tiers = [value for value in tiers if value not in TIER_ORDER]
        if bad_tiers:
            raise HTTPException(400, detail={"code": "bad_tier", "values": bad_tiers,
                                            "allowed": list(TIER_ORDER)})
        resolved_order = order or ("observed" if scope == "observed" else "published")
        with svc.ledger() as ledger:
            admission_live = _admissions_present(ledger)
            rows, total = ledger.feed(
                limit=limit, offset=offset, sources=_csv(source),
                organizations=_csv(organization), topics=_csv(topic),
                change_states=states, confirmations=_csv(confirmation),
                record_types=_csv(record_type), phases=phases,
                published_from=published_from, published_to=published_to,
                observed_from=observed_from, observed_to=observed_to,
                search=q, order=resolved_order,
                tiers=tiers if admission_live else None,
                admission_version=ADMISSION_VERSION if admission_live else None,
                scope=scope if admission_live else None,
                scope_days=admission_days,
            )
            views = ledger.admission_summary(ADMISSION_VERSION, days=admission_days) \
                if admission_live else None
            new_since = 0
            if since:
                new_since = int(ledger.con.execute(
                    "SELECT COUNT(*) FROM observation WHERE first_observed_at > ?", (since,)
                ).fetchone()[0])
        items = [_event(ledger_row, svc.taxonomy()) for ledger_row in rows]
        return {
            "schema": SCHEMA,
            "total": total,
            "count": len(items),
            "page": (offset // limit) + 1,
            "page_size": limit,
            "scope": scope,
            "admission_days": admission_days,
            "tiers": tiers,
            "views": views,
            "filters": {
                "source": _csv(source), "organization": _csv(organization), "topic": _csv(topic),
                "change_state": states, "confirmation": _csv(confirmation),
                "record_type": _csv(record_type), "phase": phases,
                "published_from": published_from, "published_to": published_to,
                "observed_from": observed_from, "observed_to": observed_to, "q": q,
                "order": resolved_order,
            },
            "new_since": new_since,
            "since": since,
            "items": items,
            "labels": {
                "change_states": CHANGE_STATES,
                "phases": {phase_id: PHASE_LABELS_EN[phase_id] for phase_id in PHASES},
            },
            "note": (
                "first_observed_at is when MedRadar saw the record; published_at/event_at are what "
                "the source states. 'latest' means published inside the window; 'observed' means "
                "first seen inside the window and may be an old document. Only qualified records "
                "appear here; each item carries its admission tier and reasons."
            ),
        }

    @router.get("/feed/admission-summary")
    def admission_summary(days: int = Query(30, ge=1, le=3650)) -> dict[str, Any]:
        with svc.ledger() as ledger:
            return {
                "schema": SCHEMA,
                "admission_version": ADMISSION_VERSION,
                "views": ledger.admission_summary(ADMISSION_VERSION, days=days),
                "tiers": list(TIER_ORDER),
            }

    @router.get("/brief")
    def brief(since: str | None = None, until: str | None = None,
              max_items: int = Query(15, ge=1, le=100)) -> dict[str, Any]:
        """The weekly brief: archive / candidate / deliverable intelligence for one window.

        Read-only and derived: it reads the ledger the feed already serves and applies the
        intelligence policy. It never writes a decision, so serving it cannot change the record.
        """
        import datetime as _dt

        from .intelligence import build_brief, evaluate

        today = _dt.date.today()
        start = since or (today - _dt.timedelta(days=7)).isoformat()
        stop = until or today.isoformat()
        try:
            _dt.date.fromisoformat(start)
            _dt.date.fromisoformat(stop)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="since/until must be YYYY-MM-DD") from error
        if start > stop:
            raise HTTPException(status_code=400, detail="since is after until")
        generated_at = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
        with svc.ledger() as ledger:
            payload = build_brief(ledger, start=start, end=stop, generated_at=generated_at,
                                  max_items=max_items)
        body = payload.as_dict()
        # The index is a per-observation map used by the offline metric script; a client needs the
        # brief itself, and shipping 20k keys would be a payload, not an answer.
        body.pop("index", None)
        body["schema"] = SCHEMA
        body["metrics"] = evaluate(payload)
        return body

    @router.get("/feed/facets")
    def feed_facets(limit: int = Query(40, ge=1, le=200)) -> dict[str, Any]:
        taxonomy = svc.taxonomy()
        with svc.ledger() as ledger:
            facets = ledger.feed_facets(limit=limit)
        for row in facets["organizations"]:
            organization = taxonomy.organization(row["organization_id"])
            row["display_name"] = organization.display_name if organization else row["organization_id"]
            row["label_zh"] = organization.label_zh if organization else None
        for row in facets["topics"]:
            topic = taxonomy.topic(row["topic_id"])
            row["label_en"] = topic.label_en if topic else row["topic_id"]
            row["label_zh"] = topic.label_zh if topic else None
        return {"schema": SCHEMA, **facets}

    @router.get("/intelligence/{observation_id}")
    def intelligence(observation_id: str) -> dict[str, Any]:
        taxonomy = svc.taxonomy()
        with svc.ledger() as ledger:
            row = ledger.observation_row(observation_id)
            if row is None:
                raise HTTPException(404, detail={"code": "observation_not_found",
                                                 "observation_id": observation_id})
            # The feed attaches the current decision to each row; this read has to do it
            # explicitly, otherwise the evidence drawer claims no decision exists.
            row["admission"] = ledger.current_admission(observation_id)
            versions = ledger.versions(observation_id)
            changes = ledger.changes_for(observation_id)
            mappings = ledger.mapping_history(observation_id)
            candidates = ledger.ai_candidates(observation_id=observation_id, limit=10)
        payload = _event(row, taxonomy)
        payload["versions"] = [
            {key: value for key, value in version.items() if key != "payload"} | {
                "payload_keys": sorted((version.get("payload") or {}).keys())
            }
            for version in versions
        ]
        payload["changes"] = changes
        payload["mapping_history"] = mappings
        payload["ai_candidates"] = candidates
        payload["evidence_references"] = [
            {
                "evidence_id": version["version_id"],
                "observation_id": observation_id,
                "content_hash": version["content_hash"],
                "captured_at": version["captured_at"],
                "change_state": version["change_state"],
                "source_url": row.get("source_url"),
            }
            for version in versions
        ]
        return {"schema": SCHEMA, **payload}

    # --------------------------------------------------------------- notices
    @router.get("/notices")
    def notices(since: str | None = None, limit: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
        with svc.ledger() as ledger:
            new_count = 0
            if since:
                new_count = int(ledger.con.execute(
                    "SELECT COUNT(*) FROM observation WHERE first_observed_at > ?", (since,)
                ).fetchone()[0])
            stream = change_stream(ledger, since=since, limit=limit)
        return {
            "schema": SCHEMA,
            "since": since,
            "new_count": new_count,
            "items": stream["items"],
            "note": (
                "Counted from first_observed_at, which is a real clock reading. Each item keeps "
                "its discovery phase so an initial load is not shown as today's news."
            ),
        }

    # ---------------------------------------------------------------- digest
    @router.get("/digest")
    def digest_endpoint(hours: int = Query(24, ge=1, le=168),
                        limit: int = Query(5, ge=1, le=10)) -> dict[str, Any]:
        """The one screen a reader can open without reading the whole feed.

        Everything here is derived from records already in the ledger: the admission decision,
        its dimensions and the source state. Nothing is model-generated, so every line points
        at a record that can be opened and checked. When nothing arrived the answer says so
        instead of padding the list.
        """
        with svc.ledger() as ledger:
            payload = build_digest(ledger, hours=hours, limit=limit)
        return {
            **payload,
            "note": (
                "Counts are records newly observed inside the window, not records published "
                "inside it. A stated public date more than a week ahead is reported as "
                "future-dated and sorted last: conference abstracts routinely carry a future "
                "issue date and are not today's news."
            ),
        }

    # ------------------------------------------------------------ watchlists
    def _feed_kwargs(filt: Mapping[str, Any], *, limit: int, offset: int = 0) -> dict[str, Any]:
        """Translate a saved filter into the same arguments the feed route uses."""
        scope = str(filt.get("scope") or "latest")
        if scope not in ("latest", "observed", "archive", "review"):
            scope = "latest"
        default_tiers = {
            "latest": [HIGH_RELEVANCE],
            "observed": [HIGH_RELEVANCE, NEEDS_REVIEW],
            "archive": [HIGH_RELEVANCE],
            "review": [NEEDS_REVIEW],
        }[scope]
        tiers = _csv(filt.get("tier")) or default_tiers
        order = filt.get("order") or ("observed" if scope == "observed" else "published")
        return {
            "limit": limit, "offset": offset,
            "sources": _csv(filt.get("source")),
            "organizations": _csv(filt.get("organization")),
            "topics": _csv(filt.get("topic")),
            "change_states": _csv(filt.get("change_state")),
            "confirmations": _csv(filt.get("confirmation")),
            "record_types": _csv(filt.get("record_type")),
            "phases": _csv(filt.get("phase")),
            "published_from": filt.get("published_from"),
            "published_to": filt.get("published_to"),
            "observed_from": filt.get("observed_from"),
            "observed_to": filt.get("observed_to"),
            "search": filt.get("q"),
            "order": order,
            "tiers": tiers,
            "admission_version": ADMISSION_VERSION,
            "scope": scope,
            "scope_days": 30,
        }

    @router.get("/watchlists")
    def list_watchlists(counts: bool = False) -> dict[str, Any]:
        with svc.human() as human:
            items = human.list_watchlists()
        if counts and items:
            with svc.ledger() as ledger:
                live = _admissions_present(ledger)
                for item in items:
                    kwargs = _feed_kwargs(item["filter"], limit=1)
                    try:
                        _, total = ledger.feed(**kwargs)
                        item["count"] = total
                    except Exception:
                        item["count"] = None
                if not live:
                    for item in items:
                        item["count"] = None
        return {"schema": SCHEMA, "count": len(items), "items": items}

    @router.post("/watchlists")
    def create_watchlist(payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        filt = payload.get("filter") or {}
        if not isinstance(filt, Mapping):
            raise HTTPException(400, detail={"code": "bad_filter"})
        try:
            with svc.human() as human:
                saved = human.save_watchlist(name, filt, actor=str(payload.get("actor") or "operator"))
        except ValueError as error:
            raise HTTPException(400, detail={"code": "bad_name", "message": str(error)}) from error
        return {"schema": SCHEMA, "watchlist": saved}

    @router.patch("/watchlists/{watchlist_id}")
    def update_watchlist(watchlist_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with svc.human() as human:
            current = human.get_watchlist(watchlist_id)
            if current is None:
                raise HTTPException(404, detail={"code": "watchlist_not_found"})
            name = str(payload.get("name") or current["name"])
            filt = payload.get("filter") if isinstance(payload.get("filter"), Mapping) else current["filter"]
            try:
                saved = human.save_watchlist(name, filt, watchlist_id=watchlist_id,
                                             actor=str(payload.get("actor") or "operator"))
            except ValueError as error:
                raise HTTPException(400, detail={"code": "bad_name", "message": str(error)}) from error
        return {"schema": SCHEMA, "watchlist": saved}

    @router.delete("/watchlists/{watchlist_id}")
    def delete_watchlist(watchlist_id: str) -> dict[str, Any]:
        with svc.human() as human:
            removed = human.delete_watchlist(watchlist_id)
        if not removed:
            raise HTTPException(404, detail={"code": "watchlist_not_found"})
        return {"schema": SCHEMA, "deleted": watchlist_id}

    # ---------------------------------------------------------------- review
    @router.get("/review/queue")
    def review_queue(status: str | None = None, limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
        if status and status not in REVIEW_STATES:
            raise HTTPException(400, detail={"code": "bad_status", "allowed": list(REVIEW_STATES)})
        with svc.human() as human:
            rows = human.review_queue(status=status, limit=limit)
            stats = human.stats()
        titles: dict[str, dict[str, Any]] = {}
        if rows and svc.available():
            with svc.ledger() as ledger:
                ids = [row["observation_id"] for row in rows]
                marks = ",".join("?" * len(ids))
                for record in ledger.raw(
                    f"SELECT observation_id, source, title, source_url, first_observed_at,"
                    f" published_at FROM observation WHERE observation_id IN ({marks})", ids):
                    titles[record["observation_id"]] = dict(record)
        items = [{**row, **(titles.get(row["observation_id"]) or {})} for row in rows]
        return {"schema": SCHEMA, "count": len(items), "items": items, "stats": stats,
                "states": list(REVIEW_STATES)}

    @router.get("/review/{observation_id}")
    def get_review(observation_id: str) -> dict[str, Any]:
        with svc.human() as human:
            decision = human.get_review(observation_id)
            history = human.review_history(observation_id)
        return {"schema": SCHEMA, "observation_id": observation_id,
                "review": decision, "history": history}

    @router.post("/review/{observation_id}")
    def set_review(observation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        status = payload.get("status")
        if status is not None and status not in REVIEW_STATES:
            raise HTTPException(400, detail={"code": "bad_status", "allowed": list(REVIEW_STATES)})
        assignee = payload.get("assignee")
        note = payload.get("note")
        try:
            with svc.human() as human:
                decision = human.set_review(
                    observation_id,
                    status=str(status) if status is not None else None,
                    assignee=str(assignee) if assignee is not None else None,
                    note=str(note) if note is not None else None,
                    actor=str(payload.get("actor") or "operator"),
                )
                history = human.review_history(observation_id)
        except ValueError as error:
            raise HTTPException(400, detail={"code": "bad_status", "message": str(error)}) from error
        return {"schema": SCHEMA, "observation_id": observation_id, "review": decision,
                "history": history}

    @router.get("/audit")
    def audit(limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
        with svc.human() as human:
            return {"schema": SCHEMA, "items": human.audit_log(limit=limit)}

    # -------------------------------------------------------------- companies
    def _org_index() -> dict[str, Any]:
        taxonomy = svc.taxonomy()
        return {org.id: org for org in getattr(taxonomy, "organizations", ())}

    @router.get("/companies")
    def companies(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
        """Every company the taxonomy tracks, with how much evidence the ledger holds for it."""
        if not svc.available():
            return {"schema": SCHEMA, "available": False, "items": []}
        organisations = _org_index()
        with svc.ledger() as ledger:
            rows = list(ledger.raw(
                "SELECT f.value AS organization_id, COUNT(*) AS observations,"
                " MAX(o.first_observed_at) AS newest,"
                " SUM(CASE WHEN o.source = 'openfda_recall' THEN 1 ELSE 0 END) AS recalls"
                " FROM observation_facet f JOIN observation o ON o.observation_id = f.observation_id"
                " WHERE f.kind = 'organization' GROUP BY f.value ORDER BY 3 DESC"))
        items = []
        for row in rows:
            org = organisations.get(row["organization_id"])
            items.append({
                "organization_id": row["organization_id"],
                "display_name": getattr(org, "display_name", None) or row["organization_id"],
                "canonical_name": getattr(org, "canonical_name", None),
                "label_zh": getattr(org, "label_zh", None),
                "country": getattr(org, "country", None),
                "observations": row["observations"],
                "recalls": row["recalls"],
                "newest_observation_at": row["newest"],
            })
        items.sort(key=lambda item: (-int(item["observations"] or 0), str(item["display_name"])))
        return {"schema": SCHEMA, "available": True, "count": len(items), "items": items[:limit]}

    @router.get("/company/{organization_id}")
    def company(organization_id: str, limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
        """One company: what the product holds about it, in the reader's own unit."""
        if not svc.available():
            return {"schema": SCHEMA, "available": False}
        org = _org_index().get(organization_id)
        with svc.ledger() as ledger:
            total = int(ledger.raw(
                "SELECT COUNT(*) AS n FROM observation_facet WHERE kind = 'organization' AND value = ?",
                (organization_id,))[0]["n"])
            if total == 0 and org is None:
                raise HTTPException(404, detail={"code": "company_not_found"})
            recent = [dict(row) for row in ledger.raw(
                "SELECT o.observation_id, o.source, o.record_type, o.title, o.source_url, o.published_at,"
                " o.event_at, o.first_observed_at, o.official_identifier, o.observation_origin,"
                " a.decision, a.tier, a.score, a.dimensions"
                " FROM observation_facet f JOIN observation o ON o.observation_id = f.observation_id"
                " LEFT JOIN admission_current a ON a.observation_id = o.observation_id"
                " WHERE f.kind = 'organization' AND f.value = ?"
                " ORDER BY o.first_observed_at DESC LIMIT ?", (organization_id, limit))]
            recalls = [dict(row) for row in ledger.raw(
                "SELECT o.observation_id, o.title, o.source_url, o.published_at, o.event_at,"
                " o.official_identifier, o.first_observed_at"
                " FROM observation_facet f JOIN observation o ON o.observation_id = f.observation_id"
                " WHERE f.kind = 'organization' AND f.value = ? AND o.source = 'openfda_recall'"
                " ORDER BY o.published_at DESC LIMIT ?", (organization_id, limit))]
            counts = {row["source"]: row["n"] for row in ledger.raw(
                "SELECT o.source, COUNT(*) AS n FROM observation_facet f"
                " JOIN observation o ON o.observation_id = f.observation_id"
                " WHERE f.kind = 'organization' AND f.value = ? GROUP BY o.source", (organization_id,))}
            topics = [dict(row) for row in ledger.raw(
                "SELECT f.value AS topic_id, COUNT(*) AS n FROM observation_facet f"
                " WHERE f.kind = 'topic' AND f.observation_id IN ("
                "   SELECT observation_id FROM observation_facet WHERE kind = 'organization' AND value = ?)"
                " GROUP BY f.value ORDER BY 2 DESC LIMIT 12", (organization_id,))]
            products = [dict(row) for row in ledger.raw(
                "SELECT f.value AS product_key, COUNT(*) AS n FROM observation_facet f"
                " WHERE f.kind = 'product' AND f.observation_id IN ("
                "   SELECT observation_id FROM observation_facet WHERE kind = 'organization' AND value = ?)"
                " GROUP BY f.value ORDER BY 2 DESC LIMIT 12", (organization_id,))]
        return {
            "schema": SCHEMA,
            "available": True,
            "company": {
                "organization_id": organization_id,
                "display_name": getattr(org, "display_name", None) or organization_id,
                "canonical_name": getattr(org, "canonical_name", None),
                "label_zh": getattr(org, "label_zh", None),
                "country": getattr(org, "country", None),
                "notes": getattr(org, "notes", None),
                "known_in_taxonomy": org is not None,
            },
            "totals": {"observations": total, "by_source": counts, "recalls": len(recalls)},
            "recent": recent,
            "recalls": recalls,
            "topics": topics,
            "products": products,
        }

    # ---------------------------------------------------------------- export
    @router.get("/export")
    def export(
        format: str = Query("csv", pattern="^(csv|json)$"),
        limit: int = Query(1000, ge=1, le=5000),
        scope: str = Query("latest", pattern="^(latest|observed|archive|review)$"),
        source: str | None = None,
        organization: str | None = None,
        topic: str | None = None,
        q: str | None = None,
    ) -> Response:
        """Export what the reader is looking at, so a judgement can leave the page."""
        if not svc.available():
            raise HTTPException(503, detail={"code": "radar_not_configured"})
        kwargs = _feed_kwargs(
            {"scope": scope, "source": source, "organization": organization, "topic": topic, "q": q},
            limit=limit,
        )
        with svc.ledger() as ledger:
            rows, total = ledger.feed(**kwargs)
            reviews: dict[str, Any] = {}
            if rows:
                ids = [row["observation_id"] for row in rows]
                with svc.human() as human:
                    reviews = human.reviews(ids)
        taxonomy = svc.taxonomy()
        records = []
        for row in rows:
            event = _event(row, taxonomy)
            decision = event.get("admission") or {}
            decision_review = reviews.get(row["observation_id"]) or {}
            records.append({
                "observation_id": event.get("observation_id"),
                "source": event.get("source"),
                "record_type": event.get("record_type"),
                "title": event.get("title"),
                "published_at": event.get("published_at"),
                "event_at": event.get("event_at"),
                "first_observed_at": event.get("first_observed_at"),
                "official_identifier": event.get("official_identifier"),
                "discovery_phase": event.get("discovery_phase"),
                "decision": decision.get("decision"),
                "tier": decision.get("tier"),
                "score": decision.get("score"),
                "review_status": decision_review.get("status"),
                "review_note": decision_review.get("note"),
                "source_url": event.get("source_url"),
            })
        if format == "json":
            body = json.dumps({"schema": SCHEMA, "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                               "total": total, "count": len(records), "scope": scope,
                               "records": records}, ensure_ascii=False)
            return Response(content=body, media_type="application/json",
                            headers={"Content-Disposition": "attachment; filename=medradar-export.json"})
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(records[0].keys()) if records else [
            "observation_id", "source", "record_type", "title", "published_at", "event_at",
            "first_observed_at", "official_identifier", "discovery_phase", "decision", "tier",
            "score", "review_status", "review_note", "source_url"])
        writer.writeheader()
        for record in records:
            writer.writerow(record)
        return Response(content=buffer.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=medradar-export.csv"})
    # ----------------------------------------------------------------- graph
    @router.get("/technology-map")
    def technology_map(
        companies: str | None = None,
        topics: str | None = None,
        topic_id: str | None = None,
        mode: str = Query("public", pattern="^(public|knowledge)$"),
        at: str | None = None,
        max_products: int = Query(25, ge=1, le=200),
        max_evidence: int = Query(10, ge=1, le=100),
        product_offset: int = Query(0, ge=0),
        evidence_offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        known_at, valid_at, label = _cut(mode, at)
        company_key = tuple(sorted(_csv(companies) or []))
        topic_key = tuple(sorted(_csv(topics) or []))
        branch_topic_key = tuple(sorted(_csv(topic_id) or []))

        def compute() -> dict[str, Any]:
            with svc.graph() as graph:
                return graph.technology_map(
                    companies=_csv(companies), topics=_csv(topic_id) or None,
                    known_at=known_at, valid_at=valid_at, max_products=max_products,
                    max_evidence=max_evidence, product_offset=product_offset,
                    evidence_offset=evidence_offset)

        # Shallow copy: the handler annotates the payload per request, and a cached dict must
        # never carry one caller's annotations into another caller's response.
        payload = dict(view(
            ("technology-map", company_key, topic_key, branch_topic_key, known_at, valid_at,
             max_products, max_evidence, product_offset, evidence_offset), compute))
        payload["requested_mode"] = label
        payload["page_limits"] = {
            "max_products": max_products, "max_evidence": max_evidence,
            "product_offset": product_offset, "evidence_offset": evidence_offset,
        }
        payload["cache_ttl_seconds"] = _VIEW_CACHE_TTL_SECONDS
        payload["available_topics"] = [topic.public() for topic in svc.taxonomy().topics]
        if topics:
            wanted = set(_csv(topics) or [])
            payload["topics"] = [topic for topic in payload["topics"] if topic["topic_id"] in wanted]
            payload["filtered_topics"] = sorted(wanted)
        payload["schema"] = SCHEMA
        return payload

    @router.get("/compare")
    def compare(
        companies: str | None = None,
        topics: str | None = None,
        mode: str = Query("public", pattern="^(public|knowledge)$"),
        at: str | None = None,
    ) -> dict[str, Any]:
        known_at, valid_at, label = _cut(mode, at)
        company_key = tuple(sorted(_csv(companies) or []))
        topic_key = tuple(sorted(_csv(topics) or []))

        def compute() -> dict[str, Any]:
            with svc.graph() as graph:
                return graph.company_compare(companies=_csv(companies), topics=_csv(topics),
                                             known_at=known_at, valid_at=valid_at)

        payload = dict(view(("compare", company_key, topic_key, known_at, valid_at),
                                    compute))
        payload["requested_mode"] = label
        payload["organizations"] = [org.public() for org in svc.taxonomy().organizations]
        payload["schema"] = SCHEMA
        payload["cache_ttl_seconds"] = _VIEW_CACHE_TTL_SECONDS
        return payload

    @router.get("/graph/summary")
    def graph_summary() -> dict[str, Any]:
        with svc.graph() as graph:
            summary = graph.summary()
        summary["schema"] = SCHEMA
        summary["edge_types"] = list(EDGE_TYPES)
        return summary

    @router.get("/graph/changes")
    def graph_changes(earlier: str, later: str | None = None,
                      limit: int = Query(300, ge=1, le=2000),
                      offset: int = Query(0, ge=0)) -> dict[str, Any]:
        if not earlier:
            raise HTTPException(400, detail={"code": "earlier_required"})

        def compute() -> dict[str, Any]:
            with svc.graph() as graph:
                return graph.changes_between(earlier=earlier, later=later)

        # The diff can answer with every assertion in the graph. Serving the whole list is a
        # multi-megabyte response and a CPU-heavy serialisation for a screen that shows counts
        # and a short list; the totals below keep the truncation explicit.
        payload = dict(view(("changes", earlier, later), compute, ttl=30.0))
        totals = {key: len(payload.get(key) or []) for key in ("added", "removed", "changed")}
        for key in ("added", "removed", "changed"):
            payload[key] = (payload.get(key) or [])[offset:offset + limit]
        payload["counts"] = {**(payload.get("counts") or {}), **totals}
        payload["listed"] = {key: len(payload[key]) for key in ("added", "removed", "changed")}
        payload["truncated"] = any(totals[key] > offset + limit for key in totals)
        payload["list_limit"] = limit
        payload["list_offset"] = offset
        payload["has_more"] = any(totals[key] > offset + limit for key in totals)
        payload["schema"] = SCHEMA
        return payload

    @router.get("/graph/node")
    def graph_node(
        node_type: str = Query(..., pattern="^(company|product|technology_topic|regulatory_record|publication|document|organization)$"),
        node_id: str = Query(...),
        mode: str = Query("public", pattern="^(public|knowledge)$"),
        at: str | None = None,
    ) -> dict[str, Any]:
        known_at, valid_at, label = _cut(mode, at)
        with svc.graph() as graph:
            payload = graph.node_detail(node_type=node_type, node_id=node_id,
                                        known_at=known_at, valid_at=valid_at)
        if payload.get("node") is None and not payload["incoming"] and not payload["outgoing"]:
            raise HTTPException(404, detail={"code": "node_not_found", "node_type": node_type,
                                            "node_id": node_id})
        payload["requested_mode"] = label
        payload["schema"] = SCHEMA
        return payload

    @router.get("/topics/{topic_id}")
    def topic_detail(
        topic_id: str,
        organization: str | None = None,
        mode: str = Query("public", pattern="^(public|knowledge)$"),
        at: str | None = None,
    ) -> dict[str, Any]:
        known_at, valid_at, label = _cut(mode, at)
        with svc.graph() as graph:
            payload = graph.topic_evidence(topic_id, organization_id=organization,
                                           known_at=known_at, valid_at=valid_at)
        payload["requested_mode"] = label
        payload["schema"] = SCHEMA
        return payload

    # -------------------------------------------------------------- pipeline
    @router.get("/pipeline")
    def pipeline() -> dict[str, Any]:
        if not svc.available():
            return {"available": False, "message": "the radar ledger does not exist yet"}
        taxonomy = svc.taxonomy()
        with svc.ledger() as ledger:
            graph = open_graph(svc.paths.graph, taxonomy, read_only=True) if svc.paths.graph.is_file() else None
            try:
                from .engine import pipeline_report

                if graph is None:
                    return {"available": False, "message": "the technology graph has not been built"}
                payload = pipeline_report(ledger, graph)
            finally:
                if graph is not None:
                    graph.store.close()
            payload["latency"] = detection_latency(ledger)
            payload["recent_runs"] = ledger.recent_runs(10)
            payload["recent_failures"] = ledger.failures(limit=10)
        payload["schema"] = SCHEMA
        payload["available"] = True
        return payload

    # --------------------------------------------------- one device, whole life
    def _device_payload(query: str, limit: int, failures: bool,
                        section_chars: int) -> dict[str, Any]:
        from .device_view import build as build_view
        from .device_view import render as render_view
        from .reference import UdiReference

        reference_path = svc.paths.reference
        if not reference_path.is_file():
            raise HTTPException(status_code=503, detail=(
                "the device register does not exist on this deployment, so there is no device "
                "to describe. This is an absent store, not an empty result."
            ))
        corpus = svc.paths.corpus
        store = UdiReference(str(reference_path))
        try:
            timeline = build_view(store, query, corpus_root=corpus if corpus.is_dir() else None,
                                  limit=limit, failures=failures)
        finally:
            store.close()
        payload = timeline.to_dict()
        payload["schema"] = "medradar.radar.device.v1"
        payload["render"] = render_view(timeline, section_chars=section_chars)
        return payload

    @router.get("/device")
    def device(query: str = Query(..., min_length=1, max_length=120),
               limit: int = Query(25, ge=1, le=100),
               failures: bool = True,
               sections: int = Query(1200, ge=0, le=8000)) -> dict[str, Any]:
        """Describe one device: its clearances, what the filings say, and how it has failed.

        ``query`` accepts a K number, a DI, a DUNS, a model or catalog number, a brand, or a
        company name. Identifier matches win over name matches; a name that resolves to hundreds
        of devices is capped and the cap is visible in ``devices``.
        """
        return _device_payload(query, limit, failures, sections)

    @router.get("/device/view", response_class=HTMLResponse)
    def device_page(query: str | None = Query(None, max_length=120),
                    limit: int = Query(10, ge=1, le=50)) -> Any:
        """A deliberately plain page over the same data.

        The workbench UI is a built React bundle; a device view does not justify a rebuild, and
        an endpoint nobody can open is not a feature. This renders the text view directly so the
        capability is reachable today.
        """
        if not query:
            return HTMLResponse(_DEVICE_PAGE.replace("{{BODY}}", ""))
        try:
            payload = _device_payload(query, limit, True, 1200)
        except HTTPException as error:
            body = f'<pre class="err">{html.escape(str(error.detail))}</pre>'
            return HTMLResponse(_DEVICE_PAGE.replace("{{BODY}}", body),
                                status_code=error.status_code)
        body = f'<pre>{html.escape(payload["render"])}</pre>'
        return HTMLResponse(_DEVICE_PAGE.replace("{{BODY}}", body))

    return router


def _event(row: dict[str, Any], taxonomy: Taxonomy) -> dict[str, Any]:
    """The standard intelligence event shape (RADAR-001 section 6)."""
    facets = row.get("facets") or {}
    organizations = []
    for candidate in facets.get("organization", []):
        organization = taxonomy.organization(candidate["value"])
        organizations.append({
            "organization_id": candidate["value"],
            "display_name": organization.display_name if organization else candidate["value"],
            "label_zh": organization.label_zh if organization else None,
            "confirmation": candidate["confirmation"],
            "method": candidate["method"],
            "confidence": candidate["confidence"],
        })
    topics = []
    for candidate in facets.get("topic", []):
        topic = taxonomy.topic(candidate["value"])
        topics.append({
            "topic_id": candidate["value"],
            "label_en": topic.label_en if topic else candidate["value"],
            "label_zh": topic.label_zh if topic else None,
            "family": topic.family if topic else None,
            "confirmation": candidate["confirmation"],
            "method": candidate["method"],
        })
    products = []
    for candidate in facets.get("product", []):
        products.append({
            "product_key": candidate["value"],
            "confirmation": candidate["confirmation"],
            "method": candidate["method"],
        })
    return {
        "observation_id": row["observation_id"],
        "source": row["source"],
        "official_identifier": row.get("official_identifier"),
        "title": row.get("title"),
        "source_url": row.get("source_url"),
        "record_type": row.get("record_type"),
        "event_date": row.get("event_at"),
        "event_date_precision": effective_precision(
            row.get("event_at"), row.get("event_at_precision")),
        "source_published_at": row.get("published_at"),
        "source_published_at_precision": effective_precision(
            row.get("published_at"), row.get("published_at_precision")),
        "first_observed_at": row.get("first_observed_at"),
        "admission": row.get("admission"),
        "last_checked_at": row.get("last_checked_at"),
        "source_updated_at": row.get("source_updated_at"),
        "content_hash": row.get("content_hash"),
        "version": int(row.get("version_count") or 1),
        "change_state": row.get("current_change_state"),
        "observation_status": row.get("observation_status"),
        "discovery_phase": row.get("discovery_phase"),
        "processing_state": row.get("processing_state"),
        "organization_candidates": organizations,
        "product_candidates": products,
        "technology_topics": topics,
        "journal_url": row.get("source_url"),
        "site_domain": row.get("site_domain"),
        "latest_version_changed_fields": row.get("latest_version_changed_fields") or [],
        "evidence_references": [{
            "evidence_id": row.get("latest_version_id"),
            "observation_id": row["observation_id"],
            "content_hash": row.get("content_hash"),
            "source": row["source"],
            "url": row.get("source_url"),
        }],
    }
