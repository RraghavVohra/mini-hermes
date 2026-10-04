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