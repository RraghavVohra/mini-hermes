# Decisions Log — Mini-Hermes

Every non-obvious decision, with the "why," recorded as it's made.

## 2026-09-29 — Project kickoff

- **Decision:** Build mini-Hermes as a learning project, not a product. Primary goal: understand agent internals (tool-calling loop, skill-creation, self-nudge loop) from first principles, not framework composition.
- **Why:** Prior project (Billie) taught framework-integration skills (Mem0, safety layers, orchestration) but left a gap — never built the core agent loop itself, always used OpenAI's tool-calling wrapper as a black box.
- **Decision:** Single verb — **GROW**. The agent must create, use, and improve its own skills, and remember across sessions.
- **Why:** Studied Nous Research's Hermes Agent positioning ("the agent that grows with you") and confirmed via docs/GitHub/research papers that every Hermes feature serves this one verb. A single-verb identity avoids the vision-fracture that killed Billie.
- **Decision:** Repo — `RraghavVohra/mini-hermes`, public.
- **Why:** Public for portfolio value, matching the Billie postmortem's public-with-transparency approach.
- **Decision:** V1 scope — Core Agent Loop, Tool Layer, Skill System, Periodic Nudge, Cross-session Memory, CLI Interface.
- **Decision:** Explicit backlog (NOT in V1) — multi-provider abstraction, messaging gateways (Telegram/Slack/etc.), sandboxed execution (Docker), subagents/parallel workstreams, full-text search (FTS5).
- **Why (backlog):** These are integration-engineering or premature-scaling concerns, not agent-mechanics. Deferring keeps focus on the actual learning goal.
- **Decision:** Build order — Core Loop → Tools → Skills → Nudge → Memory → Interface.
- **Why:** Each piece depends on the one before it structurally (Skills need a Loop to execute them; Nudge needs Skills to exist before it's meaningful; Memory is lowest-priority this round since it was already explored deeply in Billie).
- **Decision:** Process discipline per component — Theory (research-backed) → Architecture discussion → Product + Cost lens → Code (isolated, story-commented, tested) → this file updated.
- **Why:** Billie's postmortem identified "no vision before code" and "no cost discipline" as the two structural failures. This sequence bakes both in from day one instead of bolting them on after the fact.