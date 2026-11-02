# Evaluation and verification results

Updated 2026-11-02 through T-140. The earlier verification entries are historical snapshots. This ledger separates local software checks, synthetic metric-logic fixtures, earlier failed T-112/T-119/T-123 attempts, the successful real Sarvam GLM-5.3 Flash workflow, and actual research-quality evaluation. **The T-126 workflow passed operationally; no Veda research output has an expert-reviewed quality score.**

## Current local verification

| Check | Result | Establishes | Does not establish |
|---|---|---|---|
| Backend pytest -ra --tb=short | **392 passed; 2 PostgreSQL integration tests skipped** after T-103/T-104/T-106/T-107. One existing Starlette/httpx deprecation warning remains. | Local API, workflow, recovery, report persistence, schema, security, provider fixtures, retrieval and checkpoint contracts | PostgreSQL-only behavior remains skipped; no research-quality claim follows. |
| Backend Ruff format/check | Whole-backend formatting and static checks passed after T-103–T-107 (125 files formatted). | Static/format coverage for Python application, tests, scripts and migrations | Runtime/security review beyond covered checks |
| `python scripts/verify_migration_roundtrip.py` from `backend/` | Passed fresh SQLite upgrade, downgrade, re-upgrade and Alembic consistency check; no migration was needed for T-54–T-58 | Local SQLite migration chain and schema consistency; these remain JSON/contract changes | PostgreSQL migrations, lock semantics, backup/restore; developer's pre-existing local default DB was not migrated |
| Frontend npm test -- --run | **3 files / 21 tests passed** including free-route audit semantics. | API and browser unit contracts | Managed sign-in and live model quality |
| Frontend `npm run build` | Passed | TypeScript project build and Vite production bundle | Deployment and runtime API connectivity |
| Browser UI `npx playwright test --workers=1 --timeout=60000 --reporter=line` | Full suite **40/40**; after adding schema-v1 report contract fields to the browser fixtures, the report citation/history journeys passed again **3/3** | Actual Vite/React UI with deterministic API fixtures, including report inspection/history/export, axe A/AA/mobile/focus checks, T-46/T-47 history/recovery, T-53 outcomes, T-54/T-55 versioned records/metrics, T-56 source metadata compatibility, and T-44 exact claim spans | Fixture routes do not validate real-backend browser integration, managed Supabase auth, PostgreSQL, or provider-backed output |
| Dependency audits | `npm audit --audit-level=high`: 0 vulnerabilities; `uv export --locked --extra dev --no-emit-project --format requirements-txt` + `uvx --from pip-audit pip-audit -r .audit-requirements.txt`: no known vulnerabilities after pytest 8.4.2 was replaced by 9.2.0 | Locked frontend and all backend runtime/development dependencies were audited | Future advisories, full supply-chain provenance, Git history scanning, and observed CI execution |
| `python scripts/validate_research_audit.py` from `backend/` | Passed: 28 papers / 23 repositories, all fields populated, pinned SHA and per-entry audit/decision coverage | Evidence ledger is complete for the bounded sources and explicitly records unknowns | Does not expand access to unavailable papers or turn license metadata into legal clearance |
| `python scripts/validate_render_blueprint.py` from `backend/` | Passed against the current official Render Blueprint schema and local free-only safety guards | Blueprint syntax/configuration shape and prohibited-resource checks | No Docker image, Render account, database/auth service, deployment or HTTPS run was performed |
| Cost scenarios | `python scripts/calculate_cost_scenarios.py` and `tests/test_cost_model.py` pass | Deterministic planning and enforced-budget scenarios at 10/100/1,000 jobs plus 1x/2x/5x prices; no provider calls | Price may change; token counts and input caps are estimates, not measured spend |
| Postgres CI workflow | YAML parses; `.github/workflows/quality.yml` includes PostgreSQL 16 service and guards | CI checks are defined without provider credentials | CI was not triggered: no `.git` repository/remote; no Postgres service result is claimed |
| `python scripts/validate_evaluation_registry.py` | Passed: 36 draft cases, 0 gold answers | Registry schema, count, statuses and absence of fabricated answers | Any answer correctness or research-quality metric |

## Synthetic fixture metric logic (T-16)

`python scripts/evaluate_fixtures.py` passes deterministically on one explicitly synthetic fixture case. The runner rechecks its expected counts and outputs the registry's draft/gold status separately. Its report states `scientific_quality_scored: false`, `provider_calls: 0`, `database: none`, and `human_review_results: none`.

| Metric logic exercised | Fixture result | Meaning |
|---|---:|---|
| Passage-support label comparison | 2/3 | One intentionally mismatched synthetic label is detected |
| Citation-link integrity | 3/4 | One invalid synthetic citation ID is detected |
| Material-claim coverage | 3/4 | One expected synthetic material item is omitted |
| Material-claim citation coverage | 2/3 | One included synthetic material item lacks a valid evidence citation |
| Scope-field coverage | 3/4 | One expected synthetic scope field is absent |
| Scope-safe relationship classification | 4/5 | One synthetic contradiction is incorrectly retained across different scope |
| Competing-hypothesis evidence disjointness | 1/3 | Two synthetic pairs reuse claim evidence |
| Provider-call budget compliance | 2/3 | One synthetic call exceeds its declared ceiling |

These rates validate metric calculation and defect detection in the runner only. They are not Veda scores and must not be compared with human-reviewed work. The 36 draft AI-economics questions remain unscored, with `gold_answer: null`.

## T-35/T-36 security and browser acceptance (2026-10-29)

- The non-uploading secret scanner checked **141 text files, 0 findings**. Detection, output redaction, placeholder filtering, reasoned suppressions, generated/binary exclusions and oversized-text fail-closed cases pass. The GitHub Actions YAML parses and runs the scanner before dependency installation; Actions itself was not triggered.
- Mocked adversarial passage content traverses appraisal, comparison, report synthesis and semantic audit while remaining under the untrusted-content boundary. Local CORS allow/deny, auth error sanitization, security headers on success/422/413, and spoofed forwarded-IP behavior pass.
- Protected API 401 now clears stale local/managed identity; browser coverage verifies the expired local session returns to sign-in. This does not validate Supabase's real callback/refresh flow.
- Full Playwright is **15/15** on the actual Vite/React browser with deterministic API fixtures. It covers project lifecycle, paged conversation/follow-up, comparisons/hypotheses, keyboard evidence activation, modal initial focus/trap/restoration, and responsive views. axe A/AA reports zero violations on report, source inspector and comparison screens. These fixtures do not claim live backend or provider behavior.
- T-35/T-36/T-44/T-45/T-46/T-47 are DONE at their stated local or fixture-backed boundaries. T-47's eight targeted journeys pass; the full browser suite is 33/33. No real-backend browser or managed-auth journey was run.

## T-46/T-47 report history and dashboard recovery (2026-10-29)

- Report history uses the owner-scoped history API and archived-safe inspection bundle; browser fixtures verified selected-report citations/source passages and exact export ID, project/archive filtering, immutable report-schema version wording, stable bounded next/previous counts, empty state and retry after a report-list 503.
- T-47 covers announced no-match search; dashboard project-list loading, error and retry; project conversation/run collection loading, separate failure messages, preservation of the collection that succeeded, retry, and accurate empty-state messaging. axe A/AA and 360px overflow checks pass for failure and empty screens.
- Verification: full backend suite **159 passed, 2 PostgreSQL-only skipped**; frontend Vitest **2 files / 11 tests**, production build passed, touched backend Ruff passed; full Playwright **33/33** passed; local secret scan **146 text files, zero findings**. Playwright APIs are fixtures. No managed Supabase, real-backend browser, PostgreSQL, or provider call occurred.

## T-38 benchmark protocol preparation and T-43 plan v2 (2026-10-29)

- T-38 now has `evaluation/benchmark-plan.json` (fixed seven-case purposive pilot), a strict v1 annotation JSON Schema, an explicitly unreviewed schema fixture, and a validator. The cited candidate-source note records study design, sample, intervention/comparator, outcomes, scope, version/access and rights limits for the mapped primary literature. The candidate list is not the final source set; it is not a gold answer. The metric protocol names numerators/denominators, two independent reviews, adjudication, missingness and same-source reuse.
- T-38 checks: `uv run --locked python -m pytest -q tests/test_annotation_records.py tests/test_benchmark_plan.py tests/test_evaluation_runner.py` passed **9 tests**; `validate_benchmark_plan.py`, `validate_annotation_records.py`, and `validate_evaluation_registry.py` pass. The registry remains 36 draft cases, zero gold answers. No Veda benchmark job, human annotation, or research-quality score exists.
- T-43 plans are strict version 2, deterministic/no-model, owner-protected and saved in the checkpoint. They include user-supplied decision fields, explicit missing scope, query-by-query rationale, subquestions, a counterevidence query retained under quick-depth caps, and search-stop/abstention/incomparability criteria. The actual UI shows the saved scope and reasons. It does not infer a missing scope or claim evidence-type filters that providers did not apply.
- Verification: full backend **171 passed, 2 PostgreSQL-only skipped**; Ruff check/format passed; fresh SQLite migration roundtrip and Alembic consistency passed; frontend Vitest **2 files / 13 tests**, production build passed, full Playwright **33/33** passed; after adding dedicated plan-screen axe A/AA and 360px assertions, the focused research/create journey passed **1/1**. These checks establish local code/UI contracts only. No provider call, PostgreSQL, managed auth, deployment or research-quality score was run.
- Master-spec re-audit found counterfactual/comparator, possible-outcome/denominator, and confounder/selection analysis still implicit in general subquestions. This remains mapped to T-48; T-43's narrower acceptance is complete.

## Provider and retrieval runs

- **World Bank Data360 (2026-10-29):** an earlier read-only live metadata/value check against the WDI population indicator returned a CC BY-4.0 license and UN Population Division contributor; the World observation included period/value/unit/status fields. T-28 later resolved the official World Bank country API entry `India` → `IND` and made one read-only Data360 lookup; the returned row echoed `REF_AREA=IND`, had a CC BY-4.0 series license, and reported an observation for 2022. The broad search text `world population` surfaced a multidimensional-poverty headcount indicator whose title contains “population.” This is evidence of an unresolved topical relevance problem, not a successful research-quality assessment. These calls validate connectivity, code resolution and response mapping only; they are not an E2E Veda job, truth/correctness review, broad licensing clearance, or evaluation metric. Fixtures cover license gating, aggregate/ambiguous geography, malformed/mis-scoped values, response bounds and independent failure; the browser inspector uses deterministic fixtures.
- **T-27/T-28/T-29 local acceptance (2026-10-29):** latest backend full suite 127 passed / 2 skipped (loopback PostgreSQL service unavailable), Ruff passed, fresh SQLite migration round-trip/Alembic check passed, frontend 2 files/9 tests and production build passed, and Playwright passed 8/8 serially. T-29 adds an engine/client reopen, pause/resume, report citation, linked follow-up and browser refresh journey. An earlier concurrent run hit the spawned-process quota barrier; the isolated race test and full serial backend rerun passed. No model provider was called; no OpenRouter key was used.

- **T-31 API/pagination/timing acceptance (2026-10-29):** backend full suite 128 passed / 2 PostgreSQL-only skips; Ruff format/check and fresh SQLite migration roundtrip/Alembic consistency passed; frontend 2 files/10 tests and production build passed. Report history and collection pages are owner-scoped and bounded; provider query and stage timing are persisted. No Playwright suite, full model-backed job, PostgreSQL server, or deployment was exercised by this task.

- **T-32 retry/normalization acceptance (2026-10-29):** provider and workflow tests use MockTransport/fixtures only. The final backend suite passed 140 / skipped 2 PostgreSQL-only tests; Ruff format/check and fresh SQLite migration roundtrip/Alembic consistency passed. One safe GET retry and provider-classified model 429 retry are bounded; schema-invalid model output remains no-resend/uncertain. One complete Markdown fence is the only automatic response repair, and its marker persists/replays from the usage ledger. No live provider call or charge occurred.

- **T-33 typed facets and conditional synthesis (2026-10-29):** appraisal/report draft schema v2 adds exact-claim-passage economic facets and scope/evidence gates for conditional implications. Report numeric tokens are screened against linked claim text. Official-statistic facet values are deterministic transcriptions and remain labeled descriptive. Accepted implications are included in a separate semantic passage audit and rendered in the actual browser fixture. Backend pytest passed **143 / skipped 2 PostgreSQL-only tests**; Ruff passed; frontend **10 unit tests**, production build, and Playwright **8/8** passed, including axe A/AA after a contrast correction. These are structural/fixture results only: no live model report, human review, causal-quality score, PostgreSQL run or external deployment is claimed.

- **OpenRouter:** a historical adapter-only smoke request on 2026-10-28 returned one structured output with reported usage of 49 input / 17 output tokens, $0.00 reported cost and 3245 ms latency. It did not run a Veda research job or exercise scholarly retrieval, appraisal, comparison, citation audit, persistence, or final synthesis. The credential was later posted in conversation and must be rotated before reuse. The environment presence check on 2026-10-29 found no `OPENROUTER_API_KEY`; this continuation made no provider request and did not reuse the exposed key.
- **OpenAI:** no live request was made. The adapter has fixture coverage; the user's planned later test is deferred. No paid API charges were incurred in this continuation.
- **Crossref and OpenAlex:** adapter, normalization, retrieval and failure behavior are fixture-tested. No live scholarly API call is claimed for the current end-to-end workflow.

## Research-quality status and limits

- A seven-case pilot and candidate primary-source mapping now exist, but no draft case has a reviewer-validated primary-source set or gold answer. See `benchmark-plan.json` and `../docs/research/ai-work-economics-evidence-sample-2026-10-29.md` for access/version gaps.
- No human source-to-passage audit, omission review, causal interpretation review, contradiction/heterogeneity review, calibration study, or matched baseline run has been completed.
- No full OpenRouter research job has been run. Live research output quality therefore has not been evaluated.
- The annotation fixture is `not_reviewed`, with null run/reviewer metadata and null scores; it is excluded from all human denominators. No qualified independent reviewers or real annotation records are present in this workspace (B-010).
- Model-assisted appraisals, comparisons, hypotheses and semantic citation judgments remain provisional even when their structural fixtures pass.
- The bounded conversation follow-up uses lexical overlap as a planning hint; the heuristic itself has no semantic-relevance evaluation.

## Environment blockers

- PostgreSQL, managed auth, durable hosted storage, backup/restore, HTTPS deployment and Docker image build are unverified because no database/cloud credentials or Docker daemon are available; see `../docs/blockers.md` B-003–B-006.
- Representative browser report/citation inspection, local sign-in/project/research/resume flow, keyboard activation, 360px layout, and report/inspector A/AA scans are now verified with the Playwright harness (T-13). Its API routes are fixtures. Managed Supabase auth, a real-backend browser run, and app-wide accessibility remain unverified; see B-004 and inventory M-43/M-48.
- The exposed OpenRouter credential cannot be reused. A rotated key must be safely configured before T-17; do not copy keys into the repository or this results file.

## Next evaluation work

1. Continue T-19's post-build audit across all 66 requirements. Current ledger: 49 residual requirements across 63 tasks (54 DONE, 3 IN_PROGRESS, 5 BLOCKED, 1 DEFERRED); T-19 selected T-63 to expose the existing source/claim methodological appraisal and exact passage provenance in the browser inspectors. T-38's protocol is prepared, but real Veda runs and independent review remain pending.
2. Run a complete free-model Veda job only after the exposed credential has been revoked/rotated and the replacement is safely configured; record provider/model, source retrieval, every persisted stage and actual usage separately from quality claims (T-17/T-30).
3. Only after human source review, publish reviewed-case scores with reviewer protocol, sampling, denominators, exclusions and disagreement; keep draft cases separate.

## 2026-10-29 implementation verification (T-60)

- The complete local backend suite passed **308 tests**, with **2 PostgreSQL-only tests skipped** because no disposable PostgreSQL URL is available; one Starlette/httpx deprecation warning remains.
- Full frontend fixture/browser suite passed **40/40**; Vitest passed **13/13**; production TypeScript/Vite build passed. These browser API responses are deterministic fixtures, not a real-backend or hosted run.
- Whole-backend Ruff format/check passed for **104 files**. A fresh SQLite migration upgrade/downgrade/re-upgrade passed and Alembic detected no new operations.
- The implementation-backlog validator passed for **66 requirements, 50 residuals, 60 tasks**. Benchmark (7 draft cases), annotation (1 `not_reviewed` fixture), evaluation (36 draft cases), render-blueprint and research-ledger validators passed. None constitutes a quality score or human review.
- No live OpenRouter request was made in this continuation. The earlier one-request adapter smoke is not a full research job; its exposed credential remains unusable pending rotation. No OpenAI request was made. No PostgreSQL runtime, human research-quality evaluation, legal clearance or deployment is claimed.

## 2026-10-29 implementation verification (T-61)

- Added bounded structured planning that selects query indices only from the deterministic candidate set and may add at most two analytical questions. Scope, analytical lenses, evidence/counterevidence requirements, stop rules and resource limits remain fixed. Plan v4 records applied model-selection or deterministic-fallback provenance; checkpoint v2/v3 reads and stable API fields remain supported. The browser shows the actual saved method and provider/model when known. See `../docs/architecture/ADR-0019-bounded-model-assisted-planning.md`.
- Focused planner/depth/checkpoint tests: **29 passed**. Full backend: **315 passed, 2 PostgreSQL-only skipped**. A first run concurrent with four Playwright workers had one spawned-process SQLite quota timeout; the isolated race passed and the clean full backend rerun passed. Whole Ruff passed; Vitest **13/13**, production TypeScript/Vite build and full Playwright **41/41** passed.
- At the T-61 checkpoint, no live OpenRouter request had occurred because `OPENROUTER_API_KEY` was not configured for that process; the earlier adapter smoke was not a Veda research run. The later one-time ten-case attempt is documented under T-102. No live plan-quality score or human review exists.
- T-19 continued the requirement audit and selected T-62 for one bounded read-only OpenAlex/Crossref adapter call, independent of OpenRouter credentials. PostgreSQL, managed auth, durable cloud hosting, backup/restore and external deployment remain unverified or blocked; Veda is not complete.

## 2026-10-29 live scholarly adapter check (T-62)

- One read-only query (`AI adoption small business productivity`, limit 2) was sent through each existing provider adapter with no API credentials. OpenAlex returned 2 records and Crossref returned 2; all 4 passed strict `ScholarlyWorkRecordV1` validation, zero invalid records. No results were persisted.
- Crossref's first-party REST documentation confirms the public `/works` API requires no signup. The OpenAlex documentation URL redirected to a help subdomain inaccessible to the research tool; the endpoint itself responded successfully. Exact evidence and limits are recorded in `../docs/research/scholarly-adapter-live-check-2026-10-29.md`.
- This verifies current endpoint connectivity and normalization for one bounded query. It does not measure recall, relevance, record accuracy, reliability, source rights, full-text access, or research quality. No full Veda job or model call occurred.
- T-19 marked M-06 VERIFIED COMPLETE at the OpenAlex/Crossref adapter boundary and removed it from the residual crosswalk. The audit next selected T-63 for the locally actionable methodological-appraisal display gap; expert review remains unavailable under T-38.


