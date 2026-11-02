from copy import deepcopy

import pytest
import yaml

from scripts.validate_render_blueprint import BLUEPRINT_PATH, validate_preview_safety


@pytest.fixture
def blueprint():
    return yaml.safe_load(BLUEPRINT_PATH.read_text(encoding="utf-8"))


def _service(blueprint, name: str) -> dict:
    return next(service for service in blueprint["services"] if service["name"] == name)


def _env(service: dict, name: str) -> dict:
    return next(item for item in service["envVars"] if item.get("key") == name)


def test_preview_api_and_static_frontend_blueprint_pass_local_safety_policy(blueprint):
    validate_preview_safety(deepcopy(blueprint))


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    [
        ("database", "must not provision a database"),
        ("paid_api_plan", "API service must remain free"),
        ("api_auto_deploy", "API service must remain free"),
        ("frontend_auto_deploy", "frontend must remain a manual-deploy"),
        ("paid_model_provider", "must set LLM_PROVIDER=disabled"),
        ("paid_model_calls", "must set ALLOW_PAID_LLM_CALLS=false"),
        ("hardcoded_database_url", "must prompt for DATABASE_URL"),
        ("hardcoded_frontend_origin", "must prompt for FRONTEND_ORIGINS"),
        ("hardcoded_api_url", "must prompt for VITE_API_BASE_URL"),
        ("hardcoded_auth_config", "must prompt for VITE_SUPABASE_URL"),
        ("service_linked_api_url", "must prompt for VITE_API_BASE_URL"),
        ("changed_frontend_root", "must remain a manual-deploy"),
        ("changed_publish_directory", "must remain a manual-deploy"),
        ("missing_anon_key_prompt", "must prompt for VITE_SUPABASE_ANON_KEY"),
    ],
)
def test_preview_policy_rejects_unsafe_blueprint_changes(
    blueprint, mutation: str, expected_message: str
):
    unsafe = deepcopy(blueprint)
    api = _service(unsafe, "veda-api")
    frontend = _service(unsafe, "veda-web")

    if mutation == "database":
        unsafe["databases"] = [{"name": "temporary-db"}]
    elif mutation == "paid_api_plan":
        api["plan"] = "standard"
    elif mutation == "api_auto_deploy":
        api["autoDeployTrigger"] = "commit"
    elif mutation == "frontend_auto_deploy":
        frontend["autoDeployTrigger"] = "commit"
    elif mutation == "paid_model_provider":
        _env(api, "LLM_PROVIDER")["value"] = "openrouter"
    elif mutation == "paid_model_calls":
        _env(api, "ALLOW_PAID_LLM_CALLS")["value"] = "true"
    elif mutation == "hardcoded_database_url":
        _env(api, "DATABASE_URL").update(sync=False, value="postgresql://example.invalid")
    elif mutation == "hardcoded_frontend_origin":
        _env(api, "FRONTEND_ORIGINS").update(sync=False, value="https://veda.example")
    elif mutation == "hardcoded_api_url":
        _env(frontend, "VITE_API_BASE_URL")["value"] = "https://veda-api.example/api/v1"
    elif mutation == "hardcoded_auth_config":
        _env(frontend, "VITE_SUPABASE_URL")["value"] = "https://auth.example"
    elif mutation == "service_linked_api_url":
        _env(frontend, "VITE_API_BASE_URL")["fromService"] = {"name": "veda-api", "type": "web"}
    elif mutation == "changed_frontend_root":
        frontend["rootDir"] = "."
    elif mutation == "changed_publish_directory":
        frontend["staticPublishPath"] = "build"
    elif mutation == "missing_anon_key_prompt":
        frontend["envVars"] = [
            item for item in frontend["envVars"] if item.get("key") != "VITE_SUPABASE_ANON_KEY"
        ]

    with pytest.raises(SystemExit) as error:
        validate_preview_safety(unsafe)
    assert expected_message in str(error.value)
