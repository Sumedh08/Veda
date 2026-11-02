# Primary-source audit of the GLM-5.3 Flash live report

**Run:** `sarvam-glm53-research-20261030T203439162920Z.json`  
**Job:** `88f077d1-ef0d-4ee5-b236-2811d301321e`  
**Report:** `c9a06710-c31c-4970-bd34-6754966bc22e`  
**Audit date:** 2026-10-31

This is a source-identity and coverage audit, not an independent scientific review. The live job selected 14 records: 9 abstract-only and 5 metadata-only, with no full-text passages. The report therefore could not support conclusions requiring full-paper methods or results. Primary-source checks below were conducted separately against author-hosted arXiv papers and the publisher's article page.

## What the primary records establish

### GitHub Copilot controlled task experiment — report citation S7

The cited paper is Peng et al., *The Impact of AI on Developer Productivity: Evidence from GitHub Copilot* ([arXiv record](https://arxiv.org/abs/2302.06590), [full paper](https://arxiv.org/pdf/2302.06590)). Its full text describes a controlled experiment recruiting 95 professional programmers through Upwork in 2022. Participants implemented one JavaScript HTTP server; the treatment group had Copilot and the control group could use ordinary resources such as web search and Stack Overflow. The authors report 55.8% shorter completion time, with a 95% confidence interval of 21%–89% (paper, study design and results). This supports the report's narrowly worded “one task” result. It does not establish a general productivity gain across routine software work, code quality, maintenance, or current assistants.

### Three workplace field experiments — present only as metadata in the Veda run

The record is now published as Cui et al., *The Effects of Generative AI on High-Skilled Work: Evidence from Three Field Experiments with Software Developers* ([official Management Science article](https://pubsonline.informs.org/doi/10.1287/mnsc.2025.00535)). The publisher describes randomized access experiments at Microsoft, Accenture, and an anonymous Fortune 100 company, with 4,867 developers combined; its abstract reports 26.08% more completed tasks (standard error 10.3%), noisy and varying results across experiments, and larger adoption/productivity gains for less-experienced developers. The paper identifies the AEA registration as AEARCTR-0014530.

Veda's selected records for DOI `10.1257/rct.14530` and `10.1257/rct.14530-1.0` were metadata-only; neither supplied a passage, and neither appears as a supporting citation in the saved report. The earlier 2025 AEA conference abstract described a preliminary two-experiment/1,974-developer version ([AEA conference record](https://www.aeaweb.org/conference/2025/program/1916)); it is not interchangeable with the later three-experiment publication. The final live report omitted this directly relevant positive workplace evidence.

### Experienced open-source developers — not retrieved into the Veda run

Becker et al., *Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity* ([arXiv record and abstract](https://arxiv.org/abs/2507.09089), [METR study page](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)) reports a randomized controlled trial in which 16 experienced open-source developers completed 246 tasks in projects they had known for about five years. Issues were randomized to allow or disallow early-2025 AI use; the reported completion-time outcome was 19% longer when AI was allowed. The authors describe the result as setting-specific and caution that it does not establish effects for other developers or software work. The source was not among the live job's 14 selected records and is absent from its report. This is important counterevidence and an observed retrieval/coverage gap.

### Two related but distinct mixed-method field-study records — report citations S2 and S6

The report used both papers to discuss developer experience, but then characterized field research as focusing on experience “not measured output” and said the abstracts do not report productivity outcomes. The author-hosted primary manuscripts show that description is too broad:

- *Developers' Experience with Generative AI -- First Insights from an Empirical Mixed-Methods Field Study* ([arXiv manuscript](https://arxiv.org/abs/2512.19926)) links to DOI `10.1145/3786583.3786870`. Its abstract describes controlled and uncontrolled periods with GitHub Copilot and reports task duration, task completion/accuracy, and perceived workload. It reports that moderate use of in-code suggestions or chat improved controlled-session efficiency, while combined/excessive use reduced those benefits.
- *Developers' Experience with Generative AI Beyond Productivity Assessment -- Insights from an Empirical Mixed-Methods Field Study* ([arXiv manuscript](https://arxiv.org/abs/2607.02337)) links to DOI `10.1145/3847122`. Its abstract describes controlled data-collection sessions plus natural work periods and reports perceived efficiency/productivity, task efficiency, and workload differences by interaction type.

The ACM landing pages were not accessible to this audit tool (HTTP 403), so the arXiv author manuscripts establish manuscript identity and abstract content; publisher-page metadata, full methods, sample sizes, overlap between the studies, and whether either study's controlled findings generalize to ordinary work remain unverified here. The common authors and similar workplace setting mean the two records should not automatically be treated as independent replications. Both were abstract-only in Veda's saved run, and the full text was not part of its evidence.

## Quality findings for this report

1. The Copilot 55.8% statement is traceable to the cited abstract and is materially qualified by the paper's one-task experimental design. The full paper adds an important sample and 95% interval that the Veda report did not include.
2. The report's broad characterization of the two mixed-method studies as having no measured productivity/output outcomes conflicts with their primary abstracts. The first explicitly measures task duration and task completion/accuracy in controlled sessions; the second reports controlled task-efficiency comparisons. The report should distinguish controlled-task measures from perceived productivity in natural work.
3. The report does not include the directly relevant three-company randomized field evidence or the METR experienced-developer slowdown study. Consequently, its explanation that findings differ because of experiment/field/interview designs was not tested against the most directly contrasting workplace studies.
4. The two field-study records are separate papers but may share research context or data. Their independence was not established from the abstract-only Veda material; treating them as two independent confirmations would be unwarranted.
5. These checks establish source identity and correct the coverage assessment; they do not validate the full report, estimate an overall causal effect, or establish scientific reliability.

## Sources

- Peng et al. (2023), arXiv:2302.06590: [abstract and version record](https://arxiv.org/abs/2302.06590); [full text PDF](https://arxiv.org/pdf/2302.06590).
- Cui et al. (2026), *Management Science*: [publisher article page](https://pubsonline.informs.org/doi/10.1287/mnsc.2025.00535); [AEA 2025 preliminary conference abstract](https://www.aeaweb.org/conference/2025/program/1916).
- Becker et al. (2025), arXiv:2507.09089: [arXiv version/abstract](https://arxiv.org/abs/2507.09089); [METR study page](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/).
- Brandebusemeyer et al. (2025), arXiv:2512.19926, related DOI `10.1145/3786583.3786870`: [author manuscript](https://arxiv.org/abs/2512.19926).
- Brandebusemeyer et al. (2026), arXiv:2607.02337, related DOI `10.1145/3847122`: [author manuscript](https://arxiv.org/abs/2607.02337).
