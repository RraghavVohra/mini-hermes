"""
Tests for config.py.

Story: config has almost no logic, so we test for MISTAKES (typos,
unsafe values, broken fail-closed behaviour), not for copies of values.
"""
import pytest

import config


def test_model_name_is_a_non_empty_string():
    # Not pinned to one model, so intentionally switching models
    # doesn't break this test.
    assert isinstance(config.MODEL_NAME, str)
    assert config.MODEL_NAME.strip() != ""


def test_max_iterations_is_in_a_safe_range():
    # Guards against typos like 150, which would let a runaway loop
    # burn money, or 0, which would stop the agent from working at all.
    assert 1 <= config.MAX_ITERATIONS <= 50


def test_skills_dir_lives_inside_project_root():
    assert config.PROJECT_ROOT in config.SKILLS_DIR.parents


def test_require_env_fails_closed_when_variable_is_missing(monkeypatch):
    # Fail-closed principle: a missing secret must crash loudly.
    monkeypatch.delenv("SOME_MADE_UP_KEY", raising=False)
    with pytest.raises(RuntimeError):
        config.require_env("SOME_MADE_UP_KEY")

def test_reasoning_effort_is_a_value_luna_supports():
    # Allowed values per the gpt-5.6-luna model page. A typo here would
    # only show up as an API error mid-run, so we catch it early.
    allowed = {"none", "low", "medium", "high", "xhigh", "max"}
    assert config.REASONING_EFFORT in allowed


def test_max_output_tokens_is_in_a_safe_range():
    # Too low: reasoning eats the budget and we pay for no visible answer.
    # Too high: one call can burn real money.
    assert 1_000 <= config.MAX_OUTPUT_TOKENS <= 50_000