# ADR-0023: Record conditional official-statistics route outcomes

- **Status:** Accepted
- **Date:** 2026-10-29
- **Decision owners:** Veda engineering

## Context

World Bank Data360 and ILOSTAT are conditional discovery routes. The existing
provider query counter records zero both when the topic or geography excludes a
route and when no request runs; a successful request that returns no records
also needs to remain distinct from a failed request. Reports therefore could
not explain whether an optional provider was applicable, attempted, or empty.

## Decision

1. Add a versioned `conditional_statistics_routing` record to new discovery
   events and report search coverage, with one outcome for Data360 and ILOSTAT.
2. Record `searched`, `not_applicable`, or `not_attempted` separately from
   request, result, and failure counts. A request counts as searched even when
   its transport or provider response fails.
3. Restrict skip reason codes to topic/geography applicability and bounded
   execution reasons. Evaluate them in this order: unsupported topic, missing
   geography, unsupported geography, missing query plan, then elapsed deadline.
   The fixed order ensures one safe, reproducible explanation when several
   conditions apply.
4. Include safe explanations in the saved report and browser inspector. Do not
   infer outcomes for historical reports; present the route as not recorded.
5. Keep the JSON-only additive contract. No relational migration is required.

## Alternatives considered

- **Infer status from `provider_query_counts`:** rejected because zero conflates
  inapplicability, unattempted routes, and zero-result searches.
- **Store only a natural-language explanation:** rejected because it would not
  provide a bounded, machine-checkable contract for report consumers.
- **Rewrite historical report rows:** rejected because those runs do not retain
  enough routing evidence to reconstruct the missing distinction.

## Consequences and limits

- New runs explain both conditional providers even when neither is called.
- Provider HTTP failures and zero-result searches remain separately visible.
- The route record reports application logic and request outcomes, not search
  completeness, data relevance, scientific quality, or rights clearance.
- Existing reports remain unchanged and show that route details were not
  recorded.

## Verification

Contract tests reject impossible status/count combinations. Workflow tests cover
positive, topic/geography-negative, failed-request, zero-result, and elapsed
deadline outcomes, plus historical coverage fallback. A real local-API browser
run checks the saved report text and inspector. No model/provider cost is
required for the contract tests; the gated scholarly smoke uses Crossref and
OpenAlex only.
