"""Where the radar keeps its data, and how that location is chosen.

Four databases, on purpose:

``radar.db``
    the append-only observation ledger plus the mutable cursor/health/work state;

``graph.db``
    the company-technology graph, stored in the bitemporal TKG assertion store so that
    "what did MedRadar know at T" and "what was publicly true at T" are two different,
    separately answerable questions.

``human.db``
    what a person decided (watchlists, review status, audit trail). A decision is not
    derivable from sources, so it must not live in a file that can be rebuilt.

``reference.db``
    the world as the regulator describes it - device identity from UDI/GUDID, and the
    company identifier that identity hangs on. It is a *dimension*, not evidence: it can be
    rebuilt from the source at any time, it is never cited as "what MedRadar knew", and it
    is deliberately not in the ledger, because 5.18M device records are not 5.18M events.

Keeping them apart means a graph rebuild can never damage the observation history, the
ledger can be copied without dragging the derived graph along, and re-syncing device
identity cannot rewrite evidence.

Resolution order for the directory (first match wins):

1. ``MEDRADAR_RADAR_DIR`` - explicit override, used by tests and by the acceptance runs;
2. ``<MEDRADAR_HOME>/radar`` when ``MEDRADAR_HOME`` is set;
3. ``<checkout>/data/radar`` when running from a source checkout (``data/`` is gitignored);
4. ``~/.medradar/radar`` for an installed wheel with no home override.

Nothing is created until a command actually writes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..config import IS_SOURCE_TREE, ROOT, SOURCE_ROOT

ENV_RADAR_DIR = "MEDRADAR_RADAR_DIR"
LEDGER_FILENAME = "radar.db"
GRAPH_FILENAME = "graph.db"
#: Human judgement (watchlists, review decisions, audit trail). Deliberately a third file:
#: the ledger is evidence and must never be written by a web request, so what a person decides
#: lives beside it, revisable, in ~human.db~.
HUMAN_FILENAME = "human.db"
#: Device identity from the regulator (UDI/GUDID). A dimension table, rebuildable at will.
REFERENCE_FILENAME = "reference.db"

#: Environment overrides. A deployment that keeps the register or the document corpus outside
#: the radar directory has to be able to say so without editing code; an unset variable means
#: "use the conventional location", not "disabled".
ENV_REFERENCE_DB = "MEDRADAR_REFERENCE_DB"
ENV_CORPUS_DIR = "MEDRADAR_CORPUS_DIR"
CORPUS_DIRNAME = "corpus510k"


def resolve_radar_dir(override: str | Path | None = None) -> Path:
    if override:
        return Path(override).expanduser()
    configured = str(os.environ.get(ENV_RADAR_DIR) or "").strip()
    if configured:
        return Path(configured).expanduser()
    if os.environ.get("MEDRADAR_HOME"):
        return Path(ROOT) / "radar"
    if IS_SOURCE_TREE:
        return Path(SOURCE_ROOT) / "data" / "radar"
    return Path(ROOT) / "radar"


@dataclass(frozen=True)
class RadarPaths:
    root: Path

    @property
    def ledger(self) -> Path:
        return self.root / LEDGER_FILENAME

    @property
    def human(self) -> Path:
        return self.root / HUMAN_FILENAME

    @property
    def graph(self) -> Path:
        return self.root / GRAPH_FILENAME

    @property
    def reference(self) -> Path:
        """The device register. ``MEDRADAR_REFERENCE_DB`` wins when the file lives elsewhere."""
        override = os.environ.get(ENV_REFERENCE_DB)
        return Path(override) if override else self.root / REFERENCE_FILENAME

    @property
    def corpus(self) -> Path:
        """Where the 510(k) Summary documents are stored, if they are.

        DocumentStore writes one ``.json`` sidecar and one ``.txt`` per filing, so this is a
        directory rather than a database file, and it is optional: a deployment can run the
        register without ever having crawled a document.
        """
        override = os.environ.get(ENV_CORPUS_DIR)
        return Path(override) if override else self.root / CORPUS_DIRNAME

    @property
    def diagnostics(self) -> Path:
        return self.root / "diagnostics"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    def ensure(self) -> "RadarPaths":
        self.root.mkdir(parents=True, exist_ok=True)
        return self

    def describe(self) -> dict[str, str]:
        return {
            "root": str(self.root),
            "ledger": str(self.ledger),
            "graph": str(self.graph),
            "ledger_exists": str(self.ledger.is_file()),
            "graph_exists": str(self.graph.is_file()),
        }


def radar_paths(override: str | Path | None = None) -> RadarPaths:
    return RadarPaths(resolve_radar_dir(override))
