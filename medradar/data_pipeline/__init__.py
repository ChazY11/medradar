"""DATA-001: continuous FDA source monitoring, change ledger and safe publication.

The package is intentionally dependency-free beyond the Python standard library and the
existing MedRadar product modules. It does not run inside the web process: the web process
only reads the active snapshot pointer and the read-only status database.
"""
from .config import PIPELINE_VERSION, Settings
from .pipeline import Pipeline, PipelineError
from .status_service import changes_feed, data_status

__all__ = [
    "PIPELINE_VERSION",
    "Pipeline",
    "PipelineError",
    "Settings",
    "changes_feed",
    "data_status",
]
