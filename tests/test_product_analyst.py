"""Tests for the MedRadar 2.0 deterministic AI Research Analyst engine.

The analyst is a *deterministic retrieval engine*: every number in an answer must
come from a ``store`` query executed for that question, and every concrete
company/track claim must carry traceable ``event_id`` values. These tests assert
that contract on the real research store (``data/medradar.sqlite``), so the whole
module skips cleanly on a fresh checkout / CI where the data has not been built.

Run::

    python -m pytest tests/test_product_analyst.py -q
"""
from __future__ import annotations

import ast
import inspect
import json
import time

import pytest

from medradar.product import analyst, catalog, store

pytestmark = pytest.mark.skipif(
    not store.dataset_signature().get("exists"),
    reason="research store data/medradar.sqlite not built (run: python -m medradar run)",
)

EXAMPLES = list(catalog.ANALYST_EXAMPLES)
FIVE = ["medtronic", "ge_healthcare", "philips", "draeger", "mindray"]
REQUIRED_SECTION_TITLES = {"结论", "数据", "方法与口径", "局限"}

EXPECTED_INTENTS = {
    0: "company_track_trend",
    1: "company_compare",
    2: "track_company_leaders",
    3: "company_overview",
    4: "track_acceleration",
    5: "company_compare",
    6: "evidence_lookup",
    7: "evidence_lookup",
}

OUT_OF_SCOPE_QUESTIONS = [
    "美敦力的营收和利润是多少？",
    "未来三年迈瑞的超声业务会怎么增长？",
    "为什么飞利浦的患者监护记录下降了？",
    "迈瑞在全球市场占多少份额？",
    "迈瑞在患者监护赛道的创新能力排名第一吗？",
]

CLARIFICATION_QUESTIONS = [
    "帮我分析一下",
    "？",
    "2019-2024 年有哪些记录",
]

AMBIGUOUS_QUESTIONS = [
    "GE",
    "患者监护",
    "体外诊断",
    "心血管",
    "影像和超声",
    "对比",
    "2019-2024",
    "你好",
    "asdfghjkl",
]


def _ask(question: str) -> dict:
    return analyst.answer(question)


# ----------------------------------------------------------------- performance
def test_performance_each_answer_under_three_seconds():
    """Each example must be answered well under 3 s on the local frozen store."""
    for question in EXAMPLES:
        started = time.perf_counter()
        response = _ask(question)
        elapsed = time.perf_counter() - started
        assert response["status"] == "answered", question
        assert elapsed < 3.0, f"{question} took {elapsed:.2f}s"


# -------------------------------------------------------------------- contract
def test_examples_are_eight_real_questions():
    assert len(EXAMPLES) == 8
    assert all(isinstance(item, str) and item.strip() for item in EXAMPLES)


