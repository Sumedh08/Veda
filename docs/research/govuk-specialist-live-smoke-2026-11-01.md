# GOV.UK identity and specialist publication smoke — 2026-11-01

## Run identity

- Question: “For UK offshore wind renewable energy projects, how should export-cable reliability, HVDC converter topology, capital cost, and transmission resilience be balanced?”
- Local browser/API job: `993aab85-10f6-4409-99d2-de8a811d393c`.
- Report: `651652f3-0eab-4d06-a7fc-4246f482944a`.
- SQLite artifact: `evaluation/veda-govuk-evidence-20261101T205912.sqlite3`.
- Operational status: `completed_with_limitations`; model provider disabled, zero inference calls, deterministic evidence map. This is not an AI research success or scientific-quality evaluation.
- Browser test: `live scholarly/model smoke completes a bounded Veda browser run` passed **1/1** after the source passage selector was made first-match explicit. Full serial fixture Playwright passed **49**, with **15** opt-in tests skipped.

## What the job discovered and verified

- **GOV.UK:** 10 policy-paper results. The exact GOV.UK Organizations API verified two publisher identities, Department for Energy Security and Net Zero (DESNZ) and Department for Business and Trade (DBT), by exact live organization slug. Identity verification is not a methodology judgment.
- **GOV.UK selection:** two records were selected and eight were excluded as `insufficient_topic_overlap`. The selected records were “Offshore wind net zero investment roadmap” and “Electricity bill discount scheme for transmission network infrastructure: expected eligible projects.” The latter remains metadata-only and was not appraised.
- The search descriptions were available transiently and used by the eligibility gate, but the persisted lexical relevance score used title/abstract fields; these result records had no abstract. Thus the eight exclusions are a demonstrated metadata/lexical-selection limitation, not evidence that every excluded item is irrelevant. The two scores were only `0.082353`; the bill-discount title matched “projects” and “transmission,” so it may be a marginal selection. No reviewer labels exist to quantify false positives or false negatives.
- **Specialist organization:** Offshore Renewable Energy Catapult (ORE Catapult), absent from the curated registry, was discovered from topic-aligned scholarly affiliations, resolved to ROR `https://ror.org/03ffv2k10`, then searched through the official-domain-linked WordPress catalog. Two relevant publication records were selected: “Cornwall FLOW Accelerator: Optimised cable connection options for floating offshore wind” and “Offshore Wind Subsea Power Cables: Installation, Operation and Market Trends.” Their publisher identity and discovery query are recorded; they remain `metadata_only`, rights and methodology are `not_assessed`, and no content was fetched. Their citations do not carry extracted evidence passages.
- Total discovery ledger: **35 candidate records, 14 selected sources, 14 citation links**. These are counts, not recall or precision metrics.

## Content carried into the report

The selected DESNZ “Offshore wind net zero investment roadmap” page was retrieved once through the GOV.UK Content API. Veda persisted source `b49eadf2-5671-42ca-9107-f05f4260721d`, retrieved document `442b8ce2-fbf8-5368-a59e-ed358c763fdc`, content SHA-256 `b4aa6cc1c2a19ac5cbe3e094da9772812a692097a47b5053098961b18cf89a5a`, six exact passages, and six passage-linked source-reported claims. The report cites it as S1; the real browser opened the report and the cited source inspector.

The access class is `official_publication_page_body`, not full-text report. Provenance records the API and canonical publication URL, retrieval time, content hash, and a default OGL 3.0 basis with a per-item-rights caveat. The GOV.UK reuse page says most GOV.UK content is under OGL v3.0 except where stated; the Content API does not supply a per-item license here. Linked PDF/report attachments and third-party material were not fetched. The passages reflect policy/investment framing and stated deployment ambitions; the job did not inspect technical methods, outcome data, or independent evaluation of those claims. See [GOV.UK reuse terms](https://www.gov.uk/help/reuse-govuk-content) and the [GOV.UK Content Store API contract](https://docs.publishing.service.gov.uk/repos/content-store/content-store-api.html).

## Selection diagnosis and remaining specialist gap

This run corrects the earlier “all ten GOV.UK results excluded” observation for a more specific, UK-scoped question: two of ten now pass selection, one contributes persisted page evidence, and eight fail the lexical overlap gate. The current evidence cannot classify all eight as genuinely irrelevant because their descriptions are not part of the persisted score/features. Search snippets are currently discarded after selection, so later reviewers cannot reassess those decisions. No source was forced into the report due to publisher identity.

The ORE Catapult route demonstrates autonomous specialist identity and publication discovery, but not specialist evidence acquisition. A subsequent bounded OpenAIRE Graph V4 metadata lookup for the ORE-affiliated Energies DOI `10.3390/en10070851` returned CC-BY repository-location metadata, including a Strathprints URL; this lookup was outside the Veda job and fetched no publication bytes. The Veda workflow does not resolve OpenAIRE repository instances for selected works. Strathprints publishes a repository-wide noncommercial reuse policy, while the item page did not expose its license in the browser text; the exact item license and Veda product-use scope must be resolved before acquiring or retaining that copy. Its [repository policy](https://strathprints.strath.ac.uk/policies.html) distinguishes metadata reuse from full-text reuse. This is a promising implementation lead, not evidence used in the report.

Consulting, think-tank, ADB and broad general-web discovery remain unavailable. There were no model calls, OpenAlex content-file requests, PDF/attachment downloads, paid calls, or deployments. Public metadata endpoints did not report usage charges; zero charge is therefore not asserted for every metadata service.
