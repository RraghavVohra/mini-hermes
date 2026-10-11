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

## 2026-10-06: Core Agent Loop built (agent_loop.py, pieces 2-3)

- **Decision:** `run_agent` uses a bounded `for` loop (range of `max_iterations`) instead of a `while` loop.
- **Why:** Same behavior as the planned while-loop, but a bug cannot become an infinite, billed loop. Supersedes the "while-loop" wording of Decision 4.

- **Decision:** `client` is passed into `run_agent` instead of being created inside it.
- **Why:** Tests hand in a scripted FakeClient, so the full loop is tested with zero API calls and zero cost.

- **Decision:** `run_tool_call` never raises. Any failure (unknown tool, invalid JSON, tool exception, wrong argument names) returns an `"Error: ..."` function_call_output for the same `call_id`.
- **Why:** Fail-resilient principle. The model sees the error and can retry. Every `call_id` must receive an output.

- **Decision:** Tool output is capped at `MAX_TOOL_OUTPUT_CHARS` (10,000, about 2,500 tokens), set in `config.py`.
- **Why:** Tool results are replayed in history on every later iteration, so a big result is re-billed again and again.

- **Decision:** Every item in `response.output` is replayed into history through `to_input_item` (`model_dump(by_alias=True, exclude_none=True)`).
- **Why:** Plain `model_dump()` emitted unset fields as None, including `async_`, and the API rejected it with 400 "Unknown parameter: input[1].async_". Found by the first real run (Experiment 02), invisible to mock tests. SDK version at the time: openai 3.24.0. The `by_alias` part is not yet tested against a field that has a real value, `exclude_none` is the proven fix.

- **Lesson:** Mock tests prove our logic; a real API run proves the API contract. Every component that talks to the API needs both. Keep experiments/ runs as the integration check.

- **Verified (Experiment 02):** a real two-step dependent tool chain on `gpt-5.6-luna` completed in 3 iterations, answer 782, with a reasoning item replayed correctly.

- **Open items:** cost tracking (piece 4) and a budget-based stop. History grows every iteration; OpenAI docs list a Compaction feature for that, not yet researched. Revisit only when history size becomes a real cost.

## 2026-10-07: Cost tracking added (Piece 4)

- **Decision:** cost.py prices each token bucket separately: ordinary input, cached input (cache read), cache-write (1.25x input for GPT-5.6), and output. Reasoning tokens are NOT added on top of output — they are a subset.
- **Why:** Official docs confirm input_tokens includes cached and cache_write tokens, and output_tokens includes reasoning tokens. Experiment 02 real run verified both: `total == input + output` and `reasoning <= output` were True on all 3 calls.

- **Decision:** `run_agent` sums cost across all calls and returns it with the result. A per-run cost cap (`MAX_RUN_COST_INR = 15`) stops the loop before running more tools if the cap is crossed. A finished answer always wins over the cap.
- **Why:** The loop replays growing history on every iteration, so a broken run can burn money. The cap fires only on actual anomalies; normal runs cost far less (Experiment 02: Rs 0.0143 for a 3-iteration chain).

- **Observation (Experiment 02):** no prompt caching happened (cached=0, cache_write=0 on all calls). Input is too short to trigger it. Watch for caching effects when real tools produce longer history. Cache-write fee (1.25x) means a large prompt sent only once costs MORE with caching than without.

- **Observation:** input tokens grew 72 → 120 → 152 across 3 iterations (history replay). Manageable now; revisit when tools produce large outputs. Compaction is in the backlog.

- **Decision:** `PRICING_USD_PER_1M` in config.py is the single source of truth for per-model prices. A test verifies MODEL_NAME has an entry; another verifies every entry has all required fields.
- **Why:** Switching models without adding pricing would silently break cost tracking (fail closed).

- **Note:** `USD_TO_INR = 88.0` is an approximate rate, not a verified live rate. It affects only the rupee display, not the underlying USD math.

## 2026-10-08: Tool Layer started, workspace jail (Piece 2a)

- **Decision:** The agent's file tools are confined to one folder, `WORKSPACE_DIR` (`workspace/` inside the project). Every file tool must call `safe_path()` before touching disk.
- **Why:** The model chooses the path, but our code touches the disk with our Windows account's permissions. A wrong guess or a prompt injection hidden in a file could otherwise reach `.env` (API key) or overwrite our own code. Chosen over "whole project" for least privilege.

- **Decision:** `safe_path` judges the resolved destination (`resolve()` then `is_relative_to(root)`), not the spelling of the path.
- **Why:** Blocking ".." as a string would reject legit `sub/../a.txt` and miss absolute paths (`C:\...`, which discard the root when joined) and symlinks. Verified by tests: traversal blocked, absolute-outside blocked, absolute-inside allowed, `sub/../a.txt` allowed, and the real workspace cannot reach `../.env`.

- **Decision:** Violations raise `PermissionError` or `ValueError`; they are never caught inside the jail. `run_tool_call` already turns them into an `"Error: ..."` output for the model.

- **Decision:** Writing skills (needed for GROW) will go through a separate, narrow `save_skill` tool later, not by widening write access to the project.
- **Why:** Least privilege.

