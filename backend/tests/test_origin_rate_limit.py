import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.models import OriginRequestSlot
from app.research.origin_rate_limit import (
    DatabaseOriginRequestLimiter,
    OriginRateLimitUnavailable,
    OriginRequestDeferred,
)


@pytest.fixture
def rate_limit_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'origin-rate-limit.sqlite3'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    OriginRequestSlot.__table__.create(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def test_independent_limiter_instances_share_ordered_origin_slots(rate_limit_engine):
    limiters = [DatabaseOriginRequestLimiter(rate_limit_engine) for _ in range(5)]
    interval = 0.04

    def acquire(index):
        started = time.monotonic()
        limiters[index].acquire("https://papers.example", interval, deadline=started + 3)
        return time.monotonic()

    with ThreadPoolExecutor(max_workers=len(limiters)) as pool:
        acquired_at = sorted(pool.map(acquire, range(len(limiters))))

    assert all(
        later - earlier >= interval * 0.75
        for earlier, later in zip(acquired_at, acquired_at[1:], strict=False)
    ), acquired_at


def test_new_limiter_instance_observes_persisted_interval(rate_limit_engine):
    first = DatabaseOriginRequestLimiter(rate_limit_engine)
    second = DatabaseOriginRequestLimiter(rate_limit_engine)
    first.acquire("https://papers.example", 0.15, deadline=time.monotonic() + 1)

    started = time.monotonic()
    second.acquire("https://papers.example", 0.15, deadline=started + 1)

    assert time.monotonic() - started >= 0.12


def test_sqlite_busy_timeout_is_restored_after_slot_reservation(rate_limit_engine):
    limiter = DatabaseOriginRequestLimiter(rate_limit_engine)
    limiter.acquire("https://papers.example", 0, deadline=time.monotonic() + 1)

    with rate_limit_engine.connect() as connection:
        busy_timeout_ms = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()

    assert busy_timeout_ms == 5000


def test_limiter_can_reserve_using_the_workflow_session_after_identity_write(rate_limit_engine):
    """A discovery-stage identity write must not lock out its next provider request."""
    now_ms = time.time_ns() // 1_000_000
    with Session(rate_limit_engine, autoflush=False, expire_on_commit=False) as workflow_db:
        workflow_db.add(
            OriginRequestSlot(
                origin="https://identity-cache.example",
                last_slot_ms=now_ms,
                next_slot_ms=now_ms,
                updated_at=datetime.now(UTC),
            )
        )
        workflow_db.flush()

        DatabaseOriginRequestLimiter(workflow_db).acquire(
            "https://papers.example", 0, deadline=time.monotonic() + 1
        )

        with rate_limit_engine.connect() as reader:
            assert reader.scalar(
                select(OriginRequestSlot.origin).where(
                    OriginRequestSlot.origin == "https://identity-cache.example"
                )
            ) == "https://identity-cache.example"
            assert reader.scalar(
                select(OriginRequestSlot.origin).where(
                    OriginRequestSlot.origin == "https://papers.example"
                )
            ) == "https://papers.example"


def test_unrelated_origins_do_not_block_each_other(rate_limit_engine):
    limiter = DatabaseOriginRequestLimiter(rate_limit_engine)
    limiter.acquire("https://papers.example", 0.5, deadline=time.monotonic() + 1)

    started = time.monotonic()
    limiter.acquire("https://other.example", 0.5, deadline=started + 0.1)

    assert time.monotonic() - started < 0.1


def test_elapsed_reservation_window_is_released_to_database_time(rate_limit_engine):
    old_slot_ms = time.time_ns() // 1_000_000 - 10_000
    with rate_limit_engine.begin() as connection:
        connection.execute(
            OriginRequestSlot.__table__.insert().values(
                origin="https://papers.example",
                last_slot_ms=old_slot_ms,
                next_slot_ms=old_slot_ms + 100,
                updated_at=datetime.now(UTC),
            )
        )

    limiter = DatabaseOriginRequestLimiter(rate_limit_engine)
    limiter.acquire("https://papers.example", 0, deadline=time.monotonic() + 1)

    with rate_limit_engine.connect() as connection:
        row = connection.execute(
            select(OriginRequestSlot.last_slot_ms, OriginRequestSlot.next_slot_ms).where(
                OriginRequestSlot.origin == "https://papers.example"
            )
        ).one()
    assert row.last_slot_ms > old_slot_ms + 100
    assert row.next_slot_ms == row.last_slot_ms


def test_expired_deadline_does_not_create_a_reservation(rate_limit_engine):
    limiter = DatabaseOriginRequestLimiter(rate_limit_engine)
    with pytest.raises(OriginRequestDeferred):
        limiter.acquire("https://papers.example", 0.1, deadline=time.monotonic() - 1)

    with rate_limit_engine.connect() as connection:
        row = connection.scalar(
            select(OriginRequestSlot.origin).where(
                OriginRequestSlot.origin == "https://papers.example"
            )
        )
    assert row is None


def test_database_lock_wait_is_capped_by_request_deadline(rate_limit_engine):
    limiter = DatabaseOriginRequestLimiter(rate_limit_engine)
    blocker = rate_limit_engine.connect()
    blocker.exec_driver_sql("BEGIN IMMEDIATE")
    try:
        started = time.monotonic()
        with pytest.raises(OriginRateLimitUnavailable):
            limiter.acquire("https://papers.example", 0, deadline=started + 0.2)
        elapsed = time.monotonic() - started
    finally:
        blocker.rollback()
        blocker.close()

    assert elapsed < 0.8


def test_later_slot_beyond_deadline_is_deferred_without_reservation(rate_limit_engine):
    limiter = DatabaseOriginRequestLimiter(rate_limit_engine)
    limiter.acquire("https://papers.example", 0, deadline=time.monotonic() + 1)
    with rate_limit_engine.begin() as connection:
        connection.execute(
            OriginRequestSlot.__table__.update()
            .where(OriginRequestSlot.origin == "https://papers.example")
            .values(next_slot_ms=time.time_ns() // 1_000_000 + 500)
        )
    before = None
    with rate_limit_engine.connect() as connection:
        before = connection.execute(
            select(OriginRequestSlot.last_slot_ms, OriginRequestSlot.next_slot_ms).where(
                OriginRequestSlot.origin == "https://papers.example"
            )
        ).one()

    with pytest.raises(OriginRequestDeferred) as deferred:
        limiter.acquire("https://papers.example", 0.1, deadline=time.monotonic() + 0.03)

    assert deferred.value.retry_after_seconds >= 0.4
    with rate_limit_engine.connect() as connection:
        after = connection.execute(
            select(OriginRequestSlot.last_slot_ms, OriginRequestSlot.next_slot_ms).where(
                OriginRequestSlot.origin == "https://papers.example"
            )
        ).one()
    assert after == before


def test_unsupported_database_dialect_fails_closed(rate_limit_engine):
    limiter = DatabaseOriginRequestLimiter(rate_limit_engine)
    limiter._dialect = "unsupported"
    with pytest.raises(OriginRateLimitUnavailable):
        limiter.acquire("https://papers.example", 0, deadline=time.monotonic() + 1)


@pytest.mark.parametrize("interval", [True, "0", float("nan"), -1, 86_401])
def test_invalid_request_intervals_fail_closed(rate_limit_engine, interval):
    limiter = DatabaseOriginRequestLimiter(rate_limit_engine)
    with pytest.raises(OriginRateLimitUnavailable):
        limiter.acquire("https://papers.example", interval, deadline=time.monotonic() + 1)


@pytest.mark.parametrize("deadline", [True, "later", float("nan")])
def test_invalid_deadlines_fail_closed(rate_limit_engine, deadline):
    limiter = DatabaseOriginRequestLimiter(rate_limit_engine)
    with pytest.raises(OriginRateLimitUnavailable):
        limiter.acquire("https://papers.example", 0, deadline=deadline)


@pytest.mark.parametrize(
    ("dialect_name", "dialect", "clock_function"),
    [
        ("sqlite", sqlite.dialect(), "julianday"),
        ("postgresql", postgresql.dialect(), "clock_timestamp"),
    ],
)
def test_dialect_upsert_compiles_with_server_clock_and_conditional_deadline(
    rate_limit_engine, dialect_name, dialect, clock_function
):
    limiter = DatabaseOriginRequestLimiter(rate_limit_engine)
    limiter._dialect = dialect_name
    statement = limiter._reservation_statement(
        "https://papers.example",
        1500,
        time.time_ns() // 1_000_000 + 10_000,
        datetime.now(UTC),
    )

    compiled = str(statement.compile(dialect=dialect)).lower()

    assert "on conflict" in compiled
    assert clock_function in compiled
    assert "where" in compiled
    assert "returning" in compiled
