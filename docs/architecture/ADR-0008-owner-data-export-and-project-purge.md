# ADR-0008: Owner export and project purge semantics

- **Status:** Local authenticated API and browser workflow implemented; deployment retention and identity-provider account deletion remain open. Owner-wide Veda-data purge is separately specified in ADR-0029.
- **Date:** 2026-10-29
- **Decision owners:** Veda engineering

## Context

The earlier lifecycle exposed only project archive/restore and individual report downloads. Users need a usable account export and a clearly confirmed way to erase a project's Veda-managed records. Veda does not own identity-provider accounts or the original HTML/PDF payloads, and no durable scheduled-retention service is configured.

## Decision

- `GET /api/v1/me/export` streams a versioned JSON envelope with owner-scoped project, preference, quota, conversation/message, job/event, source/candidate/document/passage, claim/relationship/hypothesis, report, model-call reservation, and usage-ledger collections. It serializes one row at a time with SQLAlchemy `yield_per=100`.
- The export does not include identity-provider records, stored API credentials/authentication tokens, or original downloaded HTML/PDF bytes. Credential-shaped JSON keys are recursively redacted. Response headers mark the file `no-store` and `nosniff`; `Content-Disposition` is exposed to the browser via the configured CORS allowlist so the date-stamped filename is preserved.
- `DELETE /api/v1/projects/{id}/permanent` requires an authenticated owner, a soft-archived project, the literal `DELETE`, and the exact current project title. A successful purge removes project-owned Veda rows through the relational cascade. The UI offers this only for archived projects and reflects the irreversible effect.
- The owner can choose never, 30, 90, or 365 days for newly archived projects. The API stores a `purge_at` timestamp; restoring clears it. `python -m app.maintenance.purge_expired_projects` is a safe dry run, while `--apply` performs bounded, locked, idempotent project purges. The lifecycle panel says expiry only occurs when deployment maintenance is scheduled; this local build does not configure a scheduler. Operators remain responsible for database-backup retention. Account deletion remains unsupported because the configured identity provider owns that identity lifecycle.
- The separately named `DELETE /api/v1/me/data` operation erases all owner-scoped Veda project/research records and preferences after the exact `DELETE VEDA DATA` confirmation, with the live-lease guard and quota-safety behavior in [ADR-0029](ADR-0029-explicit-veda-data-purge.md). It does not delete the sign-in account, provider records, backups, or current-day quota safety counter.

## Consequences

The user can export, erase one archived project, or use the separately confirmed owner-wide Veda-data purge locally without pretending these actions erase external identity-provider or backup records. The API checks ownership independently of browser visibility. Requiring archive before project purge provides an additional review step, while title matching alone is not an authorization mechanism.

The retention policy and safe purge worker are locally implemented, but production requires a scheduled host task and PostgreSQL lock/restart verification (T-09/T-12). Identity-provider account deletion likewise requires a configured provider-side deletion capability. These gaps are not represented as completed.

## Verification

Backend fixtures verify tenant isolation, JSON export contents/redaction, lifecycle capability disclosure, archive-before-purge, exact-title confirmation, and project-row cascade. Browser fixtures exercise export download filename visibility through CORS and the exact-title deletion UI. SQLite tests do not establish PostgreSQL transaction behavior. No remote account or cloud data was touched.
