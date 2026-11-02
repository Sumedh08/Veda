# Workload-sized model calls and visible pre-dispatch plans

**Status:** Accepted, 2026-10-30

## Decision

Keep the model-provider adapter contract and SQL-owned workflow unchanged, but size each research operation to the Veda output envelope and split appraisal at four claims per response. A source-method appraisal is emitted only in the first unit for that source; later units retain their stable claim, source, and passage IDs. The normal operation request may use up to 4,096 completion tokens, while a task-specific lower bound rejects allocations that are too small for the largest representative schema fixture. No incomplete JSON is accepted, and per-call provider/output limits remain independent of job and daily request budgets.

Persist the remaining-work plan as a `resource_plan` event and commit it before the first appraisal POST. It reports required, planned, and deferred operations; output allocations; provider/model identity; daily global and owner quota counts; remaining job call capacity; and the authorized/remaining spend ceiling. Exact prompt envelopes and cost reservations still happen atomically for each materialized request. A route-specific latency estimate is unavailable until Veda has a validated operation-level baseline, so the plan stores `null` and explains why instead of fabricating a duration. The browser renders the saved plan as a pre-dispatch allocation, explicitly separate from completed-stage results.

The T-123 runner uses the documented Sarvam Starter completion ceiling of 4,096 for its synthetic schema probe. Its probe reserve is ₹0.50, the research-job reserve is ₹3.50, and total pre-tax reserved ceilings are ₹4.00 under the previously approved ₹5 test cap. The one-time live authorization is exhausted; these are offline settings only. A fresh approval is required before any further inference.

## Evidence and consequences

Offline serialized fixtures measured with `cl100k_base` show 1,599 proxy tokens for two source appraisals plus four claims, 1,049 for eight claim relationships and two hypothesis pairs, 794 for the maximum compact report draft, and 1,706 for the maximum semantic audit. One source with eight claims measured about 3,118 proxy tokens, too close to a 4,096 completion ceiling after accounting for reasoning and model variability; therefore appraisal uses four claims per unit. These are tokenizer comparisons, not Sarvam token counts or accepted model outputs. Full measurements and limits are in `evaluation/research-engine-output-capacity-audit-2026-10-30.md`.

The compatibility probe currently asks for one synthetic source appraisal field only; its valid output measured 49 proxy tokens, and the complete `ResearchAppraisalBatch` schema is sent as input. A 4,096 request cap creates headroom for provider reasoning, which Sarvam documents as part of `max_tokens`; it does not establish live compatibility. Sarvam's published Starter cap is 4,096 and the V2 endpoint accepts strict JSON Schema, but T-123's sole response ended at 256 with `finish_reason=length`. No request has tested the corrected cap.

The planner can mark excess appraisal batches deferred without discarding accepted prior batches. This limits research breadth when request/output capacity is insufficient; the saved plan and unknown appraisal states disclose that limitation. Comparison remains one bounded operation over at most 24 claims and eight relationships, so it is explicitly a sample rather than an exhaustive pairwise analysis. The report must continue to distinguish a deterministic evidence map from model-authored synthesis.

## Rejected alternatives

- Keep a single eight-claim appraisal batch: the measured serialized output leaves insufficient headroom under Veda's 4,096 ceiling.
- Raise the global completion ceiling above Sarvam's documented Starter limit: this would violate model capacity and may create avoidable charges.
- Change every task's allocation to exactly 4,096: task-specific floors and compact schemas preserve usable output room without claiming every operation needs the maximum.
- Estimate latency from the isolated failed T-123 probe: one failed response is not a validated operation-level latency baseline.
- Add LangChain or LangGraph: neither improves the existing SQL leases, checkpoints, quota reservations, exact schema validation, or uncertain-POST recovery boundary.

## Current provider documentation

Sarvam lists `sarvam-105b` on V2 with a 128K context, a Starter `max_tokens` limit of 4,096, and strict JSON Schema response formatting. The current pricing page lists ₹15/M input, ₹5/M cached input, and ₹60/M output; prices exclude GST. These docs do not verify the user's account billing, credit balance, or actual route behavior. [V2 API reference](https://docs.sarvam.ai/api-reference/chat/chat-completions-v2), [Sarvam-105B limits](https://docs.sarvam.ai/api/getting-started/models/sarvam-105b), [pricing and rate limits](https://docs.sarvam.ai/api/getting-started/pricing), [billing](https://docs.sarvam.ai/api/platform/billing).
