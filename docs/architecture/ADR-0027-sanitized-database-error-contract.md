# ADR-0027: Normalize database failures at the HTTP boundary

- **Status:** Accepted
- **Date:** 2026-10-29
- **Scope:** Unhandled SQLAlchemy exceptions raised by API route operations

## Context

The shared rate limiter already translates its own SQLAlchemy failures to a generic 503. A route query can fail after the limiter has committed successfully, however, and FastAPI's default handling has no Veda-specific error code or request-ID payload for this path. Driver exception text may contain connection details and must not be returned or logged verbatim.

## Decision

Register a SQLAlchemy exception handler. Operational, interface, pool-timeout, and invalidated-connection failures return HTTP 503 with `storage_unavailable`; other SQLAlchemy failures return HTTP 500 with `storage_error`. Both responses contain a stable generic message and the request ID. Log only the request ID and exception class, never the exception message, SQL, parameters, URL, or chained cause.

The existing request middleware adds response request-ID, security, and CORS headers to this handled path. The rate-limiter's existing 503 contract remains unchanged. Arbitrary unhandled exceptions are covered separately by [ADR-0028](ADR-0028-sanitized-unhandled-error-boundary.md).

## Consequences

- Route-level database failures have an observable, machine-readable API contract suitable for retry UI and incident correlation.
- Known connection/timeouts are retryable 503s; data/constraint/programming failures remain generic 500s.
- Error responses and logs omit raw database details. Operators can correlate via request ID and exception class but do not receive a stack trace from this handler.
- The behavior is verified with an injected TestClient error; no live PostgreSQL outage is claimed.
