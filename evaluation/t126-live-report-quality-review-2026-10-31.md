# T-126 live report quality review

**Review date:** 2026-10-31  
**Live artifact:** `sarvam-glm53-research-20261030T211603703874Z.json`  
**SQLite database:** `veda-sarvam-glm-20261030T211603703874Z.sqlite3`  
**Job:** `67096439-7ea1-4605-9a1d-8dac76e5c9c3`  
**Report:** `ab9eed84-eb89-4d33-a228-2eb34f762936`  
**Provider/model:** Sarvam Token Factory `glm5.3-flash`

This is a substantive spot audit of one live report and its saved source/citation records. It is not a blinded expert evaluation, a complete evidence review, or a scientific-quality score.

## Operational result

The real backend completed planning, Crossref/OpenAlex discovery, passage/claim extraction, source and claim appraisals, comparison, synthesis, deterministic citation integrity, semantic citation review, report persistence, and browser inspection. All 12 strict model outputs were accepted (one planning, eight appraisal, one comparison, one synthesis, one semantic audit). There were no provider retries, uncertain POST resends, paid fallbacks, or provider errors.

The job discovered 40 candidate occurrences (20 each from Crossref and OpenAlex), selected 14 records, persisted 27 claims, 14 citation entries and 8 relationships, and recorded zero hypothesis pairs. Ten source appraisals were model-assessed; four were not assessed. The browser opened the report and a linked citation, displayed the underlying passage and methodological assessment, and downloaded the Markdown export.

All selected evidence was metadata-limited: 11 sources were abstract-only, 3 metadata-only, and none provided full text. The report status is `completed_with_limitations`.

## Findings checked against stored passages and primary records

### The Copilot speed result is narrowly supported

Finding F1 cites the controlled Copilot task and its 55.8% faster completion result. The cited study's primary paper describes 95 professional programmers recruited via Upwork in 2022, implementing one JavaScript HTTP server. Its full paper reports a 95% confidence interval of 21%–89%. The Veda report correctly describes this as one task, but its abstract-only passage does not provide the sample size or interval. Those details should not be inferred from the stored excerpt.

Primary record: [Peng et al., arXiv:2302.06590](https://arxiv.org/abs/2302.06590).

### A finding overstates what the field studies measured

The synthesis says the retrieved field/interview studies examine experience “rather than measured productivity outcomes.” Veda's semantic audit marked finding F5 `partially_supported` and explicitly characterized that wording as an inference. This concern is substantive: the linked field-study abstracts describe task duration, task completion or accuracy, perceived efficiency/productivity, and workload measures. The report should distinguish controlled-session outcomes from perceived productivity in natural work instead of generalizing that these studies did not measure productivity. The audit tool previously checked the author manuscripts and recorded the access limitation: full methods, sample sizes, and overlap between the studies were not inspected in Veda's run.

Relevant author manuscripts: [Brandebusemeyer et al., arXiv:2512.19926](https://arxiv.org/abs/2512.19926), linked to DOI `10.1145/3786583.3786870`; [Brandebusemeyer et al., arXiv:2607.02337](https://arxiv.org/abs/2607.02337), linked to DOI `10.1145/3847122`.

After this run, the deterministic synthesis guard was extended to reject unsupported “rather than measured/measuring” and “without measured/measuring” assertions. A regression now covers the report's problematic wording while allowing it when a linked passage explicitly states the same outcome was not measured. This repair was verified offline; it did not alter the already-persisted T-126 report or prove all semantic errors are caught.

### The report overgeneralizes source access

Qualification Q1 says all sources are abstract-only. That is false in the persisted coverage record: 11 are abstract-only and 3 are metadata-only. The semantic audit marked Q1 `insufficient` and noted that its cited passage could not verify the claim. This qualification should not be reused as written.

### Directly contrasting evidence is missing

Neither of two highly relevant countervailing records appears among the 14 selected sources:

- Cui et al.'s three-company randomized field experiments at Microsoft, Accenture, and an anonymous Fortune 100 company include 4,867 developers and report more completed tasks on average with generative AI, with substantial variation across experiments: [official Management Science record](https://pubsonline.informs.org/doi/10.1287/mnsc.2025.00535).
- Becker et al.'s randomized study of 16 experienced open-source developers over 246 tasks reports 19% longer completion time when early-2025 AI tools were allowed in the studied tasks: [arXiv:2507.09089](https://arxiv.org/abs/2507.09089), [METR study page](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/).

These studies are not directly poolable: populations, tasks, tool versions, treatment settings and outcomes differ. They are nevertheless central counterevidence that should be retrieved and appraised before making a broad cross-setting conclusion. Their omission is a retrieval/coverage defect, not a result that can be repaired by stronger prose.

### Semantic and deterministic checks remain distinct

Deterministic link integrity passed for 27/27 claim-to-source-to-passage links. Separately, the model semantic audit covered 8 report items: F1/F3/F4, Q2 and D1 were marked supported; F2 and F5 partially supported; Q1 insufficient. These are model judgments, not independent verification. The uncited-material scan returned zero flags but its input was truncated; no recall or whole-report completeness claim is justified.

The report stored 8 model-assessed relationships: 3 qualifying, 3 consistent, 1 heterogeneous and 1 incomparable. It stored no competing-hypothesis pair. This is a truthful abstention in the saved output, but whether relevant counterevidence was missed is unresolved because discovery omitted the studies above.

## Usage and cost boundary

The 12 accepted responses reported 33,153 prompt tokens, 9,288 completion tokens and 276 reasoning tokens. Sarvam supplied no provider-reported INR cost. Veda recorded a conservative token-price estimate/reservation of ₹1.0386306 before taxes; the user's ₹25 total ceiling included ₹5 tax/rounding/uncertainty headroom. The run estimate is not the provider's bill. Cumulative conservative reservations across the previous Sarvam attempts and this run equal ₹6.5873388 pre-tax; earlier unknown-cost calls remain estimated from their preserved reservations. The provider does not expose an account-billing reconciliation API through this workflow.

## Overall evaluation

- **Model compatibility:** passed for the actual GLM-5.3 Flash operations used in this workflow.
- **Operational research success:** passed; all required AI stages, persisted report, and browser evidence were observed.
- **Scientific reliability:** not established. F5 and Q1 are materially flawed, important positive and negative field evidence is missing, evidence is entirely abstract/metadata-only, several assessments are model-generated, and no qualified independent reviewers scored the output.

Do not use this single run to claim general causal effects or superiority to another research assistant. Prioritize labeled retrieval-coverage evaluation, full-text access where rights allow, and independent claim/citation review before treating this report as decision-grade evidence.

## T-128 offline retrieval follow-up

The saved candidate ledger confirms the Cui et al. three-field-experiment work was discovered by a focused empirical-study query but lost at the source cap under question-only lexical ranking. Its original-question score was `0.190909`; the exact recorded-query score under the same lexical formula is `0.269231`. T-128 now preserves both features, uses their maximum only for source-cap ordering, and keeps the original-question topical gate. The offline regression verifies the rank change and gate behavior. This change did not mutate or regenerate the T-126 report, and has not been evaluated in another live retrieval run or with human relevance labels. See [ADR-0041](../docs/architecture/ADR-0041-query-aligned-source-cap-ranking.md).
