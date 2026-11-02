# Research-engine output-capacity audit — 2026-10-30

## Scope and evidence boundary

This is an offline schema-capacity audit after T-123. No model inference, OpenAI call, OpenRouter call, Sarvam call, cloud operation, or account operation was performed. The prior live Sarvam response remains a failed compatibility probe at a 256-token cap; it does not validate the 4,096-token repair. HTTP success or valid fixtures are not research success.

Representative outputs were serialized from Veda's Pydantic models and counted with `tiktoken` `cl100k_base` available in the host Python installation. This tokenizer is not a Sarvam/OpenRouter/OpenAI model tokenizer. Counts are comparative proxy sizes, not exact usage, required minimums, or evidence that a provider will complete the response. The fixture examples exercise maximum collection counts with concise, plausible field values; per-operation floors add approximately 1.5x headroom and are rounded to convenient bounds. Provider schema/protocol overhead is input-side, measured separately where shown.

## Operation capacity

| Operation | Representative complete output | Selected Veda allocation | Provider maximum known | Bounded work and request planning |
|---|---:|---:|---|---|
| Planning selection | 297 chars / 69 `cl100k` proxy tokens (8 indices, 2 subquestions) | Up to 2,048; floor 1,024 | Sarvam: 4,096 Starter. OpenRouter route and OpenAI registry maximum: not verified | One selection request before discovery; deterministic plan remains if it fails and is not recorded as model success. |
| Methodological appraisal | 7,100 chars / 1,599 proxy tokens (2 sources, 4 claims, full fields/facets); one source + 8 claims was 3,118 proxy tokens | Up to 4,096; floor 2,560 | Sarvam: 4,096 Starter. Other selected-route maximums: unknown | At most 4 claims total and 2 source appraisals per batch; source appraisal only in a source's first batch; exact source/claim/passage allowlists. Number of requests is derived from batches and remaining-stage reservations. |
| Claim comparison / hypotheses | 3,963 chars / 1,049 proxy tokens (8 relationships, 2 hypothesis pairs) | Up to 4,096; floor 1,792 | Sarvam: 4,096 Starter; other route maximums unknown | One bounded request; currently considers up to 24 claims and emits up to 8 relationships/2 hypothesis pairs. This is a declared sample, not exhaustive pairwise comparison. |
| Synthesis | 3,034 chars / 794 proxy tokens (maximum report collections) | Up to 4,096; floor 1,280 | Sarvam: 4,096 Starter; other route maximums unknown | One compact schema-valid draft, with findings/qualifications/implications linked to existing claim IDs. Deterministic limited reports remain labeled non-model-assisted. |
| Semantic citation audit | 6,960 chars / 1,706 proxy tokens (28 support items, 20 uncited-material items) | Up to 4,096; floor 2,560 | Sarvam: 4,096 Starter; other route maximums unknown | One bounded post-synthesis request in current report limits. It only sees saved report items and their linked passages; truncated evidence becomes `needs_review`, not support. |
| Sarvam compatibility probe | 192 chars / 49 proxy tokens (one synthetic source, one `design_type` field); full appraisal schema sent as input: 2,711 chars / 643 proxy tokens | 4,096; schema-specific floor 512 | Sarvam `sarvam-105b`: 4,096 max on Starter, 16,384 Pro, 128,000 Business. Veda conservatively uses Starter. | One synthetic schema-conformance request; counts against the runner's six-POST cap. It tests only a one-field operation, not the complete pipeline or real evidence. |

Schema sizes and request prompt sizes are input tokens, not output tokens. The Sarvam probe's conservative input-envelope estimator returns 4,468 tokens (UTF-8 bytes + JSON Schema + framing; deliberately not an exact tokenizer count). At current public ₹15/M input and ₹60/M output and Veda's 1.2 reservation multiplier, the 4,096-output probe reserve is **₹0.375336 pre-tax**, below the configured ₹0.50 reserve.

The T-123 runner still has a hard maximum of six inference POSTs including the probe: at most five job calls and a ₹3.50 job budget. Five full 4,096-token completions alone reserve up to **₹1.47456 pre-tax** at current public output pricing and the 1.2 margin, before input reservations. Probe plus job reservations are bounded at ₹4.00 pre-tax, leaving ₹1.00 below the old ₹5 ceiling for taxes/rounding. This is a reservation ceiling, not actual spend or an account billing guarantee. The old one-time authorization is exhausted; these values do not authorize a new run.

## Call graph, cost, latency, and quota controls

