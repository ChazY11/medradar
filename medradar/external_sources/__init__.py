"""External evidence sources — the DATA-EXPANSION-001 integration layer.

This package is deliberately isolated from the MedRadar research database.  It
collects, normalises and stages *external* evidence (regulatory listings,
patents, papers, trials, procurement, hiring, trade) without touching
``data/medradar.sqlite`` or any frozen PHOENIX artefact.

The contract has five parts:

* :mod:`medradar.external_sources.schema`   — External Evidence Schema v1
* :mod:`medradar.external_sources.base`     — bounded HTTP client + probe runner
* :mod:`medradar.external_sources.store`    — isolated staging store (SQLite)
* :mod:`medradar.external_sources.identity` — company / product identity + confidence
* :mod:`medradar.external_sources.timeq`    — time semantics and quality levels

Nothing here performs network I/O at import time, and nothing here is imported
by the existing MedRadar runtime paths, so ``python -m medradar selftest`` stays
offline and unaffected.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
