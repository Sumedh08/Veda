# ADR-0001: Lightweight persisted research pipeline

- **Status:** Accepted for the MVP implementation; managed database provider remains conditional on a no-cost connection and recovery spike.
- **Date:** 2026-10-28
- **Decision owners:** Veda engineering

## Context

The supplied package calls for durable project/job/evidence state, claim-to-passage traceability, explicit uncertainty, safe user-scoped access, and browser-assisted recovery on sleeping low-cost hosting. The workspace had no existing application or Git history. A bounded primary-source screen is recorded in `docs/research/architecture-evidence.md`; it supports a lightweight workflow but does not establish research quality or benchmark superiority. The completed Deep Research report is not included in the supplied files.

## Provisional decision

Use a small modular monolith: a TypeScript single-page client, a Python API, relational persistence, explicit provider interfaces, and a database-backed state machine whose browser advances one bounded stage at a time. Use deterministic local behavior and provider fixtures for development; configure production AI and authentication only through server-side secrets and a managed-auth JWT verifier. Keep research evidence in relational records with JSON only for versioned scope, checkpoints and provider-specific metadata.

The provisional research path is: clarify/store question and scope → create a bounded plan → discover sources through scholarly APIs → record source access status → extract only passage-linked claims when actual text is available → appraise with unknowns preserved → compare claims while separating scope differences from same-scope contradictions → verify citation IDs and support → produce a limitation-aware report. Without a configured model, show an evidence inventory and unassessed comparison status rather than fabricated hypotheses.

## Alternatives considered

| Option | Assessment | Evidence status |
|---|---|---|
| A. Small typed custom pipeline | Best initial control over ownership, budget, provenance, and checkpoint invariants; requires careful engineering of each stage. | Selected. PaperQA2, OpenScholar and DeepTRACE support separate retrieval, attribution, and audit gates in their tested settings; code fit for Veda is not established. |
| B. Extend a full researcher such as GPT Researcher | Could accelerate discovery and report generation, but reuse depends on current license, architecture, runtime weight, and whether provenance behavior matches requirements. | Not selected until source/license audit; no code execution. |
| C. Reuse components from PaperQA2, OpenScholar, STORM, SciFact | Borrow evidence-gating, bounded retrieval and query-diversity patterns; adopt code only after license, dependency, and portability checks. | Concepts borrowed; no upstream package adopted. |
| D. Graph workflow framework | Adds graph abstractions; this first workflow is bounded and browser-stepped. | Deferred until measured complexity warrants it. |
| E. Single API + static client + external Postgres | Keeps deployment and API boundaries simple while allowing the browser to resume persisted work. | Selected; Neon Free is a conditional non-production candidate. Render Free Postgres expires after 30 days. |

## Consequences

- User state is stored in PostgreSQL for deployment; SQLite supports local setup and deterministic tests. Neon Free is the first non-production deployment candidate because its current docs state no fixed plan expiry and data is not deleted on quota exhaustion. Free has no scheduled backups, no SLA, and compute suspension at quotas; restore/export must be independently tested. Render Free PostgreSQL is rejected for durable user state because it expires after 30 days.
- Development auth is opt-in and isolated from production. Production requests require a verified managed-auth token.
- Search or model outages degrade only the dependent step and must preserve completed evidence.
- Comparison judgments are stored separately from deterministic identity checks. A contradiction requires explicit passage-linked scope fields to agree; scope differences are classified as heterogeneity and missing scope is incomparable. Competing hypotheses require disjoint evidence-linked claims and carry explicit uncertainty. Both remain model-assisted, unverified judgments.
- Browser closure can pause work. Veda will expose resumable status, not promise unattended completion on a sleeping free host.
- Abstract-only evidence remains visibly distinct from full text; absent study details remain unknown.
- OpenAlex full-text retrieval is gated by a supported document-license identifier, an exact host entry in the reviewed terms registry, and a path-allowing `robots.txt` policy; every source redirect repeats both host checks. The transport pins globally reachable IPs and stores bounded passages with provenance. The registry is intentionally empty pending host-specific review, so full-text requests currently fail closed and reports use available metadata/abstract evidence. Robots rules are crawler guidance, not legal authorization; the provider license remains an assertion rather than a legal determination. See ADR-0005 and `docs/research/retrieval-rights-screen-2026-10-29.md`.
- Cost controls limit jobs and calls, but cannot guarantee exactly-once billing after a network crash.

## Revisit when

1. Primary-source review shows a small reusable component materially improves passage grounding without adding unacceptable license, memory, or security risk.
2. Deterministic recovery tests show the custom state machine is more complex or less reliable than a durable graph.
3. Official hosting docs or measured builds invalidate the chosen split deployment.
4. A completed Deep Research report becomes available.

## Verification still required

The one-host local startup/resource and software-runtime baseline is now measured in ADR-0007. Hosted memory/capacity is still unknown. Complete the Neon connection/auth/migration/backup-recovery spike; verify applicable source/API terms; and perform empirical and human research-quality evaluation. The bounded 28-paper/23-repository evidence ledgers are now audited and their reuse decisions are recorded below and in `docs/research/reuse-matrix.md`. The ledgers do not establish exhaustive file-level licensing or independently verify upstream behavior. Current Render, Neon, Supabase, and OpenAI published docs are summaries, not proof of service availability or production readiness.

## 2026-10-29 audit update

The 28-paper and 23-repository bounded audits are now recorded in `docs/research/paper-audit-P01-P14.md`, `paper-audit-P15-P28.md`, `repository-audit-2026-10-29.md`, `papers.csv`, and `repos.csv`. The paper records distinguish direct text, indexed/abstract access, methods/results/limitations, and reported author results from independent evidence. The repository records pin each observed default-branch tree and separate code license metadata from data/model terms; no candidate repository was installed or run.

The source audit does not justify replacing Veda's current core or importing benchmark data. In particular, R01's Apache-2.0 root license conflicts with its MIT `pyproject.toml` declaration; R09's MIT root license conflicts with ISC package metadata; SciFact and ScholarQABench assign different terms to code, annotations, aggregate cases, abstracts, and constituent datasets; DRBench bundled-data terms are unknown; and R23 has scientific-report disclosure and restriction-flowdown terms. P15/P18 also surface non-commercial benchmark data; P23's public repository has no visible license; and P20's underlying web-corpus rights are not cleared. These facts are captured in the candidate-by-candidate matrix at `docs/research/reuse-matrix.md`. Veda therefore keeps its own typed, persisted workflow, borrows only bounded design/evaluation ideas, and does not copy code or datasets from these candidates.

This closes the *bounded literature/repository inventory* gate only. It does not close hosted deployment, model-backed research quality, full upstream license review, service terms, or the required empirical and human evaluations. Commit SHAs identify inspected snapshots; they do not establish the dates of substantive upstream changes.

