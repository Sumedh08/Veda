import json

import httpx
import pytest
from pydantic import BaseModel

import app.providers.llm as llm
from app.providers.llm import LLMProviderError, OpenRouterProvider


class Output(BaseModel):
    ok: bool


@pytest.fixture(autouse=True)
def reset_openrouter_free_route_guard(monkeypatch):
    monkeypatch.setattr(llm, "_openrouter_free_route_guard_tripped", False)


def test_openrouter_requires_free_model_and_returns_structured_usage(monkeypatch):
    class Config:
        openrouter_api_key = "test-secret"
        openrouter_model = "openrouter/free"
        openrouter_reasoning_enabled = False

    monkeypatch.setattr(llm, "settings", Config())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-secret"
        body = json.loads(request.content)
        assert body["response_format"]["type"] == "json_schema"
        assert body["provider"]["require_parameters"] is True
        assert body["provider"]["allow_fallbacks"] is False
        assert body["provider"]["max_price"] == {
            "prompt": 0,
            "completion": 0,
            "request": 0,
        }
        assert body["reasoning"] == {"enabled": False}
        return httpx.Response(
            200,
            json={
                "model": "provider/example:free",
                "choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "completion_tokens_details": {"reasoning_tokens": 1},
                    "cost": 0,
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(client)
    result = provider.complete_json(
        schema_name="test_output",
        schema_model=Output,
        system="You return JSON.",
        user="Return ok true.",
    )
    provider.close()
    client.close()

    assert result.value.ok is True
    assert result.usage.provider == "openrouter"
    assert result.usage.reported_cost_usd == 0
    assert result.usage.finish_reason == "stop"
    assert result.usage.reasoning_tokens == 1


def test_openrouter_removes_one_json_fence_and_records_the_lossless_repair(monkeypatch):
    class Config:
        openrouter_api_key = "test-secret"
        openrouter_model = "openrouter/free"

    monkeypatch.setattr(llm, "settings", Config())
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "provider/example:free",
                    "choices": [
                        {
                            "message": {
                                "content": "```json" + chr(10) + '{"ok":true}' + chr(10) + "```"
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 3, "cost": 0},
                },
            )
        )
    )
    provider = OpenRouterProvider(client)
    result = provider.complete_json(
        schema_name="test_output",
        schema_model=Output,
        system="Return JSON.",
        user="Return ok true.",
    )
    client.close()

    assert result.value.ok is True
    assert result.usage.response_repair == "markdown_json_fence_removed"


def test_openrouter_rate_limit_is_reported_without_resending(monkeypatch):
    class Config:
        openrouter_api_key = "test-secret"
        openrouter_model = "openrouter/free"

    monkeypatch.setattr(llm, "settings", Config())
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            headers={"Retry-After": "45"},
            json={"error": {"type": "rate_limit_error", "code": "rate_limit_exceeded"}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(client)
    with pytest.raises(LLMProviderError) as error:
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
        )
    client.close()

    assert error.value.code == "provider_rate_limited"
    assert error.value.retry_after_seconds == 45
    assert error.value.cooldown_scope == "account"
    assert calls == 1


def test_openai_does_not_retry_hard_quota_429(monkeypatch):
    class Config:
        openai_api_key = "test-key"
        openai_model_fast = "fixture-model"
        allow_paid_llm_calls = True
        openai_input_price_per_million = 0.1
        openai_output_price_per_million = 0.5

    monkeypatch.setattr(llm, "settings", Config())
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            json={"error": {"type": "insufficient_quota", "code": "credit_balance_exhausted"}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = llm.OpenAIResponsesProvider(client)
    with pytest.raises(LLMProviderError):
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
            budget_ceiling_usd=1.0,
        )
    client.close()
    assert calls == 1


