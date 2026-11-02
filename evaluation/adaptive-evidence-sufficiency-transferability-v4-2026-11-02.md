# Adaptive evidence sufficiency transferability set v4

**Frozen before generic relation-language repair:** 2026-11-02

**Baseline commit:** `50a53e2`
**Protocol:** `adaptive-sufficiency-transferability-v4`

V3 exposed that inflected relation verbs can be missed by the deterministic question profiler. V3 remains the pre-repair diagnostic. This small set is frozen before changing the generic relationship-language patterns. It supplies questions only: no organizations, papers, URLs, or expected publications.

## Frozen cases

### V4-1 — Clinical staffing and safety

> How closely are overnight staffing levels connected with medication-error rates in critical-care units?

Check whether the plan distinguishes association from causation, defines the safety outcome, and preserves setting/population limits.

### V4-2 — Urban heat and health

> What evidence relates urban tree-canopy expansion to summer heat-related emergency visits?

Check whether the plan separates a relationship from a causal effect and asks for exposure/outcome measurement and alternative explanations.

### V4-3 — School attendance and air quality

> Do attendance changes track differences in local air-quality alerts across school districts?

Check whether the plan treats the question as comparative/associational and keeps district, time, and measurement differences visible.

## Evaluation boundary

- This is an offline planner transferability check, not a retrieval, source-quality, or scientific-accuracy benchmark.
- Do not add these question strings or their expected classifications to production code.
- Report all cases, including misses; do not compute recall or quality scores without an independently reviewed reference set.
- No live provider calls, inference, document requests, or content acquisition are part of this evaluation.
