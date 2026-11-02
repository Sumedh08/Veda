# ADR-0019: Bounded model-assisted research planning

- **Status:** Accepted for the local implementation boundary
- **Date:** 2026-10-29
- **Decision owners:** Veda engineering

## Context

The saved v3 plan was fully deterministic. It preserved decision scope, counterevidence, uncertainty and resource limits, but it could not prioritize query candidates based on the user's intent or add focused analytical questions. The master mandate calls for analytical planning. An unrestricted model-authored search plan would make it harder to enforce scope, reproducibility, query caps and prompt-injection boundaries.

## Decision

Use the existing structured-provider path once during planning, under its existing daily, per-user, per-job and depth quotas, request cache, uncertain-outcome handling and provider configuration gates. The model receives a finite candidate list produced by the deterministic v3 planner. It may return candidate indices and at most two question-only analytical subquestions. It cannot author retrieval query strings or edit the explicit scope, fixed analytical lenses, stopping criteria or resource limits.

Persist the outcome as a strict v4 plan with explicit planning mode and provider/model/fallback provenance. Preserve v2/v3 readers and stable plan fields. When a provider is disabled, unavailable, blocked by budget/depth/quota, uncertain, or returns a malformed or semantically invalid selection, keep the deterministic v3 plan and disclose the fallback reason. The browser displays the persisted method and provider/model when known.

## Alternatives considered

- **Keep deterministic-only planning:** safest, but does not meet the requested model-assisted intent analysis.
- **Allow arbitrary model-authored queries and scope:** more flexible, but increases prompt-injection, scope-drift and reproducibility risk; rejected.
- **Add a graph/agent framework:** unnecessary for one bounded structured call and would add state/dependency complexity without improving the safety boundary.

## Consequences and limits

- Query text always comes from the deterministic candidate set; the model can only choose order/subset within depth caps.
- User-supplied scope, direct-evidence and counterevidence searches, fixed analysis prompts and stopping criteria remain immutable.
- Added subquestions are displayed as model-generated text but are not automatically executed as searches.
- A structured response that passes schema and invariants is not necessarily a high-quality research plan. No live model planning call or scientific-quality result is claimed by the local tests.
- No database migration is required; checkpoint validation now reads plan v4 while preserving v2/v3.

## Verification

`backend/tests/test_model_planning.py` covers successful bounded selection, fixed-candidate-only output, prompt-injection scope preservation, quota and provider/schema fallback, invalid indices, uncertain outcomes, and durable replay across planning recovery. `test_depth_profiles.py` and `test_document_versions.py` cover disabled-provider API behavior, caps, v4 persistence and legacy plan reads. The browser suite checks both deterministic-fallback and model-assisted provenance labels. Tests use local fixtures; they do not call OpenRouter.
