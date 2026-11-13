"""Append-only JSONL experiment log.

Why append-only, and why a hash-able log
----------------------------------------
A training run is a sequence of decisions: readiness assessed, run started, step
50 saved, VRAM warning, aborted, resumed.  If those events live in a mutable
status file, the history is whatever the last writer felt like leaving.  JSONL
appended one line at a time is the smallest format that keeps order, survives a
crash mid-line (a torn final line is detectable), and can be diffed.

Rules enforced here
-------------------
* **One record per line**, UTF-8, ``\\n`` terminated.  ``append`` opens the file in
  ``"a"`` mode, writes one line, flushes and ``fsync``-es before returning, so a
  killed process cannot leave a half-written record that later parses as data.
* **UTC ISO-8601 timestamps**, generated at append time (the log is a witness, so
  the time is the time it was written).
* **Nothing outside the root.**  The log file name is validated and resolved with
  ``Path.resolve().is_relative_to(root)``: a caller cannot pass ``../secrets.jsonl``.
* **No silent repair on read.**  A malformed line raises :class:`RunLogError`
  instead of being skipped: a log with holes is not a log.

This module never imports a model library and never touches the network.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_LOG_NAME = "runlog.jsonl"


class RunLogError(RuntimeError):
    """The log is unusable (bad record, malformed existing content, bad root)."""


class PathEscapeError(RunLogError):
    """A caller-supplied path resolved outside the log root."""


def utc_now() -> str:
    """Current UTC time as ISO-8601 (``+00:00`` offset, microseconds preserved)."""
    return datetime.now(timezone.utc).isoformat()


def _safe_segment(value: Any, *, what: str) -> str:
    text = str(value).strip()
    if not text:
        raise PathEscapeError(f"{what} must be a non-empty path segment")
    if text in (".", ".."):
        raise PathEscapeError(f"{what} must not be {text!r}")
    if any(sep in text for sep in ("/", "\\", ":", "\x00")):
        raise PathEscapeError(f"{what} {text!r} must be a single path segment")
    return text


class RunLog:
    """Append-only JSONL log rooted at a directory that may live anywhere *except* in-file paths."""

    def __init__(self, root: str | Path, name: str = DEFAULT_LOG_NAME) -> None:
        self._root = Path(root).expanduser().resolve()
        if self._root.exists() and not self._root.is_dir():
            raise RunLogError(f"run-log root {str(self._root)!r} exists and is not a directory")
        segment = _safe_segment(name, what="run-log file name")
        candidate = (self._root / segment).resolve()
        if not candidate.is_relative_to(self._root):
            raise PathEscapeError(
                f"run-log path {str(candidate)!r} escapes root {str(self._root)!r}"
            )
        self._name = segment
        self._path = candidate

    # ------------------------------------------------------------------ properties
    @property
    def root(self) -> Path:
        return self._root

    @property
    def path(self) -> Path:
        return self._path

    # ----------------------------------------------------------------------- write
    def append(self, event: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Append one record and return it.  Flushed and fsync-ed before returning."""
        if not isinstance(event, str) or not event.strip():
            raise RunLogError("event must be a non-empty string")
        if payload is not None and not isinstance(payload, Mapping):
            raise RunLogError(f"payload must be a mapping or null, got {type(payload).__name__}")
        self._root.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": utc_now(),
            "event": event.strip(),
            "payload": dict(payload or {}),
        }
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        try:
            with open(self._path, "a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise RunLogError(f"cannot append to {str(self._path)!r}: {exc}") from exc
        return record

    # ------------------------------------------------------------------------ read
    def read_all(self) -> list[dict[str, Any]]:
        """Every record in file order.  A malformed line is an error, never skipped."""
        if not self._path.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RunLogError(f"cannot read {str(self._path)!r}: {exc}") from exc
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RunLogError(
                    f"{str(self._path)!r} line {number} is not valid JSON: {exc}"
                ) from exc
            if not isinstance(record, dict):
                raise RunLogError(f"{str(self._path)!r} line {number} is not a JSON object")
            records.append(record)
        return records

    def latest_status(self) -> str | None:
        """The ``status`` carried by the newest record that has one, else ``None``."""
        for record in reversed(self.read_all()):
            payload = record.get("payload")
            if isinstance(payload, Mapping) and isinstance(payload.get("status"), str):
                return payload["status"]
        return None

    def to_json(self, indent: int = 2) -> str:
        """The whole log as one JSON array (for reports and manifests)."""
        return json.dumps(self.read_all(), ensure_ascii=False, indent=indent, sort_keys=False)


__all__ = [
    "DEFAULT_LOG_NAME",
    "PathEscapeError",
    "RunLog",
    "RunLogError",
    "utc_now",
]
