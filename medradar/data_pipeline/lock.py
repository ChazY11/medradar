"""Cross-platform single-writer lock for check/sync/publish/rollback."""
from __future__ import annotations

import os
import time
from pathlib import Path
from types import TracebackType


class PipelineLocked(RuntimeError):
    pass


class PipelineLock:
    def __init__(self, path: Path | str, *, timeout_seconds: float = 0.0) -> None:
        self.path = Path(path)
        self.timeout_seconds = timeout_seconds
        self._handle = None

    def __enter__(self) -> "PipelineLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + max(0.0, self.timeout_seconds)
        self._handle = self.path.open("a+b")
        while True:
            try:
                self._acquire()
                break
            except OSError:
                if time.monotonic() >= deadline:
                    self._handle.close()
                    self._handle = None
                    raise PipelineLocked("another pipeline operation holds " + str(self.path))
                time.sleep(0.2)
        try:
            self._handle.seek(0)
            self._handle.truncate()
            self._handle.write(("pid=" + str(os.getpid()) + "\n").encode("ascii"))
            self._handle.flush()
        except OSError:
            pass
        return self

    def _acquire(self) -> None:
        assert self._handle is not None
        if os.name == "nt":
            import msvcrt

            self._handle.seek(0)
            if self._handle.read(1) == b"":
                self._handle.write(b"\0")
                self._handle.flush()
            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release(self) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self._handle.close()
            self._handle = None

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 tb: TracebackType | None) -> None:
        self._release()
