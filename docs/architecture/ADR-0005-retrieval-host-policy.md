# ADR-0005: Deny full-text retrieval without a reviewed host policy

**Date:** 2026-10-29  
**Status:** Accepted

## Context

OpenAlex identifies OA locations and reports a license identifier, but its documentation says hosted article PDFs retain the rightsholder's copyright and that OpenAlex grants no additional rights. The repository's HTML and PDF fetchers previously accepted any discovered host after only an `is_oa` and license-field check. The source route therefore needed a host-specific terms decision in addition to document-license metadata and transport controls.

IETF RFC 9309 specifies crawler rules and how to parse them. It expressly says those rules are not access authorization. A permitted robots path cannot grant a copyright license or override a host's terms. Conversely, a document license assertion does not override a crawler disallow rule.

## Decision

Every HTML/PDF source request requires three independent gates:

1. **Document rights evidence:** OpenAlex's selected `best_oa_location` must be marked OA and report an accepted license identifier. Veda accepts only `cc0` and `cc-by`. It records the value as an OpenAlex metadata assertion, not an independently verified license. The `public-domain` alias is excluded because the alias itself does not identify whether the work is under a CC0 dedication or a public-domain mark.
2. **Reviewed host policy:** the exact hostname must exist in `backend/app/research/retrieval-host-policies.json`, with a recent terms review, policy ID, HTTPS terms URL, explicit allowed-license list, and a numeric `minimum_interval_seconds` (0–86400). Hostnames do not use wildcards or implicit parent-domain matches. Every source redirect repeats this check. Unknown, invalid, stale, or license-out-of-scope host entries deny retrieval before connecting.
3. **Crawler and transport policy:** fetch and parse the origin's robots rules for the requested path, then apply existing DNS-pinned SSRF, redirect, HTTPS downgrade, media, size, and timeout checks. `robots.txt` has a 512 KiB cap, at most five redirects, and an in-process cache capped at 24 hours. Parseable `VedaResearch`/`*` group rules apply with longest-match and Allow-on-tie behavior. A source redirect destination is checked under that destination host's own entry and robots policy. Every outbound robots/document request reserves a shared database slot for its exact scheme/host/port origin. The effective interval for HTML/PDF is the greater of the reviewed host interval and the selected robots group's `Crawl-delay`; each hop's destination policy is checked independently. Reservations use an atomic SQLite or PostgreSQL upsert and database clock. If storage is unavailable or the next slot does not fit the retrieval deadline, no HTTP request is sent; retrieval records a sanitized failure or retryable defer. A 100 ms admission margin accounts for the database-to-socket handoff.

Veda deliberately denies retrieval for every non-200, malformed, oversized, or unreachable robots file. RFC 9309 says 4xx makes robots unavailable and permits a crawler to access content; it does not require access, so Veda chooses the stricter fail-closed policy while site permission remains unknown. A robots allow only clears the crawler-path gate.

The checked-in host registry is empty. This is intentional: no particular external full-text host received a terms review during this task. The application remains useful for metadata and abstract research; adding a host is a follow-up that requires a cited, exact host review and local verification. The cross-worker scheduler has local SQLite concurrency/restart tests and both dialect statements compile, but PostgreSQL execution, hosted multi-worker behavior, and live host retrieval remain unverified. No live full text is fetched until an entry exists.

## Consequences

- Existing fixture-level retrieval tests inject a reviewed host policy and exercise real robots/transport behavior. The default runtime path denies every unreviewed host without DNS or document requests.
- Retrieval metadata stores the provider-license evidence, host policy ID/terms URL, robots outcome, and separate safe denial code. The source inspector presents these fields without calling the provider assertion a legal determination.
- Registry authors must record `minimum_interval_seconds` explicitly, including `0` when no additional host interval is required. Positive intervals and robots delays are never silently ignored; a deadline deferral records `retry_after_seconds` where known. The extraction stage distinguishes a deferred request from a retrieval failure, but does not automatically reschedule that request.
- Research using current configuration will use abstract/metadata evidence and show the full-text gate failure. This is an explicit capability boundary, not a claim of source coverage.
- A new exact host entry needs a primary-source terms review, license-scope decision, robots check, and updated tests. OpenAlex's metadata and RFC robots rules alone are insufficient evidence.
- Live host behavior, license corroboration, production proxy behavior, and research-quality effects remain unverified.
- PostgreSQL's upsert expression has compile-time coverage only until T-09 can execute against a disposable PostgreSQL service; keep all currently screened hosts disabled.

## Evidence

- [OpenAlex Open Access fields](https://help.openalex.org/data/works/open-access/) and [license vocabulary](https://help.openalex.org/data/licenses/) describe per-location license identifiers and unknown/publisher-specific categories.
- [OpenAlex full-text documentation](https://help.openalex.org/access/fulltext/) says cached full-text PDFs retain original copyright and OpenAlex grants no additional rights.
- [IETF RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html), Sections 2.2–2.5 and 3, specifies robots matching, status handling, redirects, caching, parsing limits, and that robots is not access authorization.
- [Creative Commons CC0 and public-domain tools](https://creativecommons.org/public-domain/) distinguish the CC0 dedication from descriptive public-domain labeling.
- The scoped repository/code findings and dates are in [`retrieval-rights-screen-2026-10-29.md`](../research/retrieval-rights-screen-2026-10-29.md); implementation details and limitations are in [`retrieval-safety-decision.md`](../research/retrieval-safety-decision.md).
