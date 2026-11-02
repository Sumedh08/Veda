# ADR-0003: Bounded provider retries and lossless structured-output repair

- Status: Accepted
- Date: 2026-10-29
- Scope: Crossref/OpenAlex metadata GETs and OpenRouter/OpenAI structured model POSTs

## Context

Provider failures need a recovery path, but unbounded retries can exceed a depth step's cooperative time limit, magnify throttling, repeat charged model calls, or turn malformed model output into guessed research claims. HTTP status alone is insufficient for model-provider policy: OpenAI uses 429 for transient throttling and for exhausted credit/spend/usage limits. OpenRouter's non-streaming error envelope can also report a provider failure in a 200 response after headers have been returned.

## Decision

1. Scholarly Crossref and OpenAlex requests are idempotent GETs. They may retry once for HTTP 429, 500, 502, 503 or 504. Transport errors and malformed response bodies are surfaced immediately. Provider response bodies and URLs remain excluded from persisted errors.
2. `Retry-After` is parsed as seconds or an HTTP date. Veda waits no more than 500 ms. If a valid server minimum exceeds that bound, Veda returns the original failure and defers the operation rather than retrying early. Missing or invalid values use one 200 ms bounded delay.
3. OpenRouter structured POSTs may retry once only when the HTTP status itself is 429. OpenAI POSTs may retry once only when a JSON `error.code` explicitly identifies `rate_limit_exceeded` or `slow_down`. Credit, spend, usage, generic or malformed 429 errors are not retried. A 429 with a server delay above 500 ms is surfaced without an early retry.
4. No model POST is retried after a timeout, connection loss, 5xx, refusal/content filter, malformed/schema-invalid output, or any other outcome that might have consumed provider resources. OpenRouter's nonzero reported cost is treated as an uncertain outcome: the output is rejected, the reservation remains conservative, and the same model operation is not resent.
5. The only automatic structured-output repair removes exactly one complete outer Markdown JSON fence. It changes no JSON characters or schema constraints. The original Pydantic schema still validates the full object. Missing fields, invalid JSON and semantic/schema errors are not repaired by guessing or by silently issuing another model call. The applied normalization name is stored in the usage ledger and survives cached replay.
6. There is no circuit breaker or shared retry queue yet. One bounded retry is intentionally small, honors the quick depth's one-retry cap, and allows provider-level failure degradation to continue. A larger retry policy requires measured latency, rate-limit and cancellation evidence first.

## Evidence

- Crossref recommends backing off when its REST API returns 429: [Crossref REST API tips](https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api).
- OpenAI documents both transient rate-limit 429s and hard credit/spend/usage 429s, and says to inspect the error code; its rate-limit guidance says not to retry earlier than a valid `Retry-After` minimum: [OpenAI error codes](https://developers.openai.com/api/docs/guides/error-codes), [OpenAI rate limits](https://developers.openai.com/api/docs/guides/rate-limits).
- OpenRouter's error documentation distinguishes HTTP errors from non-streaming provider error envelopes that may appear in a successful HTTP response: [OpenRouter errors and debugging](https://github.com/OpenRouterTeam/docs/blob/main/api_reference/errors-and-debugging.mdx).
- Local transport fixtures cover status classification, one-attempt caps, oversized `Retry-After`, HTTP-date parsing, sanitized failures, strict JSON fence normalization, schema-invalid no-resend behavior and usage-ledger persistence. These are deterministic tests, not live provider results.

## Consequences and limits

- A temporary 429/5xx can still fail the current stage when the server requests a wait longer than 500 ms; the user can resume under the existing job-attempt and quota policy.
- A known-invalid model response is conservatively held as uncertain because Veda cannot infer provider billing from a malformed or incomplete response envelope. No automatic semantic repair is attempted.
- Provider latency and the per-query retry remain bounded by HTTP timeouts plus at most one permitted delay, but the stage deadline is cooperative around network calls and cannot cancel a request already in progress. This existing limit is tracked in the depth-profile inventory.
- No live OpenRouter or OpenAI request was made for this decision; no API cost was incurred.
