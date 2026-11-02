# Adaptive evidence sufficiency transferability set v3

**Frozen before the planner follow-up:** 2026-11-02

**Baseline commit:** `12b7edd`

**Protocol:** `adaptive-sufficiency-transferability-v3`

The v1 cases were inspected during earlier implementation. The v2 cases were then used to diagnose generic planning misses (source-specific effect questions, intervention association language, and geographic scope), so neither set is reported as an untouched holdout. This v3 set is fixed before changes to the generic question-classification rules below. No source names, publication titles, domains, or URLs are specified.

## Frozen cases

### V3-1 — Hospital safety

> What evidence links changes in hospital shift length to medication errors in adult intensive-care units?

The plan should distinguish association from causal attribution, identify outcome measurement and population/context limits, and avoid treating a broad body-level question as answerable from one publication.

### V3-2 — Informal employment statistics

> What are the annual rates of informal employment in Brazil by age and gender since 2010?

The plan should seek primary statistical series, definitions and denominators, demographic disaggregation, and time-series comparability without automatically demanding causal studies.

### V3-3 — Flood-control investment comparison

> How do municipal flood-control investments compare across lower-income and wealthier neighborhoods in coastal cities?

The plan should preserve comparison groups and geographic context, distinguish investment inputs from measured protection outcomes, and disclose distributional and data limitations.

## Evaluation boundary

- These are planner transferability inputs only. No expected source set is supplied.
- The cases must not be hard-coded in application code, query templates, or source-selection rules.
- Offline classification and evidence-dimension checks are software tests only. They do not validate live discovery, source quality, report accuracy, or scientific quality.
- No live provider requests, model inference, or content acquisition are authorized by this protocol.
- Report all cases, including planning misses and insufficient reports. Do not calculate recall or precision without an independently reviewed source reference set.
