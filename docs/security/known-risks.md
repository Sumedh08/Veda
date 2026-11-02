# Known risks

- Managed authentication and production PostgreSQL are not configured or verified.
- Local dev auth is not suitable for remote hosting and must be disabled outside development.
- Database leasing reduces duplicate work but cannot guarantee exactly-once third-party billing after a lost response.
- Scholarly metadata and abstracts can be incomplete, stale or subject to access/storage terms; Veda must disclose access class and defer to source terms.
- LLM support checks can miss errors; they cannot prove causal validity or replace domain review.
- Browser-stepped jobs pause when no browser advances them on sleeping infrastructure.
- Published Render, Neon, Supabase, OpenAI, and OpenRouter limits were checked on 2026-10-28; they may change and do not guarantee service availability.
- OpenRouter free-provider data-handling terms vary; the UI discloses that research excerpts may be sent to the configured provider, but each provider/model policy still needs review before confidential use.
- Research quality has not been human-reviewed. A report's deterministic citation-link check does not prove its claim is semantically supported or scientifically correct.
- The benchmark registry is unreviewed and has no gold answers; no accuracy or comparative-performance number is available.
- Database-backed API rate limits and request-body caps now have local SQLite tests. PostgreSQL concurrency and reverse-proxy client-IP behavior have not been verified; the limiter intentionally ignores forwarded-IP headers unless a trusted-proxy policy is added.
- Production/staging configuration now requires a private `RATE_LIMIT_HASH_SECRET`. No hosted environment has been configured to verify this setting or the new migration remotely.
- Route-level SQLAlchemy errors and other unhandled request exceptions now have generic sanitized 503/500 payloads with request IDs; local tests verify the generic boundary returns before framework server-error logging. Proxy and production ASGI server behavior remain unverified.

