"""Sarvam V2 strict structured-output adapter."""

import math
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.config import settings
from app.providers.contracts import (
    ProviderAuthentication,
    ProviderCapabilities,
    ProviderIdentity,
    ProviderRequestContext,
)
from app.providers.llm import (
    LLMProviderError,
    ProviderUsage,
    StructuredResult,
    _elapsed_ms,
    _repair_and_validate_json,
    _safe_finish_reason,
    _safe_int,
    _safe_model_identifier,
    _safe_reported_cost,
    _safe_validation_error_summary,
    _validate_request,
    maximum_input_token_estimate,
)
from app.providers.registry import SARVAM_MODELS, configured_model
from app.providers.retry import parse_retry_after_seconds

T = TypeVar("T", bound=BaseModel)
CHAT_COMPLETIONS_V2_URL = "https://api.sarvam.ai/v2/chat/completions"
DEFAULT_ACCOUNT_COOLDOWN_SECONDS = 60.0


class SarvamChatCompletionsProvider:
    """Translate Veda's Pydantic operation into Sarvam's V2 request contract."""

    def __init__(self, client: httpx.Client | None = None, *, model: str | None = None) -> None:
        if not settings.sarvam_api_key:
            raise LLMProviderError("Sarvam is selected but SARVAM_API_KEY is not configured.")
        profile = configured_model("sarvam", model, config=settings)
        if not profile.supported or not profile.model:
            raise LLMProviderError(profile.reason or "Sarvam model is not supported by Veda.")
        model_metadata = SARVAM_MODELS[profile.model]
        self.identity = ProviderIdentity("sarvam", profile.model)
        self.authentication = ProviderAuthentication(
            environment_variable="SARVAM_API_KEY",
            header_name="api-subscription-key",
        )
        self.capabilities = ProviderCapabilities(
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
                | ({"reasoning_effort"} if model_metadata["reasoning_control"] else set())
            ),
            max_context_tokens=model_metadata["max_context_tokens"],
            max_completion_tokens=model_metadata["max_completion_tokens"],
            reasoning_control=model_metadata["reasoning_control"],
            rate_limit_scope="account",
            cost_currency="INR",
            input_price_per_million=profile.input_price_per_million,
            output_price_per_million=profile.output_price_per_million,
            supported_reasoning_efforts=model_metadata.get(
                "supported_reasoning_efforts", frozenset()
            ),
        )
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=httpx.Timeout(45, connect=8))

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
        selected_model = model or self.identity.model
        if selected_model != self.identity.model:
            raise LLMProviderError(
                "Sarvam job model differs from the configured model; provider switching is disabled.",
                code="unexpected_model_route",
            )
        if not settings.allow_paid_llm_calls:
            raise LLMProviderError(
                "Sarvam inference requires the explicit paid-call safety setting.",
                code="paid_calls_disabled",
            )
        model_metadata = SARVAM_MODELS[selected_model]
        if model_metadata["reasoning_control"]:
            reasoning_effort = reasoning_effort or model_metadata["default_reasoning_effort"]
            if reasoning_effort not in model_metadata["supported_reasoning_efforts"]:
                raise LLMProviderError(
                    "The selected Sarvam model does not support the requested reasoning effort.",
                    code="unsupported_reasoning_effort",
                )
        elif reasoning_effort is not None:
            raise LLMProviderError(
                "The selected Sarvam model does not support reasoning-effort controls.",
                code="unsupported_reasoning_effort",
            )
        _validate_request(system, user, schema_name, max_output_tokens)
        if max_output_tokens > (self.capabilities.max_completion_tokens or 0):
            raise LLMProviderError(
                "Sarvam completion token cap exceeds the selected model's reviewed limit.",
                code="provider_token_limit_exceeded",
            )
        profile = configured_model("sarvam", selected_model, config=settings)
        input_token_upper_bound = maximum_input_token_estimate(
            system,
            user,
            schema_name=schema_name,
            schema_model=schema_model,
        )
        maximum_cost_inr = profile.maximum_cost(input_token_upper_bound, max_output_tokens)
        if (
            maximum_cost_inr is None
            or budget_ceiling_inr is None
            or not math.isfinite(budget_ceiling_inr)
            or budget_ceiling_inr <= 0
            or maximum_cost_inr > budget_ceiling_inr
        ):
            raise LLMProviderError(
                "The conservative Sarvam request estimate exceeds the configured INR job budget.",
                code="budget_exceeded",
                estimated_cost_amount=maximum_cost_inr,
                cost_currency="INR",
            )

        payload = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_output_tokens,
            "temperature": 0,
            "stream": False,
            "n": 1,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema_model.model_json_schema(),
                },
            },
        }
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort
        started = time.monotonic()
        try:
            # No automatic retry: a POST timeout or provider error can consume usage,
            # and account-level cooldown is persisted by the workflow.
            response = self.client.post(
                CHAT_COMPLETIONS_V2_URL,
                headers={
                    "api-subscription-key": settings.sarvam_api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            error = _error_object(exc.response)
            if status == 429:
                cooldown = parse_retry_after_seconds(exc.response.headers)
                raise LLMProviderError(
                    "Sarvam account rate limit reached; inference is deferred without retry.",
                    code="provider_rate_limited",
                    retry_after_seconds=cooldown or DEFAULT_ACCOUNT_COOLDOWN_SECONDS,
                    cooldown_scope="account",
                ) from exc
            if status == 402:
                raise LLMProviderError(
                    "Sarvam organization credits are exhausted; no retry was sent.",
                    code="provider_insufficient_credits",
                ) from exc
            if status in {400, 422} and _unsupported_response_format(error):
                raise LLMProviderError(
                    "Sarvam rejected the required strict JSON Schema response format.",
                    code="unsupported_response_format",
                ) from exc
            raise LLMProviderError(
                f"Sarvam request failed with HTTP {status}.",
                code=f"provider_http_{status}" if 400 <= status < 600 else "provider_http_error",
                outcome_uncertain=status >= 500,
                retry_after_seconds=parse_retry_after_seconds(exc.response.headers),
                cooldown_scope="account" if status == 503 else "unknown",
            ) from exc
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise LLMProviderError(
                "Sarvam connection could not be established.", code="provider_connect_failed"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMProviderError(
                "Sarvam response timed out; provider outcome is uncertain.",
                code="provider_timeout",
                outcome_uncertain=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(
                "Sarvam transport failed; provider outcome is uncertain.",
                code="provider_transport_error",
                outcome_uncertain=True,
            ) from exc
        except ValueError as exc:
            raise LLMProviderError(
                "Sarvam returned invalid JSON; provider outcome is uncertain.",
                code="invalid_provider_json",
                outcome_uncertain=True,
            ) from exc

        if not isinstance(body, dict):
            raise LLMProviderError(
                "Sarvam returned an invalid structured response envelope.",
                code="invalid_provider_envelope",
                outcome_uncertain=True,
                estimated_cost_amount=maximum_cost_inr,
                cost_currency="INR",
            )
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        input_tokens = _safe_int(usage.get("prompt_tokens"))
        output_tokens = _safe_int(usage.get("completion_tokens"))
        reasoning_tokens = _reasoning_tokens(usage)
        reported_cost = _safe_reported_cost(usage.get("cost"))
        estimated_cost = (
            profile.maximum_cost(input_tokens, output_tokens)
            if input_tokens is not None and output_tokens is not None
            else None
        )
        returned_model = _safe_model_identifier(body.get("model"))
        diagnostics = {
            "model_name": returned_model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "latency_ms": _elapsed_ms(started),
            "reported_cost_amount": reported_cost,
            "estimated_cost_amount": estimated_cost,
            "cost_currency": "INR",
        }
        if "error" in body:
            code = (
                "unsupported_response_format"
                if _unsupported_response_format(body["error"])
                else "provider_upstream_error"
            )
            raise LLMProviderError(
                "Sarvam returned an upstream error envelope; the structured result was rejected.",
                code=code,
                outcome_uncertain=True,
                **diagnostics,
            )
        if returned_model != selected_model:
            raise LLMProviderError(
                "Sarvam response model identity did not match the configured model.",
                code="unexpected_model_route",
                outcome_uncertain=True,
                **diagnostics,
            )
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise LLMProviderError(
                "Sarvam returned no structured response choice.",
                code="invalid_provider_envelope",
                outcome_uncertain=True,
                **diagnostics,
            )
        choice = choices[0]
        finish_reason = _safe_finish_reason(choice.get("finish_reason"))
        message = choice.get("message")
        if not isinstance(message, dict):
            raise LLMProviderError(
                "Sarvam returned an invalid structured response message.",
                code="invalid_provider_envelope",
                finish_reason=finish_reason,
                outcome_uncertain=True,
                **diagnostics,
            )
        if message.get("refusal") or finish_reason == "content_filter":
            raise LLMProviderError(
                "Sarvam declined the structured request.",
                code="provider_refusal",
                finish_reason=finish_reason,
                **diagnostics,
            )
        if finish_reason == "length":
            raise LLMProviderError(
                "Sarvam truncated the structured response at its output limit.",
                code="provider_output_truncated",
                finish_reason=finish_reason,
                **diagnostics,
            )
        try:
            content = _message_text(message.get("content"))
        except (ValueError, TypeError) as exc:
            raise LLMProviderError(
                "Sarvam returned non-text structured content.",
                code="invalid_structured_response",
                finish_reason=finish_reason,
                **diagnostics,
            ) from exc
        try:
            parsed, response_repair = _repair_and_validate_json(content, schema_model)
        except Exception as exc:
            from pydantic import ValidationError

            if isinstance(exc, ValidationError):
                error_types, error_paths = _safe_validation_error_summary(exc, schema_model)
                schema_failure = "json_invalid" not in error_types
                raise LLMProviderError(
                    "Sarvam returned JSON that failed Veda's structured schema validation."
                    if schema_failure
                    else "Sarvam returned malformed structured JSON.",
                    code="schema_validation_failed"
                    if schema_failure
                    else "invalid_structured_response",
                    finish_reason=finish_reason,
                    validation_error_types=error_types,
                    validation_error_paths=error_paths,
                    **diagnostics,
                ) from exc
            if isinstance(exc, (ValueError, TypeError)):
                raise LLMProviderError(
                    "Sarvam returned invalid structured JSON.",
                    code="invalid_structured_response",
                    finish_reason=finish_reason,
                    **diagnostics,
                ) from exc
            raise
        return StructuredResult(
            value=parsed,
            usage=ProviderUsage(
                provider="sarvam",
                model=returned_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                reported_cost_usd=None,
                estimated_cost_usd=None,
                latency_ms=_elapsed_ms(started),
                response_repair=response_repair,
                finish_reason=finish_reason,
                reasoning_tokens=reasoning_tokens,
                reported_cost_amount=reported_cost,
                estimated_cost_amount=estimated_cost,
                cost_currency="INR",
            ),
        )


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        text = "".join(
            item["text"]
            for item in value
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
        if text:
            return text
    raise ValueError("Structured response content was not text")


def _reasoning_tokens(usage: dict[str, Any]) -> int | None:
    details = usage.get("completion_tokens_details")
    return _safe_int(details.get("reasoning_tokens")) if isinstance(details, dict) else None


def _error_object(response: httpx.Response) -> object:
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("error") if isinstance(body, dict) else None


def _unsupported_response_format(error: object) -> bool:
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
        or normalized_param == "response_format"
        and normalized_code in {"unsupported_parameter", "invalid_request_error", "400"}
    )
