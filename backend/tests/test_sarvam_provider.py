import json

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from app.providers.contracts import (
    ModelProvider,
    ProviderAuthentication,
    ProviderCapabilities,
    ProviderIdentity,
)
from app.providers.llm import LLMProviderError
from app.providers.sarvam import SarvamChatCompletionsProvider
from app.research.llm_tasks import ResearchReportDraft


class AppraisalProbe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    source_id: str
    method: str
    passage_ids: list[str]


class SarvamSettings:
    sarvam_api_key = "fixture-secret"
    sarvam_model = "sarvam-105b"
    sarvam_input_price_per_million_inr = 15.0
    sarvam_output_price_per_million_inr = 60.0
    sarvam_max_job_cost_inr = 5.0
    allow_paid_llm_calls = True


class GlmFlashSarvamSettings(SarvamSettings):
    sarvam_model = "glm5.3-flash"
    sarvam_max_job_cost_inr = 20.0


def test_sarvam_adapter_implements_vendor_neutral_contract(monkeypatch):
    import app.providers.sarvam as sarvam

    monkeypatch.setattr(sarvam, "settings", SarvamSettings())
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "sarvam-105b",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": '{"status":"assessed","source_id":"S1",'
                                '"method":"abstract only","passage_ids":["P1"]}'
                            },
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 24,
                        "total_tokens": 124,
                    },
                },
            )
        )
    )
    provider = SarvamChatCompletionsProvider(client)
    try:
        assert isinstance(provider, ModelProvider)
        assert provider.identity == ProviderIdentity("sarvam", "sarvam-105b")
        assert provider.authentication == ProviderAuthentication(
            environment_variable="SARVAM_API_KEY",
            header_name="api-subscription-key",
        )
        assert provider.capabilities == ProviderCapabilities(
            strict_json_schema=True,
            supported_parameters=frozenset(
                {
                    "model",
                    "messages",
                    "max_tokens",
                    "temperature",
                    "stream",
                    "n",
                    "response_format",
                }
            ),
            max_context_tokens=128000,
            max_completion_tokens=4096,
            reasoning_control=False,
            rate_limit_scope="account",
            cost_currency="INR",
            input_price_per_million=15.0,
            output_price_per_million=60.0,
        )
    finally:
        provider.close()
        client.close()

    from app.providers.registry import configured_model

    profile = configured_model("sarvam", config=SarvamSettings())
    assert profile.strict_json_schema is True
    assert profile.max_context_tokens == 128_000
    assert profile.max_completion_tokens == 4_096
    assert profile.reasoning_control is False
    assert profile.input_price_per_million == 15.0
    assert profile.output_price_per_million == 60.0
    assert profile.cost_reservation_multiplier == 1.2


def test_sarvam_request_uses_native_v2_schema_contract_and_normalizes_cost(monkeypatch):
    import app.providers.sarvam as sarvam

    monkeypatch.setattr(sarvam, "settings", SarvamSettings())
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth_header_present"] = "api-subscription-key" in request.headers
        captured["auth_value"] = request.headers.get("api-subscription-key")
        payload = json.loads(request.content)
        captured["payload"] = payload
        return httpx.Response(
            200,
            json={
                "model": "sarvam-105b",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"status":"assessed","source_id":"S1",'
                            '"method":"not reported","passage_ids":["P1"]}'
                        },
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 24},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = SarvamChatCompletionsProvider(client)
    try:
        result = provider.complete_json(
            schema_name="veda_appraisal_probe_v1",
            schema_model=AppraisalProbe,
            system="Classify only the supplied passage.",
            user='source_id=S1; passage_id=P1; text="Methods not reported."',
            max_output_tokens=256,
            budget_ceiling_inr=5.0,
        )
    finally:
        provider.close()
        client.close()

    assert captured["path"] == "/v2/chat/completions"
    assert captured["auth_header_present"] is True
    assert captured["auth_value"] == "fixture-secret"
    request = captured["payload"]
    assert request["model"] == "sarvam-105b"
    assert request["max_tokens"] == 256
    assert request["stream"] is False
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True
    assert "reasoning_effort" not in request
    assert result.value.source_id == "S1"
    assert result.usage.provider == "sarvam"
    assert result.usage.model == "sarvam-105b"
    assert result.usage.cost_currency == "INR"
    assert result.usage.reported_cost_amount is None
    assert result.usage.estimated_cost_amount == pytest.approx(0.003528)


