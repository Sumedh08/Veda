# OpenRouter ten-case live research run

Test date: 2026-10-29. Status: **incomplete; all ten research jobs failed before appraisal was persisted**.

## Configuration and provider usage

- Route: `openrouter/free`; returned model IDs: `nvidia/nemotron-3-ultra-550b-a55b:free`, `openrouter/free`.
- Local isolated SQLite and Playwright UI; OpenAI calls: 0; paid fallback: disabled; Veda retries: 0.
- Persisted provider usage records: 20 (2 accepted, 18 failed).
- Known response costs: 2 at $0.00 and 0 nonzero; cost is unknown for 18. The known-cost subtotal is $0.00; this is **not** a confirmed total bill.
- Two structured planning responses were accepted from `nvidia/nemotron-3-ultra-550b-a55b:free` at reported $0.00. Eighteen other provider records lack confirmed cost/model response fields. No positive reported cost was observed; Veda data cannot confirm total provider billing.

## Research work completed

- Ten detailed research questions started; 140 selected scholarly records (Crossref: 137, OpenAlex: 3) from 203 candidates.
- 141 extracted claims were persisted. No methodological appraisals were persisted.
- Offline gate replay: 38 old candidates pass on title alone; 112 previously selected records fail using their saved title and abstract. This is not a human-reviewed retrieval score.
- Planning and real Crossref/OpenAlex discovery ran. Extraction ran for all ten cases. Appraisal was attempted, but all ten jobs ended `terminal_failure` at the appraisal stage.
- Reports persisted: 0; cited claims: 0; citation integrity checks: 0; semantic support checks: 0; contradiction/hypothesis analyses: 0; final syntheses: 0.
- The browser created and advanced jobs. This batch did not inspect report pages or citations because no report existed and the test stopped before report-history inspection.

## Quality and reliability observations

- The application did use the returned free model for two structured planning selections; their exact returned model was nvidia/nemotron-3-ultra-550b-a55b:free. The other eight plans fell back deterministically after uncertain provider outcomes.
- All ten appraisal operations failed with the generic backend error model_call_uncertain. The persisted usage records do not retain enough provider response detail to identify a more specific cause. Requests were not automatically resent.
- Crossref/OpenAlex discovery was live, but selected records showed poor topical relevance in several cases. Examples and full candidate/source records remain in the raw runtime snapshot; selection therefore does not establish evidence relevance.
- The planned counterevidence searches were persisted, but comparison of opposing results was not reached. No claim support, methodological quality, scientific accuracy, or outcome-effect conclusion can be assessed from this run.
- Offline replay of the new conservative topic-overlap gate against the old candidate snapshot passes 38 candidates on title alone; 112 of the 140 previously selected records fail even when their saved abstract excerpt is included. This is a heuristic regression signal, not a reviewed precision/recall score.
- The browser UI created and advanced the real jobs, but this run did not inspect generated reports or citations because none were saved.

## Per-case coverage

| Case | Status | Candidates | Selected | Claims | Plan |
|---|---:|---:|---:|---:|---|
| startup-hr-screening | terminal_failure | 20 | 14 | 22 | deterministic_fallback |
| startup-hr-onboarding | terminal_failure | 20 | 14 | 7 | deterministic_fallback |
| support-agent-assist | terminal_failure | 21 | 14 | 13 | deterministic_fallback |
| developer-copilot | terminal_failure | 22 | 14 | 17 | model_assisted_selection |
| sales-personalization | terminal_failure | 20 | 14 | 2 | deterministic_fallback |
| marketing-content | terminal_failure | 20 | 14 | 16 | deterministic_fallback |
| accounts-payable | terminal_failure | 20 | 14 | 6 | model_assisted_selection |
| knowledge-assistant | terminal_failure | 20 | 14 | 16 | deterministic_fallback |
| analyst-copilot | terminal_failure | 20 | 14 | 31 | deterministic_fallback |
| organization-wide-rollout | terminal_failure | 20 | 14 | 11 | deterministic_fallback |

## Limitations

- Cost is known only for successful responses; unknown costs must not be interpreted as zero.
- The runtime snapshot was captured shortly before child-process shutdown and shows one job as active, while the final browser artifact records all ten as terminal failures. The final browser artifact is the terminal-status source; the snapshot is used for persisted research material counts.
- A raw provider transport attempt counter was not retained; 20 persisted Veda provider usage entries are used as the call count, with zero configured retries.
- No reports were produced, so report-level evaluation remains unperformed.

Raw browser result and runtime snapshot are retained next to this report. This record contains no credential.