@pytest.mark.parametrize("index", range(len(EXAMPLES)))
def test_example_answer_matches_contract(index: int):
    question = EXAMPLES[index]
    response = _ask(question)

    assert response["status"] == "answered"
    assert response["question"] == question
    assert response["mode"] == "deterministic"
    assert response["mode_zh"]
    assert response["intent"]["type"] == EXPECTED_INTENTS[index]
    assert response["intent"]["label_zh"]

    parsed = response["intent"]["parsed"]
    for field in ("companies", "tracks", "years", "metric", "spans"):
        assert field in parsed
    assert isinstance(parsed["companies"], list)
    assert isinstance(parsed["tracks"], list)
    assert isinstance(parsed["spans"], list)

    assert isinstance(response["answer_zh"], str) and len(response["answer_zh"]) >= 10
    sections = response["sections"]
    assert sections, "sections must not be empty"
    assert REQUIRED_SECTION_TITLES <= {section["title_zh"] for section in sections}
    for section in sections:
        assert section["title_zh"]
        assert isinstance(section["body_zh"], str)
        assert isinstance(section["bullets"], list)
        if "table" in section:
            table = section["table"]
            assert table["columns"]
            assert isinstance(table["rows"], list)
            for row in table["rows"]:
                assert len(row) == len(table["columns"])
                assert all(isinstance(cell, str) for cell in row), "table cells must be strings"
    assert isinstance(response["computation_zh"], str) and response["computation_zh"]
    assert response["limitations"], "catalog LIMITATIONS must be surfaced"
    assert all(isinstance(item, str) and item for item in response["limitations"])
    # the whole payload must be JSON-serialisable, exactly as the API returns it
    json.dumps(response, ensure_ascii=False)

    # evidence discipline: every listed event exists in the store
    assert response["evidence"], f"{question} should carry traceable evidence"
    for item in response["evidence"]:
        assert set(item) == {
            "event_id",
            "event_date",
            "title",
            "url",
            "company_name_zh",
            "track_name_zh",
            "why_zh",
        }
        assert item["why_zh"], "each evidence item must explain what it supports"
        detail = store.event_detail(item["event_id"])
        assert detail["event"]["event_id"] == item["event_id"]
        assert detail["event"]["event_date"] == item["event_date"]


def test_limitations_include_core_catalog_entries():
    response = _ask(EXAMPLES[0])  # Mindray → roster-absent firm
    joined = "\n".join(response["limitations"])
    assert "美国" in joined
    assert "一条记录不等于一个产品" in joined
    assert "赛道" in joined
    assert "预测" in joined
    # entity mapping must be disclosed for the two roster-absent firms
    assert "名称匹配" in joined or "映射" in joined or "错配" in joined


# ---------------------------------------------------------- numbers are real
def test_trend_numbers_match_company_claims_query():
    """The quoted counts must equal the store's own company_claims output."""
    question = EXAMPLES[0]
    response = _ask(question)
    parsed = response["intent"]["parsed"]
    assert parsed["companies"][0]["key"] == "mindray"
    assert parsed["tracks"][0]["id"] == "imaging_us"
    assert parsed["years"] == 5

    claims = store.company_claims("mindray", 5)
    claim = next(item for item in claims["claims"] if item["track"] == "imaging_us")
    recent = claim["metrics"]["recent"]
    prior = claim["metrics"]["prior"]
    assert parsed["window"]["start"] == claims["window"]["start"]
    assert parsed["window"]["end"] == claims["window"]["end"]

    # the claim itself is recomputable to exactly the same event set
    evidence = store.evidence_search(
        companies=("mindray",),
        track="imaging_us",
        metric="approvals",
        start=claims["window"]["start"],
        end=claims["window"]["end"],
        limit=1,
    )
    assert evidence["total"] == recent

    data_section = next(section for section in response["sections"] if section["title_zh"] == "数据")
    cells = {cell for row in data_section["table"]["rows"] for cell in row}
    assert str(recent) in cells
    assert str(prior) in cells


def test_compare_reports_differences_without_innovation_ranking():
    question = EXAMPLES[5]
    response = _ask(question)
    parsed = response["intent"]["parsed"]
    assert response["intent"]["type"] == "company_compare"
    assert [company["key"] for company in parsed["companies"]] == FIVE
    assert parsed["tracks"][0]["id"] == "patient_monitoring"
    assert "不给出" in response["answer_zh"] or "不能说明创新能力" in response["answer_zh"]
    assert "创新能力" in response["answer_zh"]

    data_section = next(section for section in response["sections"] if section["title_zh"] == "数据")
    assert len(data_section["table"]["rows"]) == len(FIVE)
    joined_limitations = "\n".join(response["limitations"])
    assert "Rank" not in joined_limitations
    # computed comparability warnings must be surfaced, not hidden
    assert any(
        token in joined_limitations
        for token in ("路径", "起始时间", "名称匹配", "PMA")
    )


