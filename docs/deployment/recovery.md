# Recovery and resumption

- Each browser-driven advance runs one bounded stage and persists its outputs, event, current stage, and version. Reopening a project reloads job state from the database.
- A job with a transient failure can be resumed with a new operation key. A completed operation key returns the saved job instead of running the stage twice.
- A stage lease is stored with an expiry and version; a stale lease can be reclaimed after its timeout. Provider calls cannot be guaranteed exactly once if a host dies after a provider accepts work but before the response is persisted.
- Pause is explicit and retains the current checkpoint. Cancel is terminal. A sleeping free web service does not run research in the background.
- Local development uses SQLite; production must use external PostgreSQL. No production database is configured or tested.
- PostgreSQL connection establishment and SQLAlchemy pool checkout have separate five-second defaults, configurable from 1–60 seconds. They do not bound SQL statement execution or every DNS/multi-host delay; see [ADR-0025](../architecture/ADR-0025-bounded-database-connection-waits.md). Readiness converts database failures to a sanitized 503.
- Before hosted use, perform a database export and restore drill outside the provider, then verify one fresh login, tenant isolation, migration, restart, pause/resume, quota exhaustion, and a second device.
- The operator steps for protected PostgreSQL logical backup and restore into an empty disposable `*_test` database are in [backup-restore.md](backup-restore.md). The runbook has not been executed; provider-specific RPO/RTO, retention, sleep recovery, and backup destination remain unknown.

## Archived-project retention

Users may select no automatic expiry or a 30-, 90-, or 365-day period. The timer starts when they next archive a project; restoring cancels its pending expiry. The maintenance command defaults to a read-only preview:

```powershell
cd backend
uv run --locked python -m app.maintenance.purge_expired_projects
```

After reviewing the preview and configuring a durable deployment scheduler, the scheduled invocation may add `--apply`. It deletes only archived projects whose `purge_at` has passed, in bounded batches. Before scheduling it against real user data, validate PostgreSQL row-lock behavior, deployment retries, timezone/clock assumptions, backup retention, and an export/restore drill. This repository does not configure or run a production schedule.

