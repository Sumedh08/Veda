"""Single source of truth for depth-specific, enforceable research budgets."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DepthProfile:
    name: str
    max_queries: int
    max_records_per_provider_query: int
    max_sources: int
    max_html_pages: int
    max_html_passages: int
    max_passages: int
    max_model_calls: int
    max_prompt_characters_per_call: int
    max_prompt_characters_total: int
    max_prompt_tokens_per_call: int
    max_prompt_token_budget_total: int
    max_output_tokens_per_call: int
    max_output_token_budget_total: int
    max_retries: int
    max_step_seconds: int
    max_pdf_documents: int = 0

    def as_dict(self) -> dict[str, int | str]:
        return asdict(self)


PROFILES: dict[str, DepthProfile] = {
    "quick": DepthProfile(
        name="quick",
        max_queries=3,
        max_records_per_provider_query=3,
        max_sources=8,
        max_html_pages=1,
        max_html_passages=12,
        max_passages=80,
        max_model_calls=16,
        max_prompt_characters_per_call=12_000,
        max_prompt_characters_total=48_000,
        max_prompt_tokens_per_call=18_000,
        max_prompt_token_budget_total=72_000,
        max_output_tokens_per_call=8_192,
        max_output_token_budget_total=131_072,
        max_retries=1,
        max_step_seconds=60,
        max_pdf_documents=1,
    ),
    "standard": DepthProfile(
        name="standard",
        max_queries=4,
        max_records_per_provider_query=5,
        max_sources=14,
        max_html_pages=2,
        max_html_passages=36,
        max_passages=160,
        max_model_calls=24,
        max_prompt_characters_per_call=24_000,
        max_prompt_characters_total=144_000,
        max_prompt_tokens_per_call=30_000,
        max_prompt_token_budget_total=180_000,
        max_output_tokens_per_call=8_192,
        max_output_token_budget_total=196_608,
        max_retries=2,
        max_step_seconds=120,
        max_pdf_documents=2,
    ),
    "deep": DepthProfile(
        name="deep",
        max_queries=5,
        max_records_per_provider_query=8,
        max_sources=24,
        max_html_pages=3,
        max_html_passages=72,
        max_passages=288,
        max_model_calls=40,
        max_prompt_characters_per_call=40_000,
        max_prompt_characters_total=320_000,
        max_prompt_tokens_per_call=52_000,
        max_prompt_token_budget_total=416_000,
        max_output_tokens_per_call=8_192,
        max_output_token_budget_total=245_000,
        max_retries=3,
        max_step_seconds=180,
        max_pdf_documents=3,
    ),
}


def depth_profile(depth: str) -> DepthProfile:
    """Fail closed to the standard profile for legacy or malformed persisted values."""
    return PROFILES.get(depth, PROFILES["standard"])


def profile_for_job(depth: str, saved: object = None) -> DepthProfile:
    """Load the immutable profile snapshot stored with a job, or use today's default."""
    fallback = depth_profile(depth)
    if not isinstance(saved, dict):
        return fallback
    try:
        candidate = DepthProfile(**saved)
    except (TypeError, ValueError):
        return fallback
    if candidate.name != depth:
        return fallback
    return candidate


def public_depth_profiles() -> dict[str, dict[str, int | str]]:
    return {name: profile.as_dict() for name, profile in PROFILES.items()}
