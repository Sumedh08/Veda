# ADR-0006: Immutable retrieved-document snapshots and stable passage identity

**Status:** Accepted, implemented locally on 2026-10-29

## Context

Veda previously stored only the passage's source ID, ordinal, locator, content hash, access class, and content. Its uniqueness constraint was `(source_id, content_hash)`, so identical text in an abstract and a later full-text version could be merged. Passage primary keys were random UUIDs, so a safe stage replay that rediscovered the same source evidence could assign different IDs. Provider retrieval JSON carried some document hash/version/date fields, but no relational document record linked that provenance directly to each passage. Job checkpoints also had no independently validated envelope version.

## Decision

- Persist a `RetrievedDocument` metadata record per source snapshot. It captures schema version, provider/repository version where known, SHA-256, retrieval timestamp, source locator/host, media type, access class, hash scope, and bounded policy metadata. Veda does not persist raw HTML/PDF bytes.
- Describe hash scope explicitly. HTML/PDF records hash the downloaded raw bytes; abstract records hash the bounded excerpt; statistics records hash the normalized observation snapshot. These different hashes are not presented as interchangeable raw-document hashes.
- Generate version-1 document and passage UUIDs deterministically. Passage identity includes source ID, immutable document ID, normalized locator, and the exact UTF-8 passage content hash. Same source/version/locator/text repeats the same IDs; changed source version/content or locator creates a distinct passage. A unique `(source_id, identity_key)` constraint fences duplicate insertion.
- Keep legacy citation IDs unchanged. The migration associates old passages with a source/access-class legacy snapshot, marks identity version 0, records that original bytes/version are unavailable, and derives an identity key from the existing passage ID. It does not fabricate a historical document hash.
- Persist a versioned checkpoint envelope while retaining its existing top-level keys. Known fields are type-checked; unknown legacy keys survive round trips. Existing structured provider reservations already persist versioned operation/schema names and a request hash over the prompt, output schema, and token cap without storing prompt contents in the usage ledger.
- Return the linked document version and hash scope with passage inspection so users can distinguish an abstract excerpt from a later full-text snapshot.

## Migration and rollback boundary

The additive Alembic migration creates legacy snapshot records and keeps all historical passage and claim IDs intact. Downgrade refuses to run if a source has the same passage content hash in multiple document versions, because the prior schema cannot represent that identity without losing provenance or deleting an evidence link. No destructive resolution is automated.

## Verification boundary

Unit and workflow tests cover strict record/checkpoint validation, deterministic replay IDs, distinct identities for identical text in different versions, passage-to-document API provenance, and migration backfill with a legacy claim link. SQLite migration upgrade/downgrade/re-upgrade and schema consistency are checked. PostgreSQL transaction behavior remains under T-09; real publisher bytes and provider-version quality remain externally unverified under T-17/T-30/T-38/T-42/T-50.
