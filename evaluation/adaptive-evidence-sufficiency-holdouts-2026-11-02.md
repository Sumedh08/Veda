# Adaptive evidence sufficiency transferability set

**Frozen before implementation:** 2026-11-02  
**Baseline commit:** `26952e8a866980b82d5a9e61322157f5a216dd69`  
**Protocol version:** `adaptive-sufficiency-holdouts-v1`

This set is fixed before changes to sufficiency, evidence-independence, or report status logic. The questions are evaluation inputs only; production code must not contain these strings, their expected answers, organizations, or publications. No target organization or URL is supplied in any question.

The first three cases are diagnostic because preserved Veda runs already exist. The remaining cases are transferability holdouts; they must not be used to tune rules against expected papers. No independently reviewed gold-source set is yet available, so these cases can test workflow behavior and evidence accounting, not retrieval recall or scientific accuracy.

## Diagnostic questions

### D1 — Urban climate adaptation

> How can Indian cities assess differential vulnerability to climate hazards, and which adaptation strategies have empirical or institutional research support?

Evidence needs to represent vulnerability measurement and population/geographic differences, adaptation options, evidence for observed or modeled outcomes, time and hazard applicability, and limits on transfer across cities. This is a broad explanatory and policy question; source coverage should distinguish empirical studies, official data/methodology, and institutional analysis.

Existing artifact: `evaluation/veda-t140-climate-discovery-20261102T084725.sqlite3` (question-only; no claims or passages in the selected report).

### D2 — Food-price policy

> How do government responses influence food-price volatility and household food security in developing economies?

Evidence needs to distinguish policy instruments, price outcomes, household outcomes, countries/time periods, empirical identification versus descriptive or policy analysis, and contrary/null findings. This is a broad causal/comparative policy question; reports from one investigation or shared dataset must not be represented as independent corroboration.

Existing artifacts: the preserved food-policy and UNU-WIDER runs under `evaluation/veda-crawl4ai-food-policy-*` and `evaluation/veda-crawl4ai-unuwider-*`.

### D3 — Offshore wind and grid integration

> What economic, regulatory, and transmission challenges affect offshore wind development in India, and what evidence supports grid-integration strategies?

Evidence needs to separate costs/financing, regulatory conditions, transmission and system integration, and evidence for strategy outcomes. Distinguish observed deployment/outcomes from engineering models and policy recommendations. This is a multi-part, decision-relevant question requiring multiple evidence types and explicit uncertainty.

Existing artifacts: preserved offshore-wind and ORE Catapult runs under `evaluation/veda-*offshore*` and `evaluation/veda-ore-*`.

## Frozen transferability holdouts

### H1 — Water and groundwater

> How do water-pricing and irrigation reforms affect smallholder access and groundwater depletion in semi-arid regions?

Evidence needs to distinguish access and depletion outcomes, policy designs, geographic/population scope, and causal versus observational evidence. Independent investigations, overlapping datasets, policy reviews, and government statistics must be accounted for separately.

### H2 — Maternal health measurement

> What changes have official sources documented in maternal mortality across rural and urban districts in India since 2015, and what evidence supports attributing those changes to health-system interventions?

Evidence needs to distinguish official rates and denominators from intervention effects, time-series comparability, rural/urban and district coverage, and causal attribution. Administrative trends alone cannot establish intervention effects.

### H3 — Ports and export reliability

> How does container-port congestion affect export delivery reliability for small and medium manufacturers in Southeast Asia?

Evidence needs to distinguish congestion measures from delivery outcomes, countries/ports and time periods, primary operational data from surveys/commentary, and whether separate publications reuse the same dataset or investigation.

## Evaluation rules

- Keep D1–D3 as diagnosis cases; do not count their historical metadata-only outcomes as evidence sufficiency success.
- Keep H1–H3 untouched as holdouts for implementation tuning. Do not add their literal text to application code or provider-specific query templates.
- A run is evidence-bearing only when the report links a persisted source to actual permitted passages. Metadata, abstracts, search snippets, and multiple passages from one document do not count as independent investigations.
- Group document versions and duplicate/derivative publications under the same work or investigation when persisted identity evidence supports that relationship. Treat absent investigation/dataset relationships as `unknown`; separate publishers or publication IDs alone do not establish independence.
- Define sufficiency from covered material requirements, source applicability, evidence roles, investigation independence, contrary evidence, unresolved gaps, and completed bounded searches. Do not define it from a fixed source count.
- For each case report the question-specific plan, requirement coverage, discovered/verified/acquired sources, independent content-bearing investigations known versus unknown, contrary evidence, acquisition failures, report decision and reasons, browser inspection, requests/costs, and unmeasured review requirements.
- No live provider request, paid inference, or content fetch is authorized by this evaluation plan. Use saved artifacts and offline deterministic tests unless a separately verified free-resource preflight permits a bounded request.

