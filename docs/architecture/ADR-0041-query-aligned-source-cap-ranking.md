# ADR-0041: Use recorded query alignment in scholarly source-cap ordering

- **Status:** Accepted
- **Date:** 2026-10-31
- **Decision owners:** Veda engineering

## Context

Discovery persisted the exact Crossref/OpenAlex query for each candidate, but the source-cap sorter scored every title and abstract against only the broad user question. In the T-126 ledger, *The Effects of Generative AI on High Skilled Work: Evidence from Three Field Experiments with Software Developers* was returned by a purpose-built empirical-study query, passed the original-question topic gate, and was excluded at the source cap. Its question score was `0.190909`; recomputing the same bounded lexical formula against its recorded provider query gives `0.269231`. That is evidence of a query-to-ranking mismatch, not evidence that the paper is credible or that lexical overlap establishes relevance.

## Decision

For scholarly candidates, preserve the existing original-question relevance feature record and compute a second, separately named lexical feature record from the exact provider query that returned the occurrence. The selection score is `max(original_question_score, recorded_provider_query_score)`. Ties use the original-question score and then the existing stable identity, query-order, provider, and occurrence tie-breaks.

The original question remains authoritative for the topic-overlap eligibility gate. Query alignment changes ordering among eligible records only. It does not assess source quality, study design, validity, claim support, or truth. The API and browser expose both scores and the selection score, and the discovery event names the algorithm and features. The fields are additive in stored relevance JSON; older candidate rows remain readable.

## Alternatives considered

1. **Keep question-only ranking.** This preserves the prior algorithm but demonstrably ignores the intent of focused, logged searches and can spend a bounded source slot on an adjacent hit over a source that directly matches the executed query.
2. **Rank by provider query alone.** Rejected because it could make a narrow counterevidence or design query dominate the user's original scope.
3. **Use an arbitrary weighted blend.** Rejected because the available run demonstrates a mismatch but does not establish defensible blend weights. Taking the stronger of two independently recorded lexical signals is explicit, bounded, and requires no tuned coefficient.
4. **Add semantic or learned ranking.** Deferred until a labeled relevance set supports an evaluation. It would add a model/dependency and risk conflating topical similarity with evidence quality.

## Consequences

- Planned subqueries can recover candidates that match their stated search purpose but only partially overlap a concise research question.
- The source-cap decision is more auditable because it retains both input queries and both feature sets.
- Lexical false positives remain possible. The conservative original-question topic gate, exclusion ledger, and human-reviewed relevance evaluation remain necessary.
- The T-126 saved report is immutable and was not rerun. This repair is offline-verified only; its effect on future real scholarly runs is not live-validated.

## Verification

`backend/tests/test_workflow.py::test_recorded_subquery_alignment_can_promote_a_source_before_the_cap` reproduces the old selection failure with the T-126 question and a provider query. It verifies that the field-experiment candidate moves above a question-only-ranked candidate while retaining its lower original-question score, and that a source failing the original-question topic gate remains excluded. Existing lexical-schema and candidate-ledger tests cover old records, explainability, stable API ordering, and exclusion behavior.
