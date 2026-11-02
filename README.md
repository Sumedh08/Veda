# Veda

Veda is an evidence-tracking research workspace for questions about AI adoption, productivity, implementation and business decisions. This repository is the first implementation in progress. Its current maturity and verified behavior are tracked in [`docs/implementation-progress.md`](docs/implementation-progress.md) and [`evaluation/RESULTS.md`](evaluation/RESULTS.md).

## Local development

Requirements: Python 3.12 or newer, [uv](https://docs.astral.sh/uv/), Node.js 20 or newer, and npm. PostgreSQL is optional for local development; SQLite is used when `DATABASE_URL` is unset. Production mode fails closed unless an external PostgreSQL service, managed-auth verifier, HTTPS frontend origins and rate-limit hash secret are configured.

1. Copy `.env.example` to `.env` and set a fresh `DEV_AUTH_SECRET` for local use.
2. In `backend/`, run `uv sync --locked --extra dev`, then `uv run alembic upgrade head` and `uv run uvicorn app.main:app --reload`.
3. In `frontend/`, run `npm ci` and `npm run dev`.
4. Open the Vite URL shown by npm. The local sign-in button is available only when the backend explicitly enables development authentication.

The 66-row requirement matrix is [docs/implementation-inventory.md](docs/implementation-inventory.md); active work and external blockers are in [docs/implementation-backlog.md](docs/implementation-backlog.md) and [docs/blockers.md](docs/blockers.md). Research inputs, pinned repository snapshots, reuse decisions and known source gaps are in [docs/research](docs/research/). These records distinguish local fixtures from live integrations and research-quality evidence. Veda has an optional, bounded Crawl4AI Cloud public-web discovery route configured with `CRAWL4AI_KEY`; it has completed a live academic-publisher-to-passage/report/browser path. Non-ROR specialist and cross-sector publication discovery remains incomplete, so this does not establish comprehensive search. Keep the credential in the repository-root `.env` (ignored by Git); do not paste it into commands or logs. See T-140 in the evaluation and blockers for its limits.

## Verification

From `backend/`, run `uv run pytest -q`, `uv run ruff check .`, and `uv run ruff format --check .`. From `frontend/`, run `npm test`, `npm run build`, and `npm run test:e2e`. Browser E2E defaults to deterministic API fixtures. To additionally run the full browser suite with a real local API and freshly migrated disposable SQLite database, use PowerShell from `frontend/`:

```powershell
$env:VEDA_REAL_API_E2E = "1"
try { npm run test:e2e } finally { Remove-Item Env:VEDA_REAL_API_E2E -ErrorAction SilentlyContinue }
```

The real-API mode starts loopback-only development auth, disables all model credentials/providers, seeds clearly synthetic report/citation records, and removes the temporary database on orderly shutdown. It verifies browser-to-API persistence and citation inspection, not model research, scientific quality, managed auth, PostgreSQL, or deployment. Port 8001 is used by default; set `VEDA_REAL_E2E_API_PORT` to select another available loopback port.

An additional read-only live scholarly smoke is separately gated and excluded from routine E2E runs. It sends one non-sensitive generic quick query to Crossref and OpenAlex, keeps model providers disabled and budget at zero, and exercises the full local workflow/report path. Official-statistics requests now require both an explicitly statistical question and a user-supplied supported geography; this generic smoke asserts that Data360 receives no query. From `frontend/`:

```powershell
$env:VEDA_REAL_API_E2E = "1"
$env:VEDA_LIVE_SCHOLARLY_E2E = "1"
try { npx playwright test e2e/real-api.e2e.ts --grep "live scholarly/model smoke" --workers=1 } finally {
  Remove-Item Env:VEDA_REAL_API_E2E, Env:VEDA_LIVE_SCHOLARLY_E2E -ErrorAction SilentlyContinue
}
```

This opt-in contacts public Crossref/OpenAlex metadata APIs but makes no model call. By default it does not fetch full text. When `VEDA_EUROPEPMC_FULLTEXT_TARGET_DOI` is set, the workflow can retrieve Europe PMC JATS only after matching DOI/PMCID and a supported license preflight; OpenAlex content files are not downloaded. The persistent browser-test artifact option `VEDA_REAL_E2E_DATABASE_PATH` accepts only a new `.sqlite3` path inside repository `evaluation/` and refuses to overwrite existing data. This verifies only the observed provider/workflow/report path; search coverage, evidence quality and scholarly validity require separate review.

To repeat the T-136 model-disabled full-text report/browser smoke from `frontend/`, use a new timestamped database path:

```powershell
$env:VEDA_REAL_API_E2E = "1"
$env:VEDA_LIVE_SCHOLARLY_E2E = "1"
$env:VEDA_REAL_E2E_DATABASE_PATH = Join-Path (Split-Path (Get-Location).Path -Parent) ("evaluation\veda-fulltext-smoke-" + (Get-Date -Format "yyyyMMddTHHmmss") + ".sqlite3")
$env:VEDA_LIVE_SCHOLARLY_QUESTION = 'What does the study "Soil bacterial networks are less stable under drought than fungal networks" report about bacterial versus fungal network stability? What methods, results, and limitations support this comparison? DOI 10.1038/s41467-018-05516-7.'
$env:VEDA_EUROPEPMC_FULLTEXT_TARGET_DOI = "10.1038/s41467-018-05516-7"
try { npx playwright test e2e/real-api.e2e.ts --grep "live scholarly/model smoke" --workers=1 } finally {
  Remove-Item Env:VEDA_REAL_API_E2E, Env:VEDA_LIVE_SCHOLARLY_E2E, Env:VEDA_REAL_E2E_DATABASE_PATH, Env:VEDA_LIVE_SCHOLARLY_QUESTION, Env:VEDA_EUROPEPMC_FULLTEXT_TARGET_DOI -ErrorAction SilentlyContinue
}
```

The smoke requires public network access. The target study was retrieved from Europe PMC with matching DOI/PMCID and CC-BY metadata. The saved report is deterministic and limited with zero model calls; it demonstrates acquisition, persistence, citation and browser inspection only. Run-specific evidence is in [`evaluation/t136-europe-pmc-fulltext-smoke-2026-11-01.md`](evaluation/t136-europe-pmc-fulltext-smoke-2026-11-01.md).

The OpenRouter research validation runner is a historical, separately gated tool. Configure a currently authorized `OPENROUTER_API_KEY` only in the ignored repository-root `.env` or the local backend process; never commit the credential or place it in command text or logs. From the repository root:

```powershell
$env:VEDA_OPENROUTER_LIVE_E2E = "1"
try { uv run --locked --directory backend python scripts/run_openrouter_research_validation.py } finally {
  Remove-Item Env:VEDA_OPENROUTER_LIVE_E2E -ErrorAction SilentlyContinue
}
```

The one-question runner repeats a read-only public model/endpoint preflight and pins `xingchen-agi/xing4.0-29b-a4b:free`; it stops before inference when the local credential is unavailable. It uses one fixed developer-productivity question, isolated SQLite, loopback development auth, a six-request hard cap, zero paid fallback, zero provider retries, an explicit reasoning-off parameter, and zero prompt/completion/request price ceilings. OpenRouter currently publishes limits of 20 requests/minute and 50/day for `:free` variants on an unfunded account; failed attempts count toward the daily cap, so Veda disables retries. Missing request-price metadata, account tier/remaining allowance and account-level billing remain unknown. It records the exact route, stage results, usage/cost completeness and browser report/citation inspection without saving the key or raw provider response. This run sends the research question and retrieved public evidence to OpenRouter, Crossref and OpenAlex; do not use it for confidential research. A completed workflow verifies integration only. Human evaluation is still needed to judge source relevance, unsupported claims, counterevidence and scientific quality. The previous T-112 one-time authorization has been used; any new inference run requires separate authorization.

### T-126 Sarvam GLM-5.3 Flash validation

The one-time T-126 live validation completed successfully with Sarvam `glm5.3-flash`. The persisted report and detailed source-quality review are linked from [`evaluation/RESULTS.md`](evaluation/RESULTS.md) and [`evaluation/t126-live-report-quality-review-2026-10-31.md`](evaluation/t126-live-report-quality-review-2026-10-31.md). The report is operationally model-assisted, but has material source-coverage and semantic-support limitations; it is not an independent scientific validation or a production-readiness claim.

The report is persisted in `evaluation/veda-sarvam-glm-20261030T211603703874Z.sqlite3`; the T-126 runner launched the local API/browser and inspected it during that run. The standard local UI commands above use the default development database and do not load this isolated evaluation database. The one-time inference authorization has been used. A new live AI run must not be started until a separate spend ceiling is authorized. After that authorization, from `backend/`, the bounded runner entry point is `uv run --locked python scripts/run_sarvam_glm53_research_validation.py --execute-live --billing-confirmed`; it pins `glm5.3-flash`, checks cumulative reservations, and launches the isolated SQLite/API/browser workflow.

## Research and safety

Research uses persisted, bounded steps. In the absence of configured AI credentials, Veda may still create plans and discover public scholarly metadata. OpenAlex/OpenAIRE affiliations can reveal previously unregistered research organizations; exact ROR identities are checked before an organization is described as verified, and this identity check does not assess publication quality. Veda also has a bounded metadata-only World Bank Documents & Reports connector. It dispatches only when `WORLD_BANK_DOCUMENTS_NONCOMMERCIAL_USE_CONFIRMED=true` is set by the operator, because the current API use terms restrict API-facilitated use absent permission to non-commercial purposes. The connector does not fetch files or infer reuse rights. World Bank Data360 WDI is queried only when the research question matches a supported statistics topic and the user supplied an explicit supported geography. The single global ILOSTAT employment series requires an employment question and an explicitly supported World scope. Statistics are stored separately as descriptive observations, not study or causal estimates. Search coverage records each optional statistics route as searched, not applicable with a bounded reason, not attempted, or gated; result counts and provider failures remain separate. Older reports state that conditional routing was not recorded rather than inferring an outcome. ILOSTAT live availability and per-release rights are not verified in this environment; see the implementation ledger. Veda discloses where model-assisted appraisal or synthesis did not run. Provider usage and estimated cost are tracked separately. No paid API calls are made by default.

Planning combines a deterministic scope-and-safety scaffold with an optional quota-aware structured model selection from a fixed candidate-query set. It cannot rewrite the user's scope or remove counterevidence searches; if the provider is unavailable or output is invalid, the saved plan records its deterministic fallback. The saved method and provider/model provenance are shown in the workspace. This path has fixture coverage; live planning output and research quality remain unverified.

The Preferences and data panel supports a full owner-scoped Veda-data export and a separate exact-phrase purge of Veda-stored projects, research records and preferences. The purge is blocked while a research lease is live and preserves that UTC day's quota safety counter. It does not delete the managed sign-in identity, identity-provider records or operator-held database backups; see [ADR-0008](docs/architecture/ADR-0008-owner-data-export-and-project-purge.md) and [ADR-0029](docs/architecture/ADR-0029-explicit-veda-data-purge.md).

The user-supplied build package and working research-run artifacts are kept outside this public source snapshot. Current product requirements, architecture decisions, source-verification notes, and implementation status are maintained in `docs/`; research leads remain distinct from verified evidence.

## Deployment

Local deployment preparation is recorded in [`docs/deployment/render.md`](docs/deployment/render.md), with a root `render.yaml` that describes a free API and a static frontend and creates no database. Both services disable automatic deploys and require operator-supplied API/auth URLs; neither the Blueprint nor container has been validated by Render or Docker, and no external service has been provisioned. Persistent use requires a separately managed PostgreSQL database, configured Supabase auth, HTTPS frontend/API origins, and a verified backup/restore drill. The operator procedure for PostgreSQL export and isolated restore is [docs/deployment/backup-restore.md](docs/deployment/backup-restore.md); it has not been run because no PostgreSQL service or credentials are available.

