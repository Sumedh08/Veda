# ADR-0053: Question-adaptive evidence sufficiency and independence accounting

- **Status:** Accepted for bounded operational use
- **Date:** 2026-11-02
- **Related:** T-141, T-130, T-140, B-010, B-017

## Context

Veda previously exposed a report-level sufficiency label based largely on legacy study/source classifications. That path could omit content-bearing institutional reports and official statistics. It also did not distinguish passage count, document versions, distinct publications, and independent investigations. The application has persisted question scope, research subquestions, source/document versions, passage access classes, claims, citation links, and semantic-audit results that can support a bounded adaptive decision without another database or orchestration framework.

## Decision

Retain the legacy sufficiency record for historical compatibility and compute a separate question-adaptive decision in the existing report verification extension. Derive an explainable question profile, material requirements, evidence dimensions, and criteria from the question, saved scope, and persisted subquestions. Continue to use the existing persisted discovery and semantic-audit coverage rather than introducing a second planner.

Count content-bearing publication groups only after grouping DOI or canonical work identity and cautious DOI-less bibliographic identity. Multiple passages and versions of one work remain one publication group. Independence is a separate reviewed relationship: different works or publishers do not establish it. Investigation, overlapping-dataset, same-investigation, or synthesis classifications require an explicit reviewed basis; workflow records without that basis remain `unknown`.

Broad, high-inference, multi-requirement, and body-of-research questions conditionally require corroboration and counterevidence coverage. The operational floor of two independent investigations applies only to those profiles, is not sufficient on its own, and is not a universal scientific rule. Corroboration must support each material requirement. Planned source-class coverage must also be complete before a strong status is possible. Existing appraisals, full-text needs, claim/passage integrity, bounded search, contradictions, and unmet criteria can prevent a stronger status.

`INSUFFICIENT_EVIDENCE` means no content-bearing evidence or no material claim assessment exists. A content-bearing report with incomplete support remains `PRELIMINARY_EVIDENCE_MAP`. `SUFFICIENT_FOR_SCOPE` is available only when every derived operational gate passes. Every status explicitly states that it is neither peer review nor a scientifically validated universal standard.

The result is serialized alongside the legacy record, included in report Markdown, and presented as the primary status in the existing verification panel. No migration is required. The persisted JSON extension is additive and the UI tolerates older adaptive records that lack the per-requirement evidence array.

## Alternatives considered

- **Fixed source totals:** rejected because counts neither establish relevance nor independent evidence and can drive collection of redundant or irrelevant records.
- **One prestige/relevance score:** rejected because identity, relevance, methodology, evidence strength, access, and independence are separate decisions.
- **Model confidence as sufficiency:** rejected because it is neither independently verified nor a durable evidence standard.
- **New review tables or graph storage:** deferred because the current run can truthfully disclose independence as unknown; no verified review data is presently available to populate such a system.
- **Replace the legacy status:** rejected to preserve historical report compatibility.

## Consequences and limits

- Reports now distinguish content-bearing work groups from passages, versions, and reviewed independent investigations.
- Current workflow data does not independently adjudicate investigations or dataset overlap; those relationships remain unknown unless an explicit reviewed record is supplied to the policy.
- The v3 frozen planner check identified a miss for a question phrased as evidence “links” one exposure to an outcome. Other v3 cases distinguished descriptive time-series work from comparative policy work. These are three planner checks, not a retrieval benchmark.
- A generic relationship-language rule now recognizes inflected linking/connecting/relating terms and tracking/alignment language as association cues. The v4 cases were frozen before the initial repair; one v4 case was inspected to diagnose the remaining “track” cue and therefore the set is diagnostic, not an untouched holdout. All three now request association/design appraisal and corroboration as appropriate. This does not validate retrieval transferability.
- Read-only saved-run replay shows existing report artifacts predate this policy. The observed full-text example is academic; it does not demonstrate cross-source or scientific-quality improvement.
- The policy is operational and heuristic. No independent scientific-quality evaluation, live provider run, or human review was performed for this decision.

## Verification

See `evaluation/RESULTS.md` and the frozen sets `evaluation/adaptive-evidence-sufficiency-transferability-v2-2026-11-02.md`, `evaluation/adaptive-evidence-sufficiency-transferability-v3-2026-11-02.md`, and `evaluation/adaptive-evidence-sufficiency-transferability-v4-2026-11-02.md`. Implementation is in `backend/app/research/evidence_sufficiency.py` and `backend/app/research/workflow.py`; report compatibility is covered by `backend/tests/test_report_document_versions.py` and the adaptive policy fixtures in `backend/tests/test_adaptive_evidence_sufficiency.py`.
