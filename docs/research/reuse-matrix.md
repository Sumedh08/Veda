# Reuse and design-reference matrix

This is the implementation-facing decision record for the bounded pinned-source audit. The row-level evidence and scope limits are in `docs/research/repos.csv`, `repository-audit-2026-10-29.md`, `papers.csv`, and the two paper audit notes. No candidate repository was installed or executed. A GitHub SPDX value is not treated as a per-file or dataset license grant.

Decision vocabulary: `ADOPT` means a dependency or asset is included in Veda; `BORROW_PATTERN` means Veda independently implements a documented idea; `DESIGN_REFERENCE` means read-only architecture inspiration; `EVALUATION_ONLY` means a possible test design/data source subject to rights review; `DEFER` requires a future measured spike; and `REJECT` means no reuse from the candidate.

## Paper decisions

| Candidate | Decision | Bounded use and gate |
|---|---|---|
| P01 OpenScholar | `BORROW_PATTERN` | Retrieval diversity, reranking and evidence-linked synthesis; no corpus/model reuse and no commercial-domain quality inference. |
| P02 PaperQA2 | `BORROW_PATTERN` | Explicit abstention and bounded evidence gathering; no package adoption or performance transfer from biomedical tasks. |
| P03 STORM | `BORROW_PATTERN` | Diverse query prompts and persisted stages; generated perspectives are not genuine schools of thought. |
| P04 Co-STORM | `DESIGN_REFERENCE` | User steering and visible research structure; preference study is small and not a factuality measure. |
| P05 Mind2Report | `BORROW_PATTERN` | Clarified intent and revisable research outline; author-reported results are not independent evidence. |
| P06 Open Deep Research | `DESIGN_REFERENCE` | Workflow catalog only; repository is archived and no source was run. |
| P07 Agent Laboratory | `DESIGN_REFERENCE` | Human checkpoints only; autonomous code execution and unclear phase metrics are not transferred. |
| P08 The AI Scientist | `REJECT` | No autonomous experiment execution/code generation in Veda; use only as a warning about unsafe execution and hallucinated results. |
| P09 DeepTRACE | `BORROW_PATTERN` | Separate statement/citation-support metrics; validate any judge against human labels. Artifact URL/license remains unknown. |
| P10 ALCE | `EVALUATION_ONLY` | Citation precision/recall metric ideas; NLI agreement is imperfect and benchmark domains are not commercial reports. |
| P11 SciFact | `EVALUATION_ONLY` | Support/refute/insufficient classes; repository data has separate CC BY and ODC-By terms (see R06), so no corpus import. |
| P12 RARR | `BORROW_PATTERN` | Post-draft audit/repair concept while preserving the original and its evidence; no “hallucinate evidence” mode. |
| P13 ACM credibility survey | `DESIGN_REFERENCE` | Use named evidence-risk dimensions, not a universal truth/credibility score; publisher version was inaccessible. |
| P14 Conflicting Needles | `EVALUATION_ONLY` | Repetition/order stress-test design; synthetic conflict behavior is not a real-world error rate. |
| P15 DEER | `EVALUATION_ONLY` | Expert-report coverage rubric idea; custom dataset license restricts commercial use. |
| P16 DRBench | `EVALUATION_ONLY` | Heterogeneous evidence and distractor evaluation; synthetic enterprise tasks do not establish live-company performance. |
| P17 DeepResearch Bench | `EVALUATION_ONLY` | Report criteria and citation support; dataset license was not surfaced, so no data import. |
| P18 DeepResearch Bench II | `EVALUATION_ONLY` | Granular binary rubric design; two task sources are CC BY-NC, so the complete dataset is not cleared for commercial use. |
| P19 DR³-Eval | `EVALUATION_ONLY` | Static evidence-sandbox concept only; full paper, artifact, and license remain unavailable. |
| P20 BrowseComp-Plus | `EVALUATION_ONLY` | Fixed-corpus retrieval evaluation only; rights in the separately hosted web corpus were not audited. |
| P21 LiveDRBench | `EVALUATION_ONLY` | Intermediate claim-discovery metric; data has CDLA v2 terms and its task count discrepancy remains unexplained. |
| P22 ResearchRubrics | `EVALUATION_ONLY` | Weighted acceptance criteria; human/LLM agreement and length bias require local calibration. |
| P23 ResearcherBench | `REJECT` | No code or data reuse until a license grant is established. |
| P24 Deep Research: A Systematic Survey | `DESIGN_REFERENCE` | Taxonomy and bibliography only; follow citations to primary sources. |
| P25 Deep Research Agents survey | `DESIGN_REFERENCE` | Architecture vocabulary only; does not establish a need for multi-agent execution. |
| P26 PRISMA 2020 | `BORROW_PATTERN` | Transparent reporting of search/screening/exclusion flow; not a conduct guide or quality score. |
| P27 GRADE Handbook | `DESIGN_REFERENCE` | Risk-of-bias/indirectness vocabulary only; healthcare grading is not validated for business/economics. Handbook is being superseded. |
| P28 OpenAI Deep Research System Card | `BORROW_PATTERN` | Treat retrieved content as untrusted and constrain tool authority; vendor report is not independent evaluation. |

No benchmark rows or third-party report assets are currently `ADOPT`ed. Evaluation designs may be implemented independently; benchmark data requires per-artifact license, privacy, contamination and domain review first.

