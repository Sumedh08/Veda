# Human review rubric for research outputs

Use this rubric only after inspecting the underlying source, cited passage, scope, and report. It is an evaluation aid, not a ground-truth generator. Reviewers should score independently before reconciliation and record disagreements.

Score each dimension from **0 to 3**:

- **0 — absent or materially wrong:** a core requirement is missing, contradicted, or unsupported.
- **1 — weak:** partial treatment; important omissions or overstatement remain.
- **2 — adequate:** mostly supported and appropriately scoped, with bounded shortcomings.
- **3 — strong:** clear, auditable, appropriately qualified, and robust to the identified concern.
- **N/A — not assessable:** explain why; do not convert N/A into zero or silently omit it from a reported denominator.

## Dimensions

1. **Question and scope fit:** population, intervention/exposure, comparator, outcome, geography, and time horizon match the question.
2. **Source provenance and access:** source identity and access class are correct; abstract-only or unavailable material is not presented as full-text review.
3. **Claim-to-passage support:** sampled material claims resolve to the correct stored source and passage; the passage substantively supports the claim.
4. **Study-design interpretation:** experimental, quasi-experimental, observational, forecast, and commentary evidence are distinguished; causal language matches the design.
5. **Outcome and denominator:** task speed, accepted output, quality, worker time, firm productivity, financial return, and labor effects are not conflated.
6. **Uncertainty and limitations:** effect uncertainty, implementation costs, confounding, sample selection, attrition, and missing information are represented when the source allows assessment.
7. **Counterevidence and heterogeneity:** relevant null/negative findings and genuine differences by population, sector, geography, task, or horizon are surfaced; disagreement is not fabricated.
8. **Conclusion calibration:** conclusions do not exceed evidence coverage and identify when the evidence cannot answer company-specific ROI.
9. **Usefulness and traceability:** report structure supports a decision; key factual statements can be followed through citation to passage and source.

## Review protocol

- Record reviewer role/area of expertise, date, case ID, run ID, provider/model/version, and any conflicts. Do not put reviewer personal information in public fixtures.
- For every material citation, inspect source metadata and the linked passage. Record wrong-source, missing-passage, unsupported, or uncited-material-claim issues separately from scores.
- For causal or ROI questions, require reviewers to assess identification, counterfactual, denominator, and full cost categories; citation presence alone is not a pass.
- Keep `draft`, `human_reviewed`, and `validated` case states distinct. A case becomes `validated` only through the repository's defined human review process; this rubric does not decide correctness automatically.
- Do not aggregate a small, selected sample into a general Veda accuracy rate. Publish case selection, denominator, missing reviews, adjudication method, and uncertainty with any summary.

## Review record shape

Store each review separately from the question registry using `../schemas/annotation-record.schema.json`; one record represents one reviewer and one immutable case-run. Record run manifest SHA-256, case/run identifiers, provider/model/version, source-set version, observed cost/tokens (unknown is not zero), reviewer pseudonym/role/expertise/conflicts, all nine rubric dimensions, per-score rationales, N/A explanations, citation and uncited-claim findings, scope/omission notes, and adjudication status. Never store direct reviewer identity in public fixtures or add a model-generated answer as a gold answer without independent source review.

The schema-only example under `../annotations/` is not a review and must never enter a score denominator. Structural validation does not authenticate reviewer identity, inspect source passages, or establish correctness. The seven-case sampling and denominator rules are frozen in `../benchmark-plan.json`; preserve all independent records and any later adjudication separately.
