"""Universal Multi-Indicator & Candlestick Condition Tree Evaluator.

Parses and recursively evaluates structured condition ASTs against market data (OHLCV).
Integrates openalgo.ta (80+ indicators), native candlestick patterns,
indicator crossovers, price comparisons, and nested AND/OR/NOT logic gates.

Returns both boolean pass/fail status and real-time per-leaf diagnostics
for the frontend Live Condition Status Monitor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd
from openalgo import ta

from services.strategy_module.patterns import evaluate_pattern

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticLeaf:
    node_type: str
    label: str
    actual_value: Any
    comp: str | None = None
    threshold: Any = None
    passed: bool = False
    details: str | None = None


@dataclass
class ConditionEvaluationResult:
    passed: bool
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""


# Comparison operator mappings
COMP_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "=": lambda a, b: a == b,
}


def _get_series(df: pd.DataFrame, col: str = "close") -> pd.Series:
    col_map = {c.lower(): c for c in df.columns}
    target = col_map.get(col.lower(), col_map.get("close"))
    if not target:
        raise ValueError(f"Column '{col}' not found in DataFrame.")
    return pd.to_numeric(df[target], errors="coerce").fillna(0.0)


def compute_indicator_series(df: pd.DataFrame, name: str, params: dict[str, Any] | None = None, field_name: str | None = None) -> pd.Series:
    """Compute an indicator from openalgo.ta and return a single 1D Series."""
    clean_name = name.lower().strip()
    p = params or {}
    c = _get_series(df, "close")

    try:
        if clean_name == "rsi":
            period = int(p.get("period") or p.get("length") or 14)
            if len(c) <= period:
                return pd.Series(np.nan, index=df.index)
            raw = ta.rsi(c, period=period)
            return pd.Series(raw, index=df.index)

        elif clean_name == "ema":
            period = int(p.get("period") or p.get("length") or 9)
            if len(c) < period:
                return pd.Series(np.nan, index=df.index)
            raw = ta.ema(c, period=period)
            return pd.Series(raw, index=df.index)

        elif clean_name == "sma":
            period = int(p.get("period") or p.get("length") or 20)
            if len(c) < period:
                return pd.Series(np.nan, index=df.index)
            raw = ta.sma(c, period=period)
            return pd.Series(raw, index=df.index)

        elif clean_name == "supertrend":
            h = _get_series(df, "high")
            l = _get_series(df, "low")
            period = int(p.get("period") or p.get("length") or 10)
            if len(c) <= period:
                return pd.Series(np.nan, index=df.index)
            mult = float(p.get("multiplier") or 3.0)
            st_val, st_dir = ta.supertrend(h, l, c, period=period, multiplier=mult)
            if field_name == "direction":
                return pd.Series(st_dir, index=df.index)
            return pd.Series(st_val, index=df.index)

        elif clean_name == "macd":
            fast = int(p.get("fast") or 12)
            slow = int(p.get("slow") or 26)
            sig = int(p.get("signal") or 9)
            if len(c) <= slow:
                return pd.Series(np.nan, index=df.index)
            macd_line, sig_line, hist = ta.macd(c, fast_period=fast, slow_period=slow, signal_period=sig)
            if field_name == "signal":
                return pd.Series(sig_line, index=df.index)
            elif field_name == "hist" or field_name == "histogram":
                return pd.Series(hist, index=df.index)
            return pd.Series(macd_line, index=df.index)

        elif clean_name in ("bbands", "bollinger"):
            period = int(p.get("period") or 20)
            std = float(p.get("std_dev") or 2.0)
            if len(c) <= period:
                return pd.Series(np.nan, index=df.index)
            upper, mid, lower = ta.bbands(c, period=period, std_dev=std)
            if field_name == "upper":
                return pd.Series(upper, index=df.index)
            elif field_name == "lower":
                return pd.Series(lower, index=df.index)
            return pd.Series(mid, index=df.index)

        elif clean_name == "vwap":
            h = _get_series(df, "high")
            l = _get_series(df, "low")
            v = _get_series(df, "volume")
            raw = ta.vwap(h, l, c, v)
            return pd.Series(raw, index=df.index)

        elif clean_name == "atr":
            h = _get_series(df, "high")
            l = _get_series(df, "low")
            period = int(p.get("period") or 14)
            if len(c) <= period:
                return pd.Series(np.nan, index=df.index)
            raw = ta.atr(h, l, c, period=period)
            return pd.Series(raw, index=df.index)

        # Generic fallback: look up directly on openalgo.ta
        if hasattr(ta, clean_name):
            func = getattr(ta, clean_name)
            raw = func(c, **p)
            if isinstance(raw, tuple):
                return pd.Series(raw[0], index=df.index)
            return pd.Series(raw, index=df.index)

    except Exception as err:
        logger.warning("Could not calculate indicator %s (%s): %s", clean_name, p, err)
        return pd.Series(np.nan, index=df.index)

    raise ValueError(f"Unsupported indicator '{name}' in condition evaluator.")


def _eval_indicator_leaf(leaf: dict[str, Any], df: pd.DataFrame, idx: int) -> tuple[bool, DiagnosticLeaf]:
    ind_name = leaf.get("indicator") or leaf.get("name", "RSI")
    params = leaf.get("params") or {}
    field_name = leaf.get("field")
    comp = leaf.get("comp") or leaf.get("op", "<")
    target_val = leaf.get("value")

    series = compute_indicator_series(df, ind_name, params=params, field_name=field_name)
    actual = series.iloc[idx]

    # Special handling for categorical comparisons like Supertrend direction (1 = bullish, -1 = bearish)
    if isinstance(target_val, str) and target_val.lower() in ("bullish", "bearish", "bull", "bear"):
        is_bullish = actual == 1 or actual > 0
        expected_bullish = target_val.lower() in ("bullish", "bull")
        passed = (is_bullish == expected_bullish)
        label = f"{ind_name.upper()} is {target_val.capitalize()}"
        return passed, DiagnosticLeaf(
            node_type="indicator",
            label=label,
            actual_value="Bullish" if is_bullish else "Bearish",
            comp="==",
            threshold=target_val.capitalize(),
            passed=passed,
        )

    # Format parameter string (e.g. RSI(14))
    param_str = f"({list(params.values())[0]})" if params else ""
    field_str = f".{field_name}" if field_name else ""

    if pd.isna(actual):
        label = f"{ind_name.upper()}{field_str}{param_str} {comp} {target_val}"
        return False, DiagnosticLeaf(
            node_type="indicator",
            label=label,
            actual_value="Waiting for bars",
            comp=comp,
            threshold=target_val,
            passed=False,
            details="Insufficient historical bars for indicator calculation",
        )

    # Standard numeric comparison
    num_target = float(target_val) if target_val is not None else 0.0
    actual_num = float(actual)
    op_fn = COMP_OPS.get(comp, COMP_OPS["=="])
    passed = bool(op_fn(actual_num, num_target))

    label = f"{ind_name.upper()}{field_str}{param_str} {comp} {num_target}"

    return passed, DiagnosticLeaf(
        node_type="indicator",
        label=label,
        actual_value=round(actual_num, 2),
        comp=comp,
        threshold=num_target,
        passed=passed,
    )


def _eval_indicator_cross_leaf(leaf: dict[str, Any], df: pd.DataFrame, idx: int) -> tuple[bool, DiagnosticLeaf]:
    left_spec = leaf.get("left") or {}
    right_spec = leaf.get("right") or {}
    comp = leaf.get("comp") or leaf.get("op", "crosses_above")

    # Compute left series
    if "indicator" in left_spec:
        left_series = compute_indicator_series(
            df, left_spec["indicator"], params=left_spec.get("params"), field_name=left_spec.get("field")
        )
        left_label = f"{left_spec['indicator'].upper()}({list(left_spec.get('params', {}).values())[0] if left_spec.get('params') else ''})"
    else:
        left_col = left_spec.get("field", "close")
        left_series = _get_series(df, left_col)
        left_label = left_col.upper()

    # Compute right series
    if "indicator" in right_spec:
        right_series = compute_indicator_series(
            df, right_spec["indicator"], params=right_spec.get("params"), field_name=right_spec.get("field")
        )
        right_label = f"{right_spec['indicator'].upper()}({list(right_spec.get('params', {}).values())[0] if right_spec.get('params') else ''})"
    else:
        right_col = right_spec.get("field", "close")
        right_series = _get_series(df, right_col)
        right_label = right_col.upper()

    curr_l = left_series.iloc[idx]
    curr_r = right_series.iloc[idx]

    label = f"{left_label} {comp.replace('_', ' ')} {right_label}"

    if pd.isna(curr_l) or pd.isna(curr_r):
        return False, DiagnosticLeaf(
            node_type="indicator_cross",
            label=label,
            actual_value="Waiting for bars",
            comp=comp,
            threshold=f"{right_label}",
            passed=False,
        )

    # Needs at least 2 bars for crossover detection
    if idx == 0 or len(left_series) < 2:
        prev_l = curr_l
        prev_r = curr_r
    else:
        prev_l = left_series.iloc[idx - 1]
        prev_r = right_series.iloc[idx - 1]

    if pd.isna(prev_l) or pd.isna(prev_r):
        prev_l = curr_l
        prev_r = curr_r

    if comp == "crosses_above":
        passed = bool((prev_l <= prev_r) and (curr_l > curr_r))
    elif comp == "crosses_below":
        passed = bool((prev_l >= prev_r) and (curr_l < curr_r))
    elif comp in ("is_above", ">", ">="):
        passed = bool(curr_l > curr_r)
    elif comp in ("is_below", "<", "<="):
        passed = bool(curr_l < curr_r)
    else:
        passed = False

    return passed, DiagnosticLeaf(
        node_type="indicator_cross",
        label=label,
        actual_value=f"{curr_l:.2f} vs {curr_r:.2f}",
        comp=comp,
        threshold=f"{right_label} ({curr_r:.2f})",
        passed=passed,
    )


def _eval_candlestick_leaf(leaf: dict[str, Any], df: pd.DataFrame, idx: int) -> tuple[bool, DiagnosticLeaf]:
    pattern = leaf.get("pattern") or leaf.get("name", "HAMMER")
    passed = bool(evaluate_pattern(df, pattern, candle_idx=idx))
    label = f"{pattern.replace('_', ' ').title()} Candlestick"
    return passed, DiagnosticLeaf(
        node_type="candlestick",
        label=label,
        actual_value="Formed" if passed else "Waiting",
        threshold="Detected",
        passed=passed,
    )


def _eval_price_leaf(leaf: dict[str, Any], df: pd.DataFrame, idx: int) -> tuple[bool, DiagnosticLeaf]:
    field_col = leaf.get("field", "close").lower()
    comp = leaf.get("comp") or leaf.get("op", ">=")
    c = _get_series(df, field_col)
    curr_val = c.iloc[idx]

    mult_field = leaf.get("multiplier_field")
    mult = leaf.get("multiplier")
    target_val = leaf.get("value")

    if mult_field and mult:
        base = _get_series(df, mult_field).iloc[idx]
        target = float(base) * float(mult)
        label = f"{field_col.upper()} {comp} {mult}x {mult_field.upper()}"
    else:
        target = float(target_val) if target_val is not None else 0.0
        label = f"{field_col.upper()} {comp} {target}"

    if pd.isna(curr_val) or pd.isna(target):
        return False, DiagnosticLeaf(
            node_type="price",
            label=label,
            actual_value="Waiting for price",
            comp=comp,
            threshold=target,
            passed=False,
        )

    op_fn = COMP_OPS.get(comp, COMP_OPS["=="])
    passed = bool(op_fn(curr_val, target))

    return passed, DiagnosticLeaf(
        node_type="price",
        label=label,
        actual_value=round(curr_val, 2),
        comp=comp,
        threshold=round(target, 2),
        passed=passed,
    )


def evaluate_node(node: dict[str, Any], df: pd.DataFrame, idx: int = -1) -> tuple[bool, list[dict[str, Any]]]:
    """Recursively evaluate a node in the condition tree.

    Returns:
        (passed: bool, diagnostics: list[dict])
    """
    if not node:
        return True, []

    # Branch Node with boolean operator
    if "op" in node and "rules" in node:
        op = node["op"].upper().strip()
        rules = node["rules"]
        all_diags: list[dict[str, Any]] = []

        if op == "AND":
            branch_passed = True
            for child in rules:
                child_passed, child_diags = evaluate_node(child, df, idx)
                all_diags.extend(child_diags)
                if not child_passed:
                    branch_passed = False
            return branch_passed, all_diags

        elif op == "OR":
            branch_passed = False
            for child in rules:
                child_passed, child_diags = evaluate_node(child, df, idx)
                all_diags.extend(child_diags)
                if child_passed:
                    branch_passed = True
            return branch_passed, all_diags

        elif op == "NOT":
            if rules:
                child_passed, child_diags = evaluate_node(rules[0], df, idx)
                all_diags.extend(child_diags)
                return not child_passed, all_diags
            return True, []

    # Leaf Nodes
    node_type = (node.get("type") or "indicator").lower().strip()

    if node_type == "indicator":
        passed, diag = _eval_indicator_leaf(node, df, idx)
        return passed, [diag.__dict__]

    elif node_type == "indicator_cross":
        passed, diag = _eval_indicator_cross_leaf(node, df, idx)
        return passed, [diag.__dict__]

    elif node_type == "candlestick":
        passed, diag = _eval_candlestick_leaf(node, df, idx)
        return passed, [diag.__dict__]

    elif node_type == "price":
        passed, diag = _eval_price_leaf(node, df, idx)
        return passed, [diag.__dict__]

    # Legacy dictionary shortcut fallback (e.g. {"rsi": "<25"})
    return True, []


def evaluate_condition_tree(tree: dict[str, Any], df: pd.DataFrame, candle_idx: int = -1) -> ConditionEvaluationResult:
    """Evaluate a full condition tree against an OHLCV DataFrame."""
    if df is None or len(df) == 0:
        return ConditionEvaluationResult(passed=False, diagnostics=[], summary="No candle data available.")

    passed, diagnostics = evaluate_node(tree, df, idx=candle_idx)
    passed_count = sum(1 for d in diagnostics if d.get("passed"))
    summary = f"{passed_count}/{len(diagnostics)} rules passed" if diagnostics else "No active conditions"

    return ConditionEvaluationResult(passed=passed, diagnostics=diagnostics, summary=summary)


def legacy_rules_to_condition_tree(rules: dict[str, Any] | list[Any]) -> dict[str, Any]:
    """Convert simple flat indicator dictionary into a standardized condition tree AST."""
    if not rules:
        return {"op": "AND", "rules": []}

    ast_rules = []

    if isinstance(rules, dict):
        for k, v in rules.items():
            k_lower = str(k).lower().strip()
            if k_lower == "rsi":
                if isinstance(v, dict):
                    ast_rules.append({
                        "type": "indicator",
                        "indicator": "RSI",
                        "params": {"period": v.get("period", 14)},
                        "comp": v.get("op", "<"),
                        "value": float(v.get("val", 25.0)),
                    })
                elif isinstance(v, (int, float)):
                    ast_rules.append({"type": "indicator", "indicator": "RSI", "params": {"period": 14}, "comp": "<", "value": float(v)})
                elif isinstance(v, str) and v.startswith(("<", ">", "<=", ">=")):
                    op = "<=" if v.startswith("<=") else (">=" if v.startswith(">=") else v[0])
                    val = float(v.lstrip("<>="))
                    ast_rules.append({"type": "indicator", "indicator": "RSI", "params": {"period": 14}, "comp": op, "value": val})

            elif k_lower == "supertrend":
                direction = v.get("direction", "bullish") if isinstance(v, dict) else str(v)
                ast_rules.append({
                    "type": "indicator",
                    "indicator": "Supertrend",
                    "params": {"period": 10, "multiplier": 3.0},
                    "field": "direction",
                    "comp": "==",
                    "value": direction,
                })

            elif k_lower in ("ema", "sma"):
                period = v.get("period", 20) if isinstance(v, dict) else int(v)
                ast_rules.append({"type": "indicator_cross", "left": {"field": "close"}, "comp": "is_above", "right": {"indicator": k_lower.upper(), "params": {"period": period}}})

            elif k_lower == "candlestick":
                pattern = str(v).upper()
                ast_rules.append({"type": "candlestick", "pattern": pattern})

    elif isinstance(rules, list):
        for item in rules:
            if isinstance(item, dict):
                ast_rules.append(item)

    return {"op": "AND", "rules": ast_rules}


def extract_tree_leaves(tree: dict[str, Any]) -> list[dict[str, Any]]:
    """Recursively flatten all leaf rules in a condition tree."""
    leaves: list[dict[str, Any]] = []
    if not tree:
        return leaves

    if "rules" in tree and isinstance(tree["rules"], list):
        for child in tree["rules"]:
            leaves.extend(extract_tree_leaves(child))
    elif tree.get("type"):
        leaves.append(tree)

    return leaves


def condition_tree_to_plain_language(tree: dict[str, Any]) -> list[str]:
    """Convert a condition tree AST into user-friendly bullet points."""
    if not tree:
        return []

    lines = []
    leaves = extract_tree_leaves(tree)
    for r in leaves:
        rtype = r.get("type", "indicator")
        if rtype == "indicator":
            ind = r.get("indicator", "RSI").upper()
            p = r.get("params", {})
            param_str = f"({list(p.values())[0]})" if p else ""
            field_str = f".{r.get('field')}" if r.get("field") else ""
            lines.append(f"{ind}{field_str}{param_str} {r.get('comp', '<')} {r.get('value')}")
        elif rtype == "indicator_cross":
            lines.append(f"{r.get('left', {}).get('indicator', 'Price')} {r.get('comp', 'crosses')} {r.get('right', {}).get('indicator', 'MA')}")
        elif rtype == "candlestick":
            lines.append(f"{r.get('pattern', 'Hammer').replace('_', ' ').title()} formation on candle close")
        elif rtype == "price":
            lines.append(f"Price {r.get('comp', '>=')} {r.get('value')}")
    return lines
