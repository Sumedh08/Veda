# ADR-0010: Deferred retrieval uses an immutable continuation run

**Status:** Accepted for local implementation; PostgreSQL and live-host behavior remain unverified (T-09/T-12/T-15).

## Context

The extraction stage can defer a permitted HTML or PDF request when the shared host interval cannot fit inside that stage's deadline. The completed report must remain an immutable view of the evidence available when it was written, and successful sources in the original run must not be fetched again just because another source was deferred.

## Decision

- Persist a per-source, per-format retry state and absolute due time in the source's retrieval metadata. The state is created only for `origin_request_deferred`; ordinary transport failures are not automatically made retryable.
- Require an authenticated owner action after the due time. The API creates one idempotent child run linked by `parent_job_id`, copies the source/evidence graph with new IDs and immediate-parent provenance IDs, and puts only the selected deferred source/format pairs into the child's extraction checkpoint.
- The continuation reuses saved metadata, candidates, document snapshots, passages, and claims. It sends no request for successful sources. The child receives its own report; the original report is not edited or replaced.
- Carry forward the saved budget ceiling, spend estimate, model-call count, and token counters so a continuation does not reset the original run's configured resource envelope. Existing account-wide quotas continue to apply.
- Do not add an autonomous scheduler or worker for this boundary. The user can see the persisted due time and explicitly start a continuation; if a host defers the request again, the child records a new due time and remains inspectable.

## Alternatives considered

- **Reopen the original job at extraction:** rejected because the one-report-per-run model would either mutate the report already shown to the user or leave that report stale after new evidence arrives.
- **Create an automatic queue worker:** deferred because Veda currently advances bounded stages through the API/browser, no production worker or host review is configured, and autonomous requests would add lifecycle and deployment behavior not required to honor a recorded host interval.
- **Copy only the retried source:** rejected because the continuation report would omit evidence already assembled into the parent report. Copying the bounded evidence graph keeps the new report's citations self-contained while the source/document IDs retain lineage.
- **Retry all sources during continuation:** rejected because it repeats successful network requests and can violate the source's intended request pacing without improving the saved evidence.

## Consequences and verification boundary

The child run makes the old and updated reports independently inspectable, but duplicates the small persisted evidence metadata graph across runs; raw HTML/PDF bytes are still never retained. Due-state records are stored in JSON and are not independently indexed or scheduled. Local tests cover early denial, owner isolation, idempotent replay, evidence identity, targeted retry, re-deferral, and SQLite engine restart. The backend suite passed 253 tests with 2 PostgreSQL-only skips, the browser suite passed 38/38, Vitest passed 13/13, and the production build passed. No live host or provider was contacted; the checked-in host registry remains empty.
