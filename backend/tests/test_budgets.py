import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db import Base
from app.models import (
    DailyModelQuota,
    ModelCallReservation,
    Project,
    ProviderCooldown,
    ResearchJob,
    UsageEntry,
)
from app.providers import llm as llm_module
from app.providers.llm import LLMProviderError, ProviderUsage, StructuredResult
from app.research import workflow
from app.research.llm_tasks import ResearchAppraisalBatch
from app.research.quotas import (
    ModelCallQuotaExceeded,
    daily_model_call_blocker,
    daily_model_quota_snapshot,
    reserve_daily_model_call,
    settle_model_call_reservation,
)


def _add_job(db, owner_id: str, suffix: str, *, budget_ceiling_usd: float = 0.0) -> str:
    project = Project(owner_id=owner_id, title=f"Quota {suffix}", domain="testing")
    db.add(project)
    db.flush()
    job = ResearchJob(
        project_id=project.id,
        question=f"Test model call quota isolation for {suffix}",
        idempotency_key=f"quota-key-{suffix}",
        budget_ceiling_usd=budget_ceiling_usd,
    )
    db.add(job)
    db.flush()
    return job.id


def _reserve(
    db,
    job_id: str,
    *,
    global_limit: int,
    user_limit: int,
    attempt: int = 0,
    request_hash: str | None = None,
    reserved_cost_usd: float = 0.0,
):
    return reserve_daily_model_call(
        db,
        job_id=job_id,
        operation="test_structured_operation",
        attempt=attempt,
        provider="test-provider",
        model_name="test-model",
        request_hash=request_hash,
        reserved_cost_usd=reserved_cost_usd,
        global_limit=global_limit,
        per_user_limit=user_limit,
    )


def _process_reservation_worker(database_url: str, job_id: str, barrier, result_queue):
    engine = create_engine(database_url, connect_args={"timeout": 10})
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with sessions() as db:
            barrier.wait(timeout=10)
            _reserve(db, job_id, global_limit=1, user_limit=10)
        result_queue.put("reserved")
    except ModelCallQuotaExceeded as exc:
        result_queue.put(exc.scope)
    finally:
        engine.dispose()


def test_daily_quota_enforces_per_user_and_global_caps_independently(tmp_path):
    engine = create_engine(URL.create("sqlite", database=str(tmp_path / "quota-caps.sqlite")))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        user_a_job_1 = _add_job(db, "user-a", "a1")
        user_a_job_2 = _add_job(db, "user-a", "a2")
        user_b_job_1 = _add_job(db, "user-b", "b1")
        user_c_job_1 = _add_job(db, "user-c", "c1")
        db.commit()

    now = datetime.now(UTC)
    with sessions() as db:
        first = reserve_daily_model_call(
            db,
            job_id=user_a_job_1,
            operation="appraisal",
            attempt=0,
            provider="test",
            model_name="test",
            global_limit=2,
            per_user_limit=1,
            now=now,
        )
        assert first.state == "reserved"
        quota_snapshot = daily_model_quota_snapshot(
            db,
            job_id=user_a_job_1,
            global_limit=2,
            per_user_limit=1,
            now=now,
        )
        assert quota_snapshot == {
            "utc_date": now.date().isoformat(),
            "global_limit": 2,
            "global_used": 1,
            "global_remaining": 1,
            "per_user_limit": 1,
            "per_user_used": 1,
            "per_user_remaining": 0,
            "available_calls": 0,
        }

    with sessions() as db:
        with pytest.raises(ModelCallQuotaExceeded) as user_cap:
            reserve_daily_model_call(
                db,
                job_id=user_a_job_2,
                operation="synthesis",
                attempt=0,
                provider="test",
                model_name="test",
                global_limit=10,
                per_user_limit=1,
                now=now,
            )
        assert user_cap.value.scope == "user"

    with sessions() as db:
        reserve_daily_model_call(
            db,
            job_id=user_b_job_1,
            operation="appraisal",
            attempt=0,
            provider="test",
            model_name="test",
            global_limit=2,
            per_user_limit=1,
            now=now,
        )

    with sessions() as db:
        with pytest.raises(ModelCallQuotaExceeded) as global_cap:
            reserve_daily_model_call(
                db,
                job_id=user_c_job_1,
                operation="appraisal",
                attempt=0,
                provider="test",
                model_name="test",
                global_limit=2,
                per_user_limit=1,
                now=now,
            )
        assert global_cap.value.scope == "global"
        assert (
            daily_model_call_blocker(
                db,
                job_id=user_c_job_1,
                global_limit=2,
                per_user_limit=1,
                now=now,
            )
            == "Veda's global daily model-call limit has been reached"
        )
    engine.dispose()


