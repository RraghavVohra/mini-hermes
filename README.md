# Mini-Hermes

A small self-improving AI agent, built from scratch to learn agent internals.

**This is a learning project, not a product.** Inspired by [Nous Research's Hermes Agent](https://github.com/nousresearch/hermes-agent), scaled down to a size where every mechanism can be understood end-to-end.

## Why this exists

Previous agent builds (see the `ai-agents-qa-journey786` portfolio, and the archived `personal-ai-agent-arch` / Billie project) always used OpenAI's tool-calling wrapper as a black box. This project builds the agent loop itself — no wrapper — to close that gap.

## The verb: GROW

Every feature here exists to serve one purpose: **the agent grows with use.** It creates skills from experience, improves them over time, and remembers across sessions — without gamification, streaks, or engagement tricks.

## Status

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full roadmap and current build status.
See [DECISIONS.md](./DECISIONS.md) for the running decision log.