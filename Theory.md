# Mini-Hermes — Theory Notes

Full depth of what's been researched and learned, step by step. `DECISIONS.md` has the compressed "what we decided"; this file has the "why it works this way," with examples. Read this when `DECISIONS.md` isn't enough to jog memory.

---

## Step 1 — Core Agent Loop

### What is an "agent," really

An agent is **a loop that calls an LLM repeatedly until a task is done.** Nothing magical.

| Chatbot | Agent |
|---|---|
| User message → LLM → text response. Done. | User message → LLM → **tool call** → tool execution → result back to LLM → maybe another tool call → ... → final text response. |
| **One round-trip.** | **Multiple round-trips, in a loop.** |
| LLM decides WHAT to say. | LLM decides WHAT to DO, then WHAT to say. |

### The 5-Step Flow (verified from OpenAI's official docs, developers.openai.com/api/docs/guides/function-calling)

Tool calling is **"a multi-step conversation between your application and a model via the OpenAI API."** Five high-level steps:

1. **Make a request to the model with tools it could call.** You send the user's message plus a list of available tools (as JSON schemas).
2. **Receive a tool call from the model.** If the model decides a tool is needed, it responds with a tool call (name + arguments) instead of plain text.
3. **Execute code on the application side with input from the tool call.** **The LLM never executes anything itself** — your code parses the arguments and runs the actual function.
4. **Make a second request to the model with the tool output.** You send the tool's result back as a `tool`-role message.
5. **Receive a final response from the model (or more tool calls).** The model either answers in text, or makes another tool call — in which case the loop repeats from step 2.

This repeats until the model stops calling tools.

### Four core concepts inside the loop

**1. Message History**

The single most important data structure. A Python list of messages, each with a `role`:
- `system` — instructions (persona, rules)
- `user` — the user's input
- `assistant` — the model's response (text or tool_call)
- `tool` — a tool's execution result

**This list IS the agent's working memory for a task.** The model has no memory of its own — the full list is sent on every single API call. Forget to include a message, and the model "forgets" it happened.

This is *short-term, within-task* memory — different from Billie's Mem0-based *long-term, cross-session* memory. Both matter, for different jobs.

**2. Tool Schema (JSON Schema format)**

Each tool is described to the model as a JSON schema — the model never sees the actual function, only this description:

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read contents of a file from disk.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Absolute path to the file"
        }
      },
      "required": ["path"],
      "additionalProperties": false
    },
    "strict": true
  }
}
```

`strict: true` uses OpenAI's structured-outputs feature to **guarantee** valid JSON arguments matching the schema — without it, argument generation is "best-effort" and can occasionally be malformed.

**Description quality matters enormously.** OpenAI's own best practice, verbatim: *"Pass the intern test. Can an intern/human correctly use the function given nothing but what you gave the model? If not, what questions do they ask you? Add the answers to the prompt."*

**3. Tool Call Parsing + Execution**

When the model wants to use a tool, the response looks like:

```json
{
  "role": "assistant",
  "tool_calls": [
    {
      "id": "call_abc123",
      "type": "function",
      "function": {
        "name": "read_file",
        "arguments": "{\"path\": \"/home/user/notes.txt\"}"
      }
    }
  ]
}
```

Our code then:
1. Reads `tool_calls` from the response.
2. Looks up `function.name` to find which real function to run.
3. JSON-parses `function.arguments`.
4. Executes the actual function.
5. Appends the result back into the message list as `role: "tool"`.

This is a **dispatch mechanism** — a map from tool-name to real Python function. **This is our code, not the LLM's.** This is also exactly where safety/validation belongs — the model can *ask* for a dangerous action, but our dispatcher decides whether to actually do it.

**4. Stop Condition**

The loop ends when:
- The model's response has **no tool_calls** — just text. (Normal, successful exit.)
- **Max iterations** is hit — a safety cap (we chose 15) in case the model loops without resolving.
- An **unrecoverable error** occurs.

### Pseudocode — the whole loop in ~25 lines

```
function agent_loop(user_message, tools, system_prompt, max_iterations=15):

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    for i in range(max_iterations):
        response = call_llm_api(messages, tools)

        if response has tool_calls:
            messages.append(response.message)
            for each tool_call in response.tool_calls:
                result = dispatch_tool(tool_call.name, tool_call.arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })
        else:
            return response.message.content

    return "Error: max iterations reached without completing the task."
