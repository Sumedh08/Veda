# T-139 — Autonomous academic organization-discovery holdout

**Status:** Operational academic-affiliation discovery demonstrated; cross-sector discovery and evidence-quality validation not demonstrated.

## Run identity

- Research question: “How do battery storage and power-grid constraints affect the economics and deployment of renewable electricity in India?”
- Local SQLite artifact: `evaluation/veda-autonomous-holdout-query-repaired-20261101T163139.sqlite3`
- Job: `22602d26-65c5-4550-bf5f-4e499c605941`
- Report: `e064bc59-5237-42a1-98da-762d91f28adc`
- Operational status: `completed_with_limitations`
- Model provider: disabled; **zero inference requests**, no model-authored output and no inference cost.
- Browser/API: the actual local Playwright workflow opened the persisted report and citation/source inspection UI. The report had three citation links; source passages were not available for inspection because the selected records were metadata-only.

## Bounded discovery results

| Channel | Requests | Results/candidate occurrences |
|---|---:|---:|
| Crossref | 3 | 9 |
| OpenAlex works | 3 | 9 |
| OpenAIRE Graph | 1 | 8 |
| ROR exact identity checks | 2 | 2 |
| OpenAlex ROR-to-institution resolution | 1 | 1 |
| OpenAlex institution-publication searches | 2 | 3 |
| **Total** | **12** | **29 scholarly discovery candidate occurrences** |

Two organizations absent from the curated registry were discovered from affiliations and exactly verified through ROR:

- **University of Central Florida** — ROR `https://ror.org/036nfer12`, OpenAlex `I106165777`. Its affiliation-linked publication *Smoothing of PV Output Power in Grid-Tied Energy Storage System with Model Predictive Control and Battery Lifetime Consideration* (DOI `10.1109/ecce47101.2021.9595545`) entered the selected metadata set. Identity was verified; organization quality and the paper's methodology were not assessed.
- **Kangwon National University** — ROR `https://ror.org/01mh5ph17`, OpenAlex `I165507594`. An affiliation-linked paper *Integrated Battery and Hydrogen Energy Storage for Enhanced Grid Power Savings and Green Hydrogen Utilization* (DOI `10.3390/app14177631`) was discovered, but excluded by the source cap. Identity was verified; organization quality and the paper's methodology were not assessed.

Institution publication searches returned three additional works. The returned industrial-engineering overview, electric-vehicle patent trend analysis, and water-management roadmap were excluded by the original-topic overlap gate. This is evidence that the gate rejected obvious topic drift; it is not a precision estimate.

## Evidence and report inspection

- 29 candidate occurrences were persisted; 8 source records were selected and 10 occurrences were excluded at the source cap.
- All 8 selected records were metadata-only. No source version with legally usable full text was acquired in this run; no evidence passages or extracted claims were persisted.
- The deterministic report said that no source statements could be extracted and did not make an evidence-based substantive conclusion. It contained three citation links but zero claim-level passage citations. Deterministic citation integrity therefore checked zero claims; semantic citation support was not performed.
- The browser displayed the actual persisted report and linked source metadata. It could not inspect original evidence passages because none were available.
- Planned source coverage at the time of this artifact included academic, multilateral, official statistics and government. Only academic discovery ran. World Bank Documents & Reports was not dispatched because product-use confirmation was absent; World Bank Data360 was not dispatched because its topic gate did not recognize “renewable electricity.” Both had zero candidates. The current source-class planner v2 additionally records consulting and think-tank intent for the energy-investment question, but those routes remain `not_integrated`; v2 was implemented after this persisted report.
- A candidate titled *Electricity system based on 100% renewable energy for India and SAARC* (DOI `10.1371/journal.pone.0180611`) was excluded at source rank 16 (`source_limit`; lexical score 0.272727, 3 of 11 title terms including “India”). It is plausibly relevant to geographic coverage, but was not independently judged eligible or critical. Its exclusion is a concrete review case for future constrained source selection; it must not be inserted as a hard-coded retrieval exception.
- The source-cap stopping reason was `source_cap_excluded_candidates`. Citation expansion was not attempted because it requires operator opt-in.

## Errors, cost, and limits

- Crossref/OpenAlex/OpenAIRE/ROR identity routes reported no provider search failures. A selected IEEE DOI's optional Europe PMC JATS lookup timed out; the source record retained that failure, and full-text extraction did not occur.
- The metadata APIs' usage and account billing were not reported in Veda. Do not infer zero external API billing from the zero model-call ledger. No OpenAlex content file was downloaded; no paid inference, deployment, or credentials were used.
- Reference organizations and publications were not independently adjudicated for this holdout. Organization-discovery recall, identity-verification precision, publication-discovery recall, selection precision, counterevidence recall and critical full-text coverage are **NOT_EVALUATED** because no reviewed reference-set denominators or human labels exist.
- No consulting, think-tank, ADB, government-publication or general web-search channel ran. OpenAIRE/OpenAlex affiliation discovery is not a substitute for those source classes.
- The real run used source-planning policy v1. Policy v2 now maps energy/climate, trade/industrial-policy and regulatory cues to applicable source-class coverage intent and stores matched cue reasons. This only changes and explains planning; it does not cause an unavailable connector to run.

## Reproduction and related tests

The retained SQLite artifact is read-only evidence; do not overwrite it. The original Playwright command was `npx playwright test e2e/real-api.e2e.ts --grep 'live scholarly/model smoke' --workers=1` with `VEDA_REAL_API_E2E=1`, `VEDA_LIVE_SCHOLARLY_E2E=1`, a fresh path under `evaluation/`, the research question above, `VEDA_WORLD_BANK_DOCUMENTS_NONCOMMERCIAL_USE_CONFIRMED=false`, and `OPENALEX_ALLOW_BILLABLE_CALLS=false`. No model provider was enabled.

Offline persistence/reuse regression: `backend/tests/test_workflow.py::test_discovery_persists_openaire_unseeded_organization_publication`; identity freshness and identifier validation: `backend/tests/test_organization_identity_store.py`; domain-class planning scenarios: `backend/tests/test_source_governance.py::test_domain_planner_covers_energy_trade_and_regulatory_source_classes`.

