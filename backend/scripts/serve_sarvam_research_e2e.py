"""Serve an isolated local Veda API after one bounded Sarvam schema probe.

The probe and research workflow share one six-POST counter. The probe uses the
real Veda appraisal schema with synthetic-only content and is never treated as
research evidence. A provider error opens a process-local circuit so later
stages cannot issue another inference POST.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

MAX_TOTAL_POSTS = 6
MAX_JOB_CALLS = 5
MAX_TEST_SPEND_INR = 5.0
MAX_PRETAX_RESERVATION_INR = 4.0
PROBE_RESERVATION_INR = 0.50
JOB_BUDGET_INR = MAX_PRETAX_RESERVATION_INR - PROBE_RESERVATION_INR
PROBE_OUTPUT_TOKEN_CAP = 4096
EXPECTED_MODEL = "sarvam-105b"
EXPECTED_ENDPOINT = "https://api.sarvam.ai/v2/chat/completions"


def _safe_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0 else None


def _safe_code(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value if re.fullmatch(r"[a-zA-Z0-9_.:-]{1,80}", value) else "provider_error"


def _provider_failure_details(exc: Exception, *, stage: str) -> dict[str, Any]:
    model = getattr(exc, "model_name", None)
    if model != EXPECTED_MODEL:
        model = None
    input_tokens = getattr(exc, "input_tokens", None)
    output_tokens = getattr(exc, "output_tokens", None)
    reasoning_tokens = getattr(exc, "reasoning_tokens", None)
    cost_currency = getattr(exc, "cost_currency", None)
    if not isinstance(cost_currency, str) or not re.fullmatch(r"[A-Z]{3}", cost_currency):
        cost_currency = None
    reported_cost = _safe_number(getattr(exc, "reported_cost_amount", None))
    estimated_cost = _safe_number(getattr(exc, "estimated_cost_amount", None))
    latency = getattr(exc, "latency_ms", None)
    return {
        "stage": stage,
        "error_class": _safe_code(getattr(exc, "code", None)) or type(exc).__name__,
        "model": model,
        "model_identity_confirmed": model == EXPECTED_MODEL,
        "finish_reason": _safe_code(getattr(exc, "finish_reason", None)),
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
        "reported_cost_inr": reported_cost if cost_currency == "INR" else None,
        "estimated_cost_inr": estimated_cost if cost_currency == "INR" else None,
        "reported_cost_known": reported_cost is not None and cost_currency == "INR",
        "latency_ms": latency if type(latency) is int and latency >= 0 else None,
        "outcome_uncertain": getattr(exc, "outcome_uncertain", None) is True,
    }


def _operation_stage(schema_name: str) -> str:
    return {
        "veda_sarvam_compatibility_probe_v1": "compatibility_probe",
        "veda_research_plan_selection_v1": "planning",
        "veda_appraisal_batch_v2": "appraisal",
        "veda_comparison_batch_v1": "comparison",
        "veda_report_draft_v3": "synthesis",
        "veda_semantic_report_audit_v1": "semantic_support",
    }.get(schema_name, "structured_generation")


def _required_path(env_name: str, suffix: str, prefix: str) -> Path:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        raise ValueError(f"{env_name} is required before dispatch.")
    path = Path(raw).resolve()
    evaluation = Path(__file__).resolve().parents[2] / "evaluation"
    try:
        path.relative_to(evaluation.resolve())
    except ValueError:
        raise ValueError(f"{env_name} must stay inside the evaluation directory.") from None
    if path.suffix.casefold() != suffix or not path.name.startswith(prefix) or path.exists():
        raise ValueError(f"{env_name} must name a new, uniquely prefixed evaluation artifact.")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _probe_payload() -> tuple[str, str]:
    system = (
        "This is only a synthetic structured-output compatibility probe. It is not a real study, "
        "not research evidence, and must not be reused in a report. Follow the supplied Veda "
        "appraisal schema exactly."
    )
    user = json.dumps(
        {
            "synthetic_fixture_only": True,
            "source_id": "compat-probe-source",
            "passage_id": "compat-probe-passage",
            "passage": "Synthetic fixture: no study design or methods are described.",
            "instruction": (
                "Output only compact JSON matching the schema. Return schema_version 2, exactly "
                "one source appraisal for the supplied source ID, exactly one design_type field "
                "whose value is unknown and whose only passage ID is the supplied passage ID, "
                "and an empty claim_assessments list. Do not add explanation or other fields."
            ),
        },
        separators=(",", ":"),
    )
    return system, user


def _perform_compatibility_probe(
    counter_path: Path, probe_path: Path
) -> tuple[dict[str, Any], float]:
    import httpx

    import app.config as app_config
    import app.providers.sarvam as sarvam_module
    from app.providers.contracts import ProviderRequestContext
    from app.providers.llm import LLMProviderError, maximum_input_token_estimate
    from app.providers.registry import configured_model
    from app.research.llm_tasks import ResearchAppraisalBatch

    settings = app_config.settings
    configured = configured_model("sarvam", EXPECTED_MODEL, config=settings)
    if not configured.ready or settings.sarvam_model != EXPECTED_MODEL:
        raise RuntimeError("Sarvam model configuration is not ready for the bounded probe.")
    if settings.sarvam_input_price_per_million_inr != 15.0:
        raise RuntimeError("Sarvam input-price metadata does not match the reviewed route.")
    if settings.sarvam_output_price_per_million_inr != 60.0:
        raise RuntimeError("Sarvam output-price metadata does not match the reviewed route.")

    system, user = _probe_payload()
    schema_name = "veda_sarvam_compatibility_probe_v1"
    output_cap = PROBE_OUTPUT_TOKEN_CAP
    input_bound = maximum_input_token_estimate(
        system, user, schema_name=schema_name, schema_model=ResearchAppraisalBatch
    )
    reserved = configured.maximum_cost(input_bound, output_cap)
    if reserved is None or reserved > PROBE_RESERVATION_INR:
        raise RuntimeError("The appraisal-schema probe exceeds its ₹0.50 pre-dispatch reserve.")

    counter = {"attempts": 0, "failure": None}

    def persist_count() -> None:
        temporary = counter_path.with_suffix(counter_path.suffix + ".tmp")
        temporary.write_text(f"{counter['attempts']}\n", encoding="ascii")
        temporary.replace(counter_path)

    persist_count()
    original_post = httpx.Client.post

    def counted_post(client, url, *args, **kwargs):
        if str(url) != EXPECTED_ENDPOINT:
            raise LLMProviderError(
                "A non-Sarvam inference POST was blocked.", code="unexpected_provider_route"
            )
        if counter["attempts"] >= MAX_TOTAL_POSTS:
            raise LLMProviderError(
                "The six-request test cap was reached.", code="sarvam_request_cap"
            )
        counter["attempts"] += 1
        persist_count()
        return original_post(client, url, *args, **kwargs)

    httpx.Client.post = counted_post
    original_complete = sarvam_module.SarvamChatCompletionsProvider.complete_json

    def fail_closed_complete(provider, **kwargs):
        if counter["failure"] is not None:
            raise LLMProviderError(
                "The Sarvam test circuit stopped after an earlier failed structured operation.",
                code="sarvam_live_run_stopped_after_failure",
            )
        try:
            return original_complete(provider, **kwargs)
        except Exception as exc:
            counter["failure"] = _provider_failure_details(
                exc, stage=_operation_stage(str(kwargs.get("schema_name", "")))
            )
            failure_state = {
                "status": "stopped_after_provider_failure",
                "provider_request_attempts": counter["attempts"],
                "provider_request_hard_cap": MAX_TOTAL_POSTS,
                "pre_dispatch_reserved_cost_inr": round(reserved, 8),
                "failure": counter["failure"],
            }
            _write_json(probe_path, failure_state)
            _write_json(
                Path(os.environ["VEDA_SARVAM_SERVER_STATE_PATH"]),
                {
                    "status": "stopped_after_provider_failure",
                    "compatibility_probe": failure_state,
                    "provider_request_attempts": counter["attempts"],
                    "provider_request_hard_cap": MAX_TOTAL_POSTS,
                    "pre_dispatch_reserved_cost_inr": round(reserved, 8),
                    "probe_reservation_ceiling_inr": PROBE_RESERVATION_INR,
                    "job_budget_ceiling_inr": JOB_BUDGET_INR,
                    "maximum_pretax_reservation_inr": MAX_PRETAX_RESERVATION_INR,
                },
            )
            raise

    sarvam_module.SarvamChatCompletionsProvider.complete_json = fail_closed_complete
    sarvam_module.settings = settings
    probe_result: dict[str, Any]
    provider = None
    try:
        provider = sarvam_module.SarvamChatCompletionsProvider(model=EXPECTED_MODEL)
        request_hash = hashlib.sha256(
            (system + "\0" + user + "\0" + schema_name).encode()
        ).hexdigest()
        result = provider.complete_json(
            schema_name=schema_name,
            schema_model=ResearchAppraisalBatch,
            system=system,
            user=user,
            max_output_tokens=output_cap,
            budget_ceiling_inr=PROBE_RESERVATION_INR,
            model=EXPECTED_MODEL,
            request_context=ProviderRequestContext(
                reservation_id=str(uuid.uuid4()),
                request_hash=request_hash,
                reserved_cost_amount=reserved,
                cost_currency="INR",
                no_automatic_retry=True,
            ),
        )
        value = result.value
        provenance_ok = (
            value.schema_version == 2
            and len(value.source_appraisals) == 1
            and value.source_appraisals[0].source_id == "compat-probe-source"
            and all(
                passage_id == "compat-probe-passage"
                for field in value.source_appraisals[0].fields
                for passage_id in field.passage_ids
            )
            and value.claim_assessments == []
        )
        if not provenance_ok:
            counter["failure"] = {
                "stage": "compatibility_probe",
                "error_class": "probe_schema_provenance_rejected",
                "model": result.usage.model if result.usage.model == EXPECTED_MODEL else None,
                "model_identity_confirmed": result.usage.model == EXPECTED_MODEL,
                "finish_reason": _safe_code(result.usage.finish_reason),
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "reasoning_tokens": result.usage.reasoning_tokens,
                "usage_metadata_complete": result.usage.input_tokens is not None
                and result.usage.output_tokens is not None,
                "reported_cost_inr": _safe_number(result.usage.reported_cost_amount),
                "estimated_cost_inr": _safe_number(result.usage.estimated_cost_amount),
                "reported_cost_known": (
                    result.usage.reported_cost_amount is not None
                    and result.usage.cost_currency == "INR"
                ),
                "latency_ms": result.usage.latency_ms,
            }
            probe_result = {
                "status": "rejected",
                "accepted": False,
                "schema_name": schema_name,
                "schema_model": "ResearchAppraisalBatch",
                "model": EXPECTED_MODEL,
                "finish_reason": _safe_code(result.usage.finish_reason),
                "reserved_cost_inr": round(reserved, 8),
                "failure": counter["failure"],
            }
            _write_json(probe_path, probe_result)
            _write_json(
                Path(os.environ["VEDA_SARVAM_SERVER_STATE_PATH"]),
                {
                    "status": "probe_output_rejected",
                    "compatibility_probe": probe_result,
                    "provider_request_attempts": counter["attempts"],
                    "provider_request_hard_cap": MAX_TOTAL_POSTS,
                    "pre_dispatch_reserved_cost_inr": round(reserved, 8),
                    "probe_reservation_ceiling_inr": PROBE_RESERVATION_INR,
                    "job_budget_ceiling_inr": JOB_BUDGET_INR,
                    "maximum_pretax_reservation_inr": MAX_PRETAX_RESERVATION_INR,
                },
            )
            raise RuntimeError("Sarvam compatibility output failed Veda provenance validation.")
        usage = result.usage
        probe_result = {
            "status": "accepted",
            "accepted": True,
            "schema_name": schema_name,
            "schema_model": "ResearchAppraisalBatch",
            "model": usage.model,
            "finish_reason": _safe_code(usage.finish_reason),
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "reasoning_tokens": usage.reasoning_tokens,
            "usage_metadata_complete": usage.input_tokens is not None
            and usage.output_tokens is not None,
            "reported_cost_inr": _safe_number(usage.reported_cost_amount),
            "estimated_cost_inr": _safe_number(usage.estimated_cost_amount),
            "reported_cost_known": usage.reported_cost_amount is not None,
            "reserved_cost_inr": round(reserved, 8),
            "latency_ms": usage.latency_ms,
            "raw_response_saved": False,
            "synthetic_probe_excluded_from_research_evidence": True,
        }
        _write_json(probe_path, probe_result)
    except Exception:
        persist_count()
        raise
    finally:
        if provider is not None:
            provider.close()

    counter_path_text = str(counter_path)
    server_state_path = Path(os.environ["VEDA_SARVAM_SERVER_STATE_PATH"])
    _write_json(
        server_state_path,
        {
            "compatibility_probe": probe_result,
            "provider_request_attempts": counter["attempts"],
            "provider_request_hard_cap": MAX_TOTAL_POSTS,
            "probe_reservation_inr": round(reserved, 8),
            "job_budget_ceiling_inr": JOB_BUDGET_INR,
            "maximum_pretax_reservation_inr": MAX_PRETAX_RESERVATION_INR,
            "tax_and_billing_rounding_headroom_inr": MAX_TEST_SPEND_INR
            - MAX_PRETAX_RESERVATION_INR,
            "combined_reservation_ceiling_inr": round(reserved + JOB_BUDGET_INR, 8),
            "counter_file": counter_path_text,
        },
    )
    return probe_result, reserved


def main() -> None:
    if os.environ.get("VEDA_SARVAM_LIVE_E2E") != "1":
        raise SystemExit("Sarvam live execution requires explicit one-question opt-in.")
    if os.environ.get("VEDA_SARVAM_BILLING_VERIFIED") != "1":
        raise SystemExit("Sarvam Credits Left and Auto-recharge confirmation is required.")

    backend_dir = Path(__file__).resolve().parents[1]
    os.chdir(backend_dir)
    sys.path.insert(0, str(backend_dir))
    sys.path.insert(0, str(backend_dir / "scripts"))

    import app.config as app_config

    settings_before_overrides = app_config.Settings()
    key = settings_before_overrides.sarvam_api_key
    if not key or len(key) > 256:
        raise SystemExit("Sarvam key is unavailable to backend Settings; no request was sent.")

    counter_path = _required_path(
        "VEDA_SARVAM_REQUEST_COUNTER_PATH", ".txt", "sarvam-request-count-"
    )
    database_path = _required_path("VEDA_SARVAM_DATABASE_PATH", ".sqlite3", "veda-sarvam-")
    probe_path = _required_path("VEDA_SARVAM_COMPATIBILITY_PATH", ".json", "sarvam-compatibility-")
    server_state_path = _required_path(
        "VEDA_SARVAM_SERVER_STATE_PATH", ".json", "sarvam-server-state-"
    )
    output_path = _required_path("VEDA_SARVAM_OUTPUT_PATH", ".json", "sarvam-research-validation-")

    os.environ.update(
        {
            "APP_ENV": "test",
            "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "LLM_PROVIDER": "sarvam",
            "SARVAM_MODEL": EXPECTED_MODEL,
            "ALLOW_PAID_LLM_CALLS": "true",
            "SARVAM_MAX_JOB_COST_INR": f"{JOB_BUDGET_INR:.2f}",
            "SARVAM_INPUT_PRICE_PER_MILLION_INR": "15",
            "SARVAM_OUTPUT_PRICE_PER_MILLION_INR": "60",
            "OPENAI_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "OPENROUTER_MODEL": "",
            "MAX_JOB_COST_USD": "0",
            "MAX_DAILY_MODEL_CALLS": str(MAX_JOB_CALLS),
            "MAX_DAILY_MODEL_CALLS_PER_USER": str(MAX_JOB_CALLS),
            "OPENALEX_API_KEY": "",
            "OPENALEX_ALLOW_BILLABLE_CALLS": "false",
            "CROSSREF_MAILTO": "",
            "VEDA_SARVAM_REQUEST_COUNTER_PATH": str(counter_path),
            "VEDA_SARVAM_COMPATIBILITY_PATH": str(probe_path),
            "VEDA_SARVAM_SERVER_STATE_PATH": str(server_state_path),
            "VEDA_SARVAM_OUTPUT_PATH": str(output_path),
            "VEDA_SARVAM_DATABASE_PATH": str(database_path),
        }
    )
    # This value is passed only to the isolated API process; it is never printed
    # or written to a result artifact. The runner removes it at process exit.
    os.environ["SARVAM_API_KEY"] = key
    del key

    app_config.get_settings.cache_clear()
    app_config.settings = app_config.get_settings()
    if (
        app_config.settings.llm_provider != "sarvam"
        or app_config.settings.sarvam_model != EXPECTED_MODEL
        or not app_config.settings.allow_paid_llm_calls
        or app_config.settings.sarvam_max_job_cost_inr != JOB_BUDGET_INR
    ):
        raise SystemExit(
            "The bounded Sarvam process settings did not validate; no request was sent."
        )

    import app.providers.sarvam as sarvam_module

    sarvam_module.settings = app_config.settings
    from serve_browser_e2e import configure_isolated_environment, seed_inspection_record

    configure_isolated_environment(f"sqlite:///{database_path.as_posix()}")
    # Reapply only the authorized, run-scoped inference settings after the
    # provider-disabled browser helper sets its safe defaults.
    os.environ.update(
        {
            "LLM_PROVIDER": "sarvam",
            "SARVAM_MODEL": EXPECTED_MODEL,
            "SARVAM_API_KEY": app_config.settings.sarvam_api_key,
            "ALLOW_PAID_LLM_CALLS": "true",
            "SARVAM_MAX_JOB_COST_INR": f"{JOB_BUDGET_INR:.2f}",
            "OPENAI_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "MAX_DAILY_MODEL_CALLS": str(MAX_JOB_CALLS),
            "MAX_DAILY_MODEL_CALLS_PER_USER": str(MAX_JOB_CALLS),
            "FRONTEND_ORIGINS": "http://127.0.0.1:5176",
            "RATE_LIMIT_USER_PER_MINUTE": "10000",
            "RATE_LIMIT_IP_PER_MINUTE": "20000",
            "RATE_LIMIT_USER_JOB_CREATES_PER_HOUR": "10",
            "RATE_LIMIT_IP_JOB_CREATES_PER_HOUR": "20",
            "RATE_LIMIT_USER_ADVANCES_PER_MINUTE": "1000",
            "RATE_LIMIT_IP_ADVANCES_PER_MINUTE": "2000",
        }
    )
    app_config.get_settings.cache_clear()
    app_config.settings = app_config.get_settings()
    sarvam_module.settings = app_config.settings

    import app.providers.sarvam as sarvam_module

    # Complete local database work before spending credits. This verifies the
    # isolated migration and browser fixture without making a provider request.
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
    seed_inspection_record()

    probe_result, probe_reservation = _perform_compatibility_probe(counter_path, probe_path)
    if not probe_result.get("accepted"):
        raise SystemExit("Sarvam appraisal-schema compatibility was not accepted; stopping.")
    if (
        probe_reservation > PROBE_RESERVATION_INR
        or probe_reservation + JOB_BUDGET_INR > MAX_PRETAX_RESERVATION_INR
    ):
        raise SystemExit(
            "Combined conservative reservations exceed the ₹4 pre-tax ceiling; stopping."
        )

    from app.research.depth import PROFILES

    PROFILES["standard"] = replace(
        PROFILES["standard"],
        max_model_calls=MAX_JOB_CALLS,
        max_retries=0,
    )
    # `_perform_compatibility_probe` installs the shared capped POST wrapper and
    # one-failure circuit before this API server starts.
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
        server_state = json.loads(server_state_path.read_text(encoding="utf-8"))
        server_state["request_counter"] = int(
            counter_path.read_text(encoding="ascii").strip() or "0"
        )
        server_state["provider_request_hard_cap"] = MAX_TOTAL_POSTS
        _write_json(server_state_path, server_state)
        os.environ.pop("SARVAM_API_KEY", None)


if __name__ == "__main__":
    main()