def test_leaders_separate_observed_increase_from_statistical_signal():
    question = EXAMPLES[2]
    response = _ask(question)
    parsed = response["intent"]["parsed"]
    assert response["intent"]["type"] == "track_company_leaders"
    assert parsed["tracks"][0]["id"] == "respiratory"
    assert "增加" in response["answer_zh"]
    assert "统计" in response["answer_zh"]

    data_section = next(section for section in response["sections"] if section["title_zh"] == "数据")
    assert "z" in data_section["table"]["columns"]
    assert "判断" in data_section["table"]["columns"]
    verdicts = {row[-1] for row in data_section["table"]["rows"]}
    assert verdicts & {"增加（仅观察）", "增加（统计信号）", "减少", "持平"}
    assert any("增加" in row[-1] for row in data_section["table"]["rows"])

    result = store.track_companies("respiratory", "approvals", 5)
    top_recent = max(row["recent"] for row in result["companies"])
    assert any(row[1] == str(top_recent) for row in data_section["table"]["rows"])


def test_acceleration_ranks_counts_and_flags_signals():
    question = EXAMPLES[4]
    response = _ask(question)
    assert response["intent"]["type"] == "track_acceleration"
    assert response["intent"]["parsed"]["years"] == 3
    assert "不是未来预测" in response["answer_zh"]

    data_section = next(section for section in response["sections"] if section["title_zh"] == "数据")
    assert "变化率" in data_section["table"]["columns"]
    assert "统计信号" in data_section["table"]["columns"]
    assert data_section["table"]["rows"]
    assert any(row[-1].startswith("加速") for row in data_section["table"]["rows"])

    payload = store.tracks_acceleration(3)
    tracked = {row["track"]: row for row in payload["tracks"]}
    first_row = data_section["table"]["rows"][0]
    top_track = next(row for row in payload["tracks"] if row["name_zh"] == first_row[0])
    assert str(top_track["recent"]) == first_row[2]
    assert str(top_track["prior"]) == first_row[3]
    assert any(track in tracked for track in ("medical_ai", "respiratory", "ivd_poct"))


def test_overview_uses_company_profile_headline_and_milestones():
    question = EXAMPLES[3]
    response = _ask(question)
    assert response["intent"]["type"] == "company_overview"
    assert response["intent"]["parsed"]["years"] == 10

    profile = store.company_profile("ge_healthcare", 10)
    data_section = next(section for section in response["sections"] if section["title_zh"] == "数据")
    cells = {cell for row in data_section["table"]["rows"] for cell in row}
    assert str(profile["headline"]["approvals_all_time"]) in cells
    assert str(profile["headline"]["approvals_window"]) in cells
    assert any(section["title_zh"] == "主要赛道" for section in response["sections"])
    assert any(section["title_zh"] == "里程碑" for section in response["sections"])


def test_lookup_returns_latest_pma_record_from_store():
    question = EXAMPLES[7]
    response = _ask(question)
    parsed = response["intent"]["parsed"]
    assert response["intent"]["type"] == "evidence_lookup"
    assert parsed["companies"][0]["key"] == "medtronic"
    assert parsed["tracks"][0]["id"] == "cardiac_rhythm"
    assert parsed["metric"] == "pma"

    latest = store.evidence_search(
        companies=("medtronic",),
        track="cardiac_rhythm",
        metric="pma",
        limit=1,
    )["items"][0]
    assert response["evidence"][0]["event_id"] == latest["event_id"]
    assert response["evidence"][0]["event_date"] == latest["event_date"]
    assert response["evidence"][0]["event_date"] in response["answer_zh"]


