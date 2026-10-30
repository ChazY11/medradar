"""openFDA device collector: product-code → Chinese track dictionary + 510(k)/PMA/recall events.

Two jobs, both idempotent:

1. ``device/classification`` (≈7,000 product codes) is mapped onto the curated Chinese
   tracks from ``config/tracks_device.json`` with a deterministic keyword matcher. The
   result is written to ``config/product_code_tracks.json`` **and** to the
   ``product_codes`` SQLite table, so downstream analysis can join on either.
2. ``device/510k``, ``device/pma`` and ``device/recall`` are pulled **by time window**
   (never by applicant: a clearance filed by "Medtronic Puerto Rico" must not be lost just
   because the parent is not the submitter string). Company resolution happens locally
   through :class:`medradar.config.CompanyRegistry`, and anything that cannot be resolved
   keeps its ``applicant_raw`` value and shows up in ``stats["top_unmatched"]`` instead of
   being guessed.

Design notes
------------
* Every HTTP call goes through :class:`medradar.http.Fetcher`, so responses are cached under
  ``data/cache`` and a re-run is free (and resumable after a rate-limit).
* openFDA caps ``skip`` at 25,000 records. Windows with more hits are split in half
  recursively; a window that still fails (429/500) is split as well instead of aborting.
* ``event_date`` is the earliest *decision* date (510(k)/PMA ``decision_date``, recall
  classification/report date), never the collection date, so the analysis window cannot
  look into the future.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

from .config import CONFIG_DIR, load_companies, load_tracks
from .db import DB, make_event_id
from .http import BudgetExceeded, Fetcher, HttpError, NotFound
from .util import (
    add_months,
    iso,
    norm_text,
    parse_date,
    read_json,
    today_utc,
    tokens,
    truncate,
    write_text,
)

# --------------------------------------------------------------------------- constants
OPENFDA_BASE = "https://api.fda.gov"
CLASSIFICATION_ENDPOINT = "/device/classification.json"

#: kind -> (endpoint, date field used to slice the collection window)
DEVICE_ENDPOINTS: dict[str, tuple[str, str]] = {
    "510k": ("/device/510k.json", "decision_date"),
    "pma": ("/device/pma.json", "decision_date"),
    # openFDA device recalls expose event_date_* (the drug enforcement schema's
    # report_date / center_classification_date do not exist on this endpoint; the
    # normalizer below still prefers them if they ever appear).
    "device_recall": ("/device/recall.json", "event_date_posted"),
}

SOURCE_BY_KIND = {
    "510k": "openfda_device_510k",
    "pma": "openfda_device_pma",
    "device_recall": "openfda_device_recall",
}

PAGE_LIMIT = 1000
SKIP_CAP = 25_000  # openFDA refuses to skip deeper than this
MAX_SPLIT_DEPTH = 5
PAYLOAD_LIMIT = 4_000
TOP_UNMATCHED = 20

PRODUCT_CODE_MAP_PATH = CONFIG_DIR / "product_code_tracks.json"

#: Recall records are classified by the newest field that exists; device/recall currently
#: publishes event_date_posted, but the code tolerates the drug-style fields too.
RECALL_DATE_FIELDS = (
    "center_classification_date",
    "report_date",
    "event_date_posted",
    "event_date_initiated",
    "event_date_created",
)

ACCESSDATA_510K = "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID={}"
ACCESSDATA_PMA = "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?id={}"
ACCESSDATA_RECALL = "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRES/res.cfm?id={}"

#: Keys copied to the front of the truncated ``payload`` so the analysis can always read them.
PAYLOAD_PRIORITY: dict[str, tuple[str, ...]] = {
    "510k": (
        "k_number", "applicant", "decision_date", "date_received", "product_code",
        "device_name", "decision_code", "decision_description", "clearance_type",
        "advisory_committee", "advisory_committee_description", "statement_or_summary",
    ),
    "pma": (
        "pma_number", "supplement_number", "applicant", "decision_date", "date_received",
        "product_code", "generic_name", "trade_name", "decision_code", "supplement_type",
        "supplement_reason", "expedited_review_flag",
    ),
    "device_recall": (
        "recalling_firm", "product_description", "product_code", "reason_for_recall",
        "root_cause_description", "recall_status", "product_res_number", "res_event_number",
        "k_numbers", "pma_numbers", "event_date_posted", "event_date_initiated",
        "event_date_created", "event_date_terminated", "cfres_id",
    ),
}


# --------------------------------------------------------------------------- plumbing
def _sleep(seconds: float) -> None:
    """Indirection so tests can run the retry path without waiting."""
    if seconds > 0:
        time.sleep(seconds)


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _warn(warnings: list[str], message: str) -> None:
    if message not in warnings:
        warnings.append(message)


def _range_search(date_field: str, start: date, end: date) -> str:
    """openFDA range query, e.g. ``decision_date:[20241001 TO 20261031]``."""
    return f"{date_field}:[{start:%Y%m%d} TO {end:%Y%m%d}]"


def _count_params(search: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if search:
        params["search"] = search
    params["limit"] = 1
    return params


def _page_params(search: str, limit: int, skip: int) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if search:
        params["search"] = search
    params["limit"] = int(limit)
    params["skip"] = int(skip)
    return params


def _get_json(
    fetcher: Fetcher,
    endpoint: str,
    params: Mapping[str, Any],
    attempts: int = 3,
    refresh: bool = False,
) -> Any:
    """``Fetcher.get_json`` with an extra retry ring (429 / 5xx / transient network).

    ``None`` means "the endpoint says there is nothing here" (openFDA answers 404 for an
    empty result set, including its occasional deep-pagination tail quirk).
    """
    url = OPENFDA_BASE + endpoint
    last_error: HttpError | None = None
    for attempt in range(max(1, attempts)):
        try:
            return fetcher.get_json(url, dict(params), refresh=refresh)
        except NotFound:
            return None
        except BudgetExceeded:
            raise
        except HttpError as exc:
            last_error = exc
            if exc.status == 429:
                _sleep(min(30.0, 5.0 * (attempt + 1)))
            else:
                _sleep(min(10.0, 1.5 * (attempt + 1)))
    assert last_error is not None
    raise last_error


def _probe_total(fetcher: Fetcher, endpoint: str, search: str, probes: int = 2) -> int:
    """openFDA (Elasticsearch) occasionally answers a *partial* shard result: HTTP 200 with
    a ``total`` about half the real size. Probe twice, bypassing the cache both times (a
    partial answer must never be replayed), and take the largest value: a dataset never
    shrinks, so ``max`` is the safe estimator.
    """
    total = 0
    for attempt in range(max(1, probes)):
        try:
            payload = _get_json(fetcher, endpoint, _count_params(search), refresh=True)
        except HttpError:
            continue
        total = max(total, _total_of(payload))
        if attempt + 1 < probes:
            _sleep(0.5)
    return total


def _get_results(
    fetcher: Fetcher,
    endpoint: str,
    params: Mapping[str, Any],
    *,
    expected: int,
    hard_stop: int,
    skip: int,
    warnings: list[str],
    attempts: int = 2,
) -> list[dict[str, Any]]:
    """Fetch one page and retry short (partial-shard) answers with a cache refresh."""
    best: list[dict[str, Any]] = []
    for attempt in range(max(1, attempts)):
        try:
            payload = _get_json(fetcher, endpoint, params, attempts=1, refresh=attempt > 0)
        except NotFound:
            # 404 can be a transient answer while openFDA is shedding load; retry
            # once with a cache refresh before treating the page as truly empty.
            if attempt + 1 < max(1, attempts):
                _sleep(0.5)
                continue
            return best
        if payload is None:
            return best
        results = payload.get("results") or []
        if len(results) > len(best):
            best = results
        if len(results) >= expected or skip + len(results) >= hard_stop:
            return best
        _warn(
            warnings,
            f"{endpoint}: short page at skip={skip} ({len(results)}/{expected}); retrying",
        )
    return best


def _total_of(payload: Any) -> int:
    meta = (payload or {}).get("meta") or {}
    results = meta.get("results") or {}
    try:
        return int(results.get("total") or 0)
    except (TypeError, ValueError):
        return 0


def _split_window(
    fetcher: Fetcher,
    endpoint: str,
    date_field: str,
    start: date,
    end: date,
    cap: int,
    warnings: list[str],
    depth: int,
    windows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    midpoint = start + (end - start) // 2
    _warn(
        warnings,
        f"{endpoint}: splitting {iso(start)}..{iso(end)} at {iso(midpoint)} (depth {depth + 1})",
    )
    left = _fetch_window(fetcher, endpoint, date_field, start, midpoint, cap, warnings, depth + 1, windows)
    remaining = max(0, cap - len(left)) if cap else 0
    if cap and remaining <= 0:
        return left
    right = _fetch_window(
        fetcher,
        endpoint,
        date_field,
        midpoint + timedelta(days=1),
        end,
        remaining,
        warnings,
        depth + 1,
        windows,
    )
    return left + right


def _short_error(exc: HttpError) -> str:
    return f"HTTP {exc.status}" if exc.status else "HTTP error"


# ------------------------------------------------------------------- windowed fetching
def _fetch_window(
    fetcher: Fetcher,
    endpoint: str,
    date_field: str,
    start: date,
    end: date,
    cap: int,
    warnings: list[str],
    depth: int = 0,
    windows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Collect every record whose ``date_field`` falls inside ``[start, end]``.

    ``cap = 0`` means "no cap". Windows larger than openFDA's 25,000-record skip ceiling
    are split in half; a window that keeps failing mid-pagination is split as well.
    Every leaf window actually requested is appended to ``windows`` for the run stats.
    """
    search = _range_search(date_field, start, end)
    total = _probe_total(fetcher, endpoint, search)
    if total <= 0:
        return []
    if total > SKIP_CAP and depth < MAX_SPLIT_DEPTH and (end - start).days > 62:
        return _split_window(fetcher, endpoint, date_field, start, end, cap, warnings, depth, windows)

    entry: dict[str, Any] = {"start": iso(start), "end": iso(end), "total": total, "fetched": 0}
    if windows is not None:
        windows.append(entry)
    records: list[dict[str, Any]] = []
    skip = 0
    hard_stop = min(total, SKIP_CAP)
    while skip < hard_stop:
        page_limit = min(PAGE_LIMIT, hard_stop - skip)
        if cap:
            page_limit = min(page_limit, cap - len(records))
            if page_limit <= 0:
                break
        try:
            results = _get_results(
                fetcher,
                endpoint,
                _page_params(search, page_limit, skip),
                expected=page_limit,
                hard_stop=hard_stop,
                skip=skip,
                warnings=warnings,
            )
        except HttpError as exc:
            if depth < MAX_SPLIT_DEPTH and (end - start).days > 62:
                _warn(warnings, f"{endpoint} {search}: page skip={skip} failed ({_short_error(exc)}); splitting window")
                entry["split"] = True
                return _split_window(fetcher, endpoint, date_field, start, end, cap, warnings, depth, windows)
            _warn(warnings, f"{endpoint} {search}: page skip={skip} failed ({_short_error(exc)}); partial window")
            entry["error"] = _short_error(exc)
            break
        if not results:
            # openFDA sometimes answers 404 on a deep page while ``total`` still
            # claims more rows (transient shard / rate-limit behaviour). Accepting
            # the truncation silently would drop half the records and bias every
            # rate in the report, so split the window and re-fetch in halves.
            if depth < MAX_SPLIT_DEPTH and (end - start).days > 62:
                _warn(
                    warnings,
                    f"{endpoint} {search}: empty page at skip={skip} of {total}; splitting window",
                )
                entry["split"] = True
                return _split_window(
                    fetcher, endpoint, date_field, start, end, cap, warnings, depth, windows
                )
            _warn(warnings, f"{endpoint} {search}: no data at skip={skip} (tail quirk)")
            break
        records.extend(results)
        skip += len(results)
        if len(results) < page_limit:
            # Short answer after the cache-refresh retry: accept it and keep the absolute
            # skip moving so the next page stays aligned; a re-run fills any gap.
            _warn(warnings, f"{endpoint} {search}: accepted short page at skip={skip - len(results)}")
    entry["fetched"] = len(records)
    if skip < total and skip >= SKIP_CAP:
        _warn(warnings, f"{endpoint} {search}: truncated at skip cap ({skip}/{total})")
    return records


