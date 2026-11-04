# MCP client fit and Agent Skills distinction

**Checked:** 2026-11-03
**Scope:** Official MCP, Anthropic, OpenAI, and Agent Skills documentation, followed by an optional local SDK protocol experiment. No provider account, hosted model, paid API, or external MCP client was used.

## Findings

### Protocol and transport

The current MCP specification version reviewed is dated `2026-07-28`. Its standard local transport is `stdio`: newline-delimited messages over standard streams of a client-launched subprocess. Its deployable HTTP transport is Streamable HTTP, using one MCP endpoint and POST requests with JSON or request-scoped SSE responses. The protocol semantics are shared across transports. [MCP transport specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)

MCP authorization is optional. For HTTP transports, implementations that support authorization should follow the MCP OAuth-based authorization specification; for stdio, the specification says not to use that HTTP OAuth flow and to obtain credentials from the process environment. This makes a single-user local prototype materially simpler than a remote multi-user service, but does not replace Veda's owner isolation or data-disclosure rules. [MCP authorization specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)

The MCP security guidance explicitly covers local server command execution, SSRF, token passthrough, and confused-deputy risks. A read-only Veda server should expose only bounded, owner-scoped evidence queries, avoid arbitrary URL fetch tools, validate all identifiers, and never forward user/client credentials to other services. [MCP security best practices](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices)

### Python SDK and Veda compatibility

The official Python SDK repository lists **v2.3.0** as its latest release at the time checked. The SDK is MIT licensed, supports Python 3.11+, and implements stdio, Streamable HTTP, and SSE. Its current v2 dependency metadata includes `httpx2>=2.10.0` and `mcp-types`; the v2 line is a major rewrite from v1. [SDK releases](https://github.com/modelcontextprotocol/python-sdk/releases), [SDK README](https://github.com/modelcontextprotocol/python-sdk), [SDK project metadata](https://github.com/modelcontextprotocol/python-sdk/blob/main/pyproject.toml)

Veda's backend declares Python `>=3.12`, so the SDK's Python floor is compatible. The experiment installs `mcp==2.3.0` only as the optional backend `mcp` extra; it does not change the base application dependencies. Its separate `httpx2` stack remains optional.

### Client support and deployment implications

| Client | Supported connection relevant to Veda | Practical consequence |
|---|---|---|
| Claude Code | Native local stdio MCP process configuration; also remote HTTP. | A local read-only Veda process can be tested without hosting it. [Claude Code MCP docs](https://code.claude.com/docs/en/mcp) |
| Claude Desktop | Local MCP servers through desktop extensions (`.mcpb` packages); remote MCP connectors are configured separately in Settings. | Local access is feasible, but the supported current desktop packaging path is an extension, not an assumption that arbitrary Claude Code JSON configuration is shared. [Local MCP on Claude Desktop](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop), [remote MCP connectors](https://support.anthropic.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers) |
| ChatGPT | Custom MCP servers connect to a public HTTPS endpoint, or a supported Secure MCP Tunnel. Local/private servers are not directly reachable by ChatGPT. Availability depends on the account/workspace; current full MCP support is documented for Business and Enterprise/Edu web, while Pro is limited to read/fetch custom-server use. | A protocol-only local test does not establish ChatGPT integration. Veda would need a separately operated remote endpoint or supported tunnel and a compatible account. [ChatGPT custom MCP connections](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt) |

Claude Desktop's local extension support and Claude Code's stdio support make them the lowest-infrastructure client targets for a local proof of concept. ChatGPT integration has additional endpoint/tunnel and account prerequisites. An MCP protocol pass with a local client therefore must not be reported as ChatGPT compatibility.

### Agent Skills are not a data connection

Agent Skills define portable instruction packages centered on a `SKILL.md`, with optional scripts, references, and assets. A skill can teach an assistant how to search evidence, inspect locators, distinguish findings from metadata, and report uncertainty; it does not itself connect an assistant to Veda's database or expose tools. [Agent Skills specification](https://agentskills.io/specification)

The MCP Skills extension is a separate optional protocol extension that lets an MCP server expose skill files through resources and requires additional methods such as `skills/list` and `skills/get`. A client must implement that extension; do not assume generic MCP clients automatically load Agent Skills. [MCP Skills extension](https://skills.extensions.modelcontextprotocol.io/)

## Veda-specific assessment

MCP is a plausible **read-only evidence interface**, not an acquisition architecture replacement. It can let compatible assistants reuse Veda's existing persisted sources and passages instead of duplicating ingestion. It cannot improve document discovery or extraction by itself.

The smallest defensible prototype would be a local `stdio` server for Claude Code or Claude Desktop that calls existing Veda read paths and returns bounded source metadata, citation locators, coverage, and only text allowed by a distinct external-disclosure policy. Veda's private-research permission must not be treated as permission to transmit retained passages to a hosted model. Until Veda can distinguish external disclosure from local analysis and sharing/redistribution, expose metadata and citation identifiers only; keep protected passage text unavailable. Do not add a raw-document fetch operation.

For ChatGPT, a separate remote deployment/tunnel decision and authenticated owner-scoped access are prerequisites. The published docs establish technical connection routes, not that this user's ChatGPT plan/workspace has them enabled or that Veda is safe to expose remotely.

**Experiment result (2026-11-02):** Veda now has a local read-only stdio server over the existing owner-scoped API. The official Python SDK client completed in-memory tool listing/calls and a separate stdio subprocess handshake/tool call against a loopback-only fake API. A CC-BY fixture returned its exact bounded passage, locator and hashes; private-research-only and unverified-license text was withheld. This is MCP protocol/transport evidence only: no Claude Desktop, Claude Code, or ChatGPT client was connected, and the fixture does not establish live source acquisition or scientific benefit. No durable MCP-specific audit table was added; request logs contain no query or passage text.

**Decision:** Keep Veda hybrid and standalone: the optional MCP interface can make already acquired and expressly shareable evidence reusable by compatible clients, but it does not improve discovery, acquisition, extraction, sufficiency, or source quality. Local stdio is a practical path for local MCP clients; ChatGPT's documented custom-server connection requires a public HTTPS endpoint or supported tunnel and suitable workspace permissions. Do not build remote hosting/OAuth until a concrete deployment and privacy model is authorized. Agent Skills remain optional user guidance, not connectivity. The client-neutral research procedure now lives at [the Veda evidence research skill](../../skills/veda-evidence-research/SKILL.md); the GitHub install command is in the README, and the skill has not been installed into the user's global Codex environment. It uses only tools actually exposed by the local server.

## Primary sources

- [MCP transports, version 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)
- [MCP authorization, version 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- [MCP security best practices, version 2026-07-28](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices)
- [Official MCP Python SDK releases](https://github.com/modelcontextprotocol/python-sdk/releases)
- [Official MCP Python SDK source and license](https://github.com/modelcontextprotocol/python-sdk)
- [Official MCP Python SDK package metadata](https://github.com/modelcontextprotocol/python-sdk/blob/main/pyproject.toml)
- [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp)
- [Anthropic: local MCP servers on Claude Desktop](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)
- [Anthropic: remote MCP connectors](https://support.anthropic.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers)
- [OpenAI: connecting custom MCP servers in ChatGPT](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)
- [Agent Skills specification](https://agentskills.io/specification)
- [MCP Skills extension](https://skills.extensions.modelcontextprotocol.io/)
