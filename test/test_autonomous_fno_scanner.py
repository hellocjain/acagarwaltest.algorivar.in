"""Comprehensive test suite for Universal F&O Stock Derivatives Scanner & Dual Exit Gates.

Validates:
1. Dynamic ATM/OTM strike resolution across F&O stocks with lot sizes.
2. Next-Month Rollover Shield (prevents NSE physical settlement within 4 days of expiry).
3. AutonomousAgentToolkit creation with instrument_preference='options'.
4. viz_sink side-channel payload validation for derivative cards.
5. ScannerRunner position entry with stock option contract resolution & budget checks.
6. Dual Exit Gate evaluation:
   - Gate A: Option Premium Target (+40%) & Stop Loss (-25%)
   - Gate B: Underlying Stock Target (+10%), Stop Loss (-5%), RSI Overbought (>75), Supertrend reversal.
7. Stock Futures scanner workflow.
"""

from datetime import date
from unittest.mock import patch
import pytest

import restx_api  # noqa: F401
from database import strategy_module_db as sm_store
from services.agent.tools import ToolContext
from services.agent.tools.build_autonomous_agent import AutonomousAgentToolkit
from services.agent.viz_sink import SINK_KEY, new_sink
from services.strategy_module import engine, state
from services.strategy_module.scanner_runner import ScannerRunner
from services.strategy_module.stock_derivatives import (
    get_last_thursday,
    resolve_monthly_expiry,
    resolve_stock_future,
    resolve_stock_option,
)

USER = "fno_scanner_test_user"


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


def test_stock_derivatives_resolution():
    """Verify strike resolution, lot sizing, and symbol formatting."""
    # Test TATAMOTORS ATM Call Option
    opt_ce = resolve_stock_option("TATAMOTORS", ltp=982.50, option_type="CE", as_of=date(2026, 9, 10))
    assert opt_ce.ok is True
    assert opt_ce.strike == 980.0
    assert opt_ce.lot_size == 550
    assert opt_ce.quantity == 550
    assert opt_ce.option_type == "CE"
    assert "TATAMOTORS" in opt_ce.symbol
    assert "980CE" in opt_ce.symbol
    assert opt_ce.estimated_premium > 0
    assert opt_ce.total_capital_required > 0

    # Test RELIANCE ATM Put Option
    opt_pe = resolve_stock_option("RELIANCE", ltp=2945.0, option_type="PE", as_of=date(2026, 9, 10))
    assert opt_pe.ok is True
    assert opt_pe.strike == 2940.0
    assert opt_pe.lot_size == 250
    assert "RELIANCE" in opt_pe.symbol
    assert "2940PE" in opt_pe.symbol

    # Test Stock Futures
    fut = resolve_stock_future("INFY", ltp=1824.0, as_of=date(2026, 9, 10))
    assert fut.ok is True
    assert fut.lot_size == 400
    assert "INFY" in fut.symbol
    assert fut.symbol.endswith("FUT")
    assert fut.estimated_margin_required > 50000.0


def test_rollover_shield():
    """Verify Next-Month Rollover Shield activates when within 4 days of expiry."""
    # In September 2026, the last Thursday is 24-SEP-2026
    thursday = get_last_thursday(2026, 9)
    assert thursday == date(2026, 9, 24)

    # 1. Early in month (Sep 10): 14 days away -> Rollover Shield should NOT activate
    exp_date, fmt_exp, sym_exp, rolled_over = resolve_monthly_expiry(as_of=date(2026, 9, 10), buffer_days=4)
    assert rolled_over is False
    assert exp_date == date(2026, 9, 24)

    # 2. Expiry week Tuesday (Sep 22): 2 days away (< 4) -> Rollover Shield MUST activate
    exp_date_roll, fmt_exp_roll, sym_exp_roll, rolled_over_active = resolve_monthly_expiry(
        as_of=date(2026, 9, 22), buffer_days=4
    )
    assert rolled_over_active is True
    # Rolls over to October 2026 last Thursday (29-OCT-2026)
    assert exp_date_roll == date(2026, 10, 29)
    assert "OCT" in sym_exp_roll


