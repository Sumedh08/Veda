"""Opt-in PostgreSQL checks; tests refuse non-loopback/non-test databases."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.models import DailyModelQuota, Project, ResearchJob
from app.research.leases import acquire_job_lease
from app.research.quotas import ModelCallQuotaExceeded, reserve_daily_model_call

pytestmark = pytest.mark.skipif(
    not os.environ.get("VEDA_TEST_POSTGRES_URL"),
    reason="Set VEDA_TEST_POSTGRES_URL to a disposable loopback *_test database.",
)


@pytest.fixture
def postgres_url():
    value = os.environ["VEDA_TEST_POSTGRES_URL"]
    url = make_url(value)
    if url.get_backend_name() != "postgresql":
        pytest.fail("PostgreSQL integration tests require a PostgreSQL URL.")
    if url.host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("Refusing PostgreSQL integration tests against a non-loopback host.")
    if not (url.database or "").endswith("_test"):
        pytest.fail("Refusing PostgreSQL integration tests unless the database ends with _test.")
    return value


def _new_job(db, *, owner_id: str, title: str, key: str) -> tuple[str, str]:
    project = Project(owner_id=owner_id, title=title, domain="integration-test")
    db.add(project)
    db.flush()
    job = ResearchJob(
        project_id=project.id,
        question="Verify PostgreSQL transaction and restart behavior",
        idempotency_key=key,
    )
    db.add(job)
    db.flush()
    return project.id, job.id


def test_postgres_lease_concurrency_restart_recovery_and_foreign_key_cascade(postgres_url):
    engine = create_engine(postgres_url, pool_pre_ping=True)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    suffix = uuid4().hex
    project_id = None
    job_id = None
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
            tables = set(inspect(connection).get_table_names())
            assert {"projects", "research_jobs", "alembic_version"} <= tables
        with sessions() as db:
            project_id, job_id = _new_job(
                db,
                owner_id=f"postgres-test-{suffix}",
                title="Postgres lease test",
                key=f"pg-lease-{suffix}",
            )
            db.commit()

        barrier = Barrier(2)
        now = datetime.now(UTC)

        def try_acquire(token: str) -> bool:
            with sessions() as db:
                version = db.scalar(select(ResearchJob.version).where(ResearchJob.id == job_id))
                db.commit()
                barrier.wait(timeout=10)
                won = acquire_job_lease(
                    db,
                    job_id=job_id,
                    expected_version=version,
                    lease_token=token,
                    now=now,
                )
                db.commit()
                return won

        tokens = (f"worker-a-{suffix}", f"worker-b-{suffix}")
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(try_acquire, tokens))
        assert sorted(outcomes) == [False, True]

        engine.dispose()  # Simulate the service process and its connection pool restarting.
        restarted_engine = create_engine(postgres_url, pool_pre_ping=True)
        restarted_sessions = sessionmaker(bind=restarted_engine, expire_on_commit=False)
        try:
            expired_at = now - timedelta(minutes=5)
            with restarted_sessions() as db:
                assert acquire_job_lease(
                    db,
                    job_id=job_id,
                    expected_version=1,
                    lease_token=f"expired-worker-{suffix}",
                    now=expired_at,
                    lease_seconds=60,
                )
                db.commit()
            with restarted_sessions() as db:
                assert acquire_job_lease(
                    db,
                    job_id=job_id,
                    expected_version=2,
                    lease_token=f"recovery-worker-{suffix}",
                    now=now,
                    lease_seconds=60,
                )
                db.commit()
            with restarted_sessions() as db:
                recovered = db.get(ResearchJob, job_id)
                assert recovered is not None
                assert recovered.version == 3
                assert recovered.lease_owner == f"recovery-worker-{suffix}"
                assert not acquire_job_lease(
                    db,
                    job_id=job_id,
                    expected_version=2,
                    lease_token=f"expired-worker-{suffix}",
                    now=now,
                )
        finally:
            restarted_engine.dispose()
    finally:
        cleanup_engine = create_engine(postgres_url, pool_pre_ping=True)
        try:
            if project_id:
                with cleanup_engine.begin() as connection:
                    connection.execute(
                        text("DELETE FROM projects WHERE id = :project_id"),
                        {"project_id": project_id},
                    )
                    assert (
                        connection.execute(
                            select(func.count())
                            .select_from(ResearchJob)
                            .where(ResearchJob.id == job_id)
                        ).scalar_one()
                        == 0
                    )
        finally:
            cleanup_engine.dispose()


def test_postgres_global_quota_reservation_is_atomic(postgres_url):
    engine = create_engine(postgres_url, pool_pre_ping=True)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    suffix = uuid4().hex
    quota_day = datetime(2090 + uuid4().int % 20, 1, 1, tzinfo=UTC)
    project_ids: list[str] = []
    try:
        job_ids = []
        with sessions() as db:
            for index in range(2):
                project_id, job_id = _new_job(
                    db,
                    owner_id=f"postgres-quota-{suffix}-{index}",
                    title=f"Postgres quota test {index}",
                    key=f"pg-quota-{suffix}-{index}",
                )
                project_ids.append(project_id)
                job_ids.append(job_id)
            db.commit()

        barrier = Barrier(2)

        def attempt(job_id: str) -> str:
            with sessions() as db:
                barrier.wait(timeout=10)
                try:
                    reserve_daily_model_call(
                        db,
                        job_id=job_id,
                        operation="postgres-integration",
                        attempt=0,
                        provider="test",
                        model_name="no-provider-call",
                        global_limit=1,
                        per_user_limit=10,
                        now=quota_day,
                    )
                    return "reserved"
                except ModelCallQuotaExceeded as exc:
                    return exc.scope

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, job_ids))
        assert outcomes.count("reserved") == 1
        assert outcomes.count("global") == 1
        with sessions() as db:
            assert (
                db.scalar(
                    select(DailyModelQuota.calls_used).where(
                        DailyModelQuota.scope == "global",
                        DailyModelQuota.scope_id == "all-users",
                        DailyModelQuota.quota_date == quota_day.date(),
                    )
                )
                == 1
            )
    finally:
        with engine.begin() as connection:
            if project_ids:
                connection.execute(delete(Project).where(Project.id.in_(project_ids)))
            connection.execute(
                delete(DailyModelQuota).where(DailyModelQuota.quota_date == quota_day.date())
            )
        engine.dispose()
