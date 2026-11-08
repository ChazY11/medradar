"""Procurement and hiring connectors (DATA-EXPANSION-001, owner: ``procurement``).

Two procurement chains and one hiring route live in this subpackage, and the
whole point is that they are **not** the same thing:

Procurement
-----------
``procurement_notice``  a buying intention was published (tender / opportunity)
``procurement_award``   a winner and a signed contract were published

The five-step chain the studies must respect is
notice → award → contract signed → delivery → realised revenue.  Public sources
here cover at most the first three, and never the last two:

* ``usaspending``  — award actions only (post-award). No notice stage, no
  revenue, and no publication date at all.
* ``uk_find_a_tender`` — OCDS releases that are stage-tagged, so it emits
  ``procurement_notice`` for tender releases and ``procurement_award`` for
  award/contract releases, each with its own date.
* ``eu_ted`` — verified but **no connector**: the search index does not expose
  the winning supplier, so an award→supplier link cannot be built from it.  A
  connector that emitted awards without a supplier would be worse than none.
* ``sam_gov`` — documented, registration-gated, no connector.
* ``china_ccgp``, ``ocds_registry`` — HTML-only / standards-layer: documented,
  no connector.

Hiring
------
``greenhouse`` and ``lever`` are the only verified job APIs, and **none of the
five target firms publishes on either** (see
``research/data_expansion/samples/procurement/FIVE_FIRM_PROBE.json``).  Both
connectors are therefore shipped as the correct method with currently-empty
results for these firms, not as a claim that hiring data was obtained.

Connectors are import-safe: no module here performs network I/O at import time,
and every network call goes through :class:`medradar.external_sources.base.HttpClient`
so request budgets, rate limiting and the request ledger always apply.
"""

from __future__ import annotations

from medradar.external_sources.procurement import common

__all__ = ["common"]
