# ADR-0024: Isolate live OpenRouter free-model E2E runs

- **Status:** Accepted
- **Date:** 2026-10-29
- **Decision owners:** Veda engineering

## Context

The default real-API browser harness intentionally clears all model credentials
and sets `LLM_PROVIDER=disabled`. It verifies local API/browser persistence and
live scholarly retrieval, but cannot verify a complete model-assisted Veda run.
The only OpenRouter credential previously supplied was exposed in conversation
and must not be reused. A future live integration check needs a newly rotated
credential and must not weaken the safe default test server.

OpenRouter documents `openrouter/free` as a router that chooses an available
free model for each request; model availability and free-tier limits can vary.
The provider can also accept a specific `:free` model ID. OpenRouter warns that
paid models in a fallback array can be billed, so the Veda request must keep a
single free route and must not add fallbacks. The existing adapter already
rejects non-free model IDs and rejects results with a non-zero provider-reported
cost.

## Decision

1. Keep `serve_browser_e2e.py` provider-disabled and credential-clearing by
   default.
2. Add a separate server entry point, selected only when
   `VEDA_OPENROUTER_LIVE_E2E=1`. Refuse startup unless a key is configured and
   the model is `openrouter/free` or ends in `:free`. Error messages never
   include key contents.
3. Reuse the standard helper's disposable migrated SQLite database, synthetic
   inspection seed, loopback development authentication and request ceilings;
   restore only the configured OpenRouter key after the helper clears secrets.
4. Clear OpenAI credentials, keep paid calls disabled, cap daily model calls at
   eight, and use the quick profile (four model calls) with a $0.25 per-job
   envelope. The live browser test fails if it observes no model attempt or a
   non-zero recorded run cost.
5. Keep the real model test separately opt-in and outside routine tests. Use a
   synthetic question; disclose that the question, supplied scope and retrieved
   excerpts are sent to OpenRouter, and do not use confidential material.
6. Treat the live run as integration evidence only. It does not validate
   research quality, source relevance, passage reuse rights, or model judgment.

## Alternatives considered

- **Allow provider settings in the default real-API server:** rejected because
  routine browser tests would inherit ambient secrets and could make accidental
  external model calls.
- **Reuse the one-call adapter smoke:** rejected because it does not exercise
  planning, source retrieval, appraisal, report persistence, or browser
  inspection.
- **Add a paid fallback route:** rejected because it violates the free-only
  requirement and can silently incur charges when a free model is unavailable.

## Consequences and limits

- Offline guard tests can verify that the opt-in, key-presence and free-route
  boundaries hold without making an API call.
- A live run remains blocked until a fresh key is configured outside source
  control. Free provider availability, rate limits, model identity, and data
  handling vary; any reported non-zero cost fails the run.
- Model-generated research content may be incorrect and still requires
  independent review. The benchmark remains unscored until its source set and
  qualified human reviews are complete.

## Verification

- OpenRouter documents the free router and its availability limits in the
  [Free Models guide](https://openrouter.ai/collections/free-models) and
  [Free Models Router documentation](https://github.com/OpenRouterTeam/docs/blob/main/guides/routing/routers/free-router.mdx).
- Run the focused offline guard tests and default real-API browser suite. The
  opt-in live browser workflow is not verified until run with a freshly rotated
  credential; no credential was available for this implementation step.
