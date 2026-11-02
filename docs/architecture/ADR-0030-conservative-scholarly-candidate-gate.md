# ADR-0030: Filter scholarly selections by conservative topic overlap

- **Status:** Implemented; local fixture tests pass. Retrieval precision/recall has not been independently measured.
- **Date:** 2026-10-29
- **Decision owners:** Veda engineering

## Context

The one-time ten-case OpenRouter run completed planning, live Crossref/OpenAlex discovery and claim extraction, but did not reach appraisal or report synthesis. Its saved snapshot contained 203 bibliographic candidates and 140 selected sources. A manual title review found many off-topic selections, including a radio-engineering result for a coding-copilot question, nutrition results for a software-copilot question, and animal-housing results for a marketing-content question. Every job selected the full 14-record limit, so the previous ranking did not distinguish a genuinely relevant record from a weak-overlap fallback.

## Decision

- Keep the existing deterministic, explainable lexical score for ordering.
- Before selecting a scholarly record, apply `topic_overlap_gate_v1`: require up to two topical query-term matches (or the one available for a short query), an AI/intervention term or documented alias when the question names one, and either one topical title match or three topical abstract matches. Numeric case details and generic population/time/decision phrasing do not establish topical overlap.
- Preserve rejected records in the candidate ledger with `insufficient_topic_overlap`, ranking features, query provenance and discovery metadata. Do not delete them or represent this gate as a semantic judgment.
- Official statistics retain their separate topical/geography/rights selection rules.

## Consequences and limits

This avoids filling the selected-source list with records that share only generic wording. It can also omit relevant studies that use unrecognized synonyms or that provide their only relevant description outside the bounded metadata fields. The prior-run offline replay passed 38/203 records on title alone; 112/140 previously selected records failed when their saved abstract excerpts were included. That is a signal that the filter changes selection, not an audited precision/recall score. Human review and relevance evaluation remain required before any research-quality claim.

## Verification

- Candidate unit tests cover an irrelevant radio-coding result, a directly aligned AI-copilot result and a non-AI general research question.
- Workflow/retrieval fixtures verify candidate persistence and selection behavior.
- The live snapshot replay is offline and uses old, pre-query-fix retrievals; no additional provider request was sent.


## T-109 metadata-integrity refinement (2026-10-30)

A replay of the preserved ten-case snapshot using the refined current gate found 203 candidate occurrences, 140 historically selected occurrences, 7 malformed-title occurrences (2 historically selected), 44 clean title-only passes, and 104 clean historically selected records rejected by topical overlap. Malformed titles containing issue-page/DOI/PDF/menu artifacts now receive the separate `malformed_bibliographic_title` reason before topical matching; exclusions remain in the ledger. The detector-control title false positive is blocked, while an AI-search title variant is admitted via a direct topic title match. These are deterministic regression examples, not reviewed labels. Full counts and limits are in `evaluation/retrieval-overlap-audit-2026-10-30.md/json`.
