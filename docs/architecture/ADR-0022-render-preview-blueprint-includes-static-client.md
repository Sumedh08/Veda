# ADR-0022: Declare the API and static client together in the preview Blueprint

- **Status:** Accepted for local deployment preparation
- **Date:** 2026-10-29
- **Decision owners:** Veda engineering

## Context

The root `render.yaml` described a manually deployed API service, while the deployment runbook required the operator to create the static React/Vite site separately. That split left the frontend build, output directory, single-page routing, and build-time API/auth settings out of the machine-validated Blueprint. Veda needs a clear deployment package while external services remain unconfigured.

Render's official Blueprint reference defines static sites as `type: web` with `runtime: static`, a build command, and `staticPublishPath`; its monorepo guide says root-relative build and publish paths must match `rootDir`. A static bundle needs its API and auth URLs at build time, and a Render-assigned host is not known in this local workspace.

## Decision

Declare both the existing free API container and a `veda-web` static site in the root Blueprint. Build the frontend from `frontend/` using the locked npm install/build commands, publish `dist`, and rewrite client paths to `/index.html`. Prompt the operator for API and Supabase public configuration through `sync: false`; continue prompting the API operator for the exact frontend origin, database URL, and managed-auth verifier endpoints. Do not hardcode service hostnames, provision a database, add a provider key, or enable model spending. Disable automatic deploys on both services.

Extend the local Render schema/safety validator to require exactly these two services and verify free/manual API gates, static build/output/routing configuration, and non-hardcoded frontend settings. Keep the separately managed PostgreSQL, Supabase project, backup/restore drill, Docker execution, and external deploy as explicit operator/deployment gates.

## Alternatives considered

- **Keep static hosting entirely manual:** workable but leaves an essential half of the application outside infrastructure validation and easy to misconfigure; superseded.
- **Hardcode a guessed `onrender.com` API host:** rejected because host assignment/collision is external and build-time base URLs must be exact.
- **Enable or provision a database in the Blueprint:** rejected because a short-lived free database is not a durable storage plan; persistent use requires an independently managed PostgreSQL service and restore/export procedure.

## Consequences and limits

- The local Blueprint now expresses API and frontend as one reviewable package without provisioning or changing any external infrastructure.
- Blueprint synchronization prompts for the assigned URLs; a first deployment still requires manual review and explicit operator setup.
- No claim is made for image builds, Render behavior, managed auth, real CORS, persistent database, backups, HTTPS, or cross-device use.
- Render's current documentation supports the declared fields, but only the local schema validation was run.

## Verification

`backend/scripts/validate_render_blueprint.py` fetched Render's published JSON schema and passed schema plus repository preview-safety checks. The production frontend build passes separately. The Docker daemon is unavailable and no Render account/service or Git remote is connected, so no image, service, deploy, or hosted request was created.

## Primary documentation

- [Render Blueprint YAML reference](https://render.com/docs/blueprint-spec)
- [Render monorepo support and root-relative build paths](https://render.com/docs/monorepo-support)
- [Render infrastructure as code](https://render.com/docs/infrastructure-as-code)
