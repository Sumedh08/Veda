# ADR-0026: Use the full retrieval deadline for isolated PDF parsing

- **Status:** Accepted, superseded in part by ADR-0049
- **Date:** 2026-10-29
- **Scope:** Credential-free PDF parser subprocess and retrieval tests

## Context

PDF fetching has an eight-second total deadline. Parsing runs in a new credential-free Python subprocess with a six-second cap, and each parser request is clipped to the remaining total deadline. On this Windows environment, a measured cold parser startup and extraction took about 5.3 seconds. The shorter independent cap intermittently rejected valid small PDFs during a full test run; the PDF test helper also imposed an unrelated four-second overall timeout.

## Decision

Initially, set the parser hard cap equal to the eight-second retrieval cap and retain the parent-side remaining-deadline calculation. ADR-0049 supersedes this eight-second PDF-specific cap after a real, licensed 2.8 MB scholarly PDF reached the parser but repeatedly exceeded the shared HTML/PDF deadline. The HTML path remains capped at eight seconds.

The parser remains isolated from provider credentials and subject to existing byte, stream, decode-work, page-tree, page-count, and text-size limits. The timeout is a wall-clock limit for the child process; it is not a formal OS CPU or memory quota.

## Consequences

- Cold Windows interpreter startup has more margin while a fetch remains capped at eight seconds overall.
- Direct parser calls remain bounded to eight seconds.
- PostgreSQL, external-host, and production container behavior are unaffected.
- Regression coverage asserts the parser cap matches the configured total and exercises malformed, encrypted, empty, oversized, and valid documents.