| Candidate | Decision | What Veda borrows | Remaining gate |
|---|---|---|---|
| R01 GPT Researcher | `DESIGN_REFERENCE` | Supplied-source prompting; not a citation-support gate. | Root LICENSE/SPDX say Apache-2.0 while `pyproject.toml` says MIT; do not copy code until resolved. |
| R02 PaperQA2 | `DESIGN_REFERENCE` | Bounded evidence gathering, timeout/source limits, abstention. | Apache-2.0 root scope observed; optional parser/model/vector integrations and nested package/data terms are not cleared. No runtime or Veda quality comparison. |
| R03 Ai2 ScholarQA | `DESIGN_REFERENCE` | Citation-metadata validation fixture pattern. | No root manifest; API/UI package and nested terms remain unknown. |
| R04 OpenScholar | `DESIGN_REFERENCE` | Separate retrieval, attribution and feedback gates; passage reranking idea. | Apache-2.0 code does not establish model-weight/corpus rights; heavyweight dependencies and transfer not tested. |
| R05 STORM / Co-STORM | `DESIGN_REFERENCE` | Diverse search questions and user steering; viewpoints only guide retrieval. | MIT root scope observed; embedding/vector footprint unmeasured and no tests tree found. |
| R06 SciFact | `EVALUATION_ONLY` | Support/refute/insufficient classes and evidence-link test ideas. | Code Apache-2.0, annotations CC BY 4.0, corpus abstracts ODC-By 1.0; do not copy benchmark data without artifact-specific attribution/terms. Legacy dependencies untested. |
| R07 LangChain Open Deep Research | `DESIGN_REFERENCE` | Orchestration patterns only. | Archived; root tests are evaluations, not a unit suite; broad provider stack adds maintenance. |
| R08 LangChain Local Deep Researcher | `DESIGN_REFERENCE` | Local-first graph/state concepts only. | No test paths found; provider/local-model setup and graph dependency not exercised. |
| R09 dzhng/deep-research | `DESIGN_REFERENCE` | Iterative search loop concept. | Root LICENSE/SPDX say MIT while `package.json` says ISC; no code copy until resolved. Root test script is a placeholder. |
| R10 Jina node-DeepResearch | `DESIGN_REFERENCE` | Bounded research-loop and test organization ideas. | Apache-2.0 root scope observed; no declared Node engine and integrations not executed. |
| R11 LearningCircuit local-deep-research | `DESIGN_REFERENCE` | No direct dependency; possible isolated ideas after review. | MIT root scope observed, but dual runtime and broad provider/browser/embedding surface do not fit the compact core. |
| R12 GPT Researcher MCP | `DESIGN_REFERENCE` | Protocol wrapper tests are not evidence-quality tests. | MIT root scope observed; no need to adopt a separate tool server. |
| R13 ASReview | `DESIGN_REFERENCE` | Human screening/active-learning ideas for a future inclusion queue. | Apache-2.0 root scope observed; large review UI is outside the current product and screening is not claim verification. |
| R14 Docling | `DEFER` | Reconsider only for a measured document-ingestion spike. | MIT package/root manifests observed, but selected parser source path did not resolve; resource, model, output-locator and nested asset terms remain unverified. |
| R15 DeepEval | `EVALUATION_ONLY` | Candidate metric taxonomy only. | Apache-2.0 root scope observed; selected metric implementation not read/run and LLM-judge scores require calibration. |
| R16 Ragas | `EVALUATION_ONLY` | Candidate faithfulness metric taxonomy only. | Apache-2.0 root scope observed; broad dependencies and metric validity for economics not tested. |
| R17 Microsoft GraphRAG | `DESIGN_REFERENCE` | Graph extraction as a possible later research line. | MIT root scope observed; pinned README describes maintenance mode, research-demo status and expense; multi-package graph stack is not adopted. |
| R18 Literature review tool catalog | `DESIGN_REFERENCE` | Discovery pointers only. | CC0 applies to catalog, not separately linked projects or assets. |
| R19 Awesome Auto Research | `DESIGN_REFERENCE` | Discovery pointers only. | Root MIT does not clear linked repositories or assets. |
| R20 ScholarQABench | `EVALUATION_ONLY` | Benchmark design reference, not imported gold cases. | MIT code; ODC-By aggregate cases/sample answers/data; constituent datasets retain their own terms. No benchmark run. |
| R21 DRBench | `EVALUATION_ONLY` | Report-scoring design reference. | Apache-2.0 code; bundled task-data terms are unknown. No benchmark run or data import. |
| R22 Mind2Report | `DESIGN_REFERENCE` | Intent clarification, question framing and report-workflow concepts. | Apache-2.0 root scope observed; author-reported results are not independent; no code/runtime transfer test. |
| R23 AI Scientist | `REJECT` | None. | Custom license includes scientific-report disclosure and contractual flowdown restrictions; unrelated research-generation scope. No code or assets reused. |
| Full agent/graph frameworks | `DEFER` | No package adopted; Veda keeps its explicit persisted stages and lease controls. | Reopen only if a reproducible spike demonstrates lower operational complexity without weakening ownership, provenance, budget or recovery invariants. |
| Render Free Postgres | `REJECT for durable state` | None. | Official docs state fixed 30-day expiration and no backups; use only disposable previews. |
| Neon Free Postgres | `CONDITIONAL DEPLOYMENT CANDIDATE` | Standard PostgreSQL schema preserves portability. | No account, connection, auth, backup or restore test exists; free tier has no scheduled backups/SLA and quota suspension. It is not a production claim. |

## Decision

Veda implements the domain and evidence gates itself as a compact Python state machine. It does not adopt a full research agent or graph runtime, and it imports no candidate benchmark corpus. The pinned-source audit found license conflicts in R01 and R09, artifact-specific dataset terms in R06 and R20, unknown bundled data terms in R21, and extra report restrictions in R23. These findings strengthen the no-copy/no-data-import boundary. This is an engineering decision based on bounded source review, not a measured retrieval-quality win. Any future upstream code requires a pinned commit, scoped license/security review, dependency review, and local evidence-link fixtures before adoption.

