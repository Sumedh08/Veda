# T-119 one-question live validation review — 2026-10-30

## Outcome

The authorized question was **“Does generative AI improve software developer productivity, and why do empirical studies sometimes report different findings?”** The live validation **failed operationally as an AI research run**. Veda made four OpenRouter inference requests, accepted zero structured AI outputs, and saved a deterministic preliminary evidence map with limitations. The map was inspected in the local browser; it is not an AI-generated report and does not establish scientific reliability.

The root `.env` credential was present. Presence-only checks returned true for the T-119 runner settings path and a nested backend subprocess; the credential was never printed, copied into an artifact, or modified. The current shell itself did not have the variable exported. Public route preflight passed for `xingchen-agi/xing4.0-29b-a4b:free` at the Phala endpoint. Prompt/completion prices were zero, request-price metadata was null, and the required structured-output and reasoning parameters were listed. The route request retained `require_parameters=true`, `allow_fallbacks=false`, and zero prompt/completion/request price ceilings. This does not guarantee account-level billing.

## Runner incident before the research job

The first runner invocation wrote `openrouter-research-validation-20261030T115226647771Z.json` and stopped before job creation. The browser harness referenced `runId` inside `page.evaluate` without passing it as an argument. It raised `ReferenceError`; provider request count, jobs, and usage rows were all zero. The harness now passes `runId` explicitly. This pre-dispatch harness failure consumed no inference request and is separate from the one research job below.

## Live job and exact stage results

The single job used isolated SQLite and the real local API/browser path. It completed with status `completed_with_limitations`, id `693601f0-4364-4d7e-8a56-8a366934c32a`. Its result is `openrouter-research-validation-20261030T115353919544Z.json`; its isolated database is `veda-research-20261030T115353919544Z.sqlite3`.

| Stage | Result |
|---|---|
| Planning | The model operation `veda_research_plan_selection_v1` returned HTTP 429 and was recorded as `provider_rate_limited`. A deterministic bounded plan was used; planning was not AI-assisted success. |
| Scholarly discovery | Completed with Crossref and OpenAlex: four queries each; 20 and 11 provider results respectively; 31 candidate occurrences, 11 selected sources, 4 duplicate exclusions, 15 topic-overlap exclusions, and 1 repository-description exclusion. No provider query failures were recorded. |
| Claim extraction | Deterministic extraction persisted 25 exact source-reported statements with source/passage links. It was not a model operation. Seven statements ended mid-sentence because the provider truncation flag had been lost during versioned metadata lookup; see the offline repair below. The artifact's `claim_extraction=false` value was also undercounted by the harness, which checked `passage_ids` but the API returns singular `passage_id`; that accounting check is fixed. |
| Methodological appraisal | The model operation `veda_appraisal_batch_v2` returned HTTP 429, `provider_rate_limited`. No structured appraisal was accepted; methodological fields remain `unknown` / `not_assessed`. |
| Claim comparison and contradictions | The model operation `veda_comparison_batch_v1` returned HTTP 429, `provider_rate_limited`. No claim relationships or competing hypotheses were persisted. |
| Deterministic citation integrity | Passed: 25 of 25 stored claim links resolved to their source and passage. This validates links, not whether the cited text supports a synthesized conclusion. |
| Semantic citation support | Not dispatched. No semantic support result exists. |
| Synthesis | `veda_report_draft_v2` returned HTTP 200 but ended with `finish_reason=length`. The provider reported 7,401 prompt tokens, 2,200 completion tokens, and 0 reasoning tokens; 2,200 matched the requested completion cap. Veda rejected the truncated response. No model synthesis was accepted. |
| Persistence | A deterministic `Preliminary evidence map` was saved with status `completed_with_limitations`; it contains 11 citation entries. `model_name` is null. This fallback is not AI success. |
| Browser inspection | Passed for the fallback report: the report opened, a citation opened, an original abstract passage was visible, and the methodology inspector showed unknown/not-assessed fields. This does not count as inspection of an AI-generated report. |

The runner recorded **4 provider request attempts / 4 usage rows**, below the six-request hard cap. It recorded zero rate-limit retries and zero uncertain POST resends. All usage rows used the exact configured `:free` model identity. The three HTTP 429 rows have no token or cost metadata, leaving **3 costs unknown**. The truncated synthesis row reported $0.00. No nonzero reported cost was recorded, but the incomplete metadata and null request-price mean the account-level total is unconfirmed.

## Evidence and quality limits

The selected records were 8 abstract-only and 3 metadata-only; none had full-text evidence. The fallback's report verification passed deterministic source/passage link integrity for all 25 claims, while `semantic_support_check` was `not_performed`. No appraisal, comparison, alternative-hypothesis analysis, or AI synthesis was accepted. The report explicitly says no passage-linked relationship or competing-explanation record was retained and that this does not show the literature is unanimous.

The report included seven incomplete abstract tails, including text ending “we gathered valuab” and “combined with na”. These are not valid complete claims. In the stored provider metadata, Crossref/OpenAlex correctly carried `abstract_excerpt_truncated=true` under `provider_metadata.extensions`; extraction had checked only the top-level field. The independent regression now exercises this exact normalized metadata path and confirms that an incomplete tail is not persisted. The historical run artifact is retained unchanged so the failure remains auditable.

The sanitized usage ledger classifies the three HTTP 429s as `provider_rate_limited`, but does not preserve response bodies or identify whether account limits, endpoint capacity, or another provider-side condition caused them. Do not infer that cause. The preflight's `status=0` is also not interpreted. Scientific accuracy remains unverified.

## Offline repairs and verification

- Passed `runId` into the browser page evaluation and corrected stage coverage to accept the API's singular `passage_id`.
- Added `_abstract_excerpt_truncation_flag` to read either top-level or versioned-extension provenance, and excluded incomplete tails during extraction.
- Replaced report-draft v2 with strict, bounded `veda_report_draft_v3`; reduced field/list limits and set synthesis request output to the existing standard-profile maximum of 2,600 tokens. This is a bounded compatibility improvement, not a guarantee the route will complete output.
- Focused backend pipeline/workflow/citation/prompt/depth suite: **30 passed**, one existing Starlette/httpx deprecation warning.
- Ruff check passed. Ruff format passed after formatting `workflow.py` and `test_workflow.py`.
- Frontend production build passed. Playwright `--list` discovered the one T-119 test; it was not rerun against the provider.

No inference request was sent after this job. The one-time live authorization is spent. The 429 cause and v3 live compatibility remain unverified; another live run requires separate authorization.
