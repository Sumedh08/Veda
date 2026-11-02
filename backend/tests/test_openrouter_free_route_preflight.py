from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "evaluation" / "scripts"))

import verify_openrouter_free_route as preflight  # noqa: E402
from verify_openrouter_free_route import T112_MODEL, validate_route_metadata  # noqa: E402


def _catalog(*, prompt: str = "0", completion: str = "0", params=None):
    return {
        "data": [
            {
                "id": T112_MODEL,
                "pricing": {"prompt": prompt, "completion": completion, "request": None},
                "supported_parameters": params or ["response_format", "structured_outputs"],
            }
        ]
    }


def _endpoints(*, prompt: str = "0", completion: str = "0", params=None):
    return {
        "data": {
            "endpoints": [
                {
                    "name": "Nvidia | nemotron-test:free",
                    "provider_name": "Nvidia",
                    "pricing": {"prompt": prompt, "completion": completion, "request": None},
                    "supported_parameters": params or ["response_format", "structured_outputs"],
                }
            ]
        }
    }


def test_preflight_accepts_only_zero_price_structured_output_free_route():
    result = validate_route_metadata(
        _catalog(),
        _endpoints(),
        checked_at="2026-10-30T00:00:00Z",
    )

    assert result["eligible"] is True
    assert result["inference_request_sent"] is False
    assert result["model_id"] == T112_MODEL
    assert result["dispatch_constraints"] == {
        "require_parameters": True,
        "allow_fallbacks": False,
        "max_price": {"prompt": 0, "completion": 0, "request": 0},
    }
    assert result["zero_price_endpoints"][0]["request_price"] is None


@pytest.mark.parametrize(
    ("models", "endpoints", "message"),
    [
        (_catalog(prompt="0.000001"), _endpoints(), "catalog no longer reports zero"),
        (_catalog(), _endpoints(completion="0.01"), "No current endpoint"),
        (
            _catalog(params=["response_format"]),
            _endpoints(),
            "catalog no longer lists Veda's structured-output parameters",
        ),
        (
            _catalog(),
            _endpoints(params=["response_format"]),
            "No current endpoint",
        ),
        ({"data": []}, _endpoints(), "absent from the current catalog"),
    ],
)
def test_preflight_fails_closed_on_price_or_capability_change(models, endpoints, message):
    with pytest.raises(ValueError, match=message):
        validate_route_metadata(models, endpoints)


def test_preflight_rejects_non_free_route():
    with pytest.raises(ValueError, match="concrete OpenRouter :free"):
        validate_route_metadata(_catalog(), _endpoints(), model_id="nvidia/nemotron-3.5-super-vl")


def test_route_fetch_preserves_free_suffix_when_loading_endpoint_metadata(monkeypatch):
    requested_urls = []

    def fake_fetch(url):
        requested_urls.append(url)
        if url.endswith("/models"):
            return _catalog()
        return _endpoints()

    monkeypatch.setattr(preflight, "_fetch_json", fake_fetch)

    record = preflight.fetch_route_metadata(T112_MODEL)

    assert record["eligible"] is True
    assert requested_urls[1].endswith("/models/nvidia/nemotron-3.5-super-vl%3Afree/endpoints")
