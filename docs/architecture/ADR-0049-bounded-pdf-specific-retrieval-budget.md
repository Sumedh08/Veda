# ADR-0049: Use a bounded PDF-specific retrieval deadline

- **Status:** Accepted
- **Date:** 2026-11-01
- **Supersedes:** The eight-second PDF total cap in ADR-0026; HTML retrieval remains unchanged.

## Context

The model-disabled live workflow found an exact ORE Catapult-affiliated paper, verified the OpenAIRE repository instance against the DOI, exact title, CC-BY license and reviewed Strathprints host policy, then rejected the 2,795,705-byte PDF as too large. A first correction aligned the PDF byte default with its declared 8 MB limit. The next end-to-end attempt reached PDF parsing but returned `pdf_parser_timeout` under the shared eight-second HTML/PDF deadline.

The live failure exposed two defects, not a rights restriction: the PDF fetcher inherited the HTML 2 MB default, and its parser had no time budget beyond the HTML transport cap. The standard research step has a bounded 120-second ceiling; the fetcher must also respect the remaining per-step time.

## Decision

1. Keep HTML retrieval's existing eight-second maximum.
2. Give PDF transport, robots checks and parsing a separate **45-second maximum per document**.
3. Cap the isolated PDF parser subprocess at **30 seconds**. The fetcher passes the lesser of this parser cap and the remaining PDF/job-step deadline.
4. Preserve the workflow's persisted step deadline: a smaller remaining step budget always lowers the PDF deadline. Keep byte (8 MB), page, stream, decode-work and text limits unchanged.
5. Preserve safe fetching: pinned public IPs, exact host policy, item-level permitted license, robots checks, redirect revalidation, per-origin pacing, no content retention beyond the existing evidence snapshot, and sanitized failure codes. Do not add retries.

These ceilings allow bounded extraction work for a permitted scholarly PDF while keeping resource use finite and below the standard job-step maximum. If parsing still exceeds 30 seconds, Veda records a parser timeout and retains previously collected metadata/evidence.

## Verification

- A regression proved the old resolver contract produced the live `dns_failure`; the corrected system resolver passes `AF_UNSPEC` and `SOCK_STREAM` in their proper `getaddrinfo` positions.
- A 2.1 MB PDF fixture proved the default PDF byte cap is distinct from the 2 MB HTML default while remaining below the existing 8 MB PDF maximum.
- A deadline regression asserts the 45-second cap, 30-second parser cap, preservation of a smaller caller/job-step budget, and clamping of larger requested timeouts.
- Live browser validation after these fixes is recorded in `evaluation/RESULTS.md`; page-level PDF extraction is not described as Methods/Results section extraction unless GROBID actually produced structured sections.
