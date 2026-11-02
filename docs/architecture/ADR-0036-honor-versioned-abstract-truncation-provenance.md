# ADR-0036: Honor versioned abstract truncation provenance during extraction

- **Status:** Accepted and implemented; regression tested offline
- **Date:** 2026-10-30
- **Related:** ADR-0034, T-119

## Context

The T-119 report included seven claim strings ending mid-sentence. Crossref and OpenAlex had correctly marked the 560-character abstract excerpts as truncated, but `versioned_provider_metadata` preserved that field under `provider_metadata.extensions`; extraction checked only the top-level field and treated the excerpt tails as complete. This was a provenance lookup bug, not evidence that the provider had supplied complete abstracts.

## Decision

Read `abstract_excerpt_truncated` from either the current top-level form or the versioned `extensions` object. If the flag is true, exclude the incomplete trailing fragment before creating passages or claims; if it is absent or invalid, retain unknown provenance rather than guessing. Keep the provider metadata schema version unchanged because the field was already preserved in its extension area.

## Consequences and verification

The T-119 artifact remains unchanged as a record of what the run showed. The workflow now reads the versioned flag, and an API-level regression verifies that a truncated tail is not persisted as a claim. The focused workflow and AI-pipeline test set passed after this change. Existing citations to the affected T-119 fragments remain structurally linked, but their content-quality defect is documented in the evaluation review; no live report is rewritten.
