# ADR-0029: Explicit owner-scoped Veda data purge

- **Status:** Implemented and locally verified; PostgreSQL locking and hosted identity-provider behavior remain unverified.
- **Date:** 2026-10-29
- **Decision owners:** Veda engineering

## Context

The lifecycle API supported full export and permanent deletion of one archived project, but did not let an authenticated owner erase every Veda-stored project and research record. The configured authentication provider owns the sign-in identity and is not available for account deletion. A Veda data purge therefore needs a distinct name and must not imply that signing in, provider records, or operator backups are removed.

## Decision

- `DELETE /api/v1/me/data` requires the exact schema-validated phrase `DELETE VEDA DATA`. It locks the owner's project rows and their research-job rows in deterministic order, rejects the transaction with a sanitized 409 while any job has an unexpired lease, and deletes only the authenticated owner's project cascade and preferences in one database transaction. An empty-state retry succeeds without creating data.
- The operation removes prior-day per-user model quota rows but preserves the current UTC day's user quota safety counter and global quota counters. The response reports the UTC date through which that counter remains and returns `identity_provider_account_deleted: false`.
- The preferences UI puts the full account export before the distinct irreversible confirmation and explains that the sign-in account and operator-held backups remain. After success it clears project and run selection, refreshes the empty workspace, resets local preference controls, and reports the preserved quota boundary.
- `GET /api/v1/me/data-lifecycle` separately reports `veda_data_deletion: available` and `account_deletion: unsupported`. Provider-side identity deletion, backup expiry, and deployment retention scheduling remain external responsibilities.

## Consequences

Owners have a local self-service erase path for Veda-managed research records without confusing it with identity-provider deletion. Preserving the current-day quota safety row prevents erasure from resetting that day's model-call limit. Because the sign-in remains active, the user can create new Veda data after a successful purge. PostgreSQL row-lock behavior has not run in this environment; the verified transaction/isolation behavior is SQLite-only. This endpoint does not erase operator backups or external provider records.

## Verification

- Backend tests verify exact confirmation, unknown-field rejection, owner isolation, cascaded project/job deletion, preference deletion, prior-day quota cleanup, current/global/other-owner quota preservation, idempotent retry, and live-lease rejection followed by expired-lease deletion.
- A real Playwright browser with no API route interception used the provider-disabled local SQLite API, opened an existing research run, performed the confirmation, and verified the sign-in identity still works, project list is empty, preference defaults are restored, and the workspace returns to Overview.
- Frontend unit/build, Ruff, repository backlog/evaluation/source validators, backup/restore and Render schema validators, and the non-uploading secret scan passed. No hosted authentication, PostgreSQL, external provider, or cloud operation occurred.

See also [ADR-0008](ADR-0008-owner-data-export-and-project-purge.md) for project-level export, retention, and purge boundaries.
