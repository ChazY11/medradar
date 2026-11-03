"""hist_v2 domain panel builder — aggregate the frozen hist_v1 panel to (company, domain).

Pre-registration: ``research/protocols/hist_v2_preregistration.md`` (frozen 2026-11-03).
The hist_v1 panel (``out/hist_v1/panel.json``, schema ``hist_v1.panel.v1``) is the frozen
input and is never modified.  Each hist_v1 ``(company, track)`` pair is mapped to its
technology *domain* through ``config/tracks_device.json`` (field ``tracks[].domain``) and
the pair's per-quarter material-event counts are summed per ``(company, domain)``.

This script contains no model, no label and no outcome metric.  Standard library only, no
network, no randomness, no wall clock: ``generated_at`` is the hist_v1 data snapshot time,
so two runs on the same inputs are byte-identical.

Usage::

    python experiments/hist_v2/build_domain_panel.py

Outputs (canonical run):

* ``out/hist_v2/domain_panel.json``      (git-ignored; SHA-256 in the manifest)
* ``experiments/hist_v2/manifest.json``  (SHA-256 of inputs/script/output, row counts)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]

PANEL_SCHEMA = "hist_v2.domain_panel.v1"
AUDITS_SCHEMA = "hist_v2.audits.v1"
SOURCE_SCHEMA = "hist_v1.panel.v1"
MANIFEST_SCHEMA = "hist_v2.manifest.v1"

SOURCE_PANEL = ROOT / "out" / "hist_v1" / "panel.json"
TRACKS_CONFIG = ROOT / "config" / "tracks_device.json"
OUT_PANEL = ROOT / "out" / "hist_v2" / "domain_panel.json"
OUT_MANIFEST = ROOT / "experiments" / "hist_v2" / "manifest.json"

COMMAND = "python experiments/hist_v2/build_domain_panel.py"


# ------------------------------------------------------------------------ utilities
def sha256_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Compact, key-sorted UTF-8 JSON with a trailing newline (byte-identical re-runs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    path.write_bytes((text + "\n").encode("utf-8"))


def quarter_index(date_text: str | None) -> int | None:
    """Quarter index on the hist_v1 grid (1976-Q1 = 0) for an ISO date string."""
    if not date_text or len(date_text) < 7:
        return None
    try:
        year = int(date_text[0:4])
        month = int(date_text[5:7])
    except (TypeError, ValueError):
        return None
    if year < 1976:
        return None
    return (year - 1976) * 4 + (month - 1) // 3


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _git_head() -> tuple[str | None, str | None]:
    try:
        head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=False)
        branch = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, check=False)
        if head.returncode != 0:
            return None, None
        return head.stdout.strip() or None, (branch.stdout.strip() or None)
    except (OSError, subprocess.SubprocessError):
        return None, None


# --------------------------------------------------------------- domain aggregation
def track_domain_map(tracks_config: Mapping[str, Any]) -> dict[str, str | None]:
    """track id -> domain id (None when the config track has no domain)."""
    mapping: dict[str, str | None] = {}
    for track in tracks_config.get("tracks", []):
        track_id = track.get("id")
        if not isinstance(track_id, str) or not track_id:
            continue
        domain = track.get("domain")
        mapping[track_id] = domain if isinstance(domain, str) and domain else None
    return mapping


def domain_category_bands(tracks_config: Mapping[str, Any],
                          observed_track_ids: Iterable[str]) -> dict[str, list[str]]:
    """category band of each observed domain: union of its tracks' ``category`` values."""
    observed = set(observed_track_ids)
    categories: dict[str, set[str]] = defaultdict(set)
    for track in tracks_config.get("tracks", []):
        track_id = track.get("id")
        if track_id not in observed:
            continue
        domain = track.get("domain")
        category = track.get("category")
        if isinstance(domain, str) and domain and isinstance(category, str) and category:
            categories[domain].add(category)
    return {domain: sorted(values) for domain, values in sorted(categories.items())}


