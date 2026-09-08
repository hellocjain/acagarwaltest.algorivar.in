"""Unit tests for Native Candlestick Pattern Engine."""

import pandas as pd
import pytest

from services.strategy_module.patterns import (
    SUPPORTED_PATTERNS,
    evaluate_all_patterns,
    evaluate_pattern,
)


def test_hammer_detection():
    # Construct a hammer: Open=100, High=101, Low=90, Close=100.5
    # Lower shadow = 10, Body = 0.5, Range = 11. Body is in upper 40% of range.
    data = {
        "open": [105.0, 102.0, 100.0],
        "high": [106.0, 103.0, 101.0],
        "low": [101.0, 99.0, 90.0],
        "close": [102.0, 100.0, 100.5],
    }
    df = pd.DataFrame(data)
    assert evaluate_pattern(df, "HAMMER", candle_idx=-1) is True
    assert evaluate_pattern(df, "BEARISH_ENGULFING", candle_idx=-1) is False


def test_bullish_engulfing_detection():
    # Day 1: Red candle (open=100, close=95)
    # Day 2: Green candle engulfing (open=94, close=102)
    data = {
        "open": [105.0, 100.0, 94.0],
        "high": [106.0, 101.0, 103.0],
        "low": [104.0, 94.0, 93.0],
        "close": [104.5, 95.0, 102.0],
    }
    df = pd.DataFrame(data)
    assert evaluate_pattern(df, "BULLISH_ENGULFING", candle_idx=-1) is True
    assert evaluate_pattern(df, "BEARISH_ENGULFING", candle_idx=-1) is False


def test_bearish_engulfing_detection():
    # Day 1: Green candle (open=95, close=100)
    # Day 2: Red candle engulfing (open=101, close=93)
    data = {
        "open": [90.0, 95.0, 101.0],
        "high": [92.0, 101.0, 102.0],
        "low": [89.0, 94.0, 92.0],
        "close": [91.0, 100.0, 93.0],
    }
    df = pd.DataFrame(data)
    assert evaluate_pattern(df, "BEARISH_ENGULFING", candle_idx=-1) is True
    assert evaluate_pattern(df, "BULLISH_ENGULFING", candle_idx=-1) is False


def test_doji_detection():
    # Doji: Open=100.0, Close=100.02, High=105.0, Low=95.0
    data = {
        "open": [100.0, 100.0],
        "high": [102.0, 105.0],
        "low": [98.0, 95.0],
        "close": [101.0, 100.02],
    }
    df = pd.DataFrame(data)
    assert evaluate_pattern(df, "DOJI", candle_idx=-1) is True


def test_morning_star_detection():
    # Day 1: Strong red (open=100, close=85)
    # Day 2: Small star (open=84, close=83)
    # Day 3: Strong green recovering > 50% (open=84, close=95)
    data = {
        "open": [100.0, 84.0, 84.0],
        "high": [101.0, 85.0, 96.0],
        "low": [84.0, 82.0, 83.0],
        "close": [85.0, 83.0, 95.0],
    }
    df = pd.DataFrame(data)
    assert evaluate_pattern(df, "MORNING_STAR", candle_idx=-1) is True


def test_evaluate_all_patterns():
    data = {
        "open": [100.0, 95.0, 94.0],
        "high": [101.0, 96.0, 102.0],
        "low": [98.0, 93.0, 93.0],
        "close": [99.0, 94.0, 101.5],
    }
    df = pd.DataFrame(data)
    res = evaluate_all_patterns(df, candle_idx=-1)
    assert isinstance(res, dict)
    assert len(res) == len(SUPPORTED_PATTERNS)
    assert "BULLISH_ENGULFING" in res
