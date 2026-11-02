"""Run one pinned free-model Veda research job through the real local browser/API.

The public catalog preflight is read-only. A single provider-backed job is
started only when the caller explicitly opts in and a key is already available
to this local process or the ignored repository-root .env file. The key is
passed only to the isolated backend server process and is never printed or
written to artifacts.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

MODEL = "xingchen-agi/xing4.0-29b-a4b:free"
QUESTION = (
    "Does generative AI improve software developer productivity, and why do empirical "
    "studies sometimes report different findings?"
)
MAX_PROVIDER_REQUESTS = 6


def _available_key() -> str:
    """Read the key from process settings without ever echoing it."""
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        from app.config import Settings

        key = Settings().openrouter_api_key
    return key if isinstance(key, str) and 0 < len(key) <= 256 else ""


def main() -> int:
    if os.environ.get("VEDA_OPENROUTER_LIVE_E2E") != "1":
        print("Set VEDA_OPENROUTER_LIVE_E2E=1 to explicitly opt in; no request was sent.")
        return 2

    backend_dir = Path(__file__).resolve().parents[1]
    repository_root = backend_dir.parent
    evaluation = repository_root / "evaluation"
    frontend = repository_root / "frontend"
    os.chdir(backend_dir)
    sys.path.insert(0, str(backend_dir))
    sys.path.insert(0, str(evaluation / "scripts"))

    from verify_openrouter_research_route import fetch_route_metadata

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    artifact_path = evaluation / f"openrouter-research-validation-{timestamp}.json"
    preflight_path = evaluation / f"openrouter-research-preflight-{timestamp}.json"
    request_counter_path = evaluation / f"openrouter-research-request-count-{timestamp}.txt"
    database_path = evaluation / f"veda-research-{timestamp}.sqlite3"
    output_paths = (artifact_path, preflight_path, request_counter_path, database_path)
    if any(path.exists() for path in output_paths):
        print("Refusing to replace an existing research-validation artifact; no request was sent.")
        return 2

    try:
        preflight = fetch_route_metadata(MODEL)
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(
            f"Research validation stopped before inference: free-route preflight failed "
            f"({type(exc).__name__}); no inference request was sent."
        )
        return 2

    preflight_path.write_text(
        json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    key = _available_key()
    if not key:
        artifact_path.write_text(
            json.dumps(
                {
                    "test": "one-question OpenRouter Veda research validation",
                    "question": QUESTION,
                    "model": MODEL,
                    "status": "not_dispatched_missing_credential",
                    "inference_requests_sent": 0,
                    "provider_request_hard_cap": MAX_PROVIDER_REQUESTS,
                    "preflight_artifact": str(preflight_path),
                    "error_class": "credential_unavailable_in_local_environment",
                    "limitation": (
                        "No OPENROUTER_API_KEY was present in the process or ignored "
                        "repository-root .env; the credential previously posted in chat "
                        "was not reconstructed or reused."
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            "Public free-route preflight passed, but OPENROUTER_API_KEY is unavailable "
            "in the process and ignored repository-root .env. No inference request was sent. "
            f"Safe preflight and blocker records: {preflight_path} and {artifact_path}"
        )
        return 2

    os.environ.update(
        {
            "OPENROUTER_API_KEY": key,
            "OPENAI_API_KEY": "",
            "OPENROUTER_MODEL": MODEL,
            "OPENROUTER_REASONING_ENABLED": "false",
            "LLM_PROVIDER": "openrouter",
            "ALLOW_PAID_LLM_CALLS": "false",
            "MAX_JOB_COST_USD": "0",
            "MAX_DAILY_MODEL_CALLS": str(MAX_PROVIDER_REQUESTS),
            "MAX_DAILY_MODEL_CALLS_PER_USER": str(MAX_PROVIDER_REQUESTS),
            "VEDA_OPENROUTER_LIVE_E2E": "1",
            "VEDA_OPENROUTER_SINGLE_QUESTION_E2E": "1",
            "VEDA_OPENROUTER_RUN_ID": "research",
            "VEDA_OPENROUTER_EXPECTED_MODEL": MODEL,
            "VEDA_OPENROUTER_OUTPUT_PATH": str(artifact_path),
            "VEDA_OPENROUTER_PREFLIGHT_PATH": str(preflight_path),
            "VEDA_OPENROUTER_REQUEST_COUNTER_PATH": str(request_counter_path),
            "VEDA_OPENROUTER_DATABASE_PATH": str(database_path),
            "VEDA_REAL_E2E_API_PORT": "8001",
            "VEDA_BACKEND_PYTHON": sys.executable,
        }
    )
    del key

    print(
        json.dumps(
            {
                "test": "one-question OpenRouter Veda research validation",
                "question": QUESTION,
                "model": MODEL,
                "route_preflight_artifact": str(preflight_path),
                "result_artifact": str(artifact_path),
                "sqlite_database": str(database_path),
                "provider_request_hard_cap": MAX_PROVIDER_REQUESTS,
                "automatic_model_retries": 0,
                "paid_fallback": False,
                "reported_price_metadata": "prompt/completion zero; request price unknown",
                "account_level_billing": "unconfirmed",
            },
            ensure_ascii=False,
        )
    )
    try:
        # One Playwright invocation, one question, no runner-level retry.
        completed = subprocess.run(
            [
                os.environ.get("ComSpec", "cmd.exe"),
                "/d",
                "/c",
                "npm exec -- playwright test e2e/openrouter-single-question.e2e.ts "
                "--workers=1 --retries=0 --reporter=line",
            ],
            cwd=frontend,
            stdin=subprocess.DEVNULL,
            check=False,
        )
        return completed.returncode
    finally:
        # The parent process does not retain a key after the test process ends.
        os.environ.pop("OPENROUTER_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)


if __name__ == "__main__":
    raise SystemExit(main())