def test_inr_reservations_are_atomic_and_settle_within_job_ceiling(tmp_path):
    engine = create_engine(URL.create("sqlite", database=str(tmp_path / "quota-inr.sqlite")))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        job_id = _add_job(db, "user-inr", "inr-budget")
        db.get(ResearchJob, job_id).budget_ceiling_inr = 0.01
        db.commit()

        first = reserve_daily_model_call(
            db,
            job_id=job_id,
            operation="appraisal",
            attempt=0,
            provider="sarvam",
            model_name="sarvam-105b",
            reserved_cost_inr=0.008,
            max_job_cost_inr=0.01,
            global_limit=10,
            per_user_limit=10,
        )
        with pytest.raises(ModelCallQuotaExceeded) as blocked:
            reserve_daily_model_call(
                db,
                job_id=job_id,
                operation="synthesis",
                attempt=0,
                provider="sarvam",
                model_name="sarvam-105b",
                reserved_cost_inr=0.003,
                max_job_cost_inr=0.01,
                global_limit=10,
                per_user_limit=10,
            )
        assert blocked.value.scope == "job_budget"
        job = db.get(ResearchJob, job_id)
        assert job.cost_reserved_inr == pytest.approx(0.008)

        settle_model_call_reservation(
            db,
            reservation_id=first.id,
            state="succeeded",
            actual_cost_inr=0.006,
        )
        db.refresh(job)
        assert job.cost_spent_estimate_inr == pytest.approx(0.006)
        assert job.cost_reserved_inr == pytest.approx(0)
    engine.dispose()


def test_account_cooldown_blocks_later_structured_operation_without_a_second_post(
    client, monkeypatch
):
    project = client.post(
        "/api/v1/projects", json={"title": "Cooldown", "domain": "testing"}
    ).json()
    created = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Does a persisted account cooldown prevent duplicate provider traffic?",
            "idempotency_key": "account-cooldown-job-01",
            "model_provider": "openrouter",
            "model_name": "openrouter/free",
            "budget_ceiling_usd": 0,
        },
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]
    provider_settings = Settings(
        llm_provider="openrouter",
        openrouter_api_key="fixture-only",
        openrouter_model="openrouter/free",
        max_daily_model_calls=10,
        max_daily_model_calls_per_user=10,
    )
    monkeypatch.setattr(workflow, "settings", provider_settings)
    monkeypatch.setattr(llm_module, "settings", provider_settings)
    calls = 0

    class RateLimitedProvider:
        def complete_json(self, **kwargs):
            nonlocal calls
            calls += 1
            raise LLMProviderError(
                "sanitized 429 fixture",
                code="provider_rate_limited",
                retry_after_seconds=120,
                cooldown_scope="account",
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow, "configured_provider", RateLimitedProvider)
    request = {
        "system": "Return only the strict fixture schema.",
        "user": "A bounded fixture operation.",
        "max_output_tokens": 20,
    }
    with client.db_sessions() as db:
        with pytest.raises(workflow.WorkflowError) as first_error:
            workflow._call_structured(
                db,
                {
                    "id": job_id,
                    "attempt": 0,
                    "model_provider": "openrouter",
                    "model_name": "openrouter/free",
                },
                schema_name="veda_cooldown_first_operation",
                schema_model=ResearchAppraisalBatch,
                **request,
            )
        assert first_error.value.code == "provider_rate_limited"
        with pytest.raises(workflow.WorkflowError) as blocked_error:
            workflow._call_structured(
                db,
                {
                    "id": job_id,
                    "attempt": 0,
                    "model_provider": "openrouter",
                    "model_name": "openrouter/free",
                },
                schema_name="veda_cooldown_next_operation",
                schema_model=ResearchAppraisalBatch,
                **request,
            )
        assert blocked_error.value.code == "provider_cooldown_active"
        assert calls == 1
        assert db.scalar(select(func.count(ModelCallReservation.id))) == 1
        assert db.get(ProviderCooldown, "openrouter") is not None


