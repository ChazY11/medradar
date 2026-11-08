"""Regulatory (medical-device market-access) source connectors.

This sub-package holds one module per **verified** source in the
``regulatory`` scope of DATA-EXPANSION-001, plus the live probe definitions
used to decide whether a source is verified at all.

Every connector here follows the same contract:

* network access only through :class:`medradar.external_sources.base.HttpClient`;
* bounded pagination (``limit`` / ``max_pages``), never an unbounded loop;
* deterministic ``evidence_id`` via :func:`schema.make_evidence`, so re-running
  a collector is idempotent;
* the four clocks of :mod:`timeq` kept apart — in particular a source's
  "last updated" stamp is never used as the first-publication date;
* company links only through :class:`identity.CompanyIndex`, and a semantic
  guess is stored as ``candidate`` at confidence < 0.9.
"""

from __future__ import annotations

__all__ = ["probes"]
