# ADR-0031: Persist bounded provider error classifications

- **Status:** Implemented and locally verified on SQLite migration roundtrip; PostgreSQL migration execution remains unverified.
- **Date:** 2026-10-29
- **Decision owners:** Veda engineering

## Context

The live OpenRouter run recorded 18 failed provider usage rows, but the usage export omitted the provider adapter's sanitized error code. The job stored only `model_call_uncertain`, so the run could not distinguish timeout, invalid response envelope, missing model/cost disclosure, free-route guard rejection or other provider boundary failures. Raw response bodies, prompts and credentials must not be retained to improve diagnosis.

## Decision

- Persist the adapter's bounded static `error_class` on failed usage rows, separate from the top-level retry/resume state.
- Classify transport timeouts, pre-connection failures, HTTP status, invalid JSON, unverified model/cost, refusal, truncation and schema mismatch using fixed safe codes.
- Keep response bodies, provider error messages, request content, keys and arbitrary exception text out of this field. Preserve `model_call_uncertain` as the conservative job outcome where provider completion or cost is unknown.
- Report known response cost separately; an unknown cost remains unknown and does not become zero.

## Consequences and limits

Future runs can identify the safe failure class from the usage ledger without parsing logs or retaining provider payloads. Historical live-run rows predate this column and cannot be retroactively diagnosed. The new additive migration has been exercised through SQLite upgrade/downgrade/re-upgrade and schema consistency checks; PostgreSQL remains dependent on the external integration environment.
