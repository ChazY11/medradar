"""ATLAS source connectors: one contract, bounded access, explicit licence posture."""

from __future__ import annotations

from .accessgudid import AccessGudidConnector
from .base import Connector, Provenance, clean, provenance_of
from .canada_mdall import CanadaMdallConnector
from .openfda_510k import OpenFda510kConnector
from .openfda_udi import OpenFdaUdiConnector

__all__ = [
    "AccessGudidConnector",
    "CanadaMdallConnector",
    "Connector",
    "OpenFda510kConnector",
    "OpenFdaUdiConnector",
    "Provenance",
    "clean",
    "provenance_of",
]
