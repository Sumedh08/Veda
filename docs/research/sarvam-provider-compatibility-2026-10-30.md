# Sarvam model/API compatibility review — 2026-10-30

This is a documentation review, not an authenticated request or a live compatibility result. The full source findings are from Sarvam's official docs, checked on 2026-10-30.

## Endpoint and structured output

- Veda targets `POST https://api.sarvam.ai/v2/chat/completions` and selects the exact stable model ID `sarvam-105b`. The current V2 model list includes it; the conversations variant is documented for V1 only.
- V2 requires `api-subscription-key` (Bearer is also documented). Veda exposes only the environment-variable/header names in its provider contract, never the key.
- V2's `response_format` supports `{ "type": "json_schema", "json_schema": { ... } }` and documents schema-constrained Structured Outputs. Veda still independently parses and validates every response using its own Pydantic schema. A provider promise does not replace application validation.
- Successful V2 bodies expose `model`, choices/finish reason, and token `usage`; usage examples include prompt/completion counts and completion reasoning-token details. Cost is not represented as a guaranteed provider usage field, so Veda retains null reported cost and computes only a bounded estimate.
- The API describes `max_tokens` as the completion budget, including reasoning on models where reasoning tokens apply. A length finish reason can leave little visible content. Veda rejects that response; it never accepts partial JSON as a verified result.

## Model, parameter and price choice

- `sarvam-105b` has a documented 128K context. The model guide gives 4,096 output tokens for Starter, 16,384 for Pro and 128,000 for Business. Veda enforces the conservative 4,096 ceiling because the user's plan is unknown; current standard-depth per-call output is lower.
- There is an endpoint-specific documentation distinction: the Sarvam model guide describes `reasoning_effort` on Sarvam chat, while current V2 docs enumerate that control for other V2 model IDs and do not promise it for `sarvam-105b`. Veda therefore does not send `reasoning_effort` on V2. Reasoning usage is recorded when present; a truncation still fails strict validation.
- Current public Sarvam-105B rates are ₹15 per million input tokens and ₹60 per million output tokens. Listed prices exclude GST. Veda's reservation applies a 1.2 multiplier before dispatch as margin for taxes/estimation error; it is not an account-level billing guarantee. Unknown or missing account balance is not interpreted as free credits.
- Public Pay-as-you-go docs list 60 requests/minute for Sarvam-105B. Actual current account rate limits are shown in Sarvam's dashboard and were not verified here.
- The docs describe a ₹100 new-user credit grant for verified users, but that generic offer does not establish this account's remaining credits, organization balance, or auto-recharge status. Billing docs identify Settings → Billing as the authoritative balance and auto-recharge view; there is no reviewed public read-only balance API in the referenced docs.

## Offline implementation and live blocker

`SarvamChatCompletionsProvider` is fixture-tested for exact V2 request shape, strict schema validation, exact returned-model identity, refusal/truncation/malformed output, unknown cost/usage, sanitized 429 handling, no retry, and pre-dispatch INR cost rejection. SQLite persists provider/model route identity, call reservations, usage currency and provider cooldowns; the API pins routes per job. OpenAI and OpenRouter share the same structured-result contract and retain their own adapters.

The initial presence-only check was run from repository-root cwd and resolved the relative `../.env` path incorrectly; it reported `SARVAM_API_KEY` unavailable and emitted `python-dotenv could not parse statement starting at line 1`. A corrected check using `uv run --locked --directory backend` later confirmed key presence in backend Settings (not in raw process environment) with no warning; no value was printed. Paid calls remain disabled and the Sarvam job ceiling remains zero. The workspace contains the `.env` ignore patterns in `.gitignore`, but has no Git metadata, so `git check-ignore` could not verify the index state. The provider account's remaining credits and auto-recharge state also cannot be read from this environment. No live request was sent; actual route compatibility, cost, research stages, report persistence, and browser inspection are therefore not measured.


## Post-correction backend launcher check