def test_failed_provider_attempt_consumes_reserved_daily_quota(tmp_path):
    engine = create_engine(URL.create("sqlite", database=str(tmp_path / "quota-failure.sqlite")))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        job_id = _add_job(db, "user-failed", "failed")
        db.commit()
        reservation = _reserve(db, job_id, global_limit=1, user_limit=1)
        settle_model_call_reservation(
            db,
            reservation_id=reservation.id,
            state="failed",
            error_class="provider_timeout",
        )
        db.commit()
        stored = db.get(ModelCallReservation, reservation.id)
        assert stored is not None
        assert stored.state == "failed"
        assert stored.error_class == "provider_timeout"
        assert (
            db.scalar(select(DailyModelQuota.calls_used).where(DailyModelQuota.scope == "global"))
            == 1
        )

    with sessions() as db:
        with pytest.raises(ModelCallQuotaExceeded) as error:
            _reserve(db, job_id, global_limit=1, user_limit=1, attempt=1)
        assert error.value.scope == "global"
    engine.dispose()


def test_daily_quota_reservation_is_atomic_across_concurrent_sessions(tmp_path):
    engine_url = URL.create("sqlite", database=str(tmp_path / "quota-race.sqlite"))
    engine = create_engine(engine_url, connect_args={"timeout": 10})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        first_job = _add_job(db, "user-one", "race-1")
        second_job = _add_job(db, "user-two", "race-2")
        db.commit()
    barrier = Barrier(2)
    jobs = [first_job, second_job]

    def attempt(job_id: str) -> str:
        with sessions() as db:
            barrier.wait(timeout=5)
            try:
                _reserve(db, job_id, global_limit=1, user_limit=10)
                return "reserved"
            except ModelCallQuotaExceeded as exc:
                return exc.scope

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, jobs))

    assert results.count("reserved") == 1
    assert results.count("global") == 1
    with sessions() as db:
        assert db.scalar(select(func.sum(DailyModelQuota.calls_used))) == 2
        assert db.scalar(select(func.count(ModelCallReservation.id))) == 1
    engine.dispose()


def test_daily_quota_reservation_is_atomic_across_processes(tmp_path):
    db_path = tmp_path / "quota-process-race.sqlite"
    database_url = str(URL.create("sqlite", database=str(db_path)))
    engine = create_engine(database_url, connect_args={"timeout": 10})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        job_ids = [_add_job(db, f"process-user-{n}", f"process-{n}") for n in range(2)]
        db.commit()
    engine.dispose()

    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_process_reservation_worker,
            args=(database_url, job_id, barrier, result_queue),
        )
        for job_id in job_ids
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
    assert all(process.exitcode == 0 for process in processes)
    outcomes = [result_queue.get(timeout=5) for _ in processes]
    assert outcomes.count("reserved") == 1
    assert outcomes.count("global") == 1

    engine = create_engine(database_url)
    with sessionmaker(bind=engine)() as db:
        assert db.scalar(select(func.sum(DailyModelQuota.calls_used))) == 2
        assert db.scalar(select(func.count(ModelCallReservation.id))) == 1
    engine.dispose()


def test_workflow_records_provider_failure_against_reserved_call(client, monkeypatch):
    project_response = client.post(
        "/api/v1/projects", json={"title": "Quota failure", "domain": "testing"}
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]
    job_response = client.post(
        f"/api/v1/projects/{project_id}/research-jobs",
        json={
            "question": "Record failed provider quota use without an API request",
            "idempotency_key": "quota-provider-failure-01",
            "budget_ceiling_usd": 0,
        },
    )
    assert job_response.status_code == 201
    job_id = job_response.json()["id"]

    class FailingProvider:
        def complete_json(self, **kwargs):
            raise LLMProviderError("simulated provider failure", code="provider_timeout")

        def close(self):
            pass

    monkeypatch.setattr(
        workflow,
        "settings",
        Settings(
            llm_provider="openrouter",
            openrouter_api_key="fixture-only",
            openrouter_model="openrouter/free",
            max_daily_model_calls=1,
            max_daily_model_calls_per_user=1,
        ),
    )
    monkeypatch.setattr(workflow, "configured_provider", FailingProvider)
    with client.db_sessions() as db:
        with pytest.raises(workflow.WorkflowError, match="simulated provider failure"):
            workflow._call_structured(
                db,
                {"id": job_id, "attempt": 0, "budget_ceiling_usd": 0},
                schema_name="veda_fixture_quota_failure",
                schema_model=ResearchAppraisalBatch,
                system="Return only a schema-valid fixture response.",
                user="A bounded fixture request.",
                max_output_tokens=20,
            )

    with client.db_sessions() as db:
        reservation = db.scalar(
            select(ModelCallReservation).where(ModelCallReservation.job_id == job_id)
        )
        usage = db.scalar(select(UsageEntry).where(UsageEntry.job_id == job_id))
        assert reservation is not None
        assert reservation.state == "failed"
        assert usage is not None
        assert usage.succeeded is False
        assert usage.quota_reservation_id == reservation.id
        assert usage.error_class == "provider_timeout"
        assert (
            daily_model_call_blocker(
                db,
                job_id=job_id,
                global_limit=1,
                per_user_limit=1,
            )
            == "Veda's global daily model-call limit has been reached"
        )


