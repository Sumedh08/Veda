import json
import math
import re
import threading
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.providers.contracts import (
    ModelProvider,
    ProviderAuthentication,
    ProviderCapabilities,
    ProviderFailureKind,
    ProviderIdentity,
    ProviderRequestContext,
    ProviderUsage,
    StructuredResult,
)
from app.providers.registry import configured_model
from app.providers.retry import (
    parse_retry_after_seconds,
    repair_json_envelope,
)

T = TypeVar("T", bound=BaseModel)
MAX_PROMPT_CHARS = 40_000
# The largest completion allocation Veda can request from its current adapters.
# Provider-specific documented ceilings are checked separately where known.
# A shared transport ceiling, separate from provider/model and research-depth
# limits. GLM can accept larger allocations, while normal Veda stages stay smaller.
MAX_OUTPUT_TOKENS = 16_384
SAFE_FINISH_REASONS = frozenset(
    {"stop", "length", "content_filter", "tool_calls", "function_call", "error", "other"}
)
PROVIDER_FAILURE_KINDS = {
    "provider_refusal": ProviderFailureKind.REFUSAL,
    "provider_output_truncated": ProviderFailureKind.TRUNCATED,
    "provider_rate_limited": ProviderFailureKind.RATE_LIMITED,
    "provider_insufficient_credits": ProviderFailureKind.QUOTA,
    "provider_http_401": ProviderFailureKind.AUTHENTICATION,
    "provider_http_403": ProviderFailureKind.AUTHENTICATION,
    "provider_timeout": ProviderFailureKind.TIMEOUT,
    "provider_connect_failed": ProviderFailureKind.TRANSPORT,
    "provider_transport_error": ProviderFailureKind.TRANSPORT,
    "invalid_provider_json": ProviderFailureKind.STRUCTURED_OUTPUT,
    "invalid_provider_envelope": ProviderFailureKind.STRUCTURED_OUTPUT,
    "invalid_structured_response": ProviderFailureKind.STRUCTURED_OUTPUT,
    "unsupported_response_format": ProviderFailureKind.STRUCTURED_OUTPUT,
    "schema_validation_failed": ProviderFailureKind.STRUCTURED_OUTPUT,
    "unexpected_model_route": ProviderFailureKind.ROUTE,
    "provider_route_changed": ProviderFailureKind.ROUTE,
    "free_route_guard_tripped": ProviderFailureKind.ROUTE,
    "budget_exceeded": ProviderFailureKind.BUDGET,
    "paid_calls_disabled": ProviderFailureKind.BUDGET,
    "provider_token_limit_exceeded": ProviderFailureKind.BUDGET,
}
_openrouter_free_route_guard_lock = threading.Lock()
_openrouter_free_route_guard_tripped = False


def _trip_openrouter_free_route_guard() -> None:
    global _openrouter_free_route_guard_tripped
    with _openrouter_free_route_guard_lock:
        _openrouter_free_route_guard_tripped = True


def _openrouter_free_route_guard_is_tripped() -> bool:
    with _openrouter_free_route_guard_lock:
        return _openrouter_free_route_guard_tripped


class LLMProviderError(Exception):
    """Provider failure that is safe to show without exposing credentials or raw payloads."""

    def __init__(
        self,
        message: str,
        *,
        reported_cost_usd: float | None = None,
        estimated_cost_usd: float | None = None,
        code: str = "provider_error",
        outcome_uncertain: bool = False,
        finish_reason: str | None = None,
        model_name: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        latency_ms: int | None = None,
        reported_cost_amount: float | None = None,
        estimated_cost_amount: float | None = None,
        cost_currency: str = "USD",
        retry_after_seconds: float | None = None,
        cooldown_scope: str = "unknown",
        validation_error_types: tuple[str, ...] = (),
        validation_error_paths: tuple[str, ...] = (),
    ):
        super().__init__(message)
        self.reported_cost_usd = reported_cost_usd
        self.estimated_cost_usd = estimated_cost_usd
        self.code = code
        self.failure_kind = PROVIDER_FAILURE_KINDS.get(code, ProviderFailureKind.OTHER)
        self.outcome_uncertain = outcome_uncertain
        self.finish_reason = _safe_finish_reason(finish_reason)
        self.model_name = _safe_model_identifier(model_name)
        self.input_tokens = _safe_int(input_tokens)
        self.output_tokens = _safe_int(output_tokens)
        self.reasoning_tokens = _safe_int(reasoning_tokens)
        self.latency_ms = _safe_latency_ms(latency_ms)
        self.reported_cost_amount = _safe_currency_amount(reported_cost_amount)
        self.estimated_cost_amount = _safe_currency_amount(estimated_cost_amount)
        self.cost_currency = cost_currency if re.fullmatch(r"[A-Z]{3}", cost_currency) else "USD"
        self.retry_after_seconds = _safe_cooldown_seconds(retry_after_seconds)
        self.cooldown_scope = (
            cooldown_scope
            if cooldown_scope in {"account", "model", "endpoint", "unknown"}
            else "unknown"
        )
        self.validation_error_types = _safe_validation_error_values(validation_error_types)
        self.validation_error_paths = _safe_validation_error_paths(validation_error_paths)