def _fetch_classification(fetcher: Fetcher, warnings: list[str]) -> list[dict[str, Any]]:
    """Pull the whole product-code dictionary (deduplicated by product_code).

    Self-healing: if openFDA answers a partial shard result first (``total`` ≈ half the
    real size) the loop re-probes ``total`` and keeps paging instead of stopping early.
    """
    total = _probe_total(fetcher, CLASSIFICATION_ENDPOINT, "")
    if total <= 0:
        _warn(warnings, "device/classification returned zero product codes")
        return []

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    skip = 0
    refreshes = 0
    while True:
        hard_stop = min(total, SKIP_CAP)
        if skip >= hard_stop:
            if refreshes < 2:
                refreshed = _probe_total(fetcher, CLASSIFICATION_ENDPOINT, "")
                refreshes += 1
                if refreshed > total and skip < min(refreshed, SKIP_CAP):
                    _warn(warnings, f"device/classification total grew {total} -> {refreshed}; continuing")
                    total = refreshed
                    continue
            break
        page_limit = min(PAGE_LIMIT, hard_stop - skip)
        try:
            results = _get_results(
                fetcher,
                CLASSIFICATION_ENDPOINT,
                _page_params("", page_limit, skip),
                expected=page_limit,
                hard_stop=hard_stop,
                skip=skip,
                warnings=warnings,
            )
        except HttpError as exc:
            _warn(warnings, f"device/classification page skip={skip} failed ({_short_error(exc)}); partial dictionary")
            break
        if not results:
            if refreshes < 2:
                refreshed = _probe_total(fetcher, CLASSIFICATION_ENDPOINT, "")
                refreshes += 1
                if refreshed > total and skip < min(refreshed, SKIP_CAP):
                    _warn(warnings, f"device/classification total grew {total} -> {refreshed}; continuing")
                    total = refreshed
                    continue
            _warn(warnings, f"device/classification tail unavailable at skip={skip}; partial dictionary")
            break
        for record in results:
            code = _clean(record.get("product_code"))
            if code and code not in seen:
                seen.add(code)
                records.append(record)
        skip += len(results)
    if len(records) < min(total, SKIP_CAP):
        _warn(warnings, f"device/classification partial: {len(records)}/{min(total, SKIP_CAP)} codes")
    return records


