# ADR-0009: Shared per-origin request slots

**Date:** 2026-10-29  
**Status:** Accepted for local implementation; PostgreSQL execution pending T-09

## Context

The retrieval-rights screen observed robots `Crawl-delay` values of 15 seconds for arXiv and 30 seconds for PLOS. T-42 deliberately left both hosts disabled because a process-local sleep or counter cannot coordinate multiple API workers. A request that cannot wait within the bounded extraction step must be deferred without exceeding that step or sending the document request early.

The local SQLite path and the planned PostgreSQL deployment both need the same behavior. The database is already the durable shared coordination point for quotas and job leases. A read-then-write interval calculation would race across workers, and a timestamp sampled before a contended write can become stale before the reservation is committed. The latter was reproduced by the concurrent SQLite test and corrected by evaluating the database clock within the upsert.

## Decision

- Store one row per exact URL origin (`scheme://host[:port]`) in `origin_request_slots`. Store epoch milliseconds as 64-bit integers and retain `updated_at` for operational inspection.
- Reserve the next slot using one dialect-specific `INSERT ... ON CONFLICT DO UPDATE ... RETURNING`: SQLite uses `julianday('now')`; PostgreSQL uses `clock_timestamp()`. The conflict update chooses the greatest of database time, the previous slot plus the requested interval, and the already-reserved next slot. A conditional update prevents booking a slot beyond the caller's deadline.
- Apply the larger of the exact reviewed host's `minimum_interval_seconds` and the selected robots group's `Crawl-delay` to HTML/PDF document requests. Robots requests and every robots/document redirect use the destination origin's own reviewed host interval. All zero-delay requests are also recorded so the scheduler knows when a robots response was requested before it learns a positive delay.
- Add a 100 ms admission margin to positive intervals to cover the handoff from a committed database slot to the outbound socket write. The worker requests the slot after DNS/TLS setup and immediately before sending HTTP bytes.
- If the scheduler is missing/unavailable, reject the request. If a reserved slot cannot fit the remaining monotonic stage deadline, send no HTTP request and surface `origin_request_deferred` with `retry_after_seconds` when known. The extraction metadata distinguishes a defer from a transport failure. T-51 adds an owner-triggered due-time continuation; this does not create an automatic requeue or treat a defer as successful retrieval.
- Keep the host registry empty until an exact host terms/license review is complete. Implementing a rate limiter does not grant rights or enable a source.

## Alternatives considered

- **Per-process throttling:** rejected because each worker would maintain an independent clock and positive delays could be violated by concurrent workers.
- **Read the last request then insert/update:** rejected because concurrent workers can read the same old timestamp and schedule the same slot.
- **`SELECT ... FOR UPDATE` row lock:** not chosen for the admission path; a single dialect-specific upsert makes reservation and slot ordering one atomic write and works with both SQLite and PostgreSQL. PostgreSQL production behavior still requires T-09 runtime validation.
- **Fail every positive robots delay:** safe but prevents compliant retrieval even when a bounded shared slot can be scheduled.
- **Sleep past the current stage deadline:** rejected because it makes job runtime unbounded and can stall unrelated work.

## Verification boundary

`backend/tests/test_origin_rate_limit.py` covers independent concurrent limiters, persisted state observed by a new limiter instance, per-origin isolation, expired/deadline-limited deferral, unsupported dialect failure, and SQL compilation for both SQLite and PostgreSQL. HTML/PDF fixtures verify robots delay propagation, per-origin redirect slots, fail-closed behavior, and retryable deferral. `backend/scripts/verify_migration_roundtrip.py` exercises the full SQLite schema migration chain and Alembic metadata consistency.

SQLite has been executed locally. PostgreSQL SQL has compile-time coverage only; server execution, transaction behavior under competing PostgreSQL workers, and production concurrency remain unverified because no disposable PostgreSQL service is available (T-09/B-003). No live publisher document was fetched, no host was enabled, and no legal or research-quality conclusion follows from these tests.

## Primary documentation

- SQLAlchemy [SQLite `ON CONFLICT` support](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#insert-on-conflict-upsert).
- SQLAlchemy [PostgreSQL `ON CONFLICT` support](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert).
- SQLite [date and time functions](https://www.sqlite.org/lang_datefunc.html).
- PostgreSQL [date/time functions, including `clock_timestamp()`](https://www.postgresql.org/docs/current/functions-datetime.html).