```

Everything else we build (skills, nudge, memory, persona) wraps **around** this loop — not inside it.

### Loops vs. DAGs — when to use which

A common (and partially wrong) instinct is "DAGs are always better for reliability." Not true — it depends on the task shape:

| Situation | Use |
|---|---|
| Task is open-ended, model decides the next action | **Loop** (agent loop) |
| Workflow is fixed, steps known in advance | **DAG** (pipeline) |
| Mix — fixed pipeline with one agentic step inside | **DAG with a loop node** |

Example from Billie: the safety pipeline (Gate 1 → Gate 1b → Gate 2 → response) was always going to run in that exact order — that's a **DAG**, not a loop. Mini-Hermes's Core Agent Loop, by contrast, is genuinely open-ended — the model decides how many tool calls it needs and in what order. That's a **loop** by nature.

### AI Engineering's real scope (beyond "just call the LLM")

The LLM is the reasoning engine — everything else is engineering around it. Six real concerns:

1. **Orchestration** — loop, DAG, or hybrid, chosen per task shape.
2. **Context + Memory management** — short-term (message history) and long-term (cross-session).
3. **Reliability + Error Recovery** — retries, fallbacks, fail-closed/fail-open defaults.
4. **Evaluation + Prompt Ops** — how you test the agent is actually doing the right thing.
5. **Cost engineering** — auditing every call: is it necessary? Is the cheapest adequate model being used? Can caching help?
6. *(implicit in all of the above)* **Product thinking** — does this component actually serve the agent's single verb (GROW)?

---

*Next theory entry will be added here when Step 2 (Tool Layer) research is done.*

# Theory: Core Agent Loop (V1 Component 1)

*Built and verified during Chat 08 — Mini Hermes in the Making.*
*Date: 2026-10-07*

---

# Theory: Core Agent Loop (V1 Component 1)

*Built and verified during Chat 08 — Mini Hermes in the Making.*
*Date: 2026-10-07*

---

## 1. What is an Agent?

A regular LLM just **talks**. An agent **does things**.

The model is like a manager locked in a room with no hands. It can think, but it cannot touch the outside world. Our code is the assistant whose hands do the work.

The manager writes a note saying "multiply 17 and 23." The assistant (our code) does the work and writes the result on a note: "391." The manager reads the note. Either asks for more work, or gives the final answer. This back-and-forth continues until the answer is final.

This back-and-forth IS the agent loop. Without it, the model only talks. With it, the model acts. Every agent framework (Hermes, ChatGPT agents, LangChain, CrewAI) has this loop at its core.

---

## 2. The Agent Loop

The loop has a clear sequence that repeats: the user asks a question, and the loop sends the full history to the model. The model responds with either a final answer (no tools needed) or one or more `function_call` items asking for tools. If tools are requested, our code runs each one, appends the results to the history, and sends everything back. The loop repeats until the model gives a final answer or a safety brake kicks in.

**Key rule:** the model NEVER executes a function. It only outputs "which function to call, with what arguments." Our code parses that, runs the function, and sends the result back.

**Why a bounded loop (not while True)?** A bug in a while loop can become an infinite loop, and every iteration costs money. A `for` loop with a max bound (`MAX_ITERATIONS = 15`) guarantees the loop always stops, even if the model keeps asking for tools forever.

---

## 3. Responses API vs Chat Completions

### What changed and why

Our model (`gpt-5.6-luna`) is a **reasoning model**. OpenAI's official docs say reasoning models work better with the Responses API (improved intelligence and tool usage). Starting with GPT-5.4, Chat Completions has restrictions on tool calling with certain reasoning_effort values. Responses API is recommended for all new projects.

### Items, not Messages

In Chat Completions, input and output are **messages** (role + content). In Responses API, input and output are **items** — a flat list that can contain messages, function_call, function_call_output, AND reasoning items. This matters because the loop must handle ALL item types, not just messages.

### Tool definition shape

Chat Completions nests the tool definition inside a `function` key: `{"type": "function", "function": {"name": "multiply", "parameters": {...}}}`. Responses API keeps it flat: `{"type": "function", "name": "multiply", "parameters": {...}}`.

### Tool result shape

Chat Completions uses `{"role": "tool", "tool_call_id": "...", "content": "391"}`. Responses API uses `{"type": "function_call_output", "call_id": "...", "output": "391"}`.

### call_id: the pairing mechanism

Every `function_call` item from the model carries a `call_id`. When we send the result back, we include the SAME `call_id` in the `function_call_output`. This is how the model knows which result belongs to which request. Without it, the API rejects the call.

---

## 4. History Replay (Manual State Management)

### Two ways to maintain conversation state

The first way is `previous_response_id`: OpenAI stores the state on their server. Simpler code, but we cannot see or control the history. The second way is manual replay (`store=False`): we own the history list. Every output item is appended to our list, and the full list is sent on the next call. We chose manual replay for transparency and learning value.

### The replay rule

After every API call, we take ALL output items (reasoning, messages, function calls — everything) and append them to our history list. We do not pick and choose. The docs say reasoning items from the last function call must be passed back so the model keeps its thinking thread.

### The model_dump() bug (Experiment 02)

Plain `item.model_dump()` emits every unset field as `None`, including `async_` (Python's safe rename of the API's reserved keyword `async`). The API rejected this with 400: "Unknown parameter: input[1].async_".

The fix was `item.model_dump(by_alias=True, exclude_none=True)` — this drops the None fields and uses the API's own field names.

**Lesson:** Mock tests prove our logic; a real API run proves the API's contract. Both are needed. This bug was invisible to 28 mock tests and only appeared on the first real run.

---

## 5. Reasoning Models: How They Think

### What are reasoning tokens?

Before answering, reasoning models use internal **reasoning tokens** to "think" — break down the problem, consider approaches, plan tool calls. These tokens are invisible via the API (we cannot read what the model thought), but they occupy space in the context window and are billed as output tokens.

### reasoning_effort: the cost lever

This parameter controls how much the model thinks. Supported values for Luna: `none`, `low`, `medium` (default), `high`, `xhigh`, `max`. We use `low` because it is suited for tool use, planning, and multi-step decisions, and it optimizes for speed and cost. We raise to `medium` only if our own evals show a clear quality gain.

### reasoning_tokens are a SUBSET of output_tokens

This is the most important billing fact. In the usage object, `output_tokens` ALREADY INCLUDES `reasoning_tokens`. For example, if `output_tokens` is 1186 and `reasoning_tokens` is 1024, then the visible text used only 162 tokens (1186 - 1024). If you add reasoning on top of output, you double-count and your cost formula is wrong.

We verified this in Experiment 02: `reasoning <= output` was True on all 3 calls, and `total_tokens == input_tokens + output_tokens` was True on all 3 calls.

### Reasoning across model families

Reasoning is reusable across `gpt-5.6-sol`, `terra`, and `luna`. So if we later use Terra for a heavy stage (like skill creation), the reasoning history from Luna calls will still work. This is why per-stage model switching is safe.

---

## 6. Stop Conditions (4 Safety Brakes)

The loop must ALWAYS stop. Four conditions guarantee this.

**`completed`:** Model returned no function_call items. The reply is the final answer. This is the happy path.

**`max_iterations`:** Loop hit the configured limit (15). The model kept asking for tools, but we stop to prevent infinite billing.

**`incomplete`:** The API's `response.status` is `"incomplete"`, meaning the token cap (`MAX_OUTPUT_TOKENS`) was hit. This can happen mid-reasoning, meaning we pay for reasoning tokens but get no visible answer.

**`run_budget`:** The run's cost (in USD) crossed the per-run cap (`MAX_RUN_COST_INR = 15`). Checked AFTER recording cost but BEFORE running tools, so a finished answer always wins over the cap, and we do not do more work on a run we are about to stop.

### Priority order

First, record cost (always, even on incomplete). Then check: is the response incomplete? Stop. No function calls? Stop, completed. Over budget? Stop, run_budget. Otherwise, run the tools and loop again. If out of iterations after all that, stop with max_iterations.

---

## 7. Cost Tracking: Tokens to Money

### The four token buckets

Every API response reports usage with these buckets, each priced differently:

| Bucket | What it is | Luna price (per 1M) |
|--------|-----------|---------------------|
| Ordinary input | New text the model hasn't seen | $0.20 |
| Cached input (cache read) | Prefix that matched the cache | $0.02 (10% of input) |
| Cache write | First time a prefix is written to cache | $0.25 (1.25x input) |
| Output | Everything the model generates (including reasoning) | $1.20 |

### The formula

The ordinary input is calculated as: `input_tokens - cached_tokens - cache_write_tokens`. Then the total cost is: `(ordinary_input × input_price + cached_tokens × cached_price + cache_write_tokens × input_price × 1.25 + output_tokens × output_price) / 1,000,000`.

### Two traps to avoid

First, `input_tokens` INCLUDES cached and cache_write tokens. If you price all of input_tokens at $0.20, you overpay (cached should be $0.02). Subtract cached and cache_write first.

Second, `output_tokens` INCLUDES reasoning_tokens. Never add reasoning on top. They are already in the output total.

### Real numbers from Experiment 02

3 iterations, answer 782, cost **$0.000162 (₹0.0143)**. At this rate, ₹300 budget allows roughly 21,000 runs. Real tasks with file-reading tools will cost more, but budget is safe.

---

## 8. Prompt Caching: The Prefix Shortcut

### How it works

Caching is NOT a separate system to sync with history. It is pure **prefix matching** done by OpenAI on their end.

Every time we send history, OpenAI checks: "does the beginning of this input match something I already processed?" If yes, that matched part is read from cache (cheap). The rest is processed fresh (normal price).

In round 1, we send `[A]` and OpenAI processes it fresh and caches it. In round 2, we send `[A][B]` and OpenAI reads `[A]` from cache (cheap) and only processes `[B]` fresh. In round 3, we send `[A][B][C]` and OpenAI reads `[A][B]` from cache (cheap) and only processes `[C]` fresh.

### No sync needed

There is no sync problem because we always send the full history, OpenAI always checks from the start how much matches, and our history never edits old items — it only appends new ones at the end. So the prefix grows monotonically, and the cache match grows with it.

### Cache breaks if you change the middle

If round 3 sends `[A][X][C]` instead of `[A][B][C]`, then only `[A]` matches cache. `[X]` and `[C]` are both treated as new. Cache matches from the start, continuously. One change in the middle breaks the match for everything after it. This is why our loop never edits history items — only appends.

### The cache-write fee (GPT-5.6 specific)

Before GPT-5.6, cache writes were free. Now they cost 1.25x the normal input rate. This means a prompt sent only once costs MORE with caching than without (you paid 1.25x to write, and never read it back). But a prompt sent 2+ times saves money (each read is only 10%). Our loop sends the same prefix 3-5 times per run, so caching should help once the history is long enough to trigger it.

### The analogy

You go to office every day and show your ID to the guard. Day 1, the guard checks your full ID carefully (cache write, expensive). Day 2 onward, the guard recognizes you and waves you through (cache read, cheap). But you still bring your ID every day. Cache does not mean you stop sending the data.

### Experiment 02 observation

All 3 calls showed `cached=0, cache_write=0`. Input was too small (72-152 tokens) to trigger caching. Real tasks with larger history will show caching in action.

---

## 9. Tool Execution: Fail-Resilient, Never Crash

### Why tools can fail

The model WROTE the tool name and arguments. Any of these can be wrong: unknown tool name, invalid JSON in arguments, wrong argument names (model invented them), or the tool itself throws an exception.

### The rule: run_tool_call never raises

Every failure becomes an `"Error: ..."` string in the `function_call_output`. The model sees the error and can retry. A crash would end the whole run; an error message lets the model self-correct. Every `call_id` MUST receive a `function_call_output`, even on failure. The model is waiting for an answer to each call it made.

### Tool output cap (MAX_TOOL_OUTPUT_CHARS = 10,000)

Tool results go into history, and history is replayed on EVERY subsequent iteration. A tool that returns a 1MB file would be re-billed on every round. The cap truncates large outputs and adds `[output truncated]`.

### Parallel tool calls

The model can ask for multiple tools in one response. The loop runs ALL of them and appends ALL their results before going to the next round. Order is preserved.

---

## 10. Config as Single Source of Truth

### Why config.py exists

Billie's lesson: model names and constants were scattered across files, making cost audits hard. `config.py` is the ONE place where model name, limits, prices, and budget live. Changing the model is a one-line edit.

### What lives there

| Constant | Purpose |
|----------|---------|
| `MODEL_NAME` | Which model to call. |
| `REASONING_EFFORT` | How much the model thinks (cost lever). |
| `MAX_ITERATIONS` | Loop's round limit. |
| `MAX_OUTPUT_TOKENS` | Per-call token cap. |
| `MAX_TOOL_OUTPUT_CHARS` | Tool output truncation limit. |
| `MAX_RUN_COST_INR` | Per-run cost brake. |
| `MONTHLY_BUDGET_INR` | Documented monthly cap. |
| `PRICING_USD_PER_1M` | Per-model price table. |
| `USD_TO_INR` | Approximate exchange rate. |
| `OPENAI_API_KEY` | Loaded from `.env`, crashes at import if missing. |

### Fail closed principle

A missing key, a missing price entry, or an unknown model CRASHES at startup with a clear message. Not mid-loop where it is hard to debug.

---

## 11. Testing Strategy: Two Levels

### Level 1: Mock tests (free, fast, 46 tests)

FakeClient replays scripted responses. FakeItem and SimpleNamespace mimic SDK objects. Tests prove our logic handles every stop condition, every error path, and every edge case (parallel calls, truncation, unknown tools). Cost is zero, speed is under 3 seconds.

### Level 2: Real API runs (cheap, necessary)

The `experiments/` folder holds integration runs. These prove the API accepts what we send (the contract). They caught the `async_` bug that 28 mock tests missed. Rule: every component that talks to the API needs both levels.

---

## 12. What We Built

| Piece | File | What it does |
|-------|------|-------------|
| Config | config.py | Single source of truth for all settings and prices. |
| Parse | agent_loop.py | Read the model's tool requests (get_function_calls, parse_arguments). |
| Execute | agent_loop.py | Run tools safely, never crash (run_tool_call). |
| Replay | agent_loop.py | Convert SDK items for replay (to_input_item). |
| Loop | agent_loop.py | The full agent loop with 4 stop conditions (run_agent). |
| Cost | cost.py | Price each call, sum across the run (calculate_cost_usd, add_usage). |
| Tests | tests/ | 46 mock tests + 3 real experiments. |
| Decisions | DECISIONS.md | Every architectural choice, with reasoning. |

This is V1 Component 1: the Core Agent Loop. It can think, use tools, track its own cost, and stop safely. Next: the Tool Layer gives it real hands (file read, file write), and the Skill System lets it learn (GROW).