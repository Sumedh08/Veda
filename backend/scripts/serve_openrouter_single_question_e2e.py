"""Serve the bounded T-112 single-question OpenRouter browser/API run."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from serve_browser_e2e import configure_isolated_environment, seed_inspection_record

MAX_PROVIDER_REQUESTS = 6
T112_MODEL = "nvidia/nemotron-3.5-super-vl:free"
RESEARCH_MODEL = "xingchen-agi/xing4.0-29b-a4b:free"


def single_question_overrides(
    *, explicitly_opted_in: bool, api_key_present: bool, model: str
) -> dict[str, str]:
    if not explicitly_opted_in:
        raise ValueError("Set VEDA_OPENROUTER_LIVE_E2E=1 to enable T-112.")
    if not api_key_present:
        raise ValueError("OPENROUTER_API_KEY must be supplied to the isolated API process.")
    if model != T112_MODEL or not model.endswith(":free"):
        raise ValueError("T-112 only accepts the preflight-pinned free model route.")
    return {
        "LLM_PROVIDER": "openrouter",
        "OPENROUTER_MODEL": T112_MODEL,
        "OPENAI_API_KEY": "",
        "ALLOW_PAID_LLM_CALLS": "false",
        "MAX_JOB_COST_USD": "0",
        "MAX_DAILY_MODEL_CALLS": str(MAX_PROVIDER_REQUESTS),
        "MAX_DAILY_MODEL_CALLS_PER_USER": str(MAX_PROVIDER_REQUESTS),
    }


def research_validation_overrides(
    *, explicitly_opted_in: bool, api_key_present: bool, model: str
) -> dict[str, str]:
    """Guard the preflighted research route with reasoning explicitly disabled."""
    if not explicitly_opted_in:
        raise ValueError("Set VEDA_OPENROUTER_LIVE_E2E=1 to enable the research validation run.")
    if not api_key_present:
        raise ValueError("OPENROUTER_API_KEY must be supplied to the isolated API process.")
    if model != RESEARCH_MODEL:
        raise ValueError("Research validation only accepts the metadata-preflighted free route.")
    return {
        "LLM_PROVIDER": "openrouter",
        "OPENROUTER_MODEL": RESEARCH_MODEL,
        "OPENROUTER_REASONING_ENABLED": "false",
        "OPENAI_API_KEY": "",
        "ALLOW_PAID_LLM_CALLS": "false",
        "MAX_JOB_COST_USD": "0",
        "MAX_DAILY_MODEL_CALLS": str(MAX_PROVIDER_REQUESTS),
        "MAX_DAILY_MODEL_CALLS_PER_USER": str(MAX_PROVIDER_REQUESTS),
    }


def refresh_t112_settings(app_config):
    """Reload settings after applying isolated DB/provider environment values."""
    app_config.get_settings.cache_clear()
    app_config.settings = app_config.get_settings()
    return app_config.settings


def _request_counter_path() -> Path:
    raw_path = os.environ.get("VEDA_OPENROUTER_REQUEST_COUNTER_PATH", "").strip()
    if not raw_path:
        raise ValueError("T-112 requires a request-counter file before provider dispatch.")
    path = Path(raw_path).resolve()
    evaluation_dir = Path(__file__).resolve().parents[2] / "evaluation"
    try:
        path.relative_to(evaluation_dir.resolve())
    except ValueError:
        raise ValueError(
            "T-112 request counters must remain in the repository evaluation directory."
        ) from None
    if path.suffix.lower() != ".txt" or path.exists():
        raise ValueError("T-112 requires a new request-counter .txt file.")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def persist_request_count(path: Path, request_count: int) -> None:
    if type(request_count) is not int or not 0 <= request_count <= MAX_PROVIDER_REQUESTS:
        raise ValueError("T-112 provider request counter is outside its hard bound.")
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(f"{request_count}\n", encoding="ascii")
    temporary_path.replace(path)


def _database_url() -> str:
    raw_path = os.environ.get("VEDA_OPENROUTER_DATABASE_PATH", "").strip()
    if not raw_path:
        raise ValueError("VEDA_OPENROUTER_DATABASE_PATH must name a unique local SQLite file.")
    path = Path(raw_path).resolve()
    evaluation_dir = Path(__file__).resolve().parents[2] / "evaluation"
    try:
        path.relative_to(evaluation_dir.resolve())
    except ValueError:
        raise ValueError(
            "T-112 SQLite files must remain in the repository evaluation directory."
        ) from None
    resume_job_id = os.environ.get("VEDA_OPENROUTER_RESUME_JOB_ID", "").strip()
    run_id = os.environ.get("VEDA_OPENROUTER_RUN_ID", "t112")
    prefix = "veda-t112-" if run_id == "t112" else "veda-research-" if run_id == "research" else ""
    if path.suffix.lower() != ".sqlite3" or not prefix or not path.name.startswith(prefix):
        raise ValueError("The isolated run requires a uniquely named evaluation .sqlite3 file.")
    if bool(resume_job_id) != path.is_file():
        raise ValueError("T-112 database existence must match the validated resume mode.")
    if path.exists() and not path.is_file():
        raise ValueError("T-112 database path must be a regular file.")
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


def validate_resumable_job(job_id: str) -> None:
    """Refuse resumption unless the prior browser error left a pristine queued job."""
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models import Project, ResearchJob, UsageEntry
    from app.security import LOCAL_USER_ID

    expected_question = "Does generative AI improve software developer productivity, and why do empirical studies sometimes report different findings?"
    with SessionLocal() as session:
        job = session.get(ResearchJob, job_id)
        project = session.get(Project, job.project_id) if job else None
        usage_count = session.scalar(
            select(func.count()).select_from(UsageEntry).where(UsageEntry.job_id == job_id)
        )
        if (
            job is None
            or project is None
            or project.owner_id != LOCAL_USER_ID
            or project.title != "Local browser integration (synthetic data)"
            or job.question != expected_question
            or job.status != "queued"
            or job.current_stage != "planning"
            or job.model_calls_reserved != 0
            or usage_count != 0
        ):
            raise ValueError(
                "T-112 resume database does not contain the expected untouched local job."
            )


def main() -> None:
    if os.environ.get("VEDA_OPENROUTER_LIVE_E2E") != "1":
        raise SystemExit("Set VEDA_OPENROUTER_LIVE_E2E=1 to enable this bounded local run.")

    backend_dir = Path(__file__).resolve().parents[1]
    repository_root = backend_dir.parent
    sys.path.insert(0, str(backend_dir))
    sys.path.insert(0, str(repository_root / "evaluation" / "scripts"))
    run_id = os.environ.get("VEDA_OPENROUTER_RUN_ID", "t112")
    model = os.environ.get("OPENROUTER_MODEL", T112_MODEL)
    if run_id == "research":
        from verify_openrouter_research_route import fetch_route_metadata

        route_model = RESEARCH_MODEL
        preflight_label = "research validation"
    elif run_id == "t112":
        from verify_openrouter_free_route import fetch_route_metadata

        route_model = T112_MODEL
        preflight_label = "T-112"
    else:
        raise SystemExit(
            "Unsupported OpenRouter research-run profile; no provider request was sent."
        )

    try:
        dispatch_preflight = fetch_route_metadata(route_model)
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        raise SystemExit(
            f"{preflight_label} server stopped before provider dispatch: free-route preflight failed ({type(exc).__name__})."
        ) from None

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

    import app.config as app_config

    configured_key = app_config.settings.openrouter_api_key
    if run_id == "research":
        overrides = research_validation_overrides(
            explicitly_opted_in=True,
            api_key_present=bool(configured_key),
            model=model,
        )
    else:
        overrides = single_question_overrides(
            explicitly_opted_in=True,
            api_key_present=bool(configured_key),
            model=model,
        )
    database_url = _database_url()
    request_counter_path = _request_counter_path()
    configure_isolated_environment(database_url)
    os.environ.update(overrides)
    os.environ.update(
        {
            "FRONTEND_ORIGINS": "http://127.0.0.1:5176",
            "RATE_LIMIT_USER_PER_MINUTE": "10000",
            "RATE_LIMIT_IP_PER_MINUTE": "20000",
            "RATE_LIMIT_USER_ADVANCES_PER_MINUTE": "1000",
            "RATE_LIMIT_IP_ADVANCES_PER_MINUTE": "2000",
            "OPENALEX_ALLOW_BILLABLE_CALLS": "false",
            "OPENALEX_API_KEY": "",
            "CROSSREF_MAILTO": "",
        }
    )

    # Rebuild settings before importing app.db; otherwise its engine keeps the
    # repository's default development SQLite URL instead of the isolated T-112
    # database. The credential remains in this API process only.
    os.environ["OPENROUTER_API_KEY"] = configured_key
    refresh_t112_settings(app_config)
    persist_request_count(request_counter_path, 0)

    # Do not pass the credential to the migration subprocess.
    migration_env = os.environ.copy()
    migration_env["OPENROUTER_API_KEY"] = ""
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        env=migration_env,
        check=True,
    )
    resume_job_id = os.environ.get("VEDA_OPENROUTER_RESUME_JOB_ID", "").strip()
    if resume_job_id:
        validate_resumable_job(resume_job_id)
    else:
        seed_inspection_record()

    import app.providers.llm as llm_provider
    from app.research.depth import PROFILES

    llm_provider.MAX_RATE_LIMIT_RETRIES = 0
    PROFILES["standard"] = replace(
        PROFILES["standard"],
        max_model_calls=MAX_PROVIDER_REQUESTS,
        max_retries=0,
    )
    request_attempts = 0
    original_post = llm_provider._post_with_rate_limit_retry

    def capped_post(client, url, **kwargs):
        nonlocal request_attempts
        if request_attempts >= MAX_PROVIDER_REQUESTS:
            from app.providers.llm import LLMProviderError

            raise LLMProviderError(
                "T-112 reached its hard six-request provider cap.",
                code="t112_provider_request_cap",
            )
        request_attempts += 1
        persist_request_count(request_counter_path, request_attempts)
        return original_post(client, url, **kwargs)

    llm_provider._post_with_rate_limit_retry = capped_post

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
        os.environ.pop("OPENROUTER_API_KEY", None)
        result_path = os.environ.get("VEDA_OPENROUTER_OUTPUT_PATH")
        if result_path and Path(result_path).is_file():
            try:
                result = json.loads(Path(result_path).read_text(encoding="utf-8"))
                result["provider_request_attempts"] = request_attempts
                result["provider_request_hard_cap"] = MAX_PROVIDER_REQUESTS
                result["provider_rate_limit_retries"] = 0
                result["provider_request_counter_path"] = str(request_counter_path)
                result["database_path"] = os.environ.get("VEDA_OPENROUTER_DATABASE_PATH")
                result["dispatch_preflight"] = dispatch_preflight
                Path(result_path).write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except (OSError, ValueError):
                pass


if __name__ == "__main__":
    main()
