# ADR-0054: Optional read-only MCP access to Veda evidence

- **Status:** Accepted for local protocol evaluation
- **Date:** 2026-11-02
- **Related:** T-140, T-142, T-143, B-017

## Context

Veda already owns discovery, source verification, rights decisions, acquired-document provenance, passages, and report records. External assistants may help reason over this corpus, but a second ingestion engine or unrestricted document export would duplicate state and risk disclosing text retained only for private research. The application also needs an honest boundary between evidence acquisition success and the optional reasoning client that consumes evidence.

## Decision

Keep Veda as a standalone research workflow and add an optional local stdio MCP façade over the existing authenticated, owner-scoped API. The MCP server exposes bounded source/passage search, source provenance, and passage lookup. It never fetches original documents and does not connect to the database directly. Every API origin must be a loopback IP literal; HTTP redirects and ambient proxy settings are disabled.

MCP tool responses include bibliographic identity, rights status, document version/hash, passage locator, and content hash. Passage text is included only for full-text records whose persisted item-level rights record says `PERMITTED` analysis and `LICENSE_SCOPED` retention/sharing on a verified CC-BY 4.0 or CC0 license URL with nonempty item evidence. Other records remain metadata/locator only. The established private-research exception and citation-only excerpts are not exported to external assistants. This is deliberately stricter than local Veda inspection.

The API search endpoint accepts queries in a POST body so research terms do not appear in the URL. A separate bounded source-provenance endpoint projects at most 50 passage locators without selecting passage bodies; MCP uses it for provenance and single-passage lookup, avoiding transfer of every source passage into the MCP process. Normal Veda authentication, ownership checks, request limits, and source serializers remain authoritative. MCP is an optional `mcp` dependency extra; it adds no search provider, database, vector store, background process, or acquisition route.

## Alternatives considered

- **Replace Veda synthesis with an MCP server:** rejected. A local protocol proof does not establish client adoption, retrieval quality, or a benefit to the research workflow; Veda's existing synthesis remains available.
- **Export all locally retained passages:** rejected because personal research processing does not establish permission to disclose text to a hosted assistant.
- **Direct MCP database access or a second evidence index:** rejected because the owner-scoped API already provides the required records and reduces consistency/security risk.
- **Remote MCP hosting and OAuth:** deferred. It requires public hosting and client-specific authentication; it is unnecessary to establish local protocol feasibility.
- **Client-neutral analysis skill:** not added in this change. Procedure text cannot provide corpus connectivity and would duplicate evidence guidance already in MCP instructions and Veda's source inspection UI; it can be evaluated separately if users need reusable client instructions.

## Verification and limits

The official Python MCP SDK 2.3.0 optional extra was exercised with its client against Veda's tool registry and with its stdio transport against a loopback-only test API. Tests confirm owner-scoped API behavior, locator-only provenance responses, exact passage locators/hashes, and that private-research-only or unverified-license passages are withheld. No Claude Desktop, Claude Code, or ChatGPT client was connected. ChatGPT cloud custom MCP requires a remotely reachable server and account/workspace support; a local stdio process is not directly reachable by that service. See [the MCP client fit note](../research/mcp-client-and-agent-skills-fit-2026-11-02.md).

This protocol does not improve discovery, document acquisition, extraction, evidence independence, or scientific conclusions. There is no durable MCP-specific audit table; tool logs contain counts only, while existing API request logs and owner checks apply. Public sharing remains blocked unless explicit item-level license evidence satisfies the narrow disclosure gate.
