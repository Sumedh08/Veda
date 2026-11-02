# ADR-0007: Local runtime and resource baseline

- **Status:** Accepted as a developer-machine baseline only; hosted capacity is unverified.
- **Date:** 2026-10-29
- **Decision owners:** Veda engineering

## Context

ADR-0001 selected a small modular monolith but listed measured startup, memory, and test/runtime behavior as open evidence. This record captures one repeatable local sample and the commands used. It does not estimate container capacity, production concurrency, or PostgreSQL behavior.

## Measured environment and results

Run `scripts/benchmark_local_architecture.ps1` from the repository root. It allocates free loopback ports, starts the API and Vite development server as hidden local processes, polls each HTTP endpoint, samples the launched process family, and terminates the processes it started. Process-family memory excludes `conhost.exe`; samples are taken every 100 ms for two seconds after readiness. This is sampled working set, not kernel peak.

| Component | Readiness probe | Time to HTTP 2xx | Sampled process-family working set |
|---|---|---:|---:|
| FastAPI + Uvicorn | `/api/v1/health/live` | 4.37 s | 98.7 MiB |
| Vite development server | `/` | 1.80 s | 159.9 MiB |

The recorded host was Windows 11 Home Single Language (10.0.26200), Python 3.13.4, Node 22.16.0, npm 10.9.2, 8 logical processors, and 7,927 MiB visible physical memory. The API command starts the local development configuration and the probe uses the liveness endpoint; database query latency, migrations, auth-provider latency, and model-provider latency are excluded.

Software verification on the same worktree:

| Workload | Result | Boundary |
|---|---|---|
| `uv run --locked python -m pytest -ra` | 208 passed, 2 skipped, 36.31 s | SQLite/local fixtures; the two PostgreSQL integration tests were skipped because `VEDA_TEST_POSTGRES_URL` is unset. |
| `uv run --locked python -m pytest -ra tests/test_depth_profiles.py tests/test_retrieval_workflow.py tests/test_safe_fetch.py` | 33 passed, pytest 1.29 s; command elapsed 7.17 s | Deterministic bounded retrieval, hostile transport, and depth-profile fixtures; no scholarly host was contacted. |
| `npm test -- --run` | 13 passed, 0.744 s | Frontend unit tests. |
| `npm run build` | Passed; Vite build 9.09 s | TypeScript production build; excludes browser startup and deployment. |
| `npx playwright test --workers=1` | 36 passed, 2.1 min | Fixture-backed Chromium journeys including download filename handling, project lifecycle, evidence inspection, accessibility, and responsive views. |

The machine-readable sample is `docs/architecture/local-resource-baseline-2026-10-29.json`. Timings and memory are one local observation, not a performance guarantee. Following T-37, the retention preferences and maintenance command were added after this recorded runtime suite; T-37 has its own focused verification.

## Decision and migration triggers

Keep the current Python API, browser-stepped workflow, and static TypeScript client as one small deployment unit for now. The observed local footprint is modest on this host, and current test evidence does not justify adding a graph framework, independent queue, or service split. Do not infer production capacity from this result.

- Use PostgreSQL before any remotely hosted, multi-user deployment or more than one API worker; validate migrations, leases, quota races, and restart recovery against a disposable PostgreSQL service first (T-09/T-12).
- Add a durable background worker when product behavior must continue without a user/browser request or when a supported host cannot keep the API process awake for the bounded stage execution model.
- Split API and worker processes, or resize the target container, if representative hosted load shows repeated peak process-family memory above 80% of the selected memory limit, or the host records an out-of-memory restart. Measure under the target concurrency before making the change.
- Revisit a graph orchestrator only after real workflow requirements introduce parallel/conditional branches and a comparative spike shows the persisted stage state machine causes duplicated recovery logic or fails restart acceptance.
- Revisit local startup optimization if cold-start measurements on the actual host repeatedly exceed its published request-startup or health-check window. This machine's 4.37-second API start is not that host measurement.

## Consequences and remaining work

The chosen architecture remains appropriate for local development and deterministic fixture tests. Production storage, multi-worker transaction semantics, durable scheduled retention, auth configuration, deployment health checks, and human-reviewed research quality remain open. See T-09, T-12, T-17/T-30, T-37/T-51, and T-38.
