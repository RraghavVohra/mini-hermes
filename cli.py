"""
cli.py: the terminal front-end of mini-Hermes.

Story: run_agent is the INNER loop (one user message -> tools -> answer).
This file is the OUTER loop: read a line, run the agent, show the result,
repeat. It owns the conversation history between turns and nothing else.
No agent logic lives here.

Run it with:  python cli.py
"""
import sys

from openai import OpenAI

import config
import cost
from agent_loop import run_agent
from prompts import SYSTEM_PROMPT
from tools.files import registry

SHOW_LIMIT = 100  # characters of a tool's arguments or output shown on screen

# run_agent hands back an empty answer for these stops, so the user would
# see nothing. Say WHY it stopped instead of hiding the limit.
STOP_MESSAGES = {
    "max_iterations": "Stopped: the agent kept calling tools and hit the iteration limit.",
    "incomplete": "Stopped: the reply was cut off by the output token limit.",
    "run_budget": "Stopped: this task reached its cost limit.",
}


def classify_input(line: str) -> str:
    """Decide what a typed line is: empty, a command, or a real message.

    Why a "/" that is not a known command is NOT sent to the model: a typo
    like /exot would otherwise cost money and confuse the agent.
    """
    text = line.strip().lower()
    if not text:
        return "empty"
    if text == "/exit":
        return "exit"
    if text == "/reset":
        return "reset"
    if text.startswith("/"):
        return "unknown_command"
    return "message"


def shorten(text: str, limit: int = SHOW_LIMIT) -> str:
    """Flatten to one line and cut it, so one tool event is one screen line."""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[:limit] + "..."


def format_event(kind: str, data: dict) -> str:
    """Turn a run_agent event into one screen line ("" for unknown kinds)."""
    if kind == "tool_call":
        return f"  [tool] {data['name']}({shorten(data['arguments'])})"
    if kind == "tool_result":
        return f"  [result] {shorten(data['output'])}"
    return ""


def format_turn_summary(result, session_usd: float) -> str:
    """One status line after every turn: why it stopped, and what it cost."""
    turn_inr = cost.usd_to_inr(result.cost_usd)
    session_inr = cost.usd_to_inr(session_usd)
    return (
        f"[{result.stop_reason} | {result.iterations} iteration(s) | "
        f"this turn \u20b9{turn_inr:.3f} | session \u20b9{session_inr:.3f}]"
    )


def chat_loop(client, tools, functions, read_line=input, say=print):
    """The outer loop: read -> run the agent -> show -> repeat.

    `read_line` and `say` are passed in (not hard-wired to input/print) so
    tests can script a whole session with no keyboard and no screen.

    Why a failed turn leaves no trace: run_agent copies the history it is
    given, so if it raises, our `history` is still the last good one.
    Known limit: money spent inside a turn that crashed is not counted in
    the session total, because no result came back to read it from.
    """
    history = []
    session_usd = 0.0
    say("mini-Hermes. Commands: /reset (new conversation), /exit (quit).")

    def show_event(kind, data):
        line = format_event(kind, data)
        if line:
            say(line)

    while True:
        try:
            line = read_line("you> ")
        except (EOFError, KeyboardInterrupt):
            say()  # leave the cursor on a fresh line
            break

        action = classify_input(line)
        if action == "empty":
            continue
        if action == "exit":
            break
        if action == "reset":
            history = []
            say("Conversation cleared.")
            continue
        if action == "unknown_command":
            say("Unknown command. Use /reset or /exit.")
            continue

        try:
            result = run_agent(
                client, line.strip(), tools, functions,
                instructions=SYSTEM_PROMPT,
                history=history,
                on_event=show_event,
            )
        except KeyboardInterrupt:
            say("\n[interrupted: this turn was dropped]")
            continue
        except Exception as err:  # deliberate: an API error must not kill the session
            say(f"[error: {type(err).__name__}: {err}]")
            continue

        history = result.history
        session_usd += result.cost_usd

        if result.final_text:
            say(f"\nagent> {result.final_text}")
        if result.stop_reason in STOP_MESSAGES:
            say(STOP_MESSAGES[result.stop_reason])
        say(format_turn_summary(result, session_usd))
        say()


def main():
    # Windows consoles default to a legacy encoding that cannot print Hindi
    # or the rupee sign. Done here, not at import, so tests are not affected.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    chat_loop(client, registry.definitions(), registry.functions())


if __name__ == "__main__":
    main()