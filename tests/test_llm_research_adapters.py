"""Offline tests for the adapter layer: registry, gates, prompts, strict parsing.

Everything here runs on CPU with no model, no network and no optional dependency.
The two model-backed arms are tested for *refusal*, which is the only behaviour
this work package is allowed to exercise for them.

The `torch`-not-imported assertions are deliberate: a gated adapter must fail
before a heavy import, otherwise a test run on a laptop could allocate GPU memory.
"""

from __future__ import annotations

import dataclasses
import json
import sys

import pytest

from experiments.local_llm_event_extraction.adapters import (
    AdapterGateClosed,
    AdapterUnavailable,
    HFLocalAdapter,
    RefusingAdapter,
    RemoteOpenAIAdapter,
    ScriptedAdapter,
    build_registry,
)
from experiments.local_llm_event_extraction.adapters.base import (
    AdapterDescriptor,
    ExtractionRequest,
)
from experiments.local_llm_event_extraction.adapters.mock import scripted_descriptor
from experiments.local_llm_event_extraction.adapters.openai_compat import (
    DEFAULT_API_KEY_ENV,
)
from experiments.local_llm_event_extraction.adapters.rule_based import (
    RULES_VERSION,
    RuleBasedAdapter,
    extract_dates,
    split_sentences,
)
from experiments.local_llm_event_extraction.adapters.config import expand_env
from experiments.local_llm_event_extraction.datasets.synthetic import (
    ROSTER_ALIASES,
    load_cases,
)
from experiments.local_llm_event_extraction.parsing import (
    first_balanced_json,
    parse_batch,
    parse_response,
)
from experiments.local_llm_event_extraction.prompting import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    TEMPLATE_SHA256,
    USER_TEMPLATE,
    build_prompt,
    truncate_text,
)
from experiments.local_llm_event_extraction.safety import (
    ENV_MODEL_LOAD,
    ENV_NETWORK,
    ENV_REMOTE_API,
)
from experiments.local_llm_event_extraction.schema import (
    EVENT_CATEGORIES,
    SCHEMA_VERSION,
    ExtractorProvenance,
    SourceDocument,
)

PROMPT_SHA256_PINNED = "12d9ba346185a3e102b36c18f5b69368abf30ec652f7868854ff2752636d747e"

REQUIRED_ADAPTERS = {
    "rules-baseline": dict(backend="rule_based", enabled=True, gate=None),
    "scripted-fixture": dict(backend="scripted", enabled=True, gate=None),
    "hf-qwen3-4b": dict(backend="hf_local", enabled=False, gate="model_load"),
    "remote-openai-compat": dict(backend="openai_compat", enabled=False, gate="remote_api"),
}


def _all_gates_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in (ENV_MODEL_LOAD, ENV_NETWORK, ENV_REMOTE_API):
        monkeypatch.setenv(variable, "0")


def _provenance() -> ExtractorProvenance:
    return ExtractorProvenance(system="scripted", adapter_id="scripted-fixture")


def _document(text: str, *, doc_id: str = "doc-1", published_at: str | None = None) -> SourceDocument:
    return SourceDocument(
        doc_id=doc_id,
        source_type="press_release",
        text=text,
        title="A synthetic document",
        published_at=published_at,
        first_seen_at="2025-01-01",
    )


def _event_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "extracted",
        "company": {
            "raw_text": "Asterion Surgical",
            "canonical_id": "asterion-surgical",
            "match_basis": "roster_alias_verbatim",
        },
        "event_category": "regulatory_approval",
        "event_date": "2024-11-07",
        "published_at": "2024-11-08",
        "timestamp_quality": {
            "event_date": "exact_day",
            "published_at": "exact_day",
            "first_seen_at": "absent",
        },
        "evidence": [{"quote": "Asterion Surgical received approval", "field": "event_category"}],
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------------------------ registry
def test_registry_wires_the_required_adapters_and_defaults() -> None:
    registry = build_registry(environ={})
    ids = set(registry.ids())
    assert REQUIRED_ADAPTERS.keys() <= ids
    for adapter_id, expected in REQUIRED_ADAPTERS.items():
        descriptor = registry.descriptor(adapter_id)
        assert descriptor.backend == expected["backend"]
        assert descriptor.enabled_by_default is expected["enabled"]
        assert descriptor.gate == expected["gate"]
    assert registry.descriptor("hf-qwen3-4b").requires_gpu is True
    assert registry.descriptor("remote-openai-compat").requires_network is True
    assert registry.default_ids() == ("rules-baseline", "scripted-fixture")


