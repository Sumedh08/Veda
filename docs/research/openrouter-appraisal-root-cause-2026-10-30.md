# OpenRouter appraisal-stage failure diagnosis

**Status:** Offline diagnosis and repairs recorded; exact historical provider failure remains unknown. No OpenRouter request was sent during this analysis.

## What the preserved run establishes

- Ten research jobs reached appraisal and all ten terminated there; none persisted appraisal, claim comparison, competing-hypothesis analysis, citation integrity/semantic support, model synthesis, or a report.
- The redacted browser artifact contains 20 persisted provider usage entries: 2 accepted planning outputs and 18 failures. There are 10 failed appraisal entries and 8 failed planning entries. The two accepted planning outputs used `nvidia/nemotron-3-ultra-550b-a55b:free` and reported $0.00.
- Failed historical records have missing reported costs and a legacy `estimated_cost_usd: 0`. That value is not evidence of free execution. Billing for failed calls is unconfirmed.
- Failed planning/appraisal model identity stayed at the configured router value `openrouter/free`; no accepted model identity or finish reason was saved for the failures. The job surfaced only `model_call_uncertain`.
- The saved artifacts do not contain provider error bodies, response content, truncation reason, refusal flag, or per-call sanitized error class. We cannot determine whether failures were caused by unsupported structured output, invalid schema, route change, malformed/truncated output, refusal, timeout, upstream/provider error, missing route identity, missing cost, or another adapter exception.

## Code-level defects established independently of the provider cause

- The old adapter sent strict JSON Schema output without `provider.require_parameters`. OpenRouter currently documents that structured-output support varies by endpoint and recommends requiring parameters for routing. This is a credible failure path, not a diagnosis of the historical response.
- Error envelopes returned with HTTP 200 could be misclassified as a normal completion. Provider error handling and safe classification now cover this shape.
- Timeouts, invalid provider JSON, HTTP 5xx and transport ambiguity did not all trip the no-further-free-route guard. They now do; ambiguous POSTs remain non-retryable.
- A concrete configured `:free` route could return a different `:free` model and still be accepted. Concrete routes now require exact model identity; only `openrouter/free` may resolve dynamically to another returned `:free` identity.
- The appraisal prompt instructed schema version 1 while using schema version 2, emitted verbose unknown facets, and did not include the exact claim passage ID. These are now corrected. These issues could degrade model compliance/grounding; none can be tied to a saved historical error code.
- The appraisal stage previously propagated uncertain provider failures as job-terminal errors even though discovery, passages, and claims had already been committed. It now records unknown/not-performed appraisal fields, preserves earlier evidence and allows a limited deterministic report to be persisted. A stop marker prevents further model requests after an uncertain route/cost event.
- Failed calls with absent cost metadata could be recorded as estimated zero. They now remain null, reservations do not book an unknown amount as actual spend, and API/UI summaries expose incomplete cost accounting.

## Output-size and batching assessment

The previous appraisal request combined all selected source passages and claims in one structured response. It requested source-method fields and claim judgments for a potentially large set of records. The compact prompt now asks only for explicitly reported fields and exact supplied passage links. Output pressure remains plausible. OpenRouter documents that `max_tokens` can include reasoning tokens, and a low output cap can yield `finish_reason: length`. The historical batch preserved neither finish reasons nor token usage for failed responses, so truncation is unproven.

No automatic appraisal splitting was added. Splitting would consume additional bounded model calls and may leave less capacity for comparison and synthesis; it could also create partial domain results unless each sub-result is replayed/persisted safely. The next live validation must first test one question with bounded calls. A split strategy should be added only with an offline truncation/recovery fixture and a demonstrated per-depth call budget that leaves room for report generation.

## Regression coverage and recovery evidence

`backend/tests/test_llm.py` uses HTTP/provider fixtures to verify malformed provider JSON, unsupported response formats, HTTP-200 errors, refusal/content filtering, `finish_reason: length`, changed model identity, missing cost, malformed structured JSON/schema, timeouts, no repeated ambiguous requests, exact `:free` routes, disabled provider fallback, and zero-price routing constraints.

`backend/tests/test_ai_research_pipeline_fixtures.py` exercises all structured workflow stages with typed provider fixtures and verifies persisted claims, source/passage citation links, report and semantic-audit status. It is a deterministic contract fixture, not a real-model success.

`backend/tests/test_ai_research_failure_recovery.py` exercises unsupported-format fallback and appraisal timeout. It confirms saved sources/claims/citations survive, assessments remain explicitly unknown, cost completeness remains false, a limited report is persisted, and no subsequent model call is made.

These tests establish offline software behavior only. Veda's AI research engine is **not operationally validated** until a separately authorized real-model research job persists a report with inspectable evidence and citations.