def test_openai_rate_limit_is_reported_without_resending(monkeypatch):
    class Config:
        openai_api_key = "test-key"
        openai_model_fast = "fixture-model"
        allow_paid_llm_calls = True
        openai_input_price_per_million = 0.1
        openai_output_price_per_million = 0.5

    monkeypatch.setattr(llm, "settings", Config())
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            headers={"Retry-After": "30"},
            json={"error": {"type": "rate_limit_error", "code": "slow_down"}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = llm.OpenAIResponsesProvider(client)
    with pytest.raises(LLMProviderError) as error:
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
            budget_ceiling_usd=1.0,
        )
    client.close()

    assert error.value.code == "provider_rate_limited"
    assert error.value.retry_after_seconds == 30
    assert calls == 1


def test_openrouter_does_not_resend_ambiguous_or_schema_invalid_responses(monkeypatch):
    class Config:
        openrouter_api_key = "test-secret"
        openrouter_model = "openrouter/free"

    monkeypatch.setattr(llm, "settings", Config())
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"other":true}'}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(client)
    with pytest.raises(LLMProviderError) as error:
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
        )
    client.close()

    assert calls == 1
    assert error.value.outcome_uncertain is True


def test_openrouter_rejects_nonzero_reported_cost(monkeypatch):
    class Config:
        openrouter_api_key = "test-secret"
        openrouter_model = "openrouter/free"

    monkeypatch.setattr(llm, "settings", Config())
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "model": "provider/example:free",
                    "choices": [{"message": {"content": '{"ok":true}'}}],
                    "usage": {"cost": 0.01},
                },
            )
        )
    )
    provider = OpenRouterProvider(client)
    with pytest.raises(LLMProviderError, match="non-zero model cost"):
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
        )
    client.close()


def test_openrouter_classifies_schema_failure_with_verified_zero_cost(monkeypatch):
    class Config:
        openrouter_api_key = "test-secret"
        openrouter_model = "openrouter/free"

    monkeypatch.setattr(llm, "settings", Config())
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "provider/example:free",
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": '{"other":true}'}}
                    ],
                    "usage": {"cost": 0},
                },
            )
        )
    )
    provider = OpenRouterProvider(client)
    with pytest.raises(LLMProviderError) as error:
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
        )
    client.close()

    assert error.value.code == "invalid_structured_response"
    assert error.value.outcome_uncertain is False
    assert error.value.reported_cost_usd == 0


def test_openrouter_normalizes_unrecognized_finish_reason_without_persisting_provider_text(
    monkeypatch,
):
    class Config:
        openrouter_api_key = "test-secret"
        openrouter_model = "openrouter/free"

    monkeypatch.setattr(llm, "settings", Config())
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "provider/example:free",
                    "choices": [
                        {
                            "finish_reason": "provider-private-finish-detail",
                            "message": {"content": '{"ok":true}'},
                        }
                    ],
                    "usage": {"cost": 0},
                },
            )
        )
    )
    provider = OpenRouterProvider(client)

    result = provider.complete_json(
        schema_name="test_output",
        schema_model=Output,
        system="Return JSON.",
        user="Return ok true.",
    )

    provider.close()
    client.close()
    assert result.usage.finish_reason == "other"
    assert "provider-private-finish-detail" not in str(result.usage)


@pytest.mark.parametrize(
    ("choice", "expected_code"),
    [
        (
            {"finish_reason": "content_filter", "message": {"content": ""}},
            "provider_refusal",
        ),
        (
            {"finish_reason": "stop", "message": {"refusal": "declined", "content": ""}},
            "provider_refusal",
        ),
        (
            {"finish_reason": "length", "message": {"content": '{"ok":'}},
            "provider_output_truncated",
        ),
        (
            {"finish_reason": "stop", "message": {"content": '{"ok":'}},
            "invalid_structured_response",
        ),
    ],
)
def test_openrouter_classifies_refusal_truncation_and_malformed_json(
    monkeypatch, choice, expected_code
):
    class Config:
        openrouter_api_key = "test-secret"
        openrouter_model = "openrouter/free"

    monkeypatch.setattr(llm, "settings", Config())
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "provider/example:free",
                    "choices": [choice],
                    "usage": {"cost": 0},
                },
            )
        )
    )
    provider = OpenRouterProvider(client)
    with pytest.raises(LLMProviderError) as error:
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
        )
    client.close()

    assert error.value.code == expected_code
    assert error.value.outcome_uncertain is False
    assert error.value.reported_cost_usd == 0
    assert error.value.finish_reason == choice["finish_reason"]


