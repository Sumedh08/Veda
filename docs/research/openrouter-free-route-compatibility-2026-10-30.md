# OpenRouter free-route compatibility check — 2026-10-30

This note records read-only metadata checks used to prepare a future one-question Veda research run. No inference request was sent. Catalog metadata can change; the live runner repeats the exact route preflight before launching the browser job.

## Candidate comparison

| Concrete free model | Observed endpoint | Context / max completion | Structured parameters | Reasoning controls | Decision |
|---|---|---:|---|---|---|
| `xingchen-agi/xing4.0-29b-a4b:free` | Phala | 262,144 / 235,929 | `response_format`, `structured_outputs`, `reasoning`, `max_tokens` | `mandatory=false`, `default_enabled=true`; `reasoning.enabled=false` supported | Selected for the next bounded validation. This route can disable default reasoning and its output limits exceed Veda's current compact request budgets. No output-quality evidence exists yet. |
| `nvidia/nemotron-3.5-super-vl:free` | NVIDIA | 1,000,000 / 131,072 | Same four parameters | `mandatory=false`; default not published in observed metadata | Not selected: the T-112 route returned three truncated structured responses; the historical token split is unknown. The larger context does not address the completion truncation evidence. |
| `dots-studio/dots-3-note-preview:free` | AtlasCloud | 512,000 / 460,800 | Same four parameters | `mandatory=false`; default not published | Not selected: preview route and no demonstrated research-JSON quality. |
| `liquid/lfm-2.5-2.6b:free` | Liquid | 65,536 / 8,192 | Structured parameters were listed | Reasoning mandatory in observed metadata | Excluded for this run because reasoning cannot be disabled and the vendor model description cautions against knowledge-heavy tasks. |

For all four candidates, current model and selected-endpoint prompt/completion price metadata was `0`; request price was absent (`null`) in the observed endpoint metadata. The `:free` suffix is an explicit free-route designation, but neither the metadata nor request-side controls independently verify account billing. The selected Xing route has one eligible endpoint in this snapshot; its endpoint `status` value was preserved as raw metadata and was not interpreted because the field's semantics were not verified.

OpenRouter's current free-model policy states that concrete `:free` variants are capped at **20 requests/minute and 50/day** on an unfunded free account; the daily cap may be higher for accounts with at least $10 in credits, and failed attempts still count toward that daily cap. Per-model/provider limits may also apply. Account tier and prior daily usage are unknown here. Veda's isolated job and local daily-call caps are six, below the published per-minute limit; the harness disables automatic rate-limit retries because a failed attempt can still consume the external daily allowance.

## Runtime compatibility and limits

The route verifier requires a concrete `:free` identity, zero prompt and completion prices at model and eligible endpoint, request price null or zero, structured output and reasoning parameters, non-mandatory reasoning, a published default reasoning state, and enough context/completion capacity for Veda's bounded request envelope. At dispatch, the isolated adapter additionally requires all request parameters, disables provider fallback, sends zero maximum prompt/completion/request prices, disables reasoning for this runner, checks exact returned model identity, rejects nonzero or missing response cost, and validates the complete Pydantic response. A null request-price field remains unknown; endpoint availability is checked again immediately before the browser run.

The live harness fixes one question, standard depth, at most six provider attempts, zero job cost ceiling, zero rate-limit retries, no automatic resend of uncertain POSTs, and local isolated SQLite. Completion-token budgets remain per-operation caps; conservative input-token estimates and schema overhead are not exact tokenizer measurements. OpenRouter states that reasoning tokens usually share `max_tokens` with visible output, which makes hidden reasoning a plausible but unproven explanation of T-112 truncation.

## Sources checked

- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs): structured output support varies by model endpoint and can change.
- [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection): `require_parameters`, disabled fallbacks, and `max_price` are request routing controls.
- [OpenRouter reasoning tokens](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens): reasoning tokens may count against `max_tokens`; model metadata describes reasoning availability/mandatory status.
- [OpenRouter free-model collection](https://openrouter.ai/collections/free-models/): describes free models; rankings indicate adoption, not output quality.
- [OpenRouter pricing and usage/rate limits](https://openrouter.ai/pricing): describes free-tier request limits and failed-attempt counting.
- [OpenRouter model endpoint API](https://openrouter.ai/docs/api/api-reference/models/get-models): public model metadata includes price/context/endpoint details.

The model/endpoint values above came from a same-day read-only public API call saved in `evaluation/openrouter-free-research-route-preflight-20261030-current.json`. Metadata is a point-in-time snapshot, not a live inference or billing confirmation. Selection optimizes operational compatibility only; research quality remains untested.
