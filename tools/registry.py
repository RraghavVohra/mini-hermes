"""
tools/registry.py: the one place where a tool's schema and its function meet.

Story: before this, a tool's JSON schema and its Python function lived in
two separate places (see Experiment 02). Rename an argument in one and
forget the other, and the model would send arguments the function cannot
accept. The registry checks the two against each other at registration
time, which costs nothing and needs no API call.
"""
import copy
import inspect


def object_schema(properties: dict) -> dict:
    """Build a strict-mode compliant `parameters` schema from properties.

    OpenAI's strict mode needs additionalProperties=False and EVERY property
    listed in `required`. Building both here means a tool author cannot
    forget them. An optional argument is written as a nullable type such as
    ["string", "null"], not by leaving it out of `required`.
    """
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _types_of(prop_schema: dict) -> set:
    declared = prop_schema.get("type")
    return set(declared) if isinstance(declared, list) else {declared}


def validate_parameters(name: str, parameters: dict, func) -> None:
    """Raise ValueError if the schema or its match with `func` is unsafe."""
    if parameters.get("type") != "object":
        raise ValueError(f"Tool '{name}': parameters must be an object schema")

    if parameters.get("additionalProperties") is not False:
        raise ValueError(
            f"Tool '{name}': additionalProperties must be false (strict mode)"
        )

    properties = parameters.get("properties", {})
    if set(parameters.get("required", [])) != set(properties):
        raise ValueError(
            f"Tool '{name}': every property must be listed in required (strict mode)"
        )

    for prop_name, prop in properties.items():
        # V1 keeps parameters flat and simple. Nested objects and arrays have
        # extra strict-mode rules we have not studied yet.
        if _types_of(prop) & {"object", "array"}:
            raise ValueError(
                f"Tool '{name}': parameter '{prop_name}' must be a simple type in V1"
            )
        # The docs say to describe every parameter: the model only knows a
        # parameter through its name and description.
        if not str(prop.get("description", "")).strip():
            raise ValueError(f"Tool '{name}': parameter '{prop_name}' needs a description")

    # The bug the registry exists to prevent: schema and function disagreeing.
    function_params = set(inspect.signature(func).parameters)
    if function_params != set(properties):
        raise ValueError(
            f"Tool '{name}': function takes {sorted(function_params)} "
            f"but the schema lists {sorted(properties)}"
        )


class ToolRegistry:
    """Collects tools and hands them out in the two shapes the loop needs."""

    def __init__(self):
        self._tools = {}

    def tool(self, description: str, parameters: dict):
        """Decorator that registers a function as a tool.

        The tool's name is the function's name, so it is written only once.
        """
        def decorator(func):
            name = func.__name__
            if name in self._tools:
                raise ValueError(f"Tool '{name}' is already registered")
            if not str(description).strip():
                raise ValueError(f"Tool '{name}' needs a description")
            validate_parameters(name, parameters, func)
            self._tools[name] = {
                "description": description,
                "parameters": copy.deepcopy(parameters),
                "func": func,
            }
            # Return the function unchanged, so tests can call it directly.
            return func

        return decorator

    def definitions(self) -> list:
        """The `tools` list for client.responses.create (flat Responses shape).

        strict is set explicitly: if we omitted it, the API could quietly
        fall back to non-strict best-effort calling.
        """
        return [
            {
                "type": "function",
                "name": name,
                "description": tool["description"],
                "parameters": copy.deepcopy(tool["parameters"]),
                "strict": True,
            }
            for name, tool in self._tools.items()
        ]

    def functions(self) -> dict:
        """Name -> Python function, exactly what run_tool_call expects."""
        return {name: tool["func"] for name, tool in self._tools.items()}