def test_uncertain_provider_failure_keeps_reported_and_estimated_cost_unknown(client, monkeypatch):
    project = client.post(
        "/api/v1/projects", json={"title": "Uncertain cost", "domain": "test"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Does an uncertain provider outcome remain financially unknown?",
            "idempotency_key": "uncertain-cost-remains-unknown",
            "budget_ceiling_usd": 0,
        },
    ).json()
    openrouter_settings = Settings(
        llm_provider="openrouter",
        openrouter_api_key="fixture-only",
        openrouter_model="openrouter/free",
        max_daily_model_calls=10,
        max_daily_model_calls_per_user=10,
    )
    monkeypatch.setattr(workflow, "settings", openrouter_settings)
    monkeypatch.setattr(llm_module, "settings", openrouter_settings)
    calls = 0

    class TimedOutProvider:
        def complete_json(self, **kwargs):
            nonlocal calls
            calls += 1
            raise LLMProviderError(
                "sanitized timeout fixture",
                code="provider_timeout",
                outcome_uncertain=True,
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow, "configured_provider", TimedOutProvider)
    with client.db_sessions() as db:
        with pytest.raises(workflow.WorkflowError) as error:
            workflow._call_structured(
                db,
                {"id": job["id"], "attempt": 0, "budget_ceiling_usd": 0},
                schema_name="veda_fixture_uncertain_cost",
                schema_model=ResearchAppraisalBatch,
                system="Return a structured fixture.",
                user="Exercise unknown-cost persistence.",
                max_output_tokens=20,
            )
        assert error.value.code == "model_call_uncertain"

    with client.db_sessions() as db:
        reservation = db.scalar(
            select(ModelCallReservation).where(ModelCallReservation.job_id == job["id"])
        )
        usage = db.scalar(select(UsageEntry).where(UsageEntry.job_id == job["id"]))
        assert reservation.state == "uncertain"
        assert usage.succeeded is False
        assert usage.error_class == "provider_timeout"
        assert usage.reported_cost_usd is None
        assert usage.estimated_cost_usd is None
    assert calls == 1


def test_unexpected_provider_outcome_stays_reserved_and_counts_quota(client, monkeypatch):
    project = client.post("/api/v1/projects", json={"title": "Uncertain quota", "domain": "test"})
    project_id = project.json()["id"]
    job = client.post(
        f"/api/v1/projects/{project_id}/research-jobs",
        json={
            "question": "Keep uncertain provider outcomes counted",
            "idempotency_key": "uncertain-call",
        },
    )
    job_id = job.json()["id"]

    class OutcomeUnknownProvider:
        def complete_json(self, **kwargs):
            raise RuntimeError("connection dropped after dispatch")

        def close(self):
            pass

    monkeypatch.setattr(
        workflow,
        "settings",
        Settings(
            llm_provider="openrouter",
            openrouter_api_key="fixture-only",
            openrouter_model="openrouter/free",
            max_daily_model_calls=1,
            max_daily_model_calls_per_user=1,
        ),
    )
    monkeypatch.setattr(workflow, "configured_provider", OutcomeUnknownProvider)
    with client.db_sessions() as db:
        with pytest.raises(RuntimeError, match="connection dropped after dispatch"):
            workflow._call_structured(
                db,
                {"id": job_id, "attempt": 0, "budget_ceiling_usd": 0},
                schema_name="veda_fixture_unknown_outcome",
                schema_model=ResearchAppraisalBatch,
                system="Fixture system.",
                user="Fixture user.",
                max_output_tokens=20,
            )

    with client.db_sessions() as db:
        reservation = db.scalar(
            select(ModelCallReservation).where(ModelCallReservation.job_id == job_id)
        )
        assert reservation is not None
        assert reservation.state == "uncertain"
        assert (
            daily_model_call_blocker(
                db,
                job_id=job_id,
                global_limit=1,
                per_user_limit=1,
            )
            == "Veda's global daily model-call limit has been reached"
        )