def test_descriptors_come_from_config_not_code() -> None:
    registry = build_registry(environ={})
    hf = registry.descriptor("hf-qwen3-4b")
    assert hf.model_id == "Qwen/Qwen3-4B"
    assert hf.model_revision == "PENDING-A-PIN"
    assert hf.quantization == "nf4"
    assert hf.device == "cuda"
    assert hf.max_new_tokens > 0
    remote = registry.descriptor("remote-openai-compat")
    assert remote.model_id == "gpt-4o-mini"  # default from ${VAR:-default}, not Python
    # Arms B and C share one prompt by construction, not by convention.
    assert hf.prompt_version == PROMPT_VERSION
    assert registry.descriptor("hf-qwen3-4b-qlora").prompt_version == PROMPT_VERSION
    assert registry.descriptor("rules-baseline").prompt_version is None


def test_config_expands_environment_variables() -> None:
    assert expand_env("${VAR}", {"VAR": "/models/x"}) == "/models/x"
    assert expand_env("${VAR:-fallback}", {}) == "fallback"
    assert expand_env("${VAR}", {}) == ""
    assert expand_env(["${A}", "${B:-b}"], {"A": "a"}) == ["a", "b"]


def test_config_contains_no_absolute_machine_paths() -> None:
    from experiments.local_llm_event_extraction.adapters.config import DEFAULT_MODELS_CONFIG

    raw = DEFAULT_MODELS_CONFIG.read_text(encoding="utf-8")
    assert "C:\\" not in raw
    assert "D:\\" not in raw
    assert "/Users/" not in raw


# --------------------------------------------------------------------- gates
def test_hf_gate_refuses_before_any_heavy_import(monkeypatch: pytest.MonkeyPatch) -> None:
    _all_gates_closed(monkeypatch)
    registry = build_registry(environ={})
    adapter = registry.create("hf-qwen3-4b")
    assert adapter.is_loaded is False
    with pytest.raises(AdapterGateClosed):
        adapter.load()
    assert adapter.is_loaded is False
    assert "torch" not in sys.modules
    assert "transformers" not in sys.modules


def test_hf_quantization_aliases_and_determinism_declarations() -> None:
    registry = build_registry(environ={})
    descriptor = registry.descriptor("hf-qwen3-4b")
    assert descriptor.deterministic is True  # greedy (temperature 0) in the config
    assert HFLocalAdapter(descriptor).quantization == "bnb-4bit"
    none_descriptor = dataclasses.replace(descriptor, quantization="none")
    assert HFLocalAdapter(none_descriptor).quantization == "none"
    with pytest.raises(ValueError):
        HFLocalAdapter(dataclasses.replace(descriptor, quantization="int8"))
    # A hosted endpoint is not ours to reproduce, so it must not claim determinism.
    assert registry.descriptor("remote-openai-compat").deterministic is False


def test_hf_with_open_gate_and_no_weights_refuses_without_torch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    monkeypatch.setenv(ENV_MODEL_LOAD, "1")
    registry = build_registry(environ={})
    adapter = HFLocalAdapter(
        registry.descriptor("hf-qwen3-4b"),
        weights_path=str(tmp_path / "definitely-not-here"),
    )
    with pytest.raises(AdapterUnavailable) as excinfo:
        adapter.load()
    assert "Refusing to download" in str(excinfo.value) or "does not exist" in str(excinfo.value)
    assert "torch" not in sys.modules
    assert "transformers" not in sys.modules


def test_remote_gate_refuses_without_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    _all_gates_closed(monkeypatch)
    adapter = build_registry(environ={}).create("remote-openai-compat")
    with pytest.raises(AdapterGateClosed):
        adapter.load()
    assert adapter.is_loaded is False


