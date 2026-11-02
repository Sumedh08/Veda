# ADR-0050: Use Crossref publication links to corroborate non-ROR web publishers

- **Status:** Accepted for bounded discovery
- **Date:** 2026-11-02
- **Related:** ADR-0048; T-140

## Context

General-web discovery can find a domain with a relevant DOI-bearing publication even when ROR has no exact-domain record. Requiring ROR in every case discards those leads. Search rank, a search snippet, or a responding homepage is not enough to establish a publisher/publication relationship.

## Decision

For a search-discovered publication on a domain without an exact ROR match, Veda may continue to its bounded official-site catalog only when a Crossref DOI record has a close title match, names a publisher, and supplies an HTTPS full-text link on the observed domain or a subdomain. DOI resolution is exact when the search URL exposes a DOI; otherwise title search is capped at three records. The current title-match threshold is 0.65.

Persist this as a Crossref publisher/domain relationship, with `VERIFIED_DOMAIN_SPECIALIST` identity status and the verification source. Keep ROR and Crossref provenance distinct through the official-site adapter and report API. This decision establishes only a record-level identity/linkage signal; it does not establish organizational authority, research quality, methodology, truth, content rights, or permission to retain full text. Existing rights-gated acquisition remains mandatory.

## Alternatives considered

- **Require ROR:** rejected as the sole route because it prevents discovery of publishers absent from the ROR registry.
- **Trust the web-search domain or snippet:** rejected because search output is an unverified lead.
- **Treat Crossref publisher metadata as a quality score or rights grant:** rejected because neither follows from the metadata contract.
- **Add a bespoke registry for every publisher:** rejected in favor of reusable DOI/title/publisher/link corroboration.

## Consequences and limitations

- DOI-bearing non-ROR publishers can reach the existing bounded official-site publication catalog without a new provider framework.
- The workflow still does not verify non-DOI consultancy or think-tank publishers through this path.
- A Crossref full-text link may indicate a host relationship; it does not independently prove an organization-wide domain claim.
- The route has offline workflow and serialization tests. No live non-ROR holdout has yet exercised it, and it does not establish cross-sector publication recall.

## Verification

- `backend/app/research/workflow.py`: title, DOI, publisher, and domain-link checks.
- `backend/app/providers/official_site_search.py`: preserve the actual verification method in catalog metadata.
- `backend/app/schemas.py` and `backend/app/api/routes.py`: typed, bounded serialization.
- `backend/tests/test_workflow.py`, `backend/tests/test_official_site_search.py`, and `backend/tests/test_provider_metadata.py`.
- Crossref metadata contract note: `docs/research/crossref-non-ror-publisher-verification-2026-11-02.md`.
