# T-136 Europe PMC full-text workflow smoke — 2026-11-01

## Outcome

The opt-in, model-disabled real-browser run completed the Veda job and opened the persisted report's citation in the source inspector. The source was *Soil bacterial networks are less stable under drought than fungal networks* (DOI [10.1038/s41467-018-05516-7](https://doi.org/10.1038/s41467-018-05516-7), PMCID PMC6072794). Europe PMC metadata matched the article identity and reported `CC BY`; Veda stored `rights_decision=PERMITTED` for this route. Europe PMC `fullTextXML` returned HTTP 200. This validates this specific JATS acquisition path; it is not legal advice or blanket permission for other sources.

| Item | Recorded result |
|---|---|
| Job | `45aeb884-b675-4cd5-83b3-1e29070e84b2` |
| Report | `9e0f3d09-a12f-4f55-9556-4571c9ab895a` |
| Retained database | `evaluation/veda-fulltext-smoke-20261101T050325.sqlite3` (ignored SQLite artifact; new path, no overwrite) |
| Operational status | `completed_with_limitations`; deterministic preliminary evidence map |
| Discovery | Crossref 3 queries / 9 results; OpenAlex 3 queries / 8 results; 17 candidate ledger records; 5 selected sources |
| Target source | Selected and cited as S1; `full_text_jats`; 12 persisted passages; 13 extracted claim records |
| Document provenance | `veda-structured-xml` parser v1; raw-document SHA-256 `c71893185b1c8049ee47287de8141f389774d2b522a27d58952d242708d8dd5c`; source version includes the hash and parser version |
| Model usage | Provider explicitly disabled; 0 model calls, 0 usage-ledger rows, 0 estimated inference cost; no AI appraisal, synthesis, or semantic citation review |
| Browser | Playwright real API/browser case passed 1/1; citation link integrity reported `passed`; source inspector showed Europe PMC retrieval, `PERMITTED`, Methods/Results availability and JATS Methods/Results passages |

The persisted Methods passages identify the soil collection site and long-run local climate context. The Results passage states that bacterial and fungal communities were affected differently by drought. The stored record is partial: bounded extraction selected 12 passages, did not retain the original XML bytes, and does not establish that all method/result/limitation evidence was reviewed. The report remains provisional/limited and should not be treated as a scientific conclusion.

## Defect found and corrected

The first selected-source smoke used a broad question and failed its DOI assertion. It had selected four other records; a Europe PMC identity lookup for a preprint returned `article_metadata_unavailable`. This showed that merely setting the expected DOI in the E2E harness does not force source selection. A bounded exact-title check returned the target article first from both Crossref and OpenAlex; a separate article-specific query then completed the real workflow. The failed database remains preserved as `evaluation/veda-fulltext-smoke-20261101T045814.sqlite3`.

The first article-specific report was job `eff40b70-68af-4be4-8300-5eee346a1302`, report `218dee07-4a31-4e76-a566-ef26589a98f4`, database `evaluation/veda-fulltext-smoke-20261101T050025.sqlite3`. Inspection found that the generic `(?<=[.!?])\\s+` splitter treated `Fig.` as an ending and created the invalid claim fragment `1).`. A regression first failed on that fragment. `split_evidence_sentences` now protects common scholarly abbreviations and is used by structured JATS/TEI, HTML, and PDF extraction. The persisted post-fix report contains the complete result sentence ending `(Fig. 1).` and no orphan `1).` claim. A follow-up regression also proves source private-use characters are preserved byte-for-character through splitting. This improves passage segmentation; it does not appraise the claim's scientific support.

## Cost and limitations

No model inference or OpenAlex content-file endpoint was called. The real run did make bounded public Crossref, OpenAlex Works metadata, and Europe PMC metadata/full-text GET requests. The run record does not contain provider-account billing/credit settlement for those metadata/retrieval requests; no OpenAlex file download charge was incurred by this workflow. The failed broad-question run and the earlier wrong-path preflight are retained separately; the latter failed before server startup and sent no provider requests.

This artifact proves one licensed JATS-to-passage-to-citation/browser path. It does not prove the developer-productivity literature was retrieved comprehensively, model-assisted research success, semantic citation accuracy, human review, benchmark improvement, or production readiness. The same exact DOI result was not hard-coded into production source selection.
