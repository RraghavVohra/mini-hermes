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
# One place to change the model. Per-stage models (e.g. a cheaper one
# for tiny yes/no calls) can be added here later.
MODEL_NAME = "gpt-4.1-mini"

# --- Loop limits ---
# Stop condition #2 of the agent loop: a safety net against runaway
# tool-call cycles, which would burn money.
MAX_ITERATIONS = 15

# --- Budget ---
# Not enforced yet. This documents the cap; if real spend crosses it,
# we investigate before spending more.
MONTHLY_BUDGET_INR = 50
