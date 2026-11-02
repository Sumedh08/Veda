# ADR-0028: Sanitize unhandled request failures before server logging

- **Status:** Accepted
- **Date:** 2026-10-29
- **Scope:** Unhandled exceptions that escape route, dependency, and inner middleware execution

## Context

SQLAlchemy failures have a type-specific API contract in ADR-0027. Other unexpected exceptions still need a stable response. Registering a generic exception handler with Starlette's server-error layer is insufficient for log privacy because that layer may re-raise after returning its response, allowing the ASGI server to log the raw traceback.

## Decision

Catch otherwise unhandled `Exception` values inside Veda's request-ID/security middleware before they reach the outer server-error layer. Return HTTP 500 with a stable `internal_error` object and request ID. Preserve the standard response security headers and add CORS response headers only for an exact configured origin. Log only request ID and exception class; omit message, SQL, parameters, chained cause, and traceback.

The SQLAlchemy handler remains more specific and continues to return `storage_unavailable` 503 or `storage_error` 500. The request-size, CORS and exception middleware interactions are exercised through a real protected route in TestClient.

## Consequences

- Unexpected application failures have a consistent browser-readable error shape and correlation ID.
- Secrets in arbitrary exception messages do not enter the HTTP body or application log.
- The generic middleware catches `Exception`, not process-control `BaseException` values.
- Tests establish middleware behavior only; production proxy and server logging behavior remain unverified.
