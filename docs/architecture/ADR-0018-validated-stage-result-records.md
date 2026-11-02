# ADR-0018: Validated stage-result records

- **Status:** Accepted
- **Date:** 2026-10-29
- **Task:** T-60

## Context

The workflow already had bounded versioned schemas for source candidates, event metrics, checkpoint sections, report payloads, appraisal, and comparison records. Some producers still annotated their intermediate values as dictionaries, and several other fields relied on type hints without runtime validation. Mutable stage results could also be changed after construction and before persistence. Passage and claim extraction had exact-span helpers, but their transient records did not share one strict stage-boundary contract.

## Decision

Use `CandidateOccurrenceV1`, `JobEventDataV1`, and `ReportCitationMapV1` at the stage boundary while preserving their existing persisted and browser-facing shapes. Validate every `StageResult` collection against its existing record model or a bounded v1 record at construction and again at the start of persistence. This includes candidate, source, retrieved-document, passage, claim, appraisal, relationship, hypothesis, checkpoint, citation-map, report, and provider-usage data. Stage messages, transitions, counts, collection sizes, IDs, JSON metadata and event payloads have explicit limits.

Transient passage and claim records carry `schema_version: 1`, preserve the existing `identity_version` and `atomization_version` semantics, and verify content hashes, deterministic document/passage identity, same-source document/passage ownership, and exact claim-span text before persistence. Provider `ScholarlyWork` and the claim atomizer's `ClaimUnitSpan` remain adapter/domain types; they are converted to Veda-owned v1 records before leaving their producer. `ProviderUsage` remains a provider-runtime dataclass, now with bounded field validation. Versioned `extensions`, provider metadata and sanitized job-event extras remain JSON-valued compatibility areas under depth, item, string and 64 KiB limits; they are the only intentionally open-ended records at this boundary.

No relational columns or database models changed, so this decision requires no migration. Existing flat API and event keys remain stable. Existing legacy reads continue through the established in-memory upcast paths without rewriting rows.

## Consequences

- Invalid or mutated stage values fail before persistence rather than surfacing as downstream attribute errors or partial records.
- Candidate persistence checks its canonical provider identity; passages and claims are tied to the exact document, source and span that produced them.
- The schemas establish structure and internal provenance only. They do not establish source quality, claim truth, rights clearance, or scientific validity.
- The remaining M-26 audit is scoped to intermediate structures outside `StageResult`; the master-spec audit (T-19) must create a separate task if it finds an independently actionable gap.

## Verification

The T-60 progress entry records focused contract tests, the full backend result, static checks, browser fixtures, and the fresh SQLite migration round-trip/Alembic consistency result. PostgreSQL runtime, live providers and human-reviewed research quality were not exercised.