## 2026-10-29 implementation verification (T-63/T-64)

- T-63 source/claim methodological appraisal panels are fixture-browser verified and report provider/model provenance and exact source passage locators. This is UI/API integrity evidence, not a rating of appraisal correctness. Full Playwright: **41/41**; Vitest: **13/13**; production TypeScript/Vite build passed; focused appraisal API: **7 passed**.
- T-64 adds one process-level persistence check: fresh migrated temp SQLite, disabled providers, deterministic plan, pause between steps, hard API process kill, relaunch, duplicate-operation replay, owner resume. Focused: **1 passed in 8.10s**. This says nothing about PostgreSQL, in-flight provider requests, remote providers, or research quality.
- The first post-change full backend run collected 319 tests and reported **316 passed, 2 PostgreSQL-only skipped, 1 failed**; the sole failure was `test_implementation_backlog`, which caught the intentional stale T-63 state while T-64 was being recorded. Touched Ruff check passed; format check reported three mechanical formatting changes, which were applied. A clean full run is required after ledger synchronization.
- Current ledger is 66 requirements, 49 residual rows, 64 tasks (55 DONE, 3 IN_PROGRESS, 5 BLOCKED, 1 DEFERRED). The next executable item is T-64; human quality review/live provider run remains blocked and no score is claimed.


## 2026-10-29 clean verification and next context task

- After fixing the backlog document mismatch, the clean full backend run passed: **317 passed, 2 PostgreSQL-only skipped, 1 Starlette/httpx deprecation warning**. Ruff check/format passed; disposable SQLite migration roundtrip/Alembic consistency passed; backlog, benchmark, annotation, evaluation registry and research audit validators passed. Vitest **13/13**, production build and Playwright **41/41** passed. The temporary failing backlog check from the preceding run was resolved by updating T-63/T-64 status/counts, then verified in the clean run.
- T-64 process-restart evidence is explicitly SQLite/local only; PostgreSQL and in-flight remote provider recovery are not measured. M-23 is locally verified across persistence/API/browser boundaries; M-24 remains blocked on remote storage/auth/HTTPS.
- T-19 selected T-65 to use the existing saved project description as an editable user-authored brief, prefill it into new and follow-up decision context, and snapshot into each job scope. No generated summary, factual conclusion, database migration, or model-provider call is implied. Current graph: 66 requirements, 48 residual rows, 65 tasks (56 DONE, 3 IN_PROGRESS, 5 BLOCKED, 1 DEFERRED).

## 2026-10-29 implementation verification (T-65/T-66; T-67 pending)

- T-65 reuses the owner-scoped project description as user-authored context, prefilled into editable new/follow-up composers and persisted as a per-run snapshot. Focused API **2 passed**; full backend **318 passed, 2 PostgreSQL-only skipped, 1 deprecation warning**; Vitest **13/13**; production build and full Playwright **41/41** passed. Browser brief flows include axe A/AA and 360px layout coverage. ADR-0020 defines user/source/parent-evidence boundaries.
- T-66 closes a local prompt-boundary gap exposed by the new scope flow: planner, appraisal, comparison and report-synthesis prompts now identify user question/scope as untrusted data. Adversarial planner/appraisal/comparison/synthesis fixtures pass; focused suite **8 passed**; the full backend rerun **318 passed, 2 PostgreSQL-only skipped**; Ruff check/format; SQLite migration roundtrip; and backlog, benchmark, annotation, evaluation and research-audit validators passed. ADR-0021 documents that prompt wording and fixtures do not establish live-model robustness.
- The source scanner checked **211 text files with 0 findings** after a test-only API-restart secret was changed to a documented placeholder. The restart + secret-scanner focused tests passed **6/6**; the secret-scanner test module passed **5/5**.
- These are software and fixture results, not scientific-quality scores. Benchmark remains at seven pre-registered draft cases, zero completed Veda runs, zero counted human reviews and zero gold answers. T-67 is auditing source versions and access/rights from primary records before any run; the case registry is unchanged. No OpenRouter, OpenAI or PostgreSQL request occurred.
- Current ledger: **66 requirements, 48 residuals, 67 tasks** (58 DONE, 3 IN_PROGRESS: T-19/T-38/T-67, 5 BLOCKED, 1 DEFERRED). Veda is not complete.

## 2026-10-29 real API browser persistence (T-72/T-73)

- T-72 verifies a provider-disabled plan checkpoint through the browser and actual local API, including persisted plan/event reads and browser refresh/reopen. T-73 verifies an actual UI-created parent and follow-up, shared conversation lineage, persisted parent/child messages, the no-citation-reuse context boundary, and child refresh/reopen. These checks use synthetic questions, loopback development auth and temporary migrated SQLite. They do not use model calls or evaluate research quality.
- Full Playwright run with real API mode: **45 passed** (41 fixture-backed journeys plus 4 real-API journeys). Frontend Vitest: **13 passed**; TypeScript/Vite build passed; Ruff check passed and format check confirmed **109 files already formatted**.
- T-73 first exposed test-only API quota exhaustion. The isolated browser server now retains request limiting but uses test-specific larger ceilings so shared UI journeys can execute; production rate limits and their tests are untouched. The focused follow-up rerun passed **1/1**.
- Full backend attempt during ledger edits: **332 passed, 2 PostgreSQL-only skipped, 1 failed** because the backlog consistency check detected the stale task record. No backend application test failed; rerun after synchronizing repository ledgers. PostgreSQL remains unavailable.
- T-74 is a separately gated, pending attempt to execute a full local Veda workflow with actual Crossref/OpenAlex metadata requests, providers disabled and zero model budget. No actual metadata request, complete live retrieval run, report quality score, or expert review is claimed yet. The historical OpenRouter adapter smoke remains one structured call, not a complete Veda job.
- Current ledger: **66 requirements, 48 residuals, 74 tasks** (65 DONE, 3 IN_PROGRESS: T-19/T-38/T-74, 5 BLOCKED, 1 DEFERRED). No quality score is produced or inferred from these software tests.

## 2026-10-29: disclosed provider routing and live workflow boundary (T-75/T-76)

- T-75 updated new-run and follow-up composers to disclose external scholarly/statistics destinations and query/model input handling. Focused Playwright **3/3**, Vitest **13/13**, production build, full local-API Playwright **46 passed/1 gated skip**, and separately opted-in live workflow **1/1** passed. T-76 then restricted World Bank Data360 to a supported statistics topic explicitly present in the user's question plus a user-supplied supported geography, and sends only that question and geography to the adapter.
- T-76 targeted suite **52 passed**; full backend **337 passed, 2 PostgreSQL-only skipped, 1 deprecation warning**; Ruff passed (108 formatted files); Vitest **13/13**; build passed; full Playwright **46 passed/1 gated skip**. Live provider-disabled generic run: Crossref **3 queries/9 records**, OpenAlex **3/7**, Data360 **0/0**; final report had 8 selected sources, 16 candidates and 8 citations; 0 model calls. Deterministic citation integrity passed; semantic citation support was `not_performed`.
- These numbers describe code/integration checks and bounded public-metadata workflows. They do not score retrieval quality, relevance, source rights, appraisal accuracy, contradictions, synthesis quality, or live model behavior. The benchmark still has seven draft cases, zero gold answers, zero completed Veda quality runs and zero independent annotations. At the T-79 selection checkpoint: **66 requirements, 48 residuals, 79 tasks** (70 DONE, 3 IN_PROGRESS: T-19/T-38/T-79, 5 BLOCKED, 1 DEFERRED). T-77 has redacted HTTPX URL user-info/query/fragment from application logs.

## T-78 software verification (quality score not applicable)

- Conditional statistics routing now persists typed v1 outcomes for World Bank Data360 and ILOSTAT in discovery events and report coverage. The report inspector exposes current route outcomes and labels historical absence as not recorded. This is a coverage/contract change, not a research-quality evaluation.
- Full backend: **345 passed, 2 PostgreSQL-only skipped**; Ruff check and format passed (94 files). Frontend Vitest **13/13**, production build and the historical-report browser inspector **1/1** passed. Full isolated local-API/browser suite passed **47/47** before the final strict report-schema edits; focused current-schema real-API journeys then passed **2/2**. The zero-model-call Crossref/OpenAlex run recorded both optional routes as not applicable for unsupported topic. No research-quality score is inferred.

## T-79 disclosure regression (quality score not applicable)

- The composer now specifies that ILOSTAT may receive employment questions only when World geography is explicitly supplied, matching the adapter's current scope. New-run and follow-up fixture journeys assert that exact phrase, and the actual-API live scholarly browser journey checked it too.
- Focused composer browser tests **2/2**, Vitest **13/13**, production build, backlog validator, and actual-API/live-scholarly smoke **1/1** passed. The live run made 3 Crossref and 3 OpenAlex requests, saved 8 sources/16 candidates/8 citations, and reserved zero model calls. This is a disclosure correctness check, not evidence of live ILOSTAT availability or broader research quality.
- At the T-80 selection checkpoint, the ledger was **66 requirements, 48 residuals, 80 tasks** (71 DONE, 3 IN_PROGRESS: T-19/T-38/T-80, 5 BLOCKED, 1 DEFERRED). The seven-case pilot had zero completed Veda quality runs, zero gold answers, zero independent annotations and no quality score.

## T-80 benchmark source metadata screen (no Veda quality run)

- The frozen seven case rows map to six unique primary studies; SUP01 and SUP02 intentionally reuse one study. Authoritative arXiv, publisher and institutional records were checked and recorded in [`../docs/research/benchmark-source-version-rights-audit-2026-10-29.md`](../docs/research/benchmark-source-version-rights-audit-2026-10-29.md). The plan now accurately separates metadata/access screening from full methodological review, reviewer-validated gold-source set, and quality evaluation. Dell’Acqua’s canonical title was corrected without changing the case, DOI or sample.
- Noy–Zhang final *Science* article access returned HTTP 403 in this browser environment; the accessible MIT working paper is a distinct non-peer-reviewed version with n=444, not a substitute. Brynjolfsson’s publisher record states CC BY-NC 4.0, but the intended Veda use's noncommercial status remains unclassified. These remain unresolved; no source passages were copied into the repository.
- Targeted benchmark tests **7 passed**; benchmark plan, evaluation registry, annotation, synthetic metric and research audit validators passed; Ruff check and format passed. The quality registry remains 36 draft cases, 0 gold answers, 0 independent reviews, and 0 scientific scores. Current ledger: **66 requirements, 48 residuals, 81 tasks** (72 DONE, 3 IN_PROGRESS: T-19/T-38/T-81, 5 BLOCKED, 1 DEFERRED).
- T-19 selected T-81 to add a guarded, opt-in, free-only OpenRouter full-job browser harness. No new credential was present or used. The live OpenRouter run remains blocked until the exposed credential is rotated and a replacement is securely configured.
- Benchmark status remains seven draft cases, zero gold answers and zero counted human reviews. No research-quality score is inferred from the route or browser checks.


## 2026-10-29 software resilience checks (T-84–T-86; no quality score)

- Health/rate-limit/security contracts passed **17/17** after separating liveness/readiness from the database-backed global request limiter.
- PostgreSQL engine-option and health tests passed **6/6**; psycopg connection timeout and SQLAlchemy pool timeout were verified at the engine/DBAPI argument boundary without contacting a database.
- Request-limiter database-outage and security tests passed **5/5**, including sanitized 503, rollback and route short-circuit.
- These tests evaluate API reliability/error handling only. No PostgreSQL server, hosted service, provider model, research output, independent annotation, or scientific-quality metric was involved. The benchmark still has seven draft cases and zero completed quality runs, gold answers, independent reviews, or scores.


## T-87 PDF parser deadline update (software reliability only)

- The six-second parser child-process timeout is now capped by the unchanged eight-second overall PDF retrieval deadline; safe-PDF fetches continue to pass only the remaining deadline. Test fixtures now use the configured overall deadline rather than an artificial four seconds. Focused safe-PDF suite passed **9/9** and Ruff passed. The full backend rerun is pending; no source-quality or research-quality metric is involved.


## T-87 clean backend verification (software only)

- The clean backend suite passed **362 tests**, with **2 PostgreSQL-only integration tests skipped** because no loopback disposable `*_test` PostgreSQL URL is configured. Whole Ruff passed (98 files formatted), and backlog/benchmark/annotation/evaluation/research/Blueprint validators passed.
- T-87 changed only the safe-PDF timeout cap/test fixture and documentation. This is reliability evidence, not source-rights validation or research-quality evidence; no PDF host, database, model provider, or deployment was contacted.


## T-88 API error contract (no quality score)

- Focused route-level SQLAlchemy failure, rate-limiter, and security tests passed **7/7**. Injected connection failures map to sanitized 503; integrity failures map to sanitized 500; request ID/security/CORS headers remain present; raw credentials are absent from response and logs.
- This is API reliability/security evidence only. The full regression rerun is pending; no live database outage, provider call, research run, or quality score occurred.


## T-88 full regression (software reliability only)

- Full backend: **364 passed, 2 PostgreSQL-only skipped**; whole Ruff and backlog/benchmark/annotation/evaluation/research/Blueprint validators passed.
- T-88 adds sanitized route-level SQLAlchemy 503/500 contracts with request ID/security/CORS headers. No live PostgreSQL, provider/model research, human review, or quality score was involved.


## T-89 generic error boundary (software only; full regression pending)

- Focused API-error/limiter/security suite passed **8/8**. A secret-bearing generic exception returns a stable 500 with request ID, security headers and allowed-origin CORS; exception text is absent from body/logs. SQLAlchemy classifications continue to return the specific 503/500 contracts.
- This verifies local middleware behavior only. Full backend regression, production server/proxy behavior, live providers, research-quality review and quality scores remain unverified.


## T-89 clean regression (software only)

- Full backend passed **365 tests**, with **2 PostgreSQL-only tests skipped** because no disposable test database URL is configured. Whole Ruff and all listed repository evidence validators passed.
- T-89 verifies safe error responses only. No PostgreSQL, external service, provider/model, research output, or human quality score was involved.


## 2026-10-29 UI request-reference verification (T-91; no research score)

- Frontend unit tests passed: **2 files / 18 tests**. TypeScript and Vite production build passed. The full fixture Playwright suite passed **43 tests with 9 opt-in skips** at two workers.
- Failure parsing exposes the backend status/code and a request ID only when it matches the server allowlist; the response header takes precedence over the JSON body. API, full-account export and report-export failure paths are covered. Upstream diagnostic fields are not rendered.
- Two earlier default-parallel suite runs exposed load sensitivity in a long synthetic workflow; its test now has a 60-second cap and a 15-second evidence-load wait. The controlled full run passed. No external model, database, or research-quality review occurred; no quality score is reported.


## 2026-10-29 backup/restore documentation safety validation (T-92; no research score)

- The backup/restore runbook validator passed and its focused tests passed **5/5**. It detects destructive restore commands/flags, inline credential URLs, mismatched restore-target aliases, missing or reordered database/empty-target guards, absent no-run/RPO/RTO disclosures, and broken documentation links. The CI workflow YAML parses and includes the step; remote Actions execution remains unavailable.
- Full backend: **370 passed, 2 PostgreSQL-only skipped**. Ruff passed across 101 backend files. Backlog, benchmark, annotation, evaluation registry, research audit, Render Blueprint, and backup-runbook validators passed.
- No PostgreSQL tool/service, backup, restore, external model, human review, or scientific-quality score was involved.


## 2026-10-29 cross-origin request-reference check and ILOSTAT retry

- T-93 actual browser-to-local-ASGI request-reference test passed **1/1** over Vite/API cross-origin CORS. The Veda client received the generated response ID header, returned a typed 404 `ApiError` and displayed the same validated reference. Temporary SQLite, no provider.
- One bounded read-only retry of the configured ILOSTAT data route returned **404 `text/plain`** with redirects disabled; no response body was read. No data observation/schema/version or rights claim follows. T-49 remains blocked.
- These are integration and availability observations, not research-quality evidence; no quality score is reported.


## 2026-10-29 data-erasure software verification (T-99/T-100; no research score)

- T-99 implementation verified the owner-wide Veda-stored data purge, separate identity-provider disclosure, current-day quota safety preservation and preference/workspace reset. The real browser/API journey used only synthetic seeded records in the provider-disabled temporary SQLite harness; it is not a research run.
- T-100 directly verified cascade removal of every persisted research-artifact table for the purged tenant while another owner’s project/job remain. Focused purge tests passed **4/4** and the clean backend passed **377 tests, 2 PostgreSQL-only skips**. Frontend Vitest **18/18**, production build, fixture Playwright **44 passed/12 opt-in skipped**, and real browser/API erasure Playwright **1/1** passed.
- No Veda output was scored. The seven-case protocol remains unreviewed; zero full OpenRouter jobs, zero human review results, and zero scientific-quality scores are recorded. PostgreSQL locking, hosted authentication, deployment and backup erasure remain unverified/external. The exposed OpenRouter credential was not reused.


## 2026-10-29 authorized OpenRouter run preflight (T-17/T-30; no inference)

