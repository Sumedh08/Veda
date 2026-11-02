"""Validate the repository's Render Blueprint schema and preview-only safety policy."""

import json
from pathlib import Path
from urllib.request import Request, urlopen

import yaml
from jsonschema import Draft202012Validator

SCHEMA_URL = "https://render.com/schema/render.yaml.json"
MAX_SCHEMA_BYTES = 1_000_000
BLUEPRINT_PATH = Path(__file__).resolve().parents[2] / "render.yaml"


def main() -> None:
    request = Request(SCHEMA_URL, headers={"User-Agent": "Veda-Blueprint-Validator/1.0"})
    with urlopen(request, timeout=15) as response:
        schema_bytes = response.read(MAX_SCHEMA_BYTES + 1)
    if len(schema_bytes) > MAX_SCHEMA_BYTES:
        raise SystemExit("Render schema exceeded the 1 MB validation cap")

    schema = json.loads(schema_bytes)
    blueprint = yaml.safe_load(BLUEPRINT_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(blueprint)
    validate_preview_safety(blueprint)
    print(f"Render Blueprint schema and preview-safety checks passed: {BLUEPRINT_PATH}")


def validate_preview_safety(blueprint: dict) -> None:
    """Fail closed if this preview blueprint starts provisioning or enabling paid services."""
    if blueprint.get("databases"):
        raise SystemExit("Render preview Blueprint must not provision a database")

    services = blueprint.get("services")
    if not isinstance(services, list) or len(services) != 2:
        raise SystemExit("Render preview Blueprint must define exactly the API and static frontend")

    services_by_name = {service.get("name"): service for service in services}
    service = services_by_name.get("veda-api", {})
    if (
        service.get("name") != "veda-api"
        or service.get("type") != "web"
        or service.get("runtime") != "docker"
        or service.get("plan") != "free"
        or service.get("autoDeployTrigger") != "off"
        or service.get("healthCheckPath") != "/api/v1/health/ready"
    ):
        raise SystemExit("Render API service must remain free, manual-deploy, and health-checked")

    env = {item.get("key"): item for item in service.get("envVars", [])}
    required_values = {
        "APP_ENV": "production",
        "DEV_AUTH_ENABLED": "false",
        "LLM_PROVIDER": "disabled",
        "ALLOW_PAID_LLM_CALLS": "false",
    }
    for name, value in required_values.items():
        if env.get(name, {}).get("value") != value:
            raise SystemExit(f"Render preview Blueprint must set {name}={value}")

    for name in ("DATABASE_URL", "FRONTEND_ORIGINS", "SUPABASE_URL", "SUPABASE_JWKS_URL"):
        setting = env.get(name, {})
        if setting.get("sync") is not False or any(
            key in setting for key in ("value", "fromService", "fromGroup", "generateValue")
        ):
            raise SystemExit(f"Render preview Blueprint must prompt for {name}; never hardcode it")
    if env.get("RATE_LIMIT_HASH_SECRET", {}).get("generateValue") is not True:
        raise SystemExit("Render preview Blueprint must generate its rate-limit hash secret")

    frontend = services_by_name.get("veda-web", {})
    if (
        frontend.get("type") != "web"
        or frontend.get("runtime") != "static"
        or frontend.get("rootDir") != "frontend"
        or frontend.get("buildCommand") != "npm ci && npm run build"
        or frontend.get("staticPublishPath") != "dist"
        or frontend.get("autoDeployTrigger") != "off"
    ):
        raise SystemExit("Render frontend must remain a manual-deploy Vite static site")

    frontend_env = {item.get("key"): item for item in frontend.get("envVars", [])}
    for name in ("VITE_API_BASE_URL", "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
        setting = frontend_env.get(name, {})
        if setting.get("sync") is not False or any(
            key in setting for key in ("value", "fromService", "fromGroup", "generateValue")
        ):
            raise SystemExit(f"Render frontend Blueprint must prompt for {name}; never hardcode it")


if __name__ == "__main__":
    main()
