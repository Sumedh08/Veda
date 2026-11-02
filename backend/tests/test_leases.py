from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Project, ResearchJob
from app.research.leases import acquire_job_lease


def test_only_one_concurrent_writer_acquires_a_job_lease(tmp_path):
    engine = create_engine(
        URL.create("sqlite", database=str(tmp_path / "lease-race.sqlite")),
        connect_args={"timeout": 10},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        project = Project(owner_id="owner-a", title="Lease test", domain="testing")
        db.add(project)
        db.flush()
        job = ResearchJob(
            project_id=project.id,
            question="Test concurrent lease acquisition safely",
            idempotency_key="lease-test-key-01",
        )
        db.add(job)
        db.commit()
        job_id = job.id

    barrier = Barrier(2)
    tokens = ["lease-writer-one", "lease-writer-two"]
    now = datetime.now(UTC)

    def attempt(token: str) -> bool:
        with sessions() as db:
            observed_version = db.scalar(
                select(ResearchJob.version).where(ResearchJob.id == job_id)
            )
            db.commit()
            barrier.wait(timeout=5)
            won = acquire_job_lease(
                db,
                job_id=job_id,
                expected_version=observed_version,
                lease_token=token,
                now=now,
            )
            db.commit()
            return won

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, tokens))

    assert sorted(results) == [False, True]
    with sessions() as db:
        job = db.get(ResearchJob, job_id)
        assert job is not None
        assert job.version == 1
        assert job.lease_owner in tokens
        assert job.lease_expires_at is not None
    engine.dispose()


def test_expired_lease_can_be_reclaimed_and_fences_the_old_token(tmp_path):
    database_url = URL.create("sqlite", database=str(tmp_path / "lease-expiry.sqlite"))
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        project = Project(owner_id="owner-a", title="Lease recovery", domain="testing")
        db.add(project)
        db.flush()
        job = ResearchJob(
            project_id=project.id,
            question="Test expired lease reclaim and fencing",
            idempotency_key="lease-recovery-key-01",
        )
        db.add(job)
        db.commit()
        job_id = job.id

    now = datetime.now(UTC)
    with sessions() as db:
        assert acquire_job_lease(
            db,
            job_id=job_id,
            expected_version=0,
            lease_token="old-worker-token",
            now=now - timedelta(seconds=300),
            lease_seconds=180,
        )
        db.commit()

    # Close the original pool and reconnect to the persisted file as after a process restart.
    engine.dispose()
    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        assert acquire_job_lease(
            db,
            job_id=job_id,
            expected_version=1,
            lease_token="recovery-worker-token",
            now=now,
            lease_seconds=180,
        )
        db.commit()

    with sessions() as db:
        job = db.get(ResearchJob, job_id)
        assert job is not None
        assert job.version == 2
        assert job.lease_owner == "recovery-worker-token"
        assert not acquire_job_lease(
            db,
            job_id=job_id,
            expected_version=1,
            lease_token="old-worker-token",
            now=now,
        )
    engine.dispose()