- The user authorized one complete local free-only Veda research job. The key was not securely configured: process/user/machine environment checks were all absent, and no root/backend `.env` exists. It remains only in the prior chat message; copying it into command/tool text or a file would violate the user's explicit no-log/no-persistence requirement. No inference request was sent, no provider usage was recorded, and no charge occurred.
- A read-only unauthenticated catalog check selected `xingchen-agi/xing4.0-29b-a4b:free` as an eligible preflight candidate because it advertised text output, `structured_outputs`, and zero prompt/completion pricing. This is a catalog observation, not a model call or guarantee of continued availability; verify again at execution. OpenRouter documents that `:free` variants have zero model pricing and rate limits on its [free-model collection](https://openrouter.ai/collections/free-models).
- The guarded-run server tests passed **7/7**. They validate only local preconditions and cannot substitute for the requested real research run. No model-generated claim, citation, report, provider/model usage, or research-quality result is available from this attempt.

## 2026-10-29 one-time OpenRouter ten-case run (T-102; incomplete)

- The user explicitly authorized one local OpenRouter free-only research test. The actual browser batch used isolated SQLite, Crossref/OpenAlex, route openrouter/free, no OpenAI calls, no paid fallback and zero Veda retries. This was a research workflow attempt, not only an adapter smoke.
- Ten detailed cases created ten jobs. Discovery returned **203 candidates**, with **140 selected scholarly records** (137 Crossref and 3 OpenAlex); extraction persisted **141 claims**. Two structured planning selections were accepted from nvidia/nemotron-3-ultra-550b-a55b:free; both reported **$0.00**. The eight other plans used deterministic fallback after uncertain outcomes.
- There were **20 persisted provider usage entries**: 2 accepted and 18 failures. The 18 failed entries have unknown reported cost. No positive cost was reported, but Veda cannot confirm total provider billing. Persisted usage rows are the count basis; the raw transport-attempt counter was not captured. No retry occurred.
- **All ten jobs failed at appraisal.** No methodological appraisal, report, cited claim, deterministic citation check, semantic-support result, comparison/hypothesis analysis or final synthesis was persisted. The browser did not inspect reports/citations in this batch because none existed. Existing separate model-disabled browser/report tests establish only their own local boundaries.
- Source relevance was poor in several cases. Offline replay of T-103's conservative topic gate passes 38/203 candidates by title alone and rejects 112/140 old selected sources using saved title/abstract. This is a heuristic regression signal, not human-reviewed relevance/precision/recall. The source examples, complete case details, limits, and redacted browser/runtime evidence are in evaluation/openrouter-live-research-2026-10-29.md/json and the two raw artifacts.
- The actual model was used for two planning responses, so the batch was not silently all-deterministic; however, it did **not** produce an AI-grounded final report. The one-time authorization is exhausted. No second request is made under it. Independent source/research-quality review is still absent, so no scientific accuracy claim or quality score is justified.

## 2026-10-29 latest local software verification (T-103–T-106)

- Backend: **392 passed, 2 PostgreSQL-only skipped**, with one existing deprecation warning.
- Frontend unit: **21/21**; TypeScript/Vite production build passed. Fixture Playwright: **44 passed, 13 gated skips**.
- Whole Ruff format/check and fresh SQLite Alembic upgrade/downgrade/re-upgrade consistency passed. The PostgreSQL tests remain skipped because no disposable loopback *_test service is available. An initial system-Python pytest command failed collection in four tests because root and backend scripts were resolved from the wrong import context; the documented locked uv invocation below is the authoritative rerun and passed.
- T-103 adds conservative auditable candidate filtering; T-104 stores sanitized provider error classes and preserves unknown costs as null; T-105 improves browser auditing for partial runs; T-106 uses bounded compact bibliographic queries. These local tests do not establish live retrieval accuracy or quality.



## 2026-10-29 T-107/T-108 post-fix integration and audit checks

- The original backlog audit missed T-100+ references because it accepted exactly two digits. T-107 fixes this and now requires every residual row to retain non-DONE work. Regression tests passed **3/3**; the final validator covers **66 requirements, 48 residual rows and 108 tasks**, with zero missing open/blocked/deferred links.
- T-108 re-ran the bounded public scholarly workflow after query/relevance changes with model credentials blank and model provider disabled. The browser API run passed **1/1**; Crossref/OpenAlex each returned HTTP 200 with 3 queries each, 9/7 results, 16 candidate records, 8 selected sources and 8 citations. The persisted report and citation/source inspector were inspected in the browser. Statistics routes were not applicable; 0 model calls and $0 estimated model cost.
- This shows the revised retrieval path can persist and display a model-disabled report. It does not establish AI synthesis, citation semantic support, research accuracy, source rights, hosted behavior or PostgreSQL operation.
- Final code/backlog validators passed. The independent research-evaluation state remains: 36 draft registry cases, 0 gold answers, 1 annotation record marked not reviewed, and no scientific-quality score.


## 2026-10-30 appraisal repair and offline pipeline evidence (T-109–T-111)

The ten-case OpenRouter run is still a failed live validation. The preserved provider evidence does **not** reveal why the appraisal calls failed; `model_call_uncertain` was the only saved job-level classification and no provider error class/finish reason was recorded. We did not send another OpenRouter request. Code-level compatibility defects and their offline corrections are separated from that unknown historical cause in `docs/research/openrouter-appraisal-root-cause-2026-10-30.md` and ADR-0033.

| Check | Current result | Boundary |
|---|---|---|
| Full backend pytest (`uv run --locked python -m pytest -ra --tb=short`) | **407 passed, 2 PostgreSQL-only skipped, 1 Starlette/httpx deprecation warning** | Offline SQLite/API/workflow/security/provider fixture behavior; not PostgreSQL runtime or model quality |
| Frontend Vitest (`npm test`) | **21/21 passed** | Current unit contracts, including free-route audit/accounting semantics |
| Frontend production build (`npm run build`) | **Passed** | TypeScript/Vite compilation; not deployment |
| Provider-disabled real browser citation inspection | **1 passed on retry** | Isolated SQLite API and browser open a synthetic persisted report, inspect its citation/passage; no model or scholarly API call. The first cold-Vite attempt returned a white page after `ERR_NETWORK_CHANGED`, then the retry passed in 8.8 seconds. |
| Retrieval snapshot replay | **203 candidate occurrences; 140 historical selections; 7 malformed-title occurrences, including 2 historically selected; 44 clean title-only passes; 104 clean historically selected records rejected for topic overlap** | Deterministic metadata filtering only; no unique-paper deduplication, human labels, precision/recall, or scientific-quality claim. See `retrieval-overlap-audit-2026-10-30.md/json`. |
| Full typed provider fixture workflow | Included in the full backend suite | Fixture planning → scholarly discovery → extraction → appraisal → comparison → verification/audit → synthesis → persisted report/citation map. This is not a real-model call or model-quality validation. |
| Failure/recovery fixture | Included in the full backend suite | Unsupported-format fallback plus uncertain appraisal timeout preserves evidence, keeps cost unknown and persists a limited report; it does not reconstruct the historical provider failure. |

T-111 closed that local verification checkpoint: whole-backend Ruff and fresh SQLite migration round-trip passed; the backlog, benchmark, annotation, evaluation registry, source ledgers, Render Blueprint, backup/restore and secret validators passed (261 text files, zero findings). T-112 is now separately authorized but remains blocked on secure local credential staging. No scientific accuracy, billing total, live OpenRouter end-to-end report, PostgreSQL behavior, or external deployment is established.


## 2026-10-30 T-112 one-question live validation preflight

The user authorized exactly one local question: **“Does generative AI improve software developer productivity, and why do empirical studies sometimes report different findings?”** The one-question runner performed public, read-only catalog checks and then stopped before inference because no `OPENROUTER_API_KEY` was available in the process or repository-root/backend `.env`. No research job, API completion, provider usage, cost, report, database, or browser report inspection occurred. This is a credential-staging blocker, not a provider completion failure. The attempt record is `openrouter-t112-attempt-20261030.json`.

The route preflight selected `nvidia/nemotron-3.5-super-vl:free`; the suffix-specific endpoint record showed an active NVIDIA free endpoint supporting `response_format` and `structured_outputs`, with prompt/completion prices `0`. The model/endpoint request-price field is `null`, not numeric zero. The future request remains pinned to the free model and sets `require_parameters: true`, `allow_fallbacks: false`, and `max_price` prompt/completion/request all to zero; actual route and cost would still need confirmation from a successful inference response. Full metadata: `openrouter-t112-preflight-20261029T200048Z.json`. A preflight bug that stripped `:free` and inspected paid endpoints was corrected and regression-tested before any inference.

| Check | Result | Boundary |
|---|---|---|
| Full backend (`uv run --locked python -m pytest -ra --tb=short`) | **417 passed, 2 PostgreSQL-only skipped, 1 Starlette/httpx deprecation warning** | Offline code and fixture behavior; not a live model run or PostgreSQL runtime |
| T-112 route and browser guard tests | **17 passed** | Request setup, suffix-preserving free endpoint lookup and fail-closed metadata checks; no inference |
| Ruff check and format | **Passed** | T-112 code and backend |
| Frontend Vitest / TypeScript / production build | **21/21 / passed / passed** | Local frontend contracts and build only |
| Playwright discovery | **1 live-gated test discovered; not executed** | Missing credential stopped the runner before the browser/API job path |
| T-112 runner | **Preflight passed; stopped before dispatch** | Credential absent. Provider requests: **0**; provider error class/finish reason: **not applicable**; reported inference cost: **null / not applicable** |
| Secret-pattern scan | **268 text files; 0 findings** | No credential was copied into repository files or artifacts |

The one-question runner is `backend/scripts/run_openrouter_single_question_e2e.py`; it must recheck metadata immediately before dispatch, enforces a hard six-provider-request limit, zero Veda cost ceiling, zero rate-limit retries, and no resend of uncertain POSTs. From `backend/`, run `uv run --locked python scripts/run_openrouter_single_question_e2e.py` once the credential is staged locally without posting it in chat. Do not count a limited deterministic fallback as AI-powered success. T-112 remains BLOCKED; the AI research engine is not operationally validated, and no scientific reliability claim is made.


## 2026-10-30 T-112 actual live attempt

This section supersedes the earlier preflight-only status above. The user supplied the credential through the staging exchange and said `ready`; the one-question authorization was exercised exactly once. No credential is recorded in the run artifacts or repository documentation. No additional inference request is authorized by that one-time permission.

| Check | Observed result | Boundary |
|---|---|---|
| Free-route preflight | `nvidia/nemotron-3.5-super-vl:free`; active NVIDIA `:free` endpoint supported `response_format` and `structured_outputs`; prompt/completion price metadata was zero; request-price metadata was null. Request enforced required parameters, disabled fallbacks and zero maximum prompt/completion/request prices. | Metadata is not account billing confirmation; route may change. |
| Live model operations | 3 HTTP 200 POSTs: planning, appraisal and claim comparison. All returned `finish_reason=length`, were classified `provider_output_truncated`, and passed zero structured outputs. No retry or uncertain POST resend occurred. Usage model rows identify `nvidia/nemotron-3.5-super-vl:free`; token counts were null. | HTTP success did not mean a valid stage result. |
| Provider costs | Each call reported and estimated `$0.00`. | Account-level billing was not independently checked; request-price metadata was null. |
| Discovery and extraction | Crossref: 4 queries/20 records; OpenAlex: 4 queries/11 records; 31 candidate ledger rows, 4 duplicate exclusions, 15 topic-overlap exclusions, 12 selected sources; 8 selected abstract passages, 4 metadata-only; 26 extracted claim units. | Abstract-only; several bounded excerpts ended mid-fragment; no full text. |
| Synthesis / semantic support | Synthesis not dispatched because the serialized prompt exceeded the 24,000-character cap; semantic-support audit not run. | Required AI-stage coverage not met. |
| Saved report and browser | Deterministic limited “Preliminary evidence map” persisted in isolated SQLite and opened through the real browser. Citation/source, original passage, methodology and claim inspectors were inspected. Deterministic 26/26 stored source/passage link checks passed. | This is not an AI-powered report or semantic citation judgment. |

**Operational success: failed.** Scientific reliability: unverified. T-112 job `900c3b8d-e857-4a60-a530-0650fec1fa6e`; run artifact `openrouter-t112-resume-20261029T210403Z.json`; isolated database `veda-t112-20261029T205811Z.sqlite3`. Detailed review: `t112-live-run-quality-review-2026-10-30.md`. Offline repair/test status is in ADR-0034 and T-114/T-115; no second model request was made.


### T-116 retrieval snapshot replay

A read-only replay of the persisted T-112 SQLite ledger found 31 candidate occurrences (12 selected, 15 insufficient-topic-overlap exclusions and 4 canonical duplicates). One selected OpenAlex record titled as an empirical GenAI software-engineering study carried an abstract passage that was actually a repository inventory, including Jupyter notebooks, raw survey data and a survey tool. A narrow prefix-plus-artifact-cue check now excludes that text with `repository_artifact_description_not_abstract`, while retaining the candidate and reason. Focused discovery/relevance tests passed 13/13; touched Ruff check passed and formatting passed after applying the formatter. The excluded “Generative AI at Work” record matched AI/generative/productivity features but does not establish a false negative for a software-developer question; excluded abstracts are not stored and no human labels exist. See `t112-retrieval-quality-audit-2026-10-30.md`. No precision/recall or scientific-quality score is reported.


## T-115 final offline verification after truncation and retrieval repairs

| Check | Result | Boundary |
|---|---|---|
| Full backend (`uv run --locked python -m pytest -ra --tb=short`) | **433 passed, 2 PostgreSQL-only skipped, 1 deprecation warning** | Offline tests used blank model credentials; no provider request. The skips require a disposable loopback PostgreSQL test database. |
| Frontend | **Vitest 21/21; TypeScript/Vite build passed** | Local unit/build checks, not deployment. |
| Ruff | **Check and format passed, 114 files** | Source style only. |
| SQLite migration round-trip/Alembic | **Passed** | SQLite migration behavior, not PostgreSQL. |
| Backlog/research/deployment validators | **Passed** | 66 requirements, 48 residual crosswalk rows, 116 tasks; seven benchmark cases with no scores; one not-reviewed annotation; 36 draft evaluation cases and no gold answers; 28 papers/23 repositories; Render Blueprint and backup/restore safeguards. |
| Provider-disabled actual browser/API report citation inspection | **1/1 passed** | Synthetic persisted report/citation/passage inspection, no model or scholarly provider call. |
| Secret-pattern scan | **278 text files; 0 findings** | Run after removing the temporary OpenRouter environment setting from ignored root `.env`; remaining settings were preserved. |
| T-112 preserved-case synthesis prompt probe | **23,084 characters for 8 sources, 26 claims and 26 passages** | Under the 24,000-character Veda guard; `_model_call_blocker` was replaced with an in-memory capture, so no provider request was possible. Not a live synthesis result. |

The first post-repair full backend run had one failure because compacting the synthesis system prompt dropped the explicit phrase asserted by the prompt-injection security test. The wording was restored, the regression passed, and the clean full rerun above passed. T-114/T-116 local changes are now covered offline; T-112 remains a failed live AI validation. No scientific reliability, future route success, account-level cost, PostgreSQL runtime, managed auth or deployment is established.


## 2026-10-30 T-117/T-120 provider diagnostics and offline completion

| Check | Result | Boundary |
|---|---|---|
| Full backend (`uv run --locked python -m pytest -ra --tb=short`) | **450 passed, 2 PostgreSQL-only skipped, 1 Starlette/httpx deprecation warning** | Offline fixtures and local SQLite/API contracts; no model inference. PostgreSQL skips require a disposable loopback `*_test` DB. |
| Focused provider/workflow/depth/route tests | **Passed** | Strict validation, truncation diagnostics, exact free-route guards, reasoning-token metadata persistence, budget caps, partial appraisal/recovery and route-metadata failure cases. Fixtures do not prove model output quality. |
| Frontend Vitest / production build | **21/21; passed** | UI contracts and TypeScript/Vite build only. |
| Ruff | **Check and format passed; 135 backend files** | Static/format checks, not runtime correctness. |
| SQLite migration round-trip/Alembic | **Passed** | Upgrade/downgrade/re-upgrade and consistency, including nullable `reasoning_tokens`; PostgreSQL runtime remains unverified. |
| Fixture Playwright | **44 passed, 14 opt-in gated skips** | Real UI with deterministic API fixtures; no provider-backed report. |
| Provider-disabled real browser/API | **7 passed, 1 live scholarly/model smoke skipped** | Fresh isolated SQLite, actual API and browser; report citation and original source passage were inspected. The report is synthetic fixture data. |
| Local validators | **Passed** | 66 requirement rows, 48 residual rows, 120 task records; 7 benchmark cases with no scores; 1 not-reviewed annotation; 36 draft registry cases; 28 paper/23 repo ledgers; Render and backup/restore validators. |
| Secret scan | **288 text files, 0 findings** | Non-uploading repository file scan; no Git history exists to inspect. |
| Current OpenRouter route preflight | **Eligible; 0 inference requests** | `xingchen-agi/xing4.0-29b-a4b:free`; prompt/completion price metadata zero, request price null; structured output/reasoning controls listed; default reasoning on and not mandatory; reasoning disabled in guarded runner. Account-level billing remains unknown. |
| Guarded one-question runner | **Stopped before dispatch: credential unavailable locally** | Process variable absent, root `.env` contains no OpenRouter key, backend `.env` absent. Wrote sanitized status/preflight artifacts. No secret was reconstructed from chat. |

The first real-browser/API run accidentally executed all local API tests in parallel and failed an assertion that assumed exactly one project before the data purge. Other tests had created a second project in the shared disposable database. The assertion was changed to compare with the measured pre-purge count; the serial full-file rerun passed. No user data was touched.

The full offline structured workflow includes planning fixtures, Crossref/OpenAlex fixtures, evidence extraction, passage-linked appraisal, claim comparison, competing-hypothesis structure, deterministic citation integrity, semantic-support fixtures, synthesis, persisted report and inspection APIs, plus failure/recovery paths. This verifies Veda's deterministic contracts and safe validation, not a live AI-generated report. T-112 remains failed operationally: three outputs truncated, zero AI stages accepted. T-119's later live attempt is recorded below; it also accepted zero AI stages. A successful real-model report has not been achieved, and scientific reliability remains unverified.


## 2026-10-30 T-119 live validation and offline pipeline corrections

The root `.env` credential was available to the T-119 runner and its nested backend subprocess; presence was checked as a boolean only and the file was not modified. The selected OpenRouter route passed fresh public metadata checks for `xingchen-agi/xing4.0-29b-a4b:free`. Model and endpoint prompt/completion prices were zero; request-price metadata was null. Required structured-output parameters were advertised, and dispatch retained `require_parameters`, disabled fallback, and zero prompt/completion/request price ceilings. Public metadata does not establish account billing or endpoint availability at inference time.

The first runner invocation failed before job creation because its browser evaluation did not receive the `runId` argument; it sent **0** provider requests. After that offline harness fix, the single authorized SQLite/browser job made exactly **4** provider requests (six-call hard cap, zero rate-limit retries and zero uncertain resends). Planning, appraisal and comparison each returned HTTP 429 and were recorded `provider_rate_limited`; synthesis returned HTTP 200 but was truncated at the 2,200-token completion cap with `finish_reason=length`. No structured AI output was accepted, and no paid fallback was used. The single authorization is spent; no further inference call was made.

Crossref/OpenAlex returned 31 candidate occurrences; 11 sources were selected, 25 deterministic source-reported statements were persisted, and the fallback report had 11 citation entries. The actual browser opened the report, a citation and its original source passage. Deterministic source/passage link integrity passed **25/25**; semantic support was **not performed**. Sources were 8 abstract-only and 3 metadata-only, with no full text. Appraisal fields remained unknown; no relationship or competing-hypothesis records were produced. The saved `Preliminary evidence map` is deterministic fallback, not AI success. Three rate-limited calls have unknown cost metadata; synthesis reported $0.00; account-level billing is unconfirmed.

The report included seven incomplete claim tails from truncated 560-character abstracts. Adapters had preserved the truncation flag inside versioned `provider_metadata.extensions`, but extraction checked only the top level. The lookup now handles both shapes and a regression verifies the incomplete tail is excluded (ADR-0036). The synthesis contract is now compact v3 with bounded field/list sizes and a 2,600-token standard-profile output maximum after the live response hit its prior 2,200-token cap (ADR-0037). These changes are offline-only and have not been tested against a live model.

Focused backend tests passed **30**, Ruff check and formatting passed, frontend production build passed, and Playwright test discovery passed without running the provider test. Full stage and quality review: `evaluation/t119-live-run-quality-review-2026-10-30.md`; sanitized run artifact: `evaluation/openrouter-research-validation-20261030T115353919544Z.json`. T-119 remains **BLOCKED**, and scientific reliability remains unverified. A new live validation requires separate authorization.


## 2026-10-30 T-119 Gemini-key preflight — no inference

A later presence-only check found `GEMINI_API_KEY` configured in the root `.env`, while `OPENROUTER_API_KEY` was absent. The T-119 runner reads only `OPENROUTER_API_KEY`; a nested backend subprocess confirmed `Settings` has no Gemini key field or provider. The credential was never displayed or modified.

The pinned OpenRouter free-route metadata preflight remained eligible, with zero model/endpoint prompt and completion prices, null request price, and required structured-output parameters listed. The existing runner then stopped with `not_dispatched_missing_credential`, writing sanitized artifact `evaluation/openrouter-research-validation-20261030T122146554866Z.json`. It sent **0 inference requests**. No job was created, so planning, discovery, extraction, appraisal, comparison, citation checks, synthesis, semantic support, report persistence, and browser inspection were not run in this follow-up. This does not alter the prior failed four-request T-119 job. Details: `evaluation/t119-gemini-key-preflight-2026-10-30.md`.


## 2026-10-30 provider-neutral contract and Sarvam offline verification (T-121–T-124)

### Model-agnostic boundary

The workflow consumes a shared `ModelProvider` contract for identity, capabilities, structured generation, validated results, normalized usage/failures and reservation context. OpenAI Responses, OpenRouter and Sarvam V2 translate their own request/response formats behind adapters. Research Pydantic schemas, persistent SQL workflow state, route pinning, budget reservations, lease/checkpoint recovery and no-unsafe-retry rules remain vendor-independent. Offline regression tests cover all three adapters; no provider switch is permitted after a pinned job starts. ADR-0038 records why LangChain and LangGraph were not adopted.

### Sarvam route and validation status

Candidate reviewed: `sarvam-105b` through `POST https://api.sarvam.ai/v2/chat/completions`, with `api-subscription-key` authentication and strict V2 JSON Schema response format. Current public limits reviewed: 128K context and a conservative 4,096 completion-token cap; price estimate ₹15/M input and ₹60/M output, excluding GST, with a 1.2 reservation margin. V2-specific docs do not verify `reasoning_effort` support for this model, so the adapter does not send it. Public docs do not reveal this account’s remaining credits or auto-recharge setting. The reservation is a pre-dispatch estimate, not an account billing guarantee.

The initial pre-correction controlled preflight did **not** dispatch. It ran from repository-root cwd, so the relative `../.env` path was not the backend launcher path; it returned false for `SARVAM_API_KEY` and emitted a dotenv parse warning. The corrected launcher-context check is recorded below. Settings also reports paid model calls disabled and the Sarvam per-job INR budget at zero. Account Credits Left and auto-recharge could not be checked here. The root `.env` was not displayed, copied, changed or deleted.

| Measurement | Result |
|---|---|
| Live inference requests | **0** |
| Accepted live structured outputs | **0** |
| Planning / discovery / extraction / appraisal / comparison / hypotheses / citation integrity / semantic support / synthesis | **No live job; not run** |
| Report persistence and live browser citation inspection | **Not run** |
| Reserved and actual inference cost | **₹0 / ₹0** |
| Compatibility milestone | **Not established live; offline adapter contract only** |
| Operational AI research milestone | **Not achieved** |
| Scientific reliability | **Not evaluated** |

### Offline verification

- Full backend: **468 passed, 2 PostgreSQL-only skipped, 1 Starlette/httpx deprecation warning**.
- Ruff check and format: passed; **107 files already formatted**.
- SQLite migration upgrade/downgrade/re-upgrade and Alembic consistency: passed.
- Frontend Vitest: **21/21**; production build: passed.
- Fixture Playwright: **44 passed, 14 opt-in skipped**; the two tests that timed out while other suites/builds were competing for resources passed when rerun serially (**2/2**).
- Provider-disabled real local API/browser flow: **7/7 passed, 1 gated live-smoke skipped**; inspected the synthetic persisted fixture citation and source passage. This is not AI research.
- Repository/backlog/evaluation/source/deployment validators passed. The earlier T-124 secret scan checked 288 text files with 0 findings; a fresh post-check scanned 310 and reported one credential-pattern finding at root `.env` line 1, while emitting no matched value. `.gitignore` contains `.env` and `.env.*` exclusions, but this workspace has no Git metadata to verify ignore/index/history status. PostgreSQL integration was skipped for lack of a disposable PostgreSQL service/URL.

**Next step:** T-123 remains blocked. Before dispatch, the backend must see the key, the bounded run’s paid-call gate and ≤₹5 INR ceiling must be configured, and the operator must verify available Credits Left and auto-recharge in Sarvam Settings → Billing. The first request will be a schema-only compatibility checkpoint, with no retry; only if it succeeds may the same bounded job continue within six total POSTs. A failed live operation ends this authorization.


## 2026-10-30 T-123 repeat preflight after .env correction — no inference

The first repeat check ran from repository-root cwd. `SettingsConfigDict` loads relative `../.env`, so that invocation did not mirror the backend launcher working directory and cannot establish credential absence. It printed no credential and sent no request. Effective spend settings at that check remained provider disabled, paid calls disabled, and Sarvam per-job INR ceiling ₹0.

Official Sarvam docs were rechecked: `sarvam-105b` is currently listed for V2; `/v2/chat/completions` documents `api-subscription-key`, strict JSON Schema response formatting, and usage fields; public Sarvam-105B prices are ₹15/M input and ₹60/M output excluding GST. Signup credit availability in general does not verify this account's current Credits Left or auto-recharge state; billing documentation directs account holders to Settings → Billing. [V2 endpoint documentation](https://docs.sarvam.ai/api-reference/chat/chat-completions-v2), [Sarvam-105B limits](https://docs.sarvam.ai/api/getting-started/models/sarvam-105b), [pricing and credits](https://docs.sarvam.ai/api/getting-started/pricing), [billing and auto-recharge](https://docs.sarvam.ai/api/platform/billing).

| Measurement | Repeat preflight result |
|---|---|
| Provider inference requests | **0** |
| Accepted structured outputs | **0** |
| AI research stages / report / live browser inspection | **Not run** |
| Reserved / actual inference cost | **₹0 / ₹0** |
| Live model compatibility | **Not established** |

No compatibility POST was sent; this was a safe configuration/catalog preflight. No automatic retry or provider fallback occurred. The prior T-123 blocker remains active.

### Corrected backend-launcher presence check

After the user corrected `.env`, the check was repeated using the actual launcher context: `uv run --locked --directory backend`. Presence-only output was `process_key_present=false`, `backend_settings_key_present=true`; the backend loads the credential from its configured dotenv file without placing it in raw process environment output. No dotenv warning occurred and no credential value was displayed. The effective Settings still report `llm_provider=disabled`, `allow_paid_llm_calls=false`, and `sarvam_max_job_cost_inr=0.0`, so model readiness is false. No provider POST was sent.

Current official pricing was rechecked: Sarvam-105B is listed at ₹15/M input, ₹5/M cached input, ₹60/M output, excluding GST; the pricing table lists Pay-as-you-go limits of 60 requests/minute. Billing docs state credits are shared across the organisation and auto-recharge can trigger a top-up; account-specific Credits Left and auto-recharge cannot be read from this environment. Since the user disallowed credit purchases/top-ups, the live run remains stopped pending verification that sufficient credits are available and auto-recharge is off. See [current pricing and limits](https://docs.sarvam.ai/api/getting-started/pricing) and [billing and auto-recharge](https://docs.sarvam.ai/api/platform/billing). Requests remain **0**, accepted outputs **0**, and cost **₹0**.


## 2026-10-30 T-123 bounded Sarvam attempt — probe truncated; research not started

The user confirmed that Settings → Billing showed sufficient Credits Left for a ≤₹5 test and Auto-recharge was off. A presence-only check in backend launcher context found the key through backend Settings; its value was not printed, and the root `.env` was not changed. `.gitignore` contains `.env` and `.env.*`; this extracted workspace has no Git metadata, so `git check-ignore`/index history could not be independently queried.

Official Sarvam documentation was rechecked immediately before dispatch. V2 lists `sarvam-105b` as an accepted model, requires the `api-subscription-key` header, and documents strict `response_format.type=json_schema`; the route returned a response whose model identity passed Veda's exact model check before the finish reason was examined. Public pricing lists ₹15/M input, ₹5/M cached input, and ₹60/M output; prices exclude GST. The published PAYG rate limit is 60 requests/minute. Sarvam documents organisation-shared credits and auto-recharge; account balance was user-confirmed, not independently queried. [V2 endpoint and structured-output docs](https://docs.sarvam.ai/api-reference/chat/chat-completions-v2), [pricing and rate limits](https://docs.sarvam.ai/api/getting-started/pricing), [billing and auto-recharge](https://docs.sarvam.ai/api/platform/billing).

| Measurement | Result |
|---|---|
| Provider/model/endpoint | Sarvam `sarvam-105b`; `POST /v2/chat/completions` |
| Inference POST attempts | **1 of 6**, the appraisal-schema compatibility probe only |
| Accepted structured outputs | **0**; `provider_output_truncated`, `finish_reason=length` |
| Probe completion cap | 256 tokens; incomplete response rejected; no partial schema accepted |
| Research job and research-stage inference requests | **Not created / 0** |
| Planning, appraisal, comparison, synthesis, semantic support | **Not attempted** |
| Discovery, evidence, report, and browser inspection | SQLite migration/fixture setup completed before the probe; no research job/report or browser inspection occurred |
| Retries, fallback, OpenAI/OpenRouter | **0**, none |
| Reported/estimated actual cost | **Unknown**; the live harness failed to persist provider usage/cost fields from the truncation exception |
| Probe pre-dispatch reserved estimate | **₹0.08049 before tax**, reconstructed offline from the exact original prompt/schema, 256-token cap, and reviewed rates; the live artifact only retained the ₹0.10 ceiling |
| Authorized/pre-tax ceilings | ₹5.00 total authorization; ₹4.00 pre-tax reservations with ₹1.00 tax/rounding headroom |
| Operational AI research success | **Not achieved** |
| Scientific reliability | **Not evaluated** |

The immediate provider outcome is established: Sarvam ended the response at the configured 256-token limit and Veda rejected it. The leading explanation is an undersized probe completion cap; why the model consumed the full allowance is unknown because the old harness discarded the exception's usage diagnostics. The conservative pre-dispatch reservation is ₹0.08049 before tax, but actual reported/estimated provider usage and billed cost are unknown. No raw provider response was saved. The one-time inference authorization is exhausted; no further inference was sent.

Offline repair raises the next compatibility checkpoint to a 1,024-token cap, tightens the JSON-only instruction, reserves at most ₹0.25 for the probe, and preserves allowlisted model/finish/usage/cost/latency diagnostics. The remaining job ceiling becomes ₹3.75; total pre-tax reservation stays below ₹4.00. An offline conservative-envelope calculation is ₹0.12846 for the revised probe, under its ₹0.25 reserve. Regression tests cover safe failure metadata, unknown cost/model fields, and this reservation bound. These changes are not live-validated. A new live attempt requires fresh authorization.

## 2026-10-30 T-125 output-capacity audit and pre-dispatch execution plan

### Diagnosis and changes

A real strict-schema fixture profile exposed that the eight-claim appraisal partition had little room beneath Sarvam Starter's documented 4,096 max_tokens ceiling: the largest observed eight-claim output serialized to about 3,118 cl100k_base proxy tokens before provider-specific tokenization and reasoning. Because Sarvam V2 counts reasoning within max_tokens and does not document a V2 reasoning-effort parameter for this route, increasing every cap or assuming hidden reasoning could be disabled was not justified. Appraisal batches now cap at four claims and each operation has a fixture-derived minimum completion allocation with headroom: planning 1,024; appraisal 2,560; comparison 1,792; report draft 1,280; semantic audit 2,560. The operation can use the depth/profile allocation up to provider limits, but insufficient allocation is rejected rather than silently clamped. Previously accepted appraisal batches persist if a later call fails; incomplete model JSON remains rejected and remaining fields stay unknown/deferred.

Before appraisal dispatch, Veda now commits a resource_plan event containing the required/planned/deferred operation graph, per-operation output capacities, pinned route, daily global/per-user call slots, job call capacity and reservations, spend ceiling and remaining spend. The workspace displays this saved plan in the real browser. Route latency is recorded as unavailable until an operation-level baseline exists. Exact prompt input and cost reservation still happen immediately before each exact request; the plan is not a substitute for those atomic guards.

Fixture sizing measurements using cl100k_base (a documented comparison proxy, not Sarvam token usage) were: appraisal for two sources/four claims 1,599; eight claim relationships and two hypothesis pairs 1,049; max compact report draft 794; semantic audit 1,706. A single source plus eight claims was approximately 3,118, which motivated splitting. These numbers support capacity design, not scientific claims or guaranteed provider completion.

### Verification

- Full backend suite: **476 passed, 2 PostgreSQL-only skipped, 1 existing Starlette/httpx deprecation warning**.
- Focused backend workflow/provider/budget suite: **48 passed**.
- Ruff lint and whole-backend format check: passed.
- Frontend Vitest: **23/23**; TypeScript/Vite production build: passed.
- Playwright fixture E2E: **45 passed, 15 opt-in tests skipped**, including the resource-plan view. The skipped set includes provider-live and managed-service gates.
- Resource-plan browser case was also run in isolation: **1/1 passed**.
- SQLite migration upgrade/downgrade/re-upgrade and Alembic check: passed.
- Backlog, evaluation registry, benchmark, annotation, research audit, Render blueprint, backup/restore and secret scanner validators passed after the ledger synchronization. The secret scan checked **324 text files, 0 findings**.
- No model provider request, secret access, live billing query, paid spend or external service operation occurred.

### Outcome boundary

This resolves an offline capacity-allocation and visibility defect. It does not demonstrate that Sarvam, OpenAI, or OpenRouter will complete Veda's structured operations. T-123 remains blocked because its one-time live authorization was consumed by a truncated 256-token probe. No AI stage, AI-authored report, semantic correctness result, or scientific reliability score is claimed. The next live action requires fresh authorization and must use the existing bounded runner only after the current offline validation passes.

### 2026-10-31 final ledger check

After the T-125 crosswalk and date synchronization, the implementation-backlog validator passed: 66 requirements, 48 residual rows, 125 tasks (114 DONE, 10 BLOCKED, 1 DEFERRED), no errors. Evaluation registry, benchmark, annotation and research-audit validators passed. These are repository-structure/fixture checks; they do not add any live AI or research-quality evidence. No provider request was sent.

## 2026-10-31 T-126 end-to-end Sarvam GLM-5.3 Flash run

**Status:** Operational live research acceptance passed. Scientific reliability and production readiness remain unverified.

| Measure | Result |
|---|---|
| Provider/model/endpoint | Sarvam Token Factory `glm5.3-flash`, `POST /v2/chat/completions` |
| Job/report | `67096439-7ea1-4605-9a1d-8dac76e5c9c3` / `ab9eed84-eb89-4d33-a228-2eb34f762936` |
| Request outcomes | **12 attempted / 12 structured outputs accepted**, 0 errors, 0 retries, 0 uncertain resends, 0 fallback calls |
| Model stages | Planning 1; appraisal 8; comparison 1; synthesis 1; semantic support audit 1; all required AI operations accepted |
| Discovery/evidence | Crossref/OpenAlex: 40 candidate occurrences, 14 selected; 27 claims; 14 citation entries; 8 relationships; 0 hypothesis pairs |
| Source access | 11 abstract-only, 3 metadata-only, 0 full text; source appraisals: 10 assessed, 4 not assessed |
| Deterministic citation integrity | **27/27** claim/source/passage links valid |
| Semantic support | 8 report items assessed: F2/F5 partially supported, Q1 insufficient; other five marked supported, all model judgments unverified |
| Uncited-material scan | 0 flags but input truncated; completeness/recall not established |
| Browser | Real local browser opened the saved report and citation, displayed its passage and methodology, and downloaded the Markdown export |
| Token usage | 33,153 prompt; 9,288 completion; 276 reasoning |
| Cost | Provider-reported INR cost **not returned**. Veda conservative estimate/reservation **₹1.0386306 pre-tax** for this run; cumulative conservative reservations including earlier Sarvam calls **₹6.5873388 pre-tax**. Actual bill remains unknown; prices exclude GST and account settlement cannot be queried here. |

The user confirmed current Credits Left and Auto-recharge-off in Sarvam Settings → Billing. The runner recorded this as user-reported confirmation, not an independent provider balance query. The authorization was capped at ₹25 total with ₹20 internal pre-tax reservations and ₹5 for tax/rounding/uncertainty. This run stayed within the saved reservations. No further inference was sent.

### Actual report review

The report status is `completed_with_limitations`. Finding F5 says experience-focused field/interview studies discuss experience “rather than measured productivity outcomes”; its own semantic audit judged this only partially supported and identified that phrase as an inference. Qualification Q1 incorrectly generalizes all sources as abstract-only although three are metadata-only; the model audit judged Q1 insufficient. The uncited scan truncated its input. The report omits important directly contrasting Cui et al. workplace experiments and the METR experienced-open-source-developer RCT, and selected adjacent evidence with weak relevance. The guard added after the live run blocks the unsupported “rather than measured” assertion in future accepted synthesis, with offline regression coverage; it does not revise this already-saved report. See [`t126-live-report-quality-review-2026-10-31.md`](t126-live-report-quality-review-2026-10-31.md) for the source-by-source spot audit and primary references.

### Offline repair and regression results

- The live report-draft attempt returned `finish_reason=stop` but failed Veda validation at `findings.3.statement`; the response was rejected rather than partially accepted. Draft field limits/punctuation patterns were aligned to downstream report validators, and schema-constrained sanitized validation paths are persisted without unknown provider keys. Focused pipeline/provider/recovery tests passed.
- Budget recovery now reconciles a false legacy usage summary only when the durable POST counter matches and every actual POST has a Sarvam/GLM row with a valid estimated INR cost. Historical synthetic stop markers are excluded; missing, uncosted or mismatched POSTs still fail closed. Regression tests first reproduced both safe reconciliation and fail-closed cases.
- T-127 extends the local secret scanner to provider-prefixed names such as `SARVAM_API_KEY`. The CLI reports only path/line/rule. Its current filesystem scan checked 366 files and reported one expected local `.env` assignment without the value; `.env` was not modified. The scan is not recorded as clean.

### Final offline verification after changes

- Backend pytest: **510 passed, 2 PostgreSQL-only skipped**, 1 existing Starlette/httpx deprecation warning.
- Ruff check and whole-backend format check: passed, 152 files.
- SQLite migration round-trip and Alembic consistency: passed.
- Frontend Vitest: **23/23**; TypeScript/Vite production build: passed.
- Full Playwright suite: **46 passed, 15 opt-in skips** (managed-service and additional live-provider gates are intentionally skipped).
- Backlog validator: 66 requirements, 48 residual rows, 127 tasks (**116 DONE, 10 BLOCKED, 1 DEFERRED**); evaluation registry, benchmark-plan, annotation, research-audit, Render blueprint and backup/restore validators passed. Registry has 36 draft cases, 0 gold answers and no research-quality score.
- No PostgreSQL runtime, managed-auth service, external hosting, OpenAI inference, OpenRouter inference or subsequent Sarvam inference was used.

## 2026-10-31 T-128 offline retrieval-ranking repair

T-126's preserved discovery ledger showed a concrete ranking mismatch: *The Effects of Generative AI on High Skilled Work: Evidence from Three Field Experiments with Software Developers* was retrieved by the explicit empirical-study query but excluded by the source cap. Its stored broad-question score was `0.190909`; recomputing the same lexical method against the exact saved provider query produces `0.269231`. This comparison is only a deterministic lexical-feature replay; it is not a human relevance judgment or evidence-quality score.

Veda now persists a separate overlap feature record for the original question and the exact provider query. Eligible scholarly records use the maximum of these scores for source-cap ordering, with the broad-question score as the next tie-break. The broad-question topic-overlap gate remains unchanged. The API and browser display both component scores and the score used for ordering. Existing version-1 relevance records validate because the new nested fields are optional; there is no relational schema change or migration. ADR-0041 records the rationale and limitations.

The regression test first failed under question-only ordering, then passed with the change. It also confirms that high alignment to the executed subquery cannot bypass the original-question topic gate. The previously saved T-126 report remains unchanged, and no live or external provider request was made.

### Verification

- Full backend: **511 passed, 2 PostgreSQL-only skipped, 1 existing Starlette/httpx deprecation warning**. Command: `$env:PYTHONPATH = (Join-Path (Get-Location) 'backend'); uv run --project backend python -m pytest backend/tests -ra --tb=short` from repository root. After consolidating duplicate schema invariants into one helper, the 24 focused candidate/schema/source-cap tests and a second full backend run passed again (511 passed, same two PostgreSQL-only skips and existing warning).
- Ruff check and format: **passed, 152 files**.
- Frontend Vitest: **23/23**; production TypeScript/Vite build: **passed**.
- Candidate-library Playwright journey: **1/1 passed**, including both new score badges and ranking explanation.
- No migration round-trip was repeated because no ORM or database schema changed. No human relevance review or live-model run was performed. The new ranking's precision/recall and effect on future source coverage remain unknown.

The task graph is now **128 tasks: 117 DONE, 10 BLOCKED, 1 DEFERRED**; requirement coverage remains 66 requirements and 48 residual rows. Backlog validation passed with zero errors. Evaluation registry, benchmark, annotation, research-audit, Render Blueprint and backup/restore validators also passed. No Git-based code review was possible because the workspace has no Git repository; manual source/spec review is described in `docs/implementation-progress.md`.

## 2026-10-31 T-129/T-130/T-131 evidence-pipeline verification

### Implemented behavior

- T-129 stratifies bounded structured-document passage selection across Methods, Results, Limitations and other normalized sections before Abstract, then restores source order. Richer document resolution precedes abstract fallback, while abstract provenance remains separate. An unrelated CC-BY agriculture paper was retrieved through Crossref/OpenAlex plus Europe PMC JATS in a model-disabled local API/browser smoke; the actual Methods/Results passages and parser/rights provenance were inspected. It is parser integration evidence, not target-question evidence.
- T-130 partitions every complete report item and uncited-text window into deterministic bounded semantic-audit operations. Accepted batch outcomes and usage are persisted, uncertain POSTs are not resent, exact report/passage IDs remain validated, and incomplete input coverage blocks `EVIDENCE_VERIFIED`. Browser and Markdown report batch completeness. Model semantic judgment accuracy remains unevaluated.
- T-131 adds candidate abstract-retention status fields. Provider-wide OpenAlex CC0 is not treated as permission for externally sourced abstract text because official documentation separately flags external text, abstract reconstruction for legal reasons and per-location license scope. Candidate abstracts are omitted unless item/version rights are established; candidate identifiers, query, ranking features, disposition and exclusion reasons remain inspectable. The source-level selected abstract evidence path is still unresolved under blocker B-014.

### Verification after T-131

- Full backend after the continuation regression: **574 passed, 2 PostgreSQL-only skipped**. The skipped integration cases require a disposable PostgreSQL URL; no PostgreSQL runtime was available.
- Candidate-rights and continuation regressions: **11 passed**. SQLite Alembic upgrade/downgrade/re-upgrade and schema consistency: passed.
- Ruff check: passed. Ruff format check: **144 files already formatted** (`app`, `tests`, and `scripts`).
- Frontend Vitest: **23/23 passed**. TypeScript/Vite production build: passed.
- Candidate/source-inspector Playwright journey after T-131: **1/1 passed**. The previous one-worker full fixture E2E run for T-129/T-130 passed **48 tests with 15 opt-in skips**; the final T-131 browser journey was rerun directly.
- Requirement/backlog validator: **66 requirements, 48 residual rows, 131 tasks (120 DONE, 10 BLOCKED, 1 DEFERRED), zero errors**. Benchmark plan, annotation, evaluation registry, research-audit, Render Blueprint and backup/restore validators passed. The registry still contains 36 draft cases, zero gold answers and no research-quality score; the one annotation record remains `not_reviewed`.
- Secret scan checked **391 text files** and reported one expected `.env:1` secret-assignment rule. It printed no credential value; `.env` was not opened or modified. This is not a clean secret scan. Git ignore/index status cannot be verified in this workspace because it has no Git metadata.
- No new model inference, scholarly live request, paid service, deployment or external write was performed. T-126 remains the only accepted live AI research run; its 0-full-text coverage, F2/F5 partial support, Q1 insufficiency, incomplete uncited audit and missing Cui/METR counterevidence remain preserved historical limitations. No before/after quality score or human review is claimed.


## 2026-10-31 T-132 selected-source abstract evidence guard

- New selected-source records no longer persist unverified Crossref/OpenAlex abstract text or convert it into source passages/claims. Discovery uses provider text transiently for ranking; saved metadata records whether provider text was available and why it was omitted. Full-text extraction remains unchanged. Continuation children skip legacy abstract-only evidence graph rows, preserving parent records and full-text evidence.
- The selected-source and continuation regressions were red before implementation and green after. Four pipeline/recovery/passage-cap/restart tests were corrected to supply licensed full-text HTML fixtures rather than rely on abstract snapshots. Focused set: **4 passed**.
- Full backend: **575 passed, 2 PostgreSQL-only skipped**. Ruff check/format: passed, **144 files formatted**. Frontend Vitest **23/23**; TypeScript/Vite build passed. Source-inspector Playwright **2/2**. No migration was required.
- No provider inference or live scholarly request occurred. Historical abstract text remains stored and is still exposed by source/passage/claim/report/export representations. Rights were not established retroactively; B-014 remains open, and a separate read-policy task is needed. T-126 remains the only accepted live AI research report and remains abstract/metadata-limited.


## 2026-10-31 T-133 legacy abstract read/export policy

Historical records were retained in storage but their rights-uncertain abstract-derived prose was still returned by APIs and exports. The new exact-grant read policy withholds source excerpts, abstract-only/excerpt passages, derived claim text/spans/appraisal prose, report bodies/verification prose, and account/report exports unless a grant is bound to the exact source, version and text hash with the explicit retention/display scope. A separate source-index view keeps citation inspection possible while the report text is withheld. Source appraisal text is suppressed when an unverified source excerpt is present. The stored rows are unchanged; no migration was required. The report-level rule is deliberately conservative and can withhold the whole body when any job source has unverified abstract text.

A regression first failed because a source appraisal rationale repeated the legacy abstract text. Both abstract access labels, API/report/account exports, unchanged database rows, and exact-grant display are covered. Backend: **578 passed, 2 PostgreSQL-only skipped**. Ruff check/format passed (127 files). Frontend Vitest **23/23**, production build, five focused citation/accessibility/mobile Playwright journeys and one persisted-refresh journey passed. Backlog/evaluation/benchmark/annotation validators passed with **133 tasks (122 DONE, 10 BLOCKED, 1 DEFERRED), 66 requirements, 48 residual requirements, zero errors**. No provider request, live scholarly request, database migration, `.env` access or credential modification occurred.

This closes local text exposure, not historical rights adjudication: no qualified reviewer has established rights for legacy excerpts, and there is no trusted grant-authoring workflow. Exact-grant test fixtures are not legal verification. B-014 remains open. T-126 remains unchanged; T-133 does not establish improved scientific quality or target-question full-text coverage.


## 2026-11-01 T-134 OpenAlex availability metadata

- The bounded OpenAlex Works query now selects `has_content`; only strict `pdf` and `grobid_xml` booleans are persisted. `content_urls` are not requested, persisted, or followed. The source API and browser inspector present availability independently from retrieval, access class, and rights. No file download or migration occurred.
- Official OpenAlex documentation states that its content files retain original copyright and that API file downloads are metered at $0.01/file. This is not a blanket ban on acquisition. Veda's OpenAlex content-file request is not wired; a future adapter must reserve cost and verify work-specific rights before dispatch. Source review: `docs/research/openalex-fulltext-content-api-2026-11-01.md`; decision: ADR-0046.
- Tests: focused OpenAlex/provider-metadata **30 passed**; full backend **584 passed, 2 PostgreSQL-only skipped** (586 collected); Ruff check and format passed (**127 files formatted**); Vitest **23/23**; TypeScript/Vite production build passed; new source-inspector Playwright journey **1/1 passed**. No provider inference, OpenAlex content API request, credential access, or live scholarly request was made during T-134.
- Existing real full-text integration evidence remains the earlier T-129 model-disabled Crossref/OpenAlex metadata + Europe PMC JATS run: job `6c947443-45bc-4279-a576-356c6c155e27`, report `2b6d4208-fef0-4a61-8efa-49fdbd5c923a`, four selected sources/nine candidates/four citations and zero model calls. The unrelated CC-BY agriculture paper's Methods/Results passages and rights/parser metadata were inspected in the browser. This prior isolated DB was cleaned and the smoke does not establish target-topic retrieval or scientific quality.
- A failed first browser assertion was a fixture access-class mismatch, corrected without changing application behavior. The focused rerun passed. Generated trace files were retained.


## 2026-11-01 T-137 source-governance implementation and live metadata smoke

- Added a single strict registry, version `veda-source-governance-2026-11-01-v2`, with 23 institutional identities and empty university/journal ranking arrays. Added persisted candidate/source governance decisions, planned/searched/missing source-class coverage, API serialization and browser inspection. Source class, identity, relevance, study methodology, rights, evidence strength and truth remain distinct; no composite prestige score was added.
- Tests: source-governance suite **18 passed**; combined source-governance/Crossref/OpenAlex/workflow regression set **89 passed**; legacy candidate API compatibility suite **5 passed**; final full backend **623 passed, 2 PostgreSQL-only skipped** (one existing Starlette/httpx deprecation warning). SQLite migration round-trip/Alembic consistency passed; focused Playwright report citation/source-library/ILOSTAT inspector journeys **3/3 passed**; Ruff check/format passed for eight touched backend files; frontend Vitest **23/23** and production build passed. Backlog/evaluation/research-audit validators passed (138 tasks, 66 requirements, 48 residual rows; 36 draft cases, zero gold answers; 28 papers and 23 repositories). Regression for productivity-question source planning was observed red before adding multilateral/official-statistics cues, then green. First E2E run had 2/3 pass due fixture order and display-label mismatch; corrected and rerun 3/3. First full backend run exposed two legacy candidate fixtures lacking the new optional field; `_candidate_out` now treats governance metadata as absent for old objects, and the final full run passed.
- Live, read-only integration: Crossref's existing provider returned the real World Bank working-paper DOI `10.1596/1813-9450-10870` in a bounded query; Veda mapped prefix `10.1596` to World Bank and classified it academic + multilateral with verified identity provenance, while leaving methodology `not_assessed`. This was an adapter-level metadata smoke, not a persisted Veda report or quality judgment. A separate direct World Bank D&R API shape request returned HTTP 200 JSON; this was not performed through Veda and does not establish an integrated connector.
- Licensing/source coverage: QS official terms disclose CC BY-NC-ND restrictions, anti-scraping/non-reconfiguration, and commercial permission requirements. World Bank API terms restrict API-facilitated material use to non-commercial use absent permission. SCImago/JCR and FT50 reusable data terms remain unverified, so registry ranking arrays stay empty. Direct ADB, consulting, think-tank and general government publication adapters are not integrated. See `docs/research/source-governance-verification-2026-11-01.md`, ADR-0047, T-138 and B-016.
- No paid inference, full-text content download, credential access, or deployment occurred. No recall, precision, ranking coverage or scientific-quality score was measured. The historical T-126 report and T-136 full-text smoke remain unchanged.


## 2026-11-01 T-139 unseeded academic organization discovery and source-class planning

- A real model-disabled local browser/API run used only a research question, with no supplied organization names. It discovered University of Central Florida and Kangwon National University from OpenAIRE/OpenAlex publication affiliations; both were absent from the curated registry. Exact ROR IDs were verified, OpenAlex institution IDs were resolved, and bounded institution-publication searches returned three records. Off-topic institution-search records were excluded by the original-question eligibility gate. The actual report was persisted and opened in the browser.
- Artifact: `evaluation/veda-autonomous-holdout-query-repaired-20261101T163139.sqlite3`; job `22602d26-65c5-4550-bf5f-4e499c605941`; report `e064bc59-5237-42a1-98da-762d91f28adc`. Twelve bounded metadata requests yielded 29 candidate occurrences; 8 source records were selected. All selected records were metadata-only, with zero passages and zero claims; the deterministic report linked three citations but made no substantive claim. Semantic review and full-text retrieval did not occur. This is an academic identity/publication discovery smoke, not scientific or cross-sector success.
- The run planned only academic, multilateral, official-statistics and government classes under the then-current v1 policy. It searched academic metadata only. World Bank D&R was not dispatched because product-use confirmation was absent; Data360 was not dispatched because its topic gate did not recognize “renewable electricity.” Consulting, think-tank and government publication discovery did not run. The current source-class planner v2 now records matched question cues for energy/climate, trade/policy, business and regulatory questions, but connector availability remains separately disclosed.
- A potentially relevant India/SAARC renewable-electricity candidate was source-cap excluded at rank 16, with lexical overlap 0.272727. It is a human review case, not a proven relevant miss; no fixed retrieval insertion was made. Candidate/source discovery metrics remain `NOT_EVALUATED`: no independently reviewed organization/publication reference set or denominators exist.
- The code also persists verified public ROR identity facts and exact OpenAlex mappings separately from topic relevance, with 90-day freshness and tests for two-job cache reuse. ADR-0048 records this boundary. The small curated registry is a seed, not the source universe.
- Source-class planner tests: **19 passed** after adding energy, trade, regulatory and an unseeded health-domain case; the new planner records exact matched cues and `not_integrated` route states instead of implying search success. A red/green regression for energy/trade/regulatory planning was observed during implementation.
- A full Playwright run first passed 48, skipped 15 opt-in tests, and failed the report citation/source-inspector journey because the persisted `source_governance` coverage existed in the fixture but the report verification panel did not render it. Added report-level class coverage with planned/searched/missing states, candidate/selection counts, policy reasons, registry version and interpretation limits; typed the new `class_selection_reasons` field. The focused failing journey passed **1/1**, then the full one-worker suite passed **49**, with **15** managed-auth/live-provider opt-in tests skipped. Browser traces were retained.
- Latest full backend regression after the planner and organization-cache changes: **663 passed, 2 PostgreSQL-only skipped, 1 existing Starlette/httpx deprecation warning**. SQLite migration downgrade/re-upgrade and Alembic consistency passed. Frontend Vitest: **23/23**; TypeScript/Vite production build passed. Ruff check and format passed on the eight touched Python implementation/test files. The whole-repository Ruff check remains non-clean: **9 existing findings** in `backend/tests/test_security.py`, `evaluation/scripts/audit_retrieval_snapshot.py`, two OpenRouter route scripts, and four scripts under `scripts/`; whole-repository format check identifies **10 pre-existing files** outside the focused implementation. These unrelated lint/format issues were not changed. Implementation-backlog validator passed: **66 requirements, 48 residual requirements, 139 tasks (127 DONE, 11 BLOCKED, 1 DEFERRED), zero errors**.
- No inference, content-file request, or paid API request was made. These checks validate software behavior and browser rendering only; they do not close nonacademic discovery gaps, produce evidence passages in the T-139 holdout, or establish research-quality metrics.


## 2026-11-01 T-138 specialist publication evidence vertical slice

- Question-only, model-disabled run: “For UK offshore wind renewable energy projects, how should export-cable reliability, HVDC converter topology, capital cost, and transmission resilience be balanced?” OpenAIRE topic/affiliation discovery surfaced Offshore Renewable Energy Catapult (ORE Catapult), not present in the curated registry. Exact ROR identity `https://ror.org/03ffv2k10` was checked, and its linked official WordPress catalog returned two real ORE reports. Both remain metadata-only; their content rights were not assessed.
- Crossref/OpenAIRE located an ORE-affiliated paper, *Hybrid, Multi-Megawatt HVDC Transformer Topology Comparison for Future Offshore Wind Farms*, DOI `10.3390/en10070851`. Crossref deposited license metadata and an exact OpenAIRE DOI/title match recorded CC-BY. The selected Strathprints repository host had a reviewed, allowed host policy. Veda stored the hash-versioned PDF and 160 page-level passages from a 15-page file, selected it as S1, cited its evidence in the persisted report, and the real browser opened the citation and exact source passages.
- **Important limitations:** parser was pypdf, not GROBID; no Methods/Results section structure was extracted; the document/extraction is marked partial/truncated; the article-level UI still exposes `REQUIRES_REVIEW` on the failed Europe PMC JATS route. License metadata plus allowed host policy supported this acquisition path but were not an independent legal review. No methodological appraisal or scientific validation was performed.
- Artifact: `evaluation/veda-ore-openaire-vertical-20261101T220803.sqlite3`; job `3a5a3478-29f8-4ad7-99e6-ae1957226f79`; report `9c464875-dc5e-42a5-9ef3-56febe0b708a`. The job recorded 35 candidate records, 14 selected sources/citations, 171 source-claim records, no model calls and no AI-authored synthesis. Status is `completed_with_limitations`, deterministic evidence map.
- Source-level quality review: the retrieved article compares converter topologies in MATLAB/Simulink and reports a modeled loss/power-flow-sensitivity tradeoff. It does not provide field evidence of export-cable reliability or observed UK project costs. The report's source passage containing a 12% capital-cost figure cites references [3–5] internal to the article; those studies were not separately retrieved and the figure is not independently corroborated here. Thus S1 is relevant technical evidence for converter tradeoffs, not sufficient evidence for the full system-level question.
- GOV.UK exclusion diagnosis uses more than one preserved run. In `veda-govuk-identity-live-20261101T203601.sqlite3`, all ten candidates were excluded: the two stronger titles (offshore wind investment roadmap and transmission-network bill-discount scheme) had reason `source_limit`, while the other eight had `insufficient_topic_overlap`. In the later 22:08 report artifact, two of ten were selected metadata-only and eight remained lexical exclusions. Exact Organizations API records verify DESNZ/DBT identity, not publication method or quality. Candidate snapshots do not retain the GOV descriptions used transiently by some selection logic, and the excluded descriptions/attachment contents were not inspected. Thus these runs establish a source-cap effect for the first two and a metadata/lexical uncertainty for the other eight; they do not establish that every lexical exclusion is actually irrelevant. Potential broad policy context is a reviewer question, not grounds to force inclusion. The selected GOV publications are still metadata-only and their linked reports were not fetched. OpenAlex Works requests returned bounded 429 failures.
- Browser validation opened the persisted report from a copy of the SQLite artifact (preserving the original), inspected S1's passage/hash/host/license metadata and S12's GOV.UK directory identity and metadata-only status. The test made no scholarly rediscovery and no content request. A first report-list API call raced local sign-in; after waiting for workspace readiness, duplicate citation buttons were scoped to the first citation, and exact rendered text casing was corrected. Final focused persisted-report/browser test: **1 passed**.
- Focused runner/GOV provider regression: **37 passed**. Broad backend: **725 collected; exit 0; 2 PostgreSQL-only skipped**. Full serial Playwright: **49 passed, 16 opt-in tests skipped**. Vitest: **23/23 passed**. TypeScript/Vite production build passed. Focused Ruff check passed and format check reported **5 files already formatted**. Existing Starlette/httpx deprecation warning remains. No migration, inference, paid API or metered OpenAlex content request was made.
- This closes a single question→unseeded specialist identity→real publication→selection→full-text passage/report/browser path. It does not establish general consulting/think-tank discovery, research coverage/precision/recall, human review, or scientific reliability; those remain open under B-010 and B-017.

To repeat the browser inspection without re-running discovery, from `frontend/` in PowerShell:

```powershell
$env:VEDA_REAL_API_E2E = '1'
$env:VEDA_REAL_E2E_REUSE_DATABASE_PATH = (Resolve-Path '..\evaluation\veda-ore-browser-inspection-20261101.sqlite3').Path
$env:VEDA_REAL_E2E_REPORT_ID = '9c464875-dc5e-42a5-9ef3-56febe0b708a'
$env:VEDA_REAL_E2E_REPORT_QUESTION = 'For UK offshore wind renewable energy projects, how should export-cable reliability, HVDC converter topology, capital cost, and transmission resilience be balanced?'
npx playwright test e2e/real-api.e2e.ts --grep 'browser inspects the preserved ORE Catapult discovery report and full-text passage' --workers=1
Remove-Item Env:VEDA_REAL_API_E2E, Env:VEDA_REAL_E2E_REUSE_DATABASE_PATH, Env:VEDA_REAL_E2E_REPORT_ID, Env:VEDA_REAL_E2E_REPORT_QUESTION
```


## 2026-11-02 T-140 Crawl4AI Cloud public-web and publisher-content validation

### Question and live discovery

Question: “What technical and grid-integration challenges affect offshore hybrid renewable energy systems, and what evidence describes real-world implementations?” The user did not name the publisher. The isolated Veda job `558e7dd4-89a9-43bc-b5fe-282c23075fe9` recorded bounded Crawl4AI Cloud search and the generated question/domain query. Search returned mixed-quality leads (including unrelated/low-quality results that were not treated as evidence). The Frontiers article `https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2026.1779158/full` was on the verified `frontiersin.org` domain; exact ROR resolution identified Frontiers Media SA (`https://ror.org/00xhkbc10`). Crossref DOI/title/publisher metadata independently matched DOI `10.3389/fenrg.2026.1779158` and the article. This is unseeded academic publisher discovery, not proof of a nonacademic specialist or cross-sector search coverage.

### Acquisition and saved report

The follow-on model-disabled child job `1c5fd4f4-b1a8-4f68-bc14-f50842cd087e` persisted report `2e12fce2-3af9-4e89-a00a-4b49db9e6db9` in `evaluation/veda-crawl4ai-live-selector-retry-20261101T203315.sqlite3`. Source `45989805-2626-4850-8e58-7c953f31037f` is marked `full_text_html`, linked to the verified DOI and publisher URL, with document SHA-256 and 10 persisted passages. Before the Crawl4AI scrape, the existing host policy and robots checks succeeded and the source license signal was CC-BY. A read-only Playwright test opened the saved report and citation drawer and inspected the publication, passage text, host policy and rights/access fields; it made no Crawl4AI request. The child report citation-link integrity passed. The report has insufficient evidence status, zero model calls, no model-authored synthesis and `semantic_support_check=not_performed`; this is not a scientific-quality success.

### Request, cost, and failure ledger

- Successful child: one balance preflight, one `/v1/estimate`, and one `/scrape` HTTP request. Crawl4AI reported **0.25 credits** for `/scrape`; estimate usage/cost was unknown, so Veda retains a **1.0-credit unresolved reservation**. The provider-reported balance after scrape was 988.75 credits; Crawl4AI documents that balance snapshots can lag, so this is an observation rather than guaranteed current account balance.
- Prior page-shell attempt: one balance, estimate and scrape; provider-reported scrape charge **0.5 credits**. Its first extracted result was front-matter-only and failed browser verification; the database is preserved.
- The intervening estimate attempt returned HTTP 503; no scrape request followed. No automatic retry occurred. Provider docs state that a 5xx is uncharged. The offline fix and regression distinguish provider-confirmed noncharge from an uncertain timeout, release the former reservation only, and keep timeout reservations unresolved. It does not rewrite historical live artifacts.
- The parent search used one balance preflight and two bounded search GETs; the search ledger records **1.0 provider-reported credit** for that run. Other failed artifacts remain preserved. No Sarvam/OpenRouter/OpenAI inference, paid route, OpenAlex content-file request, payment endpoint, subscription, or top-up was invoked.

### Code and verification

The live run exposed a section-selection issue: query rank alone overfilled the passage cap with abstract text and allowed a bibliography line. The selector now picks query-relevant passages round-robin across document sections, excludes reference-style author/year lines, and records that retrieval ranking is not a support or quality judgment. A safe-fetch timeout now retains the host/robots access context only after those gates succeeded, allowing the bounded Cloud fallback without fabricating an ordinary-fetch body or hash. The Markdown heading cleanup regex was corrected so parsing failures do not silently erase passages. TDD added/fixed tests for timeout-gated fallback, credit-estimate 503 versus timeout accounting, bibliography exclusion, and section balance.

The actual saved browser artifact predates the final bibliography-selector fix and still contains one reference line. The final selector is unit/regression-tested but not live-re-extracted; no additional metered request was made to validate it. Earlier full-suite baseline before these last selector/accounting edits was **765 passed, 2 PostgreSQL-only skipped**. In this continuation: the Crawl4AI adapter HTTP-failure test passed **5 cases**; the bounded workflow matrix passed **4 cases**; frontend Vitest passed **23/23**; TypeScript/Vite build passed; focused Ruff check passed, and format check identified a formatting-only edit in `workflow.py` which is being corrected before final verification. The real saved-report Playwright inspection passed **1/1**. PostgreSQL tests remain unavailable without a disposable PostgreSQL URL.

**Current implementation gap:** T-140 is in progress. The bounded DOI-bearing fallback can proceed after Crossref title/publisher and same-domain full-text-link checks, but it has offline coverage only; unfamiliar non-ROR think tanks, consultancies, and specialist publishers remain unvalidated. Historical ORE Catapult discovery is a separate OpenAIRE/ROR/WordPress route; two ORE-authored reports remained metadata-only. This evidence does not meet the three-sector acceptance target or show a complete nonacademic organization → original publication → acquired evidence chain. Organization/publication recall and precision remain **NOT_EVALUATED** because no independently adjudicated reference set exists. See B-017 and T-140.

### 2026-11-02 T-140 offline non-ROR publisher-path correction

A red provider regression showed the official WordPress catalog adapter labeled every catalog record as ROR-verified. It now preserves the actual verifier: exact ROR, Crossref DOI/title/publisher/full-text-domain linkage, or a verified-organization-domain/catalog-record match. The output schema, source API and browser inspector preserve the distinct value. Workflow and source-inspector descriptions no longer imply ROR is mandatory or that publisher identity proves quality or rights.

Verification: the initial red case failed on the false ROR label; the focused workflow/provider/serialization tests then passed **6 tests**, with Ruff check passing. This is fixture-backed offline integration, not a live non-ROR organization result. The existing Crawl4AI real scrape remains the ROR-backed Frontiers report; its 0.25 reported credits and unresolved conservative reservation are unchanged. No additional Crawl4AI, Crossref, OpenAlex content, or model-inference request occurred for this change. T-140 remains in progress and cross-sector discovery is unvalidated.

### 2026-11-02 T-140 final academic full-text path and nonacademic holdout

The latest question-only, model-disabled E2E used an isolated SQLite database at `evaluation/veda-crawl4ai-offshore-browser-validated-20261102T031522.sqlite3`. Job `cb5921bb-8ed0-4d89-abdf-f31371417d0c` persisted report `d6889462-e5ec-492e-978a-9dc6966c1da3`. Crawl4AI discovered Frontiers Media SA, which was absent from the curated registry; exact ROR identity and Crossref DOI/title/publisher metadata independently matched the original article, *Offshore hybrid renewable energy: insights from real-world implementations* (DOI `10.3389/fenrg.2026.1779158`). Existing host and robots gates passed, the publisher license signal was CC-BY 4.0, and Crawl4AI retrieved publisher HTML. The source has a content hash and 10 persisted passages (including Methods and abstract/Results-reported material); 3 sources and 3 report citations were saved. Deterministic citation-link checks passed for 10 claims. The targeted real-browser test opened the saved report and inspected its citation, source-access/rights details and passages. This is a real academic-publisher content-to-report integration, not a nonacademic specialist demonstration.

The report is `completed_with_limitations`, insufficient evidence, with model provider disabled: zero inference requests, no model-authored synthesis and no semantic citation assessment. The article does not provide a Results section in the extracted structure; abstract-reported findings remain distinguishable. The two other selected scholarly sources are metadata-only and contribute no passages. This workflow does not establish scientific quality or answer the broader question defensibly.

A separate question-only India heat-policy holdout (job `109a5a55-ee9f-47bf-8482-ffe21b99ff37`, report `31e63006-9793-47ec-b2ff-aa038819843f`, artifact `evaluation/veda-crawl4ai-heat-policy-routed-20261102T032328.sqlite3`) discovered NatCen Social Research, an unseeded nonacademic organization, and resolved its ROR identity. It did not produce a verified relevant publication: the official homepage returned HTTP 403 and was not bypassed; site-search hits were geographically mismatched or lacked independent title/publisher evidence. PrepareCenter and CEEW candidates were ranked ahead of dated news after a selector regression fix, but Crossref identity checks returned HTTP 429. The report selected six scholarly records, all metadata-only (zero passages), including titles with weak lexical matches to the heat/health/Indian-worker question. These were not evidence analyzed. No organization was forced into selection. The diagnostic identifies a remaining relevance-quality issue alongside publisher-verification and rate-limit limitations; it is not solely a source-cap issue or a blanket copyright prohibition.

The latest successful academic run used one read-only balance preflight, two search requests (provider-reported total 1.0 credit), one estimate request with no reported charge, and one scrape request (0.25 credits reported); a conservative 1.0-credit scrape reservation remains unresolved. Across distinct saved Crawl4AI job ledgers scanned on 2026-11-02, 24 searches, 13 balance preflights, 2 estimate calls and 2 successful scrapes record 16.0 search credits and 0.5 scrape credits reported, plus 2.0 unresolved reserved credits. The latest stored balance snapshot was 2481.25 credits, but provider balance snapshots can lag. No paid inference, OpenAlex metered content, subscription, top-up or payment endpoint was used. `CRAWL4AI_KEY` was checked for presence only; its value was never displayed or modified.

After the final backend changes, full backend pytest passed **775 tests, with 2 PostgreSQL-only skips and one existing Starlette/httpx deprecation warning**. Frontend Vitest passed **23/23**, production build passed, focused Ruff check/format passed, and the targeted saved-report Playwright inspection passed. The broad serial Playwright fixture suite's last recorded result before the final UI label change was **49 passed, 15 skipped**; it was not rerun after that text-only change. The new lexical-eligibility regression first failed on the live dam-safety false positive, then passed with the directly relevant heat record still eligible; the full backend rerun includes this fix. PostgreSQL was not available. Cross-sector quality, organization/publication recall and precision remain `NOT_EVALUATED`; T-140 stays `IN_PROGRESS` and B-017 stays open.


### 2026-11-02 T-140 food-policy public-web holdout and planner correction

The question-only, model-disabled run used `evaluation/veda-crawl4ai-food-policy-e2e-20261102T043601.sqlite3` (job `1ec11634-727c-4e7c-8636-1abdd7e99d05`, report `36b733e9-8bd8-42bc-9dba-89b0a515eae4`). Two bounded Crawl4AI searches returned 17 hits and reported 1.0 search credits total. Exact ROR domain checks verified unseeded FAO and Frontiers identities; quality remained unassessed. Search surfaced a relevant UNU-WIDER publication page, but its domain did not resolve through exact ROR and the run did not verify its publisher relationship. FAO was selected for the single official-site search.

No official publication was verified. The FAO catalog request failed `response_too_large` despite the bounded WordPress result count and field projection. The metadata fallback selected an FAO URL that resolved to a not-found/home page and was correctly rejected. Crossref/OpenAlex recorded provider/rate-limit failures. The persisted report selected four metadata-only research sources, with zero extracted claims or source passages (excluding the synthetic browser fixture). Deterministic citation-link integrity had no broken links, but there were no material claims to assess. The report is `completed_with_limitations`; inference calls were zero, model-authored synthesis was absent, and semantic citation review was not performed. The targeted real-browser job/report journey passed, but no newly acquired FAO/UNU-WIDER evidence was available to inspect.

Offline TDD then fixed the source-plan omission: `policy`/`policies` now plans think-tank coverage independently of consulting and increments the planner version to v5. Official-site query normalization removes generic policy inflections, and the WordPress request is bounded to `per_page=limit` with a projection of used metadata fields. The regressions failed before the planner fix and the focused governance, organization-routing and official-site test modules passed afterward. These changes did not make FAO's live catalog operational. A bounded direct FAO DSpace metadata search (`/server/api/discover/search/objects`, size 3) returned HTTP 403; a separate `robots.txt` check timed out. No full-text fetch, Crawl4AI scrape, or content-rights decision was made. This is an observed API access restriction, not a blanket copyright prohibition on FAO material.

Final local verification for this continuation: backend **789 passed, 2 PostgreSQL-only skipped**, with the existing Starlette/httpx deprecation warning; frontend **23/23** and Vite production build passed; SQLite migration round-trip passed. Ruff check/format passed for changed files. The repository-wide Ruff invocation remains non-green due two existing E402 import-order findings in `backend/tests/test_security.py`, which this task did not modify. No paid inference or metered content request occurred. T-140 remains **IN_PROGRESS**: the Frontiers result is academic-publisher full-text evidence and the ORE Catapult report artifacts remain metadata-only; neither completes the missing nonacademic original-publication-to-permitted-content path. Cross-sector recall/precision remain `NOT_EVALUATED`.

### 2026-11-02 T-140 UNU-WIDER and IFPRI follow-up

Four question-only UNU-WIDER runs are preserved as `evaluation/veda-crawl4ai-unuwider-*.sqlite3`. They discovered UNU-WIDER and NBER, neither seeded in the curated registry; ROR exact identity checks classified both identities, without appraising their research quality. Crossref matched UNU-WIDER's genuine working paper *The political economy of food price policy: A synthesis*, DOI `10.35188/unu-wider/2015/006-5`, to the publisher. In the final browser run, job `02f76f8b-9e84-4f3e-ba6e-fbaf26ef5a7d` persisted report `3f592d35-2d5c-401a-b58d-d54753998070`; the report is `completed_with_limitations`, has eight source records and three citation-map entries, and includes this WIDER source as metadata-only with zero passages. The real Playwright workflow passed, opened the citation's source inspector and confirmed the organization/publisher provenance, metadata-only rights state, and absence of retained passages.

The highest-ranked DOI-less lead was WIDER's original Policy Brief, [How do governments respond to food price volatility?](https://www.wider.unu.edu/publication/how-do-governments-respond-food-price-volatility). The saved publication-verification attempt is `not_verified` with `error_code=access_denied`; an earlier run note attributes an HTTP 403 to `robots.txt`. Under the current implementation and RFC 9309, a robots-file 403 is `unavailable_4xx`, not a parsed `Disallow`, and the provider continues to the publication page. The saved artifact does not identify which endpoint produced `access_denied`, so the exact endpoint-level failure is unresolved. No page body was retained, no retry/bypass was attempted, and no `/scrape` call followed. The URL remains untouched pending independent evidence or an authorized safe alternative.

A separate question-only Myanmar food-price job `ff57cd80-e920-4f89-a975-77096f9ee3c4` persisted report `4b0e8b09-8b89-40ae-8fd6-5984c0e03187` in `evaluation/veda-ifpri-food-price-browser-20261102T070014.sqlite3`. Crossref returned three metadata-only IFPRI publications and an academic Foods paper was acquired as JATS with 12 passages. This did **not** verify IFPRI as a discovered organization or domain, discover an official IFPRI publication, or carry an IFPRI report into the report as evidence. Search leads on `myanmar.ifpri.info` and `cgspace.cgiar.org` were not joined to IFPRI based on name similarity. The run's saved source list therefore is not evidence of nonacademic discovery success.

Across these five preserved follow-up databases, 10 Crawl4AI Cloud `/search` requests reported **6.0 free credits** (5.0 across the four WIDER runs and 1.0 for IFPRI); no `/scrape`, paid model request, OpenAlex content-file request, or unresolved reservation was recorded. The last saved allowance snapshot is historical and can lag; it is not a live balance assertion. No full text was acquired from the WIDER site. No independent scientific review or retrieval-recall/precision evaluation was performed.

Regression fixes during this continuation: ROR domain matching now accepts exact HTTPS website links in addition to the domain field; official-site HTTP errors preserve 401/403/429/5xx classifications; official-page selection keeps the first eligible, query-ranked publication hit and avoids refetching an already Crossref-verified URL. The live E2E assertion now accepts `not_planned` for the optional World Bank route when the terms gate is not confirmed, while requiring no dispatch and no content fetch. Full backend suite reached 100% with **796 passed and 2 PostgreSQL-only skips** (798 collected; one existing Starlette/httpx deprecation warning); the focused changed backend set was 91/91. Frontend Vitest **23/23**, production build, temporary SQLite migration round-trip, changed-file Ruff, and targeted WIDER browser inspection passed. The full serial fixture browser suite passed **50 tests with 17 opt-in skips**. Repository-wide Ruff check still reports two existing E402s in `tests/test_security.py`; repository-wide format check still reports two unrelated files (`tests/test_security.py`, `tests/test_origin_rate_limit.py`), while all six changed backend files pass. T-140 remains **IN_PROGRESS**: the accepted nonacademic WIDER item is metadata-only, and no nonacademic institutional publication has yet produced permitted, persisted passages in the report/browser path.

Independent review noted that the live blocked-page branch only required a positive request count. It now requires exactly one request before stopping; the retained WIDER report records `request_count=1`, and `test_verified_publication_page_fails_closed_when_robots_disallows_fetch` asserts the sole transport path is `/robots.txt`. The duplicate metadata-only fallback lookup in the E2E file was consolidated. The changed provider regression set passed **30/30**, Playwright parsed all nine real-API journeys, and the production build was rerun. No new live request was needed.

### 2026-11-02 T-140 continuation — official-page item license and persisted HTML evidence

The general official-page metadata adapter now captures only an unambiguous item-level CC-BY 3.0/4.0 or CC0 license declaration (`rel=license` or recognized publication license metadata). The extraction workflow admits the body only when the organization identity and exact official publication URL are already verified, the page title/canonical and robots checks passed, the declared license matches a current exact-host review, and the existing bounded SafeHTML policy passes. It does not use a DOI or ROR as a mandatory condition at the extraction seam; absent/conflicting rights remain metadata-only. The accepted HTML body is persisted through the existing document hash, source-linked passage, claim, report, and citation inspection path. This is restricted reuse under the identified item license, not a general host-wide license. No migration or dependency was added.

Offline TDD covered recognized/missing/conflicting license metadata, exact host/domain/identity failures, and a persisted no-DOI/no-ROR source extraction with three substantive section-like passages and linked claims. Full backend pytest: **801 collected, 799 passed, 2 PostgreSQL-only skips** (one existing Starlette/httpx deprecation warning). Frontend Vitest **23/23**; TypeScript and production Vite build passed; changed backend Ruff check/format and SQLite Alembic upgrade/downgrade/re-upgrade plus schema check passed. The full backend run initially exposed four parameterized Europe PMC regressions from an unbound `provider_name` read; that field now comes from persisted source metadata and all four cases passed in the green full rerun.

Real-browser validation opened the preserved question-only report from `evaluation/veda-ore-openaire-vertical-20261101T215929.sqlite3` through a safe copy, `evaluation/veda-govuk-body-browser-copy-20261102T074922.sqlite3`. Job `f6fc51f9-5a51-4425-be54-75c678248aba` / report `03911823-0a6b-493f-8f00-de27553ef51a` contains the no-DOI Department for Energy Security and Net Zero *Offshore wind net zero investment roadmap*, source `40eeabe3-24b0-42be-8af7-a456e02502b3`, with `official_publication_page_body` access and **6** exact page-body passages. Citation `S1` maps to that source; the real browser opened the saved report and inspected the source drawer, provenance, exact locators and passage text. This proves the existing official-GOV body pathway and browser, not the new license-derived HTML route: it is a government policy roadmap rather than an independent specialist research study, and its historical report predates this change.

No new `/search`, `/estimate`, `/scrape`, paid inference, or metered OpenAlex content request was dispatched. Two read-only Crawl4AI balance attempts were made: first response returned but a local output script asked for a nonexistent `request_count` field and therefore did not record the balance; the second call failed with `request_timeout` after dispatch. A current available free balance and provider billing receipt are consequently **unknown**. No additional discovery search was made without a usable balance preflight. The DOI-independent specialist-report acceptance chain remains **not demonstrated live**; the no-DOI/no-ROR acquisition test is fixture-backed. The complete serial fixture-browser suite passed **50 with 18 opt-in skips**, and the targeted saved-report inspection passed **1/1**. T-140/B-017 remain open, the saved WIDER URL was not retried, and human scientific-quality evaluation remains `NOT_EVALUATED`.
### 2026-11-02 T-140 follow-up — WRI question-only publication lead and domain provenance

A model-disabled Veda job answered the question “How can Indian cities assess differential vulnerability to climate hazards and use the findings in climate adaptation planning?” without naming an institution. Preserved artifact: `evaluation/veda-t140-climate-discovery-20261102T084725.sqlite3`; job `21b901d6-c97d-4abc-acad-fd993ee6a7cc`; report `7debd60d-b656-4171-961a-72c2e6851223`. The run saved 8 sources and 3 citation-map entries; WRI's *Climate Resilient Cities: Assessing Differential Vulnerability to Climate Hazards in Urban India* (DOI `10.46830/wrirpt.22.00055`, source `40a71770-4767-4657-b5cc-45b59eaedd9e`) is cited as S2. The report is `completed_with_limitations`, with **0 passages, 0 claims, and 0 inference calls**. This is not evidence analysis or an AI-authored synthesis.

The two Crawl4AI Cloud searches found the question-relevant WRI lead and a domain-restricted WRI India result. Provider-reported use was **2 `/search` requests, 1 balance preflight, 1.5 search credits** (0.5 + 1.0), with 2.0 reserved and no unresolved reservation. No `/scrape`, paid inference, or metered OpenAlex request occurred. Provider snapshots reported `balance_credits` 961.75 and `allowance_left_credits` 2461.75; their discrepancy means a current usable balance is **unknown**. No further search was made.

ROR resolved World Resources Institute by exact name (`https://ror.org/047ktk903`), but the saved ROR identity record contains no official domains or official URLs. Crossref title/publisher metadata, a DOI record, its WRI India PDF link, and an eligible search hit support the organization identity and publisher-linked publication lead. They do not independently verify `wri-india.org` as an official domain. The initial saved record had overstated that domain as official. The code now preserves it as a publisher-linked candidate domain, leaves official domains empty unless the verified ROR record matches, and prevents an official-site query from running under that unverified domain. The API and browser relabel this historical field without changing the saved database. A newly found serialization boundary and a persisted-workflow regression passed.

The official-site publication route returned no verified official publication; one page-metadata attempt ended at `redirect_rejected`. Crossref reports no license for this work, and its PDF link is marked `intended_application=similarity-checking`, which is not Veda retrieval permission. The previously observed PDF is about 25.7 MB, above Veda's 8 MiB cap. Nothing was fetched. These are unresolved item/host permission and access conditions, **not a blanket prohibition** on WRI content.

A targeted real-browser test opened the persisted report from an isolated copy and inspected S2's organization provenance, publisher-linked domain label, metadata-only status and absence of passages (**1/1 passed**). The earlier live job/browser journey reached persistence but failed a stale assertion that required `VERIFIED_ESTABLISHED`; the actual status was `VERIFIED_DOMAIN_SPECIALIST`. The assertion was corrected, but the live job was not repeated to avoid another search charge. The saved-report inspection above is read-only apart from local-development authentication.

Also fixed Crossref source typing for records whose deposited Crossref type is exactly `report`; the existing WRI snapshot remains unchanged because its deposited type is `journal-article`. Final offline checks: backend **806 collected, 804 passed, 2 PostgreSQL-only skipped**, exit 0; changed-file Ruff check/format passed; frontend Vitest **23/23** and production build passed. PostgreSQL validation remains skipped. T-140 remains open: no unfamiliar nonacademic publication has yet supplied permitted, substantive passages in a saved report.

### 2026-11-02 T-140 rights-policy review and regression follow-up

The earlier CC-BY/CC0 requirement on several fetch paths was a conservative Veda reuse policy, not a universal legal requirement to cite or privately analyze every work only when it carries a CC license. The new deterministic rights matrix keeps discovery/metadata, automated access, analysis, retention, and sharing separate. It preserves the CC and exact reviewed-host paths, and applies an India private-research exception candidate only when the operator sets `RIGHTS_USE_MODE=private_research` and `RIGHTS_JURISDICTION=IN`, the publisher/publication identity and official domain are verified, the item is classified as an institutional report or scholarly article, public HTTPS and the robots outcome pass, site terms are screened, and no item-specific restriction signal is detected. Unstated licensing alone does not block that narrow route, but it does not establish universal permission. The profile retains at most four passages / 1,200 verbatim characters and keeps sharing citation-only. Unknown work types, official-statistics records, press releases, software, unsupported jurisdictions, restrictive/inaccessible terms, and unresolved identity remain metadata-only or review-required. This is an operational policy, not legal advice; a qualified legal review is still needed before treating the configured profile as a legal determination. The official Indian Copyright Office describes Section 52(1)(a)(i) as fair dealing for private or personal use including research, but that text does not decide the application of the exception, contracts, access conditions, or amount/retention in a particular case. [Official section 52 text](https://copyright.gov.in/Copyright_Act_1957/chapter_xi.html)

Bounded official-page inspection stores fixed item-restriction codes and whether a copyright notice was observed; it never stores the notice text and does not interpret it with a model. Item restrictions override a general item-license signal and block content processing pending review. A direct document 401/403 remains terminal; a robots-file 4xx is recorded separately as RFC 9309 “unavailable,” while robots 5xx/network failures remain fail-closed. The robots decision is not a copyright grant. The prior UNU-WIDER robots HTTP 403 was not retried. Citation-only passages remain inspectable inside the configured private workspace, but report/account exports suppress report prose when a cited restricted source has passages; incomplete citation provenance fails closed, while an unrelated, uncited restricted source no longer suppresses a fully attributed report.

The initial targeted suite found three fixture failures because SafeHTML/PDF tests omitted the newly required `institutional_report` work classification; those fixtures now state the work type explicitly, preserving fail-closed behavior for unclassified material. The subsequent focused set passed **28 tests**. The complete backend suite passed **832**, with **2 PostgreSQL-only skips** (834 collected) and the existing Starlette/httpx deprecation warning. Frontend Vitest passed **23/23**, TypeScript/Vite production build passed, the full serial Playwright suite passed **51** with **19 opt-in live/provider/auth tests skipped**, SQLite migration upgrade/downgrade/re-upgrade and Alembic check passed, and changed-file Ruff check/format passed. The repository secret scanner reported one local `.env` assignment without revealing its value; `.env` is ignored and excluded from the staged set. A staged-content scan remains required before commit.

No live unlicensed publication, Crawl4AI request, source-content request, model inference, or metered OpenAlex request was made in this follow-up. There is no new external evidence that an unlicensed source is legally usable; the real-world source coverage effect remains unmeasured. T-140 and B-017 remain open for the live unseeded nonacademic publication → permitted content → passage → saved report/browser demonstration, and no scientific-quality or legal-certainty claim is made.

### 2026-11-02 T-140 private-use configuration, terms outcomes, and saved-run funnel

The repository `.env` and current process had neither `RIGHTS_USE_MODE` nor `RIGHTS_JURISDICTION` configured. `Settings` defaulted to `private_research` with an empty jurisdiction, so the jurisdiction-specific private profile did not apply in an ordinary local run. The isolated model-disabled browser/API launcher now explicitly sets `RIGHTS_USE_MODE=private_research` and `RIGHTS_JURISDICTION=IN`; a regression clears and reloads `get_settings()` after launcher setup and verifies those effective values. The setting is limited to the disposable test launcher; no `.env` or production default was changed. The workflow passes these settings into `evaluate_rights` at extraction. This confirms configuration plumbing, not legal applicability.

Terms-state review found that request failures were already fail-closed and were not being labeled `not_found`, but multiple failures were collapsed into `unavailable`, and an empty/script-only 200 HTML body was incorrectly treated as a completed check with no restriction signal. The provider now distinguishes `access_denied`, `lookup_failed`, `parsing_inconclusive`, `robots_disallowed`, `restriction_signal`, `checked_no_restriction_signal`, and `not_found`. `not_found` is emitted only after the bounded terms paths actually queried return 404; an empty, too-short, or branded soft-404 visible body is inconclusive; a regression covers a navigation shell with a page-not-found message. These are signals for the policy engine, not a license grant. The private profile continues to require either a completed no-signal check or a completed bounded not-found check; all unresolved states remain metadata-only/review-required.

Read-only replay of three preserved question-only runs produced this operational funnel. Counts are workflow records, not independent relevance judgments; candidate deduplication is per job, and the three artifacts predate the new rights policy.

| Stage | Count | Interpretation |
|---|---:|---|
| Crawl4AI search hit records | 51 | 20 energy, 16 food-policy, 15 urban-climate |
| Distinct scholarly publication identities | 34 | Sum of per-job canonical identities in the discovery ledger; not global deduplication |
| Automated source selections | 19 | Passed Veda's source selector; substantive relevance was not human-reviewed |
| Publication-verification attempts | 8 | Includes repeat/failed page checks |
| Fully corroborated publisher identity + official domain in the accepted evidence path | 1 | Frontiers; WIDER organization identity lacked an official domain in its saved record, and WRI remained publisher-linked only |
| Unique Crossref-backed publication/publisher relationships | 3 | Frontiers article, UNU-WIDER working paper, WRI report; the WRI record was duplicated in one run |
| Content-confirmed accessible publications | 1 | Full text was actually returned through a permitted route; other institutional report access was not established |
| Full-text acquisition attempts | 4 | 1 HTML attempt and 3 JATS attempts |
| Eligible under the new private-research profile | 0 | No saved case records a decision from this policy; one academic CC-BY source used the existing license route |
| Content-returning full-text acquisitions | 1 | Licensed Frontiers HTML; the other three acquisition attempts were unsuccessful JATS lookups |
| Sources yielding substantive saved passages | 1 | 10 passages and 10 linked claims |
| Sources cited with browser-inspectable passages | 1 | Frontiers source inspector passed in the preserved report |
| Private-profile decisions in these saved runs | 0 | All three runs predate the rights policy; no live unlicensed decision was recorded |

The institutional outcomes explain the loss: the DOI-less UNU-WIDER brief verification persisted `access_denied`; the earlier robots-file 403 note is not itself a parsed robots prohibition under RFC 9309, and the saved run lacks endpoint-level detail to resolve the exact cause. The WIDER working paper remained metadata-only. The WRI report's publisher-linked host was not independently established as an official domain, its official-page route did not verify, and the linked PDF was about 25.7 MB versus Veda's 8 MiB limit. None of these saved reports contains terms-check outcomes, so they cannot establish the rights-policy effect. The dominant observed loss is institutional publisher/domain and publication-page verification, followed by an acquisition-size constraint—not missing-CC rejection. The one successful full-text source is academic and CC-BY, so it does not satisfy the nonacademic acceptance target.

The three historical jobs made six Crawl4AI `/search` requests and recorded 3.5 credits (1.0 energy, 1.0 food, 1.5 climate); no model calls were recorded. Balance snapshots from prior attempts disagree and the latest read-only preflight timed out, so current free allowance remains unknown. No new search, scrape, inference, OpenAlex content request, or document acquisition was sent. T-140 remains open pending a balance-confirmed, bounded live case from an unfamiliar nonacademic publisher; do not retry the robots-denied WIDER URL. Current code verification: focused provider/rights/launcher tests passed; full backend run collected 847, exited 0 with 845 passed and two PostgreSQL-only skips plus one existing Starlette/httpx deprecation warning; frontend Vitest 23/23 and production build passed; serial Playwright 51 passed/19 optional live/auth tests skipped. No schema migration was required.

### 2026-11-02 T-141 — question-adaptive sufficiency and independence accounting

The saved report workflow now adds a question-adaptive sufficiency extension beside the historical v1 check. It derives evidence criteria and material requirements from the question, persisted scope, and saved planner subquestions; it does not use a universal publication quota. Question-planned source classes must be searched or explicitly resolved before a strong status is possible. Broad/high-inference/multi-requirement profiles conditionally ask for corroboration and counterevidence, and corroboration must support each material requirement. This two-investigation floor is an operational heuristic, not a validated scientific standard and is not sufficient by itself. Metadata-only records and multiple passages/versions of one work do not count as independent investigations. DOI/canonical identity and cautious DOI-less title/year/author-or-publisher identity group work versions; independence, shared investigations, dataset overlap, and review synthesis require explicit reviewed evidence. The current workflow has no reviewed independence records, so actual independence remains unknown. Reports with content but incomplete support are preliminary; no content or no material assessment is insufficient. The existing verification panel shows this result and per-requirement coverage while retaining v1 compatibility.

**Frozen planner transferability check (v3):**

| Case | Question | Offline plan result | Outcome / limitation |
|---|---|---|---|
| V3-1 | What evidence links changes in hospital shift length to medication errors in adult intensive-care units? | Classified descriptive/bounded; did not identify association or require cross-study corroboration. | Planner miss: it omitted the relation/design evidence dimension. No live discovery or evidence report was run. |
| V3-2 | What are the annual rates of informal employment in Brazil by age and gender since 2010? | Classified descriptive/broad; requested measurement/denominator and time-series comparability; no independent-study quota. | Appropriate distinction for a primary time series, but no source discovery or statistical series was retrieved in this check. |
| V3-3 | How do municipal flood-control investments compare across lower-income and wealthier neighborhoods in coastal cities? | Classified mixed/broad; requested comparative/mechanism/counterevidence dimensions and corroboration. | Planner-only pass; no source discovery or evidence sufficiency was measured. |

V1 H1–H3 were inspected during implementation and V2 was used diagnostically; they are not reported as untouched holdouts. No reference publication set or independent scientific review exists, so recall, precision, and research-quality scores are not calculated.

**Post-repair offline relation-language replay:** V3-1 now profiles as comparative and includes association-design, independent-investigation, and counterevidence dimensions. The frozen v4 cases were authored before the initial repair; V4-3 was then used to diagnose a remaining “track differences” cue, so v4 is diagnostic rather than an untouched holdout. After adding generic tracking/alignment association cues, all three v4 cases were replayed: V4-1 was mixed/bounded, V4-2 comparative/underspecified, and V4-3 comparative/broad; each included association/design and conditional corroboration dimensions. This is a planner-only observation, not discovery, retrieval, sufficiency, or scientific-quality validation. No question string, expected source, organization, or publication is in production code.

**Read-only replay of four preserved research databases:** the climate run had 26 discovery candidate records, 9 source records (8 metadata-only and 1 abstract-only), one retrieved document, one abstract passage, no claims, and two reports. Food policy had 8 candidate records, 5 source records (4 metadata-only and 1 abstract-only), one retrieved document and abstract passage, no claims, and two reports. The UNU-WIDER run had 25 candidate records, 9 source records (8 metadata-only and 1 abstract-only), one retrieved document and abstract passage, no claims, and two reports. The offshore run had 10 candidate records, 4 source records (2 metadata-only, 1 abstract-only, 1 full-text HTML), two retrieved documents, 11 passages (1 abstract and 10 full-text), 10 claims, and two reports. Across these artifacts: **69 candidate records, 27 source records, 5 retrieved-document records, 14 passages, 10 claims, and 8 reports**. These are stored workflow counts, not independent relevance judgments; the reports predate T-141 and contain no adaptive v2 decision. Only the offshore case yielded full-text passages, and that source was academic. The specialist nonacademic evidence target remains unmet. Independence of these stored works was not adjudicated.

**Validation:** after a full-suite run exposed the synthesis prompt at 24,340 characters against its existing 24,000-character regression bound, the model input was reduced to requirement IDs and text rather than duplicating each requirement's purpose, and the added instruction was made concise. The regression then passed. A red regression also identified missing association appraisal for tracking-language questions; generic tracking/alignment cues now trigger that appraisal. The final backend suite collected **874**, exited 0 with **872 passed, 2 PostgreSQL-only skips, and 1 existing Starlette/httpx deprecation warning**. Changed-file Ruff check and format passed (11 Python files); frontend Vitest **23/23**, TypeScript/Vite production build passed; serial fixture Playwright **52 passed, 19 opt-in skips**; isolated SQLite migration round-trip/schema check and backlog, evaluation, annotation, benchmark-plan, and research-audit validators passed. No migration was added. The first frontend test invocation used a nonexistent `test:run` script and was immediately corrected to the repository's `npm test`; the valid test command and build passed.

No live provider call, Crawl4AI request, document acquisition, paid/metered content request, or model inference occurred in this continuation. Current Crawl4AI free balance remains unknown from the prior inconclusive balance checks. Historical provider usage above is not a current balance. These software checks do not validate scientific accuracy, legal interpretation, retrieval completeness, or independent investigation relationships. The pre-repair V3-1 miss remains as a frozen baseline; no untouched post-repair holdout, reviewed independence facts, adaptive v2 records in the preserved runs, or live/nonacademic source evidence are available.

### T-140 continuation — institutional report acquisition dispatch (2026-11-02)

**Read-only conversion funnel across four preserved question-only jobs:** 79 discovery-candidate occurrences → 46 distinct identities after per-job deduplication → 29 selected source records → 2 retrieved documents → 170 stored passages → 181 extracted claims → 4 reports / 29 citations. Four selected institutional report sources (two official-site catalog records and two GOV.UK records) produced zero passages. Only two source records were cited with source-linked passages, both scholarly. These historical records predate this dispatch fix; counts are database records, not independent relevance judgments, and claims were extracted statements rather than semantic support adjudications. Thus the largest demonstrated structural loss in this replay was before acquisition dispatch for institutional catalog records; the sample does not establish that this is the only or globally dominant research bottleneck.

The extraction workflow now verifies a selected official WordPress-catalog publication page when persisted organization identity and official domain are verified, records title/canonical, robots, terms/license and access provenance, and then routes successful pages into existing rights-gated safe HTML retrieval. Denials and incomplete verification remain metadata-only. A red integration test observed zero verification calls before the fix; the success and access-denial regression plus four existing official-page/provider regressions passed (5 total). No new dependency, schema, or institution-specific production rule was added.

**Live saved-source replay:** existing ORE Catapult report metadata was replayed through the normal Veda API/job/report workflow, without new discovery search. No new question or discovery search was submitted; the saved research job concerned UK offshore-wind transmission choices. The previously stored candidate was “Cornwall FLOW Accelerator: Optimised cable connection options for floating offshore wind” at the CMS ORE Catapult host. The isolated report contained one metadata-only citation and zero retrieved documents, passages, or claims. Two bounded public HTTP requests found the CMS `robots.txt` endpoint redirecting to the root HTML page; it failed the expected robots content-type check, so the publication body was never requested and no rights decision was inferred. The URL was not retried or bypassed. This validates persistence and a safe failure path, not successful nonacademic evidence acquisition or browser passage inspection.

No Crawl4AI, model, OpenAlex content, or paid request was made. Crawl4AI's available balance remains unverified, so no fresh question-only discovery was attempted. The complete nonacademic question → verified official publication → permitted content → passages → browser-inspected citation acceptance remains unmet. Offline mocks are not live research evidence.

**Final local verification for this continuation:** backend full suite collected **876**, exited 0 with **874 passed / 2 PostgreSQL-only skipped** and one existing Starlette/httpx deprecation warning. Changed-file Ruff check and format passed. Repository-wide `ruff check .` still reports two E402 import-order violations in untouched `backend/tests/test_security.py`; repository-wide format check reports existing formatting differences in untouched `backend/tests/test_security.py` and `backend/tests/test_origin_rate_limit.py`. Vitest **23/23**, production TypeScript/Vite build, and serial fixture Playwright **52 passed / 19 opt-in skips** passed. Backlog, evaluation registry, benchmark plan, and annotation validators passed. A post-review red regression also found the extraction-stage aggregate omitted failed page-verification requests (0 recorded versus 1 dispatched); the counter now includes bounded attempts on success and failure, and the test passes. No schema change was made, so no migration was needed for this route. Current source changes were not tested against PostgreSQL.

## 2026-11-02 acquisition-failure attribution, PDF capacity, and MCP experiment

### Saved-source conversion evidence

The saved runs use different artifact sets and must not be merged into one funnel. The T-141 replay across four preserved research databases measured 69 candidate records → 27 selected source records → 5 retrieved-document records → 14 passages → 10 claims → 8 reports. Only one academic source had full-text passages; all runs predated the adaptive sufficiency policy. The later T-140 four-job replay measured 79 candidate occurrences → 46 per-job-deduplicated identities → 29 selected source records → 2 retrieved documents → 170 passages → 181 extracted claim records → 4 reports / 29 citations. Four selected institutional report records produced no passages; only two source IDs cited with passages were scholarly. The aggregate counts are records, not independently adjudicated relevance or evidence-quality judgments.

A separate three-case saved-run replay had 51 Crawl4AI hits, 34 per-job-unique scholarly identities, 19 automated selections, 8 publication-verification attempts, 3 unique DOI-backed publisher/publication relationships, and 1 full-text source with 10 passages and browser inspection. These are separate measurements from a different replay boundary and do not establish general recall or conversion rates. Across the inspected institutional failures, later stages such as rights evaluation, body acquisition, PDF parsing, claim support, and source independence are often absent rather than negative outcomes:

| Case | Last demonstrated stage | First recorded failure / reason | Content attempted? | Attribution |
|---|---|---|---|---|
| ORE Catapult institutional report | Candidate and official catalog publication lead | `robots.txt` URL redirected to root HTML; `unexpected_content_type` after two bounded requests | No publication body or PDF request; no rights decision | Robots endpoint/content validation; not parser or document-level prohibition |
| WRI report/PDF lead | DOI metadata and publisher-linked host observed | Official domain was not independently verified; item had no license and link was marked for similarity checking | No page body or PDF request | Identity/route and authorization unresolved; the old 8 MiB cap was a downstream technical constraint only |
| UNU-WIDER working paper/brief | Organization and metadata leads | Working paper stayed metadata-only; a historic `access_denied` brief record lacks endpoint-specific attribution | Brief URL was not retried; no permission inferred | Exact robots-versus-document status remains indeterminate |

The largest demonstrated loss in the inspected sample occurs before document-body acquisition, at institutional publisher/domain/page verification and route resolution. The sample does not establish a global bottleneck rate. No institutional report reached the parser in the ORE/WRI replays, so those outcomes cannot be reported as extraction failures. A separate ORE-affiliated academic paper has previously produced a page-located PDF evidence artifact; it is not an ORE institutional report.

### T-142 PDF capacity change

The previous `MAX_PDF_BYTES` was 8,000,000; it is now 32,000,000 bytes. The downloader streams bounded chunks to an ephemeral file, updates SHA-256 while streaming, validates size/signature, and sends the path to the existing isolated parser subprocess. This removes the production downloader's need to materialize the entire response and copy it again for pypdf. The temporary file is cleaned on success and exceptions. GROBID's separate 8 MiB input ceiling remains; larger files use pypdf. Existing page-tree (500 entries), extracted-page (40), per-page (4,000 characters), total-text (60,000 characters), decoded-stream (1,000,000 bytes), decode-work (12,000,000), parser (30 s) and total-document (45 s) limits remain.

A synthetic padded 25,700,000-byte PDF with 42 text pages was processed by the current worker: 40 pages extracted, 42 page count reported, `truncated=true`, approximately 9.1 s wall time, approximately 4.35 MiB worker peak working set and 1.67 MiB parent peak delta during worker execution. The padding makes this a parser-path capacity probe, not representative PDF compression or a real research report. It did not measure network streaming memory, page-layout quality, tables/figures, scanned-document handling, or actual publisher acquisition. A large live document was not eligible or fetched. The source download/storage error distinction now has a red/green test for file-close errors versus transport errors.

### T-143 MCP feasibility

The optional `mcp==2.3.0` SDK extra adds no base application dependency. The local stdio server reuses the authenticated, owner-scoped API and exposes three read-only tools: source/passage search, source provenance, and passage retrieval. It exposes no raw-document fetch and does not access the database directly. The external disclosure gate requires a full-text record, item-level CC-BY 4.0 or CC0 evidence, `PERMITTED` analysis, license-scoped retention/sharing, and document/passage hashes. Private-research-only and unverified-license text is withheld. Search output is bounded to six source results, two passages/source, 1,200 characters/passage, and 4,000 total passage characters.

The official SDK in-memory client and stdio transport client tests pass against isolated fixtures, including a genuine JSON-RPC initialization/list/call sequence and a source-linked exact passage/locator/hash. This is protocol-only validation, not Claude Desktop/Code, ChatGPT, hosted LLM, or production-client integration. MCP reuses evidence; it does not improve discovery or document acquisition. Veda remains a hybrid standalone application. The current client fit was checked against the [MCP stdio/HTTP transport specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports), [official Python SDK](https://github.com/modelcontextprotocol/python-sdk), [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp), and [ChatGPT custom MCP connection requirements](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt). In particular, the documented ChatGPT connection uses a public HTTPS MCP URL or supported Secure MCP Tunnel plus eligible workspace support; local stdio does not connect directly to cloud ChatGPT. No remote hosting/OAuth, client-specific connection, or durable MCP audit table was added. T-144 later adds an optional client-neutral research Skill; it is not a protocol extension or external-client integration.

### 2026-11-03 T-144 — final verification

The bounded relevance feature and MCP candidate ledger passed the full backend suite: **912 passed, 2 PostgreSQL-only skips** (disposable PostgreSQL URL unavailable). Changed-file Ruff check and format passed (**10 Python files**). Frontend Vitest passed **23/23**, and the TypeScript/Vite production build passed. The final serial fixture Playwright run passed **54, with 19 provider/auth-gated skips**; it includes the opt-in composer and candidate-ledger display. During earlier validation, the source-ledger journey exposed a stale copy assertion and was corrected; a separate auth journey timed out once in a full run, passed isolated, and passed in the final full run. The focused overlong-URL regression failed before the fix and passed afterward. Backlog, evaluation registry, benchmark plan, annotation and research-audit validators passed. No schema migration was required.

No Crawl4AI, public-web, content, external MCP-client, or model-provider request occurred; provider/model cost was **$0** for this continuation. The AI relevance workflow was exercised only with deterministic fixtures/mocks. D1 was diagnostic; H1/H2/H3 remain unrun transferability holdouts and have no independently reviewed relevance labels. No relevance precision/recall, acquisition improvement, scientific quality, or live end-to-end research benefit is established. The existing T-140/B-017 nonacademic acquisition blocker remains open.

### External usage and remaining acceptance

No Crawl4AI request, balance request, OpenAlex content call, external PDF request, model inference, or paid service was used in this continuation. Current Crawl4AI free allowance remains unknown, so no new search was sent. Historical provider charges/reservations were not modified. T-140 remains `IN_PROGRESS`: no newly acquired unfamiliar nonacademic original institutional report reached permitted full text, passages, and current browser inspection. No scientific quality, independent-study count, legal conclusion, or generalized source-coverage score is claimed. Current test results and secret-scan outcome are recorded in the final verification addendum below.

### Final verification addendum — 2026-11-03

The source-provenance API now has a separate locator-only projection: it selects no passage-body column, returns at most 50 locator records, and reports total/has-more counts. MCP source provenance and one-passage retrieval use that endpoint, so they no longer transfer every passage body into the MCP process. A red API regression first returned 404 for the new route; the owner-scoped projection and route were then implemented, and the source-provenance/MCP protocol suite passed **6/6**. The full backend suite on the current code passed **886**, with **2 PostgreSQL-only skips**, in 184.98 seconds. No PostgreSQL service was available.

Final checks: changed backend Ruff check passed; changed-file formatting passed (**9 files**); Vitest **23/23**; TypeScript/Vite production build passed; full serial fixture Playwright **52 passed / 19 gated skips** against the unchanged UI before the backend-only locator endpoint; targeted citation-inspector Playwright **1/1** passed again after that endpoint; backlog, evaluation registry, benchmark plan, annotation and research-source audit validators passed. Backlog state is 143 tasks: 131 DONE, 10 BLOCKED, 1 DEFERRED and T-140 IN_PROGRESS. Evaluation has 36 draft cases, 0 gold answers and no research-quality score; the selected benchmark source set is not finalized; the single annotation remains not reviewed. No migration was needed because no ORM schema changed. No live publisher or provider request, paid/model call, or Crawl4AI/OpenAlex-content call occurred. The ORE/WRI/WIDER failures and separate saved-run funnel counts above remain the real-world evidence boundary.


### Live bounded question-only check — 2026-11-03

Question: “How can Indian cities assess unequal vulnerability to urban heat and flooding, and what adaptation strategies have empirical or institutional evidence?” The user supplied no organization or URL. The effective normal config had Crawl4AI disabled and the model provider disabled; the isolated harness enabled bounded Crawl4AI discovery only (maximum 2 search requests / 2 credits, scrape disabled). The GET-only balance preflight reported community, free balance 961.75 and allowance-left 2500 credits. One search returned 10 hits for a reported 1.0 credit; response headers reported free balance 960.75 and allowance-left 2460.75. The allowance-left discrepancy is retained as unresolved and is not interpreted as 39.25 credits spent.

Funnel for this run: 10 web hits; 10 routed domain candidates (6 eligible for identity checks, 1 aggregator excluded, 3 over candidate capacity); 6 exact-domain ROR checks, all not found; 0 verified organizations; 0 verified official publications; 0 publication-verification attempts; 0 official-domain publication searches; 8 selected scholarly metadata-only source records; 0 retrieved documents; 0 substantive passages; 0 claims; 3 report citations. NIUA's “Climate Change Adaptation Actions in Indian Cities” at https://niua.in/publication-details was only an unverified search lead. Thus no identity, publication, rights, access, acquisition, or extraction success is claimed. The persisted job is 3c9b95ce-52e8-4129-98c2-41b606345ceb, report 057752af-f350-4141-9065-4adb3749bb89, database evaluation/veda-crawl4ai-question-only-20261103T002549.sqlite3 (ignored and not committed).

The targeted live Playwright run exited 1 after the report was persisted: stale/over-specific expectation not_applicable_explicit_uk_geography_required differed from API status not_planned for an India question. It failed before the source-inspection step; this report was not browser-inspected. Crossref returned one 429 and coverage persisted one OpenAIRE failure. No Crawl4AI scrape, model inference, OpenAlex content download, paid call, or repeated search occurred. The live result confirms that the current bottleneck is organization/publication verification routing, not document parser performance. It does not establish scientific quality or full-text success.


Browser regression follow-up: for the live India question, saved source coverage planned academic only, making GOV.UK not_planned; the smoke test had hard-coded not_applicable_explicit_uk_geography_required. The assertion now follows the persisted class plan. Fixture-only Playwright after this test change: 52 passed, 19 gated skips; Vitest 23/23; TypeScript/Vite build passed. The original live test result remains failed before source inspection and was not rerun, so no browser evidence is claimed for its saved report.

### 2026-11-03 T-140 continuation — ROR-miss publication provenance

**Observed root cause.** In the saved question-only India job `3c9b95ce-52e8-4129-98c2-41b606345ceb`, Crawl4AI returned 10 hits; six eligible domains were sent to exact-domain ROR and all returned `not_found`. The official-site publication target is selected only from dynamically verified organizations. When no ROR/Crossref-supported organization record was produced, the selector returned no target and no official-site publication search could follow. The existing Crossref path remains a DOI/publisher/link corroboration route, not a general DOI-less institutional report resolver. The saved record has zero publication-verification attempts, one Crossref rate-limit event and one OpenAIRE failure; it does not preserve enough per-candidate branch detail to attribute why the Crossref fallback was skipped for each hit. The NIUA URL was not verified, accessed, or assigned rights.

**Implementation.** Added an item-scoped OpenAIRE publication corroborator in `backend/app/research/publication_provenance.py`. If discovery already has a publication-like hit on an eligible ROR-missed domain, the workflow uses its existing single OpenAIRE request slot to search that hit's title instead of running the usual OpenAIRE topic query. Acceptance requires a stable OpenAIRE record ID, exact normalized title, a specific HTTPS URL path on the same validated domain, and exactly one catalog-linked organization record with matching publisher name and website host. The original ROR result is retained separately; OpenAIRE report types remain `institutional_report`; a successful record enters ordinary source selection/acquisition with content rights still `not_assessed`. The API/source inspector displays catalog and location provenance, metadata attribution and the separate content-rights state. OpenAIRE HTTP status codes are now retained for future failures while response bodies remain omitted. No domain is added to the curated registry and no rights rule changed.

**Before/after boundary.** The saved live cohort itself is unchanged: 6 ROR misses; 0 live corroborated organizations/publications; 0 retrieved documents/passages; 3 citations. The offline normal-workflow fixture corroborated 1/1 DOI-less catalog record, persisted/cited it, and exposed its provenance through report inspection; it remained metadata-only with 0 passages. This is a deterministic integration check, not real discovery or acquisition.

**Live validation.** One bounded public OpenAIRE query used the saved NIUA title; the provider returned its sanitized `OpenAIRE metadata search failed` exception. The prior call did not retain an HTTP status or provider payload, so whether it was an API request rejection, endpoint failure or other 4xx/5xx outcome cannot be reconstructed. The new status field will disambiguate future calls. No Crawl4AI search/scrape, report URL fetch, OpenAlex content request, model inference, or paid request occurred. No live organization/publication verification or real evidence passage was obtained. OpenAIRE documents its Graph API and CC-BY attribution terms in the [Graph API quickstart](https://graph.openaire.eu/docs/apis/graph-api-v4/quickstart/) and [terms of use](https://graph.openaire.eu/docs/apis/terms/); the source metadata license does not determine document rights.

**Validation.** Focused provenance/OpenAIRE/provider-metadata/workflow checks: 45 passed. Full backend: **894 passed, 2 PostgreSQL-only skips**. Frontend Vitest **23/23**; TypeScript/Vite production build passed; focused catalog-source-inspector Playwright **1/1** passed. Changed Python Ruff check and format passed. OpenAIRE API metadata is labeled CC-BY without a version claim; explicit CC-BY 4.0 repository-document licensing remains item-specific and separate. No schema migration was required. This verifies offline ROR-miss routing, negative authenticity checks, normal persistence/citation serialization and UI disclosure; it does not meet the live nonacademic publication-to-passage acceptance. T-140/B-017 remain open.