def test_sarvam_transmits_report_sentence_and_length_constraints(monkeypatch):
    import app.providers.sarvam as sarvam

    monkeypatch.setattr(sarvam, "settings", SarvamSettings())
    captured = {}
    body = {
        "model": "sarvam-105b",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps(
                        {
                            "schema_version": 3,
                            "findings": [],
                            "qualifications": [],
                            "decision_implications": [],
                            "unanswered_questions": [],
                            "company_specific_inputs": [],
                        }
                    )
                },
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=body)

    provider = SarvamChatCompletionsProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        provider.complete_json(
            schema_name="veda_report_draft_v3",
            schema_model=ResearchReportDraft,
            system="Return a concise report draft.",
            user="Use only supplied claim evidence.",
            max_output_tokens=512,
            budget_ceiling_inr=5.0,
        )
    finally:
        provider.close()

    schema = captured["response_format"]["json_schema"]["schema"]["$defs"]
    finding_statement = schema["ReportFinding"]["properties"]["statement"]
    qualification_statement = schema["ReportQualification"]["properties"]["statement"]
    assert finding_statement["maxLength"] == 239
    assert finding_statement["pattern"] == r".*[.!?]$"
    assert qualification_statement["maxLength"] == 219
    assert qualification_statement["pattern"] == r".*[.!?]$"


def test_glm53_flash_has_model_specific_capability_and_price_profile():
    from app.config import Settings
    from app.providers.registry import configured_model

    config = Settings(
        llm_provider="sarvam",
        sarvam_api_key="fixture-secret",
        sarvam_model="glm5.3-flash",
        sarvam_max_job_cost_inr=20.0,
        allow_paid_llm_calls=True,
    )
    profile = configured_model("sarvam", "glm5.3-flash", config=config)

    assert profile.ready is True
    assert profile.strict_json_schema is True
    assert profile.max_context_tokens == 1_048_576
    assert profile.max_completion_tokens == 1_048_576
    assert profile.reasoning_control is True
    assert profile.input_price_per_million == 13.5
    assert profile.output_price_per_million == 45.0
    assert profile.cost_reservation_multiplier == 1.2


def test_glm53_flash_request_uses_reasoning_effort_and_preserves_aggregate_usage(monkeypatch):
    import app.providers.sarvam as sarvam

    monkeypatch.setattr(sarvam, "settings", GlmFlashSarvamSettings())
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "glm5.3-flash",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"status":"assessed","source_id":"S1",'
                            '"method":"not reported","passage_ids":["P1"]}'
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 200,
                    "completion_tokens_details": {"reasoning_tokens": 50},
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = SarvamChatCompletionsProvider(client, model="glm5.3-flash")
    try:
        result = provider.complete_json(
            schema_name="veda_appraisal_probe_v1",
            schema_model=AppraisalProbe,
            system="Classify only the supplied passage.",
            user='source_id=S1; passage_id=P1; text="Methods not reported."',
            max_output_tokens=8192,
            budget_ceiling_inr=1.0,
            reasoning_effort="low",
        )
    finally:
        provider.close()
        client.close()

    assert captured["payload"]["model"] == "glm5.3-flash"
    assert captured["payload"]["max_tokens"] == 8192
    assert captured["payload"]["reasoning_effort"] == "low"
    assert captured["payload"]["response_format"]["json_schema"]["strict"] is True
    assert result.usage.output_tokens == 200
    assert result.usage.reasoning_tokens == 50
    assert result.usage.estimated_cost_amount == pytest.approx(0.01242)
    assert provider.capabilities.supported_reasoning_efforts == {"low", "high", "max"}
    assert "reasoning_effort" in provider.capabilities.supported_parameters


