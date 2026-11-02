# ADR-0047: Versioned source governance without prestige truth scores

- **Status:** Accepted
- **Date:** 2026-11-01
- **Context:** Veda must search beyond academic indexes while avoiding indiscriminate web aggregation. Source identity and list membership are useful for query coverage and audit, but cannot establish document relevance, methodology, evidence strength or truth. Ranking data also have year/category identifiers and licensing constraints that cannot be inferred from a university or journal name.

## Decision

Maintain one strict, versioned source registry at `backend/app/research/source-governance-registry.json`. Persist a typed source-governance decision on discovery candidates and sources, including identity provenance, source classes, exact institution/provider identifiers, verified academic classification, methodology-review requirement and adapter state. Expose those fields and planned/searched/missing source classes in the existing coverage and source-inspection UI.

Keep source relevance and methodology separate from registry identity. Use only a verified QS top-250 rank, subject/year-specific Q1, or versioned FT50 membership as an exact categorical tie-break after relevance; never as a truth score or a substitute for appraisal. Retain relevant unregistered counterevidence for explicit review. Unknown generic sources are not promoted to fill a class quota. Report unavailable source classes honestly.

The registry schema supports ranking records, but the shipped QS/Q1/FT50 collections remain empty until exact identity, year/category, provenance and permitted reuse have been reviewed. Official World Bank publication discovery is not enabled for the application because the current API terms limit use of its materials to non-commercial use absent permission, and Veda's distribution/use scope is not established. Existing Crossref/OpenAlex and narrow statistics routes remain in place.

## Rationale and consequences

This reuses the current persisted discovery-candidate, source API, coverage and browser-inspector seams; no new orchestration framework or source database is needed. A classification can be inspected and audited without implying evidence quality. Because not every source class has an adapter, the planner and report must expose missing coverage rather than silently call discovery comprehensive.

The v2 registry currently contains 23 organization identities but no university ranks or journal-list records. Public Crossref metadata demonstrated one World Bank DOI-prefix match at the adapter level. This does not verify study methods or persist a live report. QS data rights and direct institutional publication connectors remain a product-use/license gate. See [source-governance verification](../research/source-governance-verification-2026-11-01.md).
