# ADR-0051: Verify rights-gated official publication pages without mandatory DOI or ROR

- **Status:** Accepted for bounded use
- **Date:** 2026-11-02
- **Related:** ADR-0050, ADR-0052; T-140; B-017

## Context

Many institutional reports have no DOI, Crossref record, or ROR identifier. Treating a web-search hit or an organization's own homepage as proof would admit misattributed, irrelevant, or rights-unclear material. Existing Veda records carry a verified organization identity, official domain, official-site publication lead, and report/citation provenance. The earlier extraction route also did not dispatch selected WordPress-catalog report records through page verification, so they stayed metadata-only even when the normal rights-aware HTML path could have considered them.

## Decision

Route a selected official-site WordPress catalog record into the existing extraction workflow only when its persisted organization identity and official domain are verified. Independently verify the publication page using the bounded official-page verifier; require exact title/canonical identity, a valid robots outcome, and completed bounded terms/license inspection. A successful page verification is not itself a content-use permission. Pass the item-specific license, terms, restriction, content host, and configured use profile into the existing rights evaluator. That evaluator may permit a supported explicit license or, only in an explicitly configured private-research profile and jurisdiction, a limited private-processing decision under ADR-0052. Unknown, conflicting, restricted, unverified, or unsupported outcomes stay metadata-only. Never fetch report body content before this decision. For limited private-processing decisions, preserve the existing four-passage/1,200-character retention cap and citation-only sharing rule. Reuse the existing SafeHTML fetcher, origin pacing, time and byte limits, document hash, source-linked passage/claim records, and report inspection.

This verifies a publication-to-domain relationship under the existing organization identity; it does not independently create organization identity from a search result. The identity, publication relevance, research quality, methodology, and scientific truth remain separate judgments.

## Alternatives considered

- **Require Crossref DOI or ROR for every publication:** rejected because it excludes some legitimate institution-authored reports.
- **Treat an HTTP 200, search snippet, or self-declared publisher name as sufficient:** rejected because these do not establish identity, exact publication metadata, or content rights.
- **Allow any Creative Commons label or any public PDF:** rejected because version/scope ambiguity and host terms require fail-closed behavior.
- **Add publisher-specific parsers:** rejected in favor of the existing generic metadata parser and exact host-policy registry.

## Consequences and limitations

- DOI/ROR are not required at the extraction seam once the organization identity and publication page are independently verified.
- Page verification remains distinct from access, analysis, retention, and sharing decisions. The private-research profile is a configurable operational policy, not a legal conclusion or universal authorization. This route does not grant rights to PDFs or imply that the report is empirical research.
- Offline integration tests demonstrate a DOI-less institutional report passing through verification, the existing private-processing policy, safe HTML extraction, bounded passage/claim persistence, and report citation mapping; access denial remains metadata-only. A real saved ORE Catapult report replay reached page-verification but stopped because its CMS `robots.txt` endpoint redirected to HTML (`unexpected_content_type`). No publication body was fetched, no rights result was inferred, and no source-linked passages were produced in that live replay. The unfamiliar nonacademic source-to-passage/browser acceptance therefore remains open.
- Crawl4AI free quota could not be verified in this continuation after one balance-response reporting error and one dispatched balance timeout; no additional search was sent.

## Verification

- `backend/app/providers/official_site_search.py`: exact page metadata and item-license parsing.
- `backend/app/research/workflow.py`: selected catalog-page verification dispatch, fail-closed official-page evidence resolution, and bounded extraction.
- `backend/tests/test_official_site_search.py` and `backend/tests/test_workflow.py`: adversarial license, identity/domain, rights, extraction, passage, claim, request-accounting, and access-denial regressions.
- `frontend/e2e/real-api.e2e.ts`: saved official-GOV report and passage inspection.
- Full backend, frontend build/unit, changed-file Ruff, migration round-trip, and targeted browser results are recorded in `evaluation/RESULTS.md`.
