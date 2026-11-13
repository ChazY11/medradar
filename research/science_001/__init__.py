"""SCIENCE-001 - EDGAR historical point-in-time evidence study.

This package is deliberately research code: small, standard-library only, and
runnable end-to-end from a clean checkout with no third-party dependency except
matplotlib (figures only, imported lazily so the analysis core stays portable).

Pipeline:  fetch -> verify -> build -> experiment -> figures
Entry point: python -m research.science_001.cli <command>
"""

__all__ = ["edgar", "timesemantics", "sample", "features", "experiment", "figures"]
VERSION = "1.0.0"
