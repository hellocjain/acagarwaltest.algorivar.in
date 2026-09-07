"""Comprehensive test suite for Universal Multi-Stock Scanner AI Trading Agents.

Validates:
1. Creation of multi-stock scanner agents (NIFTY 500, RSI < 25, Supertrend Bullish).
2. Plain-language metadata generation (WHEN, ENTRY GATES, IT SCANS, HOW IT EXITS).
3. Universe resolution engine (NIFTY50, NIFTY100, NIFTY500, FNO_STOCKS).
4. Engine start_run execution in sandbox mode without derivative leg requirements.
5. Decision Journal logging in sm_strategy_event.
6. Clean stop_run finalisation.
"""

from unittest.mock import patch
import pytest

import restx_api  # noqa: F401
from database import strategy_module_db as sm_store
from services.agent.tools import ToolContext
from services.agent.tools.build_autonomous_agent import AutonomousAgentToolkit
from services.agent.viz_sink import SINK_KEY, new_sink
from services.strategy_module import engine, state
from services.strategy_module.scanner_runner import ScannerRunner, evaluate_scanner_strategy
from services.strategy_module.universe import resolve_universe_symbols

USER = "scanner_agent_test_user"


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


def test_universe_resolution():
    """Verify universe expansion for NIFTY 50, NIFTY 100, NIFTY 500, and F&O."""
    nifty50 = resolve_universe_symbols("NIFTY50")
    assert len(nifty50) == 50
    assert "RELIANCE" in nifty50
    assert "TCS" in nifty50

    nifty500 = resolve_universe_symbols("NIFTY500")
    assert len(nifty500) >= 350
    assert "TATAMOTORS" in nifty500
    assert "ZOMATO" in nifty500

    fno = resolve_universe_symbols("FNO_STOCKS")
    assert len(fno) >= 100
    assert "SBIN" in fno

    custom = resolve_universe_symbols("INFY, WIPRO, HCLTECH")
    assert custom == ["INFY", "WIPRO", "HCLTECH"]


def test_scanner_agent_tool_and_lifecycle():
    # -------------------------------------------------------------------------
    # 1. AI Tool Draft Creation
    # -------------------------------------------------------------------------
    sink = new_sink()
    context = ToolContext(
        api_key="scanner_test_api_key",
        extras={SINK_KEY: sink},
    )
    toolkit = AutonomousAgentToolkit(context)

    with patch("services.agent.tools.build_autonomous_agent.get_username_by_apikey", return_value=USER):
        result_str = toolkit.build_autonomous_agent(
            name="NIFTY 500 RSI & Supertrend Hunter",
            strategy_category="scanner",
            universe="NIFTY500",
            timeframe="5m",
            indicator_rules={
                "rsi": {"period": 14, "op": "<", "val": 25},
                "supertrend": {"direction": "bullish"},
            },
            exit_rules={
                "target_pct": 10.0,
                "stop_loss_pct": 5.0,
                "rsi_exit": 75.0,
            },
            capital_per_trade_inr=10000.0,
            max_concurrent_positions=5,
            product_type="CNC",
            entry_description="RSI < 25 oversold bounce with Supertrend bullish filter",
        )

    assert "NIFTY 500 RSI & Supertrend Hunter" in result_str
    assert "status" in result_str

    # Verify viz_sink received agent_draft frame
    assert len(sink) == 1
    assert sink[0].frame.kind == "agent_draft"
    spec = sink[0].frame.spec
    assert spec["strategy_category"] == "scanner"
    assert spec["universe"] == "NIFTY500"
    assert spec["capital_per_trade_inr"] == 10000.0
    assert spec["max_concurrent_positions"] == 5

    strategy_id = spec["strategy_id"]
    assert strategy_id > 0

    # -------------------------------------------------------------------------
    # 2. Database Verification & Plain-Language Breakdown
    # -------------------------------------------------------------------------
    strategy_row = sm_store.get_strategy(strategy_id, USER)
    assert strategy_row is not None
    assert strategy_row.strategy_kind == "scanner"

    scheduler = strategy_row.scheduler or {}
    meta = scheduler.get("agent_metadata") or {}
    assert meta.get("category") == "scanner"
    assert meta.get("universe") == "NIFTY500"
    assert meta.get("capital_per_trade_inr") == 10000.0
    assert meta.get("max_concurrent_positions") == 5

    plain = meta.get("plain_language") or {}
    assert "5m candle close" in plain.get("when", "").lower()
    assert any("RSI(14) < 25" in gate for gate in plain.get("entry_gates", []))
    assert any("Supertrend" in gate for gate in plain.get("entry_gates", []))
    assert "NIFTY500" in plain.get("it_scans", "")
    assert any("10.0%" in exit_rule for exit_rule in plain.get("how_it_exits", []))
    assert any("5.0%" in exit_rule for exit_rule in plain.get("how_it_exits", []))

    # -------------------------------------------------------------------------
    # 3. Engine start_run Execution (Sandbox Mode)
    # -------------------------------------------------------------------------
    with (
        patch.object(engine, "_api_key_for", return_value="test-api-key"),
        patch.object(engine, "_broker_for", return_value="sandbox"),
    ):
        start_res = engine.start_run(strategy_id, USER, mode="sandbox")

    assert start_res.ok is True, f"start_run failed: {start_res.error}"
    assert start_res.run_id is not None
    run_id = start_res.run_id

    # Verify strategy status is running
    updated_strat = sm_store.get_strategy(strategy_id, USER)
    assert updated_strat.status == "running"
    assert updated_strat.current_run_id == run_id

    # -------------------------------------------------------------------------
    # 4. Decision Journal Verification (sm_strategy_event)
    # -------------------------------------------------------------------------
    events = sm_store.list_events(strategy_id)
    kinds = [e["kind"] for e in events]

    assert "run_started" in kinds
    assert "scan_started" in kinds
    assert "entry_gate_matched" in kinds
    assert "order_filled" in kinds

    # Verify order filled event content
    filled_event = next(e for e in events if e["kind"] == "order_filled")
    assert "Placed BUY CNC" in filled_event["message"]
    assert "Target:" in filled_event["message"]
    assert "SL:" in filled_event["message"]

    # -------------------------------------------------------------------------
    # 5. Engine stop_run Finalisation
    # -------------------------------------------------------------------------
    with patch.object(engine, "_api_key_for", return_value="test-api-key"):
        stop_res = engine.stop_run(run_id, USER, reason="manual")

    assert stop_res.get("ok") is True or stop_res.get("stop_pending") is False
    final_strat = sm_store.get_strategy(strategy_id, USER)
    assert final_strat.status == "stopped"
