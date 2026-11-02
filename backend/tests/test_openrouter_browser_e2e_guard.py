import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import get_settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend" / "scripts"))

from run_openrouter_single_question_e2e import (  # noqa: E402
    T112_QUESTION,
    load_resumable_attempt,
)
from serve_browser_e2e import configure_isolated_environment  # noqa: E402
from serve_openrouter_browser_e2e import openrouter_e2e_overrides  # noqa: E402
from serve_openrouter_single_question_e2e import (  # noqa: E402
    MAX_PROVIDER_REQUESTS,
    RESEARCH_MODEL,
    T112_MODEL,
    persist_request_count,
    research_validation_overrides,
    single_question_overrides,
)


def test_live_openrouter_browser_server_requires_explicit_opt_in():
    with pytest.raises(ValueError, match="VEDA_OPENROUTER_LIVE_E2E=1"):
        openrouter_e2e_overrides(
            explicitly_opted_in=False,
            api_key_present=True,
            model="openrouter/free",
        )


def test_default_browser_server_clears_all_provider_keys_and_stays_disabled():
    previous = os.environ.copy()
    try:
        configure_isolated_environment("sqlite:///temporary-browser-test.sqlite")

        assert os.environ["LLM_PROVIDER"] == "disabled"
        assert os.environ["ALLOW_PAID_LLM_CALLS"] == "false"
        assert os.environ["OPENAI_API_KEY"] == ""
        assert os.environ["OPENROUTER_API_KEY"] == ""
        assert os.environ["OPENALEX_API_KEY"] == ""
    finally:
        os.environ.clear()
        os.environ.update(previous)


def test_isolated_browser_server_uses_explicit_private_research_settings():
    previous = os.environ.copy()
    try:
        configure_isolated_environment("sqlite:///temporary-browser-test.sqlite")
        get_settings.cache_clear()
        effective_settings = get_settings()
        assert effective_settings.rights_use_mode == "private_research"
        assert effective_settings.rights_jurisdiction == "IN"
    finally:
        get_settings.cache_clear()
        os.environ.clear()
        os.environ.update(previous)


def test_live_openrouter_browser_server_requires_a_configured_key_without_echoing_it():
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY must be supplied") as error:
        openrouter_e2e_overrides(
            explicitly_opted_in=True,
            api_key_present=False,
            model="openrouter/free",
        )

    assert "sk-or-" not in str(error.value)


@pytest.mark.parametrize("model", ["openai/gpt-4o", "openrouter/paid-model"])
def test_live_openrouter_browser_server_rejects_non_free_routes(model: str):
    with pytest.raises(ValueError, match="only OpenRouter free model routes"):
        openrouter_e2e_overrides(
            explicitly_opted_in=True,
            api_key_present=True,
            model=model,
        )


@pytest.mark.parametrize("model", ["openrouter/free", "example/provider-model:free"])
def test_live_openrouter_browser_server_hardens_free_route_settings(model: str):
    overrides = openrouter_e2e_overrides(
        explicitly_opted_in=True,
        api_key_present=True,
        model=model,
    )

    assert overrides["LLM_PROVIDER"] == "openrouter"
    assert overrides["OPENROUTER_MODEL"] == model
    assert overrides["OPENAI_API_KEY"] == ""
    assert overrides["ALLOW_PAID_LLM_CALLS"] == "false"
    assert overrides["MAX_JOB_COST_USD"] == "0.25"
    assert overrides["MAX_DAILY_MODEL_CALLS"] == "50"
    assert overrides["MAX_DAILY_MODEL_CALLS_PER_USER"] == "50"
    assert "OPENROUTER_API_KEY" not in overrides


def test_t112_single_question_guard_uses_zero_price_and_six_request_caps():
    overrides = single_question_overrides(
        explicitly_opted_in=True,
        api_key_present=True,
        model=T112_MODEL,
    )

    assert MAX_PROVIDER_REQUESTS == 6
    assert overrides["OPENROUTER_MODEL"] == T112_MODEL
    assert overrides["ALLOW_PAID_LLM_CALLS"] == "false"
    assert overrides["MAX_JOB_COST_USD"] == "0"
    assert overrides["MAX_DAILY_MODEL_CALLS"] == "6"
    assert overrides["MAX_DAILY_MODEL_CALLS_PER_USER"] == "6"
    assert "OPENROUTER_API_KEY" not in overrides


