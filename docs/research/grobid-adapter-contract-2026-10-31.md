# GROBID PDF-to-TEI adapter contract

**Checked:** 2026-10-31 against official GROBID documentation and the `grobidOrg/grobid` repository. No GROBID service was contacted.

## REST contract

For full-document parsing, call `POST` (the docs also list `PUT`) at `{service-root}/api/processFulltextDocument`. Send a multipart form (`multipart/form-data`) with required file field `input` containing the PDF. The normal response is `application/xml` TEI for the header, body, and bibliography. Request `Accept: application/xml`; avoid `debugMode`, which changes the response into raw `text/plain` model-label output. The fulltext endpoint supports optional controls including `consolidateHeader`, `consolidateCitations`, `includeRawCitations`, `includeRawAffiliations`, `includeRawCopyrights`, repeated `teiCoordinates`, `segmentSentences`, `generateIDs`, `start`, `end`, and `flavor`. For a provenance-first Veda adapter, disable metadata consolidation unless explicitly needed: the documented consolidation options can call Crossref or biblio-glutton and alter/inject metadata, which would add network behavior and blur parser versus metadata provenance. [REST API: fulltext endpoint and parameters](https://grobid.readthedocs.io/en/latest/Grobid-service/)

Documented outcomes for this endpoint are:

| HTTP | Meaning |
| --- | --- |
| `200` | Successful operation; validate the body as TEI before accepting it. |
| `204` | Processing completed but no content could be extracted/structured. |
| `400` | Invalid request, missing parameter, or missing header. |
| `500` | Internal/processing error. Documented error codes include `BAD_INPUT_DATA`, `NO_BLOCKS` (often scanned/image-only PDF), `TOO_MANY_BLOCKS`, `TOO_MANY_TOKENS`, `TIMEOUT`, `TAGGING_ERROR`, `PARSING_ERROR`, `GENERAL`, and `PDFALTO_CONVERSION_FAILURE`. |
| `503` | Service unavailable, commonly all processing threads are occupied. The docs suggest waiting 5–10 seconds before resending `processFulltextDocument`; they do not define a universal retry policy. |

The docs do not promise a stable machine-readable error-body schema, an HTTP transport timeout duration, or general request idempotency. Veda should therefore apply its own connect/read deadlines, response-size limit, XML hardening, and sanitized status/error classification. A timeout after dispatch should be treated as an unknown processing outcome; any retry policy should be explicitly bounded. Do not classify the documented internal `TIMEOUT` 500 as a client transport timeout. [REST errors](https://grobid.readthedocs.io/en/latest/Grobid-service/)

## Health and version

The service documentation identifies:

- `GET /api/version`: running version and revision (`git describe` form when available).
- `GET /api/isalive`: plain-text `true`/`false`; HTTP 200 when initialized, 503 when not.
- `GET /api/health`: JSON readiness/status, including initialization and engine-pool metrics; HTTP 200 ready, 503 otherwise.

The default service port is 8070. Docker examples can expose the admin/metrics port separately (8071). Do not treat a TCP-open port alone as readiness. [Service checks and configuration](https://grobid.readthedocs.io/en/latest/Grobid-service/) · [Docker deployment](https://grobid.readthedocs.io/en/latest/Grobid-docker/)

## Release and runtime implications

As of this check, the official repository marks **0.9.1** as the latest stable release and the latest release; its Docker documentation gives `0.9.1-crf` and `0.9.1-full` image examples. A deployment should pin a release/image digest and record `/api/version` output instead of assuming a floating tag. [Latest stable release](https://grobid.readthedocs.io/en/latest/Install-Grobid/) · [GitHub releases](https://github.com/grobidOrg/grobid/releases) · [Docker images and requirements](https://grobid.readthedocs.io/en/latest/Grobid-docker/)

The official Docker guide distinguishes a CRF-only image (about 500 MB) from the full image (about 8 GB); the full image includes Python/TensorFlow/PyTorch and deep-learning resources and may use more memory and run more slowly without a GPU. The guide recommends about 4 GB RAM to structure full PDFs, 2 GB for header-only extraction, 3 GB for citations, and 6–8 GB for intensive parallel processing. The full image is documented for amd64 CPU hosts; GPU use in Docker is documented for Linux, not Windows/macOS. CRF-only ARM64 support is described as available, with Linux ARM64 status less established than the tested macOS case. Building from source requires OpenJDK 21 or later. Therefore an optional service adapter is appropriate: keep it disabled by default, use an independently managed local/container service, and let abstract/XML workflows continue if unavailable. [Docker runtime guide](https://grobid.readthedocs.io/en/latest/Grobid-docker/) · [Build requirements](https://grobid.readthedocs.io/en/latest/Install-Grobid/)

The service recommends web-service mode on a multicore host for production/benchmarking rather than batch mode. Models preload by default; lazy model loading saves memory if only some models are used but makes the first applicable request significantly slower. [Service operation](https://grobid.readthedocs.io/en/latest/Grobid-service/)

## License and boundaries

The official project states that GROBID software is under **Apache License 2.0**, its documentation is **CC0**, and annotated data is **CC-BY**. The repository's first-party `LICENSE` is Apache-2.0. This supports evaluating GROBID itself as an optional parser dependency/service, subject to normal Apache notices and third-party dependency review. It does **not** grant rights to download, retain, quote, or redistribute PDFs processed by GROBID; source-document acquisition, retention, and display rights must be decided separately per Veda's access policy. [Official license page](https://grobid.readthedocs.io/en/latest/License/) · [Repository LICENSE](https://github.com/grobidOrg/grobid/blob/master/LICENSE)

The REST guide says CORS allows any origin by default and can be restricted in configuration. CORS is not authentication. For a local-only adapter, keep the service bound to loopback/private networking and do not expose its unauthenticated parsing endpoint publicly; configure origins narrowly if browser access is ever enabled. [CORS configuration](https://grobid.readthedocs.io/en/latest/Grobid-service/)

## Adapter implications for Veda

1. Keep PDF-to-TEI behind an optional adapter with a configurable base URL and an explicit service-version field in parser provenance.
2. Send a bounded PDF as multipart field `input`; request XML; validate status, content type, well-formed TEI, and resource limits before extracting sections/passages.
3. Map 204, 400, 500-specific GROBID error codes, 503 saturation, transport timeout, invalid XML, and oversized output into distinct extraction outcomes. Preserve previously retrieved metadata/evidence on parser failure.
4. Disable GROBID metadata consolidation by default so source metadata remains attributable to Crossref/OpenAlex and parser output remains attributable to the PDF. If enabled later, persist that consolidation as a separate external lookup event.
5. Do not equate successful parsing with legal access, complete extraction, or scientific correctness. Keep original PDF hash, document version, rights decision, parser version, and extraction warnings in Veda's provenance model.
6. No GROBID service, PDF fixture, or actual Veda adapter was exercised for this note; runtime availability and Veda integration remain unverified.

## Unknowns and verification limits

- No live service was queried, so actual deployed version, readiness, latency, thread capacity, and service configuration are unknown.
- Official REST documentation does not specify a standard client transport-timeout value or a stable structured error response body.
- The documentation's `503` wait guidance is a suggestion, not a guarantee that retry will succeed; Veda must retain bounded retry/cooldown behavior.
- License status of a particular input PDF is outside GROBID's software license and remains source-specific.
- This review did not audit every transitive dependency or Docker image layer license; perform a pinned-image/dependency review before distribution.
- Parser output quality for Veda's target document set, including section classification and table fidelity, has not been measured here.
