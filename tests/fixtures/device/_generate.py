"""Regenerate the deterministic openFDA fixtures used by ``tests/test_device.py``.

This script never touches the network: it writes synthetic but schema-accurate openFDA
responses named by the :class:`medradar.http.Fetcher` cache key (``sha1(url)[:24].json``),
so the collector's real pagination/normalisation path can be exercised fully offline.

    python tests/fixtures/device/_generate.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medradar import collect_device as cd  # noqa: E402
from medradar.config import load_tracks  # noqa: E402
from medradar.http import Fetcher  # noqa: E402
from medradar.util import add_months  # noqa: E402

#: Must match ``tests/test_device.FIXTURE_DAY``.
FIXTURE_DAY = date(2026, 10, 30)


CLASSIFICATION = [
    {
        "product_code": "OAD",
        "device_name": "Pulsed Field Ablation System",
        "definition": "Cardiac ablation system using pulsed field energy.",
        "medical_specialty_description": "Cardiovascular",
        "regulation_number": "870.5550",
    },
    {
        "product_code": "GEX",
        "device_name": "Dental Implant System",
        "definition": "Endosseous dental implant and accessories.",
        "medical_specialty_description": "Dental",
        "regulation_number": "872.3640",
    },
    {
        "product_code": "DHT",
        "device_name": "Transcatheter Mitral Valve Repair System",
        "definition": "Mitral valve repair device.",
        "medical_specialty_description": "Cardiovascular",
        "regulation_number": "870.3310",
    },
    {
        "product_code": "QQQ",
        "device_name": "Pierced Ear Cleaning Tray",
        "definition": "Cleaning tray for pierced ears.",
        "medical_specialty_description": "General Hospital",
        "regulation_number": "880.0000",
    },
]

DEVICE_510K = [
    {
        "k_number": "K250001",
        "applicant": "MEDTRONIC MINIMED",
        "device_name": "Pulsed Field Ablation Catheter",
        "product_code": "OAD",
        "decision_date": "2025-03-14",
        "date_received": "2025-01-02",
        "decision_code": "SESE",
        "decision_description": "Substantially Equivalent",
        "clearance_type": "Traditional",
        "advisory_committee": "CV",
        "advisory_committee_description": "Cardiovascular",
        "country_code": "US",
        # Big nested field: the payload priority list must keep k_number readable.
        "openfda": {"registration_number": [f"30000{i:05d}" for i in range(300)]},
    },
    {
        "k_number": "K250002",
        "applicant": "Acme Widgets LLC",
        "device_name": "Dental Implant Kit",
        "product_code": "GEX",
        "decision_date": "2025-04-01",
        "date_received": "2025-02-01",
        "decision_code": "SESE",
        "decision_description": "Substantially Equivalent",
        "clearance_type": "Traditional",
        "advisory_committee": "DE",
        "advisory_committee_description": "Dental",
        "country_code": "US",
    },
    {
        "k_number": "K250003",
        "applicant": "Abbott Laboratories",
        "device_name": "Pierced Ear Cleaning Tray",
        "product_code": "QQQ",
        "decision_date": "2025-05-20",
        "date_received": "2025-03-20",
        "decision_code": "SESE",
        "decision_description": "Substantially Equivalent",
        "clearance_type": "Traditional",
        "advisory_committee": "SU",
        "advisory_committee_description": "General, Plastic Surgery",
        "country_code": "US",
    },
]

DEVICE_PMA = [
    {
        "pma_number": "P250001",
        "supplement_number": "",
        "applicant": "Edwards Lifesciences",
        "product_code": "DHT",
        "generic_name": "Mitral Valve Repair System",
        "trade_name": "Test Valve",
        "decision_date": "2025-06-11",
        "date_received": "2024-12-01",
        "decision_code": "APPR",
        "supplement_type": "",
        "supplement_reason": "",
        "expedited_review_flag": "N",
    },
    {
        "pma_number": "P250001",
        "supplement_number": "S001",
        "applicant": "Edwards Lifesciences",
        "product_code": "DHT",
        "generic_name": "Mitral Valve Repair System",
        "trade_name": "Test Valve",
        "decision_date": "2025-07-09",
        "date_received": "2025-01-15",
        "decision_code": "APPR",
        "supplement_type": "Real-Time Process",
        "supplement_reason": "Manufacturing change",
        "expedited_review_flag": "N",
    },
]

DEVICE_RECALL = [
    {
        # Documented (drug-enforcement style) classification date beats event_date_posted.
        "cfres_id": "99001",
        "recalling_firm": "PHILIPS MEDICAL SYSTEMS",
        "product_code": "QQQ",
        "product_description": "Ultrasound system software failure",
        "reason_for_recall": "Software issue causing unexpected reboot",
        "root_cause_description": "Software",
        "recall_status": "Terminated",
        "product_res_number": "Z-0001-2025",
        "res_event_number": "95001",
        "k_numbers": ["K240001"],
        "center_classification_date": "2025-02-05",
        "event_date_posted": "2025-02-10",
        "event_date_initiated": "2025-01-20",
    },
    {
        # Real device/recall schema: only event_date_* fields exist.
        "cfres_id": "99002",
        "recalling_firm": "Unknown Devices Inc",
        "product_code": "OAD",
        "product_description": "Catheter breakage",
        "reason_for_recall": "Shaft breakage",
        "root_cause_description": "Device design",
        "recall_status": "Open, Classified",
        "product_res_number": "Z-0002-2025",
        "res_event_number": "95002",
        "event_date_posted": "2025-08-01",
        "event_date_initiated": "2025-07-15",
    },
]


def _write(endpoint: str, params: dict, records: list[dict], total: int | None = None) -> Path:
    count = len(records) if total is None else total
    payload = {
        "meta": {"results": {"skip": params.get("skip", 0), "limit": params.get("limit"), "total": count}},
        "results": records,
    }
    url = Fetcher._with_params(cd.OPENFDA_BASE + endpoint, params)
    path = OUT / f"{Fetcher._key(url)}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=0), encoding="utf-8")
    return path


def _write_endpoint(endpoint: str, records: list[dict], search: str = "") -> list[Path]:
    """Mirror ``_fetch_classification`` / ``_fetch_window``: one count + one full page."""
    written = [_write(endpoint, cd._count_params(search), [], total=len(records))]
    skip = 0
    total = len(records)
    while skip < total:
        page_limit = min(cd.PAGE_LIMIT, total - skip)
        page = records[skip : skip + page_limit]
        written.append(_write(endpoint, cd._page_params(search, page_limit, skip), page))
        skip += len(page)
    return written


def main() -> int:
    window_start = add_months(FIXTURE_DAY, -24)
    window_end = FIXTURE_DAY
    for kind, (endpoint, date_field) in cd.DEVICE_ENDPOINTS.items():
        search = cd._range_search(date_field, window_start, window_end)
        records = {"510k": DEVICE_510K, "pma": DEVICE_PMA, "device_recall": DEVICE_RECALL}[kind]
        _write_endpoint(endpoint, records, search)
        # ``--limit 1`` variant: the collector caps the first page to the limit.
        _write(endpoint, cd._page_params(search, 1, 0), records[:1], total=len(records))
    _write_endpoint(cd.CLASSIFICATION_ENDPOINT, CLASSIFICATION)

    # Sanity: the fixture records must map to the tracks the tests assert.
    registry = load_tracks("device")
    mapping, stats = cd.build_product_code_map(CLASSIFICATION, registry)
    expected = {"OAD": "ep_pfa", "GEX": "dental", "DHT": "structural_heart"}
    if mapping != expected:
        raise SystemExit(f"fixture mapping drifted: {mapping!r} (stats={stats!r})")
    print(f"wrote {len(list(OUT.glob('*.json')))} fixtures to {OUT}")
    print(f"product-code mapping: {mapping}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
