"""Recruitment lane: observe what medical-device firms publicly advertise for R&D.

Phase 4 · Innovation Signals Observatory. The research question this lane exists to
answer is *not* "how many jobs does company X have" — it is whether publicly
observable technical hiring activity can provide credible, traceable early evidence
of an emerging R&D direction. That requires four things this package keeps
separate on purpose:

  * `records`     — the observation shape and its time semantics (what a source
                    said, when it said it, when we saw it);
  * `politeness`  — robots.txt authorisation and the rate/request ceilings;
  * `workday`     — one platform's lawful public endpoints, parsed into records;
  * <platform>    — siblings for other career systems, added only after the same
                    source investigation is recorded.

Nothing here classifies a job, infers a technology direction, or scores a company.
Classification is a separate, auditable step (rules baseline and local-model arm
under `experiments/innovation_signals_observatory/`).
"""
from __future__ import annotations

from . import politeness, records, store, workday  # noqa: F401

__all__ = ["politeness", "records", "store", "workday"]
