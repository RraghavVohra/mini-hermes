"""
Experiment 06: how does cost grow across a conversation, and does caching kick in?

Story: the API is stateless (store=False), so every request re-sends the whole
history. Theory says the cost per turn should climb, and that prompt caching
should make the repeated prefix cheap once the prompt passes ~1,024 tokens.
Theory is a guess until we measure it, so this script runs 8 short turns on
the real model, carrying history like cli.py does, and prints one row per turn.

One sample, one machine, one afternoon: read the numbers as a signal, not proof.
"""
import sys

from openai import OpenAI

import config
import cost
from agent_loop import run_agent
from prompts import SYSTEM_PROMPT
from tools.files import registry

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = OpenAI(api_key=config.OPENAI_API_KEY)
TOOLS = registry.definitions()
REGISTRY = registry.functions()

# A spend guard for the WHOLE experiment. The per-run cap (config) only limits
# one turn, and this script runs many turns back to back.
EXPERIMENT_CAP_INR = 3.0

# Mostly ~100-word answers so the history grows steadily and predictably.
# Two turns use a tool, because tool outputs also land in the history.
PROMPTS = [
    "In about 100 words, explain what an API rate limit is and why services use them.",
    "In about 100 words, explain the difference between a unit test and an integration test.",
    "List what is inside the notes folder.",
    "In about 100 words, explain what a flaky test is and two common causes.",
    "In about 100 words, explain what idempotency means for an HTTP endpoint.",
    "Read notes/hello.md and tell me what it says.",
    "In about 100 words, explain what a race condition is, with a tiny example.",
    "In about 100 words, explain why logs should not contain secrets.",
]

history = []
totals = cost.empty_totals()
total_usd = 0.0
turn_costs_inr = []

print(f"model: {config.MODEL_NAME} | experiment cap: ₹{EXPERIMENT_CAP_INR}")
print()
print(f"{'turn':>4} {'iters':>5} {'input':>7} {'cached':>7} {'write':>7} "
      f"{'output':>7} {'hit%':>5} {'₹':>8}  stop")

for n, prompt in enumerate(PROMPTS, start=1):
    if cost.usd_to_inr(total_usd) >= EXPERIMENT_CAP_INR:
        print("experiment cap reached, stopping early.")
        break

    result = run_agent(client, prompt, TOOLS, REGISTRY,
                       instructions=SYSTEM_PROMPT, history=history)
    history = result.history  # carry the conversation, exactly like cli.py

    t = result.tokens
    for key in totals:
        totals[key] += t[key]
    total_usd += result.cost_usd

    # "input" already INCLUDES cached tokens, so this is the share of the
    # prompt that was read from the cache.
    hit = 100 * t["cached"] / t["input"] if t["input"] else 0
    inr = cost.usd_to_inr(result.cost_usd)
    turn_costs_inr.append(inr)
    print(f"{n:>4} {result.iterations:>5} {t['input']:>7} {t['cached']:>7} "
          f"{t['cache_write']:>7} {t['output']:>7} {hit:>4.0f}% {inr:>8.4f}  "
          f"{result.stop_reason}")

print()
hit_overall = 100 * totals["cached"] / totals["input"] if totals["input"] else 0
print(f"total input: {totals['input']} | cached: {totals['cached']} "
      f"({hit_overall:.0f}%) | cache writes: {totals['cache_write']} "
      f"| output: {totals['output']}")

# What the same tokens would have cost with every input token at the plain
# price. If caching writes are rarely re-read, this can come out CHEAPER than
# what we paid, and that is exactly the thing worth knowing.
prices = config.PRICING_USD_PER_1M[config.MODEL_NAME]
no_cache_usd = (totals["input"] * prices["input"]
                + totals["output"] * prices["output"]) / 1_000_000
print(f"actual cost: ₹{cost.usd_to_inr(total_usd):.4f} | "
      f"same tokens with no caching: ₹{cost.usd_to_inr(no_cache_usd):.4f} | "
      f"saved by caching: ₹{cost.usd_to_inr(no_cache_usd - total_usd):.4f}")

if len(turn_costs_inr) >= 2 and turn_costs_inr[0] > 0:
    print(f"last turn cost / first turn cost: "
          f"{turn_costs_inr[-1] / turn_costs_inr[0]:.1f}x "
          f"(tool turns are noisy, read the trend, not one row)")