"""
Tests for tools/registry.py.

Story: all free, no API. We try to register broken tools on purpose and
check that each mistake is caught at registration time.
"""
from types import SimpleNamespace

import pytest

import agent_loop
from tools.registry import ToolRegistry, object_schema

NUM = {"type": "number", "description": "A number."}


def make_registry_with_multiply():
    registry = ToolRegistry()

    @registry.tool(
        description="Multiply two numbers.",
        parameters=object_schema({"a": NUM, "b": NUM}),
    )
    def multiply(a, b):
        return a * b

    return registry


def test_object_schema_is_strict_mode_compliant():
    schema = object_schema({"a": NUM, "b": NUM})
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["a", "b"]


def test_definitions_use_the_flat_responses_shape_with_strict_on():
    definition = make_registry_with_multiply().definitions()[0]
    assert definition["type"] == "function"
    assert definition["name"] == "multiply"  # taken from the function name
    assert definition["strict"] is True
    assert "function" not in definition  # flat, not nested under "function"


def test_functions_maps_names_to_callables():
    funcs = make_registry_with_multiply().functions()
    assert funcs["multiply"](17, 23) == 391


def test_decorated_function_still_works_directly():
    registry = ToolRegistry()

    @registry.tool(description="Add.", parameters=object_schema({"a": NUM, "b": NUM}))
    def add(a, b):
        return a + b

    assert add(1, 2) == 3


def test_duplicate_tool_name_is_rejected():
    registry = make_registry_with_multiply()
    with pytest.raises(ValueError):

        @registry.tool(description="Again.", parameters=object_schema({"a": NUM, "b": NUM}))
        def multiply(a, b):
            return a * b


def test_function_and_schema_parameter_mismatch_is_rejected():
    # THE bug the registry exists to prevent: the schema says "y", the
    # function says "b".
    registry = ToolRegistry()
    with pytest.raises(ValueError):

        @registry.tool(description="Multiply.", parameters=object_schema({"a": NUM, "y": NUM}))
        def multiply(a, b):
            return a * b


def test_schema_without_additional_properties_false_is_rejected():
    registry = ToolRegistry()
    bad = {"type": "object", "properties": {"a": NUM}, "required": ["a"]}
    with pytest.raises(ValueError):

        @registry.tool(description="Test.", parameters=bad)
        def thing(a):
            return a


def test_property_missing_from_required_is_rejected():
    registry = ToolRegistry()
    bad = {
        "type": "object",
        "properties": {"a": NUM, "b": NUM},
        "required": ["a"],
        "additionalProperties": False,
    }
    with pytest.raises(ValueError):

        @registry.tool(description="Test.", parameters=bad)
        def thing(a, b):
            return a


def test_property_without_a_description_is_rejected():
    registry = ToolRegistry()
    with pytest.raises(ValueError):

        @registry.tool(
            description="Test.",
            parameters=object_schema({"a": {"type": "number"}}),
        )
        def thing(a):
            return a


def test_nested_object_parameter_is_rejected_in_v1():
    registry = ToolRegistry()
    nested = {"type": "object", "description": "Nested."}
    with pytest.raises(ValueError):

        @registry.tool(description="Test.", parameters=object_schema({"a": nested}))
        def thing(a):
            return a


def test_empty_tool_description_is_rejected():
    registry = ToolRegistry()
    with pytest.raises(ValueError):

        @registry.tool(description="  ", parameters=object_schema({"a": NUM}))
        def thing(a):
            return a


def test_definitions_are_copies_so_callers_cannot_change_the_registry():
    registry = make_registry_with_multiply()
    registry.definitions()[0]["parameters"]["properties"]["a"]["description"] = "HACKED"
    fresh = registry.definitions()[0]
    assert fresh["parameters"]["properties"]["a"]["description"] == "A number."


def test_registry_functions_work_with_run_tool_call():
    # Integration with the loop's existing tool runner, still free.
    registry = make_registry_with_multiply()
    call = SimpleNamespace(name="multiply", call_id="c1", arguments='{"a":17,"b":23}')
    out = agent_loop.run_tool_call(call, registry.functions())
    assert out == {"type": "function_call_output", "call_id": "c1", "output": "391"}