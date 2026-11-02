# Veda cost model

**Price snapshot:** rechecked against official provider pages on 2026-10-29. These are model-token illustrations, not measured Veda usage, quotes, or a promise that a provider will remain available at these prices.

## Assumptions

- OpenAI reference model: `gpt-6-luna`, Standard processing, **$0.10 / 1M input tokens** and **$0.50 / 1M output tokens** in the official price sheet. Regional processing, Fast mode, long-context rates, cached-token rates, or later price changes are excluded.
- Per-job token scenarios are planning assumptions only: Quick = 6,000 input + 1,000 output; Standard = 15,000 + 2,500; Deep = 40,000 + 6,000. These counts have not been measured from production runs. Discovery depth is bounded separately in Veda; real model input depends on retrieved excerpts, retries, schema overhead, and model prompts.
- Formula: `(input_tokens × input_price + output_tokens × output_price) / 1,000,000`.
- The table excludes hosting, database, email/authentication, search, storage, taxes, refunds, and human review. No paid web-search tool is enabled in this implementation. The default provider is disabled and the default per-job budget is $0.
- The production model price is the standard, non-regional, uncached text rate. GPT-6 Luna's official page states prompts over 272K input tokens incur a 2x input/cache and 1.5x output multiplier; Veda's maximum individual prompt estimate is 52K, so the configured per-request cap stays below that threshold.

## Model-token estimate by workload

| Depth | Assumed input/output tokens per job | Estimate per job | 10 jobs | 100 jobs | 1,000 jobs |
|---|---:|---:|---:|---:|---:|
| Quick | 6,000 / 1,000 | $0.00110 | $0.011 | $0.110 | $1.10 |
| Standard | 15,000 / 2,500 | $0.00275 | $0.0275 | $0.275 | $2.75 |
| Deep | 40,000 / 6,000 | $0.00700 | $0.070 | $0.700 | $7.00 |

Amounts are rounded for display. Actual charges come from provider usage; Veda records usage when returned and uses configured prices for estimates. A zero-budget job stays in deterministic evidence-map mode. The model estimate does not include a provider's search or other tool-call price.

## Enforced resource-budget ceiling at current OpenAI prices

The preceding scenarios are deliberately lower planning assumptions. Veda now snapshots and enforces a cumulative conservative input-token envelope and output-token ceiling for each depth profile. Multiplying those maxima by today's GPT-6 Luna standard text rates gives the following upper bound if every reserved input and output token is consumed:

| Depth | Maximum input tokens | Maximum output tokens | Maximum estimate/job | 10 jobs | 100 jobs | 1,000 jobs |
|---|---:|---:|---:|---:|---:|---:|
| Quick | 72,000 | 65,536 | $0.039968 | $0.39968 | $3.9968 | $39.968 |
| Standard | 180,000 | 98,304 | $0.067152 | $0.67152 | $6.7152 | $67.152 |
| Deep | 416,000 | 163,840 | $0.12352 | $1.2352 | $12.352 | $123.52 |

Formula remains `(input_tokens × $0.10 + output_tokens × $0.50) / 1,000,000`. These are conservative budget-envelope illustrations, not actual spend: the input cap is an estimate, users may select lower job ceilings, and a run may stop before exhausting the budget. Configured provider prices can be stale; OpenAI cost preflight must be refreshed before paid use.

### Price sensitivity for 1,000 jobs

| Depth | Current rate (1x) | 2x token prices | 5x token prices |
|---|---:|---:|---:|
| Quick | $39.968 | $79.936 | $199.84 |
| Standard | $67.152 | $134.304 | $335.76 |
| Deep | $123.52 | $247.04 | $617.60 |

This sensitivity scales only model-token rates; it does not include usage-based search/tools, infrastructure, or traffic effects.

## Free-model limits