def test_t112_single_question_guard_rejects_unpinned_or_unfree_route():
    with pytest.raises(ValueError, match="preflight-pinned free model"):
        single_question_overrides(
            explicitly_opted_in=True,
            api_key_present=True,
            model="openrouter/free",
        )


def test_research_validation_guard_uses_pinned_free_route_and_disables_paid_fallbacks():
    overrides = research_validation_overrides(
        explicitly_opted_in=True,
        api_key_present=True,
        model=RESEARCH_MODEL,
    )

    assert MAX_PROVIDER_REQUESTS == 6
    assert overrides["LLM_PROVIDER"] == "openrouter"
    assert overrides["OPENROUTER_MODEL"] == "xingchen-agi/xing4.0-29b-a4b:free"
    assert overrides["OPENROUTER_REASONING_ENABLED"] == "false"
    assert overrides["OPENAI_API_KEY"] == ""
    assert overrides["ALLOW_PAID_LLM_CALLS"] == "false"
    assert overrides["MAX_JOB_COST_USD"] == "0"
    assert overrides["MAX_DAILY_MODEL_CALLS"] == "6"
    assert overrides["MAX_DAILY_MODEL_CALLS_PER_USER"] == "6"
    assert "OPENROUTER_API_KEY" not in overrides


def test_research_validation_guard_rejects_other_routes_and_missing_opt_in():
    with pytest.raises(ValueError, match="only accepts the metadata-preflighted free route"):
        research_validation_overrides(
            explicitly_opted_in=True,
            api_key_present=True,
            model="openrouter/free",
        )
    with pytest.raises(ValueError, match="enable the research validation run"):
        research_validation_overrides(
            explicitly_opted_in=False,
            api_key_present=True,
            model=RESEARCH_MODEL,
        )
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        research_validation_overrides(
            explicitly_opted_in=True,
            api_key_present=False,
            model=RESEARCH_MODEL,
        )


def test_research_validation_database_requires_research_scoped_sqlite_name(monkeypatch):
    from serve_openrouter_single_question_e2e import _database_url

    valid_path = REPOSITORY_ROOT / "evaluation" / "veda-research-guard-test.sqlite3"
    invalid_path = REPOSITORY_ROOT / "evaluation" / "veda-t112-guard-test.sqlite3"
    monkeypatch.setenv("VEDA_OPENROUTER_RUN_ID", "research")
    monkeypatch.setenv("VEDA_OPENROUTER_DATABASE_PATH", str(valid_path))
    monkeypatch.delenv("VEDA_OPENROUTER_RESUME_JOB_ID", raising=False)
    assert _database_url().endswith("/evaluation/veda-research-guard-test.sqlite3")

    monkeypatch.setenv("VEDA_OPENROUTER_DATABASE_PATH", str(invalid_path))
    with pytest.raises(ValueError, match="uniquely named evaluation"):
        _database_url()


def test_t112_request_counter_is_atomically_replaced_and_hard_bounded(tmp_path):
    counter_path = tmp_path / "provider-requests.txt"

    persist_request_count(counter_path, 0)
    assert counter_path.read_text(encoding="ascii") == "0\n"
    persist_request_count(counter_path, MAX_PROVIDER_REQUESTS)
    assert counter_path.read_text(encoding="ascii") == "6\n"
    assert not counter_path.with_suffix(".txt.tmp").exists()

    with pytest.raises(ValueError, match="outside its hard bound"):
        persist_request_count(counter_path, MAX_PROVIDER_REQUESTS + 1)