def test_remote_requires_an_api_key_when_gates_are_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_REMOTE_API, "1")
    monkeypatch.setenv(ENV_NETWORK, "1")
    monkeypatch.delenv(DEFAULT_API_KEY_ENV, raising=False)
    adapter = RemoteOpenAIAdapter(
        build_registry(environ={}).descriptor("remote-openai-compat"),
        base_url="https://example.invalid/v1",
    )
    with pytest.raises(AdapterUnavailable):
        adapter.load()


def test_remote_request_shaping_with_injected_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_REMOTE_API, "1")
    monkeypatch.setenv(ENV_NETWORK, "1")
    monkeypatch.delenv(DEFAULT_API_KEY_ENV, raising=False)
    captured: dict[str, object] = {}

    def transport(url: str, headers, body: bytes, timeout: float):
        captured["url"] = url
        captured["headers"] = dict(headers)
        captured["payload"] = json.loads(body.decode("utf-8"))
        captured["timeout"] = timeout
        return {
            "choices": [
                {"message": {"content": '{"events": []}'}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 4},
        }

    descriptor = build_registry(environ={}).descriptor("remote-openai-compat")
    adapter = RemoteOpenAIAdapter(
        descriptor,
        base_url="https://example.invalid/v1",
        api_key="test-key",
        transport=transport,
    )
    adapter.load()
    document = _document(
        "Asterion Surgical said the US Food and Drug Administration granted "
        "premarket approval on 7 November 2024."
    )
    request = ExtractionRequest(
        doc_id=document.doc_id,
        text=document.text,
        source_type=document.source_type,
        prompt=build_prompt(document),
    )
    response = adapter.generate(request)

    assert captured["url"] == "https://example.invalid/v1/chat/completions"
    headers = captured["headers"]
    assert headers["Authorization"] == "Bearer test-key"
    assert headers["Content-Type"] == "application/json"
    payload = captured["payload"]
    assert payload["model"] == "gpt-4o-mini"
    assert payload["temperature"] == 0
    assert payload["stream"] is False
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"
    assert "Asterion Surgical" in payload["messages"][1]["content"]
    assert response.text == '{"events": []}'
    assert response.tokens_in == 11
    assert response.tokens_out == 4
    assert response.peak_vram_mb is None  # remote: not measured, never 0
    # No price configured -> cost is not measured, not zero.
    assert response.metadata["estimated_cost_usd"] is None


def test_remote_cost_is_recorded_only_when_a_price_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_REMOTE_API, "1")
    monkeypatch.setenv(ENV_NETWORK, "1")
    transport = lambda *args: {  # noqa: E731 - tiny fake transport
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
    }
    descriptor = build_registry(environ={}).descriptor("remote-openai-compat")
    adapter = RemoteOpenAIAdapter(
        descriptor,
        base_url="https://example.invalid/v1",
        api_key="k",
        transport=transport,
        price_per_1k_tokens_in_usd=0.001,
        price_per_1k_tokens_out_usd=0.002,
    )
    adapter.load()
    document = _document("Some document text that is long enough for the prompt.")
    request = ExtractionRequest(
        doc_id=document.doc_id,
        text=document.text,
        source_type=document.source_type,
        prompt=build_prompt(document),
    )
    response = adapter.generate(request)
    assert response.metadata["estimated_cost_usd"] == pytest.approx(0.001 + 0.001)


# ------------------------------------------------------------------- mocks
def test_scripted_adapter_is_deterministic_and_records_calls() -> None:
    descriptor = scripted_descriptor()
    adapter = ScriptedAdapter(descriptor, {"doc-1": "canned response"})
    adapter.load()
    request = ExtractionRequest(doc_id="doc-1", text="ignored", source_type="press_release")
    first = adapter.generate(request)
    second = adapter.generate(request)
    assert first.text == second.text == "canned response"
    assert len(adapter.calls) == 2
    assert adapter.calls[0].doc_id == "doc-1"
    assert first.tokens_in is None and first.tokens_out is None  # not tokenised
    assert adapter.descriptor.deterministic is True


def test_scripted_adapter_missing_response_is_loud() -> None:
    adapter = ScriptedAdapter(scripted_descriptor(), {})
    adapter.load()
    with pytest.raises(AdapterUnavailable):
        adapter.generate(ExtractionRequest(doc_id="nope", text="x", source_type="other"))


