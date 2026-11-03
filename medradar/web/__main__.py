"""Run the MedRadar 2.0 web product.

    python -m medradar.web [--host 127.0.0.1] [--port 8787]

The server is read-only over the research store and serves the static product UI
from the repository's ``web/`` directory.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time


def warm_caches() -> list[str]:
    """Pre-compute the pages a first visitor will open (keeps first paint fast)."""
    from ..product import catalog, entities, store

    done: list[str] = []
    store.dataset_meta()
    done.append("meta")
    store.company_list()
    done.append("companies")
    for key in entities.featured_keys():
        store.company_profile(key, 5)
        done.append(f"company:{key}")
    store.radar_overview(3)
    done.append("radar")
    store.radar_track("patient_monitoring", 10)
    done.append("track:patient_monitoring")
    return done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="medradar-web", description="MedRadar 2.0 product server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-warm", action="store_true", help="skip cache warm-up")
    parser.add_argument("--reload", action="store_true", help="uvicorn auto-reload (development)")
    args = parser.parse_args(argv)

    try:
        import uvicorn
    except ImportError:  # pragma: no cover
        print("uvicorn is required: pip install 'fastapi[standard]' uvicorn", file=sys.stderr)
        return 2

    from ..product import store

    sig = store.dataset_signature()
    if not sig.get("exists"):
        print(
            f"research store missing at {sig.get('path')}\n"
            "build it once with: python -m medradar run   (or point MEDRADAR_HOME at an existing tree)",
            file=sys.stderr,
        )
        return 2

    def _warm() -> None:
        started = time.perf_counter()
        try:
            done = warm_caches()
            print(f"warmed {len(done)} caches in {time.perf_counter() - started:.1f}s", flush=True)
        except Exception as error:  # never block serving because warm-up failed
            print(f"cache warm-up skipped: {error}", file=sys.stderr, flush=True)

    if not args.no_warm:
        # Warm in a daemon thread so the server is reachable immediately; the
        # first visitor may wait a few hundred ms, later ones hit the cache.
        threading.Thread(target=_warm, name="medradar-warm", daemon=True).start()

    print(f"MedRadar 2.0 MVP -> http://{args.host}:{args.port}", flush=True)
    uvicorn.run(
        "medradar.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
