# Threat model (initial)

## Assets

User identity and project content; research questions; source/passage records; provider secrets; cost budgets; job/report integrity.

## Trust boundaries

Browser ↔ API; API ↔ identity provider; API ↔ database; API ↔ scholarly/search/model providers; fetched web documents ↔ parsers and model prompts.

## Main threats and required controls

- Cross-tenant access: verify JWT server-side and apply owner scoping to every nested query.
- Forged/expired tokens: fixed issuer/audience/algorithm checks and key rotation support; fail closed.
- Development auth exposure: local-only, explicit opt-in, production startup rejection.
- SSRF and redirect abuse: allow only HTTP(S), reject non-public resolved addresses, cap redirects/bytes/time and revalidate each hop; do not fetch user-supplied URLs by default.
- Prompt injection in documents: treat fetched text as quoted data, never as provider/tool instructions; allowlist tools in application logic.
- Malicious/oversized documents: content-type/size caps, bounded extraction and no shell execution.
- Cost abuse: per-job and global caps, bounded calls/retries, provider usage ledger, no surprise background calls.
- Secrets/log leakage: secrets only server-side, redact auth and provider headers, `.env` ignored.
- Duplicate/concurrent stages: persisted idempotency keys and fenced leases/versions.

## Implemented local controls (2026-10-29)

- API requests use database-backed fixed-window counters with atomic SQLite/PostgreSQL upserts. Limits cover per-IP and per-user requests, with tighter hourly research-job creation and per-minute stage-advance/resume limits. Development-token issuance has its own per-IP limit. The user subject is read from the bearer payload only to group rate counters; endpoint authentication separately verifies the token.
- Rate-counter identifiers are HMAC-hashed before persistence. Non-development/test deployments require `RATE_LIMIT_HASH_SECRET` (32+ characters). The limiter does not trust `X-Forwarded-For`; behind a proxy, the direct socket IP may group multiple clients together, while verified user limits still distinguish them.
- API request bodies are bounded to 1 MiB by default, with a validated 1–10 MiB configuration range; both declared content lengths and streamed bodies are checked before JSON parsing.
- The current deterministic database tests cover rate-limit status/retry headers, separate users/tokens, job-creation caps, hashed stored identity, body-size rejection, and one-winner atomic request counters across spawned SQLite processes. PostgreSQL behavior remains unverified.

These are implementation and fixture results, not a complete penetration test or deployment security review. Dependency advisory checks and the remaining prompt-injection/retrieval tests are tracked in T-14; SSRF controls remain T-03.

This is a design inventory, not a completed security audit.

