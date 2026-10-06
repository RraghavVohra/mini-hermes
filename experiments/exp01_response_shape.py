"""
Experiment 01: look at the raw shape of a Responses API reply.

Story: before writing the loop, we SEE what the model sends back. The loop
is just code that reacts to these items, so knowing them first means no
guessing later. Nothing here is the final loop.
"""
from openai import OpenAI

import config

client = OpenAI(api_key=config.OPENAI_API_KEY)

# A flat tool definition (Responses style, no nested "function" key).
# We only DESCRIBE the tool here. The model never runs it, and neither do
# we in this experiment. We just want to see the call it asks for.
tools = [
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

# store=False: we own the history (Decision B). Effort and the output cap
# come from config.py, so this experiment obeys the same cost rules as the
# real loop.
response = client.responses.create(
    model=config.MODEL_NAME,
    reasoning={"effort": config.REASONING_EFFORT},
    max_output_tokens=config.MAX_OUTPUT_TOKENS,
    store=False,
    input=[{"role": "user", "content": "What is 17 times 23? Use the multiply tool."}],
    tools=tools,
)

print("status:", response.status)
print("number of output items:", len(response.output))

# response.output is a flat list of items. The loop will branch on item.type.
for i, item in enumerate(response.output):
    print(f"\n--- item {i}: type = {item.type}")
    if item.type == "function_call":
        print("name:", item.name)
        print("call_id:", item.call_id)
        # arguments arrives as a JSON STRING, not a dict. The loop must parse it.
        print("arguments (raw):", repr(item.arguments))
    if item.type == "reasoning":
        # In stateless mode the reasoning item carries opaque encrypted
        # content that we must replay later. We never read it.
        print("has encrypted_content:", getattr(item, "encrypted_content", None) is not None)

# Usage is where cost tracking will come from (piece 4).
usage = response.usage
print("\ninput_tokens:", usage.input_tokens)
print("cached_tokens:", usage.input_tokens_details.cached_tokens)
print("output_tokens:", usage.output_tokens)
print("reasoning_tokens:", usage.output_tokens_details.reasoning_tokens)