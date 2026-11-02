# ADR-0011: Keep retrieval outcomes separate from evidence access class

**Date:** 2026-10-29  
**Status:** Accepted for local implementation; live-source frequencies remain unverified.

## Context

`Source.retrieval_status` describes which evidence Veda has: licensed HTML/PDF excerpts, an abstract, metadata, or an official statistic. The transport metadata separately records what happened during a retrieval attempt, but older values (`failed`, `deferred`, `unsupported`, `not_attempted`, `retrieved`) were unversioned and the source library did not show them consistently. Replacing the access class with `error` would hide an abstract that remains available when a full-text request fails.

## Decision

- Preserve `Source.retrieval_status` as the evidence access class. Do not rewrite an abstract-only source to `error` because its HTML request failed.
- Persist each HTML/PDF attempt separately in `metadata_json.retrieval.outcomes`, under envelope schema version 1. Each row has a format, one outcome (`not_attempted`, `retrieved`, `partial`, `unavailable`, `error`, or `deferred`), optional observed time, bounded retry delay, and allowlisted machine reason/error codes.
- Translate legacy per-format transport states into the public taxonomy at API read time. Do not manufacture an observation timestamp. Drop invalid or unsafe error/reason values and retry delays outside the documented bound.
- Use `unavailable` only when metadata explicitly lacks a requested format or marks it unsupported. Keep host-policy and budget gates as `not_attempted`; keep transport exceptions as `error`; keep origin-slot waits as `deferred`.
- Mark a retrieved result `partial` when the HTML byte cap truncates its body, PDF text is truncated, or fewer pages yield embedded text than the PDF's page count. This does not claim how much of the scholarly work was scientifically reviewed.
- Include attempt outcomes in deterministic report coverage and the source library/inspector, separately from the access-class counts.
- Store the outcome contract in existing JSON metadata; no relational schema migration is required.

## Alternatives considered

- **Replace `retrieval_status` with a single `error`/`partial` status:** rejected because it conflates the available abstract/metadata with the outcome of one optional full-text format.
- **Add outcome columns to `sources`:** deferred because there can be independent HTML and PDF outcomes per source, and the versioned JSON object is bounded, tested, and already persisted with the fetch provenance.
- **Treat every HTTP failure as unavailable:** rejected because current safe transport reports a sanitized error class without always retaining a reliable HTTP status, so that mapping could overstate what the host returned.

## Consequences and verification boundary

The report can now distinguish source coverage from retrieval outcomes and the browser can filter by either. Legacy saved records remain readable. Tests cover taxonomy mapping, malformed/unsafe legacy values, HTML/PDF success and partial extraction, HTML failure with an available abstract, deferred continuation, report counts, and browser inspection. Verification on 2026-10-29: backend **262 passed, 2 PostgreSQL-only skipped**; Playwright **39/39**; Vitest **13/13**; production build and touched Ruff checks passed. No live provider or scholarly host was contacted, and PostgreSQL execution remains externally blocked.
