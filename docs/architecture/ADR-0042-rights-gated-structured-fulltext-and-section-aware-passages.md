# ADR-0042: Rights-gated structured full text and section-aware passage selection

- **Status:** Accepted
- **Date:** 2026-10-31
- **Decision owners:** Veda engineering

## Context

T-126 completed its model workflow but selected 14 sources with no full-text evidence. A later local integration smoke showed that Europe PMC had returned a legally permitted JATS article with Methods and Results, yet the bounded passage cap could be consumed by abstract paragraphs before those sections were represented. The ingestion path also needed DOI-only Europe PMC identity resolution because OpenAlex did not always provide a PMCID.

## Decision

1. Keep discovery and full-text acquisition separate. Reuse canonical source records and `RetrievedDocument` versions; retain provider query and access provenance.
2. For Europe PMC, preflight exact PMCID or DOI identity and article reuse metadata before requesting JATS. Do not download when rights are unknown, denied, or require review. Persist the discovered PMCID, DOI, license evidence, parser version, content hash, section catalog, and extraction outcome.
3. Parse JATS/TEI as untrusted XML. Strip only a syntactically external DOCTYPE before parsing; reject entity declarations and internal subsets. Hash the original response bytes. A parser failure is an explicit retrieval failure, never an abstract/full-text substitution.
4. Allocate bounded structured passages across section types, preferring Methods, Results, and Limitations before narrative sections and Abstract. Within a section type, preserve document order; after selection, persist passages in source order. Record the selection algorithm.
5. Preserve the abstract as a separate `RetrievedDocument` representation when richer text is retrieved, but do not let abstract passages consume the full-text passage allocation. When full text is unavailable, retain bounded abstract passages; metadata-only records remain metadata-only.
6. Keep GROBID behind an optional, loopback-only adapter for PDF-to-TEI conversion. If unavailable or unsuccessful, report that exact outcome and use only the existing bounded PDF text fallback where permitted. Do not claim GROBID succeeded when it did not.
7. Keep OpenAlex's metered content endpoint disabled. Its ordinary metadata endpoint remains available for discovery; a public OA flag alone does not establish the license needed to store/display text.

## Consequences

- Existing relational tables and persisted report contracts are reused; this decision adds no database migration.
- The bounded section-first selector preserves methods/results evidence under abstract-heavy documents without weakening passage, source, rights, or claim validation.
- Europe PMC DOI lookup and sanitized external-DOCTYPE handling are covered by regression tests. One live, model-disabled local API/browser smoke retrieved and inspected a CC-BY JATS source's Methods and Results. The source was an unrelated agriculture article and demonstrates transport/parser/persistence/UI behavior only; it supplies no evidence for T-126's developer-productivity question.
- A target METR arXiv v2 source is marked CC BY 4.0 on its abstract page, but OpenAlex's selected submitted-version location reports no license. arXiv's official API terms state that the legacy metadata API omits full-text license, allow content use for research, prohibit storing/serving content unless the specific license permits it, and require legacy API calls to stay at no more than one per three seconds. Programmatic full-text harvesting is directed to arXiv's export/bulk mechanisms. Veda therefore does not infer permission from OpenAlex's generic OA flag or add a direct HTML scraper in this decision. See `docs/research/arxiv-access-contract-2026-10-31.md`.
- The T-126 report remains unchanged, with zero full-text sources. A future relevant live research run still needs separately authorized model inference and human quality review.

## Verification

- Focused structured XML, Europe PMC, JATS/HTML passage-allocation and retrieval workflow tests pass.
- The complete backend suite, frontend unit suite/build, fixture browser suite, and a separate real public scholarly API/local-browser smoke pass as recorded in `evaluation/RESULTS.md`.
- No model inference, paid content API, cloud service, or external deployment was used for this ADR's validation.
