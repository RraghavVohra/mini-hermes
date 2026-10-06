"""
Tests for agent_loop.py, piece 2.

Story: we fake the model's output items with SimpleNamespace, so these
tests cost nothing and need no network.
"""
from types import SimpleNamespace

import pytest
from openai.types.responses import ResponseFunctionToolCall

import agent_loop
import config


def make_item(item_type, **fields):
    return SimpleNamespace(type=item_type, **fields)


def test_get_function_calls_returns_only_function_calls():
    items = [
        make_item("reasoning"),
        make_item("function_call", name="multiply", call_id="c1", arguments="{}"),
        make_item("message"),
    ]
    calls = agent_loop.get_function_calls(items)
    assert len(calls) == 1
    assert calls[0].call_id == "c1"


def test_get_function_calls_returns_empty_list_when_there_are_none():
    assert agent_loop.get_function_calls([make_item("message")]) == []


def test_get_function_calls_keeps_parallel_calls_in_order():
    items = [
        make_item("function_call", call_id="c1"),
        make_item("function_call", call_id="c2"),
    ]
    calls = agent_loop.get_function_calls(items)
    assert [c.call_id for c in calls] == ["c1", "c2"]


def test_parse_arguments_accepts_the_exact_string_from_experiment_01():
    assert agent_loop.parse_arguments('{"a":17,"b":23}') == {"a": 17, "b": 23}


def test_parse_arguments_rejects_invalid_json():
    with pytest.raises(ValueError):
        agent_loop.parse_arguments('{"a":17,')


def test_parse_arguments_rejects_json_that_is_not_an_object():
    with pytest.raises(ValueError):
        agent_loop.parse_arguments("[1, 2]")

# --- run_tool_call (piece 3a) ---

def make_call(name="multiply", call_id="c1", arguments='{"a":17,"b":23}'):
    return SimpleNamespace(name=name, call_id=call_id, arguments=arguments)


def multiply(a, b):
    return a * b


def test_run_tool_call_returns_a_paired_output_item():
    out = agent_loop.run_tool_call(make_call(), {"multiply": multiply})
    assert out["type"] == "function_call_output"
    assert out["call_id"] == "c1"
    assert out["output"] == "391"  # 17 * 23, converted to a string


def test_run_tool_call_passes_string_results_through_unchanged():
    out = agent_loop.run_tool_call(make_call(), {"multiply": lambda a, b: "done"})
    assert out["output"] == "done"


def test_run_tool_call_reports_unknown_tool_instead_of_crashing():
    out = agent_loop.run_tool_call(make_call(name="nope"), {"multiply": multiply})
    assert out["call_id"] == "c1"
    assert out["output"].startswith("Error:")


def test_run_tool_call_reports_invalid_json_instead_of_crashing():
    out = agent_loop.run_tool_call(make_call(arguments='{"a":'), {"multiply": multiply})
    assert out["output"].startswith("Error:")


def test_run_tool_call_reports_tool_exceptions_instead_of_crashing():
    def broken(a, b):
        raise RuntimeError("disk on fire")

    out = agent_loop.run_tool_call(make_call(), {"multiply": broken})
    assert "disk on fire" in out["output"]


def test_run_tool_call_reports_wrong_argument_names():
    # The model can invent argument names; the error text lets it retry.
    out = agent_loop.run_tool_call(make_call(arguments='{"x":1}'), {"multiply": multiply})
    assert out["output"].startswith("Error:")


def test_run_tool_call_truncates_huge_outputs():
    big = "x" * (config.MAX_TOOL_OUTPUT_CHARS + 500)
    out = agent_loop.run_tool_call(make_call(), {"multiply": lambda a, b: big})
    assert out["output"].endswith("[output truncated]")
    assert len(out["output"]) < len(big)


# --- run_agent (piece 3b) ---
# Story: a FakeClient replays scripted replies, so the whole loop is tested
# with zero API calls and zero cost.

class FakeItem:
    """Mimics an SDK output item: has attributes AND model_dump()."""

    def __init__(self, item_type, **fields):
        self.type = item_type
        self.__dict__.update(fields)

    def model_dump(self, **kwargs):
        # Accepts the flags the real SDK takes (by_alias, exclude_none).
        return dict(self.__dict__)


def call_item(call_id="c1", name="multiply", arguments='{"a":17,"b":23}'):
    return FakeItem("function_call", name=name, call_id=call_id, arguments=arguments)


def reply(items, status="completed", text=""):
    return SimpleNamespace(status=status, output=items, output_text=text)


