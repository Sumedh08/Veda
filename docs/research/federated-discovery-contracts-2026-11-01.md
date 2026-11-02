# Federated discovery API contracts — 2026-11-01

This note records current first-party API facts relevant to Veda's organization and publication discovery adapters. It describes metadata discovery only; it does not grant rights to retrieve, retain, or redistribute linked publication content.

## ROR: identity resolution, not a research directory

ROR's REST API supports organization lookup by name/non-ROR identifiers, filters, advanced search on domains and relationships, and a distinct affiliation-matching parameter intended for unstructured institutional affiliation strings. It is most appropriate for resolving candidate organizations to an identity, not for finding the full universe of subject-relevant organizations. The current published limit is 2,000 requests per five-minute window per IP; API queries can return at most 10,000 records. ROR data and IDs are CC0. [API reference](https://ror.readme.io/docs/rest-api), [ROR terms](https://ror.org/about/terms/).

**Veda implication:** keep query scope narrow and bounded; persist the query/input and exact matched ROR record as identity evidence. ROR existence or a domain match does not establish an organization's research quality or a publication's relevance.

## OpenAlex: discover organizations and their scholarly works

OpenAlex exposes `/institutions` and `/works`. Institution records carry ROR IDs, aliases, organization type, domain-related information, and affiliation-linked works; `/works?filter=institutions.id:<OpenAlex-ID>` is the documented institution-specific publication route. Resolve and store stable IDs before querying works; names are ambiguous. The current API documentation says basic queries are available without a key, API use is subject to budgets/rate limits, and account/API-key tiers and pay-as-you-go options exist. Inspect response usage metadata and do not assume an unlimited or account-level zero-cost route. OpenAlex metadata is CC0, but full-text locations each carry their own license/access information; the database license does not grant rights in underlying documents. [Institutions reference](https://help.openalex.org/data/institutions/), [API reference](https://help.openalex.org/api/), [authentication and limits](https://help.openalex.org/api/authentication/), [location licenses](https://help.openalex.org/data/licenses/).

**Veda implication:** OpenAlex provides an operational dynamic path for research organizations that appear in scholarly affiliations, including previously unregistered universities and research institutes. It does not cover every consultancy, policy institute, government agency, or report catalog. Treat affiliation as identity/discovery evidence, not a quality score.

## OpenAIRE Graph: federated scholarly organizations and outputs

The current Graph API is under `/graph/v4`; `GET /organizations` covers universities, research organizations, funders and companies, and `GET /research-products` covers publications, datasets, software and other outputs. Search, filters, pagination, cursor paging, and response-field selection are documented. Anonymous requests are allowed but have a lower hourly limit than registered/authenticated clients. OpenAIRE says returned Graph records are reusable under CC BY with attribution; this applies to Graph metadata, not automatically to linked third-party full text. [v4 API overview](https://graph.openaire.eu/docs/apis/graph-api-v4/), [quickstart](https://graph.openaire.eu/docs/apis/graph-api-v4/quickstart/), [API terms](https://graph.openaire.eu/docs/11.2.0/apis/terms/).

**Veda implication:** OpenAIRE is a real path to discover organizations and publications beyond OpenAlex's core, but its coverage is the graph's participating data sources, not universal. Preserve provider IDs and retrieval provenance and keep publication-level relevance/method assessment in Veda.

## World Bank Documents & Reports: official publication metadata under a product-use gate

The official D&R API is a GET search endpoint (`https://search.worldbank.org/api/v3/wds`) with `qterm`, field selection (`fl`), bounded pagination (`rows`, `os`), facets and date filters. With `qterm`, results may match title, abstract, report/project fields, and other indexed metadata; relevance sorting is the documented default when using `qterm`. [API reference](https://documents.worldbank.org/en/publication/documents-reports/api).

The World Bank Group's current terms say general materials and API-facilitated use are limited to non-commercial purposes absent written permission; they also distinguish materials with separate terms and require binding agreements with users where an API facilitates their access to materials. Other parties may own rights in some materials. Thus public availability is not a blanket license, and metadata lookup does not establish a linked document's reuse rights. [Terms, material and API clauses](https://www.worldbank.org/ext/en/legal/terms-conditions), [Open Knowledge Repository terms](https://openknowledge.worldbank.org/terms-of-use).

**Veda implication:** a terms confirmation flag is not a substitute for determining the product's use, applicable material-specific terms, and downstream access conditions. Keep the adapter default-disabled until that product-use path is actually established; when enabled, label records metadata-only and do not fetch PDF content absent a separate document-rights decision.

## Not covered by these APIs

These providers do not jointly establish comprehensive discovery of consulting reports, think-tank research, general government publications, regulatory materials, or specialist institution outputs. Veda still needs an authorized provider-neutral web/catalog search adapter or additional official institutional catalogs for those classes. A typed interface without a configured and exercised provider is not live discovery.

No paid inference, content-file retrieval, or paid API operation was performed to prepare this note.
