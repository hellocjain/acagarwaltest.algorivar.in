"""Unit tests for Universal Condition Tree Evaluator."""

import numpy as np
import pandas as pd
import pytest

from services.strategy_module.condition_tree import (
    evaluate_condition_tree,
    legacy_rules_to_condition_tree,
)


@pytest.fixture
def sample_ohlcv():
    # 30 bars of simulated price data with trending prices
    np.random.seed(42)
    n = 35
    close = np.linspace(100, 120, n) + np.random.normal(0, 1, n)
    high = close + np.random.uniform(0.5, 2.0, n)
    low = close - np.random.uniform(0.5, 2.0, n)
    open_p = close - np.random.uniform(-1.0, 1.0, n)
    volume = np.random.uniform(1000, 5000, n)

    # Force a hammer on the last bar
    # Open=120, High=121, Low=110, Close=120.5 (long lower shadow)
    open_p[-1] = 120.0
    high[-1] = 121.0
    low[-1] = 110.0
    close[-1] = 120.5

    df = pd.DataFrame({
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    return df


def test_indicator_leaf_rsi(sample_ohlcv):
    tree = {
        "op": "AND",
        "rules": [
            {
                "type": "indicator",
                "indicator": "RSI",
                "params": {"period": 14},
                "comp": ">",
                "value": 30.0,
            }
        ],
    }
    res = evaluate_condition_tree(tree, sample_ohlcv, candle_idx=-1)
    assert res.passed is True
    assert len(res.diagnostics) == 1
    assert res.diagnostics[0]["passed"] is True
    assert "RSI(14)" in res.diagnostics[0]["label"]


def test_candlestick_leaf(sample_ohlcv):
    tree = {
        "op": "AND",
        "rules": [
            {
                "type": "candlestick",
                "pattern": "HAMMER",
            }
        ],
    }
    res = evaluate_condition_tree(tree, sample_ohlcv, candle_idx=-1)
    assert res.passed is True
    assert res.diagnostics[0]["actual_value"] == "Formed"


def test_nested_and_or_gates(sample_ohlcv):
    # (RSI < 10 [False] AND Hammer [True]) OR (Close > 100 [True])
    tree = {
        "op": "OR",
        "rules": [
            {
                "op": "AND",
                "rules": [
                    {"type": "indicator", "indicator": "RSI", "params": {"period": 14}, "comp": "<", "value": 10.0},
                    {"type": "candlestick", "pattern": "HAMMER"},
                ],
            },
            {
                "type": "price",
                "field": "close",
                "comp": ">",
                "value": 100.0,
            },
        ],
    }
    res = evaluate_condition_tree(tree, sample_ohlcv, candle_idx=-1)
    assert res.passed is True
    assert len(res.diagnostics) == 3


def test_legacy_rules_conversion():
    legacy = {
        "rsi": {"period": 14, "op": "<", "val": 25},
        "supertrend": "bullish",
        "candlestick": "HAMMER",
    }
    ast = legacy_rules_to_condition_tree(legacy)
    assert ast["op"] == "AND"
    assert len(ast["rules"]) == 3
    types = [r["type"] for r in ast["rules"]]
    assert "indicator" in types
    assert "candlestick" in types