def test_scripted_adapter_requires_load_first() -> None:
    adapter = ScriptedAdapter(scripted_descriptor(), {"doc-1": "x"})
    with pytest.raises(AdapterUnavailable):
        adapter.generate(ExtractionRequest(doc_id="doc-1", text="x", source_type="other"))


def test_refusing_adapter_raises_the_configured_error() -> None:
    adapter = RefusingAdapter(scripted_descriptor(adapter_id="refusing", enabled_by_default=False))
    adapter.load()
    with pytest.raises(AdapterUnavailable):
        adapter.generate(ExtractionRequest(doc_id="doc-1", text="x", source_type="other"))


# ---------------------------------------------------------------- rule arm A
def _rule_adapter() -> RuleBasedAdapter:
    descriptor = build_registry(environ={}).descriptor("rules-baseline")
    adapter = RuleBasedAdapter(descriptor, alias_map=ROSTER_ALIASES)
    adapter.load()
    return adapter


def _case(case_id: str):
    for case in load_cases():
        if case.case_id == case_id:
            return case
    raise AssertionError(f"missing synthetic case {case_id}")


def _request_for(case) -> ExtractionRequest:
    metadata = {}
    if case.document.published_at:
        metadata["published_at"] = case.document.published_at
    if case.document.first_seen_at:
        metadata["first_seen_at"] = case.document.first_seen_at
    return ExtractionRequest(
        doc_id=case.document.doc_id,
        text=case.document.text,
        source_type=case.document.source_type,
        metadata=metadata,
    )


def test_rule_adapter_emits_verbatim_quotable_evidence_via_the_registry_default_aliases() -> None:
    adapter = build_registry(environ={}).create("rules-baseline")
    adapter.load()
    case = _case("nv-001")
    request = _request_for(case)
    result = adapter.extract(request)
    assert result.parse_status == "ok"
    extracted = [event for event in result.events if event.status == "extracted"]
    assert len(extracted) == 1
    event = extracted[0]
    # Trap (ii): the subsidiary alias maps to the parent canonical id.
    assert event.company.canonical_id == "novapulse-medical"
    assert event.event_category == "regulatory_clearance"
    assert event.event_date == "2025-02-18"
    assert event.published_at == "2025-02-20"
    assert event.evidence, "an extracted event must carry evidence"
    for span in event.evidence:
        assert span.quote in case.document.text
        assert span.quote == case.document.text[span.char_start : span.char_end]


def test_rule_adapter_never_conflates_publication_date_with_event_date() -> None:
    adapter = _rule_adapter()
    case = _case("nv-002")  # press release 2024-03-05, trial start 2023-09-12
    result = adapter.extract(_request_for(case))
    extracted = [event for event in result.events if event.status == "extracted"]
    assert len(extracted) == 1
    assert extracted[0].event_date == "2023-09-12"
    assert extracted[0].published_at == "2024-03-05"
    assert extracted[0].timestamp_quality.event_date == "exact_day"


def test_rule_adapter_extracts_month_only_date_with_month_precision() -> None:
    adapter = _rule_adapter()
    case = _case("cv-001")
    result = adapter.extract(_request_for(case))
    extracted = [event for event in result.events if event.status == "extracted"]
    assert len(extracted) == 1
    assert extracted[0].event_date == "2025-03"
    assert extracted[0].timestamp_quality.event_date == "exact_month"


def test_rule_adapter_abstains_on_negative_controls() -> None:
    adapter = _rule_adapter()
    for case_id in ("nv-003", "cv-002", "ml-002"):
        case = _case(case_id)
        result = adapter.extract(_request_for(case))
        assert not any(event.status == "extracted" for event in result.events), case_id
        abstained = [event for event in result.events if event.status == "abstained"]
        assert abstained and abstained[0].abstain_reason == "no_event"


def test_rule_adapter_handles_two_events_in_one_document() -> None:
    adapter = _rule_adapter()
    case = _case("ml-001")
    result = adapter.extract(_request_for(case))
    extracted = [event for event in result.events if event.status == "extracted"]
    assert {(event.event_category, event.event_date) for event in extracted} == {
        ("regulatory_clearance", "2025-05-09"),
        ("product_launch", "2025-06-01"),
    }


