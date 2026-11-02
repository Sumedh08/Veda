# ADR-0045: Withhold legacy abstract-derived text at read time

- **Status:** Accepted
- **Date:** 2026-10-31
- **Decision owners:** Veda engineering

## Context

ADR-0043 prevents candidate-ledger text from being retained without item/version-specific reuse rights. ADR-0044 prevents new selected-source provider abstracts from becoming evidence passages or claims. Those controls did not resolve the older records already persisted before the policies changed: source excerpts, abstract-only passages, claims and exact report prose remained available through API and export surfaces without a rights record. Bulk rewriting or deleting those records would damage historical provenance and could not establish what rights applied when the text was acquired.

## Decision

1. Keep historical database rows unchanged. Apply a read-time, default-deny policy to source abstracts and passages with `abstract_only` or legacy `abstract_excerpt` access labels.
2. Permit display only when `abstract_text_rights_decision_v1` is bound to the exact source ID, provider identity, document version, text SHA-256, explicit retention/display scope, a nonempty license identifier, an HTTPS evidence URL and a decision timestamp. A provider-level license or availability field is insufficient. This record is an auditable decision input; Veda does not independently validate the legal interpretation or the evidence URL.
3. When unverified abstract-derived text is present, withhold source excerpts, passages, claim wording and spans, associated claim/source appraisal prose, report prose and verification free text from API and account/report exports. Retain identifiers, citation links, hashes, safe status fields and non-text provenance needed to inspect the records.
4. Keep source inspection possible from a withheld report by rendering a separate citation index linked to the retained source records. The source inspector continues to show access class, rights status and a fixed withholding notice, not the excerpt.
5. Use a conservative report-level rule: any source in the report's job with unverified abstract text can withhold the saved report body, even if that source is not cited. This avoids trying to infer which report sentences depend on which abstract without reliable claim-level provenance.
6. Do not migrate or rewrite historical rows. A future ingestion or rights-review workflow must populate the exact grant fields only after a responsible rights decision; no user-facing grant editor is introduced by this change.

## Alternatives considered

1. **Continue displaying old text because it was already stored.** Rejected: historical storage does not establish display or reuse rights.
2. **Delete or rewrite legacy records.** Rejected: that would destroy preserved research state and still would not resolve the rights question.
3. **Remove the entire historical report and citation graph from the API.** Rejected: source identity, citation links, hashes and rights metadata remain useful for audit, and the source inspector can display those safely.
4. **Redact only exact matching substrings from the report body.** Rejected: paraphrases and appraisals can reproduce or depend on the excerpt, and robust phrase matching cannot identify all derived prose.

## Consequences

- Legacy report prose may be less available until exact rights records are established; stored data itself remains unchanged.
- Citation links and bibliographic source records remain inspectable, while passage contents and associated appraisal prose stay withheld.
- Rights decisions are not automatically inferred, verified or generated. The exact-grant record is a gate, not a legal opinion.
- Reports can be over-withheld when any job source has an unverified abstract, including uncited sources. This is an explicit conservative limitation.
- No database migration is needed; API schemas add optional withholding fields with backward-compatible defaults.

## Verification

- `test_unverified_legacy_abstract_text_is_withheld_from_api_and_exports` checks both legacy access labels, including that stored source, passage, claim and report rows remain intact, model-derived source appraisal prose is withheld, and report/account Markdown/JSON exports do not disclose the excerpt.
- The same test adds a positive control: an exact source/version/text-hash grant permits source, passage and report display.
- Browser journeys verify that withheld report prose does not remove the ability to open the cited source, that the source inspector shows a withholding notice, that full-text-linked claim spans still work, and that the report/source inspector remain usable at mobile widths and pass the tested axe rules.
- No provider inference, scholarly network request or schema migration was used.
