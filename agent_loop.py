"""
agent_loop.py: the Core Agent Loop of mini-Hermes.

Story: built in pieces, each tested alone before the next is added.
Piece 2 (this step): read what the model asked for. These are pure
functions with no API calls, so they can be tested for free.
"""
from dataclasses import dataclass
import json
import config


def get_function_calls(output_items) -> list:
    """Return only the function_call items from a response's output.

    Why filter by type: response.output is a mixed list (reasoning items,
    messages, function calls). Experiment 01 showed a reply can be JUST a
    function_call, and harder tasks may add reasoning or message items.
    The model can also ask for several calls in one response, so we return
    a list, never "the" call.
    """
    return [item for item in output_items if item.type == "function_call"]


def parse_arguments(raw_arguments: str) -> dict:
    """Turn the model's JSON string into a dict.

    Why this can fail: arguments arrives as a string the model wrote
    (Experiment 01 showed '{"a":17,"b":23}', not a dict), and a model can
    occasionally emit invalid JSON. We raise ValueError with a clear
    message so the loop can hand the error BACK to the model
    (fail-resilient) instead of crashing.
    """
    try:
        parsed = json.loads(raw_arguments)
    except json.JSONDecodeError as err:
        raise ValueError(f"Tool arguments were not valid JSON: {err}") from err
    if not isinstance(parsed, dict):
        raise ValueError("Tool arguments must be a JSON object")
    return parsed

def run_tool_call(call, registry: dict) -> dict:
    """Run ONE function_call and return its function_call_output item.

    Why this never raises: the model wrote the tool name and arguments, so
    any of them can be wrong. A crash would end the whole run; an
    "Error: ..." string lets the model see what went wrong and try again
    (fail-resilient). Every call_id must get an answer, so even failures
    return a proper output item.

    `registry` maps tool name -> Python function. It is passed in (not
    imported) so tests can use fake tools, and the real registry from the
    Tool Layer can be plugged in later.
    """
    try:
        func = registry.get(call.name)
        if func is None:
            raise ValueError(f"Unknown tool: {call.name}")
        args = parse_arguments(call.arguments)
        result = func(**args)
        # The API wants output as a string, so non-strings become JSON.
        text = result if isinstance(result, str) else json.dumps(result)
    except Exception as err:  # deliberate: any tool failure goes back to the model
        text = f"Error: {err}"

    # Cost guard: results are re-sent on every later iteration.
    if len(text) > config.MAX_TOOL_OUTPUT_CHARS:
        text = text[: config.MAX_TOOL_OUTPUT_CHARS] + "\n[output truncated]"

    return {
        "type": "function_call_output",
        "call_id": call.call_id,  # pairs this result with the model's request
        "output": text,
    }

def to_input_item(item) -> dict:
    """Convert an SDK output item into a dict we can send back as input.

    Why not plain model_dump(): Experiment 03 showed it also emits every
    unset field as None, including 'async_' (a Python-safe rename of the
    API's 'async'). The API rejects that with 400 "Unknown parameter:
    input[1].async_". exclude_none drops the unset fields; by_alias uses
    the API's own field names if a set field ever needs renaming.
    """
    return item.model_dump(by_alias=True, exclude_none=True)

@dataclass
class AgentResult:
    """What a finished run hands back to the caller (CLI, tests).

    stop_reason is part of the result so the caller can tell the user WHY
    the agent stopped, instead of hiding limit hits as if they were answers.
    """
    final_text: str
    stop_reason: str  # "completed" | "max_iterations" | "incomplete"
    iterations: int
    history: list


def run_agent(client, user_message, tools, registry, max_iterations=None) -> AgentResult:
    """The Core Agent Loop.

    Story: send history -> read the reply -> if the model asked for tools,
    run them, append the results, and go round again -> stop when it
    answers, or when a safety limit hits.

    `client` is passed in (not created here) so tests can hand in a fake
    one that replays scripted replies for free.
    """
    if max_iterations is None:
        max_iterations = config.MAX_ITERATIONS

    # We own the history (store=False), so the whole conversation lives here.
    history = [{"role": "user", "content": user_message}]

    # A bounded for-loop: a bug cannot turn into an infinite, billed loop.
    for iteration in range(1, max_iterations + 1):
        response = client.responses.create(
            model=config.MODEL_NAME,
            reasoning={"effort": config.REASONING_EFFORT},
            max_output_tokens=config.MAX_OUTPUT_TOKENS,
            store=False,
            input=history,
            tools=tools,
        )

        # Replay EVERY output item (reasoning, messages, function calls).
        # The docs say reasoning items must go back so the model keeps its
        # thread, and we cannot predict which items a reply will contain.
        history.extend(to_input_item(item) for item in response.output)

        # Stop reason 1: the token cap was hit (possibly mid-reasoning).
        if response.status == "incomplete":
            return AgentResult(response.output_text, "incomplete", iteration, history)

        # Stop reason 2: no tool requested, so this reply is the answer.
        calls = get_function_calls(response.output)
        if not calls:
            return AgentResult(response.output_text, "completed", iteration, history)

        # Run every requested tool (the model may ask for several at once).
        # Errors become "Error: ..." outputs and the loop continues.
        for call in calls:
            history.append(run_tool_call(call, registry))

    # Stop reason 3: still asking for tools after the last allowed iteration.
    return AgentResult("", "max_iterations", max_iterations, history)