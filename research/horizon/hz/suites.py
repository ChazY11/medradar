"""Probe-suite discovery.

Suites live in ``hz/suites_<name>.py`` and each exposes ``probes()`` returning a
``list[hz.probe.Probe]``. Discovery is by filename so that parallel workstreams
can add suites without editing a shared registry file (and therefore without
merge conflicts).
"""

from __future__ import annotations

import functools
import importlib
import glob
import os
from typing import Callable

from .probe import Probe


def _suite_names() -> list[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    names = []
    for path in glob.glob(os.path.join(here, "suites_*.py")):
        names.append(os.path.basename(path)[len("suites_"):-len(".py")])
    return sorted(names)


def _loader(name: str) -> Callable[[], list[Probe]]:
    def load() -> list[Probe]:
        mod = importlib.import_module(f"hz.suites_{name}")
        return mod.probes()

    return load


SUITES: dict[str, Callable[[], list[Probe]]] = {
    name: _loader(name) for name in _suite_names()
}
