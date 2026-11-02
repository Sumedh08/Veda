# ADR-0043: Require item/version rights before retaining candidate abstract text

- **Status:** Accepted
- **Date:** 2026-10-31
- **Decision owners:** Veda engineering

## Context

T-128 made source-cap ordering auditable by persisting each candidate's exact provider query, separate question/query lexical features, disposition, and exclusion reason. A bounded abstract snapshot could help a later reviewer assess excluded records, so T-131 added nullable snapshot and retention-status fields. The initial assumption that OpenAlex's dataset-wide CC0 statement clears every abstract was too broad: its API reference says text fields are external content passed through as-is, the Works reference says plaintext abstracts are withheld for legal reasons and reconstructed from an inverted index, and the license vocabulary scopes a license to a specific location. Crossref likewise distinguishes reusable bibliographic metadata from abstract copyright.

## Decision

1. Do not copy an abstract into a discovery-candidate row unless an item- and version-specific rights record authorizes persistent storage and display of that exact text.
2. The current discovery providers do not provide Veda with an adequate text-to-version rights record. Therefore, the current policy stores no candidate abstract text and persists either `not_retained_item_text_rights_unverified` or `not_available`.
3. Keep exact query, retrieval timestamp, canonical/provider identity, lexical selection features, disposition, and exclusion reason available in the candidate API and browser.
4. Keep candidate-text rights separate from full-text rights, abstract-as-evidence handling, and the metadata dataset license. This ADR does not resolve rights for abstract passages already used in selected-source evidence records; that requires a separate source-level audit.
5. Preserve nullable fields so a future provider can retain a bounded excerpt only after adding a typed, auditable rights record tied to the exact item/version. A provider name or dataset-wide license string is insufficient.

## Alternatives considered

1. **Retain every OpenAlex excerpt under its CC0 dataset declaration.** Rejected because the provider separately identifies abstracts as externally sourced text and withholds plaintext abstracts for legal reasons; Veda does not map the excerpt to a specific licensed document version.
2. **Retain all provider abstracts for reviewer convenience.** Rejected because Crossref explicitly distinguishes abstract text from generally reusable metadata, and convenience does not establish text rights.
3. **Drop candidate audit records.** Rejected because exact query, relevance features, disposition, and exclusion reason are valuable for retrieval audit and require no abstract-text copy.

## Consequences

- Excluded candidate titles and ranking/exclusion provenance remain inspectable, while candidate abstract text is omitted when rights are unverified.
- The nullable abstract column and bounded status field are additive. Existing rows migrate with both fields null; API reads expose the legacy state as `legacy_not_recorded`.
- The frontend labels omitted text and does not claim OpenAlex abstract excerpts are CC0.
- The source-level abstract evidence path remains an explicit unresolved rights/provenance boundary; this decision must not be cited as end-to-end rights clearance.

## Verification

- A rights regression first failed because OpenAlex-provider identity alone caused the excerpt to be copied. The policy now returns no text and records the unverified-rights status for any nonempty candidate abstract.
- The workflow test verifies this status is persisted for an OpenAlex candidate. Crossref omission, missing-text distinction, candidate workflow persistence, migration round-trip, API compatibility, and frontend build/unit tests cover the changed contract.
- Primary-source findings are recorded in `docs/research/candidate-abstract-retention-rights-2026-10-31.md`.
