"""
Tests for cost.py.

Story: usage objects are faked with SimpleNamespace, so these cost nothing.
Expected numbers are worked out by hand from the Luna prices:
input $0.20, cached $0.02, output $1.20 per 1M, cache write 1.25x input.
"""
from types import SimpleNamespace

import pytest

import config
import cost

LUNA = "gpt-5.6-luna"


def make_usage(input_tokens, output_tokens, cached=0, cache_write=0, reasoning=0):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_tokens_details=SimpleNamespace(
            cached_tokens=cached, cache_write_tokens=cache_write
        ),
        output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
    )


def test_cost_matches_the_real_numbers_from_experiment_01():
    # 60 input + 21 output: (60*0.20 + 21*1.20) / 1M = 0.0000372
    usage = make_usage(input_tokens=60, output_tokens=21)
    assert cost.calculate_cost_usd(usage, LUNA) == pytest.approx(0.0000372)


def test_cost_prices_each_input_bucket_separately():
    # 1000 input = 600 cached + 100 cache-write + 300 ordinary; 200 output.
    # (300*0.20 + 600*0.02 + 100*0.20*1.25 + 200*1.20) / 1M = 0.000337
    usage = make_usage(1000, 200, cached=600, cache_write=100)
    assert cost.calculate_cost_usd(usage, LUNA) == pytest.approx(0.000337)


def test_reasoning_tokens_are_not_double_counted():
    # output_tokens already includes reasoning, so these two must cost the same.
    with_reasoning = make_usage(100, 1000, reasoning=900)
    without_reasoning = make_usage(100, 1000, reasoning=0)
    assert cost.calculate_cost_usd(with_reasoning, LUNA) == pytest.approx(
        cost.calculate_cost_usd(without_reasoning, LUNA)
    )


def test_unknown_model_fails_closed():
    with pytest.raises(ValueError):
        cost.calculate_cost_usd(make_usage(10, 10), "some-model-with-no-price")


def test_usd_to_inr_uses_the_configured_rate():
    assert cost.usd_to_inr(2.0) == pytest.approx(2.0 * config.USD_TO_INR)

def test_add_usage_accumulates_every_bucket():
    totals = cost.empty_totals()
    cost.add_usage(totals, make_usage(1000, 200, cached=600, cache_write=100, reasoning=150))
    cost.add_usage(totals, make_usage(500, 100, reasoning=50))
    assert totals == {
        "input": 1500, "cached": 600, "cache_write": 100, "output": 300, "reasoning": 200,
    }


def test_empty_totals_returns_a_fresh_dict_each_time():
    first = cost.empty_totals()
    first["input"] = 999
    assert cost.empty_totals()["input"] == 0