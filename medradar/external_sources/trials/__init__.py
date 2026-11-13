"""Clinical-trial and research-funding connectors for DATA-EXPANSION-001.

Verified live on 2026-11-09 (see ``research/data_expansion/probes/<id>/``):

==============  ==========================  ==================================
source_id       module                      live status
==============  ==========================  ==================================
clinicaltrials  :mod:`.clinicaltrials_gov`  VERIFIED_API
nih_reporter    :mod:`.nih_reporter`        VERIFIED_API
==============  ==========================  ==================================

``eu_ctis`` (VERIFIED_API), ``eu_cordis`` (VERIFIED_PUBLIC_QUERY),
``who_ictrp`` (UNAVAILABLE) and ``sbir_gov`` (UNAVAILABLE) are probe-only in this
round: their evidence lives in ``research/data_expansion/probes/`` and their
documentation is in the source register.  No connector is shipped for a source
the probe could not verify.

Both connectors attach the company with an explicit ``signal`` tier
(``lead_sponsor`` / ``collaborator`` / ``grantee``) so a sponsor match and a
consortium-participant match are never conflated.
"""

from __future__ import annotations

from typing import Any

from ..scholarly import linking
from . import clinicaltrials_gov, nih_reporter

__all__ = ["clinicaltrials_gov", "nih_reporter", "linking", "SOURCES", "collect_grants"]

#: Connectors that are cleared to run (VERIFIED_API only).
SOURCES = {
    "clinicaltrials_gov": clinicaltrials_gov,
    "nih_reporter": nih_reporter,
}


def collect_grants(
    client: Any,
    *,
    limit: int = 50,
    criteria: Any = None,
    max_pages: int = 2,
) -> list[dict]:
    """Collect NIH award records (``grant`` kind), bounded by ``limit``."""
    return nih_reporter.collect(
        client, limit=limit, criteria=criteria, max_pages=max_pages
    )

