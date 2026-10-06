"""
Experiment 03: why did the API reject our replayed item?

Story: Experiment 02 failed with "Unknown parameter: input[1].async_".
This builds a REAL SDK item locally (no API call, zero cost) and prints
how it dumps, so we fix the cause instead of guessing.
"""
import openai
from openai.types.responses import ResponseFunctionToolCall

print("openai SDK version:", openai.__version__)

item = ResponseFunctionToolCall(
    arguments='{"a":17,"b":23}',
    call_id="call_test",
    name="multiply",
    type="function_call",
)

print("\nplain model_dump():")
print(item.model_dump())

print("\nmodel_dump(by_alias=True, exclude_none=True):")
print(item.model_dump(by_alias=True, exclude_none=True))