# UN Digital Library discovery API screen — 2026-11-01

## Decision

**Conditionally suitable; product-use terms are a blocker until clarified.** The UN Digital Library (UNDL) is a high-value official catalog for UN documents and publications, including flagship publications, with a documented GET search interface and MARCXML metadata output. Its current Data Terms of Use permit Library-created content, data, and metadata only for non-commercial use with attribution. Veda must not enable this source in a commercial product unless the UN grants written permission for the intended use. Ask the Library to confirm that bounded, automated calls to the documented metadata API are permitted; its terms separately prohibit web scraping and automated downloads of “content” without approval. Do not fetch linked PDFs or other files.

This is documentation review only. No live API request, file download, paid call, or permission inquiry was made.

## Catalog and search contract

- The catalog includes UN documents, voting data, speeches, maps, flagship publications, digital materials, and bibliographic records for print UN documents from 1979. Results may be citation-only or link to a digital file. [UNDL overview and scope](https://research.un.org/en/digitallibrary)
- Official API documentation specifies `GET https://digitallibrary.un.org/search?p={query}&of=xm&jrec=1&rg=10`. Here `p` is the search pattern, `of=xm` requests MARCXML, `jrec` is the first result position, and `rg` is the page size. The `c` parameter can constrain results to the `Documents and Publications` collection. For one record, the documented route is `GET https://digitallibrary.un.org/record/{recid}?of=xm`. [Search Engine API](https://digitallibrary.un.org/help/search-engine-api?ln=en), [Record API](https://digitallibrary.un.org/help/record-api), [UNDL embedded search instructions](https://research.un.org/en/digitallibrary)
- The API docs show numeric record ID in MARC control field `001` and in `/record/{recid}`; preserve it as the provider record key. Preserve document symbol/call number separately when supplied. The example MARCXML also shows author in tag `100` and title in tag `245`. [Search Engine API](https://digitallibrary.un.org/help/search-engine-api?ln=en), [Record API](https://digitallibrary.un.org/help/record-api), [UNDL metadata overview](https://research.un.org/en/digitallibrary)
- The current UNDL search guide describes unformatted keyword search as requiring all query words somewhere in the record metadata; quoted terms do partial-phrase matching, brackets request exact phrase matching, and field searches such as `author:Einstein` are supported. The library guide says metadata search is in English; full-text search is a separate option and can cover documents in the six official languages. Use the `Documents and Publications` collection filter, and do not silently turn a metadata search into full-text retrieval. [UNDL search guide](https://digitallibrary.un.org/docs/search-guide/), [UNDL overview](https://research.un.org/en/digitallibrary)
- The API docs warn that `rg` has a server-wide maximum but publish no numeric value. They document offset pagination with `jrec`; they do not state an API rate quota, response-size cap, or service-level availability target. The published examples use GET parameters and do not specify API credentials. Treat authentication behavior and quotas as undocumented; use small bounded pages and conservative request pacing, and handle 403/429 responses without retries that amplify load. [Search Engine API](https://digitallibrary.un.org/help/search-engine-api?ln=en)

## Reuse and access terms

The current Dag Hammarskjöld Library terms say Library-created content, data, and metadata may be accessed and used free of charge **for non-commercial use** with the stated UN acknowledgement. The terms explicitly say web scraping and/or automated downloads of content require Library approval and direct reuse questions to `permissions@un.org`. They provide no commercial-use grant and no separate express commercial license for bibliographic metadata. Therefore public availability and an API endpoint do not establish commercial Veda rights. Obtain written permission covering the product’s use, metadata retention/display, and automated API access before enabling it commercially. [Dag Hammarskjöld Library Data Terms of Use](https://digitallibrary.un.org/pages/?ln=en&page=tos)

The Library terms also disclaim warranties and make the user responsible for reuse. Linked UN documents may have distinct rights; neither a catalog record nor the Library metadata terms authorize downloading or redistributing the linked publication. Keep this adapter metadata-only and link users to the UNDL record. [Data Terms of Use](https://digitallibrary.un.org/pages/?ln=en&page=tos), [UN copyright notice](https://www.un.org/en/about-us/copyright/)

## Windows/Python implementation notes

Veda’s backend requires Python 3.12+ and already depends on `httpx`. A Windows-compatible adapter can use the existing async HTTP client with explicit connect/read timeouts, redirects disabled unless specifically validated, and response-byte/page caps. Encode query parameters with an HTTP library rather than string-concatenating user text. Prefer the documented `of=xm` format over `of=recjson`: the API docs say XML returns MARC metadata and warn that JSON can be unusably slow when its server cache is cold. Parse the MARC21 slim namespace and validate expected fields; retain provider ID, record URL, retrieval time, and the terms/access status with each result. [Veda backend dependencies](../../backend/pyproject.toml), [Search Engine API](https://digitallibrary.un.org/help/search-engine-api?ln=en), [Record API](https://digitallibrary.un.org/help/record-api)

The UNDL API pages are official but use legacy Invenio API documentation and could not be fetched directly during this review (HTTP 403 through the research browser); indexed first-party page contents were available. Documentation establishes the request shape, but current endpoint behavior still requires a one-request live adapter smoke after product-use permission is resolved.

## Adapter acceptance tests

Before enabling the adapter, require tests that:

1. Build a URL-encoded GET to the fixed UNDL `/search` endpoint with a bounded query, `c=Documents and Publications`, `of=xm`, `jrec`, and conservative `rg`; never follow record file links.
2. Verify pagination is offset-based, obeys the configured aggregate result cap, and stops on an empty page; reject an unexpectedly excessive or malformed response.
3. Parse MARCXML namespace-aware, map numeric `001`, title `245`, and author `100`, preserve document symbols/call numbers when present, and reject records without a usable record ID or title.
4. Treat timeout, malformed XML, 403, 429, and 5xx as provider failures with no unbounded retries; do not report a failed request as zero results.
5. Enforce a permission/configuration gate for commercial use and metadata display/retention; keep full-text/file retrieval disabled regardless of catalog result availability.

Sources establish the documented interface, not that current production responses pass these tests. No adapter or test was implemented or run for this screen.