def test_rule_adapter_generate_roundtrips_through_the_parser() -> None:
    adapter = _rule_adapter()
    case = _case("as-001")
    response = adapter.generate(_request_for(case))
    assert response.tokens_in is None and response.tokens_out is None  # not measured
    provenance = ExtractorProvenance(system="rule_based", adapter_id="rules-baseline")
    parsed = parse_response(response.text, doc_id=case.document.doc_id, extractor=provenance)
    assert parsed.parse_status == "ok"
    assert parsed.extractor.system == "rule_based"
    extracted = [event for event in parsed.events if event.status == "extracted"]
    assert extracted[0].event_category == "regulatory_approval"


def test_rule_table_is_exposed_for_the_report() -> None:
    rules = _rule_adapter().describe_rules()
    assert rules
    for rule in rules:
        assert rule["category"] in EVENT_CATEGORIES
        assert rule["patterns"]
        assert rule["description"]
    assert {rule["category"] for rule in rules} >= {
        "regulatory_clearance",
        "regulatory_approval",
        "regulatory_negative",
        "safety_recall",
        "clinical_trial_start",
        "product_launch",
        "rd_collaboration",
        "scientific_publication",
    }
    assert RULES_VERSION.startswith("rules-")


def test_rule_date_and_sentence_helpers() -> None:
    dates = extract_dates("On 18 February 2025 the agency acted; in March 2025 it followed up.")
    assert [(date.iso, date.quality) for date in dates] == [
        ("2025-02-18", "exact_day"),
        ("2025-03", "exact_month"),
    ]
    sentences = split_sentences("One sentence. Two sentence! Three?")
    assert [sentence.text for sentence in sentences] == ["One sentence.", "Two sentence!", "Three?"]
    assert sentences[0].start == 0
    assert sentences[-1].end == len("One sentence. Two sentence! Three?")


# ------------------------------------------------------------------ prompting
def test_prompt_version_and_template_hash_are_stable() -> None:
    import hashlib

    assert PROMPT_VERSION == "extract-v1"
    assert SYSTEM_PROMPT and USER_TEMPLATE
    assert TEMPLATE_SHA256 == PROMPT_SHA256_PINNED
    recomputed = hashlib.sha256((SYSTEM_PROMPT + "\x00" + USER_TEMPLATE).encode("utf-8")).hexdigest()
    assert recomputed == TEMPLATE_SHA256


def test_prompt_is_deterministic_and_contains_the_closed_vocabularies() -> None:
    document = _document("Some text about an event.", published_at="2024-03-05")
    first = build_prompt(document, max_input_chars=2000)
    second = build_prompt(document, max_input_chars=2000)
    assert first == second
    assert first.prompt_version == PROMPT_VERSION
    assert first.template_sha256 == TEMPLATE_SHA256
    for category in EVENT_CATEGORIES:
        assert category in first.system
    assert '"absent"' in first.system or "absent" in first.system
    assert "null" in first.system
    assert "verbatim" in first.system.lower()
    assert "abstain" in first.system.lower()
    assert document.doc_id in first.user
    assert "2024-03-05" in first.user


def test_prompt_truncation_is_explicit() -> None:
    text = "word " * 5000  # 25k characters
    truncated, was_truncated, omitted = truncate_text(text, 1000)
    assert was_truncated is True
    assert omitted == len(text) - 1000
    assert truncated.startswith(text[:1000])
    assert "TRUNCATED" in truncated
    prompt = build_prompt(_document(text), max_input_chars=1000)
    assert "TRUNCATED" in prompt.user
    short, flagged, zero = truncate_text("short text", 1000)
    assert (short, flagged, zero) == ("short text", False, 0)


# ------------------------------------------------------------------- parsing
def test_parse_balanced_json_helpers() -> None:
    assert first_balanced_json('prose {"events": []} trailing') == '{"events": []}'
    assert first_balanced_json('{"a": "}"}') == '{"a": "}"}'
    assert first_balanced_json("no json here") is None
    assert first_balanced_json('{"unterminated": [1, 2') is None


