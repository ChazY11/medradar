"""ATLAS: MedRadar's foundation for traceable medical-technology knowledge.

ATLAS is deliberately *not* a model and *not* a report generator.  It is the
substrate that a research claim needs before it can be believed:

``identity``
    Companies, manufacturers, devices and identifiers, with an explicit
    separation between what a source states and what we inferred.

``evidence``
    One immutable, content-addressed record per source fact, with four clocks
    (event / public / first-observed / fetched) and append-only versions.

``graph``
    Typed relations between entities.  Every relation carries its evidence and
    is revocable; inference never masquerades as a source declaration.

``quality``
    Automated checks that make collection failure look like collection
    failure instead of "zero events".

``research``
    ``as_of()`` queries, a prospective-candidate registry, and negative
    controls.

The package is intentionally import-light: importing it never touches the
network and never opens a database.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
