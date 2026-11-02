# Primary-source audit: papers P15–P28

**Access date:** 2026-10-29 (Asia/Kolkata). I reviewed the linked publisher/preprint pages and, where accessible, author repositories, README/license files, and dataset cards. I did not install or execute repository code, make model/API calls, or independently reproduce reported benchmark results. Results below are attributed to their authors unless explicitly labeled as an engineering inference. A repository license is not assumed to cover third-party source material unless the repository says so.

## Findings

### P15 — DEER

- **Access:** PMLR proceedings record and abstract HTML; the linked paper PDF did not load through the available browser. Inspected the [official repository README](https://github.com/hanjanghoon/DEER) and [dataset license](https://github.com/hanjanghoon/DEER/blob/main/DATA_LICENSE), plus the [Hugging Face dataset card](https://huggingface.co/datasets/LG-AI-Research/DEER-Deep-Research-Benchmark).
- **Source finding:** The [PMLR record](https://proceedings.mlr.press/v306/han26m.html) identifies the ICML 2026 paper and reports an expert taxonomy with 7 dimensions, 25 subdimensions, 101 rubric items, task-specific expert guidance, and verification of cited and uncited claims. Its abstract says current systems can produce structurally plausible, cited reports but miss parts of expert requests and logical completeness. Paper-body methods, numerical results, and detailed limitations were not verified because the PDF was inaccessible.
- **Code/data:** The repository labels code MIT. The dataset has a separate custom license: non-commercial research/evaluation/development uses are allowed; commercial use requires prior written permission; redistribution/public hosting is restricted. Do not treat the code license as the data license.
- **Reuse:** Strong design precedent for separating rubric coverage from claim/evidence verification; not evidence that its scoring method is independently validated here. Dataset reuse is not cleared for a commercial product.

### P16 — DRBench (ServiceNow)

- **Access:** Full author preprint [arXiv HTML v2](https://arxiv.org/html/2510.00172) (10 Mar 2026), [ICLR proceedings abstract](https://proceedings.iclr.cc/paper_files/paper/2026/hash/0ba520d93c3df592c83a611961314c98-Abstract-Conference.html), [GitHub repository](https://github.com/ServiceNow/drbench), and [Hugging Face dataset card](https://huggingface.co/datasets/ServiceNow/drbench). Direct conference-PDF fetch timed out; no code was executed.
- **Source finding:** Authors describe 100 tasks across 10 domains, drawn from synthetic enterprise environments with files, email/chat, applications, and public-web evidence. They assess insight recall, factuality, distractor avoidance, and report quality. Their comparisons show lower performance in app-based than local-file conditions. They explicitly limit breadth to selected enterprise task families and use atomic insights rather than span-level grounding.
- **Code/data:** Repository and dataset card identify Apache-2.0. The dataset card lists 100 rows. This supports evaluating heterogeneous-source workflows; it does not establish performance on real private company records.
- **Reuse:** Best enterprise analogue in this set, but its synthetic environment and benchmark results do not establish the economics or legal posture of a live production connector.

### P17 — DeepResearch Bench

- **Access:** Full [arXiv HTML v1](https://arxiv.org/html/2506.11763), [project site](https://deepresearch-bench.github.io/), and [author repository](https://github.com/Ayanami0730/deep_research_bench). The repository README and license metadata were inspected; code was not run.
- **Source finding:** Paper authors report 100 PhD-level tasks across 22 fields, evenly split between Chinese and English. Their topic mix is informed by 96,147 raw search-chatbot queries filtered to 44,019 queries. RACE uses reference reports and adaptive criteria for report quality; FACT extracts statement–URL pairs and uses retrieved page text plus an LLM judge to score citation support and effective citations. Authors report human-alignment studies, while noting task-scale/domain-selection limits and that human evaluation was limited to 50 tasks across four agents (600 reports). The FACT pipeline depends on an LLM judge and Jina page retrieval, so the reported measures are not purely deterministic.
- **Code/data:** The repository reports Apache-2.0. Its reviewed pages did not expose a separate data license; dataset rights are therefore **unknown** here. README instructions require hosted-model and Jina credentials for evaluation; no calls were made.
- **Reuse:** Useful evaluation pattern for report criteria plus citation support, but it is a benchmark, not proof that an LLM judge is adequate for Veda’s high-impact claims.

### P18 — DeepResearch Bench II

- **Access:** Full [arXiv HTML v3](https://arxiv.org/html/2601.08536) (10 Sep 2026), [repository README](https://github.com/imlrz/DeepResearch-Bench-II), code [LICENSE](https://github.com/imlrz/DeepResearch-Bench-II/blob/main/LICENSE), and per-task [DATA_LICENSE](https://github.com/imlrz/DeepResearch-Bench-II/blob/main/DATA_LICENSE).
- **Source finding:** Authors report 132 tasks across 22 domains and two languages, scored with 9,430 binary rubrics over recall, analysis, and presentation, built through a four-stage LLM/human process and more than 400 human-hours. The paper reports current systems satisfy fewer than half the rubrics. It discloses source-article leakage despite prompt-based exclusion, possible human-annotation bias, and a presentation dimension that mainly covers formatting rather than audience personalization.
- **Code/data:** Code repository metadata says Apache-2.0. Dataset license is per source article: 129 tasks CC BY 4.0, two CC BY-NC 4.0, and one CC0. The paper’s arXiv license (CC BY-NC-SA 4.0) is distinct from those task-level data terms. Commercial reuse of the whole dataset is not cleared because two tasks are expressly non-commercial.
- **Reuse:** Fine-grained rubrics support diagnosing gaps; source leakage and subjective criteria argue for provenance-aware, human-audited evaluation.

### P19 — DR³-Eval

- **Access:** The [ACL Anthology record](https://aclanthology.org/2026.emnlp-main.1691/) exposes title, publication metadata, and abstract. The official PDF fetch failed (403/timeout in this browser), so the full paper was not read.
- **Source finding (abstract only):** Authors describe multimodal, multi-file report tasks built from user-provided materials and static per-task sandboxes containing support documents, distractors, and noise. Their abstract names five dimensions—information recall, factual accuracy, citation coverage, instruction following, and depth quality—and says alignment with human judgments was evaluated. It also says their DR³-Agent experiments expose retrieval-robustness and hallucination-control failures. No detailed methods, numerical results, limitations, or artifact/license terms are asserted here.
- **Code/data:** No artifact link appeared on the Anthology page inspected; availability and license remain unknown, not established as absent.
- **Reuse:** Static per-task evidence sandboxes look useful for reproducible regression tests, pending full-paper and data-access review.

### P20 — BrowseComp-Plus

- **Access:** [Official project page](https://texttron.github.io/BrowseComp-Plus/), author [arXiv paper](https://arxiv.org/abs/2508.06600), [GitHub repository](https://github.com/texttron/BrowseComp-Plus), and [Hugging Face query/relevance dataset card](https://huggingface.co/datasets/Tevatron/browsecomp-plus) were inspected. The dataset viewer reports an oversized row group; repository instructions say queries/answers are obfuscated, while the corpus is hosted separately.
- **Source finding:** Authors describe 830 BrowseComp-derived questions evaluated against a fixed corpus of roughly 100,000 web documents, with human-verified evidence and mined hard negatives. The project reports GPT-5 at 55.9% and GPT-5 with Qwen3-Embedding-8B at 70.1% accuracy; these are author-reported results, not reproduced here. The benchmark isolates retrieval/agent comparisons and does not by itself measure long-report quality. The paper is an arXiv technical report; the project page identifies the work as ACL 2026 Main.
- **Code/data:** GitHub reports MIT for code; the Hugging Face query/relevance card lists MIT. The separately hosted full corpus and underlying third-party web-document rights were not audited, so do not infer that all corpus content has identical reuse rights.
- **Reuse:** Useful for fixed-corpus retrieval regressions, not as a complete report-quality benchmark.

### P21 — Characterizing Deep Research / LiveDRBench

- **Access:** Full [arXiv HTML](https://arxiv.org/html/2508.04183), [Microsoft repository](https://github.com/microsoft/LiveDRBench), and [dataset card](https://huggingface.co/datasets/microsoft/LiveDRBench) were inspected. The paper says 100 tasks; the current dataset card displays 110 rows, and this count difference is not explained in the reviewed pages.
- **Source finding:** The paper defines deep research as broad, reasoning-intensive search and evaluates intermediate claim discovery with precision/recall/F1 rather than directly scoring finished report quality. Authors report overall F1 of 0.55 for OpenAI Deep Research, with substantial variation across task categories. The tasks span scientific discovery and public-interest questions; they are designed to require multiple web sources.
- **Code/data:** Repository reports MIT for code; dataset card reports CDLA v2 for the data. Do not conflate the manuscript’s arXiv CC BY 4.0 license with the dataset license.
- **Reuse:** Supports an intermediate claim ledger as a useful diagnostic, while remaining complementary to final-answer citation/report review.

### P22 — ResearchRubrics

- **Access:** Full [arXiv HTML](https://arxiv.org/html/2511.07685), [author repository](https://github.com/scaleapi/researchrubrics), and [dataset card](https://huggingface.co/datasets/ScaleAI/researchrubrics) were reviewed. The repository instructions require a hosted LLM API key for reproducing grading; none was used.
- **Source finding:** Authors describe 101 prompts and 2,500+ expert-written criteria, with three task-complexity axes and weighted mandatory/optional/negative criteria. They report 2,800+ human-hours. Their human/LLM agreement is higher for binary judgments (reported macro-F1 0.72–0.76) than ternary judgments (about 0.53–0.57). They also report a response-length/score correlation and explicitly say they cannot separate information-density effects from residual length bias without controlled tests.
- **Code/data:** Repository declares MIT; dataset card declares MIT and lists 101 rows. The arXiv manuscript page shows CC BY 4.0. This records the surfaced terms only, not a separate legal review of individual prompt content.
- **Reuse:** Useful for weighted acceptance criteria, but rubric judgments remain fallible and long answers may score better partly because they cover more criteria.

### P23 — ResearcherBench

- **Access:** Full [arXiv HTML](https://arxiv.org/html/2507.16280), [author repository](https://github.com/GAIR-NLP/ResearcherBench), and its README were reviewed. The repository page contains code and data folders but no visible LICENSE file; an attempted direct LICENSE URL returned 404. No separate data license surfaced, so reuse terms are unknown.
- **Source finding:** Authors report 65 questions across 35 AI research subjects, split into technical details, literature review, and open consulting; evaluation combines expert insight rubrics with claim/citation verification. Their reported systems perform better on consulting than precision technical tasks. Authors identify AI-only domain scope, small task count, and black-box commercial systems as limitations.
- **Code/data:** Public repository and “open-source” language in the paper do not substitute for a license grant. Do not reuse code or benchmark data without resolving the rights.
- **Reuse:** Insight plus factual-grounding evaluation is relevant, but the domain and sample limitations prevent direct transfer of its comparative rankings to business research.

### P24 — Deep Research: A Systematic Survey

- **Access:** Full [arXiv HTML v1](https://arxiv.org/html/2512.02038) and the linked [survey repository](https://github.com/mangopy/Deep-Research-Survey) were inspected at abstract/taxonomy level; no repository code was executed. The arXiv page identifies the manuscript’s standard arXiv distribution license, not a benchmark-data license.
- **Source finding:** The authors present a literature taxonomy covering query planning, information acquisition, memory, answer generation, optimization, and evaluation. This is secondary synthesis, not an empirical benchmark. I did not audit a systematic search/screening protocol or independently validate the survey’s coverage.
- **Code/data:** No Veda-reusable implementation or benchmark dataset was verified. Treat the repository as a survey companion/bibliography unless separately inspected.
- **Reuse:** Discovery aid only; follow its citations to primary papers before adopting claims.

### P25 — Deep Research Agents: A Systematic Examination and Roadmap

- **Access:** Full [arXiv HTML v2](https://arxiv.org/html/2506.18096) (3 Sep 2025) was reviewed. The inspected version is a survey/roadmap, not a controlled evaluation.
- **Source finding:** It organizes systems around API versus browser retrieval, static versus dynamic workflows, planning, single versus multi-agent designs, tool use, and memory. The authors flag generalization, rigid workflows, granular tool integration, and computational cost as open challenges. These are survey claims, not comparative test results.
- **Code/data:** No benchmark dataset or operational code was verified in the inspected source. The arXiv manuscript license does not establish rights to reuse cited systems or their code.
- **Reuse:** Useful vocabulary and bibliography, not evidence that multi-agent execution is necessary for an MVP.

### P26 — PRISMA 2020

- **Access:** Full peer-reviewed text of the same statement is accessible through the [PLOS Medicine open-access publication](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1003583) and official [PRISMA statement page](https://www.prisma-statement.org/prisma-2020-statement). The BMJ landing page/PDF in the CSV returned 403 in this browser; the PLOS publication is the co-published statement.
- **Source finding:** The article presents a 27-item reporting checklist, expanded guidance, abstract checklist, and flow diagrams. Development included review of 60 guidance documents, a survey with 110 of 220 invited respondents, and a 21-member meeting. Crucially, the authors say PRISMA is primarily for reviews of health interventions and **is not** a guide to review conduct or a tool for judging methodological quality.
- **Code/data:** Article is CC BY; checklists are available from the official PRISMA site. No software license is relevant to Veda.
- **Reuse:** Adapt transparent reporting of search, screening, exclusions, and evidence flow; do not turn PRISMA into a numerical evidence-quality score.

### P27 — GRADE Handbook

- **Access:** Full [official handbook HTML](https://gdt.gradepro.org/app/handbook/handbook.html) was reviewed. The page says the handbook was updated in October 2013 and is being replaced by the GRADE Book, available since 2024.
- **Source finding:** The GRADE approach separates confidence/certainty in effect estimates from recommendation strength and discusses risk of bias, inconsistency, indirectness, imprecision, and publication bias. The handbook explicitly targets health-care systematic review, HTA, and guideline audiences.
- **Code/data:** Not applicable. This is guidance, not a released model or dataset.
- **Reuse:** The evidence-domain vocabulary may inform an explicit confidence note. Applying GRADE as a score to business/market claims would be an engineering extrapolation, not a validated use of the handbook.

### P28 — OpenAI Deep Research System Card

- **Access:** Full [official Deployment Safety Hub system-card HTML](https://deploymentsafety.openai.com/deep-research), linked from the [OpenAI publication page](https://openai.com/index/deep-research-system-card/). Published 25 Feb 2025.
- **Source finding:** OpenAI describes an early o3 version optimized for browsing, its evaluation process, and risks including prompt injection, privacy, code execution, bias, and hallucination. The card reports mitigations but also residual prompt-injection risk and limitations in evaluation coverage. These are vendor-authored disclosures for the release described, not an independent comparison or current specification for every later system.
- **Code/data:** No reusable code or benchmark dataset is presented by this source.
- **Reuse:** Supports treating retrieved pages as untrusted input, constraining tool authority, and preserving privacy. Those are engineering implications, not proof that the documented mitigations transfer to Veda.

## Cross-paper implications for Veda (engineering inference)

The evidence favors making an auditable claim/evidence record and separate report-quality checks first-class: DEER, DRBench, DRB/DRB II, ResearchRubrics, and DR³-Eval all evaluate more than fluent prose, while LiveDRBench separates claim discovery from report writing. The enterprise benchmark adds heterogeneous-source realism but is synthetic; the fixed-corpus benchmarks improve reproducibility while omitting live-web drift. Therefore, these papers do not establish one universally best agent architecture.

For a lightweight persisted/resumable MVP, a single orchestrated workflow with explicit saved stages (question plan, source records, extracted claims, verification state, report draft) is a conservative engineering choice. Add parallel or multi-agent research only if measured latency/coverage requires it; the cited surveys describe those patterns but do not show that Veda needs them. Keep source text untrusted, retain citations at claim granularity, expose uncertainty and unresolved claims, and separate retrieval coverage from factual support and presentation. Escalate the evaluator from automated rubric checks to human review for high-impact decisions. Migration triggers include demonstrated planning bottlenecks, larger evidence corpora requiring durable indexing, a need for simultaneous specialist research, or a benchmark showing that persisted single-agent stages fail to meet coverage/latency targets.

## Known access gaps

- P15 paper PDF did not load; only its PMLR abstract/record and repository license/readme were screened.
- P19 ACL PDF could not be fetched; findings are limited to the Anthology abstract and metadata. Code/data and full methods remain unknown.
- P16 ICLR PDF fetch timed out; full arXiv HTML was screened instead.
- P26 BMJ page/PDF returned 403; full co-published PLOS text was accessible.
- Repository code was inspected at documentation/license level only, never installed, executed, or audited for behavior.
