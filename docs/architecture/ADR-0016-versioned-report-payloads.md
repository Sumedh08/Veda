# ADR-0016: Version persisted report payloads

- **Status:** Accepted
- **Date:** 2026-10-29
- **Decision owners:** Veda engineering

## Context

`ResearchReport.citation_map_json` and `verification_json` were persisted and returned as unbounded JSON dictionaries. The report is written through both the deterministic limitation-aware builder and the model-assisted synthesis/audit builder. It is read through the job report endpoint, immutable report history, archived-safe inspection, per-report JSON export, the account export and the browser's citation and verification inspectors. Citation reference integrity and a model's semantic support judgment are different kinds of evidence and must not share one status field.

## Decision

1. Keep the existing JSON columns; this change requires no relational migration.
2. Store new citation maps in a schema-v1 `{schema_version, citations, extensions}` envelope and verification data in a schema-v1 `{schema_version, record, extensions}` envelope. The report's existing `report_schema_version` remains an independent report-format version (currently v1 or v2).
3. Bound new report payloads, known field lengths and counts. Require deterministic report checks to use `deterministic_link_integrity_only`; place their status and claim-link counts in a typed `citation_link_integrity` object. Place semantic and uncited-claim model judgments in a separate typed `semantic_assessment` object whose method explicitly states that it is not independently verified. Existing flat API fields remain as compatibility aliases.
4. Validate the transient synthesis result before persistence. `StageResult.report` is now a typed `BuiltReportStageV1`, so neither report builder can bypass the same map/verification contract.
5. Normalize valid legacy flat JSON in memory for report APIs and exports; do not rewrite historical rows. Unknown legacy keys are retained in bounded extensions. Malformed or unsupported optional legacy payloads degrade to an empty citation map or a `needs_review` verification record, while the report body and evidence remain available.
6. Keep the report API's `citation_map` shape stable and add explicit `citation_map_schema_version` and `verification_schema_version` fields. Both report JSON export and full account export use the normalized schema-v1 envelopes.

## Consequences

- Existing browser citation lookup and status fields continue to work; report inspection also exposes the separate typed integrity and semantic-assessment objects.
- Existing valid report rows remain readable and unchanged. No schema migration is needed, but consumers reading the raw report JSON columns must understand the new envelopes for new rows.
- New report writes fail closed on unsupported versions, inconsistent deterministic/semantic sections, invalid spans, unbounded objects, or malformed known fields. Unknown legacy data is not silently promoted to a known field.
- A passing deterministic link-integrity check says only that stored claim/source/passage links resolve. It is not a semantic citation-support result or scientific verification.

## Verification

T-58 added strict-write, legacy-read/no-rewrite, malformed-record, separate-assessment, deterministic-builder, model-assisted-builder, persistence, report-history, inspection, per-report export, and account-export tests. The model-assisted end-to-end fixture does not call a model provider. Verification results are recorded in `docs/implementation-progress.md` and `evaluation/RESULTS.md`.
