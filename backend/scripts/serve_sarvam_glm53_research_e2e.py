"""Serve an isolated Veda API for one bounded GLM-5.3 Flash research run.

The real planning operation is the first structured compatibility check. There is
no separate synthetic inference probe. Veda's standard job budget, a hard POST
counter, provider allowlist, and one-failure circuit bound the local run.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

MODEL = "glm5.3-flash"
ENDPOINT = "https://api.sarvam.ai/v2/chat/completions"
MAX_PROVIDER_POSTS = 24
MAX_JOB_COST_INR = 20.0
MAX_TOTAL_AUTHORIZED_INR = 25.0


def _evaluation_path(env_name: str, suffix: str, prefix: str) -> Path:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        raise ValueError(f"{env_name} is required before the local run starts.")
    path = Path(raw).resolve()
    evaluation = Path(__file__).resolve().parents[2] / "evaluation"
    try:
        path.relative_to(evaluation.resolve())
    except ValueError:
        raise ValueError(f"{env_name} must remain inside evaluation/.") from None
    if path.suffix.casefold() != suffix or not path.name.startswith(prefix) or path.exists():
        raise ValueError(
            f"{env_name} must name a new evaluation artifact with the expected prefix."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _safe_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value >= 0 and value < float("inf") else None


def _safe_identifier(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value if re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", value) else None


def _safe_failure(exc: Exception, stage: str) -> dict[str, Any]:
    model = getattr(exc, "model_name", None)
    if model != MODEL:
        model = None
    currency = getattr(exc, "cost_currency", None)
    if currency != "INR":
        currency = None
    input_tokens = getattr(exc, "input_tokens", None)
    output_tokens = getattr(exc, "output_tokens", None)
    reasoning_tokens = getattr(exc, "reasoning_tokens", None)
    reported_cost = _safe_number(getattr(exc, "reported_cost_amount", None))
    estimated_cost = _safe_number(getattr(exc, "estimated_cost_amount", None))
    return {
        "stage": stage,
        "error_class": _safe_identifier(getattr(exc, "code", None)) or type(exc).__name__,
        "model": model,
        "model_identity_confirmed": model == MODEL,
        "finish_reason": _safe_identifier(getattr(exc, "finish_reason", None)),
        "input_tokens": input_tokens if type(input_tokens) is int and input_tokens >= 0 else None,
        "output_tokens": output_tokens
        if type(output_tokens) is int and output_tokens >= 0
        else None,
        "reasoning_tokens": (
            reasoning_tokens if type(reasoning_tokens) is int and reasoning_tokens >= 0 else None
        ),
        "usage_metadata_complete": (
            type(input_tokens) is int
            and input_tokens >= 0
            and type(output_tokens) is int
            and output_tokens >= 0
        ),
        "reported_cost_inr": reported_cost if currency else None,
        "estimated_cost_inr": estimated_cost if currency else None,
        "cost_metadata_complete": currency == "INR" and reported_cost is not None,
        "outcome_uncertain": getattr(exc, "outcome_uncertain", None) is True,
        "retry_after_seconds": _safe_number(getattr(exc, "retry_after_seconds", None)),
        "cooldown_scope": _safe_identifier(getattr(exc, "cooldown_scope", None)),
        "validation_error_types": [
            value for value in getattr(exc, "validation_error_types", ()) if _safe_identifier(value)
        ][:12],
        "validation_error_paths": [
            value for value in getattr(exc, "validation_error_paths", ()) if _safe_identifier(value)
        ][:12],
    }


def _operation_stage(schema_name: str) -> str:
    return {
        "veda_research_plan_selection_v1": "planning",
        "veda_appraisal_batch_v2": "appraisal",
        "veda_comparison_batch_v1": "comparison",
        "veda_report_draft_v3": "synthesis",
        "veda_semantic_report_audit_v1": "semantic_support",
    }.get(schema_name, "structured_generation")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    if os.environ.get("VEDA_SARVAM_LIVE_E2E") != "1":
        raise SystemExit("GLM live execution requires the explicit one-question opt-in.")
    if os.environ.get("VEDA_SARVAM_BILLING_VERIFIED") != "1":
        raise SystemExit("The user must confirm Credits Left covers ₹25 and Auto-recharge is off.")
    try:
        job_budget_inr = float(os.environ["VEDA_SARVAM_JOB_BUDGET_INR"])
        provider_post_cap = int(os.environ["VEDA_SARVAM_REQUEST_CAP"])
    except (KeyError, ValueError):
        raise SystemExit(
            "The cumulative budget and request cap must be supplied before inference."
        ) from None
    if not math.isfinite(job_budget_inr) or not 0 < job_budget_inr <= MAX_JOB_COST_INR:
        raise SystemExit("The remaining internal Sarvam budget is invalid; no inference was sent.")
    if not 1 <= provider_post_cap <= MAX_PROVIDER_POSTS:
        raise SystemExit(
            "The remaining provider request allowance is invalid; no inference was sent."
        )

    backend_dir = Path(__file__).resolve().parents[1]
    os.chdir(backend_dir)
    sys.path.insert(0, str(backend_dir))
    sys.path.insert(0, str(backend_dir / "scripts"))
    import app.config as app_config

    initial_settings = app_config.Settings()
    credential = initial_settings.sarvam_api_key
    if not credential or len(credential) > 256:
        raise SystemExit(
            "SARVAM_API_KEY is unavailable to backend Settings; no inference was sent."
        )

    counter_path = _evaluation_path(
        "VEDA_SARVAM_REQUEST_COUNTER_PATH", ".txt", "sarvam-glm-request-count-"
    )
    database_path = _evaluation_path("VEDA_SARVAM_DATABASE_PATH", ".sqlite3", "veda-sarvam-glm-")
    state_path = _evaluation_path(
        "VEDA_SARVAM_SERVER_STATE_PATH", ".json", "sarvam-glm-server-state-"
    )
    run_state_path = _evaluation_path(
        "VEDA_SARVAM_RUN_STATE_PATH", ".json", "sarvam-glm-run-state-"
    )

    os.environ.update(
        {
            "APP_ENV": "test",
            "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "FRONTEND_ORIGINS": "http://127.0.0.1:5176",
            "LLM_PROVIDER": "sarvam",
            "SARVAM_MODEL": MODEL,
            "ALLOW_PAID_LLM_CALLS": "true",
            "SARVAM_MAX_JOB_COST_INR": f"{job_budget_inr:.2f}",
            "SARVAM_INPUT_PRICE_PER_MILLION_INR": "13.5",
            "SARVAM_OUTPUT_PRICE_PER_MILLION_INR": "45",
            "OPENAI_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "OPENROUTER_MODEL": "",
            "MAX_JOB_COST_USD": "0",
            "MAX_DAILY_MODEL_CALLS": str(provider_post_cap),
            "MAX_DAILY_MODEL_CALLS_PER_USER": str(provider_post_cap),
            "OPENALEX_API_KEY": "",
            "OPENALEX_ALLOW_BILLABLE_CALLS": "false",
            "CROSSREF_MAILTO": "",
            "VEDA_SARVAM_REQUEST_COUNTER_PATH": str(counter_path),
            "VEDA_SARVAM_DATABASE_PATH": str(database_path),
            "VEDA_SARVAM_SERVER_STATE_PATH": str(state_path),
            "VEDA_SARVAM_RUN_STATE_PATH": str(run_state_path),
            "SARVAM_API_KEY": credential,
        }
    )
    del credential
    app_config.get_settings.cache_clear()
    app_config.settings = app_config.get_settings()

    from app.providers.registry import configured_model

    profile = configured_model("sarvam", MODEL, config=app_config.settings)
    if (
        not profile.ready
        or profile.model != MODEL
        or profile.input_price_per_million != 13.5
        or profile.output_price_per_million != 45.0
        or app_config.settings.sarvam_max_job_cost_inr != job_budget_inr
    ):
        raise SystemExit(
            "The GLM route or reserved-cost profile failed closed; no inference was sent."
        )

    migration_env = os.environ.copy()
    migration_env.update(
        {
            "SARVAM_API_KEY": "",
            "OPENAI_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "LLM_PROVIDER": "disabled",
            "ALLOW_PAID_LLM_CALLS": "false",
        }
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        env=migration_env,
        check=True,
    )
    from serve_browser_e2e import configure_isolated_environment, seed_inspection_record

    configure_isolated_environment(f"sqlite:///{database_path.as_posix()}")
    os.environ.update(
        {
            "LLM_PROVIDER": "sarvam",
            "SARVAM_MODEL": MODEL,
            "SARVAM_API_KEY": app_config.settings.sarvam_api_key,
            "ALLOW_PAID_LLM_CALLS": "true",
            "SARVAM_MAX_JOB_COST_INR": f"{job_budget_inr:.2f}",
            "SARVAM_INPUT_PRICE_PER_MILLION_INR": "13.5",
            "SARVAM_OUTPUT_PRICE_PER_MILLION_INR": "45",
            "OPENAI_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "MAX_DAILY_MODEL_CALLS": str(provider_post_cap),
            "MAX_DAILY_MODEL_CALLS_PER_USER": str(provider_post_cap),
            "FRONTEND_ORIGINS": "http://127.0.0.1:5176",
        }
    )
    app_config.get_settings.cache_clear()
    app_config.settings = app_config.get_settings()
    import app.providers.sarvam as sarvam_module

    sarvam_module.settings = app_config.settings
    seed_inspection_record()

    import httpx

    from app.providers.llm import LLMProviderError

    attempts = 0
    failure: dict[str, Any] | None = None
    original_post = httpx.Client.post
    original_complete = sarvam_module.SarvamChatCompletionsProvider.complete_json

    def counted_post(client, url, *args, **kwargs):
        nonlocal attempts
        route = str(url)
        if route.startswith("https://api.openai.com/") or route.startswith(
            "https://openrouter.ai/"
        ):
            raise LLMProviderError(
                "Other inference providers are disabled for this validation.",
                code="unexpected_provider_route",
            )
        if route == ENDPOINT:
            if attempts >= provider_post_cap:
                raise LLMProviderError(
                    "The standard-job request limit was reached; no POST was sent.",
                    code="sarvam_request_cap",
                )
            attempts += 1
            counter_path.write_text(f"{attempts}\n", encoding="ascii")
        return original_post(client, url, *args, **kwargs)

    def fail_closed_after_error(provider, **kwargs):
        nonlocal failure
        if failure is not None:
            raise LLMProviderError(
                "The live-validation circuit is open after a prior provider failure.",
                code="sarvam_live_run_stopped_after_failure",
            )
        try:
            result = original_complete(provider, **kwargs)
        except Exception as exc:
            failure = _safe_failure(exc, _operation_stage(str(kwargs.get("schema_name", ""))))
            _write_json(
                run_state_path,
                {
                    "status": "stopped_after_provider_failure",
                    "provider": "sarvam",
                    "model": MODEL if failure.get("model_identity_confirmed") else None,
                    "provider_request_attempts": attempts,
                    "provider_request_hard_cap": provider_post_cap,
                    "separate_compatibility_probe": False,
                    "failure": failure,
                    "raw_provider_response_saved": False,
                },
            )
            raise
        if result.usage.model != MODEL:
            failure = {
                "stage": _operation_stage(str(kwargs.get("schema_name", ""))),
                "error_class": "unexpected_model_route",
                "model": None,
                "model_identity_confirmed": False,
                "finish_reason": result.usage.finish_reason,
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "reasoning_tokens": result.usage.reasoning_tokens,
                "usage_metadata_complete": result.usage.input_tokens is not None
                and result.usage.output_tokens is not None,
                "reported_cost_inr": _safe_number(result.usage.reported_cost_amount),
                "estimated_cost_inr": _safe_number(result.usage.estimated_cost_amount),
                "cost_metadata_complete": result.usage.reported_cost_amount is not None,
                "outcome_uncertain": False,
            }
            _write_json(
                run_state_path, {"status": "stopped_after_route_mismatch", "failure": failure}
            )
            raise LLMProviderError(
                "The provider response model differed from the pinned GLM route.",
                code="unexpected_model_route",
            )
        return result

    httpx.Client.post = counted_post
    sarvam_module.SarvamChatCompletionsProvider.complete_json = fail_closed_after_error
    counter_path.write_text("0\n", encoding="ascii")
    _write_json(
        state_path,
        {
            "status": "ready_for_real_research_job",
            "provider": "sarvam",
            "model": MODEL,
            "endpoint": ENDPOINT,
            "provider_request_hard_cap": provider_post_cap,
            "job_budget_ceiling_inr": job_budget_inr,
            "total_authorized_spend_ceiling_inr": MAX_TOTAL_AUTHORIZED_INR,
            "separate_compatibility_probe": False,
            "first_compatibility_operation": "veda_research_plan_selection_v1",
            "automatic_retries": 0,
            "paid_fallback": False,
            "account_balance_api_available": False,
            "billing_confirmation": "user_confirmed_in_dashboard",
        },
    )

    import uvicorn

    from app.db import engine
    from app.main import app

    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=int(os.environ.get("VEDA_REAL_E2E_API_PORT", "8002")),
            log_level="warning",
        )
    finally:
        engine.dispose()
        _write_json(
            state_path,
            {
                "status": "stopped_after_provider_failure" if failure else "server_stopped",
                "provider": "sarvam",
                "model": MODEL,
                "provider_request_attempts": attempts,
                "provider_request_hard_cap": provider_post_cap,
                "failure": failure,
                "raw_provider_response_saved": False,
            },
        )
        os.environ.pop("SARVAM_API_KEY", None)


if __name__ == "__main__":
    main()
