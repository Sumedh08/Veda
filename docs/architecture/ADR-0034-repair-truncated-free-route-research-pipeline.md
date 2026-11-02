# ADR-0034: Bound and preserve model research operations after T-112 truncation

- **Status:** Accepted for local implementation
- **Date:** 2026-10-30
- **Related:** ADR-0033, T-109–T-115, `evaluation/t112-live-run-quality-review-2026-10-30.md`

## Context

The authorized T-112 local job used the preflighted `nvidia/nemotron-3.5-super-vl:free` route. Crossref and OpenAlex discovery completed, but the three structured operations that were dispatched—planning, methodological appraisal, and comparison—each ended with OpenRouter `finish_reason=length`. No model result passed Veda's schema validation. Synthesis then did not dispatch because its serialized prompt exceeded Veda's 24,000-character per-call limit. Veda persisted a deterministic evidence-map report and the browser displayed its citations and passages. This was not an AI-powered research success.

The trace proves output truncation for those three responses. It does not prove why this model produced outputs long enough to hit the cap, nor does it establish that the schema, provider route, or model behavior was the sole cause. The response-format capability and zero prompt/completion price were present in the read-only endpoint metadata; request-price metadata was null. Each usage row recorded zero reported and estimated cost, but billing was not independently verified and token counts were absent.

## Decision

Keep strict structured-output validation, free-route guards, zero-price request ceilings, no paid fallback, and no resend after an uncertain POST. Improve boundedness and preserve accepted work:

1. Split appraisal into no more than two source-balanced batches. The limit is additionally constrained by the selected depth profile and reserves three later model operations for comparison, synthesis, and semantic review. Each claim stays with its source and exact passage ID.
2. If a later appraisal batch fails, persist validated results from already completed batches. Mark unreturned records unknown, record batch counts and the sanitized failure class, and stop later provider calls after an uncertain or incompatible outcome. Do not reinterpret partial appraisal as complete appraisal.
3. Tighten appraisal and comparison output field/array limits to match their prompts. Comparison may return at most eight material relationships and two hypothesis pairs; the result is explicitly a bounded sample, not exhaustive contradiction coverage.
4. Deduplicate synthesis input: include each stored passage once per source and let claims reference source/passage IDs. Send only non-unknown appraisals; omit redundant source spans and avoid repeating a claim when it is identical to its stored passage. Use compact JSON and a shorter prompt while preserving the causal, uncertainty, citation, and decision safeguards.
5. Capture provider-level abstract excerpt truncation for Crossref/OpenAlex and do not turn the incomplete final abstract fragment into an extracted claim. Preserve the bounded passage and record exclusion provenance.
6. Raise the finite plan-selection output cap from 900 to 1,400 tokens. With two appraisal calls, the standard six-call profile's bounded reservation remains below its 15,600-token output budget: 1,400 + 2×2,600 + 2,600 + 2,200 + 2,400 = 13,800 tokens.

The compact prompts do not relax evidence provenance. Every accepted appraisal still needs exact same-source passage IDs; report claims still need stored claim IDs and deterministic source/passage links; semantic support remains a separate model operation and is not truth verification.

## Alternatives considered

- **Increase every output cap:** rejected because it would consume the per-job output budget and still allow long, unbounded responses.
- **Relax schemas or accept partial JSON:** rejected because partial provider text cannot be trusted as a validated research record.
- **Retry truncated or uncertain POSTs automatically:** rejected because the first operation may already have incurred usage and a repeated call can duplicate charges or produce a different answer.
- **Discard all appraisal output after one batch fails:** rejected because it needlessly loses validated progress; completed batches can be persisted with explicit unknowns for the rest.
- **Claim a successful report from the deterministic fallback:** rejected because T-112's AI-stage success criteria were not met.

## Consequences and verification boundary

Offline regression tests now cover balanced two-batch appraisal, partial-result preservation after an uncertain second batch, compact shared-passage synthesis input, exclusion of known-incomplete abstract tails, excerpt truncation metadata, and explicit `finish_reason=length` classification without raw-response persistence, alongside the fixture-backed structured workflow. These tests verify software behavior only. They do not establish that the free model will complete the operations, that its judgments are scientifically correct, or that a future request will incur no provider-side charge.

The one T-112 live authorization has been used. Do not dispatch another inference request under it. Any live retest requires separate authorization and a new free-route/pricing preflight.

## Follow-up compatibility work (2026-10-30)

The documented historical cause of T-112 truncation remains unknown. The adapter now preserves confirmed response model identity, visible completion tokens, reasoning tokens when reported, latency, finish reason and reported cost on bounded HTTP-200 failures. OpenRouter's current guidance explains that reasoning tokens usually count against `max_tokens` and may exhaust the visible-response budget; this is a plausible mechanism, not a proven explanation for T-112. See [OpenRouter reasoning-token guidance](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).

For a separately authorized next live validation, a read-only 2026-10-30 catalog/endpoint preflight selected the concrete `xingchen-agi/xing4.0-29b-a4b:free` route: catalog and endpoint metadata report zero prompt/completion price, `request` price is null, structured-output and reasoning parameters are supported, reasoning is not mandatory, default reasoning is enabled, and the observed endpoint is Phala. The harness pins this model, explicitly disables reasoning, requires supported parameters, disables fallbacks, sets all supported `max_price` fields to zero, and caps the job at six requests. Request-price null and account-level billing remain unknown. Model selection is compatibility-based and has not been quality-evaluated. The inspection artifact is `evaluation/openrouter-free-research-route-preflight-20261030-current.json`; method and source links are in `docs/research/openrouter-free-route-compatibility-2026-10-30.md`.

No new inference request was made: the current process environment and repository-root `.env` do not contain `OPENROUTER_API_KEY`, and the previously posted value was not reconstructed or reused. The new one-question runner stops before dispatch when the credential is absent and writes only sanitized status/route metadata. The next live run still needs a separately available local credential and explicit live-run opt-in.


## Offline verification update (2026-10-30)

After the T-112 run, the preserved SQLite job was used only to reconstruct the compact synthesis prompt with `_model_call_blocker` replaced by an in-memory capture. The serialization contained 8 sources, 26 claims and 26 passages (23,084 characters), below the 24,000-character request guard; no provider call occurred. The final offline suite passed 433 tests, with 2 PostgreSQL-only skips, and the provider-disabled real-browser citation-inspection test passed. This does not show that the free model will finish or accept output. The one-time authorization remains exhausted.
