"""Integration tests for Autonomous Agent with Multi-Indicator & Candlestick Condition Trees."""

from unittest.mock import patch
import pytest

import restx_api  # noqa: F401
from database import strategy_module_db as sm_store
from services.agent.tools import ToolContext
from services.agent.tools.build_autonomous_agent import AutonomousAgentToolkit
from services.agent.viz_sink import SINK_KEY, new_sink
from services.strategy_module import engine, state
from services.strategy_module.scanner_runner import ScannerRunner

USER = "condition_tree_agent_test_user"


@pytest.fixture(autouse=True)
def clean_test_env():
    sm_store.db_session.remove()
    sm_store.init_db()

    def purge():
        for row in sm_store.list_strategies(USER):
            if row.get("current_run_id"):
                state.clear_run_state(row["current_run_id"])
            sm_store.set_strategy_status(row["id"], "stopped", None)
            sm_store.delete_strategy(row["id"], USER)
        sm_store.clear_strategy_module_cache()

    purge()
    yield
    purge()


def test_build_agent_with_condition_tree_ast():
    sink = new_sink()
    context = ToolContext(
        api_key="cond_tree_key",
        extras={SINK_KEY: sink},
    )
    toolkit = AutonomousAgentToolkit(context)

    # Complex AST: (RSI < 25 AND Hammer) OR (EMA 9 crosses EMA 21)
    condition_tree = {
        "op": "OR",
        "rules": [
            {
                "op": "AND",
                "rules": [
                    {"type": "indicator", "indicator": "RSI", "params": {"period": 14}, "comp": "<", "value": 25.0},
                    {"type": "candlestick", "pattern": "HAMMER"},
                ],
            },
            {
                "type": "indicator_cross",
                "left": {"indicator": "EMA", "params": {"period": 9}},
                "comp": "crosses_above",
                "right": {"indicator": "EMA", "params": {"period": 21}},
            },
        ],
    }

    with patch("services.agent.tools.build_autonomous_agent.get_username_by_apikey", return_value=USER):
        res = toolkit.build_autonomous_agent(
            name="Advanced Confluence Hunter",
            strategy_category="scanner",
            universe="NIFTY50",
            timeframe="15m",
            condition_tree=condition_tree,
            exit_rules={"target_pct": 12.0, "stop_loss_pct": 6.0},
            capital_per_trade_inr=15000.0,
            max_concurrent_positions=3,
        )

    assert "Advanced Confluence Hunter" in res
    assert len(sink) >= 1
    spec = sink[0].frame.spec
    assert "condition_tree" in spec
    assert spec["condition_tree"]["op"] == "OR"

    # Verify strategy in database
    strategies = sm_store.list_strategies(USER)
    assert len(strategies) == 1
    st = strategies[0]
    meta = st["scheduler"]["agent_metadata"]
    assert "condition_tree" in meta
    assert meta["condition_tree"]["op"] == "OR"

    # Verify ScannerRunner diagnostics extraction
    runner = ScannerRunner(st["id"], USER, mode="sandbox")
    diags = runner.get_live_condition_diagnostics()
    assert len(diags) >= 2
    diag_labels = [d["label"] for d in diags]
    assert any("RSI" in lbl for lbl in diag_labels)
    assert any("Hammer" in lbl for lbl in diag_labels)
