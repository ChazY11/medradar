"""Append the B-049 task to research/BACKLOG.yaml (idempotent)."""
from __future__ import annotations

from pathlib import Path

PATH = Path("research/BACKLOG.yaml")
TASK = """  - id: B-049
    layer: understand
    priority: P1
    title: Full-roster profiles and a frozen dated snapshot set
    status: todo
    owner: lead
    depends_on: [B-027]
    acceptance: >
      Extend the seven-field profile engine beyond the five mandated deep cases to the full curated
      roster, then freeze a dated snapshot (profiles + source hashes + as-of date) so later cycles can
      compare against it. The snapshot is the point-in-time artifact any rolling-origin evaluation
      needs; without it, "what did we believe on date X" cannot be audited.
"""


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if "id: B-049" in text:
        print("B-049 already present")
        return 0
    PATH.write_text(text.rstrip("\n") + "\n\n" + TASK, encoding="utf-8", newline="\n")
    print("B-049 appended")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
