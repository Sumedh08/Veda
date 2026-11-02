"""Provider-neutral contracts for Veda's structured model operations.

Research schemas remain in ``app.research.llm_tasks``. This module describes only
transport capabilities and the normalized provider identity used around them.
Quota reservation and replay safety remain owned by the persisted workflow.
"""

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ProviderFailureKind(StrEnum):
    REFUSAL = "refusal"
    TRUNCATED = "truncated"
    RATE_LIMITED = "rate_limited"
    QUOTA = "quota"
    AUTHENTICATION = "authentication"
    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    STRUCTURED_OUTPUT = "structured_output"
    ROUTE = "route"
    BUDGET = "budget"
    OTHER = "other"


@dataclass(frozen=True)
class ProviderAuthentication:
    """Public authentication shape; never contains the credential itself."""

    environment_variable: str
    header_name: str
    value_prefix: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", self.environment_variable):
            raise ValueError("provider credential setting must be an environment-variable name")
        if not re.fullmatch(r"[A-Za-z0-9-]{1,80}", self.header_name):
            raise ValueError("provider authentication header name is invalid")
        if self.value_prefix is not None and not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_-]{0,39}", self.value_prefix
        ):
            raise ValueError("provider authentication prefix is invalid")


@dataclass(frozen=True)
class ProviderIdentity:
    provider: str
    model: str

    def __post_init__(self) -> None:
        if not self.provider or len(self.provider) > 40:
            raise ValueError("provider identity must be a bounded non-empty provider id")
        if not self.model or len(self.model) > 160:
            raise ValueError("provider identity must be a bounded non-empty model id")


@dataclass(frozen=True)
class ProviderCapabilities:
    # None means route/model metadata has not verified native enforcement.
    strict_json_schema: bool | None
    supported_parameters: frozenset[str]
    max_context_tokens: int | None
    max_completion_tokens: int | None
    reasoning_control: bool
    rate_limit_scope: str
    cost_currency: str
    input_price_per_million: float | None
    output_price_per_million: float | None
    supported_reasoning_efforts: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.rate_limit_scope not in {"account", "model", "endpoint", "unknown"}:
            raise ValueError("provider rate-limit scope is not recognized")
        if len(self.cost_currency) != 3 or not self.cost_currency.isalpha():
            raise ValueError("provider cost currency must be a three-letter code")
        for value in (self.max_context_tokens, self.max_completion_tokens):
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError("provider token ceilings must be positive integers or unknown")
        for value in (self.input_price_per_million, self.output_price_per_million):
            if value is not None and (value < 0 or value != value or value == float("inf")):
                raise ValueError("provider price metadata must be finite and non-negative")


@dataclass(frozen=True)
class ProviderRequestContext:
    """Workflow-owned reservation and replay identity passed to a provider adapter.

    Adapters must not create a second Veda reservation or automatically resend an
    uncertain inference POST. Vendor idempotency headers are used only when that
    vendor documents support for the specific endpoint.
    """

    reservation_id: str
    request_hash: str
    reserved_cost_amount: float
    cost_currency: str
    no_automatic_retry: bool = True

    def __post_init__(self) -> None:
        if not self.reservation_id or len(self.reservation_id) > 36:
            raise ValueError("provider request reservation id is invalid")
        if len(self.request_hash) != 64 or any(
            char not in "0123456789abcdef" for char in self.request_hash
        ):
            raise ValueError("provider request hash must be a lowercase SHA-256 digest")
        if (
            isinstance(self.reserved_cost_amount, bool)
            or not isinstance(self.reserved_cost_amount, (int, float))
            or not math.isfinite(self.reserved_cost_amount)
            or self.reserved_cost_amount < 0
        ):
            raise ValueError("reserved provider cost must be non-negative")
        if len(self.cost_currency) != 3 or not self.cost_currency.isalpha():
            raise ValueError("reserved provider cost currency must be a three-letter code")
        if self.no_automatic_retry is not True:
            raise ValueError("Veda structured inference POSTs must not be automatically retried")


@dataclass(frozen=True)
class ProviderUsage:
    """Normalized provider usage; missing billing data remains explicitly unknown."""

    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    reported_cost_usd: float | None
    estimated_cost_usd: float | None
    latency_ms: int
    response_repair: str | None = None
    finish_reason: str | None = None
    reasoning_tokens: int | None = None
    reported_cost_amount: float | None = None
    estimated_cost_amount: float | None = None
    cost_currency: str = "USD"

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not re.fullmatch(
            r"[a-z][a-z0-9_-]{0,39}", self.provider
        ):
            raise ValueError("provider usage must identify a bounded normalized provider id")
        if not isinstance(self.model, str) or not self.model or len(self.model) > 160:
            raise ValueError("provider usage model must be a bounded non-empty string")
        for name, value in (
            ("input_tokens", self.input_tokens),
            ("output_tokens", self.output_tokens),
            ("reasoning_tokens", self.reasoning_tokens),
        ):
            if value is not None and (type(value) is not int or not 0 <= value <= 1_000_000):
                raise ValueError(f"provider usage {name} must be a bounded non-negative integer")
        if type(self.latency_ms) is not int or not 0 <= self.latency_ms <= 3_600_000:
            raise ValueError("provider usage latency must be bounded to one hour")
        for name, value in (
            ("reported_cost_usd", self.reported_cost_usd),
            ("estimated_cost_usd", self.estimated_cost_usd),
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= 20
            ):
                raise ValueError(f"provider usage {name} must be finite and within the product cap")
        if self.response_repair is not None and (
            not isinstance(self.response_repair, str) or len(self.response_repair) > 80
        ):
            raise ValueError("provider usage response-repair marker exceeds its boundary")
        if self.finish_reason is not None and self.finish_reason not in {
            "stop",
            "length",
            "content_filter",
            "tool_calls",
            "function_call",
            "error",
            "other",
        }:
            raise ValueError("provider usage finish reason is not allowlisted")
        if not re.fullmatch(r"[A-Z]{3}", self.cost_currency):
            raise ValueError("provider usage cost currency must be a three-letter code")
        for name, value in (
            ("reported_cost_amount", self.reported_cost_amount),
            ("estimated_cost_amount", self.estimated_cost_amount),
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= 100_000
            ):
                raise ValueError(f"provider usage {name} must be finite and bounded")


@dataclass(frozen=True)
class StructuredResult[T]:
    value: T
    usage: ProviderUsage


@runtime_checkable
class ModelProvider(Protocol):
    """Common structured-generation seam implemented by each vendor adapter."""

    identity: ProviderIdentity
    capabilities: ProviderCapabilities
    authentication: ProviderAuthentication

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
        """Return a validated result without retrying an uncertain inference POST.

        The workflow persists reservations and replay state before calling the adapter.
        """
        ...

    def close(self) -> None: ...
