# PostgreSQL backup and restore drill

**Status:** runbook prepared; not executed. This workspace has no PostgreSQL tools, database URL, managed database, or backup destination. No backup or recovery objective is currently verified. See blockers B-003/B-006.

## Safety boundary

- Use a user-controlled PostgreSQL service with TLS. Do not use Render Free Postgres for persistent user research: it expires and does not provide backups.
- Keep service definitions and passwords outside the repository. Treat custom-format dumps as sensitive user data; encrypt them at rest and in transit, restrict access, and apply an operator-approved retention policy.
- Restore only an archive produced by a trusted Veda database operator. PostgreSQL warns that restoring a dump executes SQL chosen by source-database superusers; do not restore an untrusted archive into any database.
- The restore drill below targets a **pre-created empty disposable database whose name ends in `_test`**. Never point it at production. Do not add `--clean`, `--if-exists`, or commands that drop/recreate a database.
- Create the disposable database from PostgreSQL's `template0` (or the provider's documented equivalent for a clean database), then verify it contains no user relations or extra schemas. `template0` avoids locally added `template1` objects that can collide during restore.
- Select and document RPO, RTO, retention, encryption-key ownership, and off-site storage before accepting persistent user data. This repository does not configure a scheduler or backup destination.

## Configure libpq credentials outside the repository

Install PostgreSQL client tools (`psql`, `pg_dump`, `pg_restore`) on the operator workstation. Create a protected service file and password file through the organization's secret-management process. The files should use the standard libpq formats:

```ini
# pg_service.conf: use the provider's actual TLS hostname, port and CA.
[veda_backup]
host=DB_HOST_FROM_PROVIDER
port=5432
dbname=VEDA_DATABASE
user=VEDA_BACKUP_ROLE
sslmode=verify-full
sslrootcert=PATH_TO_PROVIDER_CA

[veda_restore_test]
host=DB_HOST_FROM_PROVIDER
port=5432
dbname=VEDA_RESTORE_TEST_DATABASE
user=VEDA_RESTORE_ROLE
sslmode=verify-full
sslrootcert=PATH_TO_PROVIDER_CA
```

The service entries above are placeholders, not valid connection details. The restore-test database must be a separate, empty database ending in `_test`. Add matching password entries to a protected `pgpass.conf`; do not put passwords in the service file, command line, PowerShell history, or this repository. Apply ACLs so only the operator account can read the directory, then set the environment for the current PowerShell session:

```powershell
$secretDir = "C:\secure\veda-postgres"
icacls $secretDir /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F"
$env:PGSERVICEFILE = Join-Path $secretDir "pg_service.conf"
$env:PGPASSFILE = Join-Path $secretDir "pgpass.conf"
```

Use the provider's documented CA and hostname. Do not weaken certificate verification to work around an incorrect hostname or missing CA.

## Create and inspect a logical backup

Choose a local encrypted volume or an approved encrypted backup destination with sufficient free space. This example writes locally and leaves retention/removal to the operator.

```powershell
$backupRoot = "D:\VedaBackups"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$dumpPath = Join-Path $backupRoot "veda-$stamp.dump"
$tocPath = Join-Path $backupRoot "veda-$stamp.toc.txt"
$countsPath = Join-Path $backupRoot "veda-$stamp.source-counts.txt"

psql "service=veda_backup" -X -v ON_ERROR_STOP=1 -Atc "SELECT current_database(), current_user"
if ($LASTEXITCODE -ne 0) { throw "Could not verify the selected backup database." }

psql "service=veda_backup" -X -v ON_ERROR_STOP=1 -Atc "SELECT 'projects=' || count(*) FROM projects UNION ALL SELECT 'reports=' || count(*) FROM reports" | Set-Content -Encoding ascii $countsPath
if ($LASTEXITCODE -ne 0) { throw "Could not record source project/report counts." }

pg_dump --dbname "service=veda_backup" --format=custom --no-owner --no-acl --file $dumpPath
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed; do not treat the output as a valid backup." }

pg_restore --list $dumpPath > $tocPath
if ($LASTEXITCODE -ne 0) { throw "The dump could not be read by pg_restore." }
Get-FileHash -Algorithm SHA256 $dumpPath
```

Record the UTC time, database identity, source counts, dump size/hash, tool versions, operator, and backup destination in the approved operations record. Do not record a password or full connection URL. Use a `pg_dump` client at least as new as the database server major version and record both versions. A successful `pg_dump`/table-of-contents listing verifies file readability only; it does not prove recoverability.

## Restore into a disposable test database

Verify the service target and that it has no user relations or extra user schemas before restoring. Create it from `template0` through the provider's documented database administration process; do not issue `DROP DATABASE` or overwrite an existing database:

```powershell
$restoreDb = psql "service=veda_restore_test" -X -v ON_ERROR_STOP=1 -Atc "SELECT current_database()"
if ($LASTEXITCODE -ne 0 -or $restoreDb -notmatch "_test$") { throw "Restore target must be a reachable *_test database." }

$relationCount = psql "service=veda_restore_test" -X -v ON_ERROR_STOP=1 -Atc "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema' AND c.relkind IN ('r','p','v','m','S','f')"
if ($LASTEXITCODE -ne 0 -or [int]$relationCount -ne 0) { throw "Restore target has user relations; stop and choose a fresh *_test database." }

$extraSchemaCount = psql "service=veda_restore_test" -X -v ON_ERROR_STOP=1 -Atc "SELECT count(*) FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname NOT IN ('information_schema','public')"
if ($LASTEXITCODE -ne 0 -or [int]$extraSchemaCount -ne 0) { throw "Restore target has extra user schemas; stop and choose a fresh *_test database." }

pg_restore --single-transaction --no-owner --no-acl --dbname "service=veda_restore_test" $dumpPath
if ($LASTEXITCODE -ne 0) { throw "Restore failed; preserve the test database and inspect the operator logs." }
```

Do not add `--clean` or run this against a production service. Configure a temporary local backend environment to point `DATABASE_URL` at this same test database, then verify the current migration and API readiness:

```powershell
Set-Location backend
uv run --locked alembic current
uv run --locked python -c "from app.db import engine; from sqlalchemy import inspect; print(inspect(engine).get_table_names())"
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8011
```

In a second shell, request `http://127.0.0.1:8011/api/v1/health/ready`, compare restored project/report counts against the recorded source counts, and verify that a test account can sign in and read only its own data. Stop Uvicorn and remove the disposable test database only through the database operator's normal test-resource cleanup procedure. The command examples have not been executed in this environment.

## Operational recovery policy to establish

## Source references

- [PostgreSQL `pg_dump` documentation](https://www.postgresql.org/docs/current/app-pgdump.html): custom archives, version constraints, and the warning that restore executes SQL selected by source superusers.
- [PostgreSQL `pg_restore` documentation](https://www.postgresql.org/docs/current/app-pgrestore.html): archive listing, `--single-transaction`, and use of a truly empty database created from `template0` to avoid locally added template objects.

Before launch, configure recurring encrypted backups or provider snapshots plus an independent logical export, alert on missed backups, retain more than one recovery point, and run a scheduled restore drill into an isolated database. Document the measured restore duration and recovered record counts after the drill. Provider pause/sleep, database failover, backup deletion, retention and point-in-time recovery are provider-specific; verify each against the selected service. No RPO, RTO, backup cadence, retention period, or successful restore is claimed by this repository today.
