"""Repair the backlog: quote every `notes:` value so YAML can parse prose containing colons."""
from __future__ import annotations

from pathlib import Path

BACKLOG = Path("research/BACKLOG.yaml")
PREFIX = "    notes: "


def main() -> int:
    lines = BACKLOG.read_text(encoding="utf-8").splitlines()
    out, quoted = [], 0
    for line in lines:
        if line.startswith(PREFIX) and not line.startswith(PREFIX + '"'):
            value = line[len(PREFIX):].replace('"', "'")
            out.append(f'{PREFIX}"{value}"')
            quoted += 1
        else:
            out.append(line)
    BACKLOG.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print(f"quoted {quoted} notes lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
