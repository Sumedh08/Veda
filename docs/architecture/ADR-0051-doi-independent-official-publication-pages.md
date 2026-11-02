# ADR-0051: Verify rights-gated official publication pages without mandatory DOI or ROR

- **Status:** Accepted for bounded use
- **Date:** 2026-11-02
- **Related:** ADR-0050; T-140; B-017

## Context

Many institutional reports have no DOI, Crossref record, or ROR identifier. Treating a web-search hit or an organization's own homepage as proof would admit misattributed, irrelevant, or rights-unclear material. Existing Veda records already carry a verified organization identity, official domain, official-site publication lead, and report/citation provenance; the missing seam was a rights-aware route from a verified publication page to retained source text.

## Decision

Allow the existing extraction workflow to acquire a publication page without DOI/ROR only when the persisted organization identity is already verified, the exact publication URL is on its verified official domain, robots/title/canonical metadata checks match, the item page declares one recognized CC-BY 3.0/4.0 or CC0 license, and the exact content host has a current reviewed policy for that license. Use the existing SafeHTML fetcher, origin pacing, time and byte limits, document hash, source-linked passage/claim records, and report inspection. Mark the rights decision `PERMITTED_WITH_RESTRICTIONS` and preserve its evidence. Unknown, conflicting, mismatched, or unsupported rights remain metadata-only.

This verifies a publication-to-domain relationship under the existing organization identity; it does not independently create organization identity from a search result. The identity, publication relevance, research quality, methodology, and scientific truth remain separate judgments.

## Alternatives considered

- **Require Crossref DOI or ROR for every publication:** rejected because it excludes some legitimate institution-authored reports.
- **Treat an HTTP 200, search snippet, or self-declared publisher name as sufficient:** rejected because these do not establish identity, exact publication metadata, or content rights.
- **Allow any Creative Commons label or any public PDF:** rejected because version/scope ambiguity and host terms require fail-closed behavior.
- **Add publisher-specific parsers:** rejected in favor of the existing generic metadata parser and exact host-policy registry.

## Consequences and limitations

- DOI/ROR are no longer required at the extraction seam once the organization identity and publication page are independently verified.
- The route is bounded to HTML and licenses supported by the current host policy. It does not grant PDF rights or imply that the report is empirical research.
- Offline integration tests demonstrate extraction and persistence. The real browser inspected a separate previously saved GOV.UK policy roadmap; no unfamiliar specialist nonacademic publication has yet exercised this license-derived route live.
- Crawl4AI free quota could not be verified in this continuation after one balance-response reporting error and one dispatched balance timeout; no additional search was sent.

## Verification

- `backend/app/providers/official_site_search.py`: exact page metadata and item-license parsing.
- `backend/app/research/workflow.py`: fail-closed official-page evidence resolution and bounded extraction.
- `backend/tests/test_official_site_search.py` and `backend/tests/test_workflow.py`: adversarial license, identity/domain, rights, extraction, passage, and claim regressions.
- `frontend/e2e/real-api.e2e.ts`: saved official-GOV report and passage inspection.
- Full backend, frontend build/unit, changed-file Ruff, migration round-trip, and targeted browser results are recorded in `evaluation/RESULTS.md`.
