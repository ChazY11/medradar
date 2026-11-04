"""Bounded, keyless ClinicalTrials.gov fetcher for the WP2c evidence linker.

Why a separate script
---------------------
``link_evidence.py`` must stay deterministic and offline: a pipeline that hits the
network is not re-runnable and would let a live response change a verdict. This
script is the only component that talks to the network. It fetches a **small,
declared set** of ClinicalTrials.gov API v2 responses, writes the raw JSON to
``.../results/2026-11-04/_httpcache_evidence/ctgov/`` (outside git), and the
pipeline reads that cache. Every request is recorded with its URL, status, time and
result count.

What is requested, and why it is bounded
----------------------------------------
Only candidate technology tracks (the tracks whose posting cells cleared the
candidate threshold in the evidence artifact) are queried, one request per track.
The query term is the **longest frontier keyword** of the existing track (e.g.
``PULSED FIELD ABLATION``), and the sponsor filter is the focus company's display
name (e.g. ``Medtronic``). No pagination, ``pageSize=10``, one request per track,
``MAX_REQUESTS`` hard ceiling, >=1.0 s between requests.

Linkage is *not* decided here: the pipeline re-applies the four pre-declared rules
to each returned record, including a verbatim track-keyword check and an exact
entity-token check on the lead sponsor name.

Usage
-----
    python experiments/innovation_signals_observatory/evidence/fetch_ctgov_evidence.py \
        --artifact .../results/2026-11-04/evidence_linking.json \
        --company-key medtronic

    # or explicitly (used while the authoritative snapshot is still collecting):
    python .../fetch_ctgov_evidence.py --tracks ep_pfa,cardiac_rhythm,medical_ai \
        --company-key medtronic
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EXPERIMENT_DIR = REPO_ROOT / "experiments" / "innovation_signals_observatory"
RESULTS_DIR = EXPERIMENT_DIR / "results" / "2026-11-04"
DEFAULT_CACHE = RESULTS_DIR / "_httpcache_evidence" / "ctgov"
CONFIG_DIR = REPO_ROOT / "config"

API_BASE = "https://clinicaltrials.gov/api/v2/studies"
USER_AGENT = "MedRadar-research/0.1 (public evidence; contact: local research workspace)"
MAX_REQUESTS = 20
MIN_INTERVAL_S = 1.0
DEFAULT_PAGE_SIZE = 10
FIELDS = (
    "NCTId",
    "BriefTitle",
    "OverallStatus",
    "StartDate",
    "StudyFirstPostDate",
    "LeadSponsorName",
    "Condition",
    "InterventionName",
    "BriefSummary",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_tracks() -> dict[str, dict[str, Any]]:
    doc = read_json(CONFIG_DIR / "tracks_device.json")
    return {str(track["id"]): track for track in doc.get("tracks", [])}


def load_display_name(company_key: str) -> str:
    doc = read_json(CONFIG_DIR / "universe_v1.json")
    focus = (doc.get("focus_companies") or {}).get(company_key) or {}
    name = focus.get("display_name") or company_key
    return str(name)


def candidate_tracks(artifact_path: Path) -> list[str]:
    artifact = read_json(artifact_path)
    tracks = {
        str(cell["track_id"])
        for cell in artifact.get("cells", [])
        if cell.get("is_candidate") is True
    }
    return sorted(tracks)


def query_term(track: dict[str, Any]) -> str:
    """The track's longest frontier keyword, else its longest keyword."""
    candidates = [str(k) for k in (track.get("frontier_keywords") or [])] or [
        str(k) for k in (track.get("keywords") or [])
    ]
    if not candidates:
        raise ValueError(f"track {track.get('id')!r} has no keyword to query")
    return max(candidates, key=lambda keyword: (len(keyword), keyword))


def build_url(*, sponsor: str, term: str, page_size: int) -> str:
    params = {
        "query.spons": sponsor,
        "query.term": term,
        "pageSize": str(page_size),
        "format": "json",
        "fields": ",".join(FIELDS),
    }
    return API_BASE + "?" + urllib.parse.urlencode(params)


def fetch(url: str) -> tuple[int, Any, str | None]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
            return int(response.status), json.loads(body.decode("utf-8")), None
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        return int(exc.code), None, f"HTTPError: {exc}"
    except Exception as exc:  # noqa: BLE001 - the failure mode is recorded, never hidden
        return 0, None, f"{type(exc).__name__}: {exc}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded ClinicalTrials.gov evidence fetcher")
    parser.add_argument("--artifact", default=None, help="evidence_linking.json to read candidate tracks from")
    parser.add_argument("--tracks", default=None, help="explicit comma-separated track ids")
    parser.add_argument("--company-key", default="medtronic")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--max-requests", type=int, default=MAX_REQUESTS)
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    parser.add_argument("--sleep", type=float, default=MIN_INTERVAL_S)
    args = parser.parse_args(argv)

    tracks = load_tracks()
    if args.tracks:
        wanted = [part.strip() for part in args.tracks.split(",") if part.strip()]
    elif args.artifact:
        wanted = candidate_tracks(Path(args.artifact))
    else:
        parser.error("pass --tracks or --artifact")
    unknown = [track_id for track_id in wanted if track_id not in tracks]
    if unknown:
        parser.error(f"unknown track ids: {unknown}")
    wanted = wanted[: args.max_requests]
    sponsor = load_display_name(args.company_key)

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    index_path = cache_dir / "_index.json"
    index: dict[str, Any] = (
        read_json(index_path) if index_path.exists() else {"company_key": args.company_key, "requests": []}
    )

    print(f"company={args.company_key} sponsor_query={sponsor!r} tracks={wanted} cache={cache_dir}")
    for position, track_id in enumerate(wanted):
        track = tracks[track_id]
        term = query_term(track)
        url = build_url(sponsor=sponsor, term=term, page_size=args.page_size)
        record: dict[str, Any] = {
            "track_id": track_id,
            "query_term": term,
            "url": url,
            "fetched_at": utc_now_iso(),
            "status": None,
            "n_studies": None,
            "error": None,
        }
        status, body, error = fetch(url)
        record.update({"status": status, "error": error})
        if body is not None:
            record["n_studies"] = len(body.get("studies") or [])
            target = cache_dir / f"ctgov_{track_id}.json"
            target.write_text(
                json.dumps(
                    {
                        "request": {
                            "url": url,
                            "track_id": track_id,
                            "query_term": term,
                            "company_key": args.company_key,
                            "sponsor_query": sponsor,
                            "fetched_at": record["fetched_at"],
                        },
                        "status": status,
                        "body": body,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            record["file"] = target.name
        index["requests"] = [
            existing for existing in index.get("requests", []) if existing.get("track_id") != track_id
        ] + [record]
        index["updated_at"] = utc_now_iso()
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(record, ensure_ascii=False))
        if position < len(wanted) - 1:
            time.sleep(args.sleep)

    print(f"\nwrote {len(index.get('requests', []))} request records to {index_path}")
    print("NOTE: raw responses live outside git; only the pipeline artifacts are committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
