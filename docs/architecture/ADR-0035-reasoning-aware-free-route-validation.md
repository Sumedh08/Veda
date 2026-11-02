# ADR-0035: Use reasoning-aware bounded outputs for the next free-route validation

- **Status:** Accepted for local implementation; live model behavior unverified
- **Date:** 2026-10-30
- **Related:** ADR-0033, ADR-0034, T-112, T-117, T-118

## Context

T-112 received three HTTP-200 OpenRouter responses from `nvidia/nemotron-3.5-super-vl:free`; each had `finish_reason=length`, so none passed structural validation. The persisted historical records do not include completion-token or reasoning-token counts, and therefore cannot identify why the output limit was reached. A separately captured synthesis prompt exceeded Veda's own 24,000-character guard, so synthesis was not dispatched. Existing strict schemas, no-resend behavior, budget reservations and partial evidence persistence remain necessary.

OpenRouter's official reasoning-token documentation states that on most providers reasoning tokens and visible response tokens share the `max_tokens` completion budget. It also documents an `enabled` reasoning control and model metadata describing whether reasoning is mandatory and enabled by default. The 2026-10-30 public model and endpoint metadata for `xingchen-agi/xing4.0-29b-a4b:free` reports zero prompt/completion prices, a null request-price field, structured output and reasoning parameters, and non-mandatory reasoning. This is routing compatibility evidence only; it is not evidence of model quality or guaranteed account-level zero billing.

OpenRouter currently publishes a 20 requests/minute and 50 requests/day limit for concrete `:free` variants on an unfunded account; failed requests count toward that daily allowance, and per-model/provider rate limits may also apply. The account's tier, remaining quota and daily use are unknown.

## Decision

1. Keep strict Pydantic structured-output validation, bounded prompt and completion limits, exact model identity checks, free-route-only pricing guards, `require_parameters`, `allow_fallbacks=false`, zero prompt/completion/request `max_price`, and no automatic resend after uncertain POST outcomes.
2. When a bounded HTTP-200 response exists, preserve only sanitized metadata useful for diagnosis: returned model ID (if valid), prompt/completion/reasoning token counts (if valid), latency, finish reason, and reported cost. Never persist raw response text or secret-bearing headers.
3. Configure reasoning only when `OPENROUTER_REASONING_ENABLED` is explicitly set. The next isolated research validation pins the metadata-preflighted Xing route and explicitly disables reasoning. This setting is test-runner-specific and does not change defaults for ordinary runs.
4. Keep compact field and array limits and at most two bounded hypothesis pairs. Partial appraisal results remain useful only when each accepted field preserves its exact source/passage provenance; missing records stay unknown.
5. Preflight the model and eligible endpoint immediately before the isolated run. Treat null request-price metadata, future endpoint changes, and account-level billing as unknown. A request-side zero-price limit is a guard, not proof that the account cannot be charged.
6. The runner accepts exactly one fixed research question, an exact pinned `:free` model, isolated SQLite, a maximum of six provider attempts, and zero provider rate-limit retries. The runner never copies the key into artifacts or passes it to the frontend, migration process, or shell arguments. Missing credentials stop execution before inference.

## Alternatives considered

- **Raise all output caps:** rejected because it conflicts with the existing per-job completion-token reservation and does not ensure visible JSON when hidden reasoning consumes the budget.
- **Accept partial JSON or relax schema validation:** rejected because truncated output cannot establish complete evidence, appraisal, citation, or synthesis records.
- **Reuse the previously posted credential:** rejected because its one-time authorization was already consumed; the current local environment has no configured credential.
- **Use dynamic `openrouter/free`:** rejected for this validation because its model identity is not fixed before dispatch and the selected operation needs explicit schema/reasoning compatibility checks.
- **Switch to a paid or OpenAI route:** rejected because the next validation is scoped to an explicitly free OpenRouter route.

## Consequences and verification

The provider adapter now captures bounded failure metadata and reasoning-token metadata in usage records. The isolated runner has a separate exact free route profile and refuses dispatch when the credential is unavailable. Deterministic route-preflight fixtures, provider usage/failure tests, workflow recovery tests, migration checks and local browser pipeline fixtures validate these guards. The public preflight succeeded on 2026-10-30. No inference request was sent in this checkpoint; no AI-powered research report, scientific accuracy or live quality result is claimed.

Official sources:

- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
- [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)
- [OpenRouter reasoning tokens](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)
- [OpenRouter free-model collection](https://openrouter.ai/collections/free-models/)
- [OpenRouter pricing and free-tier request limits](https://openrouter.ai/pricing)
