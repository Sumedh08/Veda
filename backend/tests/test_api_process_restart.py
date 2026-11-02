"""Verify paused research survives an abrupt local API process restart."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEV_SECRET = "test-only-not-a-real-local-restart-secret"


def _runtime_environment(database_url: str) -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENALEX_API_KEY",
        "CROSSREF_MAILTO",
        "SUPABASE_URL",
        "SUPABASE_JWKS_URL",
        "SUPABASE_JWT_SECRET",
    ):
        environment.pop(name, None)
    environment.update(
        {
            "APP_ENV": "test",
            "DATABASE_URL": database_url,
            "DEV_AUTH_ENABLED": "true",
            "DEV_AUTH_SECRET": DEV_SECRET,
            "LLM_PROVIDER": "disabled",
            "OPENROUTER_API_KEY": "",
            "OPENAI_API_KEY": "",
            "OPENALEX_API_KEY": "",
            "OPENALEX_ALLOW_BILLABLE_CALLS": "false",
            "CROSSREF_MAILTO": "",
        }
    )
    return environment


def _start_server(environment: dict[str, str], log_path: Path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    log = log_path.open("w+b")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log.flush()
            log.seek(0)
            raise AssertionError(
                f"API process exited during startup ({process.returncode}): "
                f"{log.read().decode(errors='replace')}"
            )
        try:
            response = httpx.get(f"{base_url}/api/v1/health/ready", timeout=0.5, trust_env=False)
            if response.status_code == 200:
                return process, log, base_url
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    _kill_process(process)
    log.flush()
    log.seek(0)
    raise AssertionError(f"API did not become ready: {log.read().decode(errors='replace')}")


def _kill_process(process: subprocess.Popen):
    if process.poll() is None:
        process.kill()
        process.wait(timeout=10)


def _authorization(client: httpx.Client) -> dict[str, str]:
    response = client.post("/api/v1/auth/dev-session")
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_saved_research_plan_replays_and_resumes_after_api_process_kill(tmp_path):
    database_path = tmp_path / "process-restart.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _runtime_environment(database_url)
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert migration.returncode == 0, migration.stdout + migration.stderr
    assert database_path.exists()

    process = None
    first_log = second_log = None
    try:
        process, first_log, base_url = _start_server(environment, tmp_path / "api-first.log")
        with httpx.Client(base_url=base_url, timeout=5, trust_env=False) as client:
            headers = _authorization(client)
            project_response = client.post(
                "/api/v1/projects",
                headers=headers,
                json={"title": "Process restart", "domain": "Reliability"},
            )
            assert project_response.status_code == 201, project_response.text
            project_id = project_response.json()["id"]
            job_response = client.post(
                f"/api/v1/projects/{project_id}/research-jobs",
                headers=headers,
                json={
                    "question": "How does the local API recover a paused research job?",
                    "depth": "quick",
                    "budget_ceiling_usd": 0,
                    "idempotency_key": "process-restart-job-01",
                },
            )
            assert job_response.status_code == 201, job_response.text
            job_id = job_response.json()["id"]

            operation_key = "process-restart-plan-step-01"
            planned = client.post(
                f"/api/v1/research-jobs/{job_id}/advance",
                headers=headers,
                json={"operation_key": operation_key},
            )
            assert planned.status_code == 200, planned.text
            assert planned.json()["current_stage"] == "discovery"
            assert planned.json()["status"] == "active"
            saved_plan = client.get(f"/api/v1/research-jobs/{job_id}/plan", headers=headers)
            assert saved_plan.status_code == 200, saved_plan.text
            saved_events = client.get(f"/api/v1/research-jobs/{job_id}/events", headers=headers)
            assert saved_events.status_code == 200, saved_events.text
            planning_events = [
                item
                for item in saved_events.json()["items"]
                if item["stage"] == "planning" and item["event_type"] == "step_completed"
            ]
            assert len(planning_events) == 1
            paused = client.post(f"/api/v1/research-jobs/{job_id}/pause", headers=headers)
            assert paused.status_code == 200, paused.text
            assert paused.json()["status"] == "paused"

        _kill_process(process)
        process = None
        first_log.close()
        first_log = None

        process, second_log, restarted_url = _start_server(
            environment, tmp_path / "api-restarted.log"
        )
        with httpx.Client(base_url=restarted_url, timeout=5, trust_env=False) as client:
            headers = _authorization(client)
            recovered = client.get(f"/api/v1/research-jobs/{job_id}", headers=headers)
            assert recovered.status_code == 200, recovered.text
            assert recovered.json()["current_stage"] == "discovery"
            assert recovered.json()["status"] == "paused"
            assert client.get(f"/api/v1/research-jobs/{job_id}/plan", headers=headers).json() == (
                saved_plan.json()
            )

            duplicate = client.post(
                f"/api/v1/research-jobs/{job_id}/advance",
                headers=headers,
                json={"operation_key": operation_key},
            )
            assert duplicate.status_code == 200, duplicate.text
            assert duplicate.json()["current_stage"] == "discovery"
            replayed_events = client.get(
                f"/api/v1/research-jobs/{job_id}/events", headers=headers
            ).json()["items"]
            assert (
                sum(
                    item["stage"] == "planning" and item["event_type"] == "step_completed"
                    for item in replayed_events
                )
                == 1
            )

            resumed = client.post(f"/api/v1/research-jobs/{job_id}/resume", headers=headers)
            assert resumed.status_code == 200, resumed.text
            assert resumed.json()["status"] == "queued"
            assert resumed.json()["current_stage"] == "discovery"
    finally:
        if process is not None:
            _kill_process(process)
        if first_log is not None:
            first_log.close()
        if second_log is not None:
            second_log.close()