After the user corrected the root `.env`, the backend launcher context was verified with `uv run --locked --directory backend`. Output contained only booleans: raw process environment key presence was false and backend Settings key presence was true. The app’s effective Settings still had `llm_provider=disabled`, `allow_paid_llm_calls=false`, and `sarvam_max_job_cost_inr=0.0`. No inference call was made.

The account-specific Credits Left and Auto-recharge setting remain unavailable to this process; the user later confirmed that Settings → Billing showed sufficient Credits Left and Auto-recharge off. Current pricing lists `sarvam-105b` at ₹15/M input, ₹5/M cached input, and ₹60/M output excluding GST.

## T-123 live probe result and offline harness correction

On 2026-10-30, the single authorized run used `sarvam-105b` on V2 and issued one POST for a synthetic compatibility-only `ResearchAppraisalBatch` request. The response model passed Veda's exact route check, but Sarvam ended with `finish_reason=length` at the request's 256-token completion cap. Veda rejected the truncated output as `provider_output_truncated`. The six-request counter recorded 1; no retries or fallback occurred. The runner prepared the isolated SQLite migrations and synthetic UI fixture before inference, but the API/browser test did not start after the probe failed. No research job, source retrieval, AI stage, report, or citation inspection occurred.

The saved provider failure artifact does not contain the response's token-usage or cost diagnostics. This was a harness omission: the adapter's `LLMProviderError` supports sanitized model, finish-reason, token, latency, and cost fields, but the runner wrote `usage_metadata_complete=false` unconditionally. The live response may have carried usage metadata; preserved counts and actual charge are unknown. The pre-dispatch probe reservation ceiling was ₹0.10 before tax. No raw provider response or credential was written.

The leading explanation is that the 256-token completion cap was too small; why the model consumed the full allowance is not established. Offline changes set the next probe cap to 1,024 tokens, require compact JSON-only output, increase its maximum reservation to ₹0.25, preserve allowlisted failure usage/cost/model diagnostics, and leave ₹3.75 for the job. Total pre-tax reservation is capped at ₹4.00 with ₹1.00 tax/rounding headroom below the authorized ₹5 limit. A conservative local envelope estimate for the revised probe is ₹0.12846; it is a reservation calculation, not measured usage or cost. New local tests cover truncation diagnostics, unknown cost/model handling, and the probe reservation bound. No second inference attempt is authorized by the exhausted one-time validation.

## T-125 output-capacity audit and offline repair

ADR-0039 supersedes the immediately post-T-123 probe and per-operation settings above. The current bounded runner uses a 4,096-token probe cap, a ₹0.50 probe reservation, and a ₹3.50 research-job ceiling; the runner still limits all requests to six total and five job calls. The conservative 4,468-token input envelope plus 4,096 output tokens reserves ₹0.375336 before tax at the currently listed rates and 1.2 multiplier. This is a pre-dispatch estimate, not a charge or proof of account-level billing. The original one-time live authorization remains exhausted; no new probe or research inference was issued.

The appraisal partition is now at most four claims per batch, with source-level method appraisal emitted only once per source. Two-source/four-claim full-shape serialized fixtures measured 1,599 `cl100k_base` proxy output tokens; one-source/eight-claim fixtures were about 3,118, so the latter shape was removed to preserve headroom below the 4,096 output ceiling. Planning, comparison, synthesis and semantic operations also use fixture-informed lower bounds and may request up to 4,096. The proxy tokenizer is not Sarvam's tokenizer and the fixture is not a live accepted completion. See `evaluation/research-engine-output-capacity-audit-2026-10-30.md`.

The remaining-work planner is now persisted before appraisal dispatch, includes per-user/global quota counts and job spend ceilings, and is visible in the report workspace. It marks latency estimates unavailable because no validated provider-and-stage baseline exists. Inputs and money remain independently checked: the exact prompt's conservative input envelope and cost reservation are recomputed atomically immediately before each call. Offline checks for this change passed 476 backend tests (2 PostgreSQL-only skips), frontend 23 tests/build, SQLite migration round-trip, and a focused browser allocation test. Live Sarvam compatibility, AI report completion, and scientific quality remain unverified.
