# ADR-0055: Optional bounded AI candidate relevance and read-only discovery access

- **Status:** Accepted for bounded implementation; effectiveness not independently evaluated
- **Date:** 2026-11-03
- **Related:** T-140, T-141, T-143, T-144, B-010, B-017

## Context

Veda's deterministic lexical selector can exclude relevant works whose titles use different terminology. At the same time, the workflow already has source identity and rights gates, passage-backed appraisal, claim comparison, adaptive evidence sufficiency, synthesis, and semantic citation audits. Adding another document-analysis or report-generation subsystem would duplicate those responsibilities. The read-only MCP prototype could search stored evidence and inspect source provenance, but not the saved candidate ledger.

The remaining retrieval gap is real but not benchmark-labeled: the saved 2026-11-03 India run selected eight metadata-only scholarly sources, retrieved no documents, and produced no passages. This does not establish that lexical ranking caused the acquisition failure. The frozen D1/H1/H2/H3 question set is retained for later transferability review; no relevance labels or expected answers were added.

## Decision

Keep Veda's existing sequential pipeline. When the user explicitly opts in per research job, run at most one structured candidate-relevance review over a bounded pool of up to 12 deduplicated bibliographic records. The pool reserves capacity for lexical topic-gate misses. The model receives the research question, title, publisher label, year, source type/provider, and deterministic lexical features; it does not receive abstracts, author names, DOI, URLs, or provider record IDs. Candidate text is untrusted data.

The model may change bibliographic ordering and recover a lexical miss only when it returns `directly_relevant`. It cannot bypass malformed-title, duplicate, provider block, identity, source-governance, rights, access, or acquisition checks. Lexical features and model assessment remain separate, and provider/model/reason are persisted in the existing candidate record and discovery event. The request uses Veda's existing per-job model reservations, token limits, provider allowlist, uncertainty handling, and usage accounting. It is off by default; unavailable or blocked model calls leave deterministic behavior in place.

Keep existing source-by-source/claim appraisal, comparison, gap/sufficiency evaluation, synthesis, and citation audits. Their model outputs remain marked model-assessed rather than independently verified. Deterministic HTML/PDF/JATS/TEI acquisition remains unchanged; this decision does not claim to improve document acquisition.

Extend the local read-only MCP interface with a bounded `list_research_candidates` tool backed by the authenticated owner-scoped API. It returns allowlisted bibliographic and relevance metadata only; abstract text is omitted and candidate access/rights remain explicitly not assessed. Candidate URLs are projected only when they are syntactically valid public HTTP(S) URLs within the 800-character output bound; unsafe or overlong URLs are omitted rather than truncated. Existing source/passage disclosure gates still govern exact passage text. No MCP job-creation, external document fetch, database access, remote hosting, or client-specific integration is added.

Add a client-neutral Veda research `SKILL.md` as optional documentation. It names only implemented MCP tools, distinguishes candidate metadata from evidence, and requires source/passage inspection and uncertainty disclosure. It is not installed into external clients.

## Alternatives considered

- **Keep lexical selection only:** safest and deterministic, but cannot recover all semantic terminology differences; it remains the fallback and audit baseline.
- **Use a relevance model for every candidate or let it construct URLs/searches:** rejected. It increases cost/privacy exposure and would widen authority beyond the verified provider pipeline. A bounded batch over fixed records is simpler and auditable.
- **Add a new document-analysis or multi-agent framework:** rejected. Existing passage-backed appraisal, comparison, sufficiency, synthesis and citation-audit stages already cover those jobs; duplication would increase cost and provenance complexity.
- **Make MCP the research engine:** rejected. MCP can expose existing authorized evidence and metadata but does not discover, verify, or acquire content. The local read-only server remains complementary.
- **Expose all stored abstracts or passage text through MCP:** rejected because retention for private analysis does not establish external disclosure permission.

## Verification and limitations

Offline tests cover bounded candidate selection including lexical misses, strict output schemas, exact candidate-key coverage, hard selection blocks, a normal discovery-stage promotion fixture, default-off job persistence, metadata-only MCP output, unsafe and overlong URL suppression, and existing MCP protocol behavior. Browser coverage checks that the opt-in defaults off and is sent only after user selection. No live model inference, external client connection, or live research question was used. The fixture proves wiring only; semantic improvement, false-positive rates, and model quality remain unmeasured. No database migration or new runtime dependency is required.