def test_atomic_job_budget_reservation_and_settlement(tmp_path):
    engine = create_engine(URL.create("sqlite", database=str(tmp_path / "job-budget.sqlite")))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        job_id = _add_job(db, "budget-user", "budget", budget_ceiling_usd=0.05)
        db.commit()
        reservation = _reserve(
            db,
            job_id,
            global_limit=10,
            user_limit=10,
            request_hash="a" * 64,
            reserved_cost_usd=0.04,
        )
        job = db.get(ResearchJob, job_id)
        assert job.cost_reserved_usd == pytest.approx(0.04)
        with pytest.raises(ModelCallQuotaExceeded) as error:
            _reserve(
                db,
                job_id,
                global_limit=10,
                user_limit=10,
                attempt=1,
                request_hash="b" * 64,
                reserved_cost_usd=0.02,
            )
        assert error.value.scope == "job_budget"

        settle_model_call_reservation(
            db,
            reservation_id=reservation.id,
            state="succeeded",
            actual_cost_usd=0.015,
        )
        db.commit()
        job = db.get(ResearchJob, job_id)
        assert job.cost_reserved_usd == pytest.approx(0)
        assert job.cost_spent_estimate_usd == pytest.approx(0.015)
        with pytest.raises(ModelCallQuotaExceeded) as spent_error:
            _reserve(
                db,
                job_id,
                global_limit=10,
                user_limit=10,
                attempt=1,
                request_hash="c" * 64,
                reserved_cost_usd=0.04,
            )
        assert spent_error.value.scope == "job_budget"
    engine.dispose()


def test_concurrent_reservations_cannot_overbook_one_job_budget(tmp_path):
    engine_url = URL.create("sqlite", database=str(tmp_path / "job-budget-race.sqlite"))
    engine = create_engine(engine_url, connect_args={"timeout": 10})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        job_id = _add_job(db, "budget-race-user", "budget-race", budget_ceiling_usd=0.05)
        db.commit()
    barrier = Barrier(2)

    def reserve(request_hash: str) -> str:
        with sessions() as db:
            barrier.wait(timeout=5)
            try:
                _reserve(
                    db,
                    job_id,
                    global_limit=10,
                    user_limit=10,
                    request_hash=request_hash,
                    reserved_cost_usd=0.04,
                )
                return "reserved"
            except ModelCallQuotaExceeded as exc:
                return exc.scope

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, ("d" * 64, "e" * 64)))
    assert outcomes.count("reserved") == 1
    assert outcomes.count("job_budget") == 1
    with sessions() as db:
        job = db.get(ResearchJob, job_id)
        assert job.cost_reserved_usd == pytest.approx(0.04)
        assert (
            db.scalar(
                select(func.count(ModelCallReservation.id)).where(
                    ModelCallReservation.job_id == job_id
                )
            )
            == 1
        )
    engine.dispose()


