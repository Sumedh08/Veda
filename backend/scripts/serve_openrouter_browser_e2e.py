"""Serve the separately opted-in, free-only OpenRouter browser E2E API.

The ordinary browser harness always clears provider credentials. This entry
point is isolated and requires a second explicit opt-in before it restores an
OpenRouter key into a disposable local test process.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from serve_browser_e2e import configure_isolated_environment, seed_inspection_record


def openrouter_e2e_overrides(
    *, explicitly_opted_in: bool, api_key_present: bool, model: str
) -> dict[str, str]:
    """Validate the live mode without returning or logging credential material."""
    if not explicitly_opted_in:
        raise ValueError("Set VEDA_OPENROUTER_LIVE_E2E=1 to enable this test server.")
    if not api_key_present:
        raise ValueError("OPENROUTER_API_KEY must be supplied to the isolated test process.")
    if model != "openrouter/free" and not model.endswith(":free"):
        raise ValueError("The live browser test accepts only OpenRouter free model routes.")
    return {
        "LLM_PROVIDER": "openrouter",
        "OPENROUTER_MODEL": model,
        "OPENAI_API_KEY": "",
        "ALLOW_PAID_LLM_CALLS": "false",
        "MAX_JOB_COST_USD": "0.25",
        # Ten standard jobs are explicitly limited to five model calls each.
        # The free-only OpenRouter collection is currently capped at 50/day.
        "MAX_DAILY_MODEL_CALLS": "50",
        "MAX_DAILY_MODEL_CALLS_PER_USER": "50",
    }


def main() -> None:
    if os.environ.get("VEDA_OPENROUTER_LIVE_E2E") != "1":
        raise SystemExit("Set VEDA_OPENROUTER_LIVE_E2E=1 to enable this test server.")

    backend_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend_dir))
    os.environ.update(
        {
            "APP_ENV": "test",
            "LLM_PROVIDER": "disabled",
            "DEV_AUTH_ENABLED": "true",
            "DEV_AUTH_SECRET": secrets.token_urlsafe(48),
            "RATE_LIMIT_HASH_SECRET": secrets.token_urlsafe(48),
            "OPENAI_API_KEY": "",
            "ALLOW_PAID_LLM_CALLS": "false",
        }
    )

    # Settings reads the root .env when running from backend/. The test never
    # prints the key, and the default server helper clears all credentials next.
    import app.config as app_config

    configured_key = app_config.settings.openrouter_api_key
    configured_model = os.environ.get("OPENROUTER_MODEL", app_config.settings.openrouter_model)
    overrides = openrouter_e2e_overrides(
        explicitly_opted_in=True,
        api_key_present=bool(configured_key),
        model=configured_model,
    )

    with tempfile.TemporaryDirectory(prefix="veda-openrouter-browser-") as temp_dir:
        database_path = Path(temp_dir) / "openrouter-browser-e2e.sqlite"
        configure_isolated_environment(f"sqlite:///{database_path.as_posix()}")
        os.environ.update(overrides)
        os.environ["OPENROUTER_API_KEY"] = configured_key
        app_config.get_settings.cache_clear()
        app_config.settings = app_config.get_settings()

        # A rate-limit retry is another billable/limited provider request and
        # the free-tier test has a strict request ceiling. Fail this attempt
        # on a 429 and continue only through separately reserved Veda calls.
        import app.providers.llm as llm_provider
        from app.research.depth import PROFILES

        llm_provider.MAX_RATE_LIMIT_RETRIES = 0
        PROFILES["standard"] = replace(PROFILES["standard"], max_model_calls=5)
        request_attempts = 0
        original_post = llm_provider._post_with_rate_limit_retry

        def free_route_post(client, url, **kwargs):
            nonlocal request_attempts
            if request_attempts >= 50:
                from app.providers.llm import LLMProviderError

                raise LLMProviderError(
                    "The isolated free-only test reached its hard 50-request cap.",
                    code="free_test_request_cap",
                )
            request_attempts += 1
            return original_post(client, url, **kwargs)

        llm_provider._post_with_rate_limit_retry = free_route_post

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=backend_dir,
            check=True,
        )
        seed_inspection_record()

        import uvicorn

        from app.db import engine
        from app.main import app

        try:
            uvicorn.run(
                app,
                host="127.0.0.1",
                port=int(os.environ.get("VEDA_REAL_E2E_API_PORT", "8001")),
                log_level="warning",
            )
        finally:
            engine.dispose()
            result_path = os.environ.get("VEDA_OPENROUTER_OUTPUT_PATH")
            if result_path and Path(result_path).is_file():
                try:
                    result = json.loads(Path(result_path).read_text(encoding="utf-8"))
                    result["provider_request_attempts"] = request_attempts
                    result["provider_request_hard_cap"] = 50
                    result["provider_rate_limit_retries"] = 0
                    Path(result_path).write_text(
                        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                except (OSError, ValueError):
                    # The browser test may fail before producing its report;
                    # do not put provider data or credentials into server logs.
                    pass


if __name__ == "__main__":
    main()
