# Repository audit: pinned source and scope review

**Access date:** 2026-10-29. **Scope:** all R01–R23 entries in docs/research/repos.csv. This is a bounded repository evidence audit, not an installation, security review, or legal opinion.

## Method and evidence limits

- Read GitHub repository metadata for default branch, archive state and GitHub-reported SPDX identifier; queried the default-branch commit and recursive tree; inspected selected root README, license, root manifests, and the selected source/test files listed below. The pinned-tree links resolve all listed paths at the observed commit SHA.
- No repositories were cloned, installed, built, or executed. Test and CI statements report paths found in the pinned tree, not passing results. A tests/ directory nested under src/, api/, training/, packages/, or a UI subproject is identified as nested; root tests/ content is not assumed to be unit coverage.
- GitHub SPDX is repository metadata, not a file-level license determination. I checked root LICENSE plus relevant manifest metadata and explicit dataset README/license notices where noted. I did not audit every file header, dependency license, model weight, paper, corpus, or third-party asset. Marked conflicts and unknown scope remain unresolved.
- GitHub commit timestamps establish a snapshot tip, not whether a change was substantive. Therefore CSV last_substantive_change stays unknown; an observed tip commit date is not an adequate proxy for substantive change.

## Per-repository record

### R01 — GPT Researcher

