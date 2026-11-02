# ADR-0012: Versioned research scope and job/event representations

**Status:** Accepted  
**Date:** 2026-10-29

## Context

The database stores a job's scope in a JSON column, and older rows have no
format marker. Job and event responses also lacked an explicit representation
version. Requiring a destructive data rewrite would add deployment risk without
benefit: scope lives in one bounded JSON field and legacy values can be adapted
when read.

## Decision

- New scopes use strict, bounded `ResearchScopeV1` fields and carry
  `schema_version: 1` in the saved JSON. Unrecognized keys in unversioned legacy
  objects are retained under `extensions`; already-versioned values must
  validate as v1, and unsupported versions fail closed.
- Job API records and individual event API records declare
  `schema_version: 1`. Their FastAPI response models expose this contract in
  OpenAPI as well as at runtime.
- `JobEvent.data` retains its existing metric keys. The version identifies the
  containing event representation and does not reinterpret the meaning of
  stage-specific metrics.
- API and worker snapshot reads normalize legacy scopes in memory. Reads do not
  rewrite existing database rows, and deferred continuation copies the
  normalized scope without losing known fields.

## Consequences

No migration is required. New writes are bounded and versioned; old scopes
remain unchanged in storage and appear in a compatible versioned envelope.
Unknown legacy keys remain available under `extensions` rather than being
silently discarded. Provider-specific and stage-specific metadata payloads are
still under the M-26 audit; this decision does not make those arbitrary JSON
records typed or independently validated.

## Verification boundary

Schema, API, worker snapshot, legacy-preservation and metric-preservation tests
run locally with SQLite. Browser fixtures verify the UI still renders the
versioned scope and consumes the existing event metric. These checks do not
verify PostgreSQL, a live provider, or research quality.
