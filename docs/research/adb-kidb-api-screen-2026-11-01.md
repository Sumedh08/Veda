# ADB Key Indicators Database API screen — 2026-11-01

## Recommendation

**GO for a bounded ADB statistics adapter, with per-series source-rights provenance.** KIDB has documented SDMX endpoints, machine-readable indicator names/definitions and thematic dataflows, an explicit 20-query/minute limit, and KIDB-specific terms that permit commercial and non-commercial use with attribution. This is a better first official-statistics adapter candidate than a publication catalog. It covers macroeconomic, social, environmental, labor, prices, public finance, trade and SDG indicators for ADB economies; it is not a scholarly/publication discovery source. [KIDB overview](https://kidb.adb.org/), [KIDB FAQ](https://kidb.adb.org/faq)

The commercial grant is subject to “unless otherwise indicated” and a specific third-party-data exception. KIDB records must preserve provider, dataflow, indicator, unit, methodology, observation status, and the terms URL. The current CSV response includes `DATA_SOURCE` but no license field; when the source or its applicable terms are unclear, retain a rights-unknown state and do not redistribute the underlying value until resolved. Do not label the KIDB terms as CC BY: the KIDB-specific page grants uses directly but names no Creative Commons license. The ADB Data Library has separate terms. [KIDB Terms of Use](https://kidb.adb.org/terms), [ADB website terms](https://www.adb.org/terms-use), [ADB Data Library terms](https://data.adb.org/terms-use-data)

## API contract and topic discovery

- **Data:** `GET https://kidb.adb.org/api/v5/sdmx/data/{dataflow_id}/{sdmx_key}?startPeriod=...&endPeriod=...&format=sdmx-csv`. The main DSD key is `FREQUENCY.INDICATOR.ECONOMY_CODE`; annual frequency is `A`, multiple indicator or economy codes are joined with `+`, and omitted dimensions request all available values. Trade has additional counterpart-area and currency dimensions. The dataflow ID is agency plus flow, e.g. `ADB,DF_NA`. [KIDB SDMx API guide](https://kidb.adb.org/api)
- **Flow catalog:** `GET https://kidb.adb.org/api/v5/sdmx/structure/dataflow/all/all/+?format=sdmx-json` lists flow IDs and labels; a flow can be fetched as `.../structure/dataflow/ADB/DF_NA/+?format=sdmx-json`.
- **Global indicator catalog:** `GET https://kidb.adb.org/api/v5/sdmx/structure/codelist/ADB/CL_KIDB_INDICATORS/+?format=sdmx-json` returns indicator IDs, names, and descriptions. To resolve per-flow membership, the documented `GET https://kidb.adb.org/api/dataflow/indicators/{flow_id}` returns records with indicator `code`, `name`, and `description`. The documentation does not define a server-side free-text topic-search endpoint; Veda should index these bounded catalog records and match query terms against the returned name/description, then resolve the indicator to a dataflow before requesting observations. Avoid scanning each flow on every user query; refresh and cache the catalog under the 20/minute limit. [KIDB SDMx API guide](https://kidb.adb.org/api)
- **Response identifiers and shape:** preserve agency/dataflow/version, indicator code, economy code, frequency and period. The documented outputs include XML, CSV and JSON. A live CSV sample included `DATAFLOW,FREQ,INDICATOR,ECONOMY_CODE,TIME_PERIOD,OBS_VALUE,UNIT,UNIT_MULT,DECIMALS,FOOTNOTE,OBS_STATUS,REF_YEAR,BASE_YEAR,DATA_SOURCE,METHODOLOGY`. [KIDB SDMx API guide](https://kidb.adb.org/api)
- **Bounds and auth:** ADB says the API is limited to 20 queries per minute and excess requests are temporarily blocked. The guide’s Python examples call `requests.get` without credentials; the anonymous GETs below succeeded without an API key or authorization header. The guide does not promise availability or provide a different quota for metadata. It recommends splitting large queries into chunks of about 15–20 indicators, avoiding Generic XML, and adding request delays. Period documentation currently says `startPeriod` from 2000 and `endPeriod` up to 2024. [KIDB SDMx API guide](https://kidb.adb.org/api)

## KIDB-specific reuse terms

The KIDB [Terms of Use](https://kidb.adb.org/terms) state that, unless otherwise indicated, all KIDB data and metadata may be copied, downloaded, distributed, adapted, duplicated, linked, displayed, or included in other products for commercial or non-commercial purposes at no cost. Required acknowledgement: **Asian Development Bank: Key Indicators Database Online (https://kidb.adb.org). Accessed on [date].** When sharing data, the acknowledgement must flow through sublicenses. Users may not imply ADB endorsement or use the ADB logo without permission. The page reserves ADB’s right to modify or discontinue the database or access methods.

The same KIDB terms warn that linked/contained third-party content may have different rights and direct users to the originating source’s terms. The FAQ says KIDB sources include member-economy statistical offices and international organizations, and some international-agency data are not publicly available through KIDB. ADB’s current general terms state KIDB-specific conditions are incorporated by reference; they also confirm third-party content can have different terms. Therefore a source label is provenance, not proof that the originating provider grants the same commercial reuse. The separate Data Library CC BY 3.0 IGO terms must not be substituted for KIDB’s specific terms. [KIDB Terms of Use](https://kidb.adb.org/terms), [KIDB FAQ](https://kidb.adb.org/faq), [ADB website terms](https://www.adb.org/terms-use), [ADB Data Library terms](https://data.adb.org/terms-use-data)

## Live read-only check

On 2026-11-01, read-only HTTPS GETs were made without credentials and below the published quota. No paid API or model call was made.

- `/api/dataflow/indicators/DF_NA` returned a JSON array of 145 indicators. Entries had `code`, `name`, and `description`; examples included `NGDP_XDC` / “GDP at current prices” and a definition suitable for local topic matching.
- `/api/v5/sdmx/structure/dataflow/all/all/+?format=sdmx-json` returned a structure response with `data.dataflows` entries carrying `agencyID`, `id`, `version`, `name`, and `structure`.
- `/api/v5/sdmx/structure/codelist/ADB/CL_KIDB_INDICATORS/+?format=sdmx-json` returned 691 code entries with `id`, `name`, and `description`. This request took about 19 seconds in this environment; that is an observation, not a service guarantee.
- `/api/v5/sdmx/data/ADB,DF_NA/A.NGDP_XDC.PHI?startPeriod=2020&endPeriod=2024&format=sdmx-csv` returned HTTP 200 (`text/csv`, 676 bytes) and five annual rows for the Philippines, 2020–2024. The rows included unit/value/status, `DATA_SOURCE=Philippine Statistics Authority`, and methodology fields.
- The documented `endPeriod=2024` bound was material: the same one-indicator request for `startPeriod=2025&endPeriod=2025` returned HTTP 422. The site’s “data last updated” date therefore must not be mistaken for an API period bound; current API docs do not permit querying beyond 2024.

These calls verify only the endpoints and one sample series from this environment. They do not verify all dataflows, the completeness or correctness of observations, or licensing of the identified third-party source.

## Adapter seam and acceptance tests

Keep KIDB behind a statistics-provider interface separate from publication search. On Python 3.12+, Veda’s existing `httpx` dependency can make HTTPS GETs; parse SDMX-JSON metadata and SDMX-CSV with bounded responses and explicit timeouts. Suggested checks:

1. Match topic text against indicator names/descriptions in a cached, versioned catalog; verify every matched indicator resolves to a valid flow/code pair before constructing the DSD key.
2. Construct fixed-host URLs with correctly encoded query parameters; never allow user text to choose the host, flow, indicator code, economy code, or dimensions without validating against fetched metadata.
3. Enforce the API’s 20/minute ceiling with a lower local budget, sequential backoff on 429/temporary blocks, bounded concurrency/pages, and a catalog refresh schedule; avoid fan-out on each user query.
4. Parse CSV by headers, validate identifiers, years, numeric `OBS_VALUE`, units and status; verify empty, malformed, duplicate, partial, 422, 429, timeout, and 5xx responses remain provider errors rather than zero observations.
5. Preserve the exact attribution, source, API query, retrieval time, dataflow/indicator/economy/period, methodology and `OBS_STATUS`. Enforce per-source reuse gating when third-party terms are indicated or unresolved, and never imply ADB endorsement.
6. Confirm the 2024 period ceiling is surfaced to callers; do not silently extrapolate, relabel stale data, or claim a 2025+ series was checked.

No Veda adapter or tests were implemented for this screen.
