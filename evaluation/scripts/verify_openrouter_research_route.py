"""Read-only compatibility gate for the next bounded OpenRouter research run.

This checks the public catalog and exact model endpoints. It never reads a key
or sends an inference request. Run-time routing still has to enforce zero
prices, required parameters, disabled fallbacks, exact returned model identity,
and reported usage/cost validation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

API_ROOT = "https://openrouter.ai/api/v1"
RESEARCH_MODEL = "xingchen-agi/xing4.0-29b-a4b:free"
MAX_INPUT_TOKENS = 52_000
MAX_OUTPUT_TOKENS = 3_200
REQUIRED_PARAMETERS = {"response_format", "structured_outputs", "reasoning", "max_tokens"}


def _is_zero(value: object) -> bool:
    if value is None:
        return False
    try:
        return Decimal(str(value)) == 0
    except (InvalidOperation, ValueError):
        return False


def validate_research_route(
    models_payload: dict[str, Any],
    endpoints_payload: dict[str, Any],
    *,
    model_id: str = RESEARCH_MODEL,
    checked_at: str | None = None,
) -> dict[str, Any]:
    """Require a free, structured-output route with reasoning disable support and fit."""
    if not model_id.endswith(":free"):
        raise ValueError("Research validation requires a concrete OpenRouter :free model route.")
    model = next(
        (
            item
            for item in models_payload.get("data", [])
            if isinstance(item, dict) and item.get("id") == model_id
        ),
        None,
    )
    if model is None:
        raise ValueError("The selected free model is absent from the current public catalog.")

    pricing = model.get("pricing") if isinstance(model.get("pricing"), dict) else {}
    if not _is_zero(pricing.get("prompt")) or not _is_zero(pricing.get("completion")):
        raise ValueError("The model catalog no longer reports zero prompt and completion prices.")
    model_request_price = pricing.get("request")
    if model_request_price is not None and not _is_zero(model_request_price):
        raise ValueError("The model catalog reports a non-zero request price.")
    model_parameters = set(model.get("supported_parameters") or [])
    if not REQUIRED_PARAMETERS.issubset(model_parameters):
        raise ValueError("The model catalog no longer lists Veda's required request parameters.")

    reasoning = model.get("reasoning")
    if not isinstance(reasoning, dict) or reasoning.get("mandatory") is not False:
        raise ValueError("The model does not explicitly permit reasoning to be disabled.")
    if type(reasoning.get("default_enabled")) is not bool:
        raise ValueError("The model does not publish its default reasoning state.")

    context_length = model.get("context_length")
    model_max_output = (model.get("top_provider") or {}).get("max_completion_tokens")
    if type(context_length) is not int or context_length < MAX_INPUT_TOKENS + MAX_OUTPUT_TOKENS:
        raise ValueError("The model context window is below the bounded deep-depth request envelope.")
    if type(model_max_output) is not int or model_max_output < MAX_OUTPUT_TOKENS:
        raise ValueError("The model completion limit is below Veda's bounded per-call output cap.")

    endpoint_items = (endpoints_payload.get("data") or {}).get("endpoints", [])
    eligible_endpoints: list[dict[str, Any]] = []
    for endpoint in endpoint_items:
        if not isinstance(endpoint, dict):
            continue
        endpoint_pricing = endpoint.get("pricing")
        endpoint_pricing = endpoint_pricing if isinstance(endpoint_pricing, dict) else {}
        endpoint_request_price = endpoint_pricing.get("request")
        endpoint_params = set(endpoint.get("supported_parameters") or [])
        endpoint_context = endpoint.get("context_length")
        endpoint_max_output = endpoint.get("max_completion_tokens")
        if (
            _is_zero(endpoint_pricing.get("prompt"))
            and _is_zero(endpoint_pricing.get("completion"))
            and (endpoint_request_price is None or _is_zero(endpoint_request_price))
            and REQUIRED_PARAMETERS.issubset(endpoint_params)
            and type(endpoint_context) is int
            and endpoint_context >= MAX_INPUT_TOKENS + MAX_OUTPUT_TOKENS
            and type(endpoint_max_output) is int
            and endpoint_max_output >= MAX_OUTPUT_TOKENS
        ):
            eligible_endpoints.append(
                {
                    "provider": endpoint.get("provider_name"),
                    "status": endpoint.get("status"),
                    "quantization": endpoint.get("quantization"),
                    "context_length": endpoint_context,
                    "max_completion_tokens": endpoint_max_output,
                    "prompt_price": str(endpoint_pricing.get("prompt")),
                    "completion_price": str(endpoint_pricing.get("completion")),
                    "request_price": (
                        None if endpoint_request_price is None else str(endpoint_request_price)
                    ),
                    "supported_parameters": sorted(endpoint_params),
                }
            )
    if not eligible_endpoints:
        raise ValueError(
            "No endpoint meets the zero-price, structured-output, reasoning, and token-fit requirements."
        )

    return {
        "checked_at": checked_at or datetime.now(UTC).isoformat(),
        "inference_request_sent": False,
        "eligible": True,
        "model_id": model_id,
        "context_length": context_length,
        "max_completion_tokens": model_max_output,
        "model_prompt_price": str(pricing.get("prompt")),
        "model_completion_price": str(pricing.get("completion")),
        "model_request_price": None if model_request_price is None else str(model_request_price),
        "reasoning": {
            "mandatory": False,
            "default_enabled": reasoning["default_enabled"],
            "dispatch_setting": {"enabled": False},
            "supported_efforts": reasoning.get("supported_efforts"),
        },
        "required_parameters": sorted(REQUIRED_PARAMETERS),
        "eligible_endpoints": eligible_endpoints,
        "dispatch_constraints": {
            "require_parameters": True,
            "allow_fallbacks": False,
            "max_price": {"prompt": 0, "completion": 0, "request": 0},
            "reasoning": {"enabled": False},
            "max_calls_per_job": 6,
        },
        "limitations": [
            "Public metadata is a point-in-time snapshot; it does not guarantee endpoint availability at dispatch.",
            "A null request-price field is unknown, not numeric zero; the request must retain max_price.request=0.",
            "Request-side zero-price caps do not independently establish account-level billing.",
            "Strict JSON Schema enforcement varies by endpoint; Veda's Pydantic validation remains mandatory.",
            "Catalog compatibility does not establish model output quality or scientific reliability.",
        ],
    }


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Veda-free-research-preflight"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = response.read(12_000_001)
    except HTTPError as exc:
        raise RuntimeError(f"OpenRouter public catalog returned HTTP {exc.code}.") from None
    except (TimeoutError, URLError, OSError) as exc:
        raise RuntimeError(
            f"OpenRouter public catalog request failed ({type(exc).__name__})."
        ) from None
    if len(payload) > 12_000_000:
        raise RuntimeError("OpenRouter public catalog response exceeded the 12 MB bound.")
    try:
        result = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("OpenRouter public catalog returned invalid JSON.") from None
    if not isinstance(result, dict):
        raise RuntimeError("OpenRouter public catalog returned an invalid response envelope.")
    return result


def fetch_route_metadata(model_id: str = RESEARCH_MODEL) -> dict[str, Any]:
    author, slug = model_id.split("/", 1)
    models_payload = _fetch_json(f"{API_ROOT}/models")
    endpoint_url = f"{API_ROOT}/models/{quote(author, safe='')}/{quote(slug, safe='')}/endpoints"
    endpoints_payload = _fetch_json(endpoint_url)
    return validate_research_route(models_payload, endpoints_payload, model_id=model_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=RESEARCH_MODEL)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        record = fetch_route_metadata(args.model)
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        sys.stdout.write(
            json.dumps({"eligible": False, "inference_request_sent": False, "error": str(exc)})
            + "\n"
        )
        return 2
    serialized = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            sys.stdout.write(
                json.dumps(
                    {
                        "eligible": False,
                        "error": "Refusing to replace an existing preflight artifact.",
                    }
                )
                + "\n"
            )
            return 2
        args.output.write_text(serialized, encoding="utf-8")
    sys.stdout.write(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
