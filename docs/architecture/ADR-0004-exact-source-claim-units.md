# ADR-0004: Conservative exact-span source claim units

- Status: Accepted
- Date: 2026-10-29
- Scope: sentence extraction, claim persistence, report provenance, and claim inspection

## Context

A retrieved source sentence can state more than one empirical proposition. Treating that entire sentence as one indivisible claim makes appraisal and comparison coarse. Splitting every conjunction or asking another model to paraphrase propositions creates different risks: common noun phrases can be mistaken for separate claims, generated wording can drift from the source, and another model call consumes the run's bounded budget. Exact quotation provenance is more important than maximizing the number of extracted claims.

## Decision

1. Veda keeps the original retrieved passage and stores each claim unit as an exact substring with a half-open `[start, end)` interval measured in Unicode code points. Claim text must equal that source slice at persistence time; invalid offsets or mismatches are discarded.
2. Version 1 splits only a small set of explicit clause boundaries (semicolons and selected contrast/temporal markers), and only when every resulting clause has an explicit subject token before a conservative finite-predicate vocabulary. It does not split on `and`. Attribution-only and uncertain compound clauses remain one claim and carry `compound_unatomized`; ordinary unsplit sentences carry `whole_sentence`.
3. The rule is deterministic and does not add a model call. It does not assert that clauses are logically independent, true, causally identified, methodologically sound, or semantically supported. Those questions remain in the separate appraisal, comparison, and semantic-support stages.
4. Persisted claims carry an atomization version/status and nullable span fields for compatibility. The migration backfills legacy claims as whole-passage spans, and a uniqueness constraint prevents duplicate claim spans within the same job and passage version.
5. The claims API, report verification manifest, and claim inspector expose the original sentence, exact interval, version, status, and a visual highlight only when the interval still resolves to the exact stored claim text. A mismatch is shown without highlighting.

## Evidence and verification

- Local deterministic tests exercise semicolon and contrast boundaries, an uncertain attribution clause, conjunctions, exact non-overlapping intervals, and Unicode code-point offsets.
- A workflow integration test confirms two claims from one source sentence share one passage, retain exact text/offsets, appear in the evidence API, and are listed in the report verification manifest.
- A browser fixture verifies the report manifest opens the claim inspector and highlights the exact source substring.
- SQLite migration round-trip and Alembic model comparison verify the schema change. These checks do not establish PostgreSQL deployment behavior or scientific validity.

## Consequences and limits

- Conservative rules intentionally leave many compound or syntactically complex sentences unsplit. This can reduce granularity but avoids inventing unsupported text.
- A syntactically explicit clause is not necessarily an independent proposition. Status describes segmentation only, never evidence quality.
- The predicate vocabulary is English-oriented and versioned; other languages and uncommon constructions should remain whole until an evaluated, language-aware approach is available.
- Offsets identify the exact stored passage representation, not a page-level location in a publisher PDF. The passage's own locator remains the source location.
- No additional OpenRouter/OpenAI call or provider charge is required.