def test_sarvam_105b_keeps_its_own_completion_cap_and_rejects_glm_reasoning(monkeypatch):
    import app.providers.sarvam as sarvam

    monkeypatch.setattr(sarvam, "settings", SarvamSettings())
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = SarvamChatCompletionsProvider(client)
    try:
        with pytest.raises(LLMProviderError) as cap_error:
            provider.complete_json(
                schema_name="veda_appraisal_probe_v1",
                schema_model=AppraisalProbe,
                system="Classify only the supplied passage.",
                user='source_id=S1; passage_id=P1; text="Methods not reported."',
                max_output_tokens=8192,
                budget_ceiling_inr=5.0,
            )
        with pytest.raises(LLMProviderError) as effort_error:
            provider.complete_json(
                schema_name="veda_appraisal_probe_v1",
                schema_model=AppraisalProbe,
                system="Classify only the supplied passage.",
                user='source_id=S1; passage_id=P1; text="Methods not reported."',
                max_output_tokens=256,
                budget_ceiling_inr=5.0,
                reasoning_effort="low",
            )
    finally:
        provider.close()
        client.close()

    assert cap_error.value.code == "provider_token_limit_exceeded"
    assert effort_error.value.code == "unsupported_reasoning_effort"
    assert calls == 0


@pytest.mark.parametrize(
    ("body", "expected_code"),
    [
        (
            {
                "model": "sarvam-105b",
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": '{"status":"assessed"'},
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
            "provider_output_truncated",
        ),
        (
            {
                "model": "sarvam-105b",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"refusal": "declined", "content": None},
                    }
                ],
            },
            "provider_refusal",
        ),
        (
            {
                "model": "sarvam-105b",
                "choices": [{"finish_reason": "stop", "message": {"content": "not json"}}],
            },
            "invalid_structured_response",
        ),
        (
            {
                "model": "other-model",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"status":"assessed","source_id":"S1",'
                            '"method":"x","passage_ids":["P1"]}'
                        },
                    }
                ],
            },
            "unexpected_model_route",
        ),
    ],
)
def test_sarvam_rejects_unverified_structured_outputs(monkeypatch, body, expected_code):
    import app.providers.sarvam as sarvam

    monkeypatch.setattr(sarvam, "settings", SarvamSettings())
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=body))
    )
    provider = SarvamChatCompletionsProvider(client)
    try:
        with pytest.raises(LLMProviderError) as error:
            provider.complete_json(
                schema_name="veda_appraisal_probe_v1",
                schema_model=AppraisalProbe,
                system="Classify only the supplied passage.",
                user='source_id=S1; passage_id=P1; text="Methods not reported."',
                max_output_tokens=256,
                budget_ceiling_inr=5.0,
            )
    finally:
        provider.close()
        client.close()
    assert error.value.code == expected_code


def test_sarvam_schema_failure_reports_only_safe_validation_types_and_paths(monkeypatch):
    import app.providers.sarvam as sarvam

    monkeypatch.setattr(sarvam, "settings", SarvamSettings())
    body = {
        "model": "sarvam-105b",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": '{"status":"assessed","source_id":"S1","method":"x"}'},
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10},
    }
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=body))
    )
    provider = SarvamChatCompletionsProvider(client)
    try:
        with pytest.raises(LLMProviderError) as error:
            provider.complete_json(
                schema_name="veda_appraisal_probe_v1",
                schema_model=AppraisalProbe,
                system="Classify the supplied passage.",
                user="source S1 passage P1",
                max_output_tokens=256,
                budget_ceiling_inr=5.0,
            )
    finally:
        provider.close()
        client.close()

    assert error.value.code == "schema_validation_failed"
    assert error.value.validation_error_types == ("missing",)
    assert error.value.validation_error_paths == ("passage_ids",)
    assert "fixture-secret" not in repr(error.value.validation_error_paths)


