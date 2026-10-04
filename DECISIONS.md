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


## 2026-10-04 — Core Agent Loop: Theory + Architecture locked

### Theory studied
- **Agent = a loop that calls an LLM repeatedly until the task is done.** Not magic — a chatbot does one round-trip (message → response), an agent does multiple round-trips (message → tool call → tool execution → result → maybe another tool call → ... → final text).
- **OpenAI's 5-step tool-calling flow** (verified from official docs, developers.openai.com/api/docs/guides/function-calling):
  1. Request to model with available tools listed.
  2. Model returns a tool call (name + arguments) instead of text, if it decides a tool is needed.
  3. **Our code** executes the tool — the LLM never executes anything itself.
  4. We send the tool's result back to the model as a `tool`-role message.
  5. Model gives a final text response, OR makes another tool call (loop continues).
- **Four core concepts inside the loop:**
  - **Message history** — a list of `{role, content}` messages (system/user/assistant/tool) that IS the agent's working memory for a task. No hidden state — we send the full list every API call.
  - **Tool schema** — JSON Schema definitions describing each tool's name, description, and parameters, shown to the model (not the actual function). `strict: true` guarantees valid JSON arguments.
  - **Tool dispatch** — our own code maps a tool name to a real function, executes it, and formats the result back into the message list. This is where validation/safety checks belong.
  - **Stop condition** — loop ends when the model returns text with no tool calls, OR a max-iteration cap is hit, OR an unrecoverable error occurs.
