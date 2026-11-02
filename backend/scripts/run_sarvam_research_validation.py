"""Run one bounded Sarvam Veda research validation through isolated local API/browser.

The script requires explicit one-run and billing confirmations. It reads the
credential through backend Settings, prints only presence, passes the secret to
the isolated API child, and enforces one appraisal-schema probe plus at most
five research calls under a combined conservative ₹5 reservation ceiling.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

QUESTION = "Does generative AI improve software developer productivity, and why do empirical studies sometimes report different findings?"
MODEL = "sarvam-105b"
ENDPOINT = "https://api.sarvam.ai/v2/chat/completions"
MAX_TOTAL_POSTS = 6
MAX_JOB_POSTS = 5
MAX_SPEND_INR = 5.0
MAX_PRETAX_RESERVATION_INR = 4.0
PROBE_RESERVATION_INR = 0.25
JOB_BUDGET_INR = MAX_PRETAX_RESERVATION_INR - PROBE_RESERVATION_INR
PROBE_OUTPUT_TOKEN_CAP = 1024


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute-live", action="store_true", help="Explicitly enable this one live validation."
    )
    parser.add_argument(
        "--billing-confirmed",
        action="store_true",
        help="User confirmed sufficient Credits Left and Auto-recharge is off.",
    )
    args = parser.parse_args(argv)
    if not args.execute_live or not args.billing_confirmed:
        print("No dispatch: explicit live and billing confirmations are required.")
        return 2

    backend_dir = Path(__file__).resolve().parents[1]
    root = backend_dir.parent
    frontend = root / "frontend"
    evaluation = root / "evaluation"
    os.chdir(backend_dir)
    sys.path.insert(0, str(backend_dir))

    from app.config import Settings

    settings = Settings()
    key = settings.sarvam_api_key
    print(json.dumps({"backend_settings_key_present": bool(key), "key_value_printed": False}))
    if not key or len(key) > 256:
        print("Stopped before inference: the backend Settings loader has no Sarvam credential.")
        return 2
    if settings.sarvam_model != MODEL:
        print(
            "Stopped before inference: the configured Sarvam model differs from the reviewed route."
        )
        return 2
    if (
        settings.sarvam_input_price_per_million_inr != 15.0
        or settings.sarvam_output_price_per_million_inr != 60.0
    ):
        print(
            "Stopped before inference: configured Sarvam prices differ from the reviewed public price table."
        )
        return 2

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    paths = {
        "output": evaluation / f"sarvam-research-validation-{timestamp}.json",
        "preflight": evaluation / f"sarvam-preflight-{timestamp}.json",
        "probe": evaluation / f"sarvam-compatibility-{timestamp}.json",
        "server_state": evaluation / f"sarvam-server-state-{timestamp}.json",
        "counter": evaluation / f"sarvam-request-count-{timestamp}.txt",
        "database": evaluation / f"veda-sarvam-{timestamp}.sqlite3",
    }
    if any(path.exists() for path in paths.values()):
        print("Stopped before inference: a timestamped result path already exists.")
        return 2

    preflight = {
        "checked_at": datetime.now(UTC).isoformat(),
        "model": MODEL,
        "provider": "sarvam",
        "endpoint": ENDPOINT,
        "strict_json_schema": True,
        "auth_header_name": "api-subscription-key",
        "input_price_per_million_inr": 15.0,
        "cached_input_price_per_million_inr": 5.0,
        "output_price_per_million_inr": 60.0,
        "prices_exclude_gst": True,
        "authorized_total_spend_ceiling_inr": MAX_SPEND_INR,
        "maximum_pre_tax_reservation_inr": MAX_PRETAX_RESERVATION_INR,
        "tax_and_billing_rounding_headroom_inr": MAX_SPEND_INR - MAX_PRETAX_RESERVATION_INR,
        "model_output_cap": 4096,
        "request_cap_including_probe": MAX_TOTAL_POSTS,
        "probe_reservation_inr": PROBE_RESERVATION_INR,
        "job_budget_ceiling_inr": JOB_BUDGET_INR,
        "combined_reservation_ceiling_inr": MAX_PRETAX_RESERVATION_INR,
        "paid_fallback": False,
        "automatic_inference_retries": 0,
        "openai_or_openrouter_inference": False,
        "billing_confirmation_source": "user_reported_settings_billing_review",
        "billing_safety_confirmation": "user confirmed Credits Left covers the bounded ceiling and Auto-recharge is off",
        "account_balance_api_checked": False,
        "billing_dashboard_confirmation_received": True,
        "billing_dashboard_independently_inspected_by_agent": False,
        "compatibility_probe_completion_token_cap": PROBE_OUTPUT_TOKEN_CAP,
        "official_docs": [
            "https://docs.sarvam.ai/api-reference/chat/chat-completions-v2",
            "https://docs.sarvam.ai/api/getting-started/pricing",
            "https://docs.sarvam.ai/api/platform/billing",
        ],
    }
    paths["preflight"].write_text(
        json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    env = os.environ.copy()
    env.update(
        {
            "SARVAM_API_KEY": key,
            "OPENAI_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "OPENROUTER_MODEL": "",
            "LLM_PROVIDER": "sarvam",
            "SARVAM_MODEL": MODEL,
            "ALLOW_PAID_LLM_CALLS": "true",
            "SARVAM_MAX_JOB_COST_INR": f"{JOB_BUDGET_INR:.2f}",
            "SARVAM_INPUT_PRICE_PER_MILLION_INR": "15",
            "SARVAM_OUTPUT_PRICE_PER_MILLION_INR": "60",
            "MAX_JOB_COST_USD": "0",
            "MAX_DAILY_MODEL_CALLS": str(MAX_JOB_POSTS),
            "MAX_DAILY_MODEL_CALLS_PER_USER": str(MAX_JOB_POSTS),
            "VEDA_SARVAM_LIVE_E2E": "1",
            "VEDA_SARVAM_BILLING_VERIFIED": "1",
            "VEDA_SARVAM_EXPECTED_MODEL": MODEL,
            "VEDA_SARVAM_RUN_ID": "t123-sarvam",
            "VEDA_SARVAM_OUTPUT_PATH": str(paths["output"]),
            "VEDA_SARVAM_PREFLIGHT_PATH": str(paths["preflight"]),
            "VEDA_SARVAM_COMPATIBILITY_PATH": str(paths["probe"]),
            "VEDA_SARVAM_SERVER_STATE_PATH": str(paths["server_state"]),
            "VEDA_SARVAM_REQUEST_COUNTER_PATH": str(paths["counter"]),
            "VEDA_SARVAM_DATABASE_PATH": str(paths["database"]),
            "VEDA_REAL_E2E_API_PORT": "8002",
            "VEDA_BACKEND_PYTHON": sys.executable,
        }
    )
    del key

    print(
        json.dumps(
            {
                "test": "one-question Sarvam Veda research validation",
                "question": QUESTION,
                "model": MODEL,
                "endpoint": ENDPOINT,
                "preflight_artifact": str(paths["preflight"]),
                "compatibility_artifact": str(paths["probe"]),
                "result_artifact": str(paths["output"]),
                "sqlite_database": str(paths["database"]),
                "provider_post_cap_including_probe": MAX_TOTAL_POSTS,
                "maximum_job_cost_inr": JOB_BUDGET_INR,
                "probe_pre_reserve_inr": PROBE_RESERVATION_INR,
                "combined_pre_reserve_ceiling_inr": MAX_PRETAX_RESERVATION_INR,
                "no_auto_retry": True,
                "paid_fallback": False,
                "openai_openrouter_calls": False,
            },
            ensure_ascii=False,
        )
    )
    completed: subprocess.CompletedProcess | None = None
    try:
        completed = subprocess.run(
            [
                os.environ.get("ComSpec", "cmd.exe"),
                "/d",
                "/c",
                "npm exec -- playwright test e2e/sarvam-single-question.e2e.ts "
                "--workers=1 --retries=0 --reporter=line",
            ],
            cwd=frontend,
            env=env,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    finally:
        env["SARVAM_API_KEY"] = ""
        os.environ.pop("SARVAM_API_KEY", None)
        artifact: dict[str, Any] = {}
        if paths["output"].is_file():
            try:
                artifact = json.loads(paths["output"].read_text(encoding="utf-8"))
            except (OSError, ValueError):
                artifact = {}
        if paths["probe"].is_file():
            try:
                artifact["compatibility_probe"] = json.loads(
                    paths["probe"].read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                artifact["compatibility_probe"] = {
                    "status": "artifact_unreadable",
                    "accepted": False,
                }
        if paths["server_state"].is_file():
            try:
                artifact["server_state"] = json.loads(
                    paths["server_state"].read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                artifact["server_state"] = {"status": "artifact_unreadable"}
        request_count = None
        if paths["counter"].is_file():
            try:
                text = paths["counter"].read_text(encoding="ascii").strip()
                request_count = int(text) if text.isdigit() else None
            except (OSError, ValueError):
                request_count = None
        artifact.update(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "authorization_scope": "one question; at most six Sarvam POSTs including one compatibility probe; no other model provider or top-up",
                "question": QUESTION,
                "configured_model": MODEL,
                "preflight": preflight,
                "provider_request_hard_cap": MAX_TOTAL_POSTS,
                "provider_request_attempts": request_count,
                "playwright_exit_code": completed.returncode if completed else None,
                "authorized_total_spend_ceiling_inr": MAX_SPEND_INR,
                "maximum_pre_tax_reservation_inr": MAX_PRETAX_RESERVATION_INR,
                "tax_and_billing_rounding_headroom_inr": MAX_SPEND_INR - MAX_PRETAX_RESERVATION_INR,
                "actual_reported_cost_inr": (artifact.get("usage_audit") or {}).get(
                    "reported_cost_inr"
                ),
                "actual_estimated_cost_inr": (artifact.get("usage_audit") or {}).get(
                    "estimated_cost_inr"
                ),
                "result_artifact_contains_raw_provider_response": False,
            }
        )
        paths["output"].write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return completed.returncode if completed else 2


if __name__ == "__main__":
    raise SystemExit(main())
