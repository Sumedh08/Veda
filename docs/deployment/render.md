# Render deployment preparation

**Status:** local preparation only; no Render service, external database, or auth project has been created and no deployment has been run. The root [`render.yaml`](../../render.yaml) describes one **free API service** and one **static frontend**. It deliberately creates no database, stores no provider key, disables automatic deploys for both services, and has no paid model provider enabled. Review every Blueprint change in the Render Dashboard before provisioning.

Render's current free web services are for testing/preview, sleep after 15 minutes idle, use ephemeral local filesystems, and may be suspended on quota limits. Free Postgres expires after 30 days and has no backups. Do not store real Veda research in Render Free Postgres. Use an independently managed PostgreSQL database with TLS and an independently held export/restore procedure before any persistent-user preview; paid production readiness still requires a restore drill and service review. The provider-neutral operator runbook is [backup-restore.md](backup-restore.md); it is prepared but has not been executed. [Render free-tier limitations](https://render.com/docs/free)

## Backend container

From the repository root, build the API image with `docker build -f backend/Dockerfile -t veda-api backend`. Runtime and uv builder images are pinned by multi-platform manifest digest; Python runtime packages are installed from `backend/uv.lock` with `--locked` (the project wheel itself is not copied into the runtime image). The final image runs as UID/GID 10001 and has an HTTP liveness check. Its `/tmp/veda.db` default is for disposable local container smoke use only; `APP_ENV=production` rejects SQLite, requires PostgreSQL, a configured managed-auth verifier, and HTTPS frontend origins. The Docker command applies Alembic migrations before starting Uvicorn, and Render readiness is `/api/v1/health/ready`. The Docker daemon was unavailable during local verification, so these image-level properties and startup behavior have not been container-executed.

The Blueprint pins the service to Render's free compute and sets `autoDeployTrigger: off`. Render's pre-deploy command is only available on paid web services; the current single-instance preview therefore migrates at startup. For a paid, multi-instance deployment, move migration execution to a controlled pre-deploy/one-off release step and prove migration serialization before enabling multiple instances. PostgreSQL connection establishment and SQLAlchemy pool checkout default to five seconds each; set `DATABASE_CONNECT_TIMEOUT_SECONDS` or `DATABASE_POOL_TIMEOUT_SECONDS` from 1–60 seconds when the network and service plan require different bounds. These settings do not impose a general statement/request timeout, and multi-host DNS/connection attempts may extend total elapsed time. See [ADR-0025](../architecture/ADR-0025-bounded-database-connection-waits.md). [Render Blueprint fields](https://render.com/docs/blueprint-spec), [pre-deploy command limits](https://render.com/docs/deploys)

## Environment and bootstrap order

Create and configure the managed PostgreSQL database and Supabase auth project before starting the API service. The Blueprint includes both API and static client. Supply the exact assigned static HTTPS origin in the API's `FRONTEND_ORIGINS`, and set the static build's `VITE_API_BASE_URL` to the API service's HTTPS URL ending in `/api/v1`. The Blueprint's `sync: false` entries prompt for `DATABASE_URL` (external PostgreSQL), `FRONTEND_ORIGINS`, `SUPABASE_URL`, `SUPABASE_JWKS_URL`, `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_ANON_KEY`. These build-time values are necessary because a static bundle cannot discover its API/auth origins at runtime. The Supabase anon key is public client configuration; provider service keys must never be supplied to the static site. Production startup intentionally fails when any durable-database/auth/CORS prerequisite is missing or insecure. Keep `DEV_AUTH_ENABLED=false`, `LLM_PROVIDER=disabled`, and `ALLOW_PAID_LLM_CALLS=false` until a separately authorized provider review. Review `MAX_REQUEST_BODY_BYTES` and all `RATE_LIMIT_*` values for expected traffic. The generated `RATE_LIMIT_HASH_SECRET` is used only for identity hashing.

## Static client

The Blueprint's `veda-web` static site is rooted at `frontend/`, runs `npm ci && npm run build`, publishes `dist`, and rewrites client paths to `index.html`. Its `VITE_*` settings are supplied at build time. The application bundle contains the Supabase anon key and API URL; these are public client settings, while model-provider credentials stay server-side. The build output and routing declaration have passed local TypeScript/Vite and Render-schema checks, but no Render build or hosted browser has run. The declaration follows Render's official [Blueprint static-site fields](https://render.com/docs/blueprint-spec#static-sites) and [monorepo root-directory rules](https://render.com/docs/monorepo-support).

## Final checks before a user-facing deployment

1. Apply migrations to a fresh Postgres database and verify readiness.
2. Configure auth issuer/audience and test two distinct users against project and nested-resource endpoints.
3. Test frontend CORS from its real HTTPS origin.
4. Verify export/restore and quota behavior with non-sensitive test data.
5. Verify sleeping-instance cold start, client pause/resume, and report export from another device.
6. Do not describe deployment as complete until remote HTTPS has actually been tested.

No Git repository is connected in this workspace. Render requires a linked Git provider/repository for Blueprint deployment; adding this file has not created or deployed anything. The Blueprint's initial deploy is a manual Dashboard action; automatic deploys are disabled. [Render Blueprint setup](https://render.com/docs/infrastructure-as-code)

