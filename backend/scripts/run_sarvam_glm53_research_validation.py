"""Run one live GLM-5.3 Flash Veda research job through the real browser and API.

The environment must contain SARVAM_API_KEY. This script never prints or writes
that value. Dispatch is gated by the user's one-run authorization and current
₹25 Credits Left / Auto-recharge dashboard confirmation.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

QUESTION = (
    "Does generative AI improve software developer productivity, "
    "and why do empirical studies sometimes report different findings?"
)
MODEL = "glm5.3-flash"
ENDPOINT = "https://api.sarvam.ai/v2/chat/completions"
TOTAL_CEILING_INR = 25.0
PRETAX_RESERVATION_CEILING_INR = 20.0
REQUEST_CAP = 24


def _artifact_path(directory: Path, stem: str, suffix: str) -> Path:
    return directory / f"{stem}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.{suffix}"


def _build_preflight(
    profile,
    *,
    billing_confirmed: bool,
    prior_spend_inr: float = 0.0,
    prior_provider_posts: int = 0,
    job_budget_inr: float = PRETAX_RESERVATION_CEILING_INR,
    request_cap: int = REQUEST_CAP,
) -> dict:
    from app.research.depth import PROFILES

    standard = PROFILES["standard"]
    standard_reserve = profile.maximum_cost(
        standard.max_prompt_token_budget_total,
        standard.max_output_token_budget_total,
    )
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "provider": "sarvam",
        "model": MODEL,
        "endpoint": ENDPOINT,
        "route_verified_from_local_registry": profile.ready and profile.model == MODEL,
        "strict_json_schema": profile.strict_json_schema,
        "supported_reasoning_efforts": sorted(profile.supported_reasoning_efforts),
        "initial_reasoning_effort": "low",
        "maximum_provider_context_tokens": profile.max_context_tokens,
        "maximum_provider_completion_tokens": profile.max_completion_tokens,
        "veda_standard_per_call_output_cap": standard.max_output_tokens_per_call,
        "veda_standard_total_input_token_budget": standard.max_prompt_token_budget_total,
        "veda_standard_total_output_token_budget": standard.max_output_token_budget_total,
        "conservative_standard_run_reservation_inr": standard_reserve,
        "input_price_per_million_inr": profile.input_price_per_million,
        "cached_input_price_per_million_inr": 2.5,
        "output_price_per_million_inr": profile.output_price_per_million,
        "prices_exclude_gst": True,
        "reservation_multiplier": profile.cost_reservation_multiplier,
        "authorized_total_spend_ceiling_inr": TOTAL_CEILING_INR,
        "maximum_internal_pretax_reservation_inr": PRETAX_RESERVATION_CEILING_INR,
        "prior_conservative_spend_inr": prior_spend_inr,
        "remaining_internal_pretax_budget_inr": job_budget_inr,
        "this_job_budget_ceiling_inr": job_budget_inr,
        "prior_provider_post_count": prior_provider_posts,
        "tax_rounding_and_uncertainty_headroom_inr": (
            TOTAL_CEILING_INR - PRETAX_RESERVATION_CEILING_INR
        ),
        "provider_request_hard_cap": request_cap,
        "request_cap_scope": "per-job Veda resource cap; cumulative authorization is enforced by INR reservations",
        "separate_compatibility_probe": False,
        "first_real_operation": "veda_research_plan_selection_v1",
        "paid_fallback": False,
        "automatic_retries": False,
        "openai_or_openrouter_inference": False,
        "user_confirmed_credits_cover_total_ceiling": billing_confirmed,
        "user_confirmed_auto_recharge_off": billing_confirmed,
        "account_balance_api_available": False,
        "balance_independently_verified_by_runner": False,
        "source_docs": [
            "https://docs.sarvam.ai/api/token-factory/models/glm-5-3-flash",
            "https://docs.sarvam.ai/api/token-factory/chat-completions",
            "https://docs.sarvam.ai/api/getting-started/pricing",
            "https://docs.sarvam.ai/api/platform/billing",
        ],
    }


def _artifact_post_count(path: Path, artifact: dict) -> int:
    posts = artifact.get("provider_request_attempts")
    if type(posts) is int and posts >= 0:
        return posts
    timestamp = path.stem.removeprefix("sarvam-glm53-research-")
    counter = path.with_name(f"sarvam-glm-request-count-{timestamp}.txt")
    try:
        value = counter.read_text(encoding="ascii").strip()
    except OSError:
        raise ValueError(
            f"Cannot establish the earlier provider request count for {path.name}."
        ) from None
    if not value.isdecimal():
        raise ValueError(f"Earlier provider request count is invalid for {path.name}.")
    return int(value)


def _assert_no_unfinalized_glm_runs(evaluation_dir: Path) -> None:
    """Block a new chargeable run when an earlier run's POST count is unaccounted for."""
    prefixes = (
        "sarvam-glm53-preflight-",
        "sarvam-glm53-research-",
        "sarvam-glm-request-count-",
        "sarvam-glm-run-state-",
        "sarvam-glm-server-state-",
        "veda-sarvam-glm-",
    )
    timestamps: set[str] = set()
    for path in evaluation_dir.iterdir():
        for prefix in prefixes:
            if path.name.startswith(prefix):
                stamp = path.name.removeprefix(prefix)
                if prefix == "veda-sarvam-glm-":
                    stamp = stamp.removesuffix(".sqlite3")
                elif prefix != "sarvam-glm-request-count-":
                    stamp = stamp.removesuffix(".json")
                else:
                    stamp = stamp.removesuffix(".txt")
                if stamp:
                    timestamps.add(stamp)
                break

    for stamp in sorted(timestamps):
        result_path = evaluation_dir / f"sarvam-glm53-research-{stamp}.json"
        counter_path = evaluation_dir / f"sarvam-glm-request-count-{stamp}.txt"
        if not result_path.exists():
            if not counter_path.exists():
                raise ValueError(
                    f"Prior GLM run {stamp} is unfinalized and its provider request count is unavailable."
                )
            try:
                counter_text = counter_path.read_text(encoding="ascii").strip()
            except OSError:
                raise ValueError(
                    f"Prior GLM run {stamp} is unfinalized and its provider request count is unavailable."
                ) from None
            if not counter_text.isdecimal():
                raise ValueError(f"Prior GLM run {stamp} has an invalid provider request counter.")
            post_count = int(counter_text)
            if post_count > 0:
                raise ValueError(
                    f"Prior GLM run {stamp} is unfinalized after {post_count} provider POSTs; reconcile its usage before dispatch."
                )
            continue

        try:
            artifact = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ValueError(
                f"A prior GLM run artifact cannot be read: {result_path.name}."
            ) from None
        if not isinstance(artifact, dict) or artifact.get("configured_model") != MODEL:
            continue
        artifact_count = _artifact_post_count(result_path, artifact)
        if artifact_count > 0:
            if not counter_path.exists():
                raise ValueError(f"Prior GLM run {stamp} is missing its provider request counter.")
            try:
                counter_text = counter_path.read_text(encoding="ascii").strip()
            except OSError:
                raise ValueError(
                    f"Prior GLM run {stamp} has an unreadable provider request counter."
                ) from None
            if not counter_text.isdecimal() or int(counter_text) != artifact_count:
                raise ValueError(f"Prior GLM run {stamp} has a provider request-count mismatch.")
        if artifact.get("request_count_matches_usage") is False:
            usage_cost = _reconciled_provider_usage_cost(artifact, artifact_count)
            if usage_cost is None:
                raise ValueError(
                    f"Prior GLM run {stamp} cannot reconcile every provider POST to a costed usage record."
                )


