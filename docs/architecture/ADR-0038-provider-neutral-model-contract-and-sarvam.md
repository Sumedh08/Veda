# Provider-neutral structured model contract and Sarvam V2

**Status:** Accepted, 2026-10-30

## Context and diagnosis

Veda's research schemas in `app/research/llm_tasks.py` and persisted stage/checkpoint records were already vendor-neutral. Provider selection, credentials, route identity, transport parsing, and some usage/error types were not: `app/providers/llm.py` combined OpenAI and OpenRouter adapters with shared parsing and usage records, while the workflow formerly depended on the globally configured route. The existing SQL workflow already owns durable stage checkpoints, leases, quota reservations, validated-result replay, and failure recovery; that is the correct reliability boundary.

## Decision

Use the `ModelProvider` contract in `app/providers/contracts.py` for identity, declared capabilities, public authentication shape (environment-variable and header names only), Veda-schema structured generation, normalized usage/results, and reservation context. Provider adapters own endpoint-specific request/response translation and sanitized failure classification. Research Pydantic schemas remain in `app/research/llm_tasks.py`; adapters validate the response against the supplied schema before returning it. Each job persists its provider/model identity. The workflow reserves quota and cost before dispatch, persists validated results and cooldowns, and never retries an uncertain inference POST or silently switches providers.

Sarvam is a first-class adapter on `POST https://api.sarvam.ai/v2/chat/completions`, configured with `api-subscription-key` and the reviewed stable `sarvam-105b` model. V2 documents native JSON Schema structured output, a 128K context, and response usage fields. Veda caps completion output at the conservative Starter-plan ceiling of 4,096 tokens and omits `reasoning_effort`: Sarvam's model guide documents that control on its chat API, while V2's current model-specific reasoning list does not promise it for `sarvam-105b`. Veda still records reasoning-token usage if returned. Current listed prices are ₹15/M input and ₹60/M output, excluding GST; a 1.2 reservation multiplier is a conservative estimate margin, not an account-billing guarantee. A per-job INR cap is enforced before every request. At ADR acceptance the standard research calls used a lower cap; ADR-0039 supersedes that cap with workload-measured batch floors and up to 4,096 output tokens per research operation.

Jobs retain provider/model identity in SQLite and PostgreSQL schemas. No route migration rewrites old jobs; legacy jobs recover their route from an earlier reservation when available. An unavailable selected adapter fails clearly, with no fallback.

## Framework assessment

LangChain's model wrappers could reduce some request boilerplate, but they do not replace Veda's exact schema acceptance, route pinning, per-job/global/user reservations, cost ceilings, durable cooldowns, or uncertain-POST replay rules. Adding it now would introduce another response/error translation layer without removing those controls. LangGraph would add a second state machine alongside persisted Veda stages, SQL leases, checkpoints, quota reservations, and restart recovery; equivalent persistence and migration coverage would be required. Neither library is adopted. Reconsider LangGraph only if the persisted workflow becomes materially non-linear and a migration plan can preserve the existing database guarantees. Reconsider a transport library only if a new adapter materially reduces duplicated code without taking ownership of Veda policy.

## Consequences

- A new provider can be added through configuration, one adapter, and registry metadata without changing research-stage prompts or schemas.
- Provider capability differences are declared and fail closed; capability claims are endpoint/model-specific rather than inherited from OpenAI-compatible syntax.
- Route pinning prevents a global configuration edit from silently changing an in-progress job.
- Sarvam V2 structured response compatibility is documented and fixture-tested, but the first bounded live probe did not pass: Sarvam `sarvam-105b` returned `finish_reason=length` at Veda's 256-token compatibility-probe cap, and strict validation rejected it. Exactly one POST was counted; no research job or report was produced and no retry/fallback occurred. The user confirmed sufficient Credits Left and Auto-recharge off; the account was not independently queried. A new probe is prepared offline with a 1,024-token cap and sanitized usage/cost failure diagnostics, but requires fresh live authorization. No Sarvam AI research success is claimed.

The T-123 failure showed the value of separating route/schema compatibility from research success. Immediately after that failure, the harness was repaired to use a 1,024-token probe cap and a ₹0.25 reservation. ADR-0039 supersedes those settings with a 4,096-token probe cap and a ₹0.50 reservation; the job budget is ₹3.50, so total pre-tax reservations stay within ₹4.00, leaving ₹1.00 below the exhausted ₹5 authorization for tax and rounding. The prior live harness discarded fields carried by the truncation exception; the repaired harness persists only allowlisted model, finish, usage, cost and latency metadata. These are offline harness changes, not evidence that the model will complete the probe or research workflow.

Official source review: [Sarvam Chat Completions V2](https://docs.sarvam.ai/api-reference/chat/chat-completions-v2), [Sarvam 105B model limits](https://docs.sarvam.ai/api/getting-started/models/sarvam-105b), [Sarvam pricing and rate limits](https://docs.sarvam.ai/api/getting-started/pricing), and [Sarvam billing](https://docs.sarvam.ai/api/platform/billing). Evidence and endpoint-specific limits are recorded in `docs/research/sarvam-provider-compatibility-2026-10-30.md`.
