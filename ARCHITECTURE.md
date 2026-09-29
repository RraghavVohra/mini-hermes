# Mini-Hermes — Architecture & Decisions

A small self-improving agent, built one atomic piece at a time. This doc tracks what's built and *why* — updated as the build progresses.

## System overview (target, not yet built)

```mermaid
flowchart TD
    U[User message] --> L[Core Agent Loop]
    L --> T[Tool Layer]
    L --> S[Skill System]
    L --> N[Periodic Nudge]
    N --> S
    L --> M[Cross-session Memory]
    L --> R[Response]
    R -.next turn.-> L
```

## Roadmap

| Step | Piece | Status |
|---|---|---|
| 1 | Core Agent Loop (message history, tool schema, tool-call parsing, execution, stop-condition — no wrapper) | ⏳ Pending |
| 2 | Tool Layer (small real tool set) | ⏳ Pending |
| 3 | Skill System (Markdown files, description-routed retrieval, `skill_manage`) | ⏳ Pending |
| 4 | Periodic Nudge (self-review at intervals, decides what's worth persisting) | ⏳ Pending |
| 5 | Cross-session Memory (SQLite, salvaged pattern from Billie's storage foundation) | ⏳ Pending |
| 6 | CLI Interface (interactive chat loop) | ⏳ Pending |

## Explicit backlog (not V1)

Multi-provider abstraction · Messaging gateways (Telegram/Slack/etc.) · Sandboxed execution (Docker) · Subagents/parallel workstreams · FTS5 full-text search.

---

*Each step below gets filled in with Theory → Design → Product+Cost → Implementation as it's built.*