- **Limits we accept (V1):** this is a path check, NOT a sandbox (no process isolation; containers are in the backlog). A symlink created between validation and use could bypass it (TOCTOU), acceptable for a single-user local agent.

- **Open item:** the symlink-escape test was SKIPPED on this machine (Windows account cannot create symlinks), so that protection is verified only by theory (`resolve()` follows symlinks). Re-run with symlink permission (for example Windows Developer Mode) when convenient.
- **Open item:** Windows-specific path quirks (case-insensitivity, trailing dots or spaces in names) are not tested. They are covered only because we check the resolved path, not the name.
- **Open item:** verify against OpenAI's official docs whether strict mode works with parallel tool calls (two third-party sources contradict each other) before writing the tool schemas.
- **Cost note:** tool definitions are sent as input tokens on every call, so V1 keeps to 3 tools with tight descriptions.

## 2026-10-11: Tool Layer built (registry, read_file, write_file, list_dir)

- **Decision:** All tools register through `ToolRegistry` (`tools/registry.py`), which checks the schema against the function at registration time and produces both the API `definitions()` and the loop's `functions()` dict.
- **Why:** In Experiment 02 the schema and the function lived in separate places, so a renamed argument in one would only fail on a paid API call. The registry catches the mismatch for free. It also rejects schemas that break strict-mode rules (`additionalProperties: false`, every property required, every parameter described). V1 allows only simple parameter types (no nested objects or arrays).

- **Decision:** `strict: True` is set explicitly on every tool; optional arguments are nullable types like `["integer", "null"]`.
- **Why:** If `strict` is omitted, the Responses API may silently fall back to non-strict. The official function-calling docs recommend always enabling strict. The earlier worry about strict plus parallel calls was checked against the official page: it states no such incompatibility for standard models (only a caveat for fine-tuned models). To confirm with a real parallel-call run in Piece 2d.

- **Decision:** Tool errors are written for the model: they say what went wrong and name the next tool to try (for example "Use list_dir to see what exists", "Call read_file to review it, then write again with overwrite set to true").
- **Why:** Anthropic's tool-writing guide recommends actionable errors and steering truncation messages over opaque codes. Our run_tool_call already turns every exception into an "Error: ..." output, so the message is what the model sees.

- **Decision:** `read_file` pages by lines (`start_line`, `max_lines`, default 200) and also by a character budget (`MAX_TOOL_OUTPUT_CHARS` minus a 300-character footer reserve). A footer tells the model exactly which `start_line` to call next. Files over `MAX_READ_FILE_BYTES` (2 MB) are refused.
- **Why:** Every tool result is replayed and re-billed on each later loop iteration. The page plus footer always fits under the cap, so run_tool_call's blunt truncation never fires. 200 lines is a starting value to tune after real runs (one terminal-agent paper uses 2000 as its default, but our replay cost argues for smaller).

- **Decision:** `write_file` writes atomically (temp file in the same folder, then `os.replace`), uses explicit UTF-8 with `\n` newlines, creates missing folders, and caps content at `MAX_WRITE_CHARS` (20,000).
- **Why:** A failure halfway through a direct write can corrupt the file. With a temp file the old file survives (verified by test: original intact, no temp files left behind). Windows text mode would otherwise turn `\n` into `\r\n`. A large write is billed twice: as output, then as input on every later iteration, because the content sits in the function_call in history.

- **Decision:** `write_file` takes a required boolean `overwrite`. With `overwrite=false` an existing file is never replaced, and the error steers the model to `read_file` first.
- **Why:** This is our own design choice, not from the docs. It stops the model from destroying saved work without deciding to. GROW needs updates, so overwriting stays possible, but deliberately.

- **Decision:** `list_dir` lists one level only (no recursion), folders first with a trailing slash, files with their size in bytes, capped by `MAX_LIST_ENTRIES` (200) and the same character budget. A workspace folder that does not exist yet reads as empty, and listing never creates it.
- **Why:** Recursive listings can be huge. Sizes let the model avoid reading a big file in full. Listing is for looking, not for creating folders.

- **Decision:** `workspace/` is in `.gitignore`.
- **Why:** The agent writes files there. They should never be committed by accident.

- **Limits we accept (V1):** no `fsync` (power-loss durability is not needed for a local single-user learning agent). The atomicity of `os.replace` on Windows is documented inconsistently across sources, so the guarantee we rely on is only this: if our write fails before the swap, the old file is intact. On Windows `os.replace` fails when the target is open in another program, so that error gets its own message.
- **Open item:** `list_dir` calls `is_dir()` and `stat()` on each child, and both follow symlinks, so a symlink inside the workspace pointing outside would show the type and size of its target (no content is exposed). The agent has no tool that creates symlinks, so this is low risk for now. Related to the earlier open item: the symlink-escape test is still SKIPPED on this machine.
- **Open item:** the real tools have not yet been run against the real model. Piece 2d does that, including an attack run asking for `../.env`.

## 2026-10-11: Tool Layer verified against the real model (Piece 2d, experiments/exp04_real_tools.py)

