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

def test_max_tool_output_chars_is_in_a_safe_range():
    # Too low: tools become useless. Too high: one big result is re-billed
    # on every loop iteration.
    assert 1_000 <= config.MAX_TOOL_OUTPUT_CHARS <= 100_000

def test_model_name_has_a_pricing_entry():
    # Switching MODEL_NAME without adding its price would break cost
    # tracking. This catches that at test time.
    assert config.MODEL_NAME in config.PRICING_USD_PER_1M


def test_every_pricing_entry_is_complete():
    needed = {"input", "cached_input", "output", "cache_write_multiplier"}
    for model, prices in config.PRICING_USD_PER_1M.items():
        assert needed <= set(prices), f"{model} is missing price fields"


def test_usd_to_inr_is_in_a_plausible_range():
    # Catches typos like 8.8 or 880.
    assert 50 <= config.USD_TO_INR <= 200

def test_run_cost_cap_is_positive_and_below_the_monthly_budget():
    assert 0 < config.MAX_RUN_COST_INR <= config.MONTHLY_BUDGET_INR

def test_workspace_is_strictly_inside_the_project_not_the_project_itself():
    # If the workspace were the project root, the agent could read .env.
    assert config.PROJECT_ROOT in config.WORKSPACE_DIR.parents

    