# ------------------------------------------------------------- product-code → track map
def _keyword_index(registry: Any) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for track in registry.all():
        for keyword in track.get("keywords") or []:
            normalized = norm_text(keyword)
            if normalized:
                pairs.append((normalized, track["id"]))
    # Longest keyword first: "IMPLANTABLE CARDIOVERTER" must beat "DEFIBRILLATOR".
    pairs.sort(key=lambda pair: (len(pair[0]), pair[0]), reverse=True)
    return pairs


def _stem_tokens(text: str) -> set[str]:
    """Normalized tokens plus naive singular forms (``STENTS`` → ``STENT``)."""
    out: set[str] = set()
    for token in tokens(text):
        out.add(token)
        if token.endswith("IES") and len(token) > 4:
            out.add(token[:-3] + "Y")
        elif token.endswith("ES") and len(token) > 4:
            out.add(token[:-2])
        elif token.endswith("S") and len(token) > 3:
            out.add(token[:-1])
    return out


def _match_candidates(
    keyword_index: list[tuple[str, str]], text: str
) -> tuple[list[tuple[int, str, str]], str]:
    """All keyword hits in ``text`` as ``(keyword_length, keyword, track_id)``."""
    if not text or not text.strip():
        return [], ""
    haystack = f" {norm_text(text)} "
    hits = [(len(keyword), keyword, track_id) for keyword, track_id in keyword_index if f" {keyword} " in haystack]
    if hits:
        return hits, "keyword"
    stemmed = _stem_tokens(text)
    if not stemmed:
        return [], ""
    token_hits = [
        (len(keyword), keyword, track_id)
        for keyword, track_id in keyword_index
        if len(keyword.split(" ")) > 1 and all(part in stemmed for part in keyword.split(" "))
    ]
    return token_hits, "token_set"


