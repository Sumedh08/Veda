# GOV.UK Search API discovery screen — 2026-11-01

## Decision

Use the GOV.UK Search API only as an opt-in, bounded metadata-discovery adapter for research explicitly scoped to the United Kingdom. Do not fetch or retain the linked publication body through this adapter. The publishing guidance calls the Search API unsupported, so Veda must identify it as a best-effort route rather than a durable completeness guarantee.

## Verified contract and reuse boundary

- The official [Search API guide](https://docs.publishing.service.gov.uk/repos/search-api/using-the-search-api.html) documents `GET https://www.gov.uk/api/search.json`, query/count/format filtering, and repeated `fields` parameters. The guide describes `count` up to 1500, but Veda intentionally caps requests at 10 records and issues one request per applicable job.
- GOV.UK's [reuse page](https://www.gov.uk/help/reuse-govuk-content) says the Search API is unsupported and subject to change. It describes the API as returning metadata and the terms applying to linked GOV.UK content separately.
- The [GOV.UK terms](https://www.gov.uk/help/terms-conditions) and [Open Government Licence](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/1/open-government-licence.htm) describe reuse for much Crown copyright content, with exclusions and attribution obligations. Veda's adapter therefore records a metadata-only boundary and does not infer permission to download, retain, or republish a document from the search result.

## Bounded live metadata probe

On 2026-11-01, a read-only HTTPS request to the documented endpoint with query `energy storage renewable` and `filter_format=policy_paper` returned HTTP 200. The first bounded results included “Clean Energy Industries Sector Plan,” its GOV.UK publication URL, `policy_paper` format, and three named government departments. No linked page or file was fetched. This demonstrates that the public metadata endpoint was reachable at probe time; it is not evidence of a complete catalog, stable API availability, content rights, or scientific quality.

## Implementation guardrails

- Route only when the persisted research geography explicitly names the UK or one of its constituent countries.
- Restrict the query to a short topic query and the `policy_paper` format; request only title, URL, timestamp, organisations, and format.
- Enforce fixed-host, no-redirect, bounded-response parsing and a single attempt. Record sanitized failures and do not retry automatically.
- Accept only publication paths on `gov.uk`, preserve named organisations and the original official URL, and keep source identity separate from relevance and methodology.
- Mark the Search API as unsupported/conditional in coverage. Do not represent the metadata record as retrieved full text.
