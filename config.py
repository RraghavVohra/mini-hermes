"""
config.py: single source of truth for mini-Hermes.

Story: every other file asks THIS file "which model? how many loops?".
Nobody else hardcodes these values.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Copy the values from the .env file into this process's environment.
# By default this does NOT override variables already set in the system.
load_dotenv()


def require_env(name: str) -> str:
    """Fail closed: a missing secret crashes at startup, not mid-loop."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Add it to your .env file."
        )
    return value


OPENAI_API_KEY = require_env("OPENAI_API_KEY")

# --- Paths ---
# Resolve from this file's location, so paths work no matter which
# folder the program is launched from.
PROJECT_ROOT = Path(__file__).resolve().parent
SKILLS_DIR = PROJECT_ROOT / "skills"

# --- Model ---
# Dev default: gpt-5.6-luna, chosen for best quality per rupee on agent
# tasks. Heavier stages (e.g. skill creation) can get a stronger model
# later; that is why the model lives here, in one place.
MODEL_NAME = "gpt-5.6-luna"

# --- Loop limits ---
# Stop condition #2 of the agent loop: a safety net against runaway
# tool-call cycles, which would burn money.
MAX_ITERATIONS = 15

# --- Budget ---
# Not enforced in code yet. This documents the cap; the real guard is a
# spend limit/alert on the OpenAI dashboard. If real spend crosses it,
# we investigate before spending more.
MONTHLY_BUDGET_INR = 300
