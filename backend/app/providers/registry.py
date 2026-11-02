"""Validated model registry and deployment configuration boundary.

Adding a provider requires one adapter and a registry entry; research stages consume
only the normalized model/provider identity and usage contract.
"""

from dataclasses import dataclass

from app.config import Settings, settings

SARVAM_PRICE_VERIFIED_ON = "2026-10-31"
SARVAM_MODELS = {
    # Current official docs list this stable V2 model and its public token rates.
    # Beta and unverified model ids are intentionally not selectable in Veda yet.
    "sarvam-105b": {
        "max_context_tokens": 128_000,
        "max_completion_tokens": 4_096,  # conservative Starter-plan ceiling
        # V2 documents reasoning_effort for other models; the Sarvam model's
        # reasoning control is documented on V1, so this adapter omits it on V2.
        "reasoning_control": False,
        "supported_reasoning_efforts": frozenset(),
        "default_reasoning_effort": None,
        "input_price_per_million": 15.0,
        "output_price_per_million": 60.0,
        "task_completion_tokens": {},
    },
    # GLM-5.3 Flash has a distinct V2 capability and price profile. These provider
    # ceilings are not Veda generation targets; depth profiles impose tighter caps.
    "glm5.3-flash": {
        "max_context_tokens": 1_048_576,
        "max_completion_tokens": 1_048_576,
        "reasoning_control": True,
        "supported_reasoning_efforts": frozenset({"low", "high", "max"}),
        "default_reasoning_effort": "low",
        "input_price_per_million": 13.5,
        "output_price_per_million": 45.0,
        "task_completion_tokens": {
            "veda_research_plan_selection_v1": 4_096,
            "veda_appraisal_batch_v2": 8_192,
            "veda_comparison_batch_v1": 8_192,
            "veda_report_draft_v3": 8_192,
            "veda_semantic_report_audit_v1": 8_192,
        },
    },
}


@dataclass(frozen=True)
class ConfiguredModel:
    provider: str
    model: str | None
    supported: bool
    credential_available: bool
    ready: bool
    reason: str | None
    currency: str
    input_price_per_million: float | None
    output_price_per_million: float | None
    strict_json_schema: bool | None = None
    max_context_tokens: int | None = None
    max_completion_tokens: int | None = None
    reasoning_control: bool = False
    cost_reservation_multiplier: float = 1.0
    supported_reasoning_efforts: frozenset[str] = frozenset()
    task_completion_tokens: dict[str, int] | None = None

    def maximum_cost(self, input_token_upper_bound: int, completion_token_cap: int) -> float | None:
        if self.input_price_per_million is None or self.output_price_per_million is None:
            return None
        if input_token_upper_bound < 0 or completion_token_cap < 0:
            raise ValueError("token cost bounds must be non-negative")
        return (
            input_token_upper_bound * self.input_price_per_million / 1_000_000
            + completion_token_cap * self.output_price_per_million / 1_000_000
        ) * self.cost_reservation_multiplier


def configured_model(
    provider: str | None = None,
    model: str | None = None,
    *,
    config: Settings | None = None,
) -> ConfiguredModel:
    config = config or settings
    selected_provider = provider or config.llm_provider
    if selected_provider == "disabled":
        return ConfiguredModel(
            "disabled", None, True, False, False, "model provider is disabled", "USD", None, None
        )
    if selected_provider == "openrouter":
        selected_model = model or config.openrouter_model
        supported = selected_model == "openrouter/free" or selected_model.endswith(":free")
        credential = bool(config.openrouter_api_key)
        reason = (
            None
            if supported and credential
            else (
                "unsupported OpenRouter route"
                if not supported
                else "OpenRouter credential is missing"
            )
        )
        return ConfiguredModel(
            selected_provider,
            selected_model,
            supported,
            credential,
            supported and credential,
            reason,
            "USD",
            0.0,
            0.0,
            reasoning_control=True,
            strict_json_schema=None,
        )
    if selected_provider == "openai":
        selected_model = model or config.openai_model_fast
        supported = bool(selected_model and selected_model == config.openai_model_fast)
        credential = bool(config.openai_api_key)
        prices = (
            config.openai_input_price_per_million,
            config.openai_output_price_per_million,
        )
        ready = (
            bool(selected_model and credential and config.allow_paid_llm_calls)
            and all(value is not None for value in prices)
            and supported
        )
        reason = (
            None if ready else "OpenAI model, credential, paid-call gate, or prices are missing"
        )
        return ConfiguredModel(
            selected_provider,
            selected_model or None,
            supported,
            credential,
            ready,
            reason,
            "USD",
            prices[0],
            prices[1],
            reasoning_control=True,
            strict_json_schema=True,
        )
    if selected_provider == "sarvam":
        selected_model = model or config.sarvam_model
        model_metadata = SARVAM_MODELS.get(selected_model)
        credential = bool(config.sarvam_api_key)
        supported = model_metadata is not None
        # Use reviewed model-specific rates; legacy single-model environment
        # prices cannot reduce a registered model's reservation.
        prices = (
            model_metadata.get("input_price_per_million") if model_metadata else None,
            model_metadata.get("output_price_per_million") if model_metadata else None,
        )
        ready = (
            supported
            and credential
            and config.allow_paid_llm_calls
            and config.sarvam_max_job_cost_inr > 0
            and all(value is not None for value in prices)
        )
        if ready:
            reason = None
        elif not supported:
            reason = "Sarvam model is not in Veda's reviewed supported-model registry"
        elif not credential:
            reason = "Sarvam credential is missing"
        elif not config.allow_paid_llm_calls:
            reason = "Sarvam calls require the explicit paid-call safety setting"
        else:
            reason = "Sarvam INR prices or positive per-job INR ceiling are not configured"
        assert model_metadata is None or isinstance(model_metadata, dict)
        return ConfiguredModel(
            selected_provider,
            selected_model,
            supported,
            credential,
            ready,
            reason,
            "INR",
            prices[0],
            prices[1],
            strict_json_schema=True if supported else None,
            max_context_tokens=(
                model_metadata.get("max_context_tokens") if model_metadata else None
            ),
            max_completion_tokens=(
                model_metadata.get("max_completion_tokens") if model_metadata else None
            ),
            reasoning_control=bool(model_metadata and model_metadata.get("reasoning_control")),
            cost_reservation_multiplier=1.2,
            supported_reasoning_efforts=(
                model_metadata.get("supported_reasoning_efforts", frozenset())
                if model_metadata
                else frozenset()
            ),
            task_completion_tokens=(
                model_metadata.get("task_completion_tokens") if model_metadata else None
            ),
        )
    return ConfiguredModel(
        selected_provider,
        model,
        False,
        False,
        False,
        "provider is not registered",
        "USD",
        None,
        None,
    )
