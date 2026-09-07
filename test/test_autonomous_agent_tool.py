import pytest
from services.agent.tools import ToolContext
from services.agent.tools.build_autonomous_agent import AutonomousAgentToolkit
from services.agent.viz_sink import new_sink, SINK_KEY
from database import strategy_module_db as sm_store

def test_autonomous_agent_toolkit_builds_draft():
    sink = new_sink()
    context = ToolContext(
        api_key="test_api_key_1234567890abcdef",
        extras={SINK_KEY: sink}
    )
    
    toolkit = AutonomousAgentToolkit(context)
    
    # Test building an agent
    result = toolkit.build_autonomous_agent(
        name="Test Nifty Dip Buyer",
        underlying="NIFTY",
        strategy_type="option_buying",
        capital_inr=50000,
        stop_loss_inr=1500,
        target_profit_inr=2500,
        max_lots=5, # Intentionally pass > 2 to test retail cap!
        active_days=["MON", "WED", "FRI"],
        entry_description="Crosses 20 EMA on 5m chart"
    )
    
    assert "Test Nifty Dip Buyer" in result
    assert "status" in result
    
    # Verify sink received 'agent_draft' frame
    assert len(sink) == 1
    entry = sink[0]
    assert entry.tool == "build_autonomous_agent"
    assert entry.frame.kind == "agent_draft"
    assert entry.frame.spec["name"].startswith("Test Nifty Dip Buyer")
    assert entry.frame.spec["max_lots"] == 2 # Capped at 2 lots!
    assert entry.frame.spec["capital_inr"] == 50000
    assert entry.frame.spec["stop_loss_inr"] == 1500
    assert "plain_language" in entry.frame.spec
    assert "when" in entry.frame.spec["plain_language"]
    assert "entry_gates" in entry.frame.spec["plain_language"]
    assert "how_it_exits" in entry.frame.spec["plain_language"]
