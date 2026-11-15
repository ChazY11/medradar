"""Shared fixtures for the MedRadar product tests.

The tests run against the committed snapshot in data/product/ (the same data the product
serves), so they verify the real measurement path rather than a mock. If the snapshot is
absent the data-dependent tests skip with an explicit message instead of failing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "medradar" / "product" / "snapshot"
#: A path that never exists: tests must be independent of whatever identity-review ledger a
#: developer happens to have in data/identity/review.db. Tests that exercise the ledger pass an
#: explicit review_db.
NO_REVIEW_LEDGER = ROOT / "build" / "no-such-review-ledger.db"


@pytest.fixture(scope="session")
def dataset():
    from medradar.product.dataset import load_dataset

    if not (DATA_DIR / "snapshot.json").exists():
        pytest.skip("no committed snapshot at medradar/product/snapshot; run python scripts/product_collect.py")
    return load_dataset(DATA_DIR, review_db=NO_REVIEW_LEDGER)


@pytest.fixture(scope="session")
def client(dataset):
    from fastapi.testclient import TestClient

    from medradar.product.api import create_app

    app = create_app(data_dir=DATA_DIR, web_dir=ROOT / "web" / "dist")
    with TestClient(app) as test_client:
        yield test_client
