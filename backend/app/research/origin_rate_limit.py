"""Atomic, database-backed request scheduling by exact URL origin."""

import math
import time
from contextlib import nullcontext
from datetime import UTC, datetime

from sqlalchemy import BigInteger, cast, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.models import OriginRequestSlot

ORIGIN_REQUEST_ADMISSION_MARGIN_MS = 100


class OriginRateLimitUnavailable(Exception):
    """The shared request-slot store could not safely reserve an origin slot."""


class OriginRequestDeferred(Exception):
    """The next shared slot is later than this bounded request can wait."""

    def __init__(self, retry_after_seconds: float):
        super().__init__("The host request interval exceeds this retrieval step's deadline.")
        self.retry_after_seconds = max(0.0, retry_after_seconds)


class DatabaseOriginRequestLimiter:
    """Reserve globally ordered origin slots with a single SQLite/PostgreSQL upsert."""

    def __init__(self, bind):
        self._workflow_session = bind if isinstance(bind, Session) else None
        engine_or_connection = bind.get_bind() if self._workflow_session is not None else bind
        self._session_factory = (
            None
            if self._workflow_session is not None
            else sessionmaker(bind=engine_or_connection, autoflush=False, expire_on_commit=False)
        )
        self._dialect = engine_or_connection.dialect.name

    def acquire(self, origin: str, interval_seconds: float, *, deadline: float) -> None:
        if self._dialect not in {"sqlite", "postgresql"}:
            raise OriginRateLimitUnavailable("Unsupported request-slot database dialect.")
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or not math.isfinite(interval_seconds)
            or not 0 <= interval_seconds <= 86_400
        ):
            raise OriginRateLimitUnavailable("The reviewed host interval is invalid.")
        if not isinstance(origin, str) or not origin or len(origin) > 512:
            raise OriginRateLimitUnavailable("The request origin is invalid.")
        if (
            isinstance(deadline, bool)
            or not isinstance(deadline, (int, float))
            or not math.isfinite(deadline)
        ):
            raise OriginRateLimitUnavailable("The request deadline is invalid.")

        interval_ms = math.ceil(interval_seconds * 1000)
        if interval_ms:
            # Leave a small gap for the database-to-socket handoff on busy workers.
            interval_ms += ORIGIN_REQUEST_ADMISSION_MARGIN_MS
        now_ms = time.time_ns() // 1_000_000
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            raise OriginRequestDeferred(0)
        remaining_ms = math.floor(remaining_seconds * 1000)
        latest_slot_ms = now_ms + remaining_ms
        now = datetime.now(UTC)
        try:
            session_context = (
                nullcontext(self._workflow_session)
                if self._workflow_session is not None
                else self._session_factory()
            )
            if self._workflow_session is not None:
                # A research stage can have appended an identity-cache row before a
                # later provider request. Commit that durable cache write first so
                # SQLite does not hold a writer lock while this request slot is
                # reserved. The lease was committed before stage execution, and the
                # StageResult is still persisted by the route after the stage returns.
                self._workflow_session.flush()
                self._workflow_session.commit()
            with session_context as db:
                connection = db.connection()
                previous_busy_timeout = self._apply_database_deadline(db, deadline)
                try:
                    slot = self._reserve(db, origin, interval_ms, latest_slot_ms, now)
                    if slot is None:
                        next_slot = db.scalar(
                            select(OriginRequestSlot.next_slot_ms).where(
                                OriginRequestSlot.origin == origin
                            )
                        )
                        last_slot = db.scalar(
                            select(OriginRequestSlot.last_slot_ms).where(
                                OriginRequestSlot.origin == origin
                            )
                        )
                        self._restore_sqlite_busy_timeout(connection, previous_busy_timeout)
                        db.rollback()
                        retry_now_ms = time.time_ns() // 1_000_000
                        next_start = max(
                            retry_now_ms,
                            int(next_slot or retry_now_ms),
                            int(last_slot or retry_now_ms) + interval_ms,
                        )
                        raise OriginRequestDeferred((next_start - retry_now_ms) / 1000)
                    self._restore_sqlite_busy_timeout(connection, previous_busy_timeout)
                    db.commit()
                except OriginRequestDeferred:
                    raise
                except SQLAlchemyError:
                    self._restore_sqlite_busy_timeout(connection, previous_busy_timeout)
                    db.rollback()
                    raise
        except OriginRequestDeferred:
            raise
        except SQLAlchemyError as exc:
            raise OriginRateLimitUnavailable(
                "The shared host request-slot store is unavailable."
            ) from exc

        current_epoch_ms = time.time_ns() // 1_000_000
        wait_seconds = max(0.0, (slot - current_epoch_ms) / 1000)
        remaining_seconds = deadline - time.monotonic()
        if wait_seconds >= remaining_seconds:
            raise OriginRequestDeferred(wait_seconds)
        if wait_seconds:
            time.sleep(min(wait_seconds, remaining_seconds))
        if time.monotonic() >= deadline:
            raise OriginRequestDeferred(wait_seconds)

    def _apply_database_deadline(self, db: Session, deadline: float) -> int | None:
        remaining_ms = math.floor((deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            raise OriginRequestDeferred(0)
        connection = db.connection()
        if self._dialect == "sqlite":
            current_timeout = int(connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one())
            connection.exec_driver_sql(
                f"PRAGMA busy_timeout = {min(current_timeout, remaining_ms)}"
            )
            return current_timeout
        if self._dialect == "postgresql":
            db.scalar(
                select(
                    func.set_config(
                        "statement_timeout",
                        f"{remaining_ms}ms",
                        True,
                    )
                )
            )
        return None

    def _restore_sqlite_busy_timeout(self, connection, previous_timeout: int | None) -> None:
        if self._dialect == "sqlite" and previous_timeout is not None:
            connection.exec_driver_sql(f"PRAGMA busy_timeout = {previous_timeout}")

    def _reserve(
        self,
        db: Session,
        origin: str,
        interval_ms: int,
        latest_slot_ms: int,
        now: datetime,
    ) -> int | None:
        result = db.execute(self._reservation_statement(origin, interval_ms, latest_slot_ms, now))
        reserved = result.scalar_one_or_none()
        return int(reserved) if reserved is not None else None

    def _reservation_statement(
        self,
        origin: str,
        interval_ms: int,
        latest_slot_ms: int,
        now: datetime,
    ):
        row = OriginRequestSlot.__table__
        if self._dialect == "sqlite":
            statement = sqlite_insert(OriginRequestSlot)
            greatest = func.max
            database_now_ms = cast((func.julianday("now") - 2440587.5) * 86_400_000, BigInteger)
        else:
            statement = postgresql_insert(OriginRequestSlot)
            greatest = func.greatest
            database_now_ms = cast(func.extract("epoch", func.clock_timestamp()) * 1000, BigInteger)

        slot_expression = greatest(
            database_now_ms,
            row.c.last_slot_ms + interval_ms,
            row.c.next_slot_ms,
        )
        statement = statement.values(
            origin=origin,
            last_slot_ms=database_now_ms,
            next_slot_ms=database_now_ms + interval_ms,
            updated_at=now,
        )
        return statement.on_conflict_do_update(
            index_elements=[row.c.origin],
            set_={
                "last_slot_ms": slot_expression,
                "next_slot_ms": slot_expression + interval_ms,
                "updated_at": now,
            },
            where=slot_expression <= latest_slot_ms,
        ).returning(row.c.last_slot_ms)
