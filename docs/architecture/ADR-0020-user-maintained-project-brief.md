# ADR-0020: User-maintained project brief seeds each research run

- **Status:** Accepted
- **Date:** 2026-10-29
- **Decision owners:** Veda engineering

## Context

The owner-scoped `Project.description` field was already persistent, editable, included in project export, and bounded to 4,000 characters. The new-run and follow-up composers did not carry it into their decision context, so researchers had to re-enter context and the UI gave no clear distinction between a reusable project brief and evidence collected for a particular run. The master mandate calls for persistent context across related research.

## Decision

Use the existing project description as a **user-authored project brief**. Label it that way in create/edit flows, prefill it into the editable decision-context field for new and linked follow-up runs, and submit the edited text as that run's `ResearchJob.scope.context` snapshot. The project's brief remains unchanged when a researcher edits the run-specific copy. An empty or legacy empty description continues to produce an empty optional context.

Keep the project brief, each run's decision-context snapshot, parent-run claims, and newly retrieved child-run evidence as separate records. Parent evidence may frame a follow-up, but is not thereby made evidence or citations for the child. Do not call the user-authored brief a generated summary, verified fact, or source. Existing owner checks, the 4,000-character field limits, and export/archive behavior remain the governing controls.

No database migration or automatic model summarization is required. Reusing the existing field avoids storing a second potentially divergent project summary and does not add a model call or provider cost.

## Alternatives considered

- **Add a generated project summary column:** rejected because it duplicates existing project context and requires provenance, refresh, and factual verification rules that the local product does not yet provide.
- **Automatically synthesize context from conversation history:** rejected because it could silently promote unverified conversation or evidence into durable user intent.
- **Keep the brief outside run scope:** rejected because the plan would not show the actual context used for that run and a later project edit could obscure the historical input.

## Consequences and limits

- Users can review and change the inherited brief for every run; the saved `ResearchJob.scope` is the historical snapshot.
- Updating the project brief affects subsequent runs only and does not mutate existing job scopes.
- The content remains user-authored and is not independently validated. Its presence does not establish a research fact or improve evidence quality by itself.
- The behavior is verified locally through API and fixture-backed browser journeys. Hosted persistence and PostgreSQL compatibility remain part of deployment verification.

## Verification

The API test verifies first-run context persistence, a later project-brief edit, an independent subsequent snapshot, preservation of the earlier snapshot, and denial of another user's job read. Browser coverage verifies project creation, prefill, run-specific editing and saved-plan display; follow-up prefill and saved-plan display; and project-brief composer accessibility/mobile layout. No provider call or migration is involved.