- **Loops vs. DAGs:** loops suit open-ended tasks where the model decides the next step; DAGs suit fixed, predictable pipelines (e.g. Billie's safety pipeline: Gate 1 → Gate 1b → Gate 2 → response was a DAG, not a loop). Mini-Hermes's Core Agent Loop is a loop by nature — V1 does not need a DAG.
- **AI engineering's real scope** (beyond "call the LLM"): orchestration (loop/DAG/hybrid), context + memory management, reliability + error recovery, evaluation + prompt ops, and **cost engineering** — auditing every call's necessity and model choice.

### Architecture decisions
1. **API: Chat Completions, not Responses API.** Responses API (launched March 2025) manages state server-side, hiding exactly the internals we want to learn (message history, round-trips). Chat Completions keeps everything in our own code and matches the industry-standard format (OpenAI/Anthropic/Google all similar).
2. **Primary model: `gpt-4.1-mini`** ($0.40/M input, $1.60/M output tokens, 1M context). ~6x cheaper than `gpt-4o` ($2.50/$10.00), stronger tool-calling than `gpt-4.1-nano` ($0.10/$0.40) which can be inconsistent on tool-call decisions. Monthly budget cap: ₹50. Lightweight/classification-style calls may use `gpt-4.1-nano` later — per-stage model selection, not one-size-fits-all (direct fix for Billie's reflex-model-choice mistake).
3. **File structure (flat, V1):** `config.py` (central config — model names, paths, constants), `agent_loop.py` (the core loop), `tools/registry.py` (tool-name → function + schema mapping), `tools/` (individual tool implementations), `tests/` (isolated per-component tests), `skills/` (empty for now, populated in Step 3).
4. **Loop design:** while loop, max 15 iterations (configurable). Three stop conditions — (a) model returns text with no tool calls → normal exit, (b) max iterations hit → error + log, (c) tool execution error → error string returned to the model as a tool result, model decides next action (loop does NOT break on tool errors — this keeps the agent resilient rather than brittle).
5. **Tool registration: central registry pattern.** `TOOL_REGISTRY` dict maps tool name → `{function, schema}`. Adding a new tool means one new file + one registry entry, nothing else touched. Skills (Step 3) will plug into this same registry.
6. **Error handling philosophy:** API-level errors (network, rate limit) → retry with exponential backoff (3 attempts) then graceful exit. Tool-level errors → error string back to the model, loop continues. Unexpected errors → full traceback logged, safe message returned, no crash.

## 2026-10-04: config.py (Core Agent Loop, piece 1)

- **Decision:** `load_dotenv()` with default behavior (`override=False`).
- **Why:** Standard convention, and it will work with CI/CD secrets later. Gotcha to remember: if a key is set in the system environment AND in `.env`, the system value wins. First debugging step for any key confusion is to check the system variable.

- **Decision:** `require_env()` crashes at import time if `OPENAI_API_KEY` is missing.
- **Why:** Fail-closed principle. A missing secret should stop the program at startup with a clear message, not surface mid-loop where it is hard to debug. Trade-off: nothing can import `config` without a key, which is fine because every V1 component needs it.

- **Decision:** All constants (`MODEL_NAME`, `MAX_ITERATIONS`, `MONTHLY_BUDGET_INR`, paths) live only in `config.py`.
- **Why:** Billie lesson. Cost audits and model swaps become one-file jobs. Budget cap is documented but not enforced yet.

- **Decision:** Config tests check for mistakes (safe range for `MAX_ITERATIONS`, fail-closed behavior, paths), not copies of values.
- **Why:** A test pinned to `"gpt-4.1-mini"` would fail on every intentional model change and teach us nothing.

- **Open item (cost audit):** OpenAI's model page recommends GPT-5 mini for complex tasks, with a lower input price than `gpt-4.1-mini` ($0.25 vs $0.40 per 1M tokens). Output price not verified yet. Compare at cost-audit time; switching is a one-line change in `config.py`.

## 2026-10-04: Model and budget revised (supersedes Decision 2 of the Core Agent Loop entry)

- **Decision:** Dev default model is `gpt-5.6-luna` (replaces `gpt-4.1-mini`).
- **Why:** `gpt-4.1-mini` is an April 2025 model; the GPT-5.6 family (Sol / Terra / Luna) is current. Luna gives the best quality per rupee for agent work: roughly 10x cheaper than Terra, while one third-party agentic index puts it close to Terra. Model ID confirmed available on our key via `models.retrieve`.
- **Pricing used (per 1M tokens):** Luna $0.20 input, $0.02 cached input, $1.20 output. Source is a third-party tracker (benchlm.ai), not OpenAI's live page, so confirm against the OpenAI dashboard once real spend shows up.
- **Note:** These are reasoning models, so reasoning tokens bill as output. Real cost can exceed table-based estimates.
- **Per-stage upgrade path:** Heavier stages (e.g. skill creation) can move to Terra or Sol later. Switching is a one-line change in `config.py`.

- **Decision:** `MONTHLY_BUDGET_INR` raised from 50 to 300.
- **Why:** Rough estimate is under Re 1 per typical task on Luna, so Rs 50 allows only ~55-60 tasks, too tight for 6 components with repeated test/debug runs. Estimate ignores history growth across loop iterations, so real numbers are needed. The cap is documented in `config.py`, not enforced in code. The real guard is a spend limit/alert on the OpenAI dashboard.

- **Superseded:** the earlier open item about comparing GPT-5 mini at cost-audit time. Replaced by the Luna decision above.
- **Open item:** Decision 1 (Chat Completions vs Responses API) must be re-researched now that the model is a reasoning model. To be done before `agent_loop.py` design.

## 2026-10-04: API choice revised (supersedes Decision 1 of the Core Agent Loop entry)

- **Decision:** Use the Responses API (`client.responses.create`) instead of Chat Completions.
- **Why:** The original reason for Chat Completions was transparency and learning value, chosen when the model was `gpt-4.1-mini`. With `gpt-5.6-luna` (a reasoning model), OpenAI's reasoning guide says reasoning models work better with Responses (better intelligence and tool usage), and Chat Completions remains supported but is not the recommended path. Luna's official model page confirms function calling and Responses support.
- **Impact on the loop:** The conversation is a list of items (message, function_call, function_call_output, reasoning), not just messages. A `function_call` item in the output means keep looping; none means final answer. A fourth stop condition is added: a response with status `incomplete` (hit `max_output_tokens`) is handled explicitly.

- **Decision:** Manual history replay with `store=False`. We own the history list and replay every output item (including reasoning items) into the next call.
- **Why:** Docs say reasoning items from the last function call must be passed back so the model keeps its thread. Owning the list keeps the loop transparent for learning, and nothing is stored server-side. Alternative considered: `previous_response_id` (simpler, but state lives on OpenAI's side).
- **Bonus:** Reasoning is reusable across `gpt-5.6-sol`, `terra` and `luna`, so per-stage model switching later will not break history.

- **Decision:** `REASONING_EFFORT = "low"` and `MAX_OUTPUT_TOKENS = 25_000` live in `config.py`.
- **Why:** Reasoning tokens bill as output, so effort is a cost lever. Docs suggest `low` for tool use and multi-step decisions. Raise to `medium` only if our own evals show a clear gain. The output cap leaves room for reasoning, because hitting the cap mid-reasoning can cost money with no visible answer. Worst case at 25,000 tokens is about $0.03 per call on Luna. Tune down once real `reasoning_tokens` numbers show up in `usage`.

- **Closed:** price verification. Luna's rates ($0.20 input, $0.02 cached input, $1.20 output) match OpenAI's official model page.
- **Closed:** the Decision 1 re-research open item.

