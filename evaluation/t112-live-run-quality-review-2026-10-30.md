# T-112 live run: operational and evidence quality review

**Disposition:** Operational validation failed. An evidence-map report was saved and inspected in the browser, but no structured model result was accepted and no AI-assisted research report was produced.

## Scope and execution

- **Question:** “Does generative AI improve software developer productivity, and why do empirical studies sometimes report different findings?”
- **Authorization:** One bounded local job, free-only OpenRouter route, SQLite, no paid model, no fallback, no uncertain-POST resend. That one-time authorization is exhausted.
- **Requested model:** `nvidia/nemotron-3.5-super-vl:free`.
- **Route preflight:** `Nvidia | nvidia/nemotron-3.5-super-vl-20261015:free`; structured output/`response_format` support reported; prompt and completion prices were zero; request-price metadata was null. Dispatch set `require_parameters=true`, `allow_fallbacks=false`, and zero maximum prompt/completion/request prices.
- **Research job:** `900c3b8d-e857-4a60-a530-0650fec1fa6e`, isolated SQLite file `evaluation/veda-t112-20261029T205811Z.sqlite3`; final status `completed_with_limitations`.
- **Run artifact:** `evaluation/openrouter-t112-resume-20261029T210403Z.json`. The first browser harness attempt is preserved separately as `evaluation/openrouter-t112-20261029T205811Z.json`; it failed before provider dispatch and the same untouched job was resumed.

## Pipeline stage record

| Stage | Observed result |
|---|---|
| Route preflight | Passed before dispatch. The route was free-designated and structured-output-capable; request-price metadata was unknown. |
| Planning | One real OpenRouter HTTP 200 response; rejected as truncated (`finish_reason=length`); deterministic planning fallback used. |
| Discovery | Real Crossref and OpenAlex metadata GETs completed: 4 queries/provider, Crossref 20 records, OpenAlex 11 records. No provider-query failures. |
| Extraction | 26 deterministic, source-reported claim units extracted from bounded abstracts. No model extraction was used. Several final claim units were visibly cut off by provider excerpt limits. |
| Methodological appraisal | One real HTTP 200 model response; rejected as truncated (`finish_reason=length`). No methodological appraisal was accepted; study-method fields remained unknown. |
| Claim comparison and competing hypotheses | One real HTTP 200 model response; rejected as truncated (`finish_reason=length`). Zero relationships and zero hypothesis pairs persisted. |
| Deterministic citation integrity | Passed 26/26 claim-to-source-to-passage link checks. This validates stored links only, not whether passages support the claims. |
| Synthesis | Not dispatched: serialized model prompt exceeded the configured 24,000-character per-call limit. |
| Semantic citation-support and uncited-claim audit | Not performed. |
| Persistence and browser inspection | A deterministic “Preliminary evidence map” report was persisted. The real browser opened the report, a citation/source record, original abstract passage, and claim inspector. The displayed methodology was explicitly “not assessed.” |

All five required AI operations—planning, appraisal, comparison, synthesis, and semantic support—were recorded as incomplete. `model_name` on the final report is null. The model was contacted three times, but none of its outputs became a Veda research result.

## Provider use and cost evidence

- **Requests:** 3 observed HTTP 200 completion requests, 0 accepted responses, 0 retries, 3 Veda reservations. The runner's final request counter was not finalized by the server; the artifact count is reconciled from the three HTTP 200 observations and three corresponding ledger entries. No additional POST is authorized.
- **Model identity in the usage rows:** `nvidia/nemotron-3.5-super-vl:free` for planning, appraisal, and comparison.
- **Sanitized failure:** all three rows are `provider_output_truncated`; `finish_reason=length` is directly evidenced by adapter classification and was backfilled into the isolated database during the usage-metadata migration. No raw provider response is retained.
- **Usage:** prompt/completion token counts were null for all three calls.
- **Cost:** each call reported and estimated `$0.00`; observed aggregate is `$0.00`. This is not an independently confirmed account billing total. Public route metadata's request-price field was null.
- **Uncertainty:** the finish reason establishes output-length termination. Whether the cause was the response budget, model-specific verbosity, or another interaction is not distinguishable from the sanitized trace. The route metadata does not prove the actual account will never bill for a request.

## Retrieval coverage and evidence limitations

- Candidate ledger: 31 records; 4 duplicate occurrences and 15 insufficient-topic-overlap occurrences excluded; 12 selected.
- Selected sources: 8 had abstract passages; 4 were metadata-only. Every passage-backed selected record was `abstract_only`; no full text was obtained.
- Claims: 26. They include introductions, study aims, interview descriptions, a narrative-review description, and outcome-oriented statements. They are not 26 independent measured results.
- Visible examples of incomplete excerpts include “Through a pilot case study … we gathered valuab”, “Controlled data collection sessions are combined with na”, “Drawing on interviews … model to examine the long-term impacts of AI-ass”, “The findings show that GenAI can enhance individual and”, and “Method: We conducted two semi-s”. Those fragments cannot support a complete claim.
- The record titled “An Empirical Study of Generative AI Adoption in Software Engineering” supplied a passage describing a repository of analyses, raw data, notebooks, and a survey instrument. That repository description is not itself a study result.
- Other selected material has different evidentiary scope: a 12-senior-engineer interview study examines professional identity; a 30-expert-interview study examines sociotechnical effects; and a narrative review summarizes a corpus of 20 sources. These can inform mechanisms, perceptions, or evidence maps, but should not be conflated with controlled measures of developer output or causal productivity effects.
- No accepted model analysis compared study populations, outcome definitions, task settings, tool versions, duration, novelty/learning, quality/rework, or measurement methods. The run therefore did not answer why empirical studies differ.
- The counterevidence query was part of discovery planning, but no counterevidence judgment or contradiction analysis completed. Zero recorded contradictions does not mean the literature is unanimous.

## Browser inspection and reliability judgement

The browser recorded that the report, citation, source metadata, passage, methodology panel, and claim inspector were opened. The UI correctly showed abstract-only access and “not assessed” appraisal. It also exposed deterministic citation-link integrity separately from semantic support. The displayed report therefore provides a usable evidence map, but its claim inventory contains introductory and method text, truncated fragments, and a repository-description passage. Those content-quality problems remain visible and uncorrected in the T-112 historical report.

**Scientific reliability is unverified.** The run is not an AI-powered success, no research-quality score exists, and citation-link success is not semantic support. Offline repairs and regression tests are recorded in ADR-0034 and do not change this run's result. A new live validation requires separate authorization.
