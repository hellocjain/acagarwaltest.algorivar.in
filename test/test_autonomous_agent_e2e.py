"""End-to-end full lifecycle test for Autonomous AI Trading Agents in OpenAlgo.

Tests the full path:
1. Agent creation via AutonomousAgentToolkit (Phase 1)
2. Database storage and plain-language metadata verification (Phase 2)
3. Engine sandbox execution (start_run)
4. Live Journal event logging (sm_strategy_event)
5. Emergency square-off / stop_run finalisation
"""

import json
from unittest.mock import patch
import pytest

import restx_api  # noqa: F401
from database import strategy_module_db as sm_store
from services.agent.tools import ToolContext
from services.agent.tools.build_autonomous_agent import AutonomousAgentToolkit
from services.agent.viz_sink import SINK_KEY, new_sink
from services.strategy_module import engine, state
from services.strategy_module.order_dispatch import DispatchResult
from services.strategy_module.symbol_resolver import ResolvedLeg

USER = "e2e_agent_test_user"


def _mock_resolved_leg():
    return ResolvedLeg(
        ok=True,
        symbol="NIFTY26SEP24500CE",
        exchange="NFO",
        segment="options",
        lotsize=25,
        tick_size=0.05,
        strike=24500.0,
        expiry="26-SEP-26",
        expiry_symbol="26SEP26",
        quantity=25,
        lots=1,
        option_type="CE",
        underlying="NIFTY",
        underlying_ltp=24510.0,
        atm_strike=24500.0,
    )


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


def test_autonomous_agent_full_lifecycle():
    # -------------------------------------------------------------------------
    # 1. AI Tool Draft Creation
    # -------------------------------------------------------------------------
    sink = new_sink()
    context = ToolContext(
        api_key="e2e_test_api_key",
        extras={SINK_KEY: sink},
    )
    toolkit = AutonomousAgentToolkit(context)

    with patch("services.agent.tools.build_autonomous_agent.get_username_by_apikey", return_value=USER):
        result_str = toolkit.build_autonomous_agent(
            name="E2E Premium Seller Agent",
            underlying="NIFTY",
            strategy_type="option_selling",
            capital_inr=50000,
            stop_loss_inr=1500,
            target_profit_inr=2500,
            max_lots=1,
            active_days=["MON", "TUE", "WED", "THU", "FRI"],
            entry_description="ATM Strangle when VIX < 16",
        )

    assert "E2E Premium Seller Agent" in result_str
    assert "status" in result_str

    # Verify viz_sink received agent_draft frame
    assert len(sink) == 1
    assert sink[0].frame.kind == "agent_draft"
    strategy_id = sink[0].frame.spec["strategy_id"]
    assert strategy_id > 0

    # -------------------------------------------------------------------------
    # 2. Database Metadata Verification (Phase 2 Cockpit & Details requirement)
    # -------------------------------------------------------------------------
    strategy_row = sm_store.get_strategy(strategy_id, USER)
    assert strategy_row is not None
    assert strategy_row.name.startswith("E2E Premium Seller Agent")
    assert float(strategy_row.overall_sl_mtm) == 1500.0
    assert float(strategy_row.overall_target_mtm) == 2500.0

    scheduler = strategy_row.scheduler or {}
    metadata = scheduler.get("agent_metadata") or {}
    assert metadata.get("max_lots") == 1
    assert metadata.get("capital_inr") == 50000

    plain_language = metadata.get("plain_language") or {}
    assert "when" in plain_language
    assert "entry_gates" in plain_language
    assert "it_scans" in plain_language
    assert "how_it_exits" in plain_language
    assert any("Take profit at +₹2,500" in exit_rule for exit_rule in plain_language["how_it_exits"])

    # -------------------------------------------------------------------------
    # 3. Engine Sandbox Execution (start_run)
    # -------------------------------------------------------------------------
    dispatch_mock = lambda **kw: DispatchResult(ok=True, broker_order_id="SB-E2E-1", response={})

    with (
        patch.object(engine, "_api_key_for", return_value="test-api-key"),
        patch.object(engine, "resolve_leg", return_value=_mock_resolved_leg()),
        patch.object(engine.order_dispatch, "dispatch_order", side_effect=dispatch_mock),
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
    # 4. Live Journal Event Logging (sm_strategy_event)
    # -------------------------------------------------------------------------
    sm_store.record_event(
        strategy_id,
        USER,
        kind="entry_gate_passed",
        message="Simulated Symphony XTS: Entry condition met. 1 lot sold at ₹100.",
        run_id=run_id,
        severity="info",
    )

    events = sm_store.list_events(strategy_id, limit=10)
    assert len(events) >= 1
    assert any("Simulated Symphony XTS: Entry condition met" in ev["message"] for ev in events)

    # -------------------------------------------------------------------------
    # 5. Emergency Square-Off / stop_run
    # -------------------------------------------------------------------------
    from types import SimpleNamespace

    cancel_mock = lambda **kw: DispatchResult(ok=True, broker_order_id="SB-E2E-1", response={})
    poll_mock = lambda **kw: SimpleNamespace(
        ok=True,
        order={
            "orderid": "SB-E2E-1",
            "order_status": "cancelled",
            "filled_quantity": 0,
            "average_price": 0,
            "rejection_reason": "cancelled by user",
        },
        error=None,
    )

    with (
        patch.object(engine, "_api_key_for", return_value="test-api-key"),
        patch.object(engine, "_broker_for", return_value="sandbox"),
        patch.object(engine.order_dispatch, "cancel_order", side_effect=cancel_mock, create=True),
        patch.object(engine.order_dispatch, "fetch_order_status", side_effect=poll_mock, create=True),
        patch.object(engine, "_unsubscribe_run"),
    ):
        stop_res = engine.stop_run(run_id, USER, reason="manual")

    assert stop_res.get("ok") is True, f"stop_run failed: {stop_res}"

    # Verify stopped
    final_strat = sm_store.get_strategy(strategy_id, USER)
    assert final_strat.status == "stopped"
    assert final_strat.current_run_id is None
