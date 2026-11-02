# T-112 retrieval quality audit

**Question:** Does generative AI improve software developer productivity, and why do empirical studies sometimes report different findings?

**Boundary:** This is a read-only replay of the isolated SQLite candidate/source ledger from the one authorized T-112 run. It is a small, unlabeled snapshot, not a precision/recall evaluation or a scientific-quality score.

## Discovery and filtering record

- Four Crossref queries returned 20 records; four OpenAlex queries returned 11. The persisted discovery ledger contains 31 candidate occurrences: 12 selected, 15 excluded for `insufficient_topic_overlap`, and 4 excluded as duplicate canonical identities.
- The four plan queries covered the base question, study population/setting and dates, comparable coding-assistance outcomes and a counterevidence query, plus limitations/cost/measurement. Discovery was real; claim comparison and counterevidence analysis did not complete because the model response truncated.
- The lexical score and topic gate are deterministic query/title/abstract text-overlap features. They do not assess study design, evidence quality, source type, causal validity or claim support. The selection reason `selected_by_relevance` is therefore not an endorsement.
- Eight of the 12 selected records have abstract passages; four are metadata-only. Excluded candidate abstracts are not retained in this metadata-only candidate ledger, so a title-level exclusion cannot be confidently labeled a false negative from this saved run. The stored relevance features expose matched abstract terms without reproducing excluded abstracts.

## Reproduced positive error and offline correction

The selected OpenAlex record **“An Empirical Study of Generative AI Adoption in Software Engineering”** had an `abstract_excerpt` beginning “This repository contains analyses and data related to the paper.” The remaining excerpt inventories Jupyter notebooks, raw survey/qualitative data, images and the original survey tool. This is repository/readme text, not a study abstract or empirical finding. Its topical overlap was high (`ai`, `empirical`, `generative`, `software`), which explains why the lexical filter selected it but does not make it evidence.

Added `is_repository_artifact_description` as a narrow text-type check. It requires both a leading repository inventory statement and at least two concrete artifact cues. Discovery now retains such records in the candidate ledger with reason `repository_artifact_description_not_abstract`, and records an exclusion count. The guard runs before topic-overlap selection. It does not reject all abstracts that mention repositories, datasets or software artifacts, and it is not a study-quality classifier.

Regression coverage includes the captured mislabel pattern, a study abstract that mentions a generative-AI assistant, the real discovery-stage disposition, its saved reason, and the event count. This proves the deterministic code path, not that every provider metadata corruption pattern is detected.

## Borderline exclusion and remaining unknowns

The excluded OpenAlex record **“Generative AI at Work”** matched `ai`, `generative` and `productivity` in its saved overlap features but failed the direct software/developer topic gate. It may be useful as contextual evidence about different occupations and outcomes, but it is not direct evidence about software developers. Without a persisted abstract excerpt or reviewer label, calling it a false negative would be speculative. A future contextual-comparison retrieval lane should distinguish adjacent populations from direct-scope findings rather than weakening the direct-evidence gate.

Other selected metadata illustrates scope variation: 12-senior-engineer interviews concern professional identity; 30-expert interviews concern sociotechnical impacts; an industry-focused perception study is not necessarily a GenAI intervention study; and a narrative review summarizes a corpus rather than providing a new controlled estimate. The selected set also has several incomplete provider-capped abstracts. T-114 now stores truncation provenance and excludes a known-incomplete final fragment from deterministic extraction, but the historical T-112 report is unchanged.

The counterevidence query was planned and issued to the scholarly metadata providers, but no model-supported classification of mixed/negative findings, study comparability, or explanations for disagreement was produced. No full text was retrieved. No claim about the overall effect of GenAI on developer productivity follows from this audit.

## Follow-up

1. Preserve direct-scope filtering and use a separately labeled contextual lane for adjacent populations only if the user scope calls for it.
2. Keep metadata-only candidate records and rejection reasons inspectable; do not store excluded abstracts solely to make this one replay easier.
3. Human relevance labels and paired reviewer adjudication remain necessary under T-38/B-010 before reporting retrieval precision, recall or research quality.