def test_lookup_without_records_says_evidence_is_insufficient():
    """Draeger has 2024 respiratory recalls but no approval record: be honest."""
    question = EXAMPLES[6]
    response = _ask(question)
    parsed = response["intent"]["parsed"]
    assert response["intent"]["type"] == "evidence_lookup"
    assert parsed["companies"][0]["key"] == "draeger"
    assert parsed["tracks"][0]["id"] == "respiratory"
    assert parsed["time"]["kind"] == "year"
    assert parsed["window"]["start"] == "2024-01-01"
    assert parsed["window"]["end"] == "2024-12-31"

    approvals = store.evidence_search(
        companies=("draeger",),
        track="respiratory",
        metric="approvals",
        start="2024-01-01",
        end="2024-12-31",
        limit=1,
    )
    assert approvals["total"] == 0
    assert "现有证据不足以作出该判断" in response["answer_zh"]
    # the same slice does contain other record kinds; they are returned only as
    # labelled context, never presented as approval records
    other = store.evidence_search(
        companies=("draeger",),
        track="respiratory",
        metric=None,
        start="2024-01-01",
        end="2024-12-31",
        limit=50,
    )
    assert other["total"] > 0
    assert all("不属于" in item["why_zh"] for item in response["evidence"])


# --------------------------------------------------------------- out of scope
@pytest.mark.parametrize("question", OUT_OF_SCOPE_QUESTIONS)
def test_out_of_scope_answers_are_honest(question: str):
    response = _ask(question)
    assert response["status"] == "out_of_scope"
    assert response["intent"]["type"] == "out_of_scope"
    assert response["evidence"] == []
    assert "超出" in response["answer_zh"]
    assert REQUIRED_SECTION_TITLES <= {section["title_zh"] for section in response["sections"]}
    assert 3 <= len(response["followups"]) <= 4
    assert all(isinstance(item, str) and item for item in response["followups"])
    assert response["limitations"]
    json.dumps(response, ensure_ascii=False)


@pytest.mark.parametrize("question", CLARIFICATION_QUESTIONS)
def test_needs_clarification_offers_clickable_options(question: str):
    response = _ask(question)
    assert response["status"] == "needs_clarification"
    assert response["intent"]["type"] == "needs_clarification"
    assert response["evidence"] == []
    assert 2 <= len(response["followups"]) <= 4
    assert all(isinstance(item, str) and item for item in response["followups"])
    assert REQUIRED_SECTION_TITLES <= {section["title_zh"] for section in response["sections"]}
    assert "识别" in response["answer_zh"] or "补充" in response["answer_zh"]


# ------------------------------------------------------------- parsed intent
def test_parsed_intent_exposes_entities_years_metric_and_raw_spans():
    response = _ask(EXAMPLES[5])
    parsed = response["intent"]["parsed"]
    assert [company["key"] for company in parsed["companies"]] == FIVE
    assert parsed["tracks"][0]["track_ids"] == ["patient_monitoring"]
    assert parsed["years"] == 5
    assert parsed["metric"] == "approvals"
    kinds = {span["kind"] for span in parsed["spans"]}
    assert {"company", "track"} <= kinds
    for span in parsed["spans"]:
        assert isinstance(span["text"], str) and span["text"]
        assert 0 <= span["start"] < span["end"] <= len(response["question"])
    matched_companies = {company["matched"] for company in parsed["companies"]}
    assert {"美敦力", "GE 医疗", "飞利浦", "德尔格", "迈瑞"} <= matched_companies


def test_full_width_and_traditional_chinese_are_tolerated():
    question = "德爾格２０２４年有哪些麻醉／呼吸相關的公開審批記錄？"
    response = _ask(question)
    parsed = response["intent"]["parsed"]
    assert response["status"] == "answered"
    assert parsed["companies"][0]["key"] == "draeger"
    assert parsed["companies"][0]["matched"] == "德爾格"
    assert parsed["tracks"][0]["id"] == "respiratory"
    assert parsed["time"]["kind"] == "year"
    assert parsed["window"]["start"] == "2024-01-01"