class FakeClient:
    """Plays back scripted replies and records every request it receives."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.requests = []
        self.responses = self  # so client.responses.create(...) works

    def create(self, **kwargs):
        # Copy the input list: the loop keeps appending to the real one, and
        # we want to see what was sent AT THE TIME of each request.
        self.requests.append({**kwargs, "input": list(kwargs["input"])})
        return self._replies.pop(0)


REGISTRY = {"multiply": multiply}
TOOLS = [{"type": "function", "name": "multiply"}]


def test_run_agent_completes_when_model_answers_without_tools():
    client = FakeClient([reply([FakeItem("message")], text="hi")])
    result = agent_loop.run_agent(client, "hello", TOOLS, REGISTRY)
    assert result.stop_reason == "completed"
    assert result.final_text == "hi"
    assert result.iterations == 1


def test_run_agent_runs_the_tool_then_returns_the_final_answer():
    client = FakeClient([
        reply([call_item()]),
        reply([FakeItem("message")], text="391"),
    ])
    result = agent_loop.run_agent(client, "17 x 23?", TOOLS, REGISTRY)
    assert result.stop_reason == "completed"
    assert result.final_text == "391"
    assert result.iterations == 2
    second_input = client.requests[1]["input"]
    assert second_input[1]["type"] == "function_call"
    assert second_input[-1] == {
        "type": "function_call_output", "call_id": "c1", "output": "391",
    }


def test_run_agent_replays_every_output_item_including_reasoning():
    client = FakeClient([
        reply([FakeItem("reasoning"), call_item()]),
        reply([FakeItem("message")], text="done"),
    ])
    agent_loop.run_agent(client, "go", TOOLS, REGISTRY)
    types = [item.get("type") for item in client.requests[1]["input"]]
    # First entry is the user message (a dict with no "type" key).
    assert types == [None, "reasoning", "function_call", "function_call_output"]


def test_run_agent_answers_every_parallel_call_in_order():
    client = FakeClient([
        reply([call_item("c1"), call_item("c2")]),
        reply([FakeItem("message")], text="done"),
    ])
    agent_loop.run_agent(client, "go", TOOLS, REGISTRY)
    outputs = [
        item for item in client.requests[1]["input"]
        if item.get("type") == "function_call_output"
    ]
    assert [o["call_id"] for o in outputs] == ["c1", "c2"]


def test_run_agent_stops_at_max_iterations():
    # The model keeps asking for tools forever; the loop must still stop.
    client = FakeClient([reply([call_item()]) for _ in range(3)])
    result = agent_loop.run_agent(client, "go", TOOLS, REGISTRY, max_iterations=3)
    assert result.stop_reason == "max_iterations"
    assert len(client.requests) == 3


def test_run_agent_reports_incomplete_responses():
    client = FakeClient([reply([], status="incomplete", text="")])
    result = agent_loop.run_agent(client, "go", TOOLS, REGISTRY)
    assert result.stop_reason == "incomplete"
    assert result.iterations == 1


def test_run_agent_sends_tool_errors_back_and_keeps_going():
    client = FakeClient([
        reply([call_item(name="nope")]),
        reply([FakeItem("message")], text="recovered"),
    ])
    result = agent_loop.run_agent(client, "go", TOOLS, REGISTRY)
    assert result.stop_reason == "completed"
    error_output = client.requests[1]["input"][-1]
    assert error_output["output"].startswith("Error:")


def test_run_agent_sends_the_configured_settings():
    client = FakeClient([reply([FakeItem("message")], text="ok")])
    agent_loop.run_agent(client, "go", TOOLS, REGISTRY)
    sent = client.requests[0]
    assert sent["model"] == config.MODEL_NAME
    assert sent["store"] is False
    assert sent["max_output_tokens"] == config.MAX_OUTPUT_TOKENS
    assert sent["reasoning"] == {"effort": config.REASONING_EFFORT}
    assert sent["tools"] == TOOLS


# --- to_input_item (regression for the async_ bug found in Experiment 02) ---
# Story: FakeItem could never reveal this bug because it always dumped clean
# dicts. These tests use a REAL SDK item, built locally with no API call.

def make_real_function_call():
    return ResponseFunctionToolCall(
        arguments='{"a":17,"b":23}',
        call_id="call_test",
        name="multiply",
        type="function_call",
    )


def test_to_input_item_drops_the_none_fields_the_api_rejects():
    dumped = agent_loop.to_input_item(make_real_function_call())
    assert "async_" not in dumped
    assert None not in dumped.values()


def test_to_input_item_keeps_the_fields_the_api_needs():
    dumped = agent_loop.to_input_item(make_real_function_call())
    assert dumped == {
        "arguments": '{"a":17,"b":23}',
        "call_id": "call_test",
        "name": "multiply",
        "type": "function_call",
    }