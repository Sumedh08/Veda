# ADR-0046: Surface OpenAlex content availability without fetching files

- **Status:** Accepted
- **Date:** 2026-11-01
- **Context:** OpenAlex metadata can identify cached PDF and GROBID TEI representations, but downloading each file is separately metered and OpenAlex grants no additional reuse rights. Veda already distinguishes bibliographic metadata, retrieval outcomes, rights decisions, and evidence passages.

## Decision

Include OpenAlex `has_content` in bounded Works search metadata and retain only strict `pdf` and `grobid_xml` booleans. Do not request or persist provider-supplied `content_urls`, follow those URLs, or change a source's access class based on availability. Expose a separate `openalex_fulltext_availability` field through the source API and display it in the browser with an explicit notice that no file was fetched and availability is not a reuse grant.

Full-text acquisition remains a separate operation. A provider transport method now exists behind an explicit default-off metered-download flag and requires an internal `PERMITTED` rights authorization plus a USD 0.01 minimum reservation. It constructs the fixed `content.openalex.org` TEI URL from a validated Work ID, rejects redirects and unexpected media types, enforces a 2 MB response bound, makes no retries, computes a content hash, and preserves unknown reported cost when a request was sent. The method is not called by the research workflow yet; orchestration must still bind its authorization to persisted source/version/license evidence and the job's retrieval-cost ledger before any production dispatch.

## Rationale

This makes potentially useful archived TEI discoverable without conflating metadata, access, rights, or evidence. It avoids persisting untrusted download URLs and prevents a metadata-only source from being represented as full-text evidence. The implementation stays within the existing OpenAlex adapter, versioned metadata model, source serializer, and source inspector; no new table or migration is required.

## Consequences

- Existing OpenAlex records remain readable; missing availability values mean unknown and are not inferred as false.
- New availability values do not assert legal permission, quality of the archived parse, or retrieval completion.
- No OpenAlex content file was fetched while implementing this ADR. OpenAlex's current public documentation lists content downloads at $0.01/file and preserves original copyright; see [the recorded source review](../research/openalex-fulltext-content-api-2026-11-01.md).
- The user-facing source record can indicate where future acquisition may be possible, while full-text retrieval remains outstanding.
- T-136 demonstrates the existing Europe PMC JATS path end to end on a DOI/PMCID-matched CC-BY article, with real section passages persisted, cited, and inspected in the browser. The report is deterministic and limited, not AI research success. OpenAlex content transport remains fixture-tested only; it is not workflow-integrated or live-validated, and no OpenAlex file was downloaded.
