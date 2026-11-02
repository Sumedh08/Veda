"""Send one non-sensitive schema-validation prompt through OpenRouter's free router."""

import json
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.config import settings
from app.providers.llm import LLMProviderError, OpenRouterProvider


class SmokeReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ready: bool
    marker: Literal["veda-free-provider-smoke"]


def main() -> int:
    if not settings.openrouter_api_key:
        print("OPENROUTER_API_KEY is not configured; no request was sent.", file=sys.stderr)
        return 2
    if settings.openrouter_model != "openrouter/free" and not settings.openrouter_model.endswith(":free"):
        print("Refusing to call a non-free OpenRouter model.", file=sys.stderr)
        return 2
    provider = OpenRouterProvider()
    try:
        result = provider.complete_json(
            schema_name="veda_provider_smoke",
            schema_model=SmokeReply,
            system="Return the requested JSON object exactly. This is a provider connectivity test.",
            user='Return {"ready": true, "marker": "veda-free-provider-smoke"}.',
            max_output_tokens=80,
        )
        if not result.value.ready or result.value.marker != "veda-free-provider-smoke":
            print("Provider responded but did not satisfy the smoke schema.", file=sys.stderr)
            return 1
        print(json.dumps({"status": "passed", "provider": result.usage.provider,
                          "model": result.usage.model, "input_tokens": result.usage.input_tokens,
                          "output_tokens": result.usage.output_tokens,
                          "reported_cost_usd": result.usage.reported_cost_usd,
                          "latency_ms": result.usage.latency_ms}))
        return 0
    except LLMProviderError as exc:
        print(f"Provider smoke test failed: {exc}", file=sys.stderr)
        return 1
    finally:
        provider.close()


if __name__ == "__main__":
    raise SystemExit(main())

