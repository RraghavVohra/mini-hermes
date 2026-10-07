"""
cost.py: turns API usage numbers into money.

Story: the API reports tokens in several buckets, each with its own price.
This file is the only place that knows how to price them, so the loop (and
later components like the nudge and memory) all use one honest formula.
"""
import config


def calculate_cost_usd(usage, model: str) -> float:
    """Price one API response's usage, in USD.

    Raises ValueError for a model with no pricing entry. A silent zero
    would let spending go untracked (fail closed).
    """
    prices = config.PRICING_USD_PER_1M.get(model)
    if prices is None:
        raise ValueError(
            f"No pricing for model '{model}'. Add it to PRICING_USD_PER_1M in config.py."
        )

    details = usage.input_tokens_details
    cached = details.cached_tokens or 0
    cache_write = details.cache_write_tokens or 0

    # input_tokens already INCLUDES cached and cache-write tokens (official
    # formula), so subtract them to get the plain-priced part.
    ordinary_input = usage.input_tokens - cached - cache_write

    # output_tokens already INCLUDES reasoning tokens. Never add
    # reasoning_tokens on top, that would double count.
    total = (
        ordinary_input * prices["input"]
        + cached * prices["cached_input"]
        + cache_write * prices["input"] * prices["cache_write_multiplier"]
        + usage.output_tokens * prices["output"]
    )
    return total / 1_000_000


def usd_to_inr(usd: float) -> float:
    return usd * config.USD_TO_INR

def empty_totals() -> dict:
    """A fresh token counter for one run (new dict every call, never shared)."""
    return {"input": 0, "cached": 0, "cache_write": 0, "output": 0, "reasoning": 0}


def add_usage(totals: dict, usage) -> None:
    """Add one response's usage into the run's totals.

    "input" is what the API reports, so it already includes the cached and
    cache_write tokens. "output" already includes "reasoning". Both are kept
    so we can SEE how much caching and reasoning happen in real runs.
    """
    details = usage.input_tokens_details
    totals["input"] += usage.input_tokens
    totals["cached"] += details.cached_tokens or 0
    totals["cache_write"] += details.cache_write_tokens or 0
    totals["output"] += usage.output_tokens
    totals["reasoning"] += usage.output_tokens_details.reasoning_tokens or 0