def test_depth_profile_call_prompt_and_output_caps_reserve_atomically(tmp_path):
    engine = create_engine(URL.create("sqlite", database=str(tmp_path / "depth-caps.sqlite")))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        job_id = _add_job(db, "depth-cap-user", "depth-cap", budget_ceiling_usd=1.0)
        db.commit()
        reservation = reserve_daily_model_call(
            db,
            job_id=job_id,
            operation="depth_cap_fixture",
            attempt=0,
            provider="test-provider",
            model_name="test-model",
            request_hash="f" * 64,
            prompt_characters=12,
            prompt_token_upper_bound=12,
            output_token_cap=10,
            max_job_model_calls=1,
            max_job_prompt_characters=20,
            max_job_prompt_token_budget=15,
            max_job_output_token_budget=20,
            global_limit=10,
            per_user_limit=10,
        )
        job = db.get(ResearchJob, job_id)
        assert reservation.prompt_characters == 12
        assert reservation.prompt_token_upper_bound == 12
        assert reservation.output_token_cap == 10
        assert job.model_calls_reserved == 1
        assert job.prompt_characters_reserved == 12
        assert job.prompt_token_budget_reserved == 12
        assert job.output_token_budget_reserved == 10
        with pytest.raises(ModelCallQuotaExceeded) as call_cap:
            reserve_daily_model_call(
                db,
                job_id=job_id,
                operation="another_depth_call",
                attempt=1,
                provider="test-provider",
                model_name="test-model",
                request_hash="g" * 64,
                prompt_characters=1,
                prompt_token_upper_bound=1,
                output_token_cap=1,
                max_job_model_calls=1,
                max_job_prompt_characters=20,
                max_job_prompt_token_budget=100,
                max_job_output_token_budget=20,
                global_limit=10,
                per_user_limit=10,
            )
        assert call_cap.value.scope == "depth_model_calls"
        with pytest.raises(ModelCallQuotaExceeded) as prompt_cap:
            reserve_daily_model_call(
                db,
                job_id=job_id,
                operation="another_depth_prompt",
                attempt=1,
                provider="test-provider",
                model_name="test-model",
                request_hash="h" * 64,
                prompt_characters=9,
                prompt_token_upper_bound=1,
                output_token_cap=1,
                max_job_model_calls=3,
                max_job_prompt_characters=20,
                max_job_prompt_token_budget=100,
                max_job_output_token_budget=20,
                global_limit=10,
                per_user_limit=10,
            )
        assert prompt_cap.value.scope == "depth_prompt_characters"
        with pytest.raises(ModelCallQuotaExceeded) as output_cap:
            reserve_daily_model_call(
                db,
                job_id=job_id,
                operation="another_depth_output",
                attempt=1,
                provider="test-provider",
                model_name="test-model",
                request_hash="i" * 64,
                prompt_characters=1,
                prompt_token_upper_bound=1,
                output_token_cap=11,
                max_job_model_calls=3,
                max_job_prompt_characters=30,
                max_job_prompt_token_budget=100,
                max_job_output_token_budget=20,
                global_limit=10,
                per_user_limit=10,
            )
        assert output_cap.value.scope == "depth_output_tokens"
        with pytest.raises(ModelCallQuotaExceeded) as prompt_token_cap:
            reserve_daily_model_call(
                db,
                job_id=job_id,
                operation="another_depth_prompt_tokens",
                attempt=1,
                provider="test-provider",
                model_name="test-model",
                request_hash="j" * 64,
                prompt_characters=1,
                prompt_token_upper_bound=4,
                output_token_cap=1,
                max_job_model_calls=3,
                max_job_prompt_characters=30,
                max_job_prompt_token_budget=15,
                max_job_output_token_budget=20,
                global_limit=10,
                per_user_limit=10,
            )
        assert prompt_token_cap.value.scope == "depth_prompt_tokens"
        db.refresh(job)
        assert job.model_calls_reserved == 1
        assert job.prompt_characters_reserved == 12
        assert job.prompt_token_budget_reserved == 12
        assert job.output_token_budget_reserved == 10
    engine.dispose()


