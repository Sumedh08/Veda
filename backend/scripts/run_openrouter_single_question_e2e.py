"""Run T-112 against one free OpenRouter model in isolated local processes."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from argparse import ArgumentParser
from datetime import UTC, datetime
from pathlib import Path

T112_MODEL = "nvidia/nemotron-3.5-super-vl:free"
T112_QUESTION = "Does generative AI improve software developer productivity, and why do empirical studies sometimes report different findings?"


def load_resumable_attempt(path: Path, evaluation: Path) -> tuple[dict, Path, str]:
    """Accept only this harness's pre-dispatch queued job with no model usage."""
    attempt_path = path.resolve(strict=True)
    evaluation_root = evaluation.resolve(strict=True)
    if attempt_path.parent != evaluation_root:
        raise ValueError("Resume artifact must be inside the repository evaluation directory.")
    match = re.fullmatch(r"openrouter-t112-(\d{8}T\d{6}Z)\.json", attempt_path.name)
    if not match:
        raise ValueError("Resume artifact must be a prior timestamped T-112 run artifact.")

    artifact = json.loads(attempt_path.read_text(encoding="utf-8"))
    if not isinstance(artifact, dict):
        raise ValueError("Resume artifact must contain a JSON object.")
    job = artifact.get("job")
    usage_audit = artifact.get("usage_audit")
    errors = artifact.get("errors")
    has_local_harness_error = isinstance(errors, list) and any(
        error.get("stage") == "planning" and error.get("class") == "ReferenceError"
        for error in errors
        if isinstance(error, dict)
    )
    if (
        artifact.get("configured_model") != T112_MODEL
        or artifact.get("question") != T112_QUESTION
        or artifact.get("job_status") != "queued"
        or artifact.get("current_stage") != "planning"
        or not isinstance(job, dict)
        or artifact.get("job_id") != job.get("id")
        or job.get("question") != T112_QUESTION
        or job.get("status") != "queued"
        or job.get("current_stage") != "planning"
        or job.get("model_calls_reserved") != 0
        or artifact.get("model_calls_reserved") != 0
        or artifact.get("provider_usage") != []
        or not isinstance(usage_audit, dict)
        or usage_audit.get("accepted_response_count") != 0
        or not has_local_harness_error
    ):
        raise ValueError(
            "Resume artifact is not an untouched queued T-112 job after the local harness error."
        )

    database_path = evaluation_root / f"veda-t112-{match.group(1)}.sqlite3"
    if not database_path.is_file():
        raise ValueError("The isolated SQLite database for this queued T-112 job is unavailable.")
    return artifact, database_path, str(job["id"])


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resume-from",
        type=Path,
        help="Resume only a T-112 job proven to be queued with zero model calls.",
    )
    args = parser.parse_args(argv)
    backend_dir = Path(__file__).resolve().parents[1]
    repository_root = backend_dir.parent
    frontend = repository_root / "frontend"
    evaluation = repository_root / "evaluation"
    os.chdir(backend_dir)
    sys.path.insert(0, str(backend_dir))
    sys.path.insert(0, str(evaluation / "scripts"))

    from verify_openrouter_free_route import fetch_route_metadata

    from app.config import Settings

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    result_path = evaluation / (
        f"openrouter-t112-resume-{timestamp}.json"
        if args.resume_from
        else f"openrouter-t112-{timestamp}.json"
    )
    preflight_path = evaluation / f"openrouter-t112-preflight-{timestamp}.json"
    request_counter_path = evaluation / f"openrouter-t112-request-count-{timestamp}.txt"
    resume_artifact = None
    resume_job_id = None
    if args.resume_from:
        try:
            resume_artifact, database_path, resume_job_id = load_resumable_attempt(
                args.resume_from, evaluation
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            print(f"T-112 resume refused before inference: {type(exc).__name__}.")
            return 2
    else:
        database_path = evaluation / f"veda-t112-{timestamp}.sqlite3"
    output_paths = [result_path, preflight_path, request_counter_path]
    if not args.resume_from:
        output_paths.append(database_path)
    if any(path.exists() for path in output_paths):
        print("Refusing to replace an existing T-112 artifact.")
        return 2

    try:
        preflight = fetch_route_metadata(T112_MODEL)
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(
            f"T-112 stopped before inference: free-route preflight failed ({type(exc).__name__})."
        )
        return 2
    preflight_path.write_text(
        json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    api_key = os.environ.pop("OPENROUTER_API_KEY", "")
    if not api_key:
        api_key = Settings().openrouter_api_key
    if not api_key or len(api_key) > 256:
        print(
            "T-112 preflight passed, but the credential is unavailable to the local runner. "
            "Set OPENROUTER_API_KEY in the process environment or ignored repository-root .env; "
            "do not paste it into chat. No inference request was sent."
        )
        return 2

    os.environ.update(
        {
            "OPENROUTER_API_KEY": api_key,
            "OPENAI_API_KEY": "",
            "OPENROUTER_MODEL": T112_MODEL,
            "LLM_PROVIDER": "openrouter",
            "ALLOW_PAID_LLM_CALLS": "false",
            "MAX_JOB_COST_USD": "0",
            "MAX_DAILY_MODEL_CALLS": "6",
            "MAX_DAILY_MODEL_CALLS_PER_USER": "6",
            "VEDA_OPENROUTER_LIVE_E2E": "1",
            "VEDA_OPENROUTER_T112_E2E": "1",
            "VEDA_OPENROUTER_OUTPUT_PATH": str(result_path),
            "VEDA_OPENROUTER_PREFLIGHT_PATH": str(preflight_path),
            "VEDA_OPENROUTER_REQUEST_COUNTER_PATH": str(request_counter_path),
            "VEDA_OPENROUTER_DATABASE_PATH": str(database_path),
            "VEDA_REAL_E2E_API_PORT": "8001",
            "VEDA_BACKEND_PYTHON": sys.executable,
        }
    )
    if resume_job_id:
        os.environ["VEDA_OPENROUTER_RESUME_JOB_ID"] = resume_job_id
        os.environ["VEDA_OPENROUTER_RESUME_FROM"] = str(args.resume_from.resolve())
    else:
        os.environ.pop("VEDA_OPENROUTER_RESUME_JOB_ID", None)
        os.environ.pop("VEDA_OPENROUTER_RESUME_FROM", None)
    del api_key

    print(
        json.dumps(
            {
                "test": "T-112 one-question OpenRouter research",
                "question": "Does generative AI improve software developer productivity, and why do empirical studies sometimes report different findings?",
                "model": T112_MODEL,
                "preflight_artifact": str(preflight_path),
                "result_artifact": str(result_path),
                "request_counter_path": str(request_counter_path),
                "sqlite_path": str(database_path),
                "hard_provider_request_cap": 6,
                "automatic_model_retries": 0,
                "reported_price": "prompt/completion zero in current public route metadata; actual request cost remains unconfirmed until responses report it",
                "resumed_existing_queued_job": bool(resume_job_id),
                "resumed_from_artifact": str(args.resume_from) if args.resume_from else None,
                "resumed_job_id": resume_job_id,
            },
            ensure_ascii=False,
        )
    )
    try:
        completed = subprocess.run(
            [
                os.environ.get("ComSpec", "cmd.exe"),
                "/d",
                "/c",
                "npm exec -- playwright test e2e/openrouter-single-question.e2e.ts --workers=1 --retries=0 --reporter=line",
            ],
            cwd=frontend,
            stdin=subprocess.DEVNULL,
            check=False,
        )
        return completed.returncode
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)


if __name__ == "__main__":
    raise SystemExit(main())
