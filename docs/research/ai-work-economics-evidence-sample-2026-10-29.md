# Candidate primary-source sample for AI-and-work/economics cases

**Access date:** 2026-10-29.  
**Status:** Candidate source sample for future case construction; it requires independent human source review. No human review, gold answer, report score, or benchmark result is claimed here. The case registry remains unchanged.

## Scope and method

This is a fixed, small sample selected to exercise draft questions about software development, professional writing and consulting, customer support, and heterogeneous or null effects in small businesses. I inspected the primary paper, publisher page, arXiv full text, or author/institutional repository page linked below. The access level is stated separately for each item. This is not a systematic review, and inclusion does not imply that a study answers the full draft question. Results below are the source's reported claims, not Veda report scores or independent re-analysis.

Draft question text and IDs were checked in `evaluation/questions/ai_economics_cases.json` on the access date. The registry currently has no writing-specific case, so Noy and Zhang is only a partial fit to GEN01; that coverage gap is recorded here without changing the registry.

## Source sample

### 1. Coding assistant speed on a controlled task

**Paper:** Peng, Kalliamvakou, Cihon, and Demirer, “The Impact of AI on Developer Productivity: Evidence from GitHub Copilot” ([arXiv DOI and record](https://doi.org/10.48550/arXiv.2302.06590); [full text](https://arxiv.org/html/2302.06590)).

- **Draft case mapping:** DEV01, “Among experienced software developers, does a coding assistant increase task-level coding speed, and does that translate into end-to-end delivery throughput?” This directly informs task-level speed but does not measure end-to-end delivery throughput.
- **Design, population, outcomes:** Controlled randomized experiment. The paper reports 95 professional programmers recruited via Upwork, assigned to treatment (45) or control (50), to implement a JavaScript HTTP server as quickly as possible. Only 35 participants completed the task and survey. Conditional on completing the task, the paper reports mean completion times of 71.17 minutes with Copilot and 160.89 minutes without it (55.8% lower; 95% CI 21–89%; p=.0017). The treatment group’s success rate was 7 percentage points higher, but the difference was not statistically significant.
- **Scope limits:** One short, incentivized JavaScript task; results are conditional on task completion after substantial non-completion. It does not establish accepted pull requests, production outcomes, code maintainability, or sustained team throughput. The study period predates Copilot general availability.
- **Access and rights:** Open arXiv HTML/PDF inspected. The arXiv page states an arXiv perpetual non-exclusive license; this is not treated as permission to reuse figures or underlying data. No separate dataset or code reuse license was checked.
- **Primary evidence:** [arXiv paper](https://arxiv.org/html/2302.06590).

### 2. Experienced open-source developers: a negative productivity result

**Paper:** Becker, Rush, Barnes, and Rein, “Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity” ([arXiv DOI and record](https://doi.org/10.48550/arXiv.2507.09089); [full text](https://arxiv.org/html/2507.09089)).

- **Draft case mapping:** DEV04, “How sensitive are reported developer productivity effects to using self-reported speed, task completion, accepted pull requests, or production outcomes?” This is a direct comparison of forecasts and post-study estimates with measured task time; it does not measure accepted PRs or production outcomes. It is also relevant to GEN04 as a public negative result, but does not assess publication bias.
- **Design, population, outcomes:** Randomized controlled trial assigning AI availability at the issue level. Sixteen experienced open-source developers with moderate AI experience completed 246 tasks in mature repositories where they had an average of five years of prior experience. For the February–June 2025 tool setting, the authors report that AI-allowed tasks took 19% longer in their regression estimate; participants had forecast a 24% speedup and later estimated a 20% speedup. The authors also report manually labeling screen recordings for 74 issues.
- **Scope limits:** Small, selected group working in mature repositories they knew well, using a particular early-2025 tool/model mix. The authors explicitly caution against generalizing to other settings and say experimental artifacts cannot be fully ruled out; they note that greenfield or unfamiliar-codebase work may differ. This study does not establish that AI slows all developers or current/future tools.
- **Access and rights:** Full arXiv HTML/PDF inspected; the arXiv record marks the paper CC BY 4.0. Reuse of any underlying recordings, task data, or repository material has not been assessed.
- **Primary evidence:** [arXiv paper](https://arxiv.org/html/2507.09089).

### 3. Developer field experiments with completed-task outcomes

**Paper:** Cui et al., “The Effects of Generative AI on High-Skilled Work: Evidence from Three Field Experiments with Software Developers” ([publisher DOI/article page](https://doi.org/10.1287/mnsc.2025.00535)).

- **Draft case mapping:** DEV02, “How do code assistants affect novice developers' completion time, correctness, and later unaided skill on comparable programming tasks?” This is adjacent evidence on experience heterogeneity, not a direct study of novices’ correctness or later unaided skill.
- **Design, population, outcomes:** The publisher abstract reports randomized controlled trials conducted in the ordinary course of business at Microsoft, Accenture, and an anonymous Fortune 100 company. Random subsets of developers received a coding assistant. Across 4,867 developers, the pooled estimate was a 26.08% increase in completed tasks (SE 10.3%); the publisher notes that individual experiments were noisy and varied, and that less experienced developers had higher adoption and greater productivity gains.
- **Scope limits:** The inspected evidence was the publisher abstract and metadata, not the complete article methods/results. The abstract's reported outcome is completed tasks; it does not establish correctness, learning transfer, or delayed unaided skill. Do not treat this as answering the full DEV02 question without checking the full paper.
- **Access and rights:** Publisher abstract/metadata accessible; full article text was not obtained or reviewed. The publisher lists supplemental appendices/data, but these were not retrieved and their reuse terms were not checked. Publisher page states copyright © 2026 INFORMS.
- **Primary evidence:** [INFORMS article page](https://pubsonline.informs.org/doi/10.1287/mnsc.2025.00535).

### 4. Professional writing tasks

**Paper:** Noy and Zhang, final article “Experimental Evidence on the Productivity Effects of Generative Artificial Intelligence” ([Science DOI](https://doi.org/10.1126/science.adh2586)); earlier author-hosted manuscript ([MIT PDF](https://economics.mit.edu/sites/default/files/inline-files/Noy_Zhang_1.pdf)).

- **Draft case mapping:** GEN01, “Can productivity estimates from technology firms or office tasks be generalized to healthcare, education, manufacturing, or public services?” **Partial fit only:** the study concerns professional writing tasks, not generalization across those listed sectors. The draft registry has no writing-specific case.
- **Design, population, outcomes:** The final Science abstract was accessible and reports an experiment with 453 college-educated professionals performing occupation-specific professional writing tasks, with ChatGPT randomly provided to half; it reports 40% less time and 18% higher quality. The open MIT-hosted March 2023 working-paper version is explicitly labeled “Working Paper (not peer reviewed)” and reports a different sample (444) and version-specific effect sizes (0.8 SD less time and 0.4 SD higher quality). Those figures are not interchangeable; they are reported here separately by version.
- **Scope limits:** Online, incentivized writing tasks are not a measure of real workplace delivery, long-run firm productivity, or outcomes in non-office sectors. The accessible publisher evidence was the abstract; the full final journal article was not accessed. The author-hosted manuscript is an earlier version.
- **Access and rights:** Final publisher abstract/metadata accessible; full publisher article not accessible in this review. Earlier MIT working-paper full text was open and inspected. Reuse terms for the final article, figures, and data were not verified; cite/paraphrase only unless separately licensed.
- **Primary evidence:** [Science article record](https://doi.org/10.1126/science.adh2586); [MIT working-paper PDF](https://economics.mit.edu/sites/default/files/inline-files/Noy_Zhang_1.pdf).

### 5. Consulting work and the “jagged frontier”

**Paper:** Dell’Acqua et al., “Navigating the Jagged Technological Frontier: Field Experimental Evidence of the Effects of Artificial Intelligence on Knowledge Worker Productivity and Quality” ([publisher DOI](https://doi.org/10.1287/orsc.2025.21838); [HBS-hosted full paper](https://www.hbs.edu/ris/Publication%20Files/dell-acqua-et-al-2026-navigating-the-jagged-technological-frontier_5c589c8c-fbb5-458f-b285-c944746cd717.pdf)).

- **Draft case mapping:** GEN03, “How do consulting estimates of enterprise AI ROI compare with transparent primary studies using observable costs, denominators, and follow-up?” This is a primary consulting-task experiment, not an audit of consulting firms’ enterprise ROI estimates.
- **Design, population, outcomes:** Preregistered randomized experiment with 758 BCG consultants assigned to no AI, GPT-4, or GPT-4 plus a prompt-engineering overview. For 18 tasks judged within the AI frontier, the paper reports 12.2% more tasks completed, 25.1% faster completion, and higher quality with AI. On one outside-the-frontier task, AI groups were 19 percentage points less likely to produce a correct solution.
- **Scope limits:** One consulting firm, one model era, and one outside-frontier task. This estimates task outcomes, not enterprise ROI or implementation cost. The paper notes that subjective evaluation rubrics and the single outside-frontier task constrain interpretation.
- **Access and rights:** Full author-hosted paper inspected. The paper states CC BY 4.0. Data and supplemental-material terms were not independently reviewed.
- **Primary evidence:** [HBS-hosted paper PDF](https://www.hbs.edu/ris/Publication%20Files/dell-acqua-et-al-2026-navigating-the-jagged-technological-frontier_5c589c8c-fbb5-458f-b285-c944746cd717.pdf).

### 6. Customer-support assistance and worker heterogeneity

**Paper:** Brynjolfsson, Li, and Raymond, “Generative AI at Work” ([QJE DOI and open-access article](https://doi.org/10.1093/qje/qjae044)).

- **Draft case mapping:** SUP01, “Does AI assistance reduce customer-support handling time while maintaining first-contact resolution and customer outcomes?” and SUP02, “How does AI assistance change productivity and quality for novice versus experienced support agents?”
- **Design, population, outcomes:** The QJE article studies staggered rollout of a GPT-3-based conversational assistant to 5,172 support agents at one Fortune 500 business-software firm. The paper reports a 15% average increase in issues resolved per hour; gains were larger for less experienced/lower-skill agents, while the highest-skill agents had small speed gains and a small quality decline. It also reports average-handle-time, resolution-rate, and customer-experience measures.
- **Scope limits:** This was staggered deployment, not randomized assignment across the analyzed workforce. The paper explicitly describes medium-run effects in one firm and says it is not designed to estimate aggregate employment or wage effects. Its reported resolution measures should not be assumed to equal the registry's specific first-contact-resolution outcome.
- **Access and rights:** Full QJE HTML text and metadata were accessible; publisher marks the paper Open Access. Exact downstream license for article figures/data and any separate data files was not checked.
- **Primary evidence:** [QJE article](https://academic.oup.com/qje/article/140/2/889/7990658); [DOI](https://doi.org/10.1093/qje/qjae044).

### 7. AI advice for Kenyan small-business entrepreneurs: average null with heterogeneous effects

**Paper:** Otis et al., “The Uneven Impact of Generative Artificial Intelligence on Entrepreneurial Performance: Evidence from a Field Experiment in Kenya” ([published DOI](https://doi.org/10.1287/mnsc.2024.06909); [UC eScholarship record](https://escholarship.org/uc/item/0fb001r8); [accessible author manuscript PDF](https://escholarship.org/content/qt40s41244/qt40s41244_noSplash_4105f15f8b51a189ffed1e56743b4cc8.pdf?t=sgrjiv)).

- **Draft case mapping:** SME02, “Do small firms achieve positive risk-adjusted financial returns from generative AI adoption compared with similar non-adopters?” and partially SME03 on variation in returns. It also supplies a published null/negative result relevant to GEN04, but it is not a scan for unpublished evidence.
- **Design, population, outcomes:** The open author manuscript reports an RCT with 640 Kenyan small-business entrepreneurs, half offered a GPT-4-based business assistant via WhatsApp, with business performance tracked through surveys. The published abstract and manuscript report no statistically detectable average treatment effect on revenue/profit performance; effects differed by baseline performance. The published abstract reports low performers did nearly 10% worse and high performers may have benefited by over 15%. The earlier manuscript reports corresponding estimates of about 8% lower performance for low performers and just over 15% gains for high performers. These are manuscript-version-specific figures and should not be silently combined.
- **Scope limits:** One national setting, WhatsApp-based advice, and a selected sample of mostly young businesses recruited through Meta ads; the author manuscript reports the experiment lasted approximately five months. Heterogeneity is by baseline business performance, not by firm size, digital capability, or sector. The study does not establish risk-adjusted net ROI after implementation costs.
- **Access and rights:** The institutional record exposes the published abstract and DOI; a full earlier author manuscript was accessible and inspected. The latest published full text was not verified. Reuse license for the manuscript, published article, figures, and supplemental data was not confirmed; supplemental material is linked by the publisher but was not retrieved.
- **Primary evidence:** [UC eScholarship record](https://escholarship.org/uc/item/0fb001r8); [author manuscript PDF](https://escholarship.org/content/qt40s41244/qt40s41244_noSplash_4105f15f8b51a189ffed1e56743b4cc8.pdf?t=sgrjiv); [published DOI](https://doi.org/10.1287/mnsc.2024.06909).

## Cross-case use and unresolved work

- The sources support testing whether reports distinguish task time, task completion, output quality, worker learning, customer outcomes, and firm financial outcomes. They do not share a common outcome definition and should not be pooled without further methodological review.
- Positive and negative findings coexist within this sample. Peng's narrow controlled coding task and the METR issue-level trial answer different questions and use different tools, participants, and settings. Dell’Acqua and Otis likewise show that effects can vary by task frontier or baseline capability. These differences are not evidence that one study invalidates another.
- The draft registry does not yet contain a dedicated professional-writing case; GEN01 is an imperfect fit. The sampled SME evidence does not answer implementation-cost, risk-adjusted ROI, or size/digital-capability subgroup questions. No case wording or source registry was changed as part of this note.
- Full-text review remains needed for Cui et al. and the final Noy and Zhang journal article; current-version verification and reuse-rights review remain needed for Otis et al. Source supplements, datasets, and code were not downloaded or rights-audited. These candidates should receive independent human review before becoming benchmark gold sources.