def _pick_unique_longest(hits: list[tuple[int, str, str]]) -> str | None:
    """Longest keyword wins; a tie between two different tracks is ambiguous → ``None``.

    "宁缺毋滥": a code that could belong to two tracks is left unmapped instead of being
    silently assigned to whichever keyword happened to be listed first.
    """
    if not hits:
        return None
    ordered = sorted(hits, key=lambda hit: (hit[0], hit[1]), reverse=True)
    best = ordered[0]
    for other in ordered[1:]:
        if other[0] == best[0] and other[2] != best[2]:
            return None
    return best[2]


#: Manual corrections applied to the normalized ``device_name`` before the keyword matcher.
#: Each entry is ``((marker, ...), track_id)`` and fires when every marker appears as a
#: whole-word substring of the device name. Keep this list tiny and evidence based: it is
#: only for families where the generic keyword rules are demonstrably wrong, and
#: ``config/product_code_tracks.json`` remains the place for per-code hand corrections.
MANUAL_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    # Software/SaMD primitives: these product codes describe code, not a physical modality,
    # so they must not be attributed to the hardware track their description happens to
    # mention (e.g. "System, Image Processing, Software").
    (("SOFTWARE", "IMAGE PROCESSING"), "medical_ai"),
    (("SOFTWARE", "RADIATION THERAPY"), "medical_ai"),
    (("SOFTWARE", "COMPUTED TOMOGRAPHY"), "medical_ai"),
    (("SOFTWARE", "MAGNETIC RESONANCE"), "medical_ai"),
    (("SOFTWARE", "ULTRASOUND"), "medical_ai"),
    (("SOFTWARE", "MONITOR"), "medical_ai"),
    (("COMPUTER ASSISTED", "SOFTWARE"), "medical_ai"),
    (("COMPUTER", "DIAGNOSTIC", "PROGRAMMABLE"), "medical_ai"),
    # Orthopedic implant codes whose name only carries the joint, no "PROSTHESIS" keyword.
    (("HIP", "FEMORAL STEM"), "ortho_joint"),
    (("KNEE", "FEMORAL COMPONENT"), "ortho_joint"),
    (("ENDOSSEOUS", "ROOT FORM"), "dental"),
    # Cardiac valve / heart-failure families whose openFDA name omits the track keyword.
    (("HEART VALVE",), "structural_heart"),
    (("AORTIC VALVE",), "structural_heart"),
    (("HEMODYNAMIC", "IMPLANTABLE"), "heart_failure"),
    (("CARDIAC CATHETERIZATION"), "coronary"),
    # Vascular / neurovascular plain-language names.
    (("SUPERFICIAL FEMORAL"), "peripheral_vascular"),
    (("CAROTID", "STENT"), "neurovascular"),
    (("HEMOSTASIS", "VASCULAR"), "peripheral_vascular"),
    # Imaging primitives that never spell "ULTRASOUND".
    (("DOPPLER", "ULTRASONIC"), "imaging_us"),
    (("TRANSDUCER", "ULTRASONIC"), "imaging_us"),
    # Neurostimulation families described by indication instead of device class.
    (("STIMULATOR", "PARKINSONIAN"), "neurostimulation"),
)