def test_fno_options_agent_creation_and_viz_sink():
    """Verify AI Agent tool can build an autonomous F&O Stock Options scanner."""
    sink = new_sink()
    context = ToolContext(
        api_key="fno_test_api_key",
        extras={SINK_KEY: sink},
    )
    toolkit = AutonomousAgentToolkit(context)

    with patch("services.agent.tools.build_autonomous_agent.get_username_by_apikey", return_value=USER):
        result_str = toolkit.build_autonomous_agent(
            name="F&O Momentum Call Options Hunter",
            strategy_category="scanner",
            universe="FNO",
            instrument_preference="options",
            option_type="CE",
            strike_mode="atm",
            max_premium_per_trade_inr=15000.0,
            premium_target_pct=40.0,
            premium_sl_pct=25.0,
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
            max_concurrent_positions=3,
            entry_description="RSI < 25 oversold bounce with Supertrend bullish confirmation",
        )

    assert "F&O Momentum Call Options Hunter" in result_str
    assert "status" in result_str

    # Verify viz_sink emitted agent_draft with options details
    assert len(sink) >= 1
    draft_frame = sink[0].frame
    assert draft_frame.kind == "agent_draft"
    spec = draft_frame.spec
    assert spec["instrument_preference"] == "options"
    assert spec["option_type"] == "CE"
    assert spec["strike_mode"] == "atm"
    assert spec["max_premium_per_trade_inr"] == 15000.0
    assert spec["premium_target_pct"] == 40.0
    assert spec["premium_sl_pct"] == 25.0
    assert "Dual Exit Gate A" in str(spec["plain_language"]["how_it_exits"])

    # Verify strategy created in database
    strategies = sm_store.list_strategies(USER)
    assert len(strategies) == 1
    st = strategies[0]
    meta = st["scheduler"]["agent_metadata"]
    assert meta["instrument_preference"] == "options"
    assert meta["option_type"] == "CE"
    assert meta["max_premium_per_trade_inr"] == 15000.0


def test_scanner_runner_fno_options_scan():
    """Verify ScannerRunner resolves single-stock options on simulated match."""
    # Create an options scanner agent
    strategy_config = {
        "name": "Live F&O Runner Test",
        "strategy_kind": "scanner",
        "direction": "both",
        "universe_tab": "stocks_fno",
        "underlying": "FNO",
        "underlying_exchange": "NSE",
        "strategy_type": "scanner",
        "product": "NRML",
        "pricetype": "MARKET",
        "legs": [],
        "overall_sl_mtm": 11250.0,
        "overall_target_mtm": 18000.0,
        "daily_loss_limit_inr": 15000.0,
        "scheduler": {
            "active_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
            "entry_time": "09:16",
            "exit_time": "15:15",
            "agent_metadata": {
                "strategy_category": "scanner",
                "instrument_preference": "options",
                "option_type": "CE",
                "strike_mode": "atm",
                "max_premium_per_trade_inr": 20000.0,
                "premium_target_pct": 40.0,
                "premium_sl_pct": 25.0,
                "universe": "FNO",
                "timeframe": "5m",
                "capital_per_trade_inr": 20000.0,
                "max_concurrent_positions": 2,
                "product_type": "NRML",
                "exit_rules": {"target_pct": 10.0, "stop_loss_pct": 5.0, "rsi_exit": 75.0},
            },
        },
    }

    payload, err = sm_store.create_strategy(USER, strategy_config)
    assert err is None
    strat_id = payload["id"]

    runner = ScannerRunner(strat_id, USER, mode="sandbox")
    assert runner.instrument_preference == "options"
    assert runner.option_type == "CE"
    assert runner.max_premium_per_trade == 20000.0

    # Evaluate scan with simulated stock matches
    mock_matches = [
        {"symbol": "TATAMOTORS", "ltp": 982.50, "rsi": 22.5, "supertrend": "bullish"},
    ]
    scan_res = runner.evaluate_scan(mock_matches=mock_matches)

    assert scan_res["matches_count"] == 1
    assert len(scan_res["orders_placed"]) == 1
    order = scan_res["orders_placed"][0]
    assert order["instrument"] == "options"
    assert "TATAMOTORS" in order["contract_symbol"]
    assert "980CE" in order["contract_symbol"]
    assert order["gate_a_target"] > order["price"]
    assert order["gate_a_sl"] < order["price"]
    assert order["gate_b_target"] == round(982.50 * 1.10, 2)
    assert order["gate_b_sl"] == round(982.50 * 0.95, 2)

    # Verify event logged in Decision Journal
    events = sm_store.list_events(strat_id, limit=10)
    event_kinds = [e["kind"] for e in events]
    assert "scan_started" in event_kinds
    assert "entry_gate_matched" in event_kinds
    assert "order_filled" in event_kinds


