# ADR-0013: Versioned job-event metric payloads

**Status:** Accepted  
**Date:** 2026-10-29

## Context

The event record and its API response now have representation version 1, but
`JobEvent.data_json` still contains stage- and control-specific metric keys
without a payload version. Discovery, extraction, appraisal, comparison,
verification, synthesis and control endpoints also have different payload
shapes. Internal report-coverage readers rely on existing top-level keys such
as `claim_count` and `provider_query_latencies_ms`.

## Decision

- Persist new event payloads with additive `data_schema_version: 1`.
- Validate common metric fields and nested planning/ranking structures with
  `JobEventDataV1`. Keep established metric names at the same top level; do not
  nest or rename them. Keep stage-model `schema_version` separate from the
  event-payload version.
- Preserve unknown legacy and forward-compatible JSON keys as top-level extras
  while bounding nesting depth, collection sizes, key/string lengths and total
  payload size. Reject malformed known metrics and unsupported payload-envelope
  versions.
- Normalize old payloads at API reads without rewriting stored rows. Add the
  version at the single `append_event` write boundary so internal readers and
  new events see the same payload contract.
- Exclude unset optional model fields from the event response so a schema
  declaration does not add unrelated `null` metrics to existing payloads.

## Consequences

No database migration is needed. Current metrics remain readable by the UI,
report assembly and other internal consumers. Unknown legacy values are
preserved within explicit JSON bounds. The schema validates established metric
fields but intentionally allows additional bounded fields; provider metadata
and other arbitrary stage payloads remain under M-26/T-56 rather than being
claimed as fully typed.

## Verification boundary

Tests cover known-field validation, envelope-version rejection, payload bounds,
legacy API upcast without database mutation, all seven completed research
stages, internal event consumers, and browser rendering of a versioned
`claim_count`. The backend and fixture-backed browser suites pass locally; two
PostgreSQL integration tests remain skipped. No live provider or research
quality is established by these checks.