- **Verified:** the real API accepted all three strict tool definitions on the first call (nullable `["integer","null"]` and boolean parameters, strict true). No 400 error.
- **Verified:** parallel tool calls work with strict mode. In run A the model sent `read_file` and `list_dir` back to back and both ran correctly. One observation, not a guarantee, but it matches the official docs, which state no incompatibility for standard models. Closes the earlier open item.
- **Verified:** a non-ASCII (Hindi) write and read round trip through the real model; the file on disk is LF with the exact content.
- **Verified (direct attack):** the real model called `read_file("../.env")`; the jail returned "Error: Path is outside the workspace: ../.env"; the model reported it could not read it. The API key never appeared in the history or the answer.
- **Observation (indirect attack):** given a file with a hidden instruction to read `../.env`, the model summarized only the legitimate notes and never attempted the read. So this run did NOT exercise the jail; the model resisted on its own. That is not a guarantee: OpenAI's docs say agents can still be tricked, and resistance can change between model versions. The jail is the deterministic defense, independent of model behavior.
- **Decision:** keep `exp04_real_tools.py` as a regression check. Re-run it after any model change, tool change, or jail change.
- **Observation:** the agent did not warn the user that the file contained a suspicious instruction. A possible future improvement (system prompt guidance), not V1.
- **Observation:** `run_agent` sends no `instructions` (system prompt). The model works from tool descriptions alone. The Skill System and CLI will need one: a design item.
- **Cost:** all three runs together cost $0.001092 (about Rs 0.096). Run A (write, read, list; 3 iterations) cost $0.000518.
- **Closed:** the open item on strict mode with parallel calls.
- **Still open:** the symlink-escape test is skipped on this machine (Windows account cannot create symlinks); `list_dir` follows symlinks when reading type and size.

## 2026-10-11: Model switched to gpt-6-luna; run_agent made multi-turn ready

- **Decision:** `MODEL_NAME` is now `gpt-6-luna` (was `gpt-5.6-luna`). The pricing entry for `gpt-5.6-luna` stays in `config.py`, so rollback is one line.
- **Why:** Official model pages: gpt-6-luna costs $0.10 input, $0.01 cached input, $0.125 cache write, $0.50 output per 1M tokens, against $0.20, $0.02, 1.25x input and $1.20 for gpt-5.6-luna. It was missed in the first model research because that research used a third-party aggregator that listed only the GPT-5.6 family. Availability on our key was confirmed with `models.retrieve`. Same Responses API rule: function calling with reasoning needs Responses.
- **Verified (Experiment 04, same three runs on both models):** total $0.000401 on gpt-6-luna against $0.001092 on gpt-5.6-luna, about 63% lower. Behavior held: normal job passed (write, read and list, with `read_file` and `list_dir` sent back to back under strict mode, Hindi round trip intact), the hidden instruction in the file was ignored, and the API key never appeared.
- **Observation:** in the direct attack (run B) gpt-6-luna refused on its own without calling the tool, so run B no longer exercises the jail. Run D was added: it asks for `../README.md`, a path that does not look like a secret. The model called `read_file`, the jail returned "Path is outside the workspace", and the model told the user. The jail is now verified on gpt-6-luna.
- **Lesson:** re-run `exp04_real_tools.py` after any model change, and keep at least one attack case that the model's own refusal will not hide.

- **Decision:** `run_agent` takes `instructions` (the system prompt) and sends it on EVERY call. When it is None, no `instructions` key is sent.
- **Why:** OpenAI's docs say `instructions` applies only to the request it is sent with. We replay history ourselves (`store=False`), so earlier prompts are not carried over.

- **Decision:** `run_agent` takes `history` to continue an earlier conversation. It copies the list and never changes the caller's list.

- **Decision:** history must stay valid after every stop reason. On `run_budget`, every function_call that will not run gets an output saying "Not run: ...". On `incomplete`, the cut-off reply's items are dropped from history.
- **Why:** a multi-turn CLI replays history on the next turn, and a function_call without an output would very likely make that request invalid. Not triggered yet, found by reasoning ahead of the CLI. The fix is safe either way. A test checks that no stop reason (completed, max_iterations, incomplete, run_budget) leaves an open call.
- **Test change:** `test_run_agent_stops_on_run_budget_before_running_tools` used to assert there were no function_call_output items. It now asserts that every output starts with "Not run" and that the real result (391) is absent. The intent (the tool did not run) is unchanged.

- **Research for the system prompt (GPT-5.6 guidance; to be validated on gpt-6-luna):** keep the prompt lean and state each rule once; define autonomy and approval boundaries in one compact policy; avoid broad "Be concise" instructions; `text.verbosity` exists as a default-detail setting; the prompt must be static (no untrusted text interpolated).
- **Open items:** the GPT-6 prompting guidance was written for Astra, so evaluate it on Luna. The default for `reasoning.context` on gpt-6-luna was not checked (our replay of every output item works either way). Explicit prompt caching is not used yet; watch `cached_tokens` and `cache_write_tokens` in real multi-turn sessions, because cache writes cost 1.25x. The symlink test is still skipped. There is no system prompt yet.