- The operation planner separately constrains requests, cumulative output tokens, per-call Veda capacity, and a known provider maximum. A seven-operation graph under six available calls reports one deferred operation; it is not silently treated as complete.
- Research-stage allocations use up to 4,096 tokens per call. The planning-selection request uses 2,048. Appraisal batches are independently persisted, and an uncertain later call does not erase earlier accepted results.
- The persisted `resource_plan` event is committed before the first appraisal dispatch. It reports accepted/deferred calls, batch counts, output allocations, prior reservations, provider/model, daily global/per-user remaining slots, and job spend ceilings.
- Each materialized prompt receives a conservative UTF-8/schema input envelope and atomic cost reservation immediately before dispatch. Later-stage prompts are not all materialized at the appraisal checkpoint, so the event does not call an incomplete future input sum a cost forecast. It records the authorized and remaining ceiling; each request must still pass the per-job monetary check.
- No Sarvam operation-level latency baseline is available. The plan stores `latency_estimate_ms: null` with an explicit status. Actual latency remains recorded when a provider reports it.
- Sarvam documentation says `max_tokens` includes reasoning tokens where reasoning is used. Its current V2 reference does not promise a `reasoning_effort` control for `sarvam-105b`; Veda does not add an undocumented parameter. Thus, even a 4,096 allocation may truncate, and the live route remains unvalidated.
- Historical persisted depth-profile snapshots are kept intact. Older jobs whose saved per-call caps are below the new allocations may remain limited; they are not silently rewritten. New jobs snapshot the corrected profiles.

## Root-cause diagnosis

**Confirmed implementation defects:** earlier stage constants and depth profiles placed output caps below the 4,096 Sarvam Starter limit; provider-call code could silently clamp requested output to the profile maximum; the Sarvam probe ran at 256; and appraisal partitioning permitted eight claims even though the representative output already measured about 3,118 proxy tokens. The ten-case OpenRouter cause remains unrecoverable from saved artifacts. T-112/T-119 output truncation is confirmed by `finish_reason=length`; their model-specific reasoning consumption is not known.

**Corrected offline:** each research operation may request up to 4,096 within the depth snapshot; unsupported/insufficient allocations are rejected rather than silently clamped; appraisals use four-claim batches; plans explicitly defer excess work; plans persist before dispatch and are visible in the browser; per-scope daily quotas and latency-estimate knownness are exposed; and the T-123 probe uses 4,096 with a ₹0.50 reserve. No partial JSON or ungrounded citation was accepted to achieve these changes.

**Not established:** whether `sarvam-105b` produces complete structured appraisal output at 4,096; whether full research operations complete at realistic cost; AI report quality; semantic citation correctness; account-specific billing; and scientific accuracy. T-123 remains blocked until fresh live authorization. The probe failure has not been relabeled as provider incompatibility or compatibility success.

## Verification

- Focused backend after capacity/planner changes: **48 passed**, with the existing Starlette/httpx deprecation warning.
- Full backend: **476 passed, 2 PostgreSQL-only skipped, 1 warning**. The skips require a disposable loopback PostgreSQL test URL.
- Frontend Vitest: **23/23**; TypeScript/Vite production build: passed.
- Browser check for the persisted pre-dispatch allocation card: **1/1 passed**.
- SQLite migration upgrade/downgrade/re-upgrade and Alembic autogenerate check: passed.
- Backend Ruff check and whole-backend format check: passed; 148 files already formatted.
- Fixture Playwright full E2E: 45 passed, 15 opt-in tests skipped, including the pre-dispatch plan card; no provider-live test ran.
- Backlog/evaluation/benchmark/annotation/research/Render/backup validators passed; backlog now has 125 tasks (114 DONE, 10 BLOCKED, 1 DEFERRED). Secret-pattern scan checked 324 text files with 0 findings.
- No live inference was sent. No model-authored stage, AI report, or scientific-quality result is claimed.

## Current official provider documentation

Sarvam's public V2 reference lists `sarvam-105b`, strict `response_format` JSON Schema, `api-subscription-key`, and `max_tokens`; the model guide lists a 128K context and Starter output ceiling of 4,096. The current price page lists ₹15/M input, ₹5/M cached input, and ₹60/M output and identifies a 60 requests/minute PAYG limit for `sarvam-105b`. Prices exclude GST. [V2 API](https://docs.sarvam.ai/api-reference/chat/chat-completions-v2), [model limits](https://docs.sarvam.ai/api/getting-started/models/sarvam-105b), [pricing and limits](https://docs.sarvam.ai/api/getting-started/pricing), [billing](https://docs.sarvam.ai/api/platform/billing).