The OpenRouter smoke request returned a zero reported model-token cost, but one request does not establish future availability or cost for an entire research run. OpenRouter's free-model page was last checked in the route assessment and listed 20 requests/minute and 50/day for free variants; failed attempts count against that daily cap and model/provider limits can vary. Veda's default global and per-user daily call ceilings are now 50. Depth profiles allow up to 16/24/40 calls for quick/standard/deep; the persisted execution planner calculates the actual graph from appraisal batches and reserves comparison, synthesis and semantic review capacity. At the profile maxima, the Veda global daily ceiling permits at most 3 quick, 2 standard or 1 deep job/day; provider limits can be lower. Actual jobs may use fewer calls; no measured average exists. The OpenRouter route may change models or be unavailable, and Veda rejects a response reporting nonzero token cost.

OpenAlex is separate from model-token cost. Its current official docs report $1 per 1,000 `search` calls and a free keyless daily allowance; actual account usage and paid-plan behavior depend on configuration. Veda sends OpenAlex requests without an account key by default, selects only required fields, limits each query to at most eight records, and requires `OPENALEX_ALLOW_BILLABLE_CALLS=true` before an optional server key is attached. Do not enable that flag until the account's free quota and billing behavior are confirmed. A research job makes at most the bounded plan-query count of OpenAlex calls, plus one retry only after a 429.

## Sarvam bounded-validation reservation snapshot

The current Sarvam V2 public pricing page lists `sarvam-105b` at ₹15/M input, ₹5/M cached input, and ₹60/M output. Sarvam's model guide lists a 4,096-token Starter completion ceiling; Veda does not assume the account is on a larger tier. A 4,096-output synthetic appraisal-schema probe with a conservative 4,468-token input envelope is reserved at **₹0.375336 before tax** after Veda's 1.2 reservation margin; the configured probe ceiling is ₹0.50. Five job calls at a full 4,096-token output allocation each have an output-only reserve of **₹1.47456 before tax**, excluding input. The runner limits the job to ₹3.50 and the combined probe/job pre-tax reservations to ₹4.00 under the historical ₹5 authorization. These are code-enforced bounds, not actual provider charges or account balance guarantees. The one-time authorization is exhausted, so no further Sarvam request may be sent without fresh user approval. See [Sarvam pricing and rate limits](https://docs.sarvam.ai/api/getting-started/pricing), [Sarvam-105B limits](https://docs.sarvam.ai/api/getting-started/models/sarvam-105b), and [ADR-0039](architecture/ADR-0039-workload-sized-model-calls-and-visible-preflight.md).

## Cost controls and remaining uncertainty

- Provider is `disabled` unless configured.
- OpenRouter accepts only `openrouter/free` or a model ID ending in `:free`, and rejects a response reporting nonzero model-token cost.
- OpenAI requires server-only credentials, `ALLOW_PAID_LLM_CALLS=true`, explicit nonzero job budget, configured model prices, and a global daily call limit. Configure provider prices from the live official sheet before enabling it.
- The per-job ceiling is preflighted using a conservative request estimate and checked against returned token usage when available. If token usage is missing, the configured maximum request estimate is recorded instead of treating the call as free.
- Crossref is used for public scholarly metadata discovery. Its commercial terms, rate behavior, and any downstream data-retention obligation are separate from model pricing; this implementation does not retrieve full text.
- Provider retries or a server crash after a provider accepts a request but before Veda records the response can make exact-once billing impossible. Veda reports this recovery boundary rather than promising exactly-once calls.

**Official sources checked 2026-10-29:** [OpenAI GPT-6 Luna model details and long-prompt pricing](https://developers.openai.com/api/docs/models/gpt-6-luna), [OpenAI API pricing](https://developers.openai.com/api/docs/pricing), [OpenRouter free models and limits](https://openrouter.ai/collections/free-models), [OpenAlex Works search pricing](https://help.openalex.org/api/searching/), and [OpenAlex free/keyed limits](https://help.openalex.org/api/authentication/). Provider limits and prices may change; recheck before enabling a provider.

Reproduce every table and sensitivity scenario offline with `python scripts/calculate_cost_scenarios.py` from the backend directory. The script reads the enforced limits from `app.research.depth.PROFILES` and makes no provider request.
