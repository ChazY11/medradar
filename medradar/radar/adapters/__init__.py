"""Adapter registry: the single place that knows which sources exist.

Adding a source is one module plus one entry here plus one entry in
``config/radar/sources.json``. Nothing in the ledger, the graph, the API or the UI changes.
"""

from __future__ import annotations

from typing import Any, Callable

from .crossref import CrossrefAdapter
from .draeger import DraegerAdapter
from .europepmc import EuropePmcAdapter
from .gehealthcare import GEHealthCareAdapter
from .maude import MaudeAdapter
from .nih_reporter import NihReporterAdapter
from .openfda import OpenFDAAdapter
from .openfda_recall import OpenFDARecallAdapter
from .philips import PhilipsAdapter
from .pubmed import PubMedAdapter

#: source_id -> factory(taxonomy) -> adapter
FACTORIES: dict[str, Callable[[Any], Any]] = {
    "openfda_device": lambda taxonomy: OpenFDAAdapter(taxonomy),
    "openfda_recall": lambda taxonomy: OpenFDARecallAdapter(taxonomy),
    "openfda_maude": lambda taxonomy: MaudeAdapter(taxonomy),
    "pubmed": lambda taxonomy: PubMedAdapter(taxonomy),
    "europepmc": lambda taxonomy: EuropePmcAdapter(taxonomy),
    "crossref": lambda taxonomy: CrossrefAdapter(taxonomy),
    "nih_reporter": lambda taxonomy: NihReporterAdapter(taxonomy),
    "philips_official": lambda taxonomy: PhilipsAdapter(taxonomy),
    "draeger_official": lambda taxonomy: DraegerAdapter(taxonomy),
    "gehealthcare_official": lambda taxonomy: GEHealthCareAdapter(taxonomy),
}

#: Order the scheduler and the CLI use by default: cheapest verified API first.
DEFAULT_ORDER: tuple[str, ...] = (
    "openfda_device",
    # The safety channel is cheap (three API pages per code) and is the highest-value source;
    # it runs before the literature sources so a slow PubMed cycle cannot delay it.
    "openfda_recall",
    # MAUDE is the only public corpus of free-text failure narratives, and the only lane that
    # can attribute a failure to a device model. Same host and budget as the recall channel.
    "openfda_maude",
    "pubmed",
    # Europe PMC is the first source here that publishes a real per-record public instant, so
    # it runs before Crossref: a record from it can support a point-in-time statement.
    "europepmc",
    "crossref",
    # Federal funding is the earliest public signal in the set: an award precedes a clearance by
    # years, and its organisation DUNS joins straight into the device register.
    "nih_reporter",
    "philips_official",
    "draeger_official",
    "gehealthcare_official",
)


def available_sources() -> tuple[str, ...]:
    return tuple(FACTORIES)


def build_adapters(taxonomy, source_ids: list[str] | None = None) -> list[Any]:
    """Instantiate adapters. An unknown id is an error, never silently skipped."""
    wanted = source_ids or list(DEFAULT_ORDER)
    adapters: list[Any] = []
    for source_id in wanted:
        factory = FACTORIES.get(source_id)
        if factory is None:
            raise KeyError(
                f"unknown radar source {source_id!r}; known sources: {', '.join(available_sources())}"
            )
        adapters.append(factory(taxonomy))
    return adapters


__all__ = [
    "CrossrefAdapter",
    "DEFAULT_ORDER",
    "DraegerAdapter",
    "EuropePmcAdapter",
    "FACTORIES",
    "GEHealthCareAdapter",
    "MaudeAdapter",
    "NihReporterAdapter",
    "OpenFDAAdapter",
    "OpenFDARecallAdapter",
    "PhilipsAdapter",
    "PubMedAdapter",
    "available_sources",
    "build_adapters",
]
