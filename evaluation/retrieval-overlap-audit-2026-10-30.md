# Offline retrieval-filter replay

This is a deterministic replay over preserved metadata, not a labeled relevance benchmark.

## Counts

- `candidate_occurrences`: 203
- `clean_title_only_gate_passes`: 44
- `historically_selected_occurrences`: 140
- `malformed_title_occurrences`: 7
- `selected_clean_records_passing_gate`: 34
- `selected_clean_records_rejected_for_topic_overlap`: 104
- `selected_malformed_title_occurrences`: 2

## Contaminated title examples

- `doi:10.52783/jier.v6i1.4539`: Articles "Harnessing Spirituality to Combat Workplace Stress" Ritu Saxena, Vibhor Jain DOI 10.52783/jier.v6i1.4117 357 PDF: 402 PDF The Algorithmic Customer: An In-Depth Analysis of the Impact of Artificial Intelligence and Machine Learning
- `doi:10.31327/jte.v1i2.1892`: JOURNAL OF TEACHING AND EDUCATION Q U I C K M E N U FOCUS AND SCOPE EDITORIAL TEAM REVIEWERS REVIEWER GUIDELINES AUTHOR GUIDELINES PUBLICATION ETHICS INDEXING DOWNLOAD AUTHOR FEES CONTACT US USER You are logged in as... admin My Journals My
- `doi:10.52783/jier.v6i1.4539`: Articles "Harnessing Spirituality to Combat Workplace Stress" Ritu Saxena, Vibhor Jain DOI 10.52783/jier.v6i1.4117 357 PDF: 402 PDF The Algorithmic Customer: An In-Depth Analysis of the Impact of Artificial Intelligence and Machine Learning
- `doi:10.52783/jier.v6i1.4539`: Articles "Harnessing Spirituality to Combat Workplace Stress" Ritu Saxena, Vibhor Jain DOI 10.52783/jier.v6i1.4117 357 PDF: 402 PDF The Algorithmic Customer: An In-Depth Analysis of the Impact of Artificial Intelligence and Machine Learning
- `doi:10.52783/jier.v6i1.4539`: Articles "Harnessing Spirituality to Combat Workplace Stress" Ritu Saxena, Vibhor Jain DOI 10.52783/jier.v6i1.4117 357 PDF: 402 PDF The Algorithmic Customer: An In-Depth Analysis of the Impact of Artificial Intelligence and Machine Learning
- `doi:10.52783/jier.v6i1.4539`: Articles "Harnessing Spirituality to Combat Workplace Stress" Ritu Saxena, Vibhor Jain DOI 10.52783/jier.v6i1.4117 357 PDF: 402 PDF The Algorithmic Customer: An In-Depth Analysis of the Impact of Artificial Intelligence and Machine Learning
- `doi:10.52783/jier.v6i1.4539`: Articles "Harnessing Spirituality to Combat Workplace Stress" Ritu Saxena, Vibhor Jain DOI 10.52783/jier.v6i1.4117 357 PDF: 402 PDF The Algorithmic Customer: An In-Depth Analysis of the Impact of Artificial Intelligence and Machine Learning

## Regression review

- **false positive blocked:** The sPHENIX fast-data-processing/detector-control title previously passed via generic AI, processing and time overlap; the query-context filter now rejects it.
- **adjacent synonym recovered:** Designing and Evaluating Generative AI Search Tools for Human Cognitive Augmentation now passes a knowledge-retrieval query via direct title term search plus generative-AI intervention match; the paper's topical adequacy remains unverified because its abstract was not in that snapshot.

## Limits

- Candidate occurrences are not unique papers; the same record can appear in multiple queries or jobs.
- Nonselected candidate abstracts are not present in the saved runtime snapshot, so the title-only pass count is not a replay of the full discovery gate.
- Selected records have saved abstracts; rejection counts are deterministic filter outcomes, not human relevance judgments.
- No precision, recall, false-positive rate, or scientific quality score can be calculated without reviewed labels.
