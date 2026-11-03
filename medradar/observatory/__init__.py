"""MedRadar Live Observatory — continuous, auditable public-evidence observation.

This package turns MedRadar from a snapshot-based research platform into a system
that observes authoritative public sources, records the real moment each record
was first seen, keeps every payload version, and can replay what the database
knew at any historical instant.

Public entry points::

    from medradar.observatory import ledger, runner, adapter
    from medradar.observatory.adapters import load_adapters
"""

from __future__ import annotations

from . import records
from .ledger import ObservationLedger, default_ledger_path, open_ledger, use_ledger

__all__ = [
    "ObservationLedger",
    "default_ledger_path",
    "open_ledger",
    "use_ledger",
    "records",
]
