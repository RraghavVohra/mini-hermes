"""
Experiment 02: the first REAL run of the agent loop.

Story: 28 tests proved the loop's logic with a scripted FakeClient. They
cannot prove that the real API accepts what the loop sends back (replayed
items), or that the model handles a multi-step chain. This run does. One
tiny question that FORCES two dependent tool calls.
"""
from openai import OpenAI

import config
import cost
from agent_loop import run_agent

class RecordingClient:
    """Wraps the real client and remembers every response's usage.

    Story: run_agent only returns totals. To CHECK the docs' claims we need
    each call's own usage, so this wrapper records them as they pass through.
    """

    def __init__(self, real_client):
        self._real = real_client
        self.responses = self  # so client.responses.create(...) works
        self.usages = []

    def create(self, **kwargs):
        response = self._real.responses.create(**kwargs)
        self.usages.append(response.usage)
        return response


client = RecordingClient(OpenAI(api_key=config.OPENAI_API_KEY))

# Same flat tool definition as Experiment 01.
TOOLS = [
    {
        "type": "function",
        "name": "multiply",
        "description": "Multiply two numbers and return the product.",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
            "additionalProperties": False,
        },
    }
]


def multiply(a, b):
    return a * b


# Tool name -> Python function. The Tool Layer will build this later.
REGISTRY = {"multiply": multiply}

# The second multiplication depends on the first result, so the model
# cannot do both at once. It needs at least two loop rounds plus a final
# answer round.
result = run_agent(
    client,
    "What is 17 times 23, and then multiply that result by 2? "
    "Use the multiply tool for every step.",
    TOOLS,
    REGISTRY,
)

print("stop_reason:", result.stop_reason)
print("iterations:", result.iterations)
print("final answer:", result.final_text)

# What the loop replayed to the model, item by item.
print("\nhistory:")
for i, item in enumerate(result.history):
    kind = item.get("type") or item.get("role")
    detail = ""
    if kind == "function_call":
        detail = f"{item['name']}({item['arguments']})"
    elif kind == "function_call_output":
        detail = f"output = {item['output']}"
    print(f"  {i}: {kind} {detail}")


# --- cost report (piece 4b) ---
print("\ncost this run: $%.6f  (about Rs %.4f)" % (
    result.cost_usd, cost.usd_to_inr(result.cost_usd)))
print("token totals from the loop:", result.tokens)

print("\nper-call usage (docs check):")
for i, u in enumerate(client.usages, start=1):
    d = u.input_tokens_details
    r = u.output_tokens_details.reasoning_tokens
    print(
        f"  call {i}: input={u.input_tokens} cached={d.cached_tokens} "
        f"cache_write={d.cache_write_tokens} output={u.output_tokens} "
        f"reasoning={r} total={u.total_tokens}"
    )
    print("    total == input + output:", u.total_tokens == u.input_tokens + u.output_tokens)
    print("    reasoning <= output:", r <= u.output_tokens)

print(
    "\nloop total input matches the recorded calls:",
    result.tokens["input"] == sum(u.input_tokens for u in client.usages),
)