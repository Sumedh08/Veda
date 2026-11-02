# ADR-0015: Typed, bounded research checkpoint sections

- **Status:** Accepted
- **Date:** 2026-10-29
- **Task:** T-57

## Context

`ResearchJob.checkpoint_json` is the durable recovery and stage-handoff record.
Its version-1 envelope previously used arbitrary dictionaries for saved depth
limits, v2/v3 plans, follow-up context, citation audit/map, and deferred
retrieval continuation. Recovery and API readers then trusted those shapes
directly. These fields are central to resumability, lineage, and report
inspection, so malformed records must not be interpreted as if they were
valid.

## Decision

Keep the existing JSON column and top-level section names. Make the checkpoint
envelope strict and type known section payloads, including a shared bounded
depth-profile contract used by both saved plan generations. New job creation,
continuation, and stage persistence use strict validation. The API and worker
read path upcasts legacy checkpoint objects in memory without rewriting the
database row.

Legacy v2 and v3 plans remain valid. Unknown top-level and section fields are
retained under explicit `extensions` containers. A malformed legacy known
section is retained under `extensions.invalid_legacy_sections`, omitted from
its active field, and left unchanged in storage; consumers then use their
documented safe fallback (for example, the job's configured depth profile).
Unsupported checkpoint envelope versions still fail closed.

The whole checkpoint is bounded to 256 KiB, depth 12, 1,000 items per array,
128 object entries, and 16,384 characters per string. Known fields have
narrower type and length limits. The persisted citation map retains its
existing label-to-source shape so current workflow readers remain compatible.

No migration is needed because the record remains in the existing JSON column
and legacy reads do not mutate it.

## Alternatives considered

- **Continue treating all sections as `dict[str, Any]`:** keeps recovery
  readers exposed to arbitrary shapes and does not validate the saved plan or
  citation links.
- **Reject every malformed legacy checkpoint:** would prevent unrelated
  source/report inspection and could stop a worker on a damaged optional
  section. The chosen behavior isolates and preserves the bad section while
  allowing unrelated sections to recover safely.
- **Rewrite or migrate all existing rows:** adds unnecessary write and
  deployment risk; compatibility upcasts are sufficient for current users.

## Verification

Tests cover bounded profiles and plan resource limits, both plan generations,
follow-up metadata, citation audit/map, retrieval continuation/retry payloads,
unknown extensions, malformed legacy fallback without row mutation, strict
new writes, restart/continuation journeys, and the source/workflow API paths.
Full backend and static/UI checks are recorded in `implementation-progress.md`
and `evaluation/RESULTS.md`.