def _prior_validation_totals(evaluation_dir: Path) -> tuple[float, int]:
    """Conservatively account for earlier Sarvam attempts under the shared ceiling."""
    _assert_no_unfinalized_glm_runs(evaluation_dir)
    prior_spend = 0.0
    prior_posts = 0
    for path in sorted(evaluation_dir.glob("sarvam-glm53-research-*.json")):
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ValueError(f"A prior GLM run artifact cannot be read: {path.name}.") from None
        if not isinstance(artifact, dict) or artifact.get("configured_model") != MODEL:
            continue
        posts = _artifact_post_count(path, artifact)
        if posts == 0:
            continue
        top_level = artifact.get("conservative_combined_reservation_inr")
        job = artifact.get("job") if isinstance(artifact.get("job"), dict) else {}
        spent = job.get("cost_spent_estimate_inr")
        reserved = job.get("cost_reserved_inr")
        job_total = (
            float(spent) + float(reserved)
            if _finite_nonnegative(spent) and _finite_nonnegative(reserved)
            else None
        )
        candidates = [
            float(value) for value in (top_level, job_total) if _finite_nonnegative(value)
        ]
        if artifact.get("request_count_matches_usage") is False:
            usage_cost = _reconciled_provider_usage_cost(artifact, posts)
            if usage_cost is not None:
                candidates.append(usage_cost)
        if not candidates:
            raise ValueError(
                f"Prior GLM run {path.name} dispatched requests but has unknown conservative cost; refusing another dispatch."
            )
        prior_spend += max(candidates)
        prior_posts += posts
    for path in sorted(evaluation_dir.glob("sarvam-research-validation-*.json")):
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ValueError(f"A prior Sarvam run artifact cannot be read: {path.name}.") from None
        if not isinstance(artifact, dict) or artifact.get("configured_model") != "sarvam-105b":
            continue
        posts = artifact.get("provider_request_attempts")
        if type(posts) is not int or posts < 0:
            probe = artifact.get("compatibility_probe")
            posts = probe.get("provider_request_attempts") if isinstance(probe, dict) else None
        if type(posts) is not int or posts < 0:
            raise ValueError(f"Prior Sarvam request count is invalid for {path.name}.")
        if posts == 0:
            continue
        probe_reservation = artifact.get("compatibility_probe_pre_dispatch_reserved_cost_inr")
        probe = artifact.get("compatibility_probe")
        failure = probe.get("failure") if isinstance(probe, dict) else None
        nested_reservation = (
            failure.get("pre_dispatch_reserved_cost_inr") if isinstance(failure, dict) else None
        )
        candidates = [
            float(value)
            for value in (probe_reservation, nested_reservation)
            if _finite_nonnegative(value)
        ]
        if not candidates:
            raise ValueError(
                f"Prior Sarvam run {path.name} dispatched requests but has unknown conservative cost."
            )
        prior_spend += max(candidates)
        prior_posts += posts
    return prior_spend, prior_posts


