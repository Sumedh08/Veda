# ADR-0021: Treat user scope as untrusted prompt data

- **Status:** Accepted
- **Date:** 2026-10-29
- **Decision owners:** Veda engineering

## Context

T-65 now carries a user-authored project brief into each research run's versioned scope. That scope is sent to the model-assisted appraiser, claim comparer, and report synthesizer. These calls already treated retrieved passages as untrusted, but did not consistently say that the research question and user-supplied scope are also untrusted data. A brief could contain instruction-like text that attempts to override evidence, uncertainty, citation, or causality constraints.

## Decision

In every structured call that receives the question or scope, the system instructions explicitly say that these values are user-provided, untrusted data used only to define relevance or request boundaries; they cannot override the system's task and evidence rules. Continue to serialize user data separately from system instructions. Preserve the existing strict output schemas, fixed query candidates, required direct/counterevidence selections, identifier allow-lists, passage-link checks, and deterministic fallbacks as independent controls.

The planner already marks the question, scope, candidate queries, and existing subquestions as untrusted. The appraisal, comparison, and synthesis prompts now state the same boundary. The semantic report audit receives a constrained report/evidence payload rather than the original scope, and already treats the report and passages as untrusted.

## Alternatives considered

- **Rely on the JSON boundary alone:** rejected because serialization prevents string concatenation into the system prompt but does not stop a model from interpreting a user value as an instruction.
- **Strip instruction-like phrases from user context:** rejected because lexical filtering is unreliable, can corrupt legitimate context, and is not a substitute for an explicit instruction hierarchy.
- **Drop project context from analytical prompts:** rejected because scope is needed to appraise relevance and preserve decision boundaries.

## Consequences and limits

- User context remains available to constrain analysis but is never represented as a trusted instruction source.
- Prompt wording reduces risk but cannot prove resistance to prompt injection or ensure model compliance.
- Strict structured validation and evidence-link checks remain necessary even when the prompt follows the boundary.
- Tests use a fixture provider and assert serialized input/system separation; no live model robustness or scientific quality is claimed.

## Verification

The planner regression passes an adversarial project brief through the saved scope and checks it appears only in serialized user data, while direct evidence and counterevidence requirements remain enforced. The workflow injection test passes hostile retrieved text and a hostile saved context through appraisal, comparison, synthesis, and semantic audit fixtures, then checks the scope warning for every call that receives scope. The semantic audit does not receive the original scope. No live provider request is made.