class OpenRouterProvider:
    def __init__(self, client: httpx.Client | None = None, *, model: str | None = None) -> None:
        if not settings.openrouter_api_key:
            raise LLMProviderError(
                "OpenRouter is selected but OPENROUTER_API_KEY is not configured."
            )
        model = model or settings.openrouter_model
        if model != "openrouter/free" and not model.endswith(":free"):
            raise LLMProviderError("Only OpenRouter free model routes are enabled for Veda.")
        self.model = model
        self.identity = ProviderIdentity("openrouter", model)
        self.authentication = ProviderAuthentication(
            environment_variable="OPENROUTER_API_KEY",
            header_name="Authorization",
            value_prefix="Bearer",
        )
        self.capabilities = ProviderCapabilities(
            strict_json_schema=None,
            supported_parameters=frozenset(
                {"model", "messages", "max_tokens", "temperature", "response_format", "provider"}
            ),
            max_context_tokens=None,
            # Route-specific limits are not verified here. Veda's global
            # transport ceiling is separate from this unknown route limit.
            max_completion_tokens=None,
            reasoning_control=True,
            rate_limit_scope="account",
            cost_currency="USD",
            input_price_per_million=0.0,
            output_price_per_million=0.0,
        )
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=httpx.Timeout(40, connect=8))

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def complete_json(
        self,
        *,
        schema_name: str,
        schema_model: type[T],
        system: str,
        user: str,
        max_output_tokens: int = 1200,
        budget_ceiling_usd: float | None = None,
        budget_ceiling_inr: float | None = None,
        model: str | None = None,
        request_context: ProviderRequestContext | None = None,
        reasoning_effort: str | None = None,
    ) -> StructuredResult[T]:
        if reasoning_effort is not None:
            raise LLMProviderError(
                "This OpenRouter adapter does not expose a validated reasoning-effort parameter.",
                code="unsupported_reasoning_effort",
            )
        if _openrouter_free_route_guard_is_tripped():
            raise LLMProviderError(
                "OpenRouter free-route verification failed earlier; no further requests were sent.",
                code="free_route_guard_tripped",
            )
        _validate_request(system, user, schema_name, max_output_tokens)
        if model is not None and model != self.model:
            raise LLMProviderError(
                "OpenRouter job model differs from the initialized provider route.",
                code="unexpected_model_route",
            )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_output_tokens,
            "temperature": 0,
            # OpenRouter otherwise may select an endpoint that ignores response_format.
            "provider": {
                "require_parameters": True,
                "allow_fallbacks": False,
                "max_price": {"prompt": 0, "completion": 0, "request": 0},
            },
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema_model.model_json_schema(),
                },
            },
            "usage": {"include": True},
        }
        reasoning_enabled = getattr(settings, "openrouter_reasoning_enabled", None)
        if type(reasoning_enabled) is bool:
            payload["reasoning"] = {"enabled": reasoning_enabled}
        started = time.monotonic()
        try:
            response = self.client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                    "X-Title": "Veda Research",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 429:
                raise LLMProviderError(
                    "OpenRouter free-tier rate limit reached; retry later.",
                    code="provider_rate_limited",
                    retry_after_seconds=parse_retry_after_seconds(exc.response.headers),
                    cooldown_scope="account",
                ) from exc
            if status_code in {400, 422} and _is_unsupported_response_format_error(
                _error_object(exc.response)
            ):
                _trip_openrouter_free_route_guard()
                raise LLMProviderError(
                    "The selected OpenRouter route does not support the required JSON Schema response format.",
                    code="unsupported_response_format",
                ) from exc
            if status_code >= 500:
                _trip_openrouter_free_route_guard()
            raise LLMProviderError(
                f"OpenRouter request failed with HTTP {status_code}.",
                code=(
                    f"provider_http_{status_code}"
                    if 400 <= status_code < 600
                    else "provider_http_error"
                ),
                outcome_uncertain=status_code >= 500,
            ) from exc
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise LLMProviderError(
                "OpenRouter connection could not be established.",
                code="provider_connect_failed",
            ) from exc
        except httpx.TimeoutException as exc:
            _trip_openrouter_free_route_guard()
            raise LLMProviderError(
                "OpenRouter response timed out; the provider outcome is uncertain.",
                code="provider_timeout",
                outcome_uncertain=True,
            ) from exc
        except httpx.HTTPError as exc:
            _trip_openrouter_free_route_guard()
            raise LLMProviderError(
                "OpenRouter transport failed; the provider outcome is uncertain.",
                code="provider_transport_error",
                outcome_uncertain=True,
            ) from exc
        except ValueError as exc:
            _trip_openrouter_free_route_guard()
            raise LLMProviderError(
                "OpenRouter returned invalid JSON; the provider outcome is uncertain.",
                code="invalid_provider_json",
                outcome_uncertain=True,
            ) from exc

        try:
            if not isinstance(body, dict):
                _trip_openrouter_free_route_guard()
                raise LLMProviderError(
                    "OpenRouter returned an invalid response envelope; route and cost could not be verified.",
                    code="invalid_provider_envelope",
                    outcome_uncertain=True,
                )
            usage = body.get("usage")
            if not isinstance(usage, dict):
                usage = {}
            returned_model = _safe_model_identifier(body.get("model"))
            failure_diagnostics = {
                "model_name": returned_model,
                "input_tokens": _safe_int(usage.get("prompt_tokens")),
                "output_tokens": _safe_int(usage.get("completion_tokens")),
                "reasoning_tokens": _reasoning_tokens(usage),
                "latency_ms": _elapsed_ms(started),
            }
            if "error" in body:
                error_code = (
                    "unsupported_response_format"
                    if _is_unsupported_response_format_error(body.get("error"))
                    else "provider_upstream_error"
                )
                # HTTP 200 may still contain an upstream failure after processing began.
                # Never infer a free route or zero cost from omitted response metadata.
                _trip_openrouter_free_route_guard()
                message = (
                    "The selected OpenRouter route rejected the required JSON Schema response format."
                    if error_code == "unsupported_response_format"
                    else "OpenRouter returned an upstream error in its completion envelope."
                )
                raise LLMProviderError(
                    message,
                    reported_cost_usd=_safe_reported_cost(usage.get("cost")),
                    code=error_code,
                    outcome_uncertain=True,
                    **failure_diagnostics,
                )
            if returned_model is None:
                _trip_openrouter_free_route_guard()
                raise LLMProviderError(
                    "OpenRouter did not identify the selected model; the response was not accepted.",
                    code="missing_model_identity",
                    outcome_uncertain=True,
                    **failure_diagnostics,
                )
            is_dynamic_free_route = self.model == "openrouter/free"
            route_mismatch = returned_model != self.model and not (
                is_dynamic_free_route and returned_model.endswith(":free")
            )
            if route_mismatch:
                _trip_openrouter_free_route_guard()
                raise LLMProviderError(
                    "OpenRouter returned a model outside the free route; the response was not accepted.",
                    code="unexpected_model_route",
                    outcome_uncertain=True,
                    **failure_diagnostics,
                )

            reported_cost = _safe_float(usage.get("cost"))
            if reported_cost is None:
                _trip_openrouter_free_route_guard()
                raise LLMProviderError(
                    "OpenRouter did not report request cost; the response was not accepted.",
                    code="missing_reported_cost",
                    outcome_uncertain=True,
                    **failure_diagnostics,
                )
            if not math.isfinite(reported_cost) or reported_cost < 0:
                _trip_openrouter_free_route_guard()
                raise LLMProviderError(
                    "OpenRouter reported an invalid request cost; the response was not accepted.",
                    code="invalid_reported_cost",
                    outcome_uncertain=True,
                    **failure_diagnostics,
                )
            if reported_cost > 0:
                _trip_openrouter_free_route_guard()
                raise LLMProviderError(
                    "OpenRouter reported a non-zero model cost; the result was not accepted.",
                    reported_cost_usd=reported_cost,
                    code="nonzero_reported_cost",
                    outcome_uncertain=True,
                    **failure_diagnostics,
                )

            choices = body.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise LLMProviderError(
                    "OpenRouter returned no structured response choice.",
                    reported_cost_usd=reported_cost,
                    estimated_cost_usd=0.0,
                    code="invalid_provider_envelope",
                    **failure_diagnostics,
                )
            choice = choices[0]
            finish_reason = _safe_finish_reason(choice.get("finish_reason"))
            if not isinstance(choice.get("message"), dict):
                raise LLMProviderError(
                    "OpenRouter returned an invalid structured response message.",
                    reported_cost_usd=reported_cost,
                    estimated_cost_usd=0.0,
                    code="invalid_provider_envelope",
                    finish_reason=finish_reason,
                    **failure_diagnostics,
                )
            message = choice["message"]
            if message.get("refusal") or choice.get("finish_reason") == "content_filter":
                raise LLMProviderError(
                    "OpenRouter declined this structured request.",
                    reported_cost_usd=reported_cost,
                    estimated_cost_usd=0.0,
                    code="provider_refusal",
                    finish_reason=finish_reason,
                    **failure_diagnostics,
                )
            if choice.get("finish_reason") == "length":
                raise LLMProviderError(
                    "OpenRouter truncated the structured response at its output limit.",
                    reported_cost_usd=reported_cost,
                    estimated_cost_usd=0.0,
                    code="provider_output_truncated",
                    finish_reason=finish_reason,
                    **failure_diagnostics,
                )
            content = message.get("content")
            if isinstance(content, list):
                content = "".join(
                    item["text"]
                    for item in content
                    if isinstance(item, dict) and isinstance(item.get("text"), str)
                )
            try:
                parsed, response_repair = _repair_and_validate_json(content, schema_model)
            except (ValidationError, ValueError, TypeError) as exc:
                raise LLMProviderError(
                    "OpenRouter returned JSON that did not match the requested structured schema.",
                    reported_cost_usd=reported_cost,
                    estimated_cost_usd=0.0,
                    code="invalid_structured_response",
                    finish_reason=finish_reason,
                    **failure_diagnostics,
                ) from exc
            return StructuredResult(
                value=parsed,
                usage=ProviderUsage(
                    provider="openrouter",
                    model=returned_model,
                    input_tokens=_safe_int(usage.get("prompt_tokens")),
                    output_tokens=_safe_int(usage.get("completion_tokens")),
                    reported_cost_usd=reported_cost,
                    estimated_cost_usd=0.0,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    response_repair=response_repair,
                    finish_reason=finish_reason,
                    reasoning_tokens=_reasoning_tokens(usage),
                ),
            )
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(
                "OpenRouter returned an unexpected structured-response envelope.",
                code="invalid_provider_envelope",
            ) from exc


