# ADR-0037: Bound synthesis output after a live completion-cap failure

- **Status:** Accepted for local implementation; live behavior unverified
- **Date:** 2026-10-30
- **Related:** ADR-0034, ADR-0035, T-119

## Context

In the single authorized T-119 run, the pinned free route returned HTTP 200 for synthesis but the response ended with `finish_reason=length`. The provider reported exactly 2,200 completion tokens, matching Veda's configured synthesis cap; it reported 7,401 prompt tokens and zero reasoning tokens. The result could not be accepted as a complete structured report. The route's context window was not the apparent limit. Separately, planning, appraisal, and comparison each received HTTP 429 and were recorded as `provider_rate_limited`; the saved evidence does not identify the underlying account, provider-capacity, or endpoint cause.

## Decision

Introduce `veda_report_draft_v3` with shorter field limits and smaller maximum arrays, and request up to 2,600 completion tokens, the existing standard-depth per-call ceiling. This combines a smaller valid response shape with the available bounded output budget; it does not relax JSON or evidence validation. Keep the six-call cap, zero-price request guard, disabled paid fallback, and no-resend policy. Do not retry the live route under the spent authorization.

## Consequences and verification

Focused deterministic pipeline, citation, injection, depth-budget, and schema-bound tests passed; frontend build and the T-119 browser test discovery passed. No live call has tested the v3 schema. The 429 cause, account-level billing, model quality, and completion reliability remain unverified. Another live validation requires separate authorization.
