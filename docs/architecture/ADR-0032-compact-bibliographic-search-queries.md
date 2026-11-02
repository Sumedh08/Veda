# ADR-0032: Compact provider-facing bibliographic queries

- **Status:** Implemented; local planner/retrieval tests pass. No post-change live provider comparison has run.
- **Date:** 2026-10-29
- **Decision owners:** Veda engineering

## Context

The one-time live run's saved Crossref/OpenAlex query rationales were full question sentences and concatenated scope prose, often truncated at 300 characters. Queries therefore contained case counts, generic syntax and partial final words. Discovery returned irrelevant metadata in several cases. The job still stores the user's original question and scope; the provider query does not need to repeat that prose.

## Decision

- Generate provider-facing queries as ordered, deduplicated keywords from the question first, then supplied scope and focus terms.
- Drop question grammar, generic decision framing and case-size/time counts; preserve explicitly stated four-digit years, research concepts, outcomes and location terms that survive the bounded token cap.
- Preserve the full job question, scope, query rationale and stopping criteria. Each compact query retains its direct/requested-scope/counterevidence/design/limitations purpose in the plan.
- Keep the 300-character/32-term hard boundary and do not expand, rewrite or silently add provider queries during execution.

## Consequences and limits

Keyword bags should reduce truncation and improve precision for bibliographic matching; they may lose phrase semantics or a useful synonym. The conservative topic-overlap gate remains a separate selection rule. Both changes need post-change source review and human relevance evaluation before a retrieval-quality claim. The old live snapshot cannot establish an improvement because its queries predate this change.

## Verification

- Unit fixtures check case-count removal, year retention, diacritic normalization, order, deduplication and term/character bounds.
- Planner and workflow fixtures verify direct, scoped and counterevidence queries remain bounded and purpose-labelled while the user's original job question remains unchanged.
- No external provider request was made to verify this change.
