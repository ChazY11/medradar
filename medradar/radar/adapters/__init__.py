"""Adapter registry: the single place that knows which sources exist.

Adding a source is one module plus one entry here plus one entry in
``config/radar/sources.json``. Nothing in the ledger, the graph, the API or the UI changes.
"""

from __future__ import annotations

from typing import Any, Callable

from .crossref import CrossrefAdapter
from .draeger import DraegerAdapter
from .gehealthcare import GEHealthCareAdapter
from .openfda import OpenFDAAdapter
from .philips import PhilipsAdapter
from .pubmed import PubMedAdapter

#: source_id -> factory(taxonomy) -> adapter
FACTORIES: dict[str, Callable[[Any], Any]] = {
    "openfda_device": lambda taxonomy: OpenFDAAdapter(taxonomy),
    "pubmed": lambda taxonomy: PubMedAdapter(taxonomy),
    "crossref": lambda taxonomy: CrossrefAdapter(taxonomy),
    "philips_official": lambda taxonomy: PhilipsAdapter(taxonomy),
    "draeger_official": lambda taxonomy: DraegerAdapter(taxonomy),
    "gehealthcare_official": lambda taxonomy: GEHealthCareAdapter(taxonomy),
}

#: Order the scheduler and the CLI use by default: cheapest verified API first.
DEFAULT_ORDER: tuple[str, ...] = (
    "openfda_device",
    "pubmed",
    "crossref",
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
    "FACTORIES",
    "GEHealthCareAdapter",
    "OpenFDAAdapter",
    "PhilipsAdapter",
    "PubMedAdapter",
    "available_sources",
    "build_adapters",
]
