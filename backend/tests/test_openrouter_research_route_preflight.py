from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "evaluation" / "scripts"))

import verify_openrouter_research_route as preflight  # noqa: E402
from verify_openrouter_research_route import (  # noqa: E402
    RESEARCH_MODEL,
    validate_research_route,
)


def _catalog(
    *,
    prompt: str = "0",
    completion: str = "0",
    request: str | None = None,
    params: list[str] | None = None,
    reasoning: dict | None = None,
    context: int = 262_144,
    max_output: int = 235_929,
):
    return {
        "data": [
            {
                "id": RESEARCH_MODEL,
                "pricing": {"prompt": prompt, "completion": completion, "request": request},
                "supported_parameters": params
                or ["response_format", "structured_outputs", "reasoning", "max_tokens"],
                "reasoning": reasoning or {"mandatory": False, "default_enabled": True},
                "context_length": context,
                "top_provider": {"max_completion_tokens": max_output},
            }
        ]
    }


def _endpoints(
    *,
    prompt: str = "0",
    completion: str = "0",
    request: str | None = None,
    params: list[str] | None = None,
    context: int = 262_144,
    max_output: int = 235_929,
):
    return {
        "data": {
            "endpoints": [
                {
                    "provider_name": "Phala",
                    "status": 0,
                    "quantization": "unknown",
                    "pricing": {"prompt": prompt, "completion": completion, "request": request},
                    "supported_parameters": params
                    or ["response_format", "structured_outputs", "reasoning", "max_tokens"],
                    "context_length": context,
                    "max_completion_tokens": max_output,
                }
            ]
        }
    }


def test_preflight_requires_free_structured_endpoint_and_explicit_reasoning_disable():
    result = validate_research_route(_catalog(), _endpoints(), checked_at="2026-10-30T00:00:00Z")

    assert result["eligible"] is True
    assert result["inference_request_sent"] is False
    assert result["model_id"] == RESEARCH_MODEL
    assert result["reasoning"]["dispatch_setting"] == {"enabled": False}
    assert result["reasoning"]["default_enabled"] is True
    assert result["dispatch_constraints"]["require_parameters"] is True
    assert result["dispatch_constraints"]["allow_fallbacks"] is False
    assert result["dispatch_constraints"]["max_price"] == {
        "prompt": 0,
        "completion": 0,
        "request": 0,
    }
    assert result["eligible_endpoints"][0]["request_price"] is None


@pytest.mark.parametrize(
    ("models", "endpoints", "message"),
    [
        (_catalog(prompt="0.000001"), _endpoints(), "zero prompt and completion"),
        (_catalog(request="0.001"), _endpoints(), "non-zero request price"),
        (_catalog(), _endpoints(completion="0.001"), "No endpoint meets"),
        (
            _catalog(params=["response_format", "structured_outputs", "max_tokens"]),
            _endpoints(),
            "required request parameters",
        ),
        (
            _catalog(reasoning={"mandatory": True, "default_enabled": True}),
            _endpoints(),
            "reasoning to be disabled",
        ),
        (_catalog(context=50_000), _endpoints(), "context window"),
        (_catalog(max_output=2_000), _endpoints(), "completion limit"),
        (
            _catalog(),
            _endpoints(params=["response_format", "structured_outputs", "max_tokens"]),
            "No endpoint meets",
        ),
        (_catalog(), _endpoints(request="0.001"), "No endpoint meets"),
    ],
)
def test_preflight_fails_closed_on_price_reasoning_or_capacity_change(models, endpoints, message):
    with pytest.raises(ValueError, match=message):
        validate_research_route(models, endpoints)


def test_preflight_rejects_router_alias_and_non_free_models():
    for model_id in ("openrouter/free", "xingchen-agi/xing4.0-29b-a4b"):
        with pytest.raises(ValueError, match="concrete OpenRouter :free"):
            validate_research_route(_catalog(), _endpoints(), model_id=model_id)


def test_route_fetch_preserves_free_suffix_for_exact_endpoint_lookup(monkeypatch):
    requested_urls = []

    def fake_fetch(url):
        requested_urls.append(url)
        return _catalog() if url.endswith("/models") else _endpoints()

    monkeypatch.setattr(preflight, "_fetch_json", fake_fetch)

    record = preflight.fetch_route_metadata()

    assert record["eligible"] is True
    assert requested_urls[1].endswith("/models/xingchen-agi/xing4.0-29b-a4b%3Afree/endpoints")
