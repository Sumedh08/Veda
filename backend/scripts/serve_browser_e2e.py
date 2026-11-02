"""Run a model-disabled SQLite API for real-browser integration checks.

The helper seeds one synthetic inspection record; an explicitly enabled scholarly
smoke may add public provider records. Databases are temporary by default. The
full-text smoke can opt into a new, non-overwriting artifact under evaluation/.
An explicit inspection mode can serve an existing evaluation database without
migrating it or inserting the synthetic fixture. API rate-limit bookkeeping can
still write to that database, so use a copy when inspecting a historical run.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def persistent_database_path(configured_path: str | None, *, repository_root: Path) -> Path | None:
    """Validate an explicit, new SQLite artifact path; never overwrite prior evidence."""
    if not configured_path:
        return None
    requested = Path(configured_path).expanduser().resolve()
    evaluation_dir = (repository_root / "evaluation").resolve()
    if requested.suffix.casefold() != ".sqlite3":
        raise ValueError("persistent E2E database must use the .sqlite3 extension")
    try:
        requested.relative_to(evaluation_dir)
    except ValueError:
        raise ValueError("persistent E2E database must be inside repository evaluation/") from None
    if requested.exists():
        raise FileExistsError("persistent E2E database already exists; refusing to overwrite it")
    return requested


def existing_database_path(configured_path: str | None, *, repository_root: Path) -> Path | None:
    """Validate an existing evaluation artifact for no-migration inspection."""
    if not configured_path:
        return None
    requested = Path(configured_path).expanduser().resolve()
    evaluation_dir = (repository_root / "evaluation").resolve()
    if requested.suffix.casefold() != ".sqlite3":
        raise ValueError("existing E2E database must use the .sqlite3 extension")
    try:
        requested.relative_to(evaluation_dir)
    except ValueError:
        raise ValueError("existing E2E database must be inside repository evaluation/") from None
    if not requested.is_file():
        raise FileNotFoundError("existing E2E database does not exist")
    return requested


def configure_isolated_environment(database_url: str) -> None:
    os.environ.update(
        {
            "APP_ENV": "test",
            "DATABASE_URL": database_url,
            "FRONTEND_ORIGINS": "http://127.0.0.1:5176",
            "DEV_AUTH_ENABLED": "true",
            "DEV_AUTH_SECRET": secrets.token_urlsafe(48),
            "RATE_LIMIT_HASH_SECRET": secrets.token_urlsafe(48),
            # These routes are exercised through the full UI, which issues
            # many small API reads. Keep limits enabled but high enough that
            # a disposable multi-journey suite does not exhaust its own quota.
            # Production-rate-limit behavior is covered separately by API tests.
            "RATE_LIMIT_USER_PER_MINUTE": "10000",
            "RATE_LIMIT_IP_PER_MINUTE": "20000",
            "RATE_LIMIT_USER_JOB_CREATES_PER_HOUR": "100",
            "RATE_LIMIT_IP_JOB_CREATES_PER_HOUR": "200",
            "RATE_LIMIT_USER_ADVANCES_PER_MINUTE": "1000",
            "RATE_LIMIT_IP_ADVANCES_PER_MINUTE": "2000",
            "LLM_PROVIDER": "disabled",
            "ALLOW_PAID_LLM_CALLS": "false",
            "OPENAI_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "SARVAM_API_KEY": "",
            "GEMINI_API_KEY": "",
            "OPENALEX_API_KEY": "",
            "CRAWL4AI_ENABLED": "true"
            if os.environ.get("VEDA_CRAWL4AI_LIVE_E2E") == "1"
            else "false",
            "OPENALEX_ALLOW_BILLABLE_CALLS": "false",
            "SUPABASE_URL": "",
            "SUPABASE_JWKS_URL": "",
            "SUPABASE_JWT_SECRET": "",
        }
    )


def seed_inspection_record() -> None:
    from app.db import SessionLocal
    from app.models import (
        Passage,
        Project,
        ResearchJob,
        ResearchReport,
        RetrievedDocument,
        Source,
    )
    from app.schemas import versioned_report_citation_map, versioned_report_verification
    from app.security import LOCAL_USER_ID

    now = datetime.now(UTC)
    project_id = "10000000-0000-4000-8000-000000000701"
    job_id = "10000000-0000-4000-8000-000000000702"
    source_id = "10000000-0000-4000-8000-000000000703"
    document_id = "10000000-0000-4000-8000-000000000704"
    passage_id = "10000000-0000-4000-8000-000000000705"
    report_id = "10000000-0000-4000-8000-000000000706"
    source_title = "Synthetic Browser Integration Source — TEST DATA"
    passage_text = (
        "Synthetic integration text for checking the real API-to-browser citation inspector. "
        "This is not a paper excerpt or a research finding."
    )

    project = Project(
        id=project_id,
        owner_id=LOCAL_USER_ID,
        title="Local browser integration (synthetic data)",
        description="Disposable API/browser test records only; not research evidence.",
        domain="Software integration testing",
        created_at=now,
        updated_at=now,
    )
    job = ResearchJob(
        id=job_id,
        project_id=project_id,
        question="Synthetic browser/API citation-inspection test — not a research question",
        scope_json={"schema_version": 1, "extensions": {}},
        depth="quick",
        status="completed_with_limitations",
        current_stage="complete",
        checkpoint_json={},
        idempotency_key="local-browser-integration-synthetic-fixture",
        attempt=1,
        version=8,
        created_at=now,
        updated_at=now,
    )
    source = Source(
        id=source_id,
        job_id=job_id,
        external_id="local-fixture:synthetic-source",
        title=source_title,
        url="https://example.invalid/veda-browser-integration-fixture",
        authors_json=[],
        publisher="Local test fixture",
        source_type="scholarly_article",
        retrieval_status="abstract_only",
        abstract_excerpt=passage_text,
        appraisal_json={},
        metadata_json={"provider": "local_fixture"},
        created_at=now,
    )
    document = RetrievedDocument(
        id=document_id,
        source_id=source_id,
        identity_key=hashlib.sha256(b"veda-browser-integration-document").hexdigest(),
        source_version="synthetic-fixture-v1",
        document_sha256=hashlib.sha256(passage_text.encode("utf-8")).hexdigest(),
        retrieved_at=now,
        locator="synthetic test record",
        media_type="text/plain",
        access_class="abstract_excerpt",
        hash_scope="fixture_text_only",
    )
    passage = Passage(
        id=passage_id,
        source_id=source_id,
        document_id=document_id,
        identity_key=hashlib.sha256(passage_text.encode("utf-8")).hexdigest(),
        identity_version=1,
        ordinal=0,
        locator="synthetic fixture excerpt",
        content=passage_text,
        content_hash=hashlib.sha256(passage_text.encode("utf-8")).hexdigest(),
        access_level="abstract_excerpt",
        truncated=False,
        created_at=now,
    )
    citation_map = versioned_report_citation_map(
        {
            "schema_version": 1,
            "citations": {
                "S1": {
                    "source_id": source_id,
                    "title": source_title,
                    "doi": None,
                    "url": source.url,
                    "passages": [passage_id],
                }
            },
            "extensions": {},
        },
        strict=True,
    )
    verification = versioned_report_verification(
        {
            "report_schema_version": 2,
            "level": "deterministic_link_integrity_only",
            "status": "needs_review",
            "claims_checked": 0,
            "claims_with_valid_source_and_passage": 0,
        },
        strict=True,
    )
    report = ResearchReport(
        id=report_id,
        job_id=job_id,
        status="completed_with_limitations",
        body_markdown=(
            "# Synthetic Browser Integration Fixture\n\n"
            "This is synthetic test data used only to verify citation inspection [S1].\n\n"
            "## Limitations\n\n"
            "It contains no research finding. Citation checks are marked needs review."
        ),
        citation_map_json=citation_map,
        verification_json=verification,
        model_name=None,
        created_at=now,
    )

    with SessionLocal() as session:
        session.add_all([project, job, source, document, passage, report])
        session.commit()


def _run_isolated_server(
    backend_dir: Path, database_path: Path, *, initialize_database: bool = True
) -> None:
    configure_isolated_environment(f"sqlite:///{database_path.as_posix()}")
    if initialize_database:
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


def main() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    repository_root = backend_dir.parent
    reuse_path = existing_database_path(
        os.environ.get("VEDA_REAL_E2E_REUSE_DATABASE_PATH"),
        repository_root=repository_root,
    )
    persistent_path = persistent_database_path(
        os.environ.get("VEDA_REAL_E2E_DATABASE_PATH"),
        repository_root=repository_root,
    )
    if reuse_path is not None and persistent_path is not None:
        raise ValueError("choose either a new E2E database or existing-database inspection")
    if reuse_path is not None:
        _run_isolated_server(backend_dir, reuse_path, initialize_database=False)
        return
    if persistent_path is not None:
        persistent_path.parent.mkdir(parents=True, exist_ok=True)
        with persistent_path.open("xb"):
            pass
        _run_isolated_server(backend_dir, persistent_path)
        return

    with tempfile.TemporaryDirectory(prefix="veda-real-browser-") as temp_dir:
        database_path = Path(temp_dir) / "browser-integration.sqlite"
        _run_isolated_server(backend_dir, database_path)


if __name__ == "__main__":
    main()
