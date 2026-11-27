"""Versioned export for ATLAS-001.

An export is a directory that can be consumed without this repository:

    exports/<export_id>/
        MANIFEST.json          <- what is inside, hashes, licence posture
        README.md              <- how to load it, and what it does not claim
        <source_id>.jsonl      <- horizon.evidence.v1 records, one per line
        <source_id>.sha256     <- digest of the jsonl

The manifest deliberately records *coverage limits* next to the counts, because
the single most expensive mistake in this class of work is reading a row count
as a coverage statement.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Iterable

from .schema import SCHEMA_VERSION, EvidenceRecord, dedupe_key


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_file(path: str) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def write_export(
    root: str,
    export_id: str,
    by_source: dict[str, list[dict]],
    *,
    generator: str,
    command: str,
    coverage_notes: list[str],
    licence_summary: dict[str, str],
    extra: dict[str, Any] | None = None,
) -> str:
    """Write one immutable export directory; return its path."""
    out = os.path.join(root, "exports", export_id)
    os.makedirs(out, exist_ok=True)

    files: list[dict[str, Any]] = []
    per_source: list[dict[str, Any]] = []
    for source_id, records in sorted(by_source.items()):
        path = os.path.join(out, f"{source_id}.jsonl")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        digest, size = _sha256_file(path)
        with open(path + ".sha256", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f"{digest}  {source_id}.jsonl\n")
        keys = [dedupe_key(r) for r in records]
        uniq = len(set(keys))
        with_id = sum(1 for r in records if r.get("identifiers"))
        with_pub = sum(1 for r in records if r.get("source_public_at"))
        with_ev = sum(1 for r in records if r.get("event_at"))
        files.append(
            {
                "source_id": source_id,
                "path": f"{source_id}.jsonl",
                "sha256": digest,
                "bytes": size,
                "records": len(records),
            }
        )
        per_source.append(
            {
                "source_id": source_id,
                "records": len(records),
                "unique_dedupe_keys": uniq,
                "records_with_identifiers": with_id,
                "records_with_source_public_at": with_pub,
                "records_with_event_at": with_ev,
                "licence_status": licence_summary.get(source_id, "unknown"),
            }
        )

    manifest = {
        "export_id": export_id,
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "generator": generator,
        "reproduce_command": command,
        "files": files,
        "per_source": per_source,
        "totals": {
            "sources": len(by_source),
            "records": sum(f["records"] for f in files),
            "bytes": sum(f["bytes"] for f in files),
        },
        "licence_summary": licence_summary,
        "coverage_notes": coverage_notes,
        "extra": extra or {},
    }
    with open(os.path.join(out, "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    readme = [
        f"# Export `{export_id}`",
        "",
        f"Schema: `{SCHEMA_VERSION}`  ",
        f"Generated: {manifest['generated_at']}  ",
        f"Generator: `{generator}`",
        "",
        "## How to load",
        "",
        "```python",
        "import json",
        f"rows = [json.loads(l) for l in open('{list(by_source)[0] if by_source else 'SOURCE'}.jsonl', encoding='utf-8')]",
        "```",
        "",
        "Every row validates against `research/horizon/hz/schema.py`. Rows are "
        "already deduplicated *within* a source; cross-source dedupe uses "
        "`hz.schema.dedupe_key`.",
        "",
        "## What this export does NOT claim",
        "",
    ]
    for n in coverage_notes:
        readme.append(f"- {n}")
    readme += [
        "",
        "## Per-source counts",
        "",
        "| source | records | unique keys | with id | with public date | licence |",
        "|---|---|---|---|---|---|",
    ]
    for p in per_source:
        readme.append(
            f"| `{p['source_id']}` | {p['records']} | {p['unique_dedupe_keys']} | "
            f"{p['records_with_identifiers']} | {p['records_with_source_public_at']} | "
            f"{p['licence_status']} |"
        )
    readme.append("")
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(readme))
    return out
