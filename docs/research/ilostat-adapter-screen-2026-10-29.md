# ILOSTAT SDMX adapter screen — 2026-10-29

## Decision

Add a deliberately narrow ILOSTAT adapter for one global annual employment
series. Do not treat the adapter as live-service verified: the documented API
host could not be reached from this environment, and the current Swagger server
URL resolves through a different host/path that returned 404. The production
code uses the 2024 ILOSTAT service guide's HTTPS root and degrades independently
if that route is unavailable. Fixture tests verify the request contract, CSV
validation, bounds and pipeline persistence only.

## First-party evidence

- The [ILOSTAT SDMX User Guide](https://www.ilo.org/resource/other/ilostat-sdmx-user-guide)
  describes the API as a public SDMX service for ILO labour statistics.
- Its [2024 API Reference Guide](https://www.ilo.org/sites/default/files/2024-12/ILOSTAT-SDMX_Dissem%20API%20Ref%20Guide_V4.1-%28ILO%20Style%29.pdf)
  names `https://sdmx.ilo.org/rest` as the production root, documents HTTPS GET
  data and metadata resources, SDMX-CSV output, dimension-filtered dataflow
  queries, `lastNObservations`, and the `Range: values=...` bound. It warns that
  unrestricted flows can return hundreds of thousands of rows and multi-megabyte
  responses. The guide documents `DF_EMP_TEMP_SEX_AGE_NB` and its total sex/age
  classification pattern; `X01` is the ILOSTAT code for World. The exact
  `EMP_TEMP_NB` measure key is derived from the guide's documented indicator
  naming formula, not from a live dataflow response.
- The indexed [ILOSTAT SDMX Swagger/OpenAPI document](https://sdmx.ilo.org/swagger.json)
  reports `https://www.ilo.org/sdmx/rest` as its server and documents CSV output,
  one-or-more latest observations, and response format/media types.
- The ILO [Rights and permissions policy](https://www.ilo.org/rights-and-permissions)
  says datasets and accompanying reference metadata published or made available
  from 2023-05-03 are CC BY 4.0, while older datasets do not automatically
  qualify. It excludes microdata supplied by or obtained from constituents and
  partner institutions for ILO-only use, and warns about third-party materials.
- ILOSTAT identifies itself as the ILO Statistics Branch's labour-statistics
  database and provides the [ILOSTAT data portal](https://ilostat.ilo.org/data/).

## Live endpoint check

Read-only requests were attempted against the published production paths on
2026-10-29. `https://sdmx.ilo.org/rest/dataflow/...` returned HTTP 403. The
Swagger server path on `www.ilo.org` returned HTTP 301 to the same SDMX path on
`webapps.ilo.org`; the redirected request returned HTTP 404. The test host
`sdmx-test.ilo.org` did not resolve. A second bounded read-only attempt of the exact pinned adapter data URL (`/rest/data/ILO,DF_EMP_TEMP_SEX_AGE_NB/X01.A.EMP_TEMP_NB.SEX_T.AGE_5YRBANDS_TOTAL`, `lastNObservations=1`, `detail=full`, `format=csv`) on 2026-10-29 returned HTTP 404 `text/plain` with no redirect; the response body was not read. These are environment observations, not a
claim that the ILO service is generally down. The API behavior and current
response columns still need a live run from an allowed network.

## Implemented scope and limits

- Only explicitly employment-related queries with an explicit global/world
  geography are eligible. Country requests and other statistical topics do not
  reach ILOSTAT; World Bank Data360 remains independently scoped.
- The adapter sends no research prompt to ILO. It requests the fixed
  `DF_EMP_TEMP_SEX_AGE_NB` flow with one pinned annual world/total-sex/total-age
  series and `lastNObservations=1`.
- Redirects are disabled; connect/read timeouts are short; the response is
  streamed and capped at 512 KB; the API range and parser row cap are ten; CSV
  dimensions and numeric values are validated; multiple matching rows are
  rejected rather than silently ranked.
- Values are presented and stored as descriptive official statistics, never as
  studies, causal estimates, or scholarly-ranked results. ILOSTAT source notes
  and the ILO rights-policy limits are retained in the source inspector and
  report attribution.
- The dataset's per-series publication date/version is not exposed by the
  guide's documented query contract. Veda therefore surfaces the policy's
  2023-05-03 threshold and third-party/microdata exceptions in the reuse
  statement and limitation text; it does not claim to have independently audited
  constituent-level rights.

## Verification status

The tests use mock HTTP responses. They check fixed request shape, API range,
media type, exact dimensions, valid and invalid values, row/byte bounds,
ambiguous result rejection, scope/topic exclusion, sanitized failures, separate
statistics evidence, source attribution, and provider degradation. No ILO
observation has been fetched or validated against the live API in this task.

**Next external verification:** once the route responds from an allowed network,
run one read-only request for the pinned flow, inspect the actual CSV header and
dataflow version, compare the returned observation and source note to ILOSTAT's
portal, and confirm that the rights policy applies to that data release. Until
then, do not describe ILOSTAT retrieval as live-tested.