class OpenAIResponsesProvider:
    def __init__(self, client: httpx.Client | None = None, *, model: str | None = None) -> None:
        if not settings.openai_api_key:
            raise LLMProviderError("OpenAI is selected but OPENAI_API_KEY is not configured.")
        if not settings.allow_paid_llm_calls:
            raise LLMProviderError("Paid OpenAI calls require ALLOW_PAID_LLM_CALLS=true.")
        if (
            settings.openai_input_price_per_million is None
            or settings.openai_output_price_per_million is None
        ):
            raise LLMProviderError(
                "Configure current OpenAI input and output prices before enabling paid calls."
            )
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=httpx.Timeout(45, connect=8))
        self.model = model or settings.openai_model_fast
        self.identity = ProviderIdentity("openai", self.model or "configured-model")
        self.authentication = ProviderAuthentication(
            environment_variable="OPENAI_API_KEY",
            header_name="Authorization",
            value_prefix="Bearer",
        )
        self.capabilities = ProviderCapabilities(
            strict_json_schema=True,
            supported_parameters=frozenset(
                {"model", "input", "max_output_tokens", "text.format", "store"}
            ),
            max_context_tokens=None,
            # The configured model's published ceiling is not part of these
            # settings; Veda's global transport ceiling is applied separately.
            max_completion_tokens=None,
            reasoning_control=True,
            rate_limit_scope="account",
            cost_currency="USD",
            input_price_per_million=settings.openai_input_price_per_million,
            output_price_per_million=settings.openai_output_price_per_million,
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def complete_json(
        self,
        *,
        schema_name: str,
        schema_model: type[T],
        system: str,
        user: str,
        max_output_tokens: int = 1200,
        budget_ceiling_usd: float,
        budget_ceiling_inr: float | None = None,
        model: str | None = None,
        request_context: ProviderRequestContext | None = None,
        reasoning_effort: str | None = None,
    ) -> StructuredResult[T]:
        if reasoning_effort is not None:
            raise LLMProviderError(
                "This OpenAI adapter does not expose a validated reasoning-effort profile for the selected model.",
                code="unsupported_reasoning_effort",
            )
        _validate_request(system, user, schema_name, max_output_tokens)
        model_name = model or self.model
        if model_name != self.identity.model:
            raise LLMProviderError(
                "OpenAI job model differs from the initialized provider route.",
                code="unexpected_model_route",
            )
        if not model_name:
            raise LLMProviderError(
                "Set OPENAI_MODEL_FAST to a currently supported structured-output model."
            )
        max_estimate = maximum_cost_estimate(
            system,
            user,
            max_output_tokens,
            schema_name=schema_name,
            schema_model=schema_model,
        )
        if max_estimate > budget_ceiling_usd:
            raise LLMProviderError(
                f"The conservative request estimate (${max_estimate:.4f}) exceeds this job's budget ceiling."
            )
        payload = {
            "model": model_name,
            "store": False,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_output_tokens": max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema_model.model_json_schema(),
                }
            },
        }
        started = time.monotonic()
        try:
            response = self.client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            error_body = _error_object(exc.response)
            if status == 429:
                if _openai_hard_quota_exhausted(error_body):
                    raise LLMProviderError(
                        "OpenAI account quota is exhausted.",
                        code="provider_insufficient_credits",
                    ) from exc
                if _openai_transient_rate_limit(exc.response):
                    raise LLMProviderError(
                        "OpenAI account rate limit reached; no automatic retry was sent.",
                        code="provider_rate_limited",
                        retry_after_seconds=parse_retry_after_seconds(exc.response.headers),
                        cooldown_scope="account",
                    ) from exc
            raise LLMProviderError(
                f"OpenAI request failed with HTTP {status}.",
                code=("provider_http_429" if status == 429 else "provider_error"),
                outcome_uncertain=status >= 500,
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMProviderError(
                "OpenAI could not be reached or returned invalid JSON.", outcome_uncertain=True
            ) from exc

        try:
            text_parts: list[str] = []
            for item in body.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "refusal":
                        raise LLMProviderError(
                            "OpenAI declined this structured request.", outcome_uncertain=True
                        )
                    if content.get("type") == "output_text":
                        text_parts.append(content.get("text", ""))
            parsed, response_repair = _repair_and_validate_json("".join(text_parts), schema_model)
            usage = body.get("usage") or {}
            input_tokens = _safe_int(usage.get("input_tokens"))
            output_tokens = _safe_int(usage.get("output_tokens"))
            reasoning_tokens = _safe_int(
                (usage.get("output_tokens_details") or {}).get("reasoning_tokens")
                if isinstance(usage.get("output_tokens_details"), dict)
                else None
            )
            estimate = _cost_for_tokens(input_tokens, output_tokens)
            if estimate is None:
                estimate = max_estimate
            if estimate > budget_ceiling_usd:
                raise LLMProviderError(
                    "OpenAI usage exceeded the job budget estimate; result was not accepted.",
                    estimated_cost_usd=estimate,
                    code="budget_exceeded",
                )
            return StructuredResult(
                value=parsed,
                usage=ProviderUsage(
                    provider="openai",
                    model=str(body.get("model") or model_name),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    reported_cost_usd=None,
                    estimated_cost_usd=estimate,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    response_repair=response_repair,
                    reasoning_tokens=reasoning_tokens,
                ),
            )
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(
                "OpenAI response did not match the requested schema.", outcome_uncertain=True
            ) from exc


def create_model_provider(provider: str, model: str | None) -> ModelProvider:
    """Construct an adapter for one validated provider/model profile."""
    if provider == "openrouter":
        return OpenRouterProvider(model=model)
    if provider == "openai":
        return OpenAIResponsesProvider(model=model)
    if provider == "sarvam":
        from app.providers.sarvam import SarvamChatCompletionsProvider

        return SarvamChatCompletionsProvider(model=model)
    raise LLMProviderError("The configured provider/model is not registered.")


def configured_provider() -> ModelProvider | None:
    if settings.llm_provider == "disabled":
        return None
    profile = configured_model(config=settings)
    if not profile.ready or not profile.model:
        raise LLMProviderError(profile.reason or "The selected provider/model is not ready.")
    return create_model_provider(profile.provider, profile.model)


def _openai_transient_rate_limit(response: httpx.Response) -> bool:
    if response.status_code != 429:
        return False
    try:
        error = response.json().get("error")
    except (ValueError, AttributeError):
        return False
    return (
        isinstance(error, dict)
        and error.get("type") in {None, "rate_limit_error"}
        and error.get("code") in {"rate_limit_exceeded", "slow_down"}
    )


def _openai_hard_quota_exhausted(error: object) -> bool:
    if not isinstance(error, dict):
        return False
    return error.get("type") == "insufficient_quota" or error.get("code") in {
        "insufficient_quota",
        "credit_balance_exhausted",
    }


def _repair_and_validate_json[T: BaseModel](
    value: object, schema_model: type[T]
) -> tuple[T, str | None]:
    """Apply only lossless envelope normalization, then enforce the original schema."""
    normalized, repair_name = repair_json_envelope(value)
    return schema_model.model_validate_json(normalized), repair_name


def _safe_validation_error_summary(
    exc: ValidationError, schema_model: type[BaseModel]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return bounded diagnostics; only known schema fields and array indexes form paths."""
    error_types: list[str] = []
    error_paths: list[str] = []
    known_fields = _json_schema_field_names(schema_model.model_json_schema())
    for item in exc.errors(include_url=False, include_context=False, include_input=False)[:12]:
        error_type = item.get("type")
        if isinstance(error_type, str):
            error_types.append(error_type)
        location = item.get("loc")
        if isinstance(location, tuple | list):
            parts = [str(part) for part in location if isinstance(part, (str, int))]
            if parts and all(
                (part in known_fields and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", part))
                or re.fullmatch(r"\d{1,5}", part)
                for part in parts
            ):
                error_paths.append(".".join(parts)[:160])
    return _safe_validation_error_values(error_types), _safe_validation_error_paths(error_paths)


def _json_schema_field_names(schema: object) -> set[str]:
    """Collect field keys from Veda's trusted schema, never from provider JSON."""
    field_names: set[str] = set()
    pending = [schema]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            properties = current.get("properties")
            if isinstance(properties, dict):
                field_names.update(
                    name
                    for name in properties
                    if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name)
                )
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return field_names


def _safe_validation_error_values(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    safe: list[str] = []
    for value in values[:12]:
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value):
            if value not in safe:
                safe.append(value)
    return tuple(safe)


def _safe_validation_error_paths(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Keep only bounded schema paths composed of field names and array indexes."""
    safe: list[str] = []
    segment = r"(?:[A-Za-z0-9_-]{1,64}|\d{1,5})"
    pattern = rf"{segment}(?:\.{segment}){{0,12}}"
    for value in values[:12]:
        if isinstance(value, str) and len(value) <= 160 and re.fullmatch(pattern, value):
            if value not in safe:
                safe.append(value)
    return tuple(safe)


def _validate_request(system: str, user: str, name: str, max_output_tokens: int) -> None:
    if not system.strip() or not user.strip() or len(system) + len(user) > MAX_PROMPT_CHARS:
        raise LLMProviderError("Prompt is empty or exceeds Veda's configured request size limit.")
    if not name.replace("_", "").isalnum() or not 1 <= len(name) <= 64:
        raise LLMProviderError("Structured-output schema name is invalid.")
    if not 1 <= max_output_tokens <= MAX_OUTPUT_TOKENS:
        raise LLMProviderError("Structured-output token limit is outside Veda's configured bounds.")


def maximum_cost_estimate(
    system: str,
    user: str,
    max_output_tokens: int,
    *,
    schema_name: str,
    schema_model: type[BaseModel],
) -> float:
    input_token_estimate = maximum_input_token_estimate(
        system, user, schema_name=schema_name, schema_model=schema_model
    )
    return (
        input_token_estimate * float(settings.openai_input_price_per_million) / 1_000_000
        + max_output_tokens * float(settings.openai_output_price_per_million) / 1_000_000
    )


def maximum_input_token_estimate(
    system: str,
    user: str,
    *,
    schema_name: str,
    schema_model: type[BaseModel],
) -> int:
    """Return a conservative UTF-8 byte envelope, not provider tokenizer output."""
    schema_bytes = len(
        json.dumps(schema_model.model_json_schema(), separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    )
    # One token usually covers multiple UTF-8 bytes; bytes plus schema and framing
    # is a deliberately conservative cross-provider budget envelope.
    return (
        len(system.encode("utf-8"))
        + len(user.encode("utf-8"))
        + schema_bytes
        + len(schema_name)
        + 1024
    )


def _cost_for_tokens(input_tokens: int | None, output_tokens: int | None) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    return (
        input_tokens * float(settings.openai_input_price_per_million) / 1_000_000
        + output_tokens * float(settings.openai_output_price_per_million) / 1_000_000
    )


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if type(value) is int:
        return value if 0 <= value <= 1_000_000 else None
    if isinstance(value, str) and value.isdecimal():
        parsed = int(value)
        return parsed if parsed <= 1_000_000 else None
    return None


def _safe_model_identifier(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 160:
        return None
    return normalized if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/+-]*", normalized) else None


def _safe_latency_ms(value: Any) -> int | None:
    if type(value) is int and 0 <= value <= 3_600_000:
        return value
    return None


def _safe_currency_amount(value: Any) -> float | None:
    parsed = _safe_float(value)
    if parsed is not None and math.isfinite(parsed) and 0 <= parsed <= 100_000:
        return parsed
    return None


def _safe_cooldown_seconds(value: Any) -> float | None:
    parsed = _safe_float(value)
    if parsed is not None and math.isfinite(parsed) and 0 <= parsed <= 86_400:
        return parsed
    return None


def _elapsed_ms(started: float) -> int:
    return max(0, min(3_600_000, int((time.monotonic() - started) * 1000)))


def _reasoning_tokens(usage: dict[str, Any]) -> int | None:
    details = usage.get("completion_tokens_details")
    return _safe_int(details.get("reasoning_tokens")) if isinstance(details, dict) else None


def _safe_finish_reason(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return "other"
    normalized = value.strip().lower()
    return normalized if normalized in SAFE_FINISH_REASONS else "other"


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_reported_cost(value: Any) -> float | None:
    parsed = _safe_float(value)
    if parsed is None or not math.isfinite(parsed) or not 0 <= parsed <= 20:
        return None
    return parsed


def _error_object(response: httpx.Response) -> object:
    """Read only enough of a provider error envelope for safe classification."""
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("error") if isinstance(body, dict) else None


def _is_unsupported_response_format_error(error: object) -> bool:
    """Classify stable error fields without retaining upstream prose or payloads."""
    if not isinstance(error, dict):
        return False
    code = error.get("code")
    error_type = error.get("type")
    param = error.get("param")
    normalized_code = code.casefold() if isinstance(code, str) else ""
    normalized_type = error_type.casefold() if isinstance(error_type, str) else ""
    normalized_param = param.casefold() if isinstance(param, str) else ""
    return (
        normalized_code in {"unsupported_response_format", "response_format_not_supported"}
        or normalized_type in {"unsupported_response_format", "response_format_not_supported"}
        or (
            normalized_param == "response_format"
            and normalized_code in {"unsupported_parameter", "invalid_request_error", "400"}
        )
    )