def test_successful_structured_output_replays_without_recharge(client, monkeypatch):
    project = client.post(
        "/api/v1/projects", json={"title": "Replay cache", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Can a completed model operation be replayed safely?",
            "idempotency_key": "structured-replay-cache-01",
            "budget_ceiling_usd": 0.05,
        },
    ).json()
    settings_for_test = Settings(
        llm_provider="openai",
        openai_api_key="fixture-only",
        openai_model_fast="fixture-model",
        allow_paid_llm_calls=True,
        openai_input_price_per_million=1.0,
        openai_output_price_per_million=1.0,
        max_daily_model_calls=10,
        max_daily_model_calls_per_user=10,
    )
    monkeypatch.setattr(workflow, "settings", settings_for_test)
    monkeypatch.setattr(llm_module, "settings", settings_for_test)
    calls = {"count": 0}

    class CountingProvider:
        def complete_json(self, **kwargs):
            calls["count"] += 1
            return StructuredResult(
                value=ResearchAppraisalBatch(
                    schema_version=2, source_appraisals=[], claim_assessments=[]
                ),
                usage=ProviderUsage(
                    provider="openai",
                    model="fixture-model",
                    input_tokens=80,
                    output_tokens=20,
                    reported_cost_usd=None,
                    estimated_cost_usd=0.001,
                    latency_ms=12,
                    response_repair="markdown_json_fence_removed",
                ),
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow, "configured_provider", CountingProvider)
    job_snapshot = {"id": job["id"], "attempt": 0, "budget_ceiling_usd": 0.05}
    kwargs = {
        "schema_name": "veda_fixture_replay",
        "schema_model": ResearchAppraisalBatch,
        "system": "Return the fixture schema.",
        "user": "A stable request to be cached.",
        "max_output_tokens": 20,
    }
    with client.db_sessions() as db:
        first, first_usage = workflow._call_structured(db, job_snapshot, **kwargs)
        assert first.schema_version == 2
    with client.db_sessions() as db:
        replay, replay_usage = workflow._call_structured(db, job_snapshot, **kwargs)
        assert replay == first
        assert replay_usage.estimated_cost_usd == pytest.approx(0.001)
        assert replay_usage.response_repair == "markdown_json_fence_removed"
        stored_job = db.get(ResearchJob, job["id"])
        assert stored_job.cost_reserved_usd == pytest.approx(0)
        assert stored_job.cost_spent_estimate_usd == pytest.approx(first_usage.estimated_cost_usd)
        assert (
            db.scalar(
                select(func.count(ModelCallReservation.id)).where(
                    ModelCallReservation.job_id == job["id"]
                )
            )
            == 1
        )
        assert (
            db.scalar(select(func.count(UsageEntry.id)).where(UsageEntry.job_id == job["id"])) == 1
        )
    # The cache key includes the complete request, so changed content is a new
    # operation and must not accidentally receive the prior answer.
    with client.db_sessions() as db:
        changed, _ = workflow._call_structured(
            db, job_snapshot, **{**kwargs, "user": "Changed question, changed result key."}
        )
        assert changed == first
        assert (
            db.scalar(
                select(func.count(ModelCallReservation.id)).where(
                    ModelCallReservation.job_id == job["id"]
                )
            )
            == 2
        )
    assert calls["count"] == 2


def test_concurrent_identical_structured_requests_dispatch_only_once(tmp_path, monkeypatch):
    engine_url = URL.create("sqlite", database=str(tmp_path / "structured-replay-race.sqlite"))
    engine = create_engine(engine_url, connect_args={"timeout": 10})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        job_id = _add_job(db, "replay-race-user", "structured-replay-race")
        db.commit()

    openrouter_settings = Settings(
        llm_provider="openrouter",
        openrouter_api_key="fixture-only",
        openrouter_model="openrouter/free",
        max_daily_model_calls=10,
        max_daily_model_calls_per_user=10,
    )
    monkeypatch.setattr(workflow, "settings", openrouter_settings)
    reserve_barrier = Barrier(2)
    real_reserve = workflow.reserve_daily_model_call
    provider_calls = {"count": 0}

    def synchronized_reserve(*args, **kwargs):
        # Both workers have already observed a cache miss at this point.
        reserve_barrier.wait(timeout=5)
        return real_reserve(*args, **kwargs)

    class CountingProvider:
        def complete_json(self, **kwargs):
            provider_calls["count"] += 1
            return StructuredResult(
                value=ResearchAppraisalBatch(
                    schema_version=2, source_appraisals=[], claim_assessments=[]
                ),
                usage=ProviderUsage(
                    provider="openrouter",
                    model="openrouter/free",
                    input_tokens=20,
                    output_tokens=10,
                    reported_cost_usd=0.0,
                    estimated_cost_usd=0.0,
                    latency_ms=1,
                ),
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow, "reserve_daily_model_call", synchronized_reserve)
    monkeypatch.setattr(workflow, "configured_provider", CountingProvider)
    kwargs = {
        "schema_name": "veda_fixture_concurrent_replay",
        "schema_model": ResearchAppraisalBatch,
        "system": "Fixture system.",
        "user": "Identical concurrent request.",
        "max_output_tokens": 20,
    }

    def run_call():
        with sessions() as db:
            try:
                result, _usage = workflow._call_structured(
                    db, {"id": job_id, "attempt": 0}, **kwargs
                )
                return result.schema_version
            except workflow.WorkflowError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: run_call(), range(2)))
    assert results.count(2) + results.count("model_call_uncertain") == 2
    assert provider_calls["count"] == 1
    with sessions() as db:
        assert (
            db.scalar(
                select(func.count(ModelCallReservation.id)).where(
                    ModelCallReservation.job_id == job_id
                )
            )
            == 1
        )
        assert db.scalar(select(func.sum(DailyModelQuota.calls_used))) == 2
    engine.dispose()


