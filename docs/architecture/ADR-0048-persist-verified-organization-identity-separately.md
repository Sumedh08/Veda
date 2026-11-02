# ADR-0048: Persist verified organization identity separately from research relevance

- **Status:** Accepted
- **Date:** 2026-11-01
- **Context:** T-139 extends the existing OpenAIRE/OpenAlex affiliation-discovery workflow. It can encounter organizations absent from the curated source registry, but those candidates are question-specific while ROR identity and a verified ROR-to-OpenAlex mapping are reusable public facts. Treating a previous topic match as permanent authority or relevance would contaminate later research runs.

## Decision

Persist exact, verified ROR identity facts in a small SQL table with the verification source, source-record update date, verified timestamp, status, aliases, types, official domains/URLs and country. Persist an OpenAlex institution ID only after exact ROR identity resolution. Reuse these public facts for at most 90 days; invalidate the mapping when the upstream ROR source record changes or its own resolution freshness expires.

Do not store topic relevance, publication relevance, study quality, methodology, or evidence strength in this reusable identity cache. Those are job/source-version decisions and remain in the existing job checkpoint and candidate/source provenance records. Organizations without exact ROR identity remain pending and are not promoted by name similarity alone.

## Alternatives considered

- **Keep all identity only in job checkpoints:** simpler, but repeats bounded identity API requests for every later question and provides no durable verified-identity reuse.
- **Persist a universal trust/prestige score:** rejected because identity does not establish relevance, methods, or truth.
- **Add a graph database:** rejected; the existing SQL workflow and affiliation records already express the bounded relationship.

## Consequences

- SQLite and PostgreSQL use the existing SQLAlchemy/Alembic workflow; identity cache upserts are idempotent.
- A new topic still performs question-scoped discovery and OpenAlex publication search; only stable public identity facts are cached.
- Freshness and exact-ID checks are testable without external services; real ROR/OpenAlex identity has been demonstrated in the T-139 holdout.
- The current discovery surface remains academic-affiliation led. This decision does not add a general web-search, consulting, think-tank, or government publication provider.
- Identity lookup failures or stale records do not become verified identities; the job can preserve its discovered evidence and disclose the incomplete verification.

## Verification

- `backend/app/research/organization_identity_store.py`
- `backend/tests/test_organization_identity_store.py`
- `backend/tests/test_workflow.py::test_discovery_persists_openaire_unseeded_organization_publication`
- `backend/alembic/versions/20261101_verified_org_identity.py`
- Real local browser/API evidence: `evaluation/veda-autonomous-holdout-query-repaired-20261101T163139.sqlite3`

