"""What the public tunnel is doing, read from the files the tunnel script writes.

The relay rotates its subdomain and answers 502 for the old address during a reconnect. A reader who hits
that window sees "bad gateway" and has no way to tell it from the service being down, so the state the
script already records is shown next to the data-coverage page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def state(url_file: Path, history_file: Path, *, limit: int = 5) -> dict[str, Any]:
    """Current address and the last few rotations.

    Files rather than a database: the tunnel runs under /bin/sh and must not need the Python venv to record
    what it did. Absence of either file is reported as `available: False` rather than as an empty address.
    """
    out: dict[str, Any] = {"available": False, "url": "", "history": [], "history_file": str(history_file)}
    try:
        url = url_file.read_text(encoding="utf-8").strip()
    except OSError:
        return out
    if not url:
        return out
    out["available"] = True
    out["url"] = url
    try:
        lines = history_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    events = []
    for line in lines:
        if "\t" not in line:
            continue
        stamp, _, address = line.partition("\t")
        if address.strip():
            events.append({"at": stamp.strip(), "url": address.strip()})
    out["history"] = events[-limit:][::-1]  # newest first
    out["rotations"] = len(events)
    return out
