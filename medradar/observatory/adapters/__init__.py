"""Source adapters for the Live Observatory.

Adapters are discovered lazily by source id so that a missing/optional adapter
never breaks the CLI, the web product or an offline test run.
"""

from __future__ import annotations

import importlib
from typing import Iterable

ADAPTER_SPECS: dict[str, str] = {
    "sec_edgar": "medradar.observatory.adapters.sec_edgar:SecEdgarAdapter",
    "ctgov": "medradar.observatory.adapters.ctgov:ClinicalTrialsAdapter",
    "europepmc": "medradar.observatory.adapters.europepmc:EuropePmcAdapter",
}

#: Source order used by `observatory sync` when no --source is given.
DEFAULT_SOURCE_ORDER = ("sec_edgar", "ctgov", "europepmc")


def known_sources() -> list[str]:
    return list(ADAPTER_SPECS)


def load_adapter(source_id: str, **kwargs) -> object:
    spec = ADAPTER_SPECS.get(source_id)
    if not spec:
        raise KeyError(f"unknown source {source_id!r}; known: {', '.join(ADAPTER_SPECS)}")
    module_name, _, class_name = spec.partition(":")
    module = importlib.import_module(module_name)
    factory = getattr(module, class_name)
    return factory(**kwargs)


def load_adapters(sources: Iterable[str] | None = None, **kwargs) -> dict[str, object]:
    selected = [str(name).strip() for name in (sources or DEFAULT_SOURCE_ORDER) if str(name).strip()]
    loaded: dict[str, object] = {}
    for source_id in selected:
        loaded[source_id] = load_adapter(source_id, **kwargs)
    return loaded