def test_openrouter_truncation_preserves_verified_route_and_usage_metadata(monkeypatch):
    class Config:
        openrouter_api_key = "test-secret"
        openrouter_model = "openrouter/free"

    monkeypatch.setattr(llm, "settings", Config())
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "provider/example:free",
                    "choices": [{"finish_reason": "length", "message": {"content": '{"ok":'}}],
                    "usage": {
                        "prompt_tokens": 211,
                        "completion_tokens": 1200,
                        "completion_tokens_details": {"reasoning_tokens": 900},
                        "cost": 0,
                    },
                },
            )
        )
    )
    provider = OpenRouterProvider(client)

    with pytest.raises(LLMProviderError) as error:
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
            max_output_tokens=1200,
        )
    client.close()

    assert error.value.code == "provider_output_truncated"
    assert error.value.model_name == "provider/example:free"
    assert error.value.input_tokens == 211
    assert error.value.output_tokens == 1200
    assert error.value.reasoning_tokens == 900
    assert error.value.reported_cost_usd == 0
    assert error.value.latency_ms is not None
    assert error.value.finish_reason == "length"


@pytest.mark.parametrize(
    ("status", "body", "expected_code"),
    [
        (
            400,
            {"error": {"code": "unsupported_response_format", "message": "private detail"}},
            "unsupported_response_format",
        ),
        (
            200,
            {
                "error": {
                    "code": "unsupported_response_format",
                    "message": "private detail",
                    "param": "response_format",
                }
            },
            "unsupported_response_format",
        ),
        (
            200,
            {"error": {"code": "upstream_failure", "message": "private detail"}},
            "provider_upstream_error",
        ),
    ],
)
def test_openrouter_classifies_unsupported_format_and_http_200_error_without_leaking_body(
    monkeypatch, status, body, expected_code
):
    class Config:
        openrouter_api_key = "test-secret"
        openrouter_model = "openrouter/free"

    monkeypatch.setattr(llm, "settings", Config())
    requests = []
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(status, json=body)
        )
    )
    provider = OpenRouterProvider(client)

    with pytest.raises(LLMProviderError) as error:
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
        )
    client.close()

    assert error.value.code == expected_code
    assert error.value.outcome_uncertain is (status == 200)
    assert error.value.reported_cost_usd is None
    assert len(requests) == 1
    assert "private detail" not in str(error.value)
    assert "test-secret" not in str(error.value)


def test_openrouter_classifies_timeout_without_retry_or_payload_leak(monkeypatch):
    class Config:
        openrouter_api_key = "test-secret"
        openrouter_model = "openrouter/free"

    monkeypatch.setattr(llm, "settings", Config())
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("provider diagnostic contains no retained body")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(client)
    with pytest.raises(LLMProviderError) as error:
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
        )
    client.close()

    assert calls == 1
    assert error.value.code == "provider_timeout"
    assert error.value.outcome_uncertain is True
    assert "diagnostic" not in str(error.value)
    assert "test-secret" not in str(error.value)
    with pytest.raises(LLMProviderError) as blocked:
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
        )
    assert calls == 1
    assert blocked.value.code == "free_route_guard_tripped"


def test_openrouter_classifies_malformed_provider_json_as_uncertain_and_stops_followup_calls(
    monkeypatch,
):
    class Config:
        openrouter_api_key = "test-secret"
        openrouter_model = "openrouter/free"

    monkeypatch.setattr(llm, "settings", Config())
    requests = []
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: (
                requests.append(request) or httpx.Response(200, content=b"{not valid JSON")
            )
        )
    )
    provider = OpenRouterProvider(client)
    with pytest.raises(LLMProviderError) as error:
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
        )
    with pytest.raises(LLMProviderError) as blocked:
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
        )
    client.close()

    assert error.value.code == "invalid_provider_json"
    assert error.value.outcome_uncertain is True
    assert blocked.value.code == "free_route_guard_tripped"
    assert len(requests) == 1


