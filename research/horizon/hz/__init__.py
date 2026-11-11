"""HORIZON-001 data engineering core.

Independent, versioned data-exchange layer for MedRadar.
This package deliberately does NOT import from ``medradar`` so that it can run
in a worktree without depending on ATLAS-001's evolving core.

Layout
------
hz.schema    horizon.evidence.v1 record contract + hashing
hz.http      bounded HTTP client (budget / retry / response cap / request log)
hz.probe     declarative source probes -> SOURCE_PROBES/ evidence
hz.registry  source register (access, licence, blockers) -> registry/sources/
hz.export    versioned JSONL export + manifest for ATLAS-001 handoff
hz.cli       argparse entry point
"""

__version__ = "1.0.0"
SCHEMA_VERSION = "horizon.evidence.v1"