def _parse(text) -> object:
    return parse_response(text, doc_id="doc-1", extractor=_provenance())


@pytest.mark.parametrize(
    ("text", "expected_status"),
    [
        ("", "empty"),
        ("   \n\t ", "empty"),
        (None, "empty"),
        ('{"unterminated": [1, 2', "invalid_json"),
        ('{"events": [{"status": "extracted"}]}', "invalid_json"),
        ("I cannot help with this request.", "refused"),
        ("抱歉，我无法完成这个请求。", "refused"),
    ],
)
def test_parser_failure_modes(text, expected_status) -> None:
    parsed = _parse(text)
    assert parsed.parse_status == expected_status
    assert parsed.events == ()
    assert parsed.parse_error
    assert parsed.failed is True


def test_parser_accepts_fenced_json() -> None:
    body = json.dumps({"events": [_event_payload()]})
    parsed = _parse(f"```json\n{body}\n```")
    assert parsed.parse_status == "ok"
    assert len(parsed.events) == 1
    assert parsed.events[0].event_category == "regulatory_approval"
    assert parsed.parse_error is None


def test_parser_accepts_trailing_prose_and_array_payloads() -> None:
    body = json.dumps({"events": [_event_payload()]})
    parsed = _parse(body + "\n\nI hope this extraction is useful.")
    assert parsed.parse_status == "ok"
    array_payload = json.dumps([_event_payload(), _event_payload(status="abstained", abstain_reason="no_event", evidence=[], event_category=None)])
    parsed_array = _parse(array_payload)
    assert parsed_array.parse_status == "ok"
    assert len(parsed_array.events) == 2


def test_parser_rejects_unknown_keys_instead_of_dropping_them() -> None:
    payload = {"events": [_event_payload(confidence=0.99)]}
    parsed = _parse(json.dumps(payload))
    assert parsed.parse_status == "invalid_json"
    assert parsed.events == ()
    assert "unknown key" in (parsed.parse_error or "").lower()


def test_parser_rejects_unknown_category_and_missing_evidence_without_repair() -> None:
    bad_category = _parse(json.dumps({"events": [_event_payload(event_category="made_up")]}))
    assert bad_category.parse_status == "invalid_json"
    missing_evidence = _parse(json.dumps({"events": [_event_payload(evidence=[])]}))
    assert missing_evidence.parse_status == "invalid_json"
    assert "evidence" in (missing_evidence.parse_error or "").lower()


def test_parser_accepts_a_bare_event_object() -> None:
    parsed = _parse(json.dumps(_event_payload()))
    assert parsed.parse_status == "ok"
    assert len(parsed.events) == 1


def test_parser_discards_model_supplied_provenance_and_doc_id() -> None:
    payload = {
        "doc_id": "a-different-document",
        "schema_version": SCHEMA_VERSION,
        "extractor": {"system": "hf_local", "adapter_id": "hf-qwen3-4b"},
        "events": [_event_payload()],
    }
    parsed = _parse(json.dumps(payload))
    assert parsed.parse_status == "ok"
    assert parsed.doc_id == "doc-1"
    assert parsed.extractor.adapter_id == "scripted-fixture"
    assert parsed.extractor.system == "scripted"


def test_parse_batch_preserves_order_and_keys() -> None:
    responses = {
        "doc-b": json.dumps({"events": [_event_payload()]}),
        "doc-a": "I cannot help with this request.",
    }
    parsed = parse_batch(responses, extractor=_provenance())
    assert list(parsed) == ["doc-b", "doc-a"]
    assert parsed["doc-b"].parse_status == "ok"
    assert parsed["doc-a"].parse_status == "refused"


def test_parsed_extraction_is_an_extraction_result() -> None:
    from experiments.local_llm_event_extraction.schema import ExtractionResult

    parsed = _parse(json.dumps({"events": [_event_payload()]}))
    assert isinstance(parsed, ExtractionResult)
    hydrated = parsed.to_dict(include_raw=True)
    assert hydrated["doc_id"] == "doc-1"
    assert hydrated["raw_output"].startswith("{")
