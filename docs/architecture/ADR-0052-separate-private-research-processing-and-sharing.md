# ADR-0052: Separate private research processing from content sharing

- **Status:** Accepted for bounded local use
- **Date:** 2026-11-02
- **Related:** ADR-0043–0045, ADR-0051, T-140, B-017

## Context

The former full-text path required an explicit `cc0`/`cc-by` assertion and an exact reviewed host policy before it would access or retain HTML/PDF text. That is a defensible but conservative reuse gate; it also treated a missing license as a reason not to fetch or analyze a document, even though citation metadata could still be kept. Access, private analysis, limited retention, and redistribution are different decisions. A public URL or personal purpose alone does not resolve all of them.

## Decision

Keep the existing explicit-license route unchanged. Add a second, opt-in-by-jurisdiction private-research policy profile for verified official HTML publications whose item license is not stated. It is limited to records classified as `institutional_report` or `scholarly_article`; unknown types, official statistics, press releases, and software remain outside this profile. It requires a verified publisher identity and official domain, exact publication-page title/canonical metadata, public HTTPS access, robots permission or RFC 9309 robots-file 4xx unavailability, no direct document 401/403, and a bounded same-origin terms check. A detected item-specific restriction signal overrides an otherwise recognized license and the private-research profile. Inaccessible terms, uncertain identity, or an unconfigured jurisdiction leaves content metadata-only/review-required.

For the configured India private-research profile, Veda records the basis as `india_private_research_exception_candidate`; it is an operational policy decision informed by the research exception wording in section 52(1)(a)(i) of India's Copyright Act, not a legal opinion or assurance that every acquisition or use is lawful. The profile excludes commercial/public-sharing use and software, does not override item-specific restrictions or access controls, and permits only up to four exact passages and 1,200 retained verbatim characters. Sharing remains `CITATION_ONLY`. Unlicensed HTML/PDF uses the existing SSRF-safe, public-IP-pinned, bounded, paced transport and verified-domain boundary. A direct document 403 remains terminal. A robots-file 4xx is recorded separately as RFC “unavailable”; robots rules do not grant copyright permission.

Private passages remain visible inside the researcher's Veda workspace for the configured research purpose. Report and account-data exports withhold exact evidence text and source-derived report text when a cited private-only source has passages; when citation provenance is absent or incomplete and such passages exist, export fails closed. An unrelated, uncited private-only source does not suppress a report whose citations are complete and point elsewhere. Bibliographic citation metadata remains available. Licensed exports continue to follow their item license scope. No raw HTML/PDF bytes are retained. The policy is controlled by `RIGHTS_USE_MODE` and `RIGHTS_JURISDICTION`; blank jurisdiction leaves no-license material metadata-only/review-required.

## Alternatives considered

- **Keep CC-only and reviewed-host gates as the only full-text path:** safest as a product default, but unnecessarily excludes some publicly accessible research when a configured private-research exception is applicable.
- **Treat public availability or personal intent as general permission:** rejected because it conflates access, copyright, contractual conditions, analysis, retention, and redistribution.
- **Ask for manual approval on every new publisher:** rejected as an operational bottleneck; unresolved or consequential restrictions still require review.
- **Add a legal-language model or per-publisher rules:** rejected because model interpretation is not independent legal authority, and publisher-specific code would not generalize.

## Consequences and limits

- Missing license metadata no longer means access or analysis is automatically prohibited; the no-license path is bounded to a configured, narrow purpose and jurisdiction.
- It does not establish a universal fair-dealing rule, resolve publisher contract enforceability, or make content suitable for public distribution. Qualified legal review is required before representing the profile as legal advice or using it in a different product/use context.
- Site terms are checked with bounded deterministic signals, not fully interpreted. Explicit restriction signals and inaccessible terms fail closed; absence of a terms page is recorded as absence, not permission.
- The official-page screen retains only item-specific restriction codes and a copyright-notice-presence boolean, never the notice body; the scanner is not a legal interpreter.
- Source identity and publication verification remain separate from methodological quality and scientific truth.
- The change is implemented and fixture-tested; no newly discovered unlicensed real document was fetched. The saved WIDER robots-denied URL was not retried. T-140/B-017 remain open for the live nonacademic publication-to-evidence demonstration.
- No schema migration, new dependency, paid inference, Crawl4AI call, or metered content request is part of this decision.

## Verification and legal sources

- `backend/app/research/rights_policy.py`: deterministic rights matrix and limited private profile.
- `backend/app/providers/official_site_search.py`: bounded terms checks, restriction-signal hashes, item-license and official publication metadata, robots outcomes.
- `backend/app/research/safe_fetch.py` and `safe_pdf.py`: unchanged SSRF/redirect/host/size/rate safeguards plus rights-decision capability checks.
- `backend/app/research/workflow.py`: persisted rights provenance, limited passage retention, automatic continuation after an ineligible source.
- `backend/app/api/routes.py`: private workspace inspection plus citation-only report/account export behavior.
- Tests: `test_rights_policy.py`, `test_official_site_search.py`, `test_safe_fetch.py`, `test_safe_pdf.py`, `test_retrieval_workflow.py`, and `test_workflow.py`.
- [India Copyright Act, section 52](https://copyright.gov.in/Copyright_Act_1957/chapter_xi.html) — the Act includes private or personal use, including research, within specified fair-dealing purposes; this policy does not determine case-specific legality.
- [IETF RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html) — robots 4xx “unavailable” versus 5xx/network “unreachable” semantics and non-authorization caveat.
