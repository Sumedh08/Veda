"""Verify current OpenRouter catalog and endpoint metadata before T-112.

This performs read-only public catalog requests only. It never reads a key and
never dispatches a model completion. Inference must still set provider
require_parameters, disable fallbacks, and cap every price at zero.
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
T112_MODEL = "nvidia/nemotron-3.5-super-vl:free"


def _zero(value: object) -> bool:
    if value is None:
        return False
    try:
        return Decimal(str(value)) == 0
    except (InvalidOperation, ValueError):
        return False


def validate_route_metadata(
    models_payload: dict[str, Any],
    endpoints_payload: dict[str, Any],
    *,
    model_id: str = T112_MODEL,
    checked_at: str | None = None,
) -> dict[str, Any]:
    """Return a sanitized preflight record or reject the route fail-closed."""
    if not model_id.endswith(":free"):
        raise ValueError("T-112 requires a concrete OpenRouter :free model route.")

    model = next(
        (
            item
            for item in models_payload.get("data", [])
            if isinstance(item, dict) and item.get("id") == model_id
        ),
        None,
    )
    if model is None:
        raise ValueError("The requested free model is absent from the current catalog.")

    pricing = model.get("pricing") if isinstance(model.get("pricing"), dict) else {}
    model_parameters = set(model.get("supported_parameters") or [])
    if not _zero(pricing.get("prompt")) or not _zero(pricing.get("completion")):
        raise ValueError("The model catalog no longer reports zero prompt and completion prices.")
    if not {"response_format", "structured_outputs"}.issubset(model_parameters):
        raise ValueError("The model catalog no longer lists Veda's structured-output parameters.")

    endpoint_items = endpoints_payload.get("data", {}).get("endpoints", [])
    eligible_endpoints: list[dict[str, Any]] = []
    for endpoint in endpoint_items:
        if not isinstance(endpoint, dict):
            continue
        endpoint_pricing = endpoint.get("pricing")
        endpoint_pricing = endpoint_pricing if isinstance(endpoint_pricing, dict) else {}
        endpoint_parameters = set(endpoint.get("supported_parameters") or [])
        if (
            _zero(endpoint_pricing.get("prompt"))
            and _zero(endpoint_pricing.get("completion"))
            and {"response_format", "structured_outputs"}.issubset(endpoint_parameters)
        ):
            eligible_endpoints.append(
                {
                    "name": endpoint.get("name"),
                    "provider": endpoint.get("provider_name"),
                    "prompt_price": str(endpoint_pricing.get("prompt")),
                    "completion_price": str(endpoint_pricing.get("completion")),
                    "request_price": (
                        None
                        if endpoint_pricing.get("request") is None
                        else str(endpoint_pricing.get("request"))
                    ),
                    "supports_response_format": True,
                    "supports_structured_outputs": True,
                }
            )
    if not eligible_endpoints:
        raise ValueError(
            "No current endpoint simultaneously reports zero token prices and Veda's structured-output parameters."
        )

    return {
        "checked_at": checked_at or datetime.now(UTC).isoformat(),
        "inference_request_sent": False,
        "eligible": True,
        "model_id": model_id,
        "model_prompt_price": str(pricing.get("prompt")),
        "model_completion_price": str(pricing.get("completion")),
        "model_request_price": (
            None if pricing.get("request") is None else str(pricing.get("request"))
        ),
        "supports_response_format": True,
        "supports_structured_outputs": True,
        "zero_price_endpoints": eligible_endpoints,
        "dispatch_constraints": {
            "require_parameters": True,
            "allow_fallbacks": False,
            "max_price": {"prompt": 0, "completion": 0, "request": 0},
        },
        "limitations": [
            "Catalog metadata is a point-in-time observation and may change before dispatch.",
            "A null request-price field is not a reported numeric zero; dispatch must retain max_price.request=0.",
            "Only the inference response can confirm its actual model identity and reported cost.",
        ],
    }


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(
        url, headers={"Accept": "application/json", "User-Agent": "Veda-T112-preflight"}
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


def fetch_route_metadata(model_id: str = T112_MODEL) -> dict[str, Any]:
    # The `:free` suffix names the free route's endpoint set. Stripping it
    # would inspect the model's paid provider endpoints and produce a false
    # negative (or, worse, encourage dispatch against the wrong route).
    author, slug = model_id.split("/", 1)
    models_payload = _fetch_json(f"{API_ROOT}/models")
    endpoint_url = f"{API_ROOT}/models/{quote(author, safe='')}/{quote(slug, safe='')}/endpoints"
    endpoints_payload = _fetch_json(endpoint_url)
    return validate_route_metadata(models_payload, endpoints_payload, model_id=model_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=T112_MODEL)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        record = fetch_route_metadata(args.model)
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(json.dumps({"eligible": False, "inference_request_sent": False, "error": str(exc)}))
        return 2
    serialized = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            print(
                json.dumps(
                    {
                        "eligible": False,
                        "error": "Refusing to replace an existing preflight artifact.",
                    }
                )
            )
            return 2
        args.output.write_text(serialized, encoding="utf-8")
    sys.stdout.write(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
