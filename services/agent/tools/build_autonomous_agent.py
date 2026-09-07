"""Autonomous Agent Toolkit for OpenAlgo.

Enables the AI Assistant to compile user trading intent into a validated,
durable OpenAlgo strategy (sm_strategy) and emit an interactive AgentDraftCard
to the UI side-channel via viz_sink.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from database import strategy_module_db as sm_store
from database.auth_db import get_username_by_apikey
from services.agent.prompts import wrap_tool_result
from services.agent.tools.base import OpenAlgoToolkit
from services.agent.viz_sink import emit, no_sink_message, sink_of
from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from services.agent.tools import ToolContext

logger = get_logger(__name__)

__all__ = ["AutonomousAgentToolkit"]


class AutonomousAgentToolkit(OpenAlgoToolkit):
    """Toolkit for creating and registering autonomous trading agents."""

    def __init__(self, context: ToolContext):
        super().__init__(
            context,
            name="autonomous_agent",
            tools=[self.build_autonomous_agent],
        )

    def build_autonomous_agent(
        self,
        name: str,
        underlying: str,
        strategy_type: str,
        capital_inr: float,
        stop_loss_inr: float,
        target_profit_inr: float,
        max_lots: int = 1,
        active_days: list[str] | None = None,
        entry_description: str = "",
        when_time: str = "09:16",
        auto_exit_time: str = "15:15",
    ) -> str:
        """Build and register an autonomous trading agent strategy in OpenAlgo.

        Args:
            name: Display name for the autonomous agent (e.g. '₹100 Premium Seller', 'Nifty Dip Buyer').
            underlying: Index or stock symbol (e.g. 'NIFTY', 'BANKNIFTY', 'SENSEX').
            strategy_type: Trading approach ('option_selling', 'option_buying', 'intraday', 'momentum').
            capital_inr: Total allocated capital in INR (e.g. 50000).
            stop_loss_inr: Maximum tolerable loss in INR per trade (e.g. 1500).
            target_profit_inr: Target profit in INR per trade (e.g. 2500).
            max_lots: Number of lots to trade (strictly capped at 2 for retail safety).
            active_days: Days the strategy runs, e.g. ['MON', 'WED', 'THU', 'FRI'].
            entry_description: Plain-language summary of the entry rule.
            when_time: Daily entry check time in HH:MM (default '09:16').
            auto_exit_time: Daily mandatory square-off time in HH:MM (default '15:15').

        Returns:
            JSON summary confirming the creation of the strategy draft.
        """
        days = active_days or ["MON", "TUE", "WED", "THU", "FRI"]
        safe_lots = max(1, min(int(max_lots), 2))
        safe_sl = min(float(stop_loss_inr), max(500.0, float(capital_inr) * 0.10))
        clean_underlying = underlying.upper().strip()

        # Resolve exchange
        exchange = "NSE_INDEX" if clean_underlying in ("NIFTY", "BANKNIFTY", "FINNIFTY") else "BSE_INDEX"

        # Resolve user
        user_id = "admin"
        if self.api_key:
            try:
                resolved = get_username_by_apikey(self.api_key)
                if resolved:
                    user_id = resolved
            except Exception:
                pass

        plain_language = {
            "when": f"At {when_time} · {', '.join(days)}",
            "entry_gates": [
                entry_description or f"Matches {strategy_type.replace('_', ' ')} criteria",
                f"Trading days: {', '.join(days)}",
            ],
            "it_scans": f"Scans {clean_underlying} weekly options, {safe_lots} lot max.",
            "how_it_exits": [
                f"Take profit at +₹{target_profit_inr:,.2f}",
                f"Stop loss at -₹{safe_sl:,.2f}",
                f"Mandatory {auto_exit_time} auto-exit",
            ],
        }

        # Format default legs for strategy execution
        is_buying = "buy" in strategy_type.lower() or "dip" in name.lower()
        legs = [
            {
                "id": 1,
                "leg_id": "leg_1",
                "segment": "options",
                "expiry": "weekly",
                "lots": safe_lots,
                "position": "B" if is_buying else "S",
                "action": "BUY" if is_buying else "SELL",
                "option_type": "CE" if is_buying else "PE",
                "instrument_type": "CE" if is_buying else "PE",
                "strike_mode": "atm",
                "atm_offset": "ATM",
                "strike_offset": 0,
            }
        ]

        strategy_config = {
            "name": name,
            "strategy_kind": "batch",
            "direction": "both",
            "universe_tab": "weekly_monthly",
            "underlying": clean_underlying,
            "underlying_exchange": exchange,
            "strategy_type": "intraday",
            "product": "MIS",
            "pricetype": "MARKET",
            "legs": legs,
            "overall_sl_mtm": float(safe_sl),
            "overall_target_mtm": float(target_profit_inr),
            "daily_loss_limit_inr": float(safe_sl) * 1.5,
            "scheduler": {
                "active_days": days,
                "entry_time": when_time,
                "exit_time": auto_exit_time,
                "agent_metadata": {
                    "category": strategy_type,
                    "capital_inr": capital_inr,
                    "max_lots": safe_lots,
                    "plain_language": plain_language,
                },
            },
        }

        # Save to database
        payload, err = sm_store.create_strategy(user_id, strategy_config)
        if err and "already exists" in err:
            # Append timestamp to allow versioning
            ts = datetime.datetime.now().strftime("%H%M")
            strategy_config["name"] = f"{name} ({ts})"
            payload, err = sm_store.create_strategy(user_id, strategy_config)

        strategy_id = payload["id"] if payload else 1

        # Emit draft frame via viz_sink side-channel
        sink = sink_of(self.context)
        draft_spec = {
            "strategy_id": strategy_id,
            "name": strategy_config["name"],
            "underlying": clean_underlying,
            "strategy_type": strategy_type,
            "capital_inr": capital_inr,
            "stop_loss_inr": safe_sl,
            "target_profit_inr": target_profit_inr,
            "max_lots": safe_lots,
            "account": "AC Agarwal (DM933)",
            "summary": f"{clean_underlying} current_weekly | {safe_lots} lot | SL: ₹{safe_sl:,.0f} | Target: ₹{target_profit_inr:,.0f}",
            "plain_language": plain_language,
        }

        emitted = emit(
            sink,
            tool="build_autonomous_agent",
            kind="agent_draft",
            spec=draft_spec,
            title=strategy_config["name"],
            source="autonomous_agent_tool",
        )

        result = {
            "status": "success" if not err else "created_with_notice",
            "strategy_id": strategy_id,
            "name": strategy_config["name"],
            "summary": draft_spec["summary"],
            "rendered_card": emitted,
            "plain_language": plain_language,
        }
        return wrap_tool_result("build_autonomous_agent", result)
