# ADR-0003: Explainable candidate relevance and conservative identity

- **Status:** Accepted for the local implementation; relevance quality remains unevaluated.
- **Date:** 2026-10-29.
- **Scope:** scholarly candidate ordering within one research job.

## Context

Crossref and OpenAlex return provider-ordered records for multiple planned queries. Provider positions and provider-native scores are not necessarily comparable across providers or queries. The source cap therefore needs a repeatable Veda ordering rule that preserves the search query that found a record and does not turn visibility, citation counts, or journal prestige into a quality judgment. Cross-provider identity must likewise avoid merging records based on uncertain title or publisher-page URL matches.

## Decision

1. Score each scholarly result against the **same original user research question for the job**. Preserve the particular provider retrieval query separately as candidate provenance; do not compare scores whose query denominators differ.
2. Use `lexical_overlap_v1`: case-fold text, extract alphanumeric/apostrophe tokens, remove a fixed English stopword list, deduplicate query terms, and cap the initial query terms at 120. The stored record discloses truncation and the exact retained term set. Score is `0.7 × title term coverage + 0.3 × bounded abstract-excerpt term coverage`, in `[0,1]`.
3. Persist the schema/algorithm version, question basis, query terms, matched title and abstract terms, term coverages, weights, explanation, limitation text, numeric score, and exact per-job `ranking_order`. Order higher scores first; resolve ties deterministically from canonical identity, planned-query order, provider identity, record ID, and stable discovery order.
4. Do not use publisher, venue, author identity, publication year, provider rank, citation count, social popularity, model judgments, or statistical significance as ranking features. A relevance score is retrieval relevance only; it does not measure source quality, validity, support, or truth.
5. Official statistics remain in their separately reserved slot and receive no scholarly relevance score.
6. Canonical cross-provider identity requires a normalized DOI, including a recognized DOI resolver URL. Without a DOI, retain the provider namespace and exact provider record ID. Do not fuzzy-merge titles or normalize generic publisher URLs into shared identity.

## Consequences and limits

- The source-cap selection can be replayed from the persisted feature record and order without another provider request.
- This baseline is lexical and English-centric: it misses synonyms and cross-language matches, may rank titles with repeated topical words highly, depends on abstract availability, and ignores nuanced scope fit. The stopword/tokenizer and weights are versioned code, not calibrated thresholds.
- Scores are comparable only within a job because all use the same original research question. They must not be presented as probabilities or compared across research questions.
- Synthetic/adversarial fixtures test the implementation mechanics. There is no human relevance judgment or measured retrieval-quality improvement; T-38 must evaluate that separately.
- SQLite migration roundtrip and Alembic metadata consistency pass. PostgreSQL execution remains external under T-09.
