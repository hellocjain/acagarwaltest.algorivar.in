"""Native Vectorized Candlestick Pattern Engine for OpenAlgo.

High-performance, pure-Python / NumPy implementation of 14 key candlestick formations
without requiring external C-binary compilation (such as TA-Lib).

Operates on standard OHLCV DataFrames and evaluates patterns on both full series
and specific candle indices (e.g. latest closed candle at index -1).
"""

from __future__ import annotations

import logging
from typing import Any
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SUPPORTED_PATTERNS = {
    "HAMMER",
    "INVERTED_HAMMER",
    "BULLISH_ENGULFING",
    "BEARISH_ENGULFING",
    "MORNING_STAR",
    "EVENING_STAR",
    "DOJI",
    "DRAGONFLY_DOJI",
    "GRAVESTONE_DOJI",
    "SHOOTING_STAR",
    "HANGING_MAN",
    "MARUBOZU_BULLISH",
    "MARUBOZU_BEARISH",
    "PIERCING_LINE",
    "DARK_CLOUD_COVER",
    "THREE_WHITE_SOLDIERS",
    "THREE_BLACK_CROWS",
}


def _normalize_ohlc(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Extract and normalize OHLC column names (case-insensitive)."""
    cols = {c.lower(): c for c in df.columns}
    required = ["open", "high", "low", "close"]
    missing = [r for r in required if r not in cols]
    if missing:
        raise ValueError(f"DataFrame missing required OHLC columns: {missing}")

    o = df[cols["open"]].astype(float)
    h = df[cols["high"]].astype(float)
    l = df[cols["low"]].astype(float)
    c = df[cols["close"]].astype(float)
    return o, h, l, c


def detect_hammer(df: pd.DataFrame, shadow_ratio: float = 2.0) -> pd.Series:
    """Detect Hammer (bullish reversal with long lower shadow in lower range)."""
    o, h, l, c = _normalize_ohlc(df)
    body = (c - o).abs()
    candle_range = h - l
    lower_shadow = np.minimum(o, c) - l
    upper_shadow = h - np.maximum(o, c)

    # Criteria:
    # 1. Non-zero range
    # 2. Lower shadow at least shadow_ratio * body (or large lower shadow if body is tiny)
    # 3. Upper shadow <= 20% of range
    # 4. Body located in upper 40% of total candle range
    is_hammer = (
        (candle_range > 0)
        & (lower_shadow >= np.maximum(body * shadow_ratio, candle_range * 0.50))
        & (upper_shadow <= candle_range * 0.20)
        & (np.minimum(o, c) >= l + (candle_range * 0.50))
    )
    return is_hammer


def detect_inverted_hammer(df: pd.DataFrame, shadow_ratio: float = 2.0) -> pd.Series:
    """Detect Inverted Hammer (bullish reversal with long upper shadow)."""
    o, h, l, c = _normalize_ohlc(df)
    body = (c - o).abs()
    candle_range = h - l
    lower_shadow = np.minimum(o, c) - l
    upper_shadow = h - np.maximum(o, c)

    is_inv_hammer = (
        (candle_range > 0)
        & (upper_shadow >= np.maximum(body * shadow_ratio, candle_range * 0.50))
        & (lower_shadow <= candle_range * 0.20)
        & (np.maximum(o, c) <= l + (candle_range * 0.50))
    )
    return is_inv_hammer


def detect_shooting_star(df: pd.DataFrame, shadow_ratio: float = 2.0) -> pd.Series:
    """Detect Shooting Star (bearish reversal after uptrend with long upper shadow)."""
    # Similar structure to inverted hammer
    return detect_inverted_hammer(df, shadow_ratio=shadow_ratio)


def detect_hanging_man(df: pd.DataFrame, shadow_ratio: float = 2.0) -> pd.Series:
    """Detect Hanging Man (bearish reversal after uptrend with long lower shadow)."""
    # Similar structure to hammer
    return detect_hammer(df, shadow_ratio=shadow_ratio)


def detect_bullish_engulfing(df: pd.DataFrame) -> pd.Series:
    """Detect Bullish Engulfing (current green candle engulfs prior red candle body)."""
    o, h, l, c = _normalize_ohlc(df)
    prior_o = o.shift(1)
    prior_c = c.shift(1)

    prior_red = prior_c < prior_o
    curr_green = c > o
    curr_body_engulfs = (o <= prior_c) & (c >= prior_o)

    return prior_red & curr_green & curr_body_engulfs


def detect_bearish_engulfing(df: pd.DataFrame) -> pd.Series:
    """Detect Bearish Engulfing (current red candle engulfs prior green candle body)."""
    o, h, l, c = _normalize_ohlc(df)
    prior_o = o.shift(1)
    prior_c = c.shift(1)

    prior_green = prior_c > prior_o
    curr_red = c < o
    curr_body_engulfs = (o >= prior_c) & (c <= prior_o)

    return prior_green & curr_red & curr_body_engulfs


def detect_doji(df: pd.DataFrame, threshold: float = 0.10) -> pd.Series:
    """Detect Doji (open and close are nearly identical, body <= 10% of candle range)."""
    o, h, l, c = _normalize_ohlc(df)
    body = (c - o).abs()
    candle_range = h - l
    return (candle_range > 0) & (body <= candle_range * threshold)


def detect_dragonfly_doji(df: pd.DataFrame, threshold: float = 0.10) -> pd.Series:
    """Detect Dragonfly Doji (Doji with virtually no upper shadow and long lower shadow)."""
    o, h, l, c = _normalize_ohlc(df)
    body = (c - o).abs()
    candle_range = h - l
    upper_shadow = h - np.maximum(o, c)
    lower_shadow = np.minimum(o, c) - l

    return (
        (candle_range > 0)
        & (body <= candle_range * threshold)
        & (upper_shadow <= candle_range * 0.10)
        & (lower_shadow >= candle_range * 0.60)
    )


def detect_gravestone_doji(df: pd.DataFrame, threshold: float = 0.10) -> pd.Series:
    """Detect Gravestone Doji (Doji with virtually no lower shadow and long upper shadow)."""
    o, h, l, c = _normalize_ohlc(df)
    body = (c - o).abs()
    candle_range = h - l
    upper_shadow = h - np.maximum(o, c)
    lower_shadow = np.minimum(o, c) - l

    return (
        (candle_range > 0)
        & (body <= candle_range * threshold)
        & (lower_shadow <= candle_range * 0.10)
        & (upper_shadow >= candle_range * 0.60)
    )


def detect_morning_star(df: pd.DataFrame) -> pd.Series:
    """Detect Morning Star (3-candle bullish reversal pattern)."""
    o, h, l, c = _normalize_ohlc(df)
    # Candle 1 (t-2): Long red candle
    c1_red = c.shift(2) < o.shift(2)
    c1_body = (o.shift(2) - c.shift(2)).abs()

    # Candle 2 (t-1): Star / small body
    c2_body = (c.shift(1) - o.shift(1)).abs()
    c2_star = c2_body <= (c1_body * 0.5)

    # Candle 3 (t): Strong green candle closing > 50% into candle 1 body
    c3_green = c > o
    c1_midpoint = (o.shift(2) + c.shift(2)) / 2.0
    c3_recovery = c > c1_midpoint

    return c1_red & c2_star & c3_green & c3_recovery


def detect_evening_star(df: pd.DataFrame) -> pd.Series:
    """Detect Evening Star (3-candle bearish reversal pattern)."""
    o, h, l, c = _normalize_ohlc(df)
    # Candle 1 (t-2): Long green candle
    c1_green = c.shift(2) > o.shift(2)
    c1_body = (c.shift(2) - o.shift(2)).abs()

    # Candle 2 (t-1): Star / small body
    c2_body = (c.shift(1) - o.shift(1)).abs()
    c2_star = c2_body <= (c1_body * 0.5)

    # Candle 3 (t): Strong red candle closing > 50% down into candle 1 body
    c3_red = c < o
    c1_midpoint = (o.shift(2) + c.shift(2)) / 2.0
    c3_reversal = c < c1_midpoint

    return c1_green & c2_star & c3_red & c3_reversal


def detect_marubozu_bullish(df: pd.DataFrame, shadow_tol: float = 0.05) -> pd.Series:
    """Detect Bullish Marubozu (long green body with nearly zero shadows)."""
    o, h, l, c = _normalize_ohlc(df)
    candle_range = h - l
    body = c - o
    upper_shadow = h - c
    lower_shadow = o - l

    return (
        (candle_range > 0)
        & (body > 0)
        & (body >= candle_range * (1.0 - (2 * shadow_tol)))
        & (upper_shadow <= candle_range * shadow_tol)
        & (lower_shadow <= candle_range * shadow_tol)
    )


def detect_marubozu_bearish(df: pd.DataFrame, shadow_tol: float = 0.05) -> pd.Series:
    """Detect Bearish Marubozu (long red body with nearly zero shadows)."""
    o, h, l, c = _normalize_ohlc(df)
    candle_range = h - l
    body = o - c
    upper_shadow = h - o
    lower_shadow = c - l

    return (
        (candle_range > 0)
        & (body > 0)
        & (body >= candle_range * (1.0 - (2 * shadow_tol)))
        & (upper_shadow <= candle_range * shadow_tol)
        & (lower_shadow <= candle_range * shadow_tol)
    )


def detect_piercing_line(df: pd.DataFrame) -> pd.Series:
    """Detect Piercing Line (bullish reversal: opens below prior low, closes > 50% into prior body)."""
    o, h, l, c = _normalize_ohlc(df)
    prior_red = c.shift(1) < o.shift(1)
    curr_green = c > o
    opens_lower = o < l.shift(1)
    prior_mid = (o.shift(1) + c.shift(1)) / 2.0
    closes_above_mid = c >= prior_mid

    return prior_red & curr_green & opens_lower & closes_above_mid


def detect_dark_cloud_cover(df: pd.DataFrame) -> pd.Series:
    """Detect Dark Cloud Cover (bearish reversal: opens above prior high, closes > 50% into prior body)."""
    o, h, l, c = _normalize_ohlc(df)
    prior_green = c.shift(1) > o.shift(1)
    curr_red = c < o
    opens_higher = o > h.shift(1)
    prior_mid = (o.shift(1) + c.shift(1)) / 2.0
    closes_below_mid = c <= prior_mid

    return prior_green & curr_red & opens_higher & closes_below_mid


def detect_three_white_soldiers(df: pd.DataFrame) -> pd.Series:
    """Detect Three White Soldiers (3 consecutive strong green candles)."""
    o, h, l, c = _normalize_ohlc(df)
    c1 = (c.shift(2) > o.shift(2)) & (c.shift(2) > o.shift(3))
    c2 = (c.shift(1) > o.shift(1)) & (c.shift(1) > c.shift(2)) & (o.shift(1) > o.shift(2))
    c3 = (c > o) & (c > c.shift(1)) & (o > o.shift(1))
    return c1 & c2 & c3


def detect_three_black_crows(df: pd.DataFrame) -> pd.Series:
    """Detect Three Black Crows (3 consecutive strong red candles)."""
    o, h, l, c = _normalize_ohlc(df)
    c1 = (c.shift(2) < o.shift(2)) & (c.shift(2) < o.shift(3))
    c2 = (c.shift(1) < o.shift(1)) & (c.shift(1) < c.shift(2)) & (o.shift(1) < o.shift(2))
    c3 = (c < o) & (c < c.shift(1)) & (o < o.shift(1))
    return c1 & c2 & c3


PATTERN_DISPATCH = {
    "HAMMER": detect_hammer,
    "INVERTED_HAMMER": detect_inverted_hammer,
    "SHOOTING_STAR": detect_shooting_star,
    "HANGING_MAN": detect_hanging_man,
    "BULLISH_ENGULFING": detect_bullish_engulfing,
    "BEARISH_ENGULFING": detect_bearish_engulfing,
    "DOJI": detect_doji,
    "DRAGONFLY_DOJI": detect_dragonfly_doji,
    "GRAVESTONE_DOJI": detect_gravestone_doji,
    "MORNING_STAR": detect_morning_star,
    "EVENING_STAR": detect_evening_star,
    "MARUBOZU_BULLISH": detect_marubozu_bullish,
    "MARUBOZU_BEARISH": detect_marubozu_bearish,
    "PIERCING_LINE": detect_piercing_line,
    "DARK_CLOUD_COVER": detect_dark_cloud_cover,
    "THREE_WHITE_SOLDIERS": detect_three_white_soldiers,
    "THREE_BLACK_CROWS": detect_three_black_crows,
}


def evaluate_pattern(df: pd.DataFrame, pattern_name: str, candle_idx: int = -1) -> bool:
    """Evaluate whether a specific candlestick pattern is active on a given candle index.

    Args:
        df: DataFrame with OHLC columns.
        pattern_name: Name of pattern (case-insensitive, e.g. 'HAMMER', 'BULLISH_ENGULFING').
        candle_idx: Index of candle to inspect (-1 for most recently completed candle).
    """
    clean_name = pattern_name.upper().strip()
    if clean_name not in PATTERN_DISPATCH:
        raise ValueError(f"Unknown candlestick pattern '{pattern_name}'. Supported: {sorted(SUPPORTED_PATTERNS)}")

    func = PATTERN_DISPATCH[clean_name]
    series = func(df)
    if len(series) == 0:
        return False

    try:
        val = series.iloc[candle_idx]
        return bool(val) if not pd.isna(val) else False
    except IndexError:
        return False


def evaluate_all_patterns(df: pd.DataFrame, candle_idx: int = -1) -> dict[str, bool]:
    """Evaluate all supported patterns and return a dictionary of active flags."""
    results = {}
    for name in SUPPORTED_PATTERNS:
        try:
            results[name] = evaluate_pattern(df, name, candle_idx=candle_idx)
        except Exception:
            results[name] = False
    return results