def test_openrouter_keeps_missing_token_counts_unknown_when_zero_cost_is_reported(monkeypatch):
    class Config:
        openrouter_api_key = "test-secret"
        openrouter_model = "openrouter/free"

    monkeypatch.setattr(llm, "settings", Config())
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "provider/example:free",
                    "choices": [{"message": {"content": '{"ok":true}'}}],
                    "usage": {"cost": 0},
                },
            )
        )
    )
    provider = OpenRouterProvider(client)
    result = provider.complete_json(
        schema_name="test_output",
        schema_model=Output,
        system="Return JSON.",
        user="Return ok true.",
    )
    client.close()

    assert result.usage.input_tokens is None
    assert result.usage.output_tokens is None
    assert result.usage.reported_cost_usd == 0


@pytest.mark.parametrize(
    ("body", "expected_code"),
    [
        (
            {
                "model": "provider/example:free",
                "choices": [{"message": {"content": '{"ok":true}'}}],
                "usage": {},
            },
            "missing_reported_cost",
        ),
        (
            {
                "model": "provider/example-paid",
                "choices": [{"message": {"content": '{"ok":true}'}}],
                "usage": {"cost": 0},
            },
            "unexpected_model_route",
        ),
        (
            {
                "choices": [{"message": {"content": '{"ok":true}'}}],
                "usage": {"cost": 0},
            },
            "missing_model_identity",
        ),
    ],
)
def test_openrouter_rejects_unverified_model_or_cost_and_trips_guard(
    monkeypatch, body, expected_code
):
    class Config:
        openrouter_api_key = "test-secret"
        openrouter_model = "openrouter/free"

    monkeypatch.setattr(llm, "settings", Config())
    requests = []
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(200, json=body)
        )
    )
    provider = OpenRouterProvider(client)
    with pytest.raises(LLMProviderError) as error:
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
        )
    with pytest.raises(LLMProviderError, match="no further requests were sent") as blocked:
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
        )
    client.close()

    assert len(requests) == 1
    assert error.value.code == expected_code
    assert blocked.value.code == "free_route_guard_tripped"


def test_openrouter_rejects_changed_concrete_free_model_route(monkeypatch):
    class Config:
        openrouter_api_key = "test-secret"
        openrouter_model = "provider/selected-model:free"

    monkeypatch.setattr(llm, "settings", Config())
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "provider/other-model:free",
                    "choices": [{"message": {"content": '{"ok":true}'}}],
                    "usage": {"cost": 0},
                },
            )
        )
    )
    provider = OpenRouterProvider(client)

    with pytest.raises(LLMProviderError) as error:
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="Return JSON.",
            user="Return ok true.",
        )
    client.close()

    assert error.value.code == "unexpected_model_route"
    assert error.value.outcome_uncertain is True


def test_paid_openai_requires_explicit_flag_and_price_limits(monkeypatch):
    class Config:
        openai_api_key = "test-key"
        allow_paid_llm_calls = False
        openai_input_price_per_million = 1.0
        openai_output_price_per_million = 2.0

    monkeypatch.setattr(llm, "settings", Config())
    with pytest.raises(LLMProviderError, match="ALLOW_PAID_LLM_CALLS=true"):
        llm.OpenAIResponsesProvider()


def test_paid_openai_zero_budget_is_rejected_before_network_call(monkeypatch):
    class Config:
        openai_api_key = "test-key"
        openai_model_fast = "gpt-6-luna"
        allow_paid_llm_calls = True
        openai_input_price_per_million = 0.1
        openai_output_price_per_million = 0.5

    monkeypatch.setattr(llm, "settings", Config())
    requests = []
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(500)
        )
    )
    provider = llm.OpenAIResponsesProvider(client)
    with pytest.raises(LLMProviderError, match="conservative request estimate"):
        provider.complete_json(
            schema_name="test_output",
            schema_model=Output,
            system="You return JSON.",
            user="Return ok true.",
            budget_ceiling_usd=0.0,
        )
    assert requests == []
    client.close()