def test_t112_database_engine_binds_to_isolated_url_after_settings_reload():
    backend_dir = REPOSITORY_ROOT / "backend"
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "test",
            "DATABASE_URL": "sqlite:///./veda.db",
            "LLM_PROVIDER": "disabled",
            "OPENROUTER_API_KEY": "test-only-secret",
            "OPENAI_API_KEY": "",
            "ALLOW_PAID_LLM_CALLS": "false",
            "DEV_AUTH_ENABLED": "true",
            "DEV_AUTH_SECRET": "test-only-development-secret-0123456789",
            "RATE_LIMIT_HASH_SECRET": "test-only-rate-limit-secret-0123456789",
        }
    )
    script = """
import os
import sys
sys.path.insert(0, sys.argv[1])
import app.config as app_config
assert app_config.settings.database_url == "sqlite:///./veda.db"
os.environ.update({
    "DATABASE_URL": "sqlite:///./veda-t112-isolated.sqlite3",
    "LLM_PROVIDER": "openrouter",
    "OPENROUTER_MODEL": "nvidia/nemotron-3.5-super-vl:free",
})
from serve_openrouter_single_question_e2e import refresh_t112_settings
settings = refresh_t112_settings(app_config)
from app.db import engine
assert settings.database_url == "sqlite:///./veda-t112-isolated.sqlite3"
assert engine.url.database == "./veda-t112-isolated.sqlite3"
assert settings.openrouter_api_key == "test-only-secret"
engine.dispose()
print("isolated_engine_binding_verified")
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(backend_dir / "scripts")],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "isolated_engine_binding_verified"


def _write_resume_fixture(evaluation: Path, *, overrides: dict | None = None) -> Path:
    evaluation.mkdir(parents=True, exist_ok=True)
    timestamp = "20261029T205811Z"
    database = evaluation / f"veda-t112-{timestamp}.sqlite3"
    database.touch()
    artifact = {
        "configured_model": T112_MODEL,
        "question": T112_QUESTION,
        "job_id": "900c3b8d-e857-4a60-a530-0650fec1fa6e",
        "job_status": "queued",
        "current_stage": "planning",
        "model_calls_reserved": 0,
        "provider_usage": [],
        "usage_audit": {"accepted_response_count": 0},
        "errors": [{"stage": "planning", "class": "ReferenceError"}],
        "job": {
            "id": "900c3b8d-e857-4a60-a530-0650fec1fa6e",
            "question": T112_QUESTION,
            "status": "queued",
            "current_stage": "planning",
            "model_calls_reserved": 0,
        },
    }
    artifact.update(overrides or {})
    path = evaluation / f"openrouter-t112-{timestamp}.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return path


def test_t112_resume_accepts_only_pristine_queued_pre_dispatch_job(tmp_path):
    evaluation = tmp_path / "evaluation"
    artifact_path = _write_resume_fixture(evaluation)

    artifact, database_path, job_id = load_resumable_attempt(artifact_path, evaluation)

    assert artifact["job_status"] == "queued"
    assert database_path.name == "veda-t112-20261029T205811Z.sqlite3"
    assert job_id == "900c3b8d-e857-4a60-a530-0650fec1fa6e"


@pytest.mark.parametrize(
    "overrides",
    [
        {"provider_usage": [{"operation": "planning"}]},
        {"model_calls_reserved": 1},
        {"job_status": "failed"},
        {"configured_model": "openrouter/paid-model"},
        {"errors": [{"stage": "planning", "class": "timeout"}]},
    ],
)
def test_t112_resume_rejects_any_attempt_with_provider_use_or_changed_state(tmp_path, overrides):
    evaluation = tmp_path / "evaluation"
    artifact_path = _write_resume_fixture(evaluation, overrides=overrides)

    with pytest.raises(ValueError, match="not an untouched queued T-112 job"):
        load_resumable_attempt(artifact_path, evaluation)


def test_t112_browser_status_set_is_declared_inside_serialized_evaluate_callback():
    source = (REPOSITORY_ROOT / "frontend" / "e2e" / "openrouter-single-question.e2e.ts").read_text(
        encoding="utf-8"
    )
    browser_callback = source.split("const run = await page.evaluate(async (", 1)[1].split(
        "}, { apiOrigin, researchQuestion: question, resumeJobId });", 1
    )[0]

    assert "const terminalStatuses = new Set" in browser_callback
    assert "resumeJobId, runId }) =>" in source
