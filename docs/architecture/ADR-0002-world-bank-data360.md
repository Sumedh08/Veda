# ADR-0002: Add licensed, descriptive World Bank Data360 observations

- **Status:** Accepted (2026-10-29)
- **Decision owners:** Veda implementation
- **Scope:** A narrow official-statistics discovery path for global and exact country/economy WDI indicator queries

## Context and evidence

Veda needs institutional data that can complement scholarly papers without being mislabeled as a causal study or copied without a clear reuse basis. The World Bank's official [Data360 OpenAPI specification](https://raw.githubusercontent.com/worldbank/open-api-specs/main/Data360%20Open_API.json) documents indicator search, metadata, observation, and disaggregation endpoints. WDI is cataloged as [World Development Indicators, dataset 0037712](https://datacatalog.worldbank.org/infrastructure-data/search/dataset/0037712/world-development-indicators). The World Bank's [dataset terms](https://www.worldbank.org/ext/en/legal/terms-conditions/datasets) state CC BY 4.0 as a general rule while describing exceptions; its [WDI catalog entry](https://datacatalog.worldbank.org/infrastructure-data/search/dataset/0037712/world-development-indicators) also warns that some inputs originate from third parties. The API's series metadata exposes a license and named contributing sources, so permission is checked on the specific series before its values are requested.

A read-only metadata/value request for WDI population data returned series license `CC BY-4.0`, contributor metadata identifying the UN Population Division, and a World observation with period, raw value and observation unit codes. This confirmed the response shape, not the correctness or fitness of all possible indicators. No bulk dataset was copied.

## Decision

Use the official Data360 API only for one bounded indicator candidate per discovery step. Search results are constrained to the `WB_WDI` database and an indicator identifier matching the WDI namespace. Fetch series metadata first. Fetch observations only when that series declares the exact CC BY 4.0 license name and URI. Request the latest World (`WLD`) observation set, then keep at most four finite numeric observations that match the requested indicator/geography and have only total/unclassified breakdown dimensions.

Persist the indicator ID/name, WDI dataset identity, original Data360 observation endpoint, query, retrieval timestamp, observation period and raw value, geography, unit codes/multiplier/status, metadata-provided measurement unit, source update date, periodicity, definition, statistical concept, methodology, limitations, license, attribution, contributor list, and terms/data-catalog URLs. The UI and report label this record as an official statistic, distinguish raw unit codes from the descriptive unit metadata, and state that it is descriptive rather than a study or causal estimate. Appraisal is not applicable.

Global questions use Data360's `WLD` aggregate directly. A country/economy name or code must resolve exactly through the official [World Bank Countries API](https://datahelpdesk.worldbank.org/knowledgebase/articles/898590-country-api-queries); aggregate rows are excluded by their `region.id == "NA"` marker. The API states that its three-letter ID is an ISO 3166-1 alpha-3 code where available and otherwise a World Bank three-letter code, so the adapter treats it as a World Bank country/economy reference code rather than asserting every code is ISO. It requests only that `REF_AREA`, then persists only rows that echo the exact indicator and resolved area and satisfy the same total/unclassified-dimension filter. The indicator-level response is the final check that a code maps to a usable Data360 series. Names with multiple matches, aggregate names/codes, multi-country scopes and unknown names fail closed. Subnational areas and country groups remain unsupported.

Failure or an unavailable/license-blocked statistic does not stop scholarly discovery; a source slot is reserved only for a usable licensed result. The adapter does not retry automatically, follow redirects, retain raw responses, or claim indicator semantics are adequate for the user's question. Country catalog requests are read-only, limited to one page and a 512 KB response cap, use a four-second timeout, and are not cached across jobs in this release.

## Rejected alternatives

- **World Bank Indicators API as a generic data license:** the general API documentation does not establish a reuse grant for every indicator and series. It is not used as permission evidence; a future adapter must check each indicator's rights and third-party source terms.
- **Treating an institution or publisher as a blanket license:** this would miss series-level exceptions and contributor rights. Metadata license gates observation retrieval; attribution and contributor provenance are retained.
- **Treating every three-character reference code as a country:** Data360 returns aggregates alongside individual areas. Country/economy names and codes now resolve against the maintained World Bank country API and aggregate entries are excluded before an indicator-specific exact-area query.
- **Using statistic appraisal fields intended for empirical studies:** a descriptive series does not carry study design, comparator, or causal identification. The current appraisal result is `not_applicable`.

## Consequences and follow-up

- Data360 and the country catalog are independent, read-only public provider calls, not model calls. Each response is bounded by a four-second HTTP timeout, 512 KB response cap and one search result.
- Search relevance, unit interpretation, freshness, and source coverage remain empirical quality questions. The UI shows the source-provided fields instead of inferring conversions or causal meaning.
- Country/economy support is limited to exact World Bank API names/codes; region groups, subnational scope, indicator relevance evaluation, provider rate-limit monitoring and human research-quality evaluation remain separate backlog work.
- No OpenRouter key is used by this adapter. The key previously pasted into the conversation is considered exposed and must be rotated before any live model job.