- **Pinned snapshot:** default branch main; tip SHA 3582a6841fe7dc801e2a34e34ee408641aea9bce. [Pinned tree](https://github.com/assafelovic/gpt-researcher/tree/3582a6841fe7dc801e2a34e34ee408641aea9bce); archived: false.
- **License scope:** GitHub SPDX Apache-2.0; root LICENSE is Apache 2.0, but root pyproject declares MIT: unresolved conflict.
- **Runtime and repository surface:** Python >=3.12; pyproject includes FastAPI, LangChain OpenAI, LangGraph/checkpoint/SDK and more. [Relevant paths/tree](https://github.com/assafelovic/gpt-researcher/tree/3582a6841fe7dc801e2a34e34ee408641aea9bce): prompts.py and agent.py; root tests/; .github/workflows/tests.yml and other CI/deploy workflows.
- **Assessment:** Report prompt requires a references section and relevant URL hyperlinks, but it is not an enforcement gate for claim-to-passage support. Design reference only; resolve license conflict before any reuse. Selected source and root manifest inspected at pinned SHA.

### R02 — PaperQA2

- **Pinned snapshot:** default branch main; tip SHA c692d0dfeac4a0296599f7fe21a253a58b7ac12a. [Pinned tree](https://github.com/Future-House/paper-qa/tree/c692d0dfeac4a0296599f7fe21a253a58b7ac12a); archived: false.
- **License scope:** GitHub SPDX and root LICENSE: Apache-2.0; nested package/model/data terms not audited.
- **Runtime and repository surface:** Python >=3.11,<3.15; root pyproject has optional extras and multiple packages; includes Pydantic and LMI; PyMuPDF/Docling/Nemotron/local/Qdrant integrations are optional. [Relevant paths/tree](https://github.com/Future-House/paper-qa/tree/c692d0dfeac4a0296599f7fe21a253a58b7ac12a): src/paperqa/agents/main.py and env.py; src/paperqa/settings.py; root tests/ plus package-specific tests; build.yml and tests.yml.
- **Assessment:** Agent path is tool-driven; settings expose a maximum source count (default 5) and optional controls. Strong reference for bounded retrieval/abstention, not a drop-in MVP core. Pinned source paths and package tests inspected in tree; no repository code executed. Optional parser, local-model and vector-store integrations expand runtime surface.

### R03 — Ai2 ScholarQA

- **Pinned snapshot:** default branch main; tip SHA 19e6827ba9e7fe05068624d0851f38cd74ff5efc. [Pinned tree](https://github.com/allenai/ai2-scholarqa-lib/tree/19e6827ba9e7fe05068624d0851f38cd74ff5efc); archived: false.
- **License scope:** GitHub SPDX and root LICENSE: Apache-2.0.
- **Runtime and repository surface:** No root dependency manifest. README describes Docker/local service and a Python package; API, proxy and UI subtrees have their own runtime/configuration not audited. [Relevant paths/tree](https://github.com/allenai/ai2-scholarqa-lib/tree/19e6827ba9e7fe05068624d0851f38cd74ff5efc): README.md; api/scholarqa/lite response/prompt utilities; api/tests/test_citation_validation.py and related nested API tests; no root CI workflow found.
- **Assessment:** The focused test checks citation metadata conditions, useful as a validation-fixture idea. This is a demo/service repo, not a pure SDK; packaging and service dependencies remain unknown. README and citation-validation test inspected; no root manifest, so API/UI runtime constraints and nested license scope remain unknown.

### R04 — OpenScholar

- **Pinned snapshot:** default branch main; tip SHA 0e9b8fb912273d3dae39e593da86e4f6d3bf8de1. [Pinned tree](https://github.com/AkariAsai/OpenScholar/tree/0e9b8fb912273d3dae39e593da86e4f6d3bf8de1); archived: false.
- **License scope:** GitHub SPDX and root LICENSE: Apache-2.0; model weights, source corpora and third-party artifacts not reviewed.
- **Runtime and repository surface:** Root requirements list Transformers, OpenAI and Torch; no root Python version bound or lockfile inspected. [Relevant paths/tree](https://github.com/AkariAsai/OpenScholar/tree/0e9b8fb912273d3dae39e593da86e4f6d3bf8de1): src/open_scholar.py and src/use_search_apis.py; training/tests/ are nested under training; no workflow CI found.
- **Assessment:** Code includes passage reranking and search API helpers; these are architecture references. Torch/Transformers imply model runtime needs that were not measured. Do not reuse weights/data based on code license. Selected synthesis/retrieval source and root requirements inspected. Model, corpus, training asset and GPU terms/costs are outside this license screen.

### R05 — STORM / Co-STORM

- **Pinned snapshot:** default branch main; tip SHA fb951af7744dab086e34962e9bc6fe878e145f83. [Pinned tree](https://github.com/stanford-oval/storm/tree/fb951af7744dab086e34962e9bc6fe878e145f83); archived: false.
- **License scope:** GitHub SPDX, root LICENSE and setup.py: MIT.
- **Runtime and repository surface:** setup.py requires Python >=3.10; requirements include sentence-transformers, LangChain text splitters/HuggingFace and Qdrant. No bounded memory profile. [Relevant paths/tree](https://github.com/stanford-oval/storm/tree/fb951af7744dab086e34962e9bc6fe878e145f83): knowledge_storm/storm_wiki/engine.py and collaborative_storm/engine.py; root requirements.txt/setup.py; CI workflows for format and package; no tests/ tree found.
- **Assessment:** Pinned tree has separate Wiki-style and collaborative engine modules. Useful query-diversification/steering reference; no test suite or Veda persistence gate demonstrated in this screen. Engine and packaging files inspected. Embedding/search stack and runtime footprint not installed or measured.

### R06 — SciFact

- **Pinned snapshot:** default branch master; tip SHA 68b98a56d93e0f9da0d2aab4e6c3294699a0f72e. [Pinned tree](https://github.com/allenai/scifact/tree/68b98a56d93e0f9da0d2aab4e6c3294699a0f72e); archived: false.
- **License scope:** GitHub SPDX NOASSERTION. Root LICENSE.md scopes CC BY 4.0 to claim/evidence annotations, ODC-By 1.0 to corpus abstracts, and Apache-2.0 to code.
- **Runtime and repository surface:** requirements pin Torch 1.5.0 and Transformers 2.7.0; no root manifest/lock or contemporary environment validation. [Relevant paths/tree](https://github.com/allenai/scifact/tree/68b98a56d93e0f9da0d2aab4e6c3294699a0f72e): README.md, LICENSE.md, requirements.txt and benchmark data/scripts; no tests or CI workflows found in tree.
- **Assessment:** Evaluation-only. The code license does not relicense included S2ORC abstracts; any data reuse must retain the corpus-specific terms and attribution. README/license/requirements/tree inspected; corpus and claim annotations have different explicit terms. Legacy dependency pins were not installed.

### R07 — LangChain Open Deep Research

- **Pinned snapshot:** default branch main; tip SHA 1b7d2e80db9faa586165c60e09096dbbfd483a64. [Pinned tree](https://github.com/langchain-ai/open_deep_research/tree/1b7d2e80db9faa586165c60e09096dbbfd483a64); archived: true.
- **License scope:** GitHub SPDX and root LICENSE: MIT.
- **Runtime and repository surface:** Python >=3.10; broad optional/provider dependencies across LangChain OpenAI, Anthropic, MCP, Tavily, Groq, DeepSeek, Vertex, Gemini and AWS. [Relevant paths/tree](https://github.com/langchain-ai/open_deep_research/tree/1b7d2e80db9faa586165c60e09096dbbfd483a64): src/open_deep_research/deep_researcher.py; root tests/ primarily evaluation scripts/results; conventional tests are nested in src/legacy/tests; archived=true; no general test CI found (Claude workflows only).
- **Assessment:** Useful orchestration reference, but archived default-branch snapshot and provider breadth add upkeep. Root evaluation artifacts are not unit-test coverage; no direct state/persistence adaptation verified. Archived status read from GitHub repository metadata. Root tests/ contains eval scripts/results, while legacy tests are nested. No run or test execution.

### R08 — LangChain Local Deep Researcher

- **Pinned snapshot:** default branch add-claude-github-actions-1754523214489; tip SHA 96555649619b9c482442f2cba043312bd7692507. [Pinned tree](https://github.com/langchain-ai/local-deep-researcher/tree/96555649619b9c482442f2cba043312bd7692507); archived: false.
- **License scope:** GitHub SPDX and root LICENSE: MIT.
- **Runtime and repository surface:** Python >=3.9; LangGraph and LangChain Ollama/OpenAI, local LM Studio helpers; no test suite paths found. Docker workflow exists. [Relevant paths/tree](https://github.com/langchain-ai/local-deep-researcher/tree/96555649619b9c482442f2cba043312bd7692507): src/ollama_deep_researcher/graph.py, state.py, configuration.py; pyproject.toml; no tests/ or general test CI found.
- **Assessment:** Graph supports a local-first setup but includes provider and framework complexity beyond Veda's persisted finite-state core. Local model execution and quality were not tested. Graph and configuration source inspected at pinned default branch. No automated tests found in tree; Ollama/LM Studio setup not exercised.

### R09 — dzhng/deep-research

- **Pinned snapshot:** default branch main; tip SHA 1f8f3e285bbc23e80b98a66a64effab9069f3ad4. [Pinned tree](https://github.com/dzhng/deep-research/tree/1f8f3e285bbc23e80b98a66a64effab9069f3ad4); archived: false.
- **License scope:** GitHub SPDX and root LICENSE say MIT; root package.json declares ISC: unresolved packaging/license conflict.
- **Runtime and repository surface:** Node 22.x; OpenAI AI SDK and Firecrawl; root test script deliberately exits with 'no test specified', though src/ai/text-splitter.test.ts exists. [Relevant paths/tree](https://github.com/dzhng/deep-research/tree/1f8f3e285bbc23e80b98a66a64effab9069f3ad4): src/deep-research.ts; src/ai/text-splitter.ts and its nested test; package.json; no CI workflow found.
- **Assessment:** Iterative research loop is a design reference. License conflict must be resolved before reuse; available test surface is not a complete research-loop test. Selected loop and package metadata inspected. npm package license says ISC while root LICENSE and repository SPDX say MIT; no code reuse pending clarification.

### R10 — Jina node-DeepResearch

- **Pinned snapshot:** default branch main; tip SHA fd323b521a51264d497bec333bfb997da1bf3210. [Pinned tree](https://github.com/jina-ai/node-DeepResearch/tree/fd323b521a51264d497bec333bfb997da1bf3210); archived: false.
- **License scope:** GitHub SPDX, root LICENSE and package.json: Apache-2.0.
- **Runtime and repository surface:** TypeScript/Node; package.json defines Express/AI SDK/search dependencies and build/test scripts but no Node engines bound. [Relevant paths/tree](https://github.com/jina-ai/node-DeepResearch/tree/fd323b521a51264d497bec333bfb997da1bf3210): src/agent.ts, src/server.ts, nested src/__tests__ (agent/docker/server); Jest; .github/workflows/test.yml and publishing workflows.
- **Assessment:** Search/rewrite/evaluation loop and tests make this a code reference, not an application core. Browser/search integrations and API credentials were not exercised. Selected source plus nested Jest suite and CI paths inspected. Node version support is not declared by package.json.

### R11 — LearningCircuit local-deep-research

- **Pinned snapshot:** default branch main; tip SHA 450af26a664a8629dd499200bd40ca33c1fff229. [Pinned tree](https://github.com/LearningCircuit/local-deep-research/tree/450af26a664a8629dd499200bd40ca33c1fff229); archived: false.
- **License scope:** GitHub SPDX and root LICENSE: MIT.
- **Runtime and repository surface:** Python >=3.12,<3.15 and frontend Node >=24; broad LangChain/provider, Playwright and sentence-transformer dependencies, PDM lock, Docker. [Relevant paths/tree](https://github.com/LearningCircuit/local-deep-research/tree/450af26a664a8629dd499200bd40ca33c1fff229): src/local_deep_research/; root tests/ and .semgrep/tests; package.json; numerous CI/security workflows; no code run.
- **Assessment:** Recent large dual-runtime research application; not a lightweight library to transplant. Revisit isolated ideas only after license/security review and resource fit. Pinned manifest/tree and root license inspected; Python+Node runtime and broad integration footprint make full reuse unsuitable for MVP. Dependencies not installed.

### R12 — GPT Researcher MCP

- **Pinned snapshot:** default branch master; tip SHA 63884773685b1f12c7f0d9e283b3d71a5b9b5fda. [Pinned tree](https://github.com/assafelovic/gptr-mcp/tree/63884773685b1f12c7f0d9e283b3d71a5b9b5fda); archived: false.
- **License scope:** GitHub SPDX and root LICENSE: MIT.
- **Runtime and repository surface:** Python requirements include FastAPI, Uvicorn and Pydantic; MCP server wrapper around GPT Researcher. [Relevant paths/tree](https://github.com/assafelovic/gptr-mcp/tree/63884773685b1f12c7f0d9e283b3d71a5b9b5fda): README.md; tests/test_mcp_server.py checks SSE/session/protocol/tool discovery; no CI workflow found.
- **Assessment:** Integration wrapper only; test scope is server transport/protocol, not answer support or citation correctness. No reason to adopt as Veda's research engine. Wrapper test source inspected. Protocol tests do not validate evidence or research quality; no CI configured in repository tree.

### R13 — ASReview

- **Pinned snapshot:** default branch main; tip SHA 79d568212b2b0a78f9fd7be3c5117dfb890489f9. [Pinned tree](https://github.com/asreview/asreview/tree/79d568212b2b0a78f9fd7be3c5117dfb890489f9); archived: false.
- **License scope:** GitHub SPDX, root LICENSE, selected source header and pyproject: Apache-2.0.
- **Runtime and repository surface:** Python >=3.10; Flask/webapp and package dependencies, plus frontend assets. [Relevant paths/tree](https://github.com/asreview/asreview/tree/79d568212b2b0a78f9fd7be3c5117dfb890489f9): asreview/webapp/_api/projects.py; root tests/ and nested asreview/webapp/tests; core/integration/webapp and other CI workflows.
- **Assessment:** Systematic-review project screening and active-learning UI can inspire inclusion triage. Screening relevance is not source-claim verification; no transplant warranted. One selected API source, manifest, tree and root license inspected. Large UI/test surface not needed for Veda's MVP.

### R14 — Docling

- **Pinned snapshot:** default branch main; tip SHA 9051777f9e420fa3a37df77425b08f22d0bf5981. [Pinned tree](https://github.com/docling-project/docling/tree/9051777f9e420fa3a37df77425b08f22d0bf5981); archived: false.
- **License scope:** GitHub SPDX and root LICENSE: MIT; package manifests declare MIT. Third-party models/assets not audited.
- **Runtime and repository surface:** Root is a workspace with separate packages; packages/docling requires Python >=3.10,<4 and package-specific parsing/model dependencies. Exact installed footprint not measured. [Relevant paths/tree](https://github.com/docling-project/docling/tree/9051777f9e420fa3a37df77425b08f22d0bf5981): packages/docling/pyproject.toml; root tests/ and many CI workflows; file conversion code exists under package source but was not inspected.
- **Assessment:** Potential PDF/DOCX parsing component for a later ingest spike. Keep off the lightweight core until memory/model-download/resource and output-locator tests pass. Root/package manifests, license, tests and CI tree inspected; attempted source path did not resolve at pinned SHA, so parser internals remain unreviewed.

### R15 — DeepEval

- **Pinned snapshot:** default branch main; tip SHA d6cd78ac44da4623ff07c73310dfca474c212068. [Pinned tree](https://github.com/confident-ai/deepeval/tree/d6cd78ac44da4623ff07c73310dfca474c212068); archived: false.
- **License scope:** GitHub SPDX and root LICENSE.md: Apache-2.0.
- **Runtime and repository surface:** Python >=3.9,<4; Poetry; OpenAI plus Pydantic; optional/dev integrations add more dependencies. [Relevant paths/tree](https://github.com/confident-ai/deepeval/tree/d6cd78ac44da4623ff07c73310dfca474c212068): deepeval/metrics/answer_relevancy and faithfulness/citation-faithfulness; nested tests under package/setup wizard and root tests; extensive CI.
- **Assessment:** Evaluation harness only. LLM judge metrics can structure review, but need human/rule-based calibration and should not gate Veda truth by themselves. Root metadata, license and tree paths inspected; selected metric implementation not read. Model/judge calls and result validity not assessed.

### R16 — Ragas

- **Pinned snapshot:** default branch main; tip SHA 298b68274234c060deacab3cf5fb52aa3a20e885. [Pinned tree](https://github.com/vibrantlabsai/ragas/tree/298b68274234c060deacab3cf5fb52aa3a20e885); archived: false.
- **License scope:** GitHub SPDX and root LICENSE: Apache-2.0.
- **Runtime and repository surface:** Python >=3.9; root pyproject dependencies include OpenAI and LangChain ecosystem; optional Transformers/sentence-transformers. [Relevant paths/tree](https://github.com/vibrantlabsai/ragas/tree/298b68274234c060deacab3cf5fb52aa3a20e885): src/ragas/metrics/_faithfulness.py and collections; root tests/ and CI workflow.
- **Assessment:** RAG evaluation components only; not a substitute for claim/source review or domain expert checks. Broad model integrations add dependency/cost surface. Root manifest, license and tree inspected; metric implementation not opened or run. No scores are attributed to Veda.

### R17 — Microsoft GraphRAG

- **Pinned snapshot:** default branch main; tip SHA c600ff80b77b9b62c47d539a3ac9569e95d8949b. [Pinned tree](https://github.com/microsoft/graphrag/tree/c600ff80b77b9b62c47d539a3ac9569e95d8949b); archived: false.
- **License scope:** GitHub SPDX and root LICENSE: MIT; package code has MIT headers.
- **Runtime and repository surface:** Python >=3.11,<3.14 for main package; multi-package workspace and Azure/vector/model dependencies. [Relevant paths/tree](https://github.com/microsoft/graphrag/tree/c600ff80b77b9b62c47d539a3ac9569e95d8949b): packages/graphrag/graphrag/index/operations/extract_graph/extract_graph.py; root tests/ and unit/integration/notebook CI.
- **Assessment:** README says project is largely in maintenance mode, code is a research demonstration, and indexing can be expensive. Graph retrieval is a design lead, not a suitable low-cost default. Pinned README, package manifest, source module, license and CI/test tree inspected. README itself says maintenance mode and warns of indexing expense.

### R18 — Literature review tool catalog

- **Pinned snapshot:** default branch main; tip SHA 1c3079988ae82f7a4fff015e65f0941e3727afe0. [Pinned tree](https://github.com/brycewang-stanford/lit-review-agent-tools/tree/1c3079988ae82f7a4fff015e65f0941e3727afe0); archived: false.
- **License scope:** Root LICENSE: CC0-1.0; linked projects, model/data assets and copied third-party snippets retain independent terms.
- **Runtime and repository surface:** No root app/dependency manifest. [Relevant paths/tree](https://github.com/brycewang-stanford/lit-review-agent-tools/tree/1c3079988ae82f7a4fff015e65f0941e3727afe0): README variants; recipes including 03-verify-citations and PDF-to-Markdown; lint/metadata workflows; no tests.
- **Assessment:** Discovery/catalog plus small recipes; use for leads only. CC0 does not clear licenses of referenced third-party tools or materials. Catalog and recipe paths inspected in tree; individual linked repos and recipe dependency/license scopes remain separate.

### R19 — Awesome Auto Research

- **Pinned snapshot:** default branch main; tip SHA 445efe29f8137b842f4d261806db22712386423d. [Pinned tree](https://github.com/EdwardLeeLPZ/Awesome-Auto-Research/tree/445efe29f8137b842f4d261806db22712386423d); archived: false.
- **License scope:** Root LICENSE and GitHub SPDX: MIT for catalog repository; links are separately licensed.
- **Runtime and repository surface:** No app manifest or executable runtime found. [Relevant paths/tree](https://github.com/EdwardLeeLPZ/Awesome-Auto-Research/tree/445efe29f8137b842f4d261806db22712386423d): README.md and catalog content only; no tests or CI.
- **Assessment:** Discovery catalog only; listing does not verify quality, maturity or permission to reuse linked artifacts. Root documentation/license and tree inspected. Linked works/code were not reviewed under this repository audit.

### R20 — ScholarQABench

- **Pinned snapshot:** default branch main; tip SHA 95e6fc52b0a8a0ce0a74956029991e3bb00c38b9. [Pinned tree](https://github.com/AkariAsai/ScholarQABench/tree/95e6fc52b0a8a0ce0a74956029991e3bb00c38b9); archived: false.
- **License scope:** GitHub SPDX and root LICENSE: MIT for repository code. README scopes ODC-By 1.0 to aggregate test cases, sample answers and data; constituent datasets may have separate terms.
- **Runtime and repository surface:** README setup says Python 3.10; requirements pin Transformers 4.44 and Torch 2.4.0+cu121; evaluation scripts support API/model endpoints including OpenAI. [Relevant paths/tree](https://github.com/AkariAsai/ScholarQABench/tree/95e6fc52b0a8a0ce0a74956029991e3bb00c38b9): README.md, requirements.txt, data/, scripts; no tests/ or CI paths found.
- **Assessment:** Evaluation-only. Do not assume MIT covers benchmark contents; assess constituent terms and time-cutoff/comparability before using scores. README explicitly states ODC-By terms for aggregate benchmark cases/sample answers/data and directs users to individual dataset licenses. No benchmark code executed.

### R21 — DRBench

- **Pinned snapshot:** default branch main; tip SHA 0d699ecf6aa96b1de378595b432e9b16a82f0ed9. [Pinned tree](https://github.com/ServiceNow/drbench/tree/0d699ecf6aa96b1de378595b432e9b16a82f0ed9); archived: false.
- **License scope:** GitHub SPDX and root LICENSE: Apache-2.0 for repository/code. Task data licensing was not established by root license or inspected README.
- **Runtime and repository surface:** Python >=3.12,<4; OpenAI dependency in root pyproject; environment may include simulated enterprise sources and prebuilt task data. [Relevant paths/tree](https://github.com/ServiceNow/drbench/tree/0d699ecf6aa96b1de378595b432e9b16a82f0ed9): drbench/score_report.py; tests/test_tasks.py and tests/test_metrics_changes.py; README task loader/evaluation guide; no CI workflows found.
- **Assessment:** Enterprise multi-hop research benchmark with claim-citation outputs and report scoring. Useful rubric/evaluation reference; repository's benchmark data and any enterprise fixtures require separate licensing/privacy review. Scoring and task tests plus README inspected. Apache code license does not establish permissions for bundled task data; no benchmark run.

### R22 — Mind2Report

- **Pinned snapshot:** default branch main; tip SHA c293d5c6cc8dabde785499620690cb68139b9769. [Pinned tree](https://github.com/ustc-ai4science/Mind2Report/tree/c293d5c6cc8dabde785499620690cb68139b9769); archived: false.
- **License scope:** GitHub SPDX, root LICENSE and pyproject declare Apache-2.0. README links a placeholder dataset address; data/model terms not established.
- **Runtime and repository surface:** Python >=3.10; pinned Poetry dependencies include LangChain/LangGraph, MCP, Tavily, DeepSeek adapter and web parsing; external provider access/configuration required by workflow. [Relevant paths/tree](https://github.com/ustc-ai4science/Mind2Report/tree/c293d5c6cc8dabde785499620690cb68139b9769): src/agent/agent.py builds a LangGraph with clarify/search/outline/learning/generate/local-save nodes; src/agent/deepsearch.py; nested src/agent/test_agent.py; no CI workflows found.
- **Assessment:** Relevant commercial-report workflow reference (intent clarification, evolving notes, iterative synthesis), but repo runtime/provider and persistence setup is broader than Veda MVP. Selected source/README only; no reproducibility test. Selected workflow source and README inspected at pinned SHA. Test is nested under src/agent, not root tests; no CI path found. Repository does not establish third-party model/data terms.

### R23 — AI Scientist

- **Pinned snapshot:** default branch main; tip SHA 1de1dbc1f4ee2c5f61e9c94348d55eb51d7fa2eb. [Pinned tree](https://github.com/SakanaAI/AI-Scientist/tree/1de1dbc1f4ee2c5f61e9c94348d55eb51d7fa2eb); archived: false.
- **License scope:** GitHub SPDX NOASSERTION; root LICENSE is AI Scientist Source Code License v1.0 (December 2025), with enumerated use restrictions. Its AI Scientist clause requires prominent, intelligible disclosure when generating or disseminating scientific manuscripts, papers, or technical reports, and section 3.3 requires passing the restrictions into user/distribution agreements.
- **Runtime and repository surface:** Root requirements include OpenAI, Torch and Transformers; long-running experimental/code-execution scope; exact isolation/resource needs not tested. [Relevant paths/tree](https://github.com/SakanaAI/AI-Scientist/tree/1de1dbc1f4ee2c5f61e9c94348d55eb51d7fa2eb): README.md, requirements.txt and experiment/template/data directories; no root tests or CI paths found.
- **Assessment:** Autonomous scientific experimentation is outside Veda's evidence-backed report workflow. Do not treat as permissively reusable; review the complete restriction list and nested/model/data terms first. Root license is a custom source-code license with use restrictions; repository metadata is NOASSERTION. No source execution or license compatibility determination.

## Cross-repository decisions

- The clearest license conflicts are R01: repository SPDX and root LICENSE say Apache-2.0 while pyproject says MIT; and R09: repository SPDX/root LICENSE say MIT while npm package metadata says ISC. No reuse from these repos until the inconsistency is resolved against the relevant file/asset and distribution.
- Dataset permission must be separated from code permission: SciFact R06 explicitly assigns different code, claim-annotation and abstract/corpus terms; ScholarQABench R20 identifies ODC-By for aggregate benchmark/data and separately points to constituent dataset terms; DRBench R21's Apache code grant did not establish bundled task-data rights in the inspected README. Do not infer benchmark-data permission from repository SPDX.
- R23's custom source license is not captured by GitHub SPDX (NOASSERTION). Its AI Scientist clause requires prominent disclosure on AI-generated scientific/technical reports and contractual flowdown of the restrictions; this would require product/legal review before Veda could adopt any code.
- For the lightweight Veda MVP, retain design ideas, not whole research runtimes: bounded retrieval/abstention (R02), query diversity and user steering (R05), metadata-aware citation tests (R03), report workflow inspiration (R22), and evaluation ideas (R20/R21) can guide Veda-owned implementation. This is an engineering inference from the inspected paths/manifests, not a measured quality or performance comparison.
- Migration/reuse triggers: pin and review the exact module and all data/model licenses; confirm Python/Node/runtime compatibility; verify persistence and restart semantics; and demonstrate a focused fixture improvement without exceeding the application resource/cost envelope.

## CSV update

docs/research/repos.csv now records each exact default-branch SHA, snapshot branch/archive state, inspected license scope, relevant paths, audit access level and bounded decision. For rows without a commit-date-as-substantive finding, last_substantive_change remains unknown. The audit does not modify source code or claim any tests passed.
