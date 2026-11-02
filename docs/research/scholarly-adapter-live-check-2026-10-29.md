# OpenAlex and Crossref adapter live check

- **Checked:** 2026-10-29
- **Scope:** one read-only metadata search through each existing provider adapter
- **Query:** `AI adoption small business productivity`
- **Limit:** 2 results per adapter
- **Credentials/charges:** no API credential was configured or sent; no paid model or API call was made
- **Persistence:** results were validated in memory and not stored in a Veda project

## Results

| Adapter | Endpoint used by code | Returned | Validated as `ScholarlyWorkRecordV1` | Invalid |
|---|---|---:|---:|---:|
| OpenAlex | `https://api.openalex.org/works` | 2 | 2 | 0 |
| Crossref | `https://api.crossref.org/works` | 2 | 2 | 0 |

The exact check used each adapter's `search(query, limit=2)` method, converted returned provider-neutral records to dictionaries, and validated them with the strict Veda `ScholarlyWorkRecordV1` schema. It printed provider, count and schema-validity totals only. This verifies current endpoint reachability and response normalization for this query.

## Evidence and limits

- Crossref's [official REST API documentation](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) documents the public `/works` endpoint, JSON results, and states that no sign-up is required. This is bibliographic metadata, not a license to retrieve full text or abstracts without checking their rights.
- The attempted OpenAlex [official Works search documentation](https://docs.openalex.org/api-entities/works/search-works) redirected to `help.openalex.org`, which this research tool could not access. The adapter's public endpoint nevertheless returned two records and both normalized under the local schema. This record does not infer more API behavior than the request exercised.
- One small query does not establish provider reliability, completeness, relevance, ranking quality, record accuracy, access rights, full-text availability, or the quality of an end-to-end Veda report. Provider outage/degradation and normalization behavior remain covered separately by local fixtures.
- No titles, abstracts, authors or returned record payloads were written to the repository.