def aggregate_pairs(
    records: Iterable[Mapping[str, Any]],
    mapping: dict[str, str | None],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Sum hist_v1 ``(company, track)`` pair counts into ``(company, domain)`` pairs.

    ``event_counts`` is the event multiset per quarter (sum of the source tracks' counts);
    ``event_iso`` is the earliest availability date among the contributing events in that
    quarter, so aggregation preserves per-quarter activity without inventing events.
    Pairs whose track has no domain are excluded and reported in the audit block.
    """
    grouped: dict[tuple[str, str], list[tuple[int, str, int]]] = defaultdict(list)
    kinds: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    source_events = 0
    source_510k = source_pma = 0
    unmapped_510k = unmapped_pma = 0
    unmapped_tracks: Counter[str] = Counter()
    unmapped_events: Counter[tuple[str, str]] = Counter()
    for pair in records:
        qidxs = pair.get("event_qidx") or []
        if not qidxs:
            continue
        counts = pair.get("event_counts") or [1] * len(qidxs)
        isos = pair.get("event_iso") or [""] * len(qidxs)
        track_id = pair.get("track_id")
        domain = mapping.get(track_id)
        pair_events = sum(int(count) for count in counts)
        pair_510k = int(pair.get("n_510k") or 0)
        pair_pma = int(pair.get("n_pma") or 0)
        source_events += pair_events
        source_510k += pair_510k
        source_pma += pair_pma
        if domain is None:
            unmapped_tracks[track_id or "<null>"] += 1
            unmapped_events[(pair["company_key"], track_id or "<null>")] += pair_events
            unmapped_510k += pair_510k
            unmapped_pma += pair_pma
            continue
        kind = kinds[(pair["company_key"], domain)]
        kind[0] += pair_510k
        kind[1] += pair_pma
        for index, qidx in enumerate(qidxs):
            grouped[(pair["company_key"], domain)].append(
                (int(qidx), isos[index], int(counts[index])))
    domain_pairs: list[dict[str, Any]] = []
    for (company, domain), items in sorted(grouped.items()):
        items.sort()
        iso_by_quarter: dict[int, str] = {}
        count_by_quarter: dict[int, int] = {}
        for qidx, iso, count in items:
            if qidx not in iso_by_quarter or iso < iso_by_quarter[qidx]:
                iso_by_quarter[qidx] = iso
            count_by_quarter[qidx] = count_by_quarter.get(qidx, 0) + count
        qidxs = sorted(iso_by_quarter)
        exact = kinds[(company, domain)]
        domain_pairs.append({
            "company_key": company,
            "domain_id": domain,
            "event_qidx": qidxs,
            "event_iso": [iso_by_quarter[qidx] for qidx in qidxs],
            "event_counts": [count_by_quarter[qidx] for qidx in qidxs],
            "n_510k": exact[0],
            "n_pma": exact[1],
        })
    return domain_pairs, {
        "source_events": source_events,
        "source_510k": source_510k,
        "source_pma": source_pma,
        "unmapped_510k": unmapped_510k,
        "unmapped_pma": unmapped_pma,
        "unmapped_pair_count": sum(unmapped_tracks.values()),
        "unmapped_tracks": dict(sorted(unmapped_tracks.items())),
        "unmapped_events": [
            {"company_key": company, "track_id": track, "events": events}
            for (company, track), events in sorted(unmapped_events.items(), key=str)],
    }


# ---------------------------------------------------------------------------- panel
def build(*, panel_path: Path, tracks_config_path: Path,
          out_panel_path: Path, manifest_path: Path) -> dict[str, Any]:
    source = read_json(panel_path)
    tracks_config = read_json(tracks_config_path)

    if source.get("schema") != SOURCE_SCHEMA:
        raise SystemExit(f"source panel schema {source.get('schema')!r} != {SOURCE_SCHEMA!r}")
    quarters = list(source["quarters"])
    if not quarters:
        raise SystemExit("source panel has no quarters")

    mapping = track_domain_map(tracks_config)
    observed_track_ids = ({record["id"] for record in source["tracks"]}
                          | {pair["track_id"] for pair in source["pairs"]})
    bands = domain_category_bands(tracks_config, observed_track_ids)

    pairs, pair_audit = aggregate_pairs(source["pairs"], mapping)
    pairs_no_acquired, pair_audit_no_acquired = aggregate_pairs(
        source.get("pairs_no_acquired") or [], mapping)

    # ---- companies (same universe/order as hist_v1: sorted by key)
    events_by_company: Counter[str] = Counter()
    first_by_company: dict[str, int] = {}
    last_by_company: dict[str, int] = {}
    domains_by_company: dict[str, set[str]] = defaultdict(set)
    for pair in pairs:
        events = sum(pair["event_counts"])
        company = pair["company_key"]
        events_by_company[company] += events
        first_by_company[company] = min(first_by_company.get(company, pair["event_qidx"][0]),
                                        pair["event_qidx"][0])
        last_by_company[company] = max(last_by_company.get(company, pair["event_qidx"][-1]),
                                       pair["event_qidx"][-1])
        domains_by_company[company].add(pair["domain_id"])
    companies = []
    for record in source["companies"]:
        key = record["key"]
        companies.append({
            "key": key,
            "display_name": record.get("display_name"),
            "cohort": record.get("cohort"),
            "total_material_events": events_by_company.get(key, 0),
            "first_event_qidx": first_by_company.get(key),
            "last_event_qidx": last_by_company.get(key),
            "n_domains_ever": len(domains_by_company.get(key, ())),
        })

    # ---- domains (only the domains observed in the frozen hist_v1 panel)
    observed_domains = sorted({pair["domain_id"] for pair in pairs})
    domain_name = {record.get("id"): record.get("name_en")
                   for record in tracks_config.get("domains", [])}
    domain_stats: dict[str, dict[str, Any]] = {}
    for domain in observed_domains:
        domain_pairs = [pair for pair in pairs if pair["domain_id"] == domain]
        industry = [qidx for pair in domain_pairs
                    for qidx, count in zip(pair["event_qidx"], pair["event_counts"])
                    for _ in range(count)]
        domain_stats[domain] = {
            "track_ids": sorted(track for track in observed_track_ids
                                if mapping.get(track) == domain),
            "n_firms_ever": len({pair["company_key"] for pair in domain_pairs}),
            "total_material_events": len(industry),
            "n_510k": sum(pair["n_510k"] for pair in domain_pairs),
            "n_pma": sum(pair["n_pma"] for pair in domain_pairs),
            "first_industry_qidx": min(pair["event_qidx"][0] for pair in domain_pairs),
        }
    domains = []
    for domain in observed_domains:
        stats = domain_stats[domain]
        domains.append({
            "id": domain,
            "name_en": domain_name.get(domain) or domain,
            "n_tracks": len(stats["track_ids"]),
            "track_ids": stats["track_ids"],
            "categories": bands.get(domain, []),
            "first_industry_qidx": stats["first_industry_qidx"],
            "n_firms_ever": stats["n_firms_ever"],
            "total_material_events": stats["total_material_events"],
            "n_510k": stats["n_510k"],
            "n_pma": stats["n_pma"],
        })

    # ---- sibling domains (the domain-level adjacency used by the evaluator)
    band_of = {domain: frozenset(bands.get(domain, [])) for domain in observed_domains}
    siblings = {
        domain: sorted(other for other in observed_domains
                       if other != domain and (band_of[domain] & band_of[other]))
        for domain in observed_domains}
    domain_bands = {
        domain: {"categories": sorted(band_of[domain]), "sibling_domains": siblings[domain]}
        for domain in observed_domains}

    def pair_summary(records: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "n_pairs": len(records),
            "n_events": sum(sum(pair["event_counts"]) for pair in records),
            "n_510k": sum(pair["n_510k"] for pair in records),
            "n_pma": sum(pair["n_pma"] for pair in records),
            "n_pair_quarters": sum(len(pair["event_qidx"]) for pair in records),
        }

    summary = pair_summary(pairs)
    summary_no_acquired = pair_summary(pairs_no_acquired)
    source_total_events = int(source["audits"]["panel_summary"]["n_material_events"])
    unmapped_events = pair_audit["unmapped_events"]
    n_unmapped_events = sum(int(entry["events"]) for entry in unmapped_events)
    source_510k = pair_audit["source_510k"]
    source_pma = pair_audit["source_pma"]
    unmapped_510k = pair_audit["unmapped_510k"]
    unmapped_pma = pair_audit["unmapped_pma"]

    per_domain = {
        domain: {
            "pairs": sum(1 for pair in pairs if pair["domain_id"] == domain),
            "events": domain_stats[domain]["total_material_events"],
            "companies": domain_stats[domain]["n_firms_ever"],
            "n_510k": domain_stats[domain]["n_510k"],
            "n_pma": domain_stats[domain]["n_pma"],
            "first_event_quarter": quarters[domain_stats[domain]["first_industry_qidx"]],
        } for domain in observed_domains}

    audits = {
        "schema": AUDITS_SCHEMA,
        "source": {
            "panel_path": _rel(panel_path),
            "panel_sha256": sha256_file(panel_path),
            "panel_schema": source.get("schema"),
            "tracks_config_path": _rel(tracks_config_path),
            "tracks_config_sha256": sha256_file(tracks_config_path),
        },
        "aggregation": {
            "method": (
                "each hist_v1 (company, track) pair is mapped to its technology domain via "
                "config/tracks_device.json tracks[].domain; per-quarter event_counts are "
                "summed; event_iso is the earliest availability date in the quarter; "
                "n_510k/n_pma are exact sums of the source pair totals"),
            "n_source_pairs": len(source["pairs"]),
            "n_source_pair_quarters": sum(len(pair["event_qidx"]) for pair in source["pairs"]),
            "n_source_events": source_total_events,
            "n_source_510k": source_510k,
            "n_source_pma": source_pma,
            "n_domain_pairs": summary["n_pairs"],
            "n_domain_pair_quarters": summary["n_pair_quarters"],
            "n_domain_events": summary["n_events"],
            "n_domain_510k": summary["n_510k"],
            "n_domain_pma": summary["n_pma"],
            "events_reconciled": (summary["n_events"] == source_total_events - n_unmapped_events),
            "kinds_reconciled": (summary["n_510k"] == source_510k - unmapped_510k
                                 and summary["n_pma"] == source_pma - unmapped_pma),
        },
        "panel_summary": {
            "n_quarters": len(quarters),
            "n_companies": len(companies),
            "n_companies_deep_case": sum(1 for record in companies
                                         if record.get("cohort") == "deep_case"),
            "n_domains": len(domains),
            "n_pairs": summary["n_pairs"],
            "n_pairs_no_acquired": summary_no_acquired["n_pairs"],
            "n_material_events": summary["n_events"],
            "n_material_events_510k": summary["n_510k"],
            "n_material_events_pma": summary["n_pma"],
            "n_events_without_domain": n_unmapped_events,
            "first_panel_event_quarter": quarters[min(pair["event_qidx"][0] for pair in pairs)],
            "last_panel_event_quarter": quarters[max(pair["event_qidx"][-1] for pair in pairs)],
        },
        "pairs_no_acquired": summary_no_acquired,
        "per_domain": per_domain,
        "domain_bands": domain_bands,
        "track_to_domain": {track: mapping.get(track) for track in sorted(observed_track_ids)},
        "unmapped": {
            "definition": (
                "a hist_v1 pair whose track_id has no `domain` in config/tracks_device.json, "
                "or a track id absent from the config"),
            "n_pairs": pair_audit["unmapped_pair_count"],
            "n_pairs_no_acquired": pair_audit_no_acquired["unmapped_pair_count"],
            "n_events": n_unmapped_events,
            "details": unmapped_events,
            "note": (
                "every configured track carries a domain and all 38 observed hist_v1 tracks "
                "map, so this list is empty for the canonical input; the field exists so a "
                "future taxonomy change cannot silently drop events"),
        },
    }

    panel = {
        "schema": PANEL_SCHEMA,
        "generated_at": source.get("generated_at"),
        "quarter_start": quarters[0],
        "quarter_end": quarters[-1],
        "quarters": quarters,
        "companies": companies,
        "domains": domains,
        "pairs": pairs,
        "pairs_no_acquired": pairs_no_acquired,
        "audits": audits,
    }
    _validate_panel(panel, source=source)

    write_json(out_panel_path, panel)
    panel_sha = sha256_file(out_panel_path)
    panel_bytes = out_panel_path.stat().st_size

    head_commit, branch = _git_head()
    script_path = Path(__file__).resolve()
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "generated_at": source.get("generated_at"),
        "generated_at_semantics": (
            "the hist_v1 data snapshot time inherited from the source panel; no wall-clock "
            "value is embedded so regeneration is byte-identical"),
        "command": COMMAND,
        "argv": list(sys.argv),
        "worktree": ROOT.as_posix(),
        "git": {"head_commit": head_commit, "branch": branch,
                "available": head_commit is not None,
                "note": "the worktree HEAD commit; this build did not commit anything"},
        "files": {
            _rel(panel_path): {"sha256": sha256_file(panel_path),
                               "bytes": panel_path.stat().st_size,
                               "role": "frozen hist_v1 source panel (read-only input)"},
            _rel(tracks_config_path): {"sha256": sha256_file(tracks_config_path),
                                       "bytes": tracks_config_path.stat().st_size,
                                       "role": "track metadata: track -> domain mapping"},
            _rel(script_path): {"sha256": sha256_file(script_path),
                                "bytes": script_path.stat().st_size,
                                "role": "domain panel builder"},
            _rel(out_panel_path): {"sha256": panel_sha, "bytes": panel_bytes,
                                   "role": "generated domain panel"},
        },
        "row_counts": {
            "source_panel": {
                "companies": len(source["companies"]),
                "tracks": len(source["tracks"]),
                "pairs": len(source["pairs"]),
                "pairs_no_acquired": len(source.get("pairs_no_acquired") or []),
                "material_events": source_total_events,
                "quarters": len(quarters),
            },
            "domain_panel": {
                "companies": len(companies),
                "companies_deep_case": sum(1 for record in companies
                                           if record.get("cohort") == "deep_case"),
                "domains": len(domains),
                "pairs": len(pairs),
                "pairs_no_acquired": len(pairs_no_acquired),
                "material_events": summary["n_events"],
                "pair_quarters": summary["n_pair_quarters"],
                "quarters": len(quarters),
                "events_without_domain": n_unmapped_events,
            },
        },
        "notes": [
            "outputs: out/hist_v2/domain_panel.json (git-ignored), "
            "experiments/hist_v2/manifest.json",
            "domain_panel.json is compact, key-sorted UTF-8 JSON with a trailing newline; "
            "two runs on the same inputs are byte-identical",
            "the hist_v1 panel is not modified; domain-level events are sums of its "
            "per-quarter event_counts",
            "domain adjacency is operationalised over sibling domains sharing a config "
            "`category` band (see audits.domain_bands); the literal reading of 'a different "
            "domain' is implied by firm establishment at domain granularity",
        ],
    }
    write_json(manifest_path, manifest)
    return {
        "panel": panel,
        "panel_path": out_panel_path,
        "panel_sha256": panel_sha,
        "panel_bytes": panel_bytes,
        "manifest_path": manifest_path,
        "manifest": manifest,
        "audits": audits,
    }


def _validate_panel(panel: Mapping[str, Any], *, source: Mapping[str, Any]) -> None:
    """Fail the build if the aggregated panel violates the documented contract."""
    quarters = panel["quarters"]
    if quarters != list(source["quarters"]):
        raise SystemExit("domain panel validation: quarter grid differs from the source panel")
    if panel["quarter_start"] != quarters[0] or panel["quarter_end"] != quarters[-1]:
        raise SystemExit("domain panel validation: quarter_start/quarter_end mismatch")
    max_qidx = len(quarters) - 1

    company_keys = [record["key"] for record in panel["companies"]]
    if company_keys != sorted(company_keys) or len(set(company_keys)) != len(company_keys):
        raise SystemExit("domain panel validation: companies not sorted and unique")
    domain_ids = [record["id"] for record in panel["domains"]]
    if domain_ids != sorted(domain_ids) or len(set(domain_ids)) != len(domain_ids):
        raise SystemExit("domain panel validation: domains not sorted and unique")
    companies = {record["key"]: record for record in panel["companies"]}
    domains = {record["id"]: record for record in panel["domains"]}

    pair_keys: list[tuple[str, str]] = []
    events_by_company: Counter[str] = Counter()
    events_by_domain: Counter[str] = Counter()
    for pair in panel["pairs"]:
        key = (pair["company_key"], pair["domain_id"])
        pair_keys.append(key)
        if key[0] not in companies:
            raise SystemExit(f"domain panel validation: pair {key} references unknown company")
        if key[1] not in domains:
            raise SystemExit(f"domain panel validation: pair {key} references unknown domain")
        qidxs, isos, counts = pair["event_qidx"], pair["event_iso"], pair["event_counts"]
        if not qidxs or not (len(qidxs) == len(isos) == len(counts)):
            raise SystemExit(f"domain panel validation: bad event arrays for {key}")
        if qidxs != sorted(set(qidxs)):
            raise SystemExit(f"domain panel validation: event_qidx not sorted/unique for {key}")
        if any(not isinstance(count, int) or count < 1 for count in counts):
            raise SystemExit(f"domain panel validation: event_counts must be positive for {key}")
        for qidx, iso in zip(qidxs, isos):
            if not 0 <= qidx <= max_qidx:
                raise SystemExit(f"domain panel validation: event_qidx out of bounds for {key}")
            if quarter_index(iso) != qidx:
                raise SystemExit(
                    f"domain panel validation: event_iso {iso!r} is not in quarter {qidx} for "
                    f"{key} (event placed earlier than its availability)")
        n_events = pair["n_510k"] + pair["n_pma"]
        if n_events < len(qidxs):
            raise SystemExit(f"domain panel validation: fewer events than quarters for {key}")
        if sum(counts) != n_events:
            raise SystemExit(
                f"domain panel validation: sum(event_counts) != n_510k + n_pma for {key}")
        events_by_company[key[0]] += n_events
        events_by_domain[key[1]] += n_events
    if pair_keys != sorted(pair_keys) or len(set(pair_keys)) != len(pair_keys):
        raise SystemExit("domain panel validation: pairs not sorted and unique")
    for record in panel["companies"]:
        if record["total_material_events"] != events_by_company[record["key"]]:
            raise SystemExit(
                f"domain panel validation: company {record['key']} event total mismatch")
        if record["total_material_events"] < 1:
            raise SystemExit(f"domain panel validation: company {record['key']} has no event")
    for record in panel["domains"]:
        if record["total_material_events"] != events_by_domain[record["id"]]:
            raise SystemExit(f"domain panel validation: domain {record['id']} event total mismatch")
    if sum(events_by_company.values()) != sum(events_by_domain.values()):
        raise SystemExit("domain panel validation: company/domain event totals disagree")

    # pairs_no_acquired must be an event subset of pairs on the same keys
    by_key = dict(zip(pair_keys, panel["pairs"]))
    for pair in panel["pairs_no_acquired"]:
        key = (pair["company_key"], pair["domain_id"])
        if key not in by_key:
            raise SystemExit(f"domain panel validation: pairs_no_acquired {key} is not a pair")
        if sum(pair["event_counts"]) > sum(by_key[key]["event_counts"]):
            raise SystemExit(
                f"domain panel validation: pairs_no_acquired {key} exceeds the panel pair")
        if pair["n_510k"] + pair["n_pma"] > by_key[key]["n_510k"] + by_key[key]["n_pma"]:
            raise SystemExit(
                f"domain panel validation: pairs_no_acquired {key} kind totals exceed the pair")

    audits = panel["audits"]
    summary = audits["panel_summary"]
    if summary["n_pairs"] != len(panel["pairs"]):
        raise SystemExit("domain panel validation: audit n_pairs mismatch")
    if summary["n_material_events"] != sum(events_by_company.values()):
        raise SystemExit("domain panel validation: audit n_material_events mismatch")
    if summary["n_domains"] != len(panel["domains"]):
        raise SystemExit("domain panel validation: audit n_domains mismatch")
    if not audits["aggregation"]["events_reconciled"]:
        raise SystemExit("domain panel validation: events do not reconcile with the source")
    if not audits["aggregation"]["kinds_reconciled"]:
        raise SystemExit("domain panel validation: 510(k)/PMA totals do not reconcile")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(SOURCE_PANEL),
                        help="frozen hist_v1 panel (schema hist_v1.panel.v1)")
    parser.add_argument("--tracks-config", default=str(TRACKS_CONFIG),
                        help="track metadata with the `domain` field")
    parser.add_argument("--out", default=str(OUT_PANEL),
                        help="output domain panel JSON")
    parser.add_argument("--manifest", default=str(OUT_MANIFEST),
                        help="output manifest JSON")
    args = parser.parse_args(argv)

    result = build(panel_path=Path(args.panel),
                   tracks_config_path=Path(args.tracks_config),
                   out_panel_path=Path(args.out),
                   manifest_path=Path(args.manifest))
    panel = result["panel"]
    summary = {
        "panel": str(result["panel_path"]),
        "panel_bytes": result["panel_bytes"],
        "panel_sha256": result["panel_sha256"],
        "manifest": str(result["manifest_path"]),
        "quarter_start": panel["quarter_start"],
        "quarter_end": panel["quarter_end"],
        "n_quarters": len(panel["quarters"]),
        "n_companies": len(panel["companies"]),
        "n_domains": len(panel["domains"]),
        "n_pairs": len(panel["pairs"]),
        "n_pairs_no_acquired": len(panel["pairs_no_acquired"]),
        "n_material_events": result["audits"]["panel_summary"]["n_material_events"],
        "n_events_without_domain": result["audits"]["panel_summary"]["n_events_without_domain"],
        "git_head": result["manifest"]["git"]["head_commit"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
