# Candidate abstract retention rights review

**Reviewed:** 2026-10-31  
**Scope:** Abstract text copied into Veda's scholarly discovery-candidate ledger and selected-source evidence records. This is a conservative engineering policy, not legal advice.

## Findings from primary provider documentation

- OpenAlex describes its dataset as CC0, while warning that title, abstract, and affiliation text comes from external sources and is passed through as-is. Its Works reference also says plaintext abstracts are not shipped for legal reasons and that clients reconstruct them from an inverted index. These statements do not establish that an individual abstract is licensed for Veda's persistent copy, display, or redistribution. [OpenAlex API reference](https://help.openalex.org/api/) · [Works attributes](https://help.openalex.org/data/works/attributes/)
- OpenAlex records licenses at individual work locations; the license belongs to a particular copy, not universally to the work or every representation. An abstract snapshot from the discovery record is not currently linked to an exact licensed document version. [OpenAlex license vocabulary](https://help.openalex.org/data/licenses/)
- Crossref says most deposited metadata may be reused, but deposited abstracts retain publisher/author copyright unless a reuse right applies. [Crossref metadata documentation](https://www.crossref.org/documentation/retrieve-metadata/)

## Veda policy

Veda retains no abstract text in discovery-candidate rows unless a future item- and version-specific rights record explicitly clears the text and its intended retention/display use. The current discovery workflow does not establish that link, so it records `not_retained_item_text_rights_unverified` for candidates with an abstract excerpt and `not_available` when there is none.

The candidate ledger continues to retain bibliographic identifiers, title, provider, exact query and retrieval time, relevance features, selection disposition, and exclusion reason. A reviewer can follow the source link for further review. This keeps selection decisions inspectable without treating an API dataset license as an article-text license.

This policy is scoped to candidate snapshots. It does not by itself resolve rights for abstract passages already represented in selected-source evidence records; that separate source-level behavior must remain visible as an open legal/provenance review item.

## Selected-source evidence path review

The discovery workflow also used provider abstracts in-process for topical eligibility and ranking. Before T-132, it copied selected records' excerpts into `Source.abstract_excerpt`; the extraction stage then stored abstract-only document snapshots, passages, and claims after full-text attempts. The excerpt did not have an item/version text-retention decision. A provider's location license for a full-text copy was not sufficient evidence that a separate metadata excerpt came from that version or that its text could be retained and displayed.

T-132 therefore separates transient discovery use from durable evidence use. The workflow may still use the provider excerpt in memory to compare candidate relevance against the user question and exact retrieval query. The persisted selected-source row keeps only whether an excerpt was available and its retention outcome. It is classified as `metadata_only` until a supported, rights-permitted full-text representation is retrieved. The extraction stage no longer makes provider-abstract passages or claims. Deferred continuation runs also omit legacy abstract-only document snapshots, passages, and their dependent claims; the original parent evidence and report are not rewritten.

This change prevents new unverified abstract evidence from being created and prevents deferred child runs from copying legacy abstract evidence. It does not retroactively erase or suppress abstract text already persisted in historical source, passage, claim, or report records. Those records remain a separate rights-review item, and Veda does not claim end-to-end rights clearance.
