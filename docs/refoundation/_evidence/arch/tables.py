"""Inventory CREATE TABLE statements per store/ref. Read-only git access."""
import re
import subprocess

GIT = ["git", "-C", r"<REDACTED_LOCAL_PATH>"]
TARGETS = [
    ("origin/main", "medradar/db.py"),
    ("origin/main", "medradar/forecast_registry.py"),
    ("origin/main", "medradar/tkg/store.py"),
    ("origin/main", "medradar/intelligence/storage.py"),
    ("origin/main", "medradar/intelligence/sources/market_data.py"),
    ("origin/feat/observatory-reliability-v1", "medradar/observatory/ledger.py"),
    ("origin/foundation/atlas-001", "medradar/atlas/db/migrations.py"),
    ("origin/foundation/atlas-001", "medradar/atlas/store.py"),
    ("origin/research/data-expansion-001", "medradar/external_sources/store.py"),
    ("origin/integration/convergence-001", "medradar/integration/staging.py"),
]


def show(ref, path):
    p = subprocess.run(GIT + ["show", f"{ref}:{path}"], capture_output=True, text=True, errors="replace")
    return p.stdout


for ref, path in TARGETS:
    src = show(ref, path)
    tables = re.findall(r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+([\w.\"]+)", src)
    triggers = re.findall(r"CREATE TRIGGER(?:\s+IF NOT EXISTS)?\s+([\w]+)", src)
    print(f"{len(tables):3d} tables {len(triggers):3d} triggers  {ref}:{path}")
    print("      " + ", ".join(tables))
    if triggers:
        print("      triggers: " + ", ".join(triggers))