def test_deterministic_same_question_twice():
    for question in (EXAMPLES[0], EXAMPLES[5], EXAMPLES[4], EXAMPLES[2]):
        first = _ask(question)
        second = _ask(question)
        assert first["intent"] == second["intent"]
        assert first["sections"] == second["sections"]
        assert first["evidence"] == second["evidence"]
        assert first["answer_zh"] == second["answer_zh"]


@pytest.mark.parametrize("question", AMBIGUOUS_QUESTIONS)
def test_ambiguous_input_never_crashes(question: str):
    response = _ask(question)
    assert response["status"] in {"answered", "needs_clarification", "out_of_scope"}
    assert response["answer_zh"]
    assert response["sections"]


def test_explicit_range_trend_uses_that_window():
    question = "2019-2024 年迈瑞在超声赛道有什么变化"
    response = _ask(question)
    parsed = response["intent"]["parsed"]
    assert response["intent"]["type"] == "company_track_trend"
    assert parsed["time"]["kind"] == "range"
    assert parsed["window"]["start"] == "2019-01-01"
    assert parsed["window"]["end"] == "2024-12-31"

    table = store.company_track_table("mindray", "approvals", "2019-01-01", "2024-12-31")
    row = next(item for item in table["rows"] if item["track"] == "imaging_us")
    data_section = next(section for section in response["sections"] if section["title_zh"] == "数据")
    cells = {cell for item in data_section["table"]["rows"] for cell in item}
    assert str(row["recent"]) in cells
    assert str(row["prior"]) in cells
    for item in response["evidence"]:
        assert "2019-01-01" <= item["event_date"] <= "2024-12-31"


def test_record_keyword_does_not_misread_a_trend_question():
    response = _ask("过去 5 年迈瑞的监护记录趋势")
    assert response["intent"]["type"] == "company_track_trend"
    assert response["intent"]["parsed"]["record_lookup"] is False


def test_explicit_compare_window_is_disclosed_as_approximation():
    response = _ask("2019-2024 年对比迈瑞和飞利浦在超声赛道的活动")
    assert response["intent"]["type"] == "company_compare"
    method = next(section for section in response["sections"] if section["title_zh"] == "方法与口径")
    assert "折算" in method["body_zh"]
    assert "滚动窗口" in method["body_zh"]


def test_question_validation_raises_value_error():
    for question in ("", "   ", "x" * 301):
        with pytest.raises(ValueError):
            analyst.answer(question)
    with pytest.raises(ValueError):
        analyst.parse_question("")


def test_engine_has_no_llm_or_network_dependencies():
    source = inspect.getsource(analyst)
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {"requests", "httpx", "urllib", "urllib3", "socket", "openai", "anthropic", "aiohttp", "http"}
    assert not (imported & forbidden), imported & forbidden
    lowered = source.lower()
    for token in ("api_key", "openai", "anthropic", "completion("):
        assert token not in lowered


# --------------------------------------------------------------------- routes
def test_analyst_routes():
    from fastapi.testclient import TestClient

    from medradar.web.app import app

    client = TestClient(app)

    examples = client.get("/api/analyst/examples")
    assert examples.status_code == 200
    payload = examples.json()
    assert payload["examples"] == EXAMPLES
    assert payload["capabilities"]["can_zh"]
    assert payload["mode"] == "deterministic"
    assert payload["mode_zh"]

    answered = client.post("/api/analyst/ask", json={"question": EXAMPLES[0]})
    assert answered.status_code == 200
    assert answered.json()["status"] == "answered"
    assert answered.json()["sections"]

    assert client.post("/api/analyst/ask", json={"question": ""}).status_code == 400
    assert client.post("/api/analyst/ask", json={}).status_code == 400
    assert client.post("/api/analyst/ask", json={"question": "x" * 301}).status_code == 400
    assert client.post("/api/analyst/ask", json=["not", "an", "object"]).status_code == 400
    bad_json = client.post(
        "/api/analyst/ask",
        content="{not json",
        headers={"Content-Type": "application/json"},
    )
    assert bad_json.status_code == 400