def test_dual_exit_gates_evaluation():
    """Verify Dual Exit Gates (Gate A: Option Premium, Gate B: Underlying Stock/Indicators)."""
    strategy_config = {
        "name": "Dual Exit Test Agent",
        "strategy_kind": "scanner",
        "direction": "both",
        "universe_tab": "stocks_fno",
        "underlying": "FNO",
        "underlying_exchange": "NSE",
        "strategy_type": "scanner",
        "product": "NRML",
        "pricetype": "MARKET",
        "legs": [],
        "overall_sl_mtm": 5000.0,
        "overall_target_mtm": 10000.0,
        "daily_loss_limit_inr": 7500.0,
        "scheduler": {
            "agent_metadata": {
                "instrument_preference": "options",
                "max_premium_per_trade_inr": 20000.0,
            }
        },
    }
    payload, err = sm_store.create_strategy(USER, strategy_config)
    strat_id = payload["id"]
    runner = ScannerRunner(strat_id, USER, mode="sandbox")

    mock_position = {
        "contract_symbol": "TATAMOTORS24SEP26980CE",
        "underlying": "TATAMOTORS",
        "price": 27.0,
        "gate_a_target": 37.8,  # +40%
        "gate_a_sl": 20.25,     # -25%
        "gate_b_target": 1080.0, # Stock +10%
        "gate_b_sl": 930.0,      # Stock -5%
        "rsi_exit": 75.0,
    }

    # 1. Neutral market - holding within bounds
    res_hold = runner.evaluate_dual_exit(
        position=mock_position,
        current_option_price=29.0,
        current_stock_price=990.0,
        current_rsi=45.0,
        current_supertrend="bullish",
    )
    assert res_hold["exit"] is False

    # 2. Gate A: Option Premium Target reached
    res_gate_a_tgt = runner.evaluate_dual_exit(
        position=mock_position,
        current_option_price=38.5,
        current_stock_price=1010.0,
    )
    assert res_gate_a_tgt["exit"] is True
    assert "Gate A" in res_gate_a_tgt["gate"]
    assert "Target hit" in res_gate_a_tgt["reason"]

    # 3. Gate A: Option Premium Stop Loss breached
    res_gate_a_sl = runner.evaluate_dual_exit(
        position=mock_position,
        current_option_price=19.5,
        current_stock_price=960.0,
    )
    assert res_gate_a_sl["exit"] is True
    assert "Gate A" in res_gate_a_sl["gate"]
    assert "Stop Loss hit" in res_gate_a_sl["reason"]

    # 4. Gate B: Underlying Stock reaches target
    res_gate_b_tgt = runner.evaluate_dual_exit(
        position=mock_position,
        current_option_price=32.0,
        current_stock_price=1085.0,
    )
    assert res_gate_b_tgt["exit"] is True
    assert "Gate B" in res_gate_b_tgt["gate"]
    assert "Underlying Target Price reached" in res_gate_b_tgt["reason"]

    # 5. Gate B: Technical Indicator RSI > 75
    res_gate_b_rsi = runner.evaluate_dual_exit(
        position=mock_position,
        current_option_price=30.0,
        current_stock_price=1020.0,
        current_rsi=76.5,
    )
    assert res_gate_b_rsi["exit"] is True
    assert "Gate B" in res_gate_b_rsi["gate"]
    assert "RSI Overbought" in res_gate_b_rsi["reason"]

    # 6. Gate B: Technical Indicator Supertrend Bearish Reversal
    res_gate_b_st = runner.evaluate_dual_exit(
        position=mock_position,
        current_option_price=26.0,
        current_stock_price=970.0,
        current_supertrend="bearish",
    )
    assert res_gate_b_st["exit"] is True
    assert "Gate B" in res_gate_b_st["gate"]
    assert "Supertrend flipped to Bearish" in res_gate_b_st["reason"]
