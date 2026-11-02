# ADR-0017: Versioned appraisal and comparison payloads

- **Status:** Accepted
- **Date:** 2026-10-29
- **Task:** T-59

## Context

Structured appraisal and comparison model responses already used strict input schemas, and the stage producers filtered IDs against retrieved records. The assembled objects then crossed `StageResult` as mutable dictionaries. Persistence trusted those dictionaries, while source/claim API reads returned JSON columns without an explicit compatibility boundary. Checkpoint state was also carried through `appraisal_updates` using a reserved `__checkpoint__` key, mixing separate data lifecycles in one field.

## Decision

Use bounded Pydantic v1 records for persisted source methodological appraisal, claim appraisal/economic facets, evidence relationships, and competing hypotheses. Unknown legacy fields are retained only in bounded `extensions` on valid normalized records. Strict writes reject unknown fields and oversized payloads; API reads upcast compatible legacy records in memory and never rewrite the database row. Malformed or future-version optional appraisal/comparison data degrades to an explicit `legacy_unvalidated` state so it cannot make source or claim evidence unavailable.

`StageResult` carries typed appraisal and comparison records. Checkpoint changes use a separate `checkpoint_update` field. Before persistence, source appraisals are checked against passages owned by that source, claim appraisals against the claim's exact passage, and comparison/hypothesis links against claims owned by the current job and each claim's exact stored passage. Duplicate model evidence links are coalesced by claim. A hypothesis group must contain distinct A/B alternatives; persistence tolerates a replay where either side already exists.

All model-assisted statuses remain `model_assessed_not_independently_verified`. The record types prove bounded structure and referential integrity only; they do not prove the interpretation, methodology, or conclusion is scientifically correct.

No relational columns changed, so this decision requires no database migration. The stable API keeps its existing outer response fields and adds the versioned appraisal shape.

## Consequences

- Appraisal and comparison writes now fail closed on malformed records and cross-source/cross-claim passage references.
- Existing valid JSON rows remain unchanged at rest and are normalized only when read.
- Future appraisals can be additive through bounded extension maps, but schema versions still need explicit handling.
- Evidence relationships still store only two claim links; duplicate links from a model are merged before persistence.
- Model output remains advisory; human annotation and live model quality checks are tracked separately in T-38/T-17/T-30.
- Remaining transient `StageResult` dictionaries (`candidates`, `event_data`, and `citation_map`) are assigned to T-60. M-26 remains partially implemented until that audit and any further requirement gaps close.

## Verification

See `docs/implementation-progress.md` for the exact focused/full test commands and results. T-59 required no schema migration; the fresh SQLite migration round-trip and Alembic consistency check passed independently.
