# ADR-0014: Versioned provider-specific source metadata

- **Status:** Accepted
- **Date:** 2026-10-29
- **Task:** T-56

## Context

Crossref, OpenAlex, World Bank Data360, and ILOSTAT return different metadata
shapes. Veda stored these dictionaries in `Source.metadata_json` without a
provider-specific validation boundary. Discovery also reads fields such as
`selection_block_reason`, `statistics`, and OpenAlex's best open-access
location, so malformed values could affect selection or downstream analysis.
Existing rows contain unversioned metadata and must remain readable.

## Decision

Add provider-keyed Pydantic v1 contracts at provider ingress, source
persistence, and API reads. Known fields retain their current top-level names
so existing workflow consumers continue to work. Unknown legacy keys are
retained in bounded `extensions` objects at their corresponding metadata level;
empty nested extension objects are omitted. The source API reports
`provider_metadata_schema_version` after successful validation.

Provider metadata is descriptive provenance only. It is not a rights decision,
retrieved evidence, or scientific/methodological appraisal. Rights and evidence
remain in their existing independent records.

The boundary limits serialized metadata to 64 KiB, nested depth to 12, arrays
to 1,000 entries, and individual strings to 16,384 characters, with narrower
limits on known provider fields. New writes are v1. Unversioned rows are
upcast on read without database mutation. Unsupported future versions or
malformed known fields are rejected at provider ingress. The optional metadata
portion of a source API response degrades to absent metadata when a legacy row
is malformed, while the source and its evidence remain inspectable.

No migration is required because the records remain in the existing JSON
column and reads are compatibility-aware.

## Alternatives considered

- **Keep a universal untyped dictionary:** does not validate provider-specific
  shapes and leaves dynamic metadata trusted throughout the workflow.
- **Drop unknown fields:** would lose existing catalog context during a
  compatibility upcast.
- **Move each provider into new database columns/tables:** adds migration and
  deployment coupling without improving the bounded JSON contract needed by
  current consumers.

## Verification

Tests cover all four provider shapes, malformed known fields, unsupported
versions, JSON size/depth limits, nested legacy extensions, API compatibility
without legacy-row rewrites, and persistence through scholarly/statistics
workflow runs. Full backend, frontend unit/build, Ruff, and browser results are
recorded in `implementation-progress.md` and `evaluation/RESULTS.md`.
