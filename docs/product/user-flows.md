# User flows

1. **Sign in:** use managed authentication in production; local development offers a clearly labeled local session only when explicitly enabled.
2. **Start project:** create a project with title, domain and context; open its research workspace.
3. **Research:** submit a question, context, geography/population/time horizon, depth and cost ceiling. The server stores an immutable request snapshot.
4. **Advance and resume:** browser asks the server to execute one bounded step. Timeline reflects persisted stage events. Refresh or browser closure does not erase completed work.
5. **Inspect evidence:** source access level, metadata, passages, linked claims and appraisal missingness are shown with citations.
6. **Read result:** report separates source-reported findings from synthesis, shows audit limitations and provides Markdown/JSON export.
7. **Follow up:** start a child job in the same project and retain earlier reports and evidence.
8. **Manage data:** download an owner-scoped JSON export; archive and restore projects; choose a retention window for future archives; or permanently delete an archived project after exact-title confirmation. Expiration requires deployment maintenance to be scheduled. Identity-provider account deletion is not available in Veda.

