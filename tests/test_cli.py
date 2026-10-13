"""
Tests for cli.py.

Story: no keyboard, no screen, no API. A whole chat session is scripted
with a list of typed lines, run_agent is replaced by a fake that records
what it was given, and everything the user would see is collected in a list.
"""
import pytest

import agent_loop
import cli
import cost
from prompts import SYSTEM_PROMPT


def make_result(text="ok", reason="completed", history=None, cost_usd=0.0, iterations=1):
    return agent_loop.AgentResult(
        text, reason, iterations, history if history is not None else [], cost_usd, {}
    )


def run_session(monkeypatch, typed_lines, fake_run):
    """Play scripted lines into chat_loop and return everything shown.

    When the script runs out, read_line raises EOFError, which is exactly
    what Ctrl+D / Ctrl+Z gives, so a session always ends.
    """
    shown = []
    lines = iter(typed_lines)

    def read_line(prompt):
        try:
            return next(lines)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr(cli, "run_agent", fake_run)
    cli.chat_loop(
        None, [], {},
        read_line=read_line,
        say=lambda *args: shown.append(" ".join(str(a) for a in args)),
    )
    return shown


# --- classify_input ---

@pytest.mark.parametrize("line, expected", [
    ("", "empty"),
    ("   ", "empty"),
    ("/exit", "exit"),
    ("/EXIT", "exit"),
    ("/reset", "reset"),
    ("/help", "unknown_command"),
    ("hello", "message"),
    ("notes folder mein kya hai?", "message"),
])
def test_classify_input(line, expected):
    assert cli.classify_input(line) == expected


# --- display formatting ---

def test_format_event_shows_a_tool_call_on_one_line():
    text = cli.format_event("tool_call", {"name": "read_file", "arguments": '{"path": "a.md"}'})
    assert "read_file" in text
    assert "\n" not in text


def test_format_event_truncates_long_output_and_flattens_newlines():
    text = cli.format_event("tool_result", {"name": "x", "output": "line\n" * 500})
    assert "\n" not in text
    assert len(text) < cli.SHOW_LIMIT + 30


def test_format_event_ignores_unknown_kinds():
    assert cli.format_event("mystery", {}) == ""


def test_turn_summary_shows_the_reason_and_both_costs():
    text = cli.format_turn_summary(make_result(cost_usd=0.01), session_usd=0.02)
    assert "completed" in text
    assert f"{cost.usd_to_inr(0.01):.3f}" in text
    assert f"{cost.usd_to_inr(0.02):.3f}" in text


# --- the session loop ---

def test_exit_command_ends_the_session_without_calling_the_agent(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(1)
        return make_result()

    run_session(monkeypatch, ["/exit", "hello"], fake_run)
    assert calls == []


def test_end_of_input_ends_the_session_cleanly(monkeypatch):
    run_session(monkeypatch, [], lambda *a, **k: make_result())  # must not raise


def test_empty_line_does_not_call_the_agent(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(1)
        return make_result()

    run_session(monkeypatch, ["", "   "], fake_run)
    assert calls == []


def test_history_is_carried_from_one_turn_to_the_next(monkeypatch):
    seen = []

    def fake_run(client, message, tools, registry, **kwargs):
        seen.append((message, list(kwargs["history"])))
        return make_result(history=kwargs["history"] + [{"role": "user", "content": message}])

    run_session(monkeypatch, ["one", "two"], fake_run)
    assert seen[0] == ("one", [])
    assert seen[1] == ("two", [{"role": "user", "content": "one"}])


def test_reset_clears_the_history(monkeypatch):
    seen = []

    def fake_run(client, message, tools, registry, **kwargs):
        seen.append(list(kwargs["history"]))
        return make_result(history=kwargs["history"] + [{"role": "user", "content": message}])

    run_session(monkeypatch, ["one", "/reset", "two"], fake_run)
    assert seen[1] == []  # "two" starts a fresh conversation


def test_a_failed_turn_leaves_no_trace_and_the_session_survives(monkeypatch):
    seen = []

    def fake_run(client, message, tools, registry, **kwargs):
        seen.append(list(kwargs["history"]))
        if message == "boom":
            raise RuntimeError("api down")
        return make_result(history=[{"role": "user", "content": message}])

    shown = run_session(monkeypatch, ["boom", "fine"], fake_run)
    assert seen[1] == []  # the failed turn added nothing to the history
    assert any("api down" in line for line in shown)


def test_ctrl_c_during_a_turn_drops_that_turn_and_keeps_going(monkeypatch):
    seen = []

    def fake_run(client, message, tools, registry, **kwargs):
        seen.append(message)
        if message == "slow":
            raise KeyboardInterrupt
        return make_result()

    shown = run_session(monkeypatch, ["slow", "next"], fake_run)
    assert seen == ["slow", "next"]
    assert any("interrupted" in line for line in shown)


def test_every_turn_gets_the_system_prompt_and_a_display_hook(monkeypatch):
    seen = []

    def fake_run(client, message, tools, registry, **kwargs):
        seen.append(kwargs)
        return make_result()

    run_session(monkeypatch, ["hi"], fake_run)
    assert seen[0]["instructions"] == SYSTEM_PROMPT
    assert callable(seen[0]["on_event"])


def test_tool_events_reach_the_screen(monkeypatch):
    def fake_run(client, message, tools, registry, **kwargs):
        kwargs["on_event"]("tool_call", {"name": "list_dir", "arguments": '{"path": "notes"}'})
        kwargs["on_event"]("tool_result", {"name": "list_dir", "output": "hello.md"})
        return make_result()

    shown = run_session(monkeypatch, ["list"], fake_run)
    assert any("[tool] list_dir" in line for line in shown)
    assert any("[result] hello.md" in line for line in shown)


def test_a_limit_stop_tells_the_user_why(monkeypatch):
    shown = run_session(
        monkeypatch, ["go"],
        lambda *a, **k: make_result(text="", reason="run_budget"),
    )
    assert any(cli.STOP_MESSAGES["run_budget"] in line for line in shown)