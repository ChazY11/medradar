"""Trade statistics and trade-shipment connectors (DATA-EXPANSION-001).

Two things that look similar and are not
----------------------------------------
``trade_aggregate``
    Country-level statistics by HS/CN code (UN Comtrade, US Census, Eurostat
    Comext, UK HMRC ``OTS``).  The unit of observation is *a country's trade in a
    commodity in a period*.  It **cannot** name an importer, an exporter, a
    shipment or a product.  It is a macro backdrop, never firm evidence.

``shipment``
    Company-level records (bills of lading, customs consignments, trader
    registers).  The unit of observation is *a named company trading something*.
    Only this class can support a statement about Medtronic / GE HealthCare /
    Philips / Dräger / Mindray.

The two are **not interchangeable**: aggregating bill-of-lading records does not
reproduce national statistics (different coverage, thresholds, valuation and
confidentiality rules), and national statistics cannot be disaggregated to
firms.  Every module here states which class it produces, and
:func:`medradar.external_sources.schema.make_evidence` records it as the
``kind``.

What is implemented, and what is deliberately absent
----------------------------------------------------
Implemented (probed live, open access, no key):

* :mod:`~medradar.external_sources.trade.un_comtrade` — Comtrade public preview
* :mod:`~medradar.external_sources.trade.eurostat_comext` — Eurostat Comext
* :mod:`~medradar.external_sources.trade.uk_hmrc_trade` — HMRC UK Trade Info

Deliberately absent: **there is no patent connector in this package.**  Every
patent source probed in this round (EPO OPS, USPTO Open Data Portal, PatentsView,
USPTO bulk, WIPO PATENTSCOPE, Google Patents BigQuery, Lens.org) either requires
registration/credentials, is paid, or is retired; a connector that cannot be
exercised against a live endpoint would be untested code pretending to be
infrastructure.  See ``research/data_expansion/handoffs/patents.json``.

Also absent for the same reason: US Census trade (needs a key), USITC DataWeb (no
machine interface), ImportYeti (robots-disallowed), China customs (captcha/412),
ImportGenius / Panjiva / Datamyne (paid).

Nothing here performs network I/O at import time.
"""

from __future__ import annotations

__all__ = [
    "AGGREGATE_KIND",
    "SHIPMENT_KIND",
    "CLASS_NOTE",
]

#: Evidence kind used by country-level statistics.
AGGREGATE_KIND = "trade_aggregate"
#: Evidence kind used by company-level trade records.
SHIPMENT_KIND = "shipment"

CLASS_NOTE = (
    "trade_aggregate = country x HS-code x period; identifies no company. "
    "shipment = company-level record. They are not interchangeable."
)
