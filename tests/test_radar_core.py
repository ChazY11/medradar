"""RADAR-001 core contracts: time semantics, taxonomy validation and the HTTP transport.

These are the rules the rest of the system is allowed to assume. They are tested without a
network, a database or a model, so a regression here is unambiguous.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from medradar.radar.http import (
    BudgetExceeded,
    FetchResult,
    HostPolicy,
    NetworkFailure,
    NotFound,
    PoliteFetcher,
    RateLimited,
    Refused,
)
from medradar.radar.records import (
    PRECISION_DATE,
    PRECISION_DATETIME,
    PRECISION_UNKNOWN,
    PRECISION_YEAR,
    RawRecord,
    canonical_json,
    changed_fields,
    content_hash,
    hours_between,
    normalize_moment,
    observation_id,
    parse_moment,
    version_id,
)
from medradar.radar.taxonomy import Taxonomy, TaxonomyError, load_taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"


# ------------------------------------------------------------------ time semantics
def test_date_only_keeps_date_precision_and_is_not_a_fake_midnight():
    value, precision = normalize_moment("2026-10-31")
    assert value == "2026-10-31"
    assert precision == PRECISION_DATE


def test_aware_datetime_is_normalised_to_utc_with_datetime_precision():
    value, precision = normalize_moment("2026-11-02T13:00:00+01:00")
    assert value == "2026-11-02T12:00:00+00:00"
    assert precision == PRECISION_DATETIME


def test_naive_datetime_is_downgraded_to_date_rather_than_guessing_a_zone():
    value, precision = normalize_moment(datetime(2026, 3, 4, 9, 30))
    assert value == "2026-03-04"
    assert precision == PRECISION_DATE


def test_year_and_year_month_precision_are_preserved():
    assert normalize_moment("2026") == ("2026", PRECISION_YEAR)
    assert normalize_moment("2026-07") == ("2026-07", PRECISION_YEAR)


def test_missing_time_is_unknown_and_never_today():
    assert normalize_moment(None) == (None, PRECISION_UNKNOWN)
    assert normalize_moment("") == (None, PRECISION_UNKNOWN)
    assert normalize_moment("not a date") == (None, PRECISION_UNKNOWN)


def test_hours_between_anchors_a_date_only_value_for_arithmetic_only():
    # 2026-01-01 date-precision publication, observed 2026-01-02T06:00Z => 30 hours.
    assert hours_between("2026-01-01", "2026-01-02T06:00:00+00:00") == 30.0
    assert hours_between(None, "2026-01-02T06:00:00+00:00") is None


def test_parse_moment_accepts_z_suffix():
    parsed = parse_moment("2026-11-16T18:46:31Z")
    assert parsed is not None and parsed.tzinfo is not None
    assert parsed.astimezone(timezone.utc).hour == 18


# ------------------------------------------------------------------ record contract
def test_raw_record_rejects_unknown_record_type():
    with pytest.raises(ValueError):
        RawRecord(source="s", source_record_id="1", record_type="rumour", title="t")


def test_raw_record_rejects_precision_without_a_value():
    with pytest.raises(ValueError):
        RawRecord(source="s", source_record_id="1", record_type="publication", title="t",
                  published_at=None, published_at_precision=PRECISION_DATETIME)


def test_observation_id_is_deterministic_and_source_scoped():
    first = observation_id("pubmed", "pmid:1")
    assert first == observation_id("pubmed", "pmid:1")
    assert first != observation_id("crossref", "pmid:1")
    assert version_id(first, "abc") == version_id(first, "abc")


def test_content_hash_ignores_key_order_and_detects_a_real_change():
    left = {"title": "a", "pmid": "1"}
    right = {"pmid": "1", "title": "a"}
    assert content_hash(left) == content_hash(right)
    assert content_hash(left) != content_hash({"title": "b", "pmid": "1"})


def test_changed_fields_is_stable_and_sorted():
    assert changed_fields({"a": 1, "b": 2}, {"b": 3, "a": 1}) == ["b"]
    assert changed_fields(None, {"z": 1, "a": 2}) == ["a", "z"]


def test_canonical_json_rejects_nan():
    with pytest.raises(ValueError):
        canonical_json({"value": float("nan")})


# ---------------------------------------------------------------------- taxonomy
def test_taxonomy_loads_and_is_fingerprinted():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    assert len(taxonomy.topics) >= 10
    assert taxonomy.fingerprint
    assert taxonomy.version
    # The fingerprint must not change between two loads of the same files.
    assert load_taxonomy(str(CONFIG_DIR)).fingerprint == taxonomy.fingerprint


def test_every_declared_product_code_is_a_verified_three_letter_fda_code():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    for topic in taxonomy.topics:
        for code in topic.product_codes:
            assert len(code) == 3 and code.isalpha() and code.isupper()


def test_text_match_is_topic_related_and_reports_the_matched_span():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    matches = taxonomy.match_text("A modular patient monitor reduced alarm fatigue in the ICU")
    ids = {match["topic_id"] for match in matches}
    assert "smart_alarms" in ids
    assert all(match["confirmation"] == "TOPIC_RELATED" for match in matches)
    assert any("alarm fatigue" in match["matched_terms"] for match in matches)


def test_product_code_mapping_is_stronger_than_text_and_still_topic_related():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    entries = taxonomy.topics_for_product_codes(["MHX"])
    assert entries
    assert all(entry["confirmation"] == "TOPIC_RELATED" for entry in entries)
    assert all(entry["method"] == "rule_product_code" for entry in entries)


def test_organisation_resolution_uses_the_longest_published_alias():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    match = taxonomy.resolve_organization("Philips Medizin Systeme Boeblingen GmbH")
    assert match and match[0]["organization_id"] == "philips"
    assert match[0]["confirmation"] == "CONFIRMED"


def test_a_broad_legal_name_stays_a_candidate_not_a_confirmed_company():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    match = taxonomy.resolve_organization("General Electric Co.")
    assert match and match[0]["confirmation"] == "CANDIDATE"


def test_an_unknown_applicant_is_not_folded_into_a_company():
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    assert taxonomy.resolve_organization("Totally Unrelated Instruments Pty Ltd") == []


def test_taxonomy_rejects_a_topic_without_evidence_rules(tmp_path):
    topics = {"taxonomy_version": "t", "topics": [{"id": "empty", "family": "f"}]}
    orgs = {"registry_version": "o", "organizations": []}
    (tmp_path / "topics.json").write_text(json.dumps(topics), encoding="utf-8")
    (tmp_path / "organizations.json").write_text(json.dumps(orgs), encoding="utf-8")
    with pytest.raises(TaxonomyError):
        Taxonomy(tmp_path)


def test_taxonomy_rejects_an_unverified_product_code_label(tmp_path):
    topics = {"taxonomy_version": "t", "topics": [{
        "id": "x", "family": "f", "product_codes": [{"code": "MHX"}]}]}
    orgs = {"registry_version": "o", "organizations": []}
    (tmp_path / "topics.json").write_text(json.dumps(topics), encoding="utf-8")
    (tmp_path / "organizations.json").write_text(json.dumps(orgs), encoding="utf-8")
    with pytest.raises(TaxonomyError):
        Taxonomy(tmp_path)


# ------------------------------------------------------------------------- http
class _Response:
    def __init__(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self._body = body
        self.headers = headers or {"Content-Type": "application/json; charset=utf-8"}

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(status: int, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x.test/", status, "error", headers or {}, None)


def test_a_refusal_is_terminal_and_never_retried():
    calls = {"n": 0}

    def opener(request, timeout=None):
        calls["n"] += 1
        raise _http_error(403)

    fetcher = PoliteFetcher(opener=opener, sleep=lambda _s: None, max_requests=10)
    with pytest.raises(Refused):
        fetcher.get_text("https://vendor.test/news")
    assert calls["n"] == 1
    assert fetcher.stats["refusals"] == 1


def test_rate_limit_is_retried_and_retry_after_is_honoured():
    slept: list[float] = []
    calls = {"n": 0}

    def opener(request, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(429, {"Retry-After": "2"})
        return _Response(200, b"{\"ok\": true}")

    fetcher = PoliteFetcher(opener=opener, sleep=slept.append,
                            policies={"x.test": HostPolicy(max_attempts=3)})
    payload = fetcher.get_json("https://x.test/data")
    assert payload == {"ok": True}
    assert calls["n"] == 2
    assert slept and slept[0] >= 2.0


def test_a_404_is_not_a_refusal_and_can_be_opted_into_as_empty():
    def opener(request, timeout=None):
        raise _http_error(404)

    fetcher = PoliteFetcher(opener=opener, sleep=lambda _s: None)
    with pytest.raises(NotFound):
        fetcher.get_text("https://x.test/missing")
    assert fetcher.get_json("https://x.test/missing", allow_not_found=True) is None


def test_the_request_budget_is_a_hard_stop():
    def opener(request, timeout=None):
        return _Response(200, b"[]")

    fetcher = PoliteFetcher(opener=opener, sleep=lambda _s: None, max_requests=1)
    fetcher.get_json("https://x.test/one")
    with pytest.raises(BudgetExceeded):
        fetcher.get_json("https://x.test/two")


def test_network_failure_is_retried_then_reported():
    calls = {"n": 0}

    def opener(request, timeout=None):
        calls["n"] += 1
        raise urllib.error.URLError("connection reset")

    fetcher = PoliteFetcher(opener=opener, sleep=lambda _s: None,
                            policies={"x.test": HostPolicy(max_attempts=2)})
    with pytest.raises(NetworkFailure):
        fetcher.get_text("https://x.test/data")
    assert calls["n"] == 2
