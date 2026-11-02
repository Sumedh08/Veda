# Sarvam GLM-5.3 Flash task budgets and live-run contract

**Status:** Accepted, 2026-10-31

## Context

Veda has offline provider fixtures and an SQL-owned research workflow, but no real model-assisted report has completed all mandatory stages. T-112's free OpenRouter route returned three truncated structured responses and did not reach synthesis. T-119's free route was rate-limited for three operations and truncated synthesis. T-123's Sarvam sarvam-105b probe ended with finish_reason=length at a 256-token cap. The latter does not establish that 105B itself cannot return valid structured output.

The prior implementation imposed a shared 4,096-token transport ceiling and assigned 4,096 to every operation, despite model-specific limits and reasoning-token behavior. The job-create schema also capped INR budgets at ₹5, so a ₹20 configured limit could not be used through the actual API. The old Sarvam browser runner spent one request on a synthetic probe, restricted the real job to five calls, and retained old pricing. Reusing it would not execute the authorized GLM research workflow.

Sarvam's official Token Factory documentation was checked for the exact glm5.3-flash model, Chat Completions V2, strict JSON Schema, reasoning parameters, output limits, usage metadata, errors and pricing. The reviewed findings and unresolved account facts are in docs/research/sarvam-token-factory-glm5-3-flash-2026-10-31.md.

## Decision

Keep the existing ModelProvider interface and persisted SQL workflow. Model registry metadata now carries reviewed model identity, provider context/completion ceilings, supported reasoning efforts, uncached input/output prices, and optional task-specific completion allocations. The workflow remains model-vendor agnostic: it reads the selected model profile, asks for a declared low reasoning effort when one exists, and includes that value in replay identity. A reasoning value is rejected by adapters that do not declare support.

Register glm5.3-flash separately from glm5.3 and sarvam-105b, with:

- Chat Completions V2 at https://api.sarvam.ai/v2/chat/completions.
- Required strict JSON Schema output, followed by Veda's independent Pydantic and evidence-ID validation.
- 1,048,576 context and provider completion ceilings. These are provider capabilities, not Veda generation targets.
- Explicit reasoning_effort="low" for current Veda operations. Reasoning cannot be disabled and shares the completion allowance. No operation uses high until evaluation establishes that it improves the comparison result.
- Current public uncached input rate ₹13.50/M and output rate ₹45/M, including reasoning output. Cached-input price is not used in reservations. The registry price is authoritative for the model; legacy single-model environment price fields cannot lower its reservation.

Preserve the sarvam-105b model's 128,000 context, 4,096 provider completion ceiling, ₹15/M input and ₹60/M output. Model-specific task allocations keep existing routes at their prior limits by default; GLM uses 4,096 for planning and 8,192 for appraisal, comparison, synthesis, and semantic support. The shared transport ceiling is 16,384, the per-depth task ceiling is 8,192, and strict validation remains mandatory. These are calibrated Veda budgets, not estimates of Sarvam's internal reasoning use.

For Veda depth profiles, prompt and completion capacity remain independent from calls and money. Quick reserves up to 72,000 input and 131,072 output tokens; standard 180,000 and 196,608; deep 416,000 and 245,000. At official uncached prices and the existing 1.2 reservation multiplier, the respective worst-case reservations are ₹8.244288, ₹13.532832, and ₹19.969200. The deep profile therefore fits the ₹20 internal ceiling at its configured token maxima; the accepted live job uses standard depth. These are conservative estimates, not account billing certainty. Prices exclude GST, with the separately confirmed ₹5 headroom inside the user's ₹25 total ceiling.

Replace the separate compatibility probe with the real persisted planning operation as the first structured request. The actual appraisal operation subsequently exercises Veda's appraisal schema. The local runner uses isolated SQLite, the real browser/API, a 24-request process hard cap consistent with standard job quota, per-job ₹20 reservations, zero paid fallback, zero automatic retries, and a process circuit after the first provider error. Each exact request reserves cost atomically before dispatch. Unknown usage/cost remains unknown. The report is only successful if every required AI operation is accepted, the report and citations persist, and the browser inspects the cited source passage and methodology plus a report export.

The current public docs do not expose an account-balance API. Before dispatch, the user confirmed that current Credits Left covers ₹25 and Auto-recharge is off. The runner records this as user-reported dashboard confirmation, not an independent account query.

## Consequences

- glm5.3-flash can be selected through job-pinned provider/model settings without changing research schemas or stage prompts.
- A successful plan call is the first real compatibility output; no isolated synthetic response is misrepresented as research success.
- Strict output schemas, exact model identity, validated source/passage links, durable reservations, refusal/truncation diagnostics, and no-unsafe-retry behavior remain in force.
- GLM reasoning-token count stays null unless Sarvam supplies a numeric field. The aggregate completion_tokens remains the billable output count and is not added to reasoning a second time.
- Per-request limits and total job spend remain separate. A job may be safely limited before all stages if exact prompt reservations exceed its remaining budget.
- sarvam-105b remains selectable with its prior capability and task limits.
- LangChain and LangGraph remain rejected under ADR-0038: neither removes Veda's SQL leases, checkpoints, quota reservations, exact-schema validation, or uncertain-POST policy.

## Verification and status

The GLM registry, strict request payload, explicit reasoning effort, output usage accounting, old-model ceiling, ₹20 job creation, cost envelope, workflow reasoning/hash identity, no-retry failure guard, and sanitized diagnostics have deterministic tests. The live browser runner uses the complete research workflow; no separate compatibility request is sent.

### T-126 live validation addendum (2026-10-31)

The first live GLM-5.3 Flash research workflow completed under the separately authorized ₹25 total ceiling. Isolated SQLite job `67096439-7ea1-4605-9a1d-8dac76e5c9c3` persisted report `ab9eed84-eb89-4d33-a228-2eb34f762936`. The real Sarvam route accepted 12/12 strict structured operations: planning 1, appraisal 8, comparison 1, synthesis 1, semantic citation audit 1. No retries, uncertain resend or provider fallback occurred. Crossref/OpenAlex yielded 40 candidate occurrences and 14 selected records. The actual browser opened the report, a citation, the linked source passage and methodology, and downloaded its Markdown export. The exact output and usage ledger are in `evaluation/sarvam-glm53-research-20261030T211603703874Z.json`; a source-level quality review is in `evaluation/t126-live-report-quality-review-2026-10-31.md`.

Operational execution is now demonstrated, but the persisted report is `completed_with_limitations`, not scientifically validated. It used 11 abstract-only and 3 metadata-only sources with no full text; 4 of 14 sources were not methodologically assessed; no hypothesis pair was produced; semantic review marked two findings partially supported and one qualification insufficient; and the uncited-material scan was truncated. Sarvam returned token usage but no provider-reported INR cost. Veda's ₹1.0386306 figure is a conservative token-price estimate, not an account charge. Scientific-quality review, cost reconciliation and production acceptance remain separate work.

## Official sources

- [GLM-5.3 Flash model](https://docs.sarvam.ai/api/token-factory/models/glm-5-3-flash)
- [Token Factory model catalog](https://docs.sarvam.ai/api/token-factory/models)
- [Chat Completions](https://docs.sarvam.ai/api/token-factory/chat-completions)
- [Responses API](https://docs.sarvam.ai/api/token-factory/responses-api)
- [Pricing and rate limits](https://docs.sarvam.ai/api/getting-started/pricing)
- [Billing and payments](https://docs.sarvam.ai/api/platform/billing)