def test_unknown_provider_json_key_is_not_persisted_as_validation_path(monkeypatch):
    import app.providers.sarvam as sarvam

    monkeypatch.setattr(sarvam, "settings", SarvamSettings())
    payload = {
        "status": "assessed",
        "source_id": "S1",
        "method": "abstract only",
        "passage_ids": ["P1"],
        "fixturesecret": "sensitive-provider-value",
    }
    body = {
        "model": "sarvam-105b",
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload)}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10},
    }
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=body))
    )
    provider = SarvamChatCompletionsProvider(client)
    try:
        with pytest.raises(LLMProviderError) as error:
            provider.complete_json(
                schema_name="veda_appraisal_probe_v1",
                schema_model=AppraisalProbe,
                system="Classify the supplied passage.",
                user="source S1 passage P1",
                max_output_tokens=256,
                budget_ceiling_inr=5.0,
            )
    finally:
        provider.close()
        client.close()

    assert error.value.code == "schema_validation_failed"
    assert error.value.validation_error_types == ("extra_forbidden",)
    assert error.value.validation_error_paths == ()
    assert "fixturesecret" not in repr(error.value.validation_error_paths)
    assert "sensitive-provider-value" not in repr(error.value.validation_error_paths)


def test_sarvam_429_is_sanitized_and_never_retried(monkeypatch):
    import app.providers.sarvam as sarvam

    monkeypatch.setattr(sarvam, "settings", SarvamSettings())
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            headers={"Retry-After": "45"},
            json={"error": {"code": "rate_limit_exceeded_error", "message": "sensitive"}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = SarvamChatCompletionsProvider(client)
    try:
        with pytest.raises(LLMProviderError) as error:
            provider.complete_json(
                schema_name="veda_appraisal_probe_v1",
                schema_model=AppraisalProbe,
                system="Classify only the supplied passage.",
                user='source_id=S1; passage_id=P1; text="Methods not reported."',
                max_output_tokens=256,
                budget_ceiling_inr=5.0,
            )
    finally:
        provider.close()
        client.close()

    assert calls == 1
    assert error.value.code == "provider_rate_limited"
    assert error.value.failure_kind == "rate_limited"
    assert error.value.cooldown_scope == "account"
    assert error.value.retry_after_seconds == 45
    assert "sensitive" not in str(error.value)


def test_sarvam_unknown_usage_is_explicit_and_not_reported_as_zero(monkeypatch):
    import app.providers.sarvam as sarvam

    monkeypatch.setattr(sarvam, "settings", SarvamSettings())
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "sarvam-105b",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": '{"status":"assessed","source_id":"S1",'
                                '"method":"not reported","passage_ids":["P1"]}'
                            },
                        }
                    ],
                },
            )
        )
    )
    provider = SarvamChatCompletionsProvider(client)
    try:
        result = provider.complete_json(
            schema_name="veda_appraisal_probe_v1",
            schema_model=AppraisalProbe,
            system="Classify only the supplied passage.",
            user='source_id=S1; passage_id=P1; text="Methods not reported."',
            max_output_tokens=256,
            budget_ceiling_inr=5.0,
        )
    finally:
        provider.close()
        client.close()

    assert result.usage.input_tokens is None
    assert result.usage.output_tokens is None
    assert result.usage.reported_cost_amount is None
    assert result.usage.estimated_cost_amount is None


def test_sarvam_cost_ceiling_rejects_before_dispatch(monkeypatch):
    import app.providers.sarvam as sarvam

    monkeypatch.setattr(sarvam, "settings", SarvamSettings())
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = SarvamChatCompletionsProvider(client)
    try:
        with pytest.raises(LLMProviderError) as error:
            provider.complete_json(
                schema_name="veda_appraisal_probe_v1",
                schema_model=AppraisalProbe,
                system="Classify only the supplied passage.",
                user='source_id=S1; passage_id=P1; text="Methods not reported."',
                max_output_tokens=256,
                budget_ceiling_inr=0.001,
            )
    finally:
        provider.close()
        client.close()

    assert error.value.code == "budget_exceeded"
    assert error.value.cost_currency == "INR"
    assert error.value.estimated_cost_amount is not None
    assert error.value.estimated_cost_amount > 0.001
    assert calls == 0