def _manual_track(device_name: str) -> str | None:
    normalized = f" {norm_text(device_name)} "
    if not normalized.strip():
        return None
    for markers, track_id in MANUAL_RULES:
        if all(f" {marker} " in normalized for marker in markers):
            return track_id
    return None



def _match_track_staged(keyword_index: list[tuple[str, str]], device_name: str, definition: str) -> tuple[str | None, str]:
    """Staged ``device_name`` → ``definition`` match with a unique-longest tie-break."""
    hits, method = _match_candidates(keyword_index, device_name)
    if hits:
        return _pick_unique_longest(hits), f"device_name_{method}"
    hits, method = _match_candidates(keyword_index, definition)
    if hits:
        return _pick_unique_longest(hits), f"definition_{method}"
    return None, ""


def _match_track(registry: Any, keyword_index: list[tuple[str, str]], text: str) -> tuple[str | None, str]:
    """Deterministic single-field ``text -> track_id`` (event fallback)."""
    hits, method = _match_candidates(keyword_index, text)
    return _pick_unique_longest(hits), method


def build_product_code_map(
    classification: Iterable[Mapping[str, Any]],
    registry: Any,
    existing: Mapping[str, Any] | None = None,
) -> tuple[dict[str, str], dict[str, int]]:
    """Map every classification record to a track; returns ``(code -> track_id, stats)``.

    Mapping order: hand-curated ``existing`` overlay (valid track ids) > manual rules >
    staged ``device_name`` → ``definition`` keyword match. ``existing`` wins so corrections
    typed into ``config/product_code_tracks.json`` survive a re-collection.
    """
    keyword_index = _keyword_index(registry)
    valid_tracks = set(registry.ids())
    mapping: dict[str, str] = {}
    stats: Counter[str] = Counter()
    for record in classification:
        code = _clean(record.get("product_code"))
        if not code or code in mapping:
            continue
        device_name = _clean(record.get("device_name"))
        track_id = _manual_track(device_name)
        if track_id:
            mapping[code] = track_id
            stats["manual"] += 1
            continue
        track_id, how = _match_track_staged(keyword_index, device_name, _clean(record.get("definition")))
        if track_id:
            mapping[code] = track_id
            stats[how] += 1
    for code, track_id in (existing or {}).items():
        code, track_id = _clean(code), _clean(track_id)
        if not code or track_id not in valid_tracks:
            continue
        auto = mapping.get(code)
        if auto is None:
            mapping[code] = track_id
            stats["existing_new"] += 1
        elif auto != track_id:
            mapping[code] = track_id
            stats["existing_override"] += 1
    return mapping, dict(stats)


def _write_product_code_map(mapping: Mapping[str, str], path: str | Path) -> None:
    """Write the map as compact, code-sorted JSON."""
    ordered = {code: mapping[code] for code in sorted(mapping)}
    write_text(path, json.dumps(ordered, ensure_ascii=False, separators=(",", ":")) + "\n")


def _product_code_row(record: Mapping[str, Any], code_map: Mapping[str, str]) -> dict[str, Any]:
    code = _clean(record.get("product_code"))
    return {
        "product_code": code,
        "track_id": code_map.get(code),
        "device_name": truncate(_clean(record.get("device_name")), 400),
        "definition": truncate(_clean(record.get("definition")), 4000),
        "specialty": _clean(record.get("medical_specialty_description")),
        "regulation_number": _clean(record.get("regulation_number")),
    }


