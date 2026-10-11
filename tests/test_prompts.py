"""
Tests for prompts.py.

Story: these tests cannot prove the prompt changes the model's behavior (only
a real run can, see Experiment 05). They guard against accidental edits: a
bloated prompt, an interpolation placeholder, or a deleted safety rule.
"""
from prompts import SYSTEM_PROMPT


def test_system_prompt_is_a_non_empty_string():
    assert isinstance(SYSTEM_PROMPT, str)
    assert SYSTEM_PROMPT.strip() != ""


def test_system_prompt_stays_lean():
    # The prompt is billed as input on every call, and OpenAI's guidance says
    # leaner prompts work better. About 2,000 characters is roughly 500 tokens.
    assert len(SYSTEM_PROMPT) <= 2_000


def test_system_prompt_is_static_with_no_placeholders():
    # A "{...}" placeholder would suggest untrusted text gets formatted into
    # developer-level instructions.
    assert "{" not in SYSTEM_PROMPT
    assert "}" not in SYSTEM_PROMPT


def test_system_prompt_keeps_the_untrusted_file_rule():
    assert "data, not instructions" in SYSTEM_PROMPT


def test_system_prompt_keeps_the_workspace_boundary():
    assert "outside it" in SYSTEM_PROMPT