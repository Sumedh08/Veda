# ADR-0044: Do not persist unverified provider abstracts as selected-source evidence

- **Status:** Accepted
- **Date:** 2026-10-31
- **Decision owners:** Veda engineering

## Context

ADR-0043 stopped candidate-ledger rows from copying provider abstracts without item/version rights. The selected-source path still persisted the same abstract text into `Source.abstract_excerpt`, then created abstract-only document snapshots, passages, and claims during extraction. Discovery-provider identity and a separate full-text location license do not establish that the exact abstract excerpt belongs to that licensed version or may be persistently stored and displayed. OpenAlex distinguishes its CC0 dataset from externally sourced abstract text and location-scoped licenses; Crossref distinguishes reusable metadata from abstract copyright. Primary-source findings are recorded in `docs/research/candidate-abstract-retention-rights-2026-10-31.md`.

## Decision

1. Discovery may use a provider abstract transiently in memory for topic eligibility and query-aligned ranking. Persisted candidate and selected-source records retain only bibliographic metadata, relevance features, and a bounded abstract-availability/retention status.
2. A newly selected scholarly source with no retrieved rights-permitted full-text representation is stored as `metadata_only`. Provider abstract text is not written to `Source.abstract_excerpt`, and the extraction stage does not turn a provider abstract into document, passage, or claim evidence.
3. A retrieved HTML, PDF, or structured JATS representation continues through its existing source/version, host, license, and parser checks. Its passages remain eligible for extraction under those existing checks; the policy concerns the separate provider-supplied abstract snapshot.
4. Deferred continuation creates a new child evidence graph without copying legacy `abstract_only` document snapshots, passages, or claims linked to those passages. The parent report and source records remain unchanged. Full-text and official-statistics evidence still copies with lineage.
5. Report coverage and source inspection state how many provider abstracts were omitted and why. This is an evidence-coverage limitation; it must not be represented as full-text coverage.
6. Do not bulk-delete or rewrite historical source, passage, claim, or report text. Existing records remain subject to a separate item/version rights and display review. This ADR is not legal advice and does not claim end-to-end rights clearance.

## Alternatives considered

1. **Keep abstract fallback under a provider-wide metadata license.** Rejected because the license may cover bibliographic metadata while third-party abstract text remains separately copyrighted.
2. **Treat a full-text location license as permission for the metadata abstract.** Rejected because the excerpt is not linked to that location's exact document version and rights scope.
3. **Remove abstract text from discovery before ranking.** Rejected because transient use can still improve lexical eligibility/ranking while the text need not be persisted as evidence.
4. **Rewrite or delete historical reports and passages.** Rejected because that would destroy preserved research provenance and alter user artifacts; legacy rights status remains explicit work.

## Consequences

- New reports can have fewer source-reported claims when only metadata abstracts are available. This is deliberate and should lower evidence sufficiency rather than create unverified evidence.
- Candidate ranking can still use ephemeral provider text, but no provider abstract is persisted as evidence without a future exact rights decision.
- No relational schema migration is required: the availability and retention fields live in the existing source metadata JSON; existing reads remain compatible.
- Legacy abstract-only rows remain in the parent database. A continuation does not re-use their abstract evidence, while full-text evidence remains eligible for lineage copying.

## Verification

- `test_selected_source_abstract_is_not_persisted_as_evidence_without_item_version_rights` first failed with the exact stored excerpt, then passed after the policy change; it also checks no abstract claim is created and the report discloses the omission.
- `test_continuation_does_not_reuse_legacy_abstract_passages_or_claims` first failed because the child copied the stored excerpt, then passed after the child graph excluded the legacy abstract document/passage/claim while the parent report remained unchanged.
- Licensed JATS and HTML extraction tests confirm their full-text passages continue to be stored and linked. Targeted/full results are recorded in `evaluation/RESULTS.md`.
