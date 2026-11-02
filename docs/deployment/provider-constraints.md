# Hosting and model-provider constraints

**Source review date:** 2026-10-29. Published vendor documentation is evidence of stated plan limits, not a service-level guarantee. The Render free-tier/Blueprint/pre-deploy behavior below was refreshed against current official docs on 2026-10-29. No account or service was created and no hosted connection was tested.

## Render

- Render Free web services are preview/hobby instances; official docs state 512 MB RAM and 0.1 CPU, spin down after 15 minutes without inbound traffic, and take about a minute to wake.
- Free web filesystems are ephemeral and instances can restart. Veda's durable records must therefore live in an external database.
- Render Free Postgres is 1 GB, has no backups or managed connection pooling, and expires after 30 days. It is rejected for persistent Veda project state.
- Keep job execution client-assisted and checkpointed; browser inactivity can pause research. Do not advertise unattended completion.
- Sources: [Render Free services](https://render.com/docs/free), [Render compute plans](https://render.com/docs/compute-plans), [Blueprint YAML reference](https://render.com/docs/blueprint-spec), [pre-deploy commands](https://render.com/docs/deploys).

## PostgreSQL candidate

- Neon Free docs state no fixed plan time limit, 1 GB/project, 100 compute-unit hours/project/month, and 5 GB egress. Compute scales to zero after five minutes. Quota exhaustion suspends compute but does not delete stored data.
- Neon Free has no scheduled backups and no SLA. It offers short instant-restore history and one manual snapshot; an independently held export is required before treating it as safe for user data.
- Supabase Free integrates Postgres and Auth/JWT/RLS, but can pause after seven days of low database activity; Free has no automatic backups/PITR, and its pause guide documents a one-year restore window while post-window recovery is unknown.
- **Status:** Neon is a conditional non-production candidate only. No connection, migration, ownership test, quota test, or restore/export has been run.
- Sources: [Neon plans](https://neon.com/docs/introduction/plans), [Neon pricing](https://neon.com/pricing), [Supabase pausing](https://supabase.com/docs/guides/platform/free-project-pausing), [Supabase backups](https://supabase.com/docs/guides/platform/backups).

## OpenRouter free test provider

- Veda accepts `openrouter/free` or a model ID ending in `:free`; the service rejects other OpenRouter routes. `LLM_PROVIDER=disabled` remains the default.
- OpenRouter's official collection says `:free` routes currently have zero prompt/completion token pricing, 20 requests/minute and 50 requests/day, subject to account/provider limits. `openrouter/free` selects a currently available free model.
- OpenRouter's API is OpenAI-compatible at `/api/v1/chat/completions`; provider data handling varies. Do not send confidential research inputs until privacy/retention terms are reviewed. The one smoke prompt used no project or user research data.
- Sources: [OpenRouter free models](https://openrouter.ai/collections/free-models), [free router](https://openrouter.ai/openrouter/free), [chat completions API](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request?explorer=true).

## OpenAI

- The adapter uses the Responses API structured-output schema and does not store responses (`store: false`). The model ID and price inputs are environment-configured.
- A paid request requires `ALLOW_PAID_LLM_CALLS=true`, a nonzero job budget, and configured per-million input/output prices. `OPENAI_API_KEY` is server-only. No OpenAI key was configured and no OpenAI request was made in this build session.
- Confirm the current model and price before enabling the adapter. Sources: [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create), [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses), [pricing](https://developers.openai.com/api/docs/pricing).