# ----------------------------------------------------------------------- normalisation
def _payload(record: Mapping[str, Any], priority: tuple[str, ...] = ()) -> str:
    """Raw record as JSON, truncated; ``priority`` keys are emitted first so they survive.

    openFDA records carry a few very large fields (``openfda.registration_number``,
    ``code_info``) that can push the interesting keys past the 4,000-character cut, so the
    keys the analysis actually reads are moved to the front before truncation.

    The truncation must yield **valid JSON**: the analysis layer parses this payload, and a
    torn string used to silently disable recall deduplication and field extraction. When the
    full record does not fit we shrink values and then stop adding keys, rather than cutting
    the text mid-string.
    """
    ordered: dict[str, Any] = {key: record[key] for key in priority if key in record}
    for key, value in record.items():
        if key not in ordered:
            ordered[key] = value
    try:
        text = json.dumps(ordered, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = json.dumps({str(k): str(v) for k, v in ordered.items()}, ensure_ascii=False)
    if len(text) <= PAYLOAD_LIMIT:
        return text

    def shrink(value: Any) -> Any:
        if isinstance(value, str):
            return truncate(value, 300)
        if isinstance(value, (list, tuple)):
            return [shrink(item) for item in list(value)[:20]]
        if isinstance(value, dict):
            return {str(key): shrink(item) for key, item in list(value.items())[:20]}
        return value

    compact: dict[str, Any] = {}
    for key, value in ordered.items():
        candidate = dict(compact)
        candidate[key] = shrink(value)
        if len(json.dumps(candidate, ensure_ascii=False, default=str)) > PAYLOAD_LIMIT:
            break
        compact = candidate
    return json.dumps(compact, ensure_ascii=False, default=str)


def _base_event(
    kind: str,
    event_id: str,
    *,
    event_date: date | None,
    as_of: str,
    company_key: str | None,
    applicant_raw: str,
    country: str = "US",
    track_id: str | None,
    product_code: str | None,
    title: str,
    summary: str,
    url: str,
    payload: str,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "source": SOURCE_BY_KIND[kind],
        "kind": kind,
        "event_date": iso(event_date) if event_date else "",
        "as_of": as_of,
        "company_key": company_key or None,
        "applicant_raw": applicant_raw,
        "country": (country or "US").upper(),
        "track_id": track_id or None,
        "product_code": product_code or None,
        "title": truncate(title, 400),
        "summary": truncate(summary, 1200),
        "url": url,
        "payload": payload,
    }


def _summary_bits(*bits: Any) -> str:
    return "｜".join(str(bit).strip() for bit in bits if bit is not None and str(bit).strip())


def normalize_510k(
    record: Mapping[str, Any],
    *,
    company_key: str | None,
    track_id: str | None,
    track_zh: str = "未分类",
    as_of: str = "",
) -> dict[str, Any] | None:
    """Turn one ``device/510k`` record into an event row (``None`` when unusable)."""
    k_number = _clean(record.get("k_number"))
    if not k_number:
        return None
    applicant = _clean(record.get("applicant"))
    product_code = _clean(record.get("product_code")) or None
    device_name = _clean(record.get("device_name"))
    decision_date = parse_date(record.get("decision_date"))
    event_date = decision_date or parse_date(record.get("date_received"))
    clearance = _clean(record.get("clearance_type"))
    decision_code = _clean(record.get("decision_code"))
    decision_description = _clean(record.get("decision_description"))
    advisory = _clean(record.get("advisory_committee_description")) or _clean(record.get("advisory_committee"))
    title = f"{applicant or '未知申请人'} 510(k)：{device_name or k_number}"
    summary = _summary_bits(
        track_zh,
        f"产品码 {product_code}" if product_code else "",
        clearance,
        f"决策 {decision_code} {decision_description}".strip() if decision_code or decision_description else "",
        advisory,
    )
    return _base_event(
        "510k",
        make_event_id(SOURCE_BY_KIND["510k"], "510k", k_number),
        event_date=event_date,
        as_of=as_of,
        company_key=company_key,
        applicant_raw=applicant,
        country=_clean(record.get("country_code")) or "US",
        track_id=track_id,
        product_code=product_code,
        title=title,
        summary=summary,
        url=ACCESSDATA_510K.format(k_number),
        payload=_payload(record, PAYLOAD_PRIORITY["510k"]),
    )


def normalize_pma(
    record: Mapping[str, Any],
    *,
    company_key: str | None,
    track_id: str | None,
    track_zh: str = "未分类",
    as_of: str = "",
) -> dict[str, Any] | None:
    """Turn one ``device/pma`` record (original or supplement) into an event row."""
    pma_number = _clean(record.get("pma_number"))
    if not pma_number:
        return None
    supplement = _clean(record.get("supplement_number"))
    applicant = _clean(record.get("applicant"))
    product_code = _clean(record.get("product_code")) or None
    trade_name = _clean(record.get("trade_name"))
    generic_name = _clean(record.get("generic_name"))
    decision_code = _clean(record.get("decision_code"))
    supplement_type = _clean(record.get("supplement_type"))
    supplement_reason = _clean(record.get("supplement_reason"))
    expedited = _clean(record.get("expedited_review_flag"))
    event_date = parse_date(record.get("decision_date")) or parse_date(record.get("date_received"))
    label = trade_name or generic_name or pma_number
    if supplement:
        title = f"{applicant or '未知申请人'} PMA 补充 {pma_number}/{supplement}：{label}"
    else:
        title = f"{applicant or '未知申请人'} PMA 批准 {pma_number}：{label}"
    summary = _summary_bits(
        track_zh,
        f"PMA {pma_number}" + (f" 补充 {supplement}" if supplement else ""),
        f"产品码 {product_code}" if product_code else "",
        supplement_type or supplement_reason,
        f"决策 {decision_code}" if decision_code else "",
        "加急" if expedited.upper() in {"Y", "YES"} else "",
    )
    return _base_event(
        "pma",
        make_event_id(SOURCE_BY_KIND["pma"], "pma", pma_number, supplement),
        event_date=event_date,
        as_of=as_of,
        company_key=company_key,
        applicant_raw=applicant,
        track_id=track_id,
        product_code=product_code,
        title=title,
        summary=summary,
        url=ACCESSDATA_PMA.format(pma_number),
        payload=_payload(record, PAYLOAD_PRIORITY["pma"]),
    )


def recall_event_date(record: Mapping[str, Any]) -> date | None:
    """Earliest relevant recall date; tolerates both the real and the documented schema."""
    for field in RECALL_DATE_FIELDS:
        parsed = parse_date(record.get(field))
        if parsed:
            return parsed
    return None


def normalize_recall(
    record: Mapping[str, Any],
    *,
    company_key: str | None,
    track_id: str | None,
    track_zh: str = "未分类",
    as_of: str = "",
) -> dict[str, Any] | None:
    """Turn one ``device/recall`` record into a ``device_recall`` event row."""
    identity = _clean(record.get("cfres_id")) or _clean(record.get("product_res_number")) or _clean(record.get("res_event_number"))
    if not identity:
        return None
    firm = _clean(record.get("recalling_firm"))
    product_code = _clean(record.get("product_code")) or None
    product_description = _clean(record.get("product_description"))
    reason = _clean(record.get("reason_for_recall"))
    recall_status = _clean(record.get("recall_status"))
    classification = _clean(record.get("classification")) or recall_status
    root_cause = _clean(record.get("root_cause_description"))
    event_date = recall_event_date(record)
    res_event_number = _clean(record.get("res_event_number"))
    title = f"{firm or '未知厂商'} 召回：{truncate(product_description, 90)}"
    summary = _summary_bits(
        track_zh,
        f"严重度/状态 {classification}" if classification else "",
        f"根因 {truncate(root_cause, 120)}" if root_cause else "",
        f"原因 {truncate(reason, 240)}" if reason else "",
        f"产品码 {product_code}" if product_code else "",
    )
    url = ACCESSDATA_RECALL.format(res_event_number) if res_event_number else ""
    return _base_event(
        "device_recall",
        make_event_id(SOURCE_BY_KIND["device_recall"], "device_recall", identity),
        event_date=event_date,
        as_of=as_of,
        company_key=company_key,
        applicant_raw=firm,
        country=_clean(record.get("country")) or "US",
        track_id=track_id,
        product_code=product_code,
        title=title,
        summary=summary,
        url=url,
        payload=_payload(record, PAYLOAD_PRIORITY["device_recall"]),
    )


_NORMALIZERS = {
    "510k": normalize_510k,
    "pma": normalize_pma,
    "device_recall": normalize_recall,
}


def _track_text(kind: str, record: Mapping[str, Any]) -> str:
    if kind == "510k":
        return _clean(record.get("device_name"))
    if kind == "pma":
        return " ".join(filter(None, [_clean(record.get("generic_name")), _clean(record.get("trade_name"))]))
    return " ".join(filter(None, [_clean(record.get("product_description")), _clean(record.get("reason_for_recall"))]))


def _event_track(
    kind: str,
    record: Mapping[str, Any],
    code_map: Mapping[str, str],
    registry: Any,
    keyword_index: list[tuple[str, str]],
) -> tuple[str | None, str]:
    code = _clean(record.get("product_code"))
    if code and code in code_map:
        return code_map[code], "product_code"
    track_id, how = _match_track(registry, keyword_index, _track_text(kind, record))
    return track_id, how


# ------------------------------------------------------------------------------ public
def collect(
    db: DB,
    fetcher: Fetcher,
    months: int = 120,
    limit: int = 0,
    code_map_path: str | Path | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Collect openFDA device data into ``db``; returns a JSON-serialisable stats dict.

    ``months`` is the history window (0/negative is clamped to one year, matching the
    default backfill), ``limit`` caps records per kind (0 = no cap). ``code_map_path`` and
    ``today`` are injection points for offline tests only.
    """
    end = today or today_utc()
    start = add_months(end, -max(1, int(months or 1)))
    as_of = iso(end)
    warnings: list[str] = []

    company_registry = load_companies("device")
    track_registry = load_tracks("device")
    db.upsert_companies(company_registry.all())
    db.upsert_tracks(track_registry.all())

    map_path = Path(code_map_path) if code_map_path else PRODUCT_CODE_MAP_PATH
    existing_map = read_json(map_path, {})
    if not isinstance(existing_map, dict):
        existing_map = {}

    # 1) product-code dictionary --------------------------------------------------
    try:
        classification = _fetch_classification(fetcher, warnings)
    except BudgetExceeded as exc:
        _warn(warnings, f"classification: request budget exhausted ({exc}); partial run")
        classification = []
    code_map, map_stats = build_product_code_map(classification, track_registry, existing_map)
    if classification:
        _write_product_code_map(code_map, map_path)
        db.upsert_product_codes([_product_code_row(record, code_map) for record in classification])
    elif code_map:
        _warn(warnings, f"classification unavailable; reusing {len(code_map)} codes from {map_path}")

    # 2) device events ------------------------------------------------------------
    keyword_index = _keyword_index(track_registry)
    events_by_kind: dict[str, list[dict[str, Any]]] = {}
    windows_by_kind: dict[str, list[dict[str, Any]]] = {}
    missing_event_date = 0
    budget_hit = False
    cap = max(0, int(limit or 0))

    for kind, (endpoint, date_field) in DEVICE_ENDPOINTS.items():
        windows_by_kind[kind] = []
        if budget_hit:
            events_by_kind[kind] = []
            continue
        try:
            records = _fetch_window(
                fetcher, endpoint, date_field, start, end, cap, warnings, windows=windows_by_kind[kind]
            )
        except BudgetExceeded as exc:
            _warn(warnings, f"{kind}: request budget exhausted ({exc}); partial run")
            budget_hit = True
            records = []

        by_id: dict[str, dict[str, Any]] = {}
        for record in records:
            applicant = _clean(record.get("applicant")) or _clean(record.get("recalling_firm"))
            company_key = company_registry.resolve(applicant)[0]
            track_id, _ = _event_track(kind, record, code_map, track_registry, keyword_index)
            event = _NORMALIZERS[kind](
                record,
                company_key=company_key,
                track_id=track_id,
                track_zh=track_registry.name_zh(track_id),
                as_of=as_of,
            )
            if event is None:
                continue
            if not event["event_date"]:
                missing_event_date += 1
            by_id[event["event_id"]] = event
        events = list(by_id.values())
        if events:
            db.upsert_events(events)
        events_by_kind[kind] = events

    # 3) stats --------------------------------------------------------------------
    all_events = [event for events in events_by_kind.values() for event in events]
    total = len(all_events)
    matched = sum(1 for event in all_events if event.get("company_key"))
    major_keys = set(company_registry.major_keys())
    major_matched = sum(1 for event in all_events if event.get("company_key") in major_keys)
    track_matched = sum(1 for event in all_events if event.get("track_id"))

    per_kind: dict[str, int] = {}
    per_kind_match: dict[str, dict[str, Any]] = {}
    per_kind_track: dict[str, float] = {}
    for kind, events in events_by_kind.items():
        per_kind[kind] = len(events)
        kind_matched = sum(1 for event in events if event.get("company_key"))
        kind_track = sum(1 for event in events if event.get("track_id"))
        per_kind_match[kind] = {
            "total": len(events),
            "matched": kind_matched,
            "match_rate": round(kind_matched / len(events), 4) if events else 0.0,
        }
        per_kind_track[kind] = round(kind_track / len(events), 4) if events else 0.0

    unmatched_counter: Counter[str] = Counter()
    unmatched_display: dict[str, str] = {}
    for event in all_events:
        if event.get("company_key"):
            continue
        raw = _clean(event.get("applicant_raw"))
        if not raw:
            continue
        key = norm_text(raw)
        unmatched_counter[key] += 1
        unmatched_display.setdefault(key, raw)
    top_unmatched = [
        {"applicant": unmatched_display[key], "count": count}
        for key, count in unmatched_counter.most_common(TOP_UNMATCHED)
    ]

    classified_codes = {_clean(record.get("product_code")) for record in classification}
    classified_codes.discard("")
    mapped_codes = sum(1 for code in classified_codes if code in code_map)
    unmapped_codes = len(classified_codes) - mapped_codes

    # Which unmapped product codes actually show up in events? Ranked by event volume so
    # the keyword dictionary can be extended where it matters.
    code_names = {
        _clean(record.get("product_code")): _clean(record.get("device_name"))
        for record in classification
        if _clean(record.get("product_code"))
    }
    unmapped_event_codes: Counter[str] = Counter()
    for event in all_events:
        code = _clean(event.get("product_code"))
        if code and code not in code_map:
            unmapped_event_codes[code] += 1
    top_unmapped_codes = [
        {"product_code": code, "device_name": code_names.get(code, ""), "events": count}
        for code, count in unmapped_event_codes.most_common(TOP_UNMATCHED)
    ]

    return {
        "window": {"start": iso(start), "end": iso(end), "months": max(1, int(months or 1))},
        "per_kind": per_kind,
        "per_kind_match": per_kind_match,
        "per_kind_track_match": per_kind_track,
        "events_total": total,
        "matched": matched,
        "unmatched": total - matched,
        "match_rate": round(matched / total, 4) if total else 0.0,
        "major_matched": major_matched,
        "major_match_rate": round(major_matched / total, 4) if total else 0.0,
        "track_matched": track_matched,
        "track_match_rate": round(track_matched / total, 4) if total else 0.0,
        "top_unmatched": top_unmatched,
        "unmapped_codes": unmapped_codes,
        "top_unmapped_codes": top_unmapped_codes,
        "missing_event_date": missing_event_date,
        "product_codes": {
            "classification_records": len(classification),
            "codes": len(classified_codes),
            "mapped_codes": mapped_codes,
            "unmapped_codes": unmapped_codes,
            "mapped_rate": round(mapped_codes / len(classified_codes), 4) if classified_codes else 0.0,
            "match_methods": map_stats,
            "file": str(map_path),
        },
        "windows": windows_by_kind,
        "requests": int(fetcher.stats.get("requests", 0)),
        "cache_hits": int(fetcher.stats.get("cache_hits", 0)),
        "warnings": warnings,
    }