def _reconciled_provider_usage_cost(artifact: dict, post_count: int) -> float | None:
    """Return a per-POST INR estimate only when every call has a valid usage row.

    Older runner versions also wrote synthetic "stopped after failure" rows that do
    not represent provider requests.  A false summary flag can therefore be repaired
    from exact POST counters and fully costed call rows, without mistaking markers for
    requests or accepting an uncosted POST.
    """
    usage_rows = artifact.get("provider_usage")
    if not isinstance(usage_rows, list):
        return None
    request_rows = [
        row
        for row in usage_rows
        if isinstance(row, dict)
        and row.get("error_class") != "sarvam_live_run_stopped_after_failure"
    ]
    if len(request_rows) != post_count:
        return None
    cost_total = 0.0
    for row in request_rows:
        if row.get("provider") != "sarvam" or row.get("model_name") != MODEL:
            return None
        amount = row.get("estimated_cost_inr")
        if not _finite_nonnegative(amount):
            return None
        cost_total += float(amount)
    return cost_total


def _finite_nonnegative(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def _remaining_budget(prior_spend_inr: float, prior_provider_posts: int) -> tuple[float, int]:
    if not math.isfinite(prior_spend_inr) or prior_spend_inr < 0:
        raise ValueError("Prior spend is not a finite non-negative amount.")
    if type(prior_provider_posts) is not int or prior_provider_posts < 0:
        raise ValueError("Prior provider request count is invalid.")
    budget = math.floor((PRETAX_RESERVATION_CEILING_INR - prior_spend_inr + 1e-9) * 100) / 100
    if budget <= 0:
        raise ValueError("The authorized cumulative budget is exhausted.")
    # REQUEST_CAP is the existing per-job hard stop. Spend reservations, not an
    # arbitrary cumulative request count, bound separately diagnosed run attempts.
    return budget, REQUEST_CAP


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument(
        "--billing-confirmed",
        action="store_true",
        help="Confirm current Credits Left covers ₹25 and Auto-recharge is off.",
    )
    args = parser.parse_args(argv)
    if not args.execute_live or not args.billing_confirmed:
        print(
            "No inference dispatched: explicit live and current billing confirmations are required."
        )
        return 2

    backend_dir = Path(__file__).resolve().parents[1]
    root = backend_dir.parent
    frontend_dir = root / "frontend"
    evaluation_dir = root / "evaluation"
    os.chdir(backend_dir)
    sys.path.insert(0, str(backend_dir))

    from app.config import Settings
    from app.providers.registry import configured_model

    initial = Settings()
    credential = initial.sarvam_api_key
    if not credential or len(credential) > 256:
        print("Stopped before inference: backend Settings has no Sarvam credential.")
        return 2

    try:
        prior_spend, prior_posts = _prior_validation_totals(evaluation_dir)
        job_budget, request_cap = _remaining_budget(prior_spend, prior_posts)
    except ValueError as exc:
        print(f"Stopped before inference: {exc}")
        return 2

    config = Settings(
        app_env="test",
        sarvam_api_key=credential,
        llm_provider="sarvam",
        sarvam_model=MODEL,
        sarvam_input_price_per_million_inr=13.5,
        sarvam_output_price_per_million_inr=45.0,
        sarvam_max_job_cost_inr=job_budget,
        allow_paid_llm_calls=True,
    )
    config.validate_security_configuration()
    profile = configured_model("sarvam", MODEL, config=config)
    if (
        not profile.ready
        or profile.model != MODEL
        or profile.input_price_per_million != 13.5
        or profile.output_price_per_million != 45.0
        or profile.strict_json_schema is not True
        or "low" not in profile.supported_reasoning_efforts
    ):
        print("Stopped before inference: the exact model capability or price checks failed.")
        return 2
    preflight = _build_preflight(
        profile,
        billing_confirmed=args.billing_confirmed,
        prior_spend_inr=prior_spend,
        prior_provider_posts=prior_posts,
        job_budget_inr=job_budget,
        request_cap=request_cap,
    )
    if preflight["conservative_standard_run_reservation_inr"] > job_budget:
        print(
            "Stopped before inference: the standard-run reservation exceeds the remaining authorized budget."
        )
        return 2

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    paths = {
        "output": evaluation_dir / f"sarvam-glm53-research-{timestamp}.json",
        "preflight": evaluation_dir / f"sarvam-glm53-preflight-{timestamp}.json",
        "state": evaluation_dir / f"sarvam-glm-server-state-{timestamp}.json",
        "run_state": evaluation_dir / f"sarvam-glm-run-state-{timestamp}.json",
        "counter": evaluation_dir / f"sarvam-glm-request-count-{timestamp}.txt",
        "database": evaluation_dir / f"veda-sarvam-glm-{timestamp}.sqlite3",
    }
    if any(path.exists() for path in paths.values()):
        print("Stopped before inference: an isolated run artifact path already exists.")
        return 2
    paths["preflight"].write_text(
        json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    environment = os.environ.copy()
    environment.update(
        {
            "SARVAM_API_KEY": initial.sarvam_api_key,
            "OPENAI_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "LLM_PROVIDER": "sarvam",
            "SARVAM_MODEL": MODEL,
            "ALLOW_PAID_LLM_CALLS": "true",
            "SARVAM_MAX_JOB_COST_INR": f"{job_budget:.2f}",
            "SARVAM_INPUT_PRICE_PER_MILLION_INR": "13.5",
            "SARVAM_OUTPUT_PRICE_PER_MILLION_INR": "45",
            "MAX_DAILY_MODEL_CALLS": str(request_cap),
            "MAX_DAILY_MODEL_CALLS_PER_USER": str(request_cap),
            "VEDA_SARVAM_LIVE_E2E": "1",
            "VEDA_SARVAM_BILLING_VERIFIED": "1",
            "VEDA_SARVAM_JOB_BUDGET_INR": f"{job_budget:.2f}",
            "VEDA_SARVAM_REQUEST_CAP": str(request_cap),
            "VEDA_SARVAM_EXPECTED_MODEL": MODEL,
            "VEDA_SARVAM_RUN_ID": "glm53flash",
            "VEDA_SARVAM_OUTPUT_PATH": str(paths["output"]),
            "VEDA_SARVAM_PREFLIGHT_PATH": str(paths["preflight"]),
            "VEDA_SARVAM_SERVER_STATE_PATH": str(paths["state"]),
            "VEDA_SARVAM_RUN_STATE_PATH": str(paths["run_state"]),
            "VEDA_SARVAM_REQUEST_COUNTER_PATH": str(paths["counter"]),
            "VEDA_SARVAM_DATABASE_PATH": str(paths["database"]),
            "VEDA_REAL_E2E_API_PORT": "8002",
            "VEDA_BACKEND_PYTHON": sys.executable,
        }
    )
    del credential

    print(
        json.dumps(
            {
                "test": "one-question Sarvam GLM-5.3 Flash research validation",
                "question": QUESTION,
                "model": MODEL,
                "endpoint": ENDPOINT,
                "preflight_artifact": str(paths["preflight"]),
                "result_artifact": str(paths["output"]),
                "sqlite_database": str(paths["database"]),
                "request_hard_cap": request_cap,
                "total_authorized_spend_ceiling_inr": TOTAL_CEILING_INR,
                "internal_reservation_ceiling_inr": job_budget,
                "prior_conservative_spend_inr": prior_spend,
                "credential_value_printed": False,
                "automatic_retries": False,
                "paid_fallback": False,
            },
            ensure_ascii=False,
        )
    )
    completed: subprocess.CompletedProcess | None = None
    try:
        if os.name == "nt":
            completed = subprocess.run(
                [
                    os.environ.get("ComSpec", "cmd.exe"),
                    "/d",
                    "/c",
                    "npm exec -- playwright test e2e/sarvam-single-question.e2e.ts "
                    "--workers=1 --retries=0 --reporter=line",
                ],
                cwd=frontend_dir,
                env=environment,
                stdin=subprocess.DEVNULL,
                check=False,
            )
        else:
            completed = subprocess.run(
                [
                    "npm",
                    "exec",
                    "--",
                    "playwright",
                    "test",
                    "e2e/sarvam-single-question.e2e.ts",
                    "--workers=1",
                    "--retries=0",
                    "--reporter=line",
                ],
                cwd=frontend_dir,
                env=environment,
                stdin=subprocess.DEVNULL,
                check=False,
            )
    finally:
        environment["SARVAM_API_KEY"] = ""
        os.environ.pop("SARVAM_API_KEY", None)
    artifact = {}
    if paths["output"].is_file():
        try:
            artifact = json.loads(paths["output"].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            artifact = {"result_artifact_readable": False}
    artifact.update(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "authorization_scope": "one research question; GLM-5.3 Flash only; ₹25 total ceiling; ₹20 reserved ceiling",
            "question": QUESTION,
            "configured_model": MODEL,
            "preflight": preflight,
            "provider_request_hard_cap": request_cap,
            "playwright_exit_code": completed.returncode if completed else None,
            "raw_provider_response_saved": False,
        }
    )
    paths["output"].write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return completed.returncode if completed else 2


if __name__ == "__main__":
    raise SystemExit(main())
