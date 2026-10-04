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