def test_paid_budget_rejects_before_provider_dispatch(client, monkeypatch):
    project = client.post(
        "/api/v1/projects", json={"title": "Tiny budget", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Reject an estimate above the job ceiling before dispatch.",
            "idempotency_key": "tiny-paid-budget-01",
            "budget_ceiling_usd": 0.0000001,
        },
    ).json()
    paid_settings = Settings(
        llm_provider="openai",
        openai_api_key="fixture-only",
        openai_model_fast="fixture-model",
        allow_paid_llm_calls=True,
        openai_input_price_per_million=1.0,
        openai_output_price_per_million=1.0,
        max_daily_model_calls=10,
        max_daily_model_calls_per_user=10,
    )
    monkeypatch.setattr(workflow, "settings", paid_settings)
    monkeypatch.setattr(llm_module, "settings", paid_settings)
    provider_factory_calls = {"count": 0}

    def unexpected_provider_factory():
        provider_factory_calls["count"] += 1
        raise AssertionError("provider factory must not run after budget rejection")

    monkeypatch.setattr(workflow, "configured_provider", unexpected_provider_factory)
    with client.db_sessions() as db:
        with pytest.raises(workflow.WorkflowError) as error:
            workflow._call_structured(
                db,
                {"id": job["id"], "attempt": 0},
                schema_name="veda_fixture_tiny_budget",
                schema_model=ResearchAppraisalBatch,
                system="Do bounded work.",
                user="This request estimate exceeds the configured ceiling.",
                max_output_tokens=20,
            )
        assert error.value.code == "budget_exhausted"
    assert provider_factory_calls["count"] == 0
    with client.db_sessions() as db:
        assert (
            db.scalar(
                select(func.count(ModelCallReservation.id)).where(
                    ModelCallReservation.job_id == job["id"]
                )
            )
            == 0
        )


def test_uncertain_paid_call_holds_budget_and_is_never_resent(client, monkeypatch):
    project = client.post(
        "/api/v1/projects", json={"title": "Uncertain spend", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Does an uncertain paid provider outcome remain reserved?",
            "idempotency_key": "uncertain-spend-cache-01",
            "budget_ceiling_usd": 0.05,
        },
    ).json()
    openai_settings = Settings(
        llm_provider="openai",
        openai_api_key="fixture-only",
        openai_model_fast="fixture-model",
        allow_paid_llm_calls=True,
        openai_input_price_per_million=1.0,
        openai_output_price_per_million=1.0,
        max_daily_model_calls=10,
        max_daily_model_calls_per_user=10,
    )
    monkeypatch.setattr(workflow, "settings", openai_settings)
    monkeypatch.setattr(llm_module, "settings", openai_settings)
    calls = {"count": 0}

    class CrashAfterDispatch:
        def complete_json(self, **kwargs):
            calls["count"] += 1
            raise RuntimeError("connection dropped after dispatch")

        def close(self):
            pass

    monkeypatch.setattr(workflow, "configured_provider", CrashAfterDispatch)
    job_snapshot = {"id": job["id"], "attempt": 0, "budget_ceiling_usd": 0.05}
    kwargs = {
        "schema_name": "veda_fixture_uncertain_spend",
        "schema_model": ResearchAppraisalBatch,
        "system": "Fixture system.",
        "user": "Fixture request whose remote outcome is uncertain.",
        "max_output_tokens": 20,
    }
    with client.db_sessions() as db:
        with pytest.raises(RuntimeError, match="connection dropped after dispatch"):
            workflow._call_structured(db, job_snapshot, **kwargs)
    with client.db_sessions() as db:
        reservation = db.scalar(
            select(ModelCallReservation).where(ModelCallReservation.job_id == job["id"])
        )
        stored_job = db.get(ResearchJob, job["id"])
        usage = db.scalar(select(UsageEntry).where(UsageEntry.job_id == job["id"]))
        assert reservation.state == "uncertain"
        assert reservation.reserved_cost_usd > 0
        assert stored_job.cost_reserved_usd == pytest.approx(reservation.reserved_cost_usd)
        assert usage is not None
        assert usage.quota_reservation_id == reservation.id
        assert usage.succeeded is False
        assert usage.error_class == "unexpected_provider_outcome"
        with pytest.raises(workflow.WorkflowError) as error:
            workflow._call_structured(db, {**job_snapshot, "attempt": 1}, **kwargs)
        assert error.value.code == "model_call_uncertain"
    assert calls["count"] == 1
