# Acceptance tests

Status starts as **planned**; update only with an executed result. The coverage matrix records the exact current implementation boundary.

- [ ] An unauthenticated request cannot read a project.
- [ ] User A cannot read or mutate User B's project, job, source, passage, claim or report by ID.
- [ ] A research question creates a durable job and event before external work starts.
- [ ] One bounded stage advances per request and can resume after process restart.
- [ ] Duplicate advance operation keys do not create duplicate stage outputs or events.
- [ ] A transient source failure preserves earlier results and is visible to the user.
- [ ] A claim without a stored source passage cannot be marked grounded.
- [ ] Report citations resolve to the correct source and passage; unsupported citations are flagged.
- [ ] Model-unavailable flow does not fabricate a synthesis and states the missing stage.
- [ ] A 360px viewport can sign in, create a project, resume work, inspect a source and read a report.
- [ ] No live/paid API call is required for deterministic end-to-end checks.

## Recorded verification

- [x] Mocked Crossref source-to-report path persists a plan, source, exact passage, source-reported claim, deterministic source map, events and limitation-aware report.
- [x] Duplicate advance operation key is idempotent; provider failure is resumable; selected project/job/source ownership checks reject a second user.
- [x] A zero-dollar paid-model budget completes through the evidence-map fallback without writing a model-usage entry.
- [x] OpenRouter provider adapter accepts a mocked zero-cost structured response and rejects a mocked nonzero cost. One separate live structured-output smoke request through the adapter passed using a free route; no user research was sent.
- [x] OpenAI paid-provider preflight refuses a zero-budget request before making an HTTP request.
- [x] Frontend production typecheck/build and API-client/citation-marker unit tests pass; no browser/mobile/accessibility audit has been run.
- [x] Local SQLite migration upgrade and `alembic check` pass; no fresh Postgres migration or recovery drill has been run.
- [ ] Managed authentication, live OpenAI app workflow, remote database, browser sign-in, remote HTTPS, and cross-device resume remain unverified.

