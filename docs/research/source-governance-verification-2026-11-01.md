# Source-governance verification — 2026-11-01

## Implemented boundary

The single governed registry is `backend/app/research/source-governance-registry.json`, version `veda-source-governance-2026-11-01-v2`. It records 23 institutional identities, official domains, aliases, identity provenance, categories and adapter status. The strict schema can represent QS university ranks, subject-specific journal quartiles and FT50 membership, with identifiers and dated provenance. The shipped university and journal arrays are intentionally empty: no ranking/list records have been imported. Fixture tests exercise those classifier paths; they are not evidence that a real institution or journal in the registry has a verified rank.

Identity, relevance, document methodology, evidence strength, access and rights remain separate fields. Registry identity cannot assert that a report is relevant or methodologically sound. Ranking membership is only an exact, categorical tie-break after the persisted relevance score; it does not establish truth. Unregistered relevant counterevidence is retained for review. Unknown generic sources receive no promotion merely to fill a source-class slot. Source-class plans and searched/missing adapter states flow through discovery coverage, candidate/source APIs and the browser inspector.

## Actual integration evidence and limits

- Crossref and OpenAlex remain the integrated scholarly discovery adapters. A bounded live Crossref query for “Who on Earth Is Using Generative AI” returned the World Bank working paper DOI `10.1596/1813-9450-10870`. Crossref’s public DOI-prefix record identifies `10.1596` as World Bank. Veda’s current classifier resolved the record as `academic` and `multilateral`, identity `verified`, adapter status `registered_adapter_available`, and methodology `not_assessed`. This was an adapter-level metadata smoke, not a persisted Veda report or an appraisal of the paper.
- The official World Bank Documents & Reports API was inspected with one bounded public metadata request and returned JSON records, including *Who on Earth Is Using Generative AI?*. Its official documentation describes bounded query/field/page parameters. The Veda workflow connector is implemented, but it does not dispatch unless `world_bank_documents_noncommercial_use_confirmed` is explicitly enabled. The World Bank terms restrict API-facilitated use of materials to non-commercial uses absent permission; Veda's product-use scope is not confirmed, and publication-specific content rights remain separate. The T-139 holdout recorded this connector as not attempted for that reason.
- World Bank Data360 and ILOSTAT adapters already exist for narrow official-statistics use cases. They are conditional and do not amount to institutional-publication search. ILOSTAT live reachability/version and series-specific rights remain unresolved under T-49/B-011. No dedicated ADB, consulting/MBB/Big Four, think-tank or general government-publication connector is integrated. The plan/UI must report these as missing rather than searched.
- A model-disabled real local browser/API holdout (T-139; question-only input) discovered University of Central Florida and Kangwon National University, neither in the 23-identity seed registry, from OpenAIRE/OpenAlex publication affiliations. ROR exact-ID records verified identity and yielded official domains; OpenAlex resolved both to institution IDs and returned institution-linked publication metadata. Irrelevant institution-query results were excluded by Veda's original-question topic gate. The persisted report/browser record is `evaluation/t139-autonomous-academic-organization-discovery-2026-11-01.md`. This validates dynamic academic-affiliation discovery only. The report selected eight metadata-only records, produced zero passages/claims, and left multilateral/official/government coverage missing. Organization identity does not establish quality, and neither institution nor publication methods were independently reviewed.
- The T-139 candidate ledger also preserved an India/SAARC renewable-electricity paper as capacity-excluded (rank 16, lexical score 0.272727). This is a plausible geographic-coverage candidate requiring human relevance review, not a proven retrieval miss or a hard-coded inclusion case. The holdout has no adjudicated reference set; all organization/publication discovery-quality metrics remain `NOT_EVALUATED`.
- The existing Europe PMC JATS report/browser smoke (T-136) is genuine permitted full-text integration for one unrelated CC-BY paper. It predates source-governance persistence and is not evidence of source-class coverage or target-topic quality.

## Ranking-data decision

The official QS ranking page exposes the 2027 WUR, but QS terms state that the rankings data are licensed CC BY-NC-ND 4.0, prohibit scraping/reconfiguration, and direct commercial use to QS for permission. Veda will not scrape or bulk import that dataset on the current product-use record. The registry therefore makes no QS institution claims. No primary, reusable SCImago/JCR quartile export or licensed FT50 membership list was verified for this checkpoint; no Q1 or FT50 records are asserted. The data schema and fixture tests preserve an extension path once the exact dataset, year, subject/ISSN mapping and permitted use are reviewed.

This is a licensing and product-use gate, not a claim that QS rankings are categorically prohibited or that a journal list cannot ever be licensed. Ranking datasets are optional contextual metadata and are not prerequisites for discovery. A specific, properly licensed record can be added with its source/version provenance.

## Primary references

- [QS World University Rankings 2027](https://www.topuniversities.com/qs-top-uni-wur)
- [QS Terms and Conditions](https://www.topuniversities.com/terms-conditions)
- [QS data copyright and license](https://www.topuniversities.com/data-copyright)
- [World Bank Documents & Reports API](https://documents.worldbank.org/en/publication/documents-reports/api)
- [World Bank Group Terms & Conditions](https://www.worldbank.org/ext/en/legal/terms-conditions)
- [Crossref DOI prefix record for 10.1596](https://api.crossref.org/prefixes/10.1596)
- [Crossref Works API](https://api.crossref.org/works)
- [OpenAlex full-text availability and access documentation](https://help.openalex.org/access/fulltext/)

No model inference, paid API request, content-file download or deployment was performed for this source-governance check. No scientific-quality improvement score is available; independent relevance, methods and claim-support labels remain absent.
