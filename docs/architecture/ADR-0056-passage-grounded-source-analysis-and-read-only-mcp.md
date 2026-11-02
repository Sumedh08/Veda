# ADR-0056: Passage-grounded document analysis and read-only research MCP

**Status:** Accepted for implementation; live model and external-client behavior remain unverified.
**Date:** 2026-11-03

## Context

Veda already persists bounded document passages, structured source/claim appraisal, cross-source relationships, adaptive evidence coverage, citation audits, saved reports, and a local read-only MCP server. It lacked a compact per-source reading that external users and the report synthesis could navigate, while MCP did not expose saved analyses, report/coverage status, document structure, or job accounting. These gaps did not explain or fix the separate live nonacademic full-text acquisition failure.

## Decision

- Extend the existing appraisal response with an optional, typed per-source analysis of stored passages: question fit, study focus, passage-linked findings/limitations/cannot-conclude points, and separately labeled further-information gaps.
- Persist the extension in the existing appraisal JSON field; do not add a parallel appraisal table or migration. Reject analysis whose passage IDs do not belong to that same source.
- Pass only bounded saved subquestions and passages to the existing appraisal call. The analysis is a provisional navigation aid. Synthesis may use it to find evidence but report findings remain validated against supplied stored claims and exact passages.
- Reuse the existing comparison, sufficiency, report and citation machinery. Comparison now round-robins claim samples across passage-bearing sources and reports `not_assessed` when fewer than two sources qualify. Investigation independence remains unknown unless separately reviewed.
- Extend the optional MCP server with bounded, read-only job-status, document-structure, document-analysis, comparison, coverage, and saved-report tools backed by existing owner-scoped API routes. Do not expose job creation/advancement, arbitrary URL fetching, raw document bodies, or direct database access.
- Apply the explicit item-level external-sharing gate to passages, derived analysis, section-heading text, comparisons, and report prose. Derived-text tools additionally require exact source passage locators and matching passage/document hashes. Private-research processing alone is not external disclosure permission.
- Keep candidate relevance opt-in and single-call, capped at 12 deduplicated metadata records, and include bounded planned subquestions. Abstracts, author names and URLs remain out of the model payload absent a separate processing/disclosure basis. Deterministic selection remains the fallback.

## Alternatives considered

- **A new multi-agent/coordinator framework:** rejected. It would duplicate Veda's resumable state machine, cost reservations, appraisal, comparison, and citation audit, while increasing calls and failure states.
- **MCP-first research acquisition:** rejected. The local MCP server is an evidence interface; it is not a discovery/acquisition engine. Research-job mutation would need its own explicit authorization and cost controls.
- **Separate model calls per document:** deferred. Reusing the already reserved appraisal call avoids multiplying inference and preserves per-source failure behavior. A separate call is not justified without output-quality and cost measurements.
- **Include abstracts in relevance review:** rejected for now. Abstract availability does not grant permission to disclose publisher-controlled text to the model provider. This leaves the current title/publisher/year/source-type input less informative and its semantic accuracy unmeasured.

## Consequences and limits

No runtime dependency or database migration was added. Existing API ownership and database records remain authoritative. Source-analysis output is model-assisted, not independently validated; external text is withheld unless item-level sharing evidence passes. The 12-candidate relevance cap is a fixed one-call input/output and resource bound, not a user-controlled preference; candidates outside the deterministic sample can remain unseen by the model. No automatic discovery follow-up is initiated when comparison identifies a gap. No model call, live search/acquisition, or external MCP client was used for this implementation. The T-140 nonacademic source-to-passage acceptance remains open.
