# Adaptive evidence sufficiency transferability set v2

**Frozen before the follow-up implementation:** 2026-11-02

**Baseline commit:** `25b9b90d3ebfeaa4e4077ec4ca1242466be1f7c3`
**Protocol:** `adaptive-sufficiency-transferability-v2`

The prior H1–H3 cases in `adaptive-evidence-sufficiency-holdouts-2026-11-02.md` were inspected during implementation and one wording feature informed a generic question classifier. They are reclassified as diagnostic; no untouched holdout result is claimed for them. This successor set is frozen before the follow-up changes to DOI-less work-version grouping and requirement-level independence accounting. The cases must not be added to production logic or used to select expected publications.

## Frozen cases

### V2-1 — Coastal ecosystem restoration

> What evidence shows whether mangrove restoration changes storm-surge exposure and local fishery outcomes in delta communities?

This case tests causal and explanatory planning across environmental hazard and livelihood outcomes, with a need to distinguish modeled exposure from observed community or fishery outcomes.

### V2-2 — Hospital antimicrobial stewardship

> Which hospital antimicrobial stewardship interventions are associated with lower resistant infections, and what implementation factors explain differences in outcomes?

This case tests comparative and explanatory planning, clinical outcomes, intervention design, implementation context, and risk of conflating institutional guidance with independent clinical evidence.

### V2-3 — Remote drought monitoring

> How well do satellite drought indicators track subsequent crop-yield changes across semi-arid farming regions, and where do the measures disagree?

This case tests comparative, temporal, measurement, geographic, and counterevidence requirements while distinguishing remote-sensing indicators from observed agricultural outcomes.

## Evaluation boundary

- No institutions, publishers, papers, domains, URLs, or expected findings are seeded.
- These questions are evaluation inputs only; production code must remain question-independent.
- Offline planner tests may check that the criteria differ appropriately. They do not establish retrieval recall, publication quality, scientific correctness, or legal sufficiency.
- No live provider request, model inference, or document acquisition is authorized by this set. A live test requires a separate reliable resource preflight.
- A result can be considered sufficient only if the existing source-linked report pipeline records content, material requirement coverage, provenance, completed bounded search, and any question-dependent corroboration. Unknown investigation independence remains unknown.
- Every case, including failures, must be reported. No aggregate score will be calculated without an independently prepared and reviewed reference set.
