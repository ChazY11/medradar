"""RADAR-001: the MedRadar Live Intelligence Engine and Company Technology Graph.

The package is layered so each layer can be tested and replaced on its own:

``records``    the vocabulary and time semantics shared by every layer;
``taxonomy``   the versioned ICU-monitoring technology and organisation registry (config);
``ledger``     the append-only observation ledger plus cursor/health/work state;
``http``       the polite, budgeted, retrying transport;
``adapter``    the source-adapter contract and the incremental run engine;
``adapters``   one module per real source (openFDA, PubMed, Crossref, Philips, Dräger, GE);
``classify``   the deterministic rule layer and the model-claim vetting gate;
``graph``      the company technology graph over the bitemporal TKG store;
``engine``     ingest -> deduplicate -> classify -> resolve -> link -> publish;
``ai``         the local small-model worker, its backlog and its measured evaluation;
``health``     source status, latency and backlog projections;
``scheduler``  per-source cadence, single-writer lease and safe deferral;
``api``        the read-only HTTP surface the workbench consumes;
``cli``        the operator commands under ``python -m medradar radar ...``.
"""

from __future__ import annotations

from .paths import RadarPaths, radar_paths, resolve_radar_dir
from .records import (
    CHANGE_FETCH_FAILED,
    CHANGE_NEW,
    CHANGE_REMOVED,
    CHANGE_UNCHANGED,
    CHANGE_UPDATED,
    COLLECTOR_VERSION,
    CONFIRMED,
    CANDIDATE,
    MAPPING_VERSION,
    PHASE_BACKFILL,
    PHASE_INCREMENTAL,
    PHASE_INITIAL,
    RECORD_TYPES,
    TOPIC_RELATED,
    UNKNOWN_RELATION,
    MappingResult,
    Page,
    RawRecord,
    RecordOutcome,
    Scope,
)

__all__ = [
    "CHANGE_FETCH_FAILED",
    "CHANGE_NEW",
    "CHANGE_REMOVED",
    "CHANGE_UNCHANGED",
    "CHANGE_UPDATED",
    "COLLECTOR_VERSION",
    "CANDIDATE",
    "CONFIRMED",
    "MAPPING_VERSION",
    "PHASE_BACKFILL",
    "PHASE_INCREMENTAL",
    "PHASE_INITIAL",
    "RECORD_TYPES",
    "RadarPaths",
    "MappingResult",
    "Page",
    "RawRecord",
    "RecordOutcome",
    "Scope",
    "TOPIC_RELATED",
    "UNKNOWN_RELATION",
    "radar_paths",
    "resolve_radar_dir",
]

__version__ = "1.0.0"
