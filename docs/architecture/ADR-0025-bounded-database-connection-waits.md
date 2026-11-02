# ADR-0025: Bound database connection and pool waits

- **Status:** Accepted
- **Date:** 2026-10-29
- **Scope:** PostgreSQL connection establishment and SQLAlchemy connection-pool checkout

## Context

Readiness executes a database query, and ordinary API requests use the same SQLAlchemy engine. A failing database can therefore delay requests while a pool checkout or new driver connection waits. A clean 503 response contract does not bound either wait.

SQLAlchemy documents `pool_timeout` as the maximum wait for a `QueuePool` connection and passes `connect_args` through to the DBAPI. Psycopg 3 documents `connect_timeout` for a connection attempt. The relevant primary documentation is [SQLAlchemy engine configuration](https://docs.sqlalchemy.org/en/20/core/engines.html), [SQLAlchemy pool exhaustion guidance](https://docs.sqlalchemy.org/en/20/errors.html), and [Psycopg connection usage](https://www.psycopg.org/psycopg3/docs/basic/usage.html).

## Decision

Configure PostgreSQL engine creation with `DATABASE_CONNECT_TIMEOUT_SECONDS=5` and `DATABASE_POOL_TIMEOUT_SECONDS=5` by default. Both settings are operator-overridable integers bounded from 1 to 60 seconds. Preserve SQLite's existing `check_same_thread=False` behavior and do not pass PostgreSQL-only arguments to SQLite.

These settings bound driver connection establishment and pool checkout. They do not bound every query execution, DNS lookup on every platform, a multi-host connection string's aggregate attempts, request processing, or total job duration. PostgreSQL runtime behavior remains unverified until T-09 can run against a disposable PostgreSQL service.

## Consequences

- Pool saturation and failed connection establishment surface as errors sooner instead of waiting on driver/pool defaults.
- Readiness retains its sanitized 503 response for database failures; application middleware and route handling remain responsible for translating failures safely.
- Defaults may need operator adjustment for high-latency managed databases, within the documented 60-second cap.
- Local deterministic tests inspect SQLAlchemy's effective pool timeout and the Psycopg dialect's connect arguments without opening a network connection.
