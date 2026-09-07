"""Autonomous Agent Toolkit for OpenAlgo.

Enables the AI Assistant to compile user trading intent into a validated,
durable OpenAlgo strategy (sm_strategy) for both Single-Index Options and
Universal Multi-Stock Scanners (NIFTY 500, RSI, Supertrend, etc.), and emit
an interactive AgentDraftCard to the UI side-channel via viz_sink.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from database import strategy_module_db as sm_store
from database.auth_db import get_username_by_apikey
from services.agent.prompts import wrap_tool_result
from services.agent.tools.base import OpenAlgoToolkit
from services.agent.viz_sink import emit, no_sink_message, sink_of
from services.strategy_module.universe import resolve_universe_symbols
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
        strategy_category: str = "options",
        # Options strategy parameters:
        underlying: str = "NIFTY",
        strategy_type: str = "weekly_option_selling",
        capital_inr: float = 50000.0,
        stop_loss_inr: float = 1500.0,
        target_profit_inr: float = 2500.0,
        max_lots: int = 1,
        active_days: list[str] | None = None,
        when_time: str = "09:16",
        auto_exit_time: str = "15:15",
        # Scanner strategy parameters:
        universe: str = "NIFTY500",
        timeframe: str = "5m",
        indicator_rules: dict | str | None = None,
        exit_rules: dict | str | None = None,
        capital_per_trade_inr: float = 10000.0,
        max_concurrent_positions: int = 5,
        product_type: str = "CNC",
        entry_description: str = "",
    ) -> str:
        """Build and register an autonomous trading agent strategy in OpenAlgo.

        Supports two distinct execution categories:
        1. 'options': Derivatives option seller/buyer on indices (NIFTY/BANKNIFTY)
        2. 'scanner': Multi-stock technical scanner across universes (NIFTY 500, RSI, Supertrend, etc.)

        Args:
            name: Display name for the autonomous agent (e.g. 'Nifty 500 RSI & Supertrend Dip Buyer').
            strategy_category: 'options' for index derivatives or 'scanner' for stock universe scanning.
            underlying: Index/Stock for options mode (e.g. 'NIFTY', 'BANKNIFTY').
            strategy_type: Trading approach ('option_selling', 'option_buying', 'momentum', 'mean_reversion').
            capital_inr: Total allocated portfolio capital in INR (e.g. 50000).
            stop_loss_inr: Maximum loss in INR or percent (e.g. 1500 or 5.0%).
            target_profit_inr: Target profit in INR or percent (e.g. 2500 or 10.0%).
            max_lots: Max lots for options (strictly capped at 2 for retail safety).
            active_days: Days the strategy runs, e.g. ['MON', 'TUE', 'WED', 'THU', 'FRI'].
            when_time: Daily entry check time in HH:MM (default '09:16').
            auto_exit_time: Mandatory intraday square-off time in HH:MM (default '15:15').
            universe: Stock universe for scanner ('NIFTY500', 'NIFTY50', 'NIFTY100', 'FNO_STOCKS' or custom).
            timeframe: Candle timeframe for indicator evaluation ('1m', '5m', '15m', '1d').
            indicator_rules: Technical indicator conditions (e.g. RSI < 25 and Supertrend is Bullish).
            exit_rules: Exit conditions (e.g. 10% target, 5% stop loss, or RSI > 75).
            capital_per_trade_inr: Fixed capital allocated per triggered stock (e.g. 10000).
            max_concurrent_positions: Max simultaneous open stock positions (default 5).
            product_type: 'CNC' (Cash Delivery) or 'MIS' (Intraday).
            entry_description: Plain-language summary of entry logic.

        Returns:
            JSON summary confirming the creation of the strategy draft.
        """
        days = active_days or ["MON", "TUE", "WED", "THU", "FRI"]
        if strategy_category == "scanner" or indicator_rules is not None or "scanner" in name.lower():
            category = "scanner"
        else:
            category = "options"

        # Resolve user
        user_id = "admin"
        if self.api_key:
            try:
                resolved = get_username_by_apikey(self.api_key)
                if resolved:
                    user_id = resolved
            except Exception:
                pass

        if category == "scanner":
            # -------------------------------------------------------------
            # UNIVERSAL MULTI-STOCK SCANNER MODE (NIFTY 500 / RSI / SUPERTREND)
            # -------------------------------------------------------------
            clean_universe = (universe or "NIFTY500").strip().upper()
            symbols = resolve_universe_symbols(clean_universe)
            num_stocks = len(symbols)
            safe_max_pos = max(1, min(int(max_concurrent_positions), 10))
            safe_capital_per_trade = max(1000.0, float(capital_per_trade_inr))
            total_budget = safe_capital_per_trade * safe_max_pos

            # Format indicator rule description
            if isinstance(indicator_rules, dict):
                formatted_rules = []
                for k, v in indicator_rules.items():
                    k_lower = str(k).lower()
                    if isinstance(v, dict):
                        if k_lower == "rsi":
                            p = v.get("period", 14)
                            op = v.get("op", "<")
                            val = v.get("val", 25)
                            formatted_rules.append(f"RSI({p}) {op} {val}")
                        elif k_lower == "supertrend":
                            d = v.get("direction", "bullish").capitalize()
                            formatted_rules.append(f"Supertrend is {d}")
                        else:
                            formatted_rules.append(f"{k.upper()}: {v}")
                    else:
                        formatted_rules.append(f"{k.upper()}: {v}")
                rules_str = " AND ".join(formatted_rules)
            elif indicator_rules:
                rules_str = str(indicator_rules)
            else:
                rules_str = entry_description or "RSI(14) < 25 AND Supertrend(10,3) is Bullish"

            # Format exit rule description
            if isinstance(exit_rules, dict):
                exits_list = [
                    f"Target: +{exit_rules.get('target_pct', 10.0)}%",
                    f"Stop Loss: -{exit_rules.get('stop_loss_pct', 5.0)}%",
                ]
                if "rsi_exit" in exit_rules:
                    exits_list.append(f"Exit when RSI > {exit_rules['rsi_exit']}")
                if "supertrend_exit" in exit_rules:
                    exits_list.append("Exit when Supertrend turns Bearish")
            elif exit_rules:
                exits_list = [str(exit_rules)]
            else:
                exits_list = [
                    "Take profit at +10.0% per trade",
                    "Stop loss at -5.0% per trade",
                    "Mandatory exit when RSI > 75 or Supertrend turns Bearish",
                ]

            plain_language = {
                "when": f"Every {timeframe} candle close · 09:15 - 15:30 IST",
                "entry_gates": [
                    rules_str,
                    f"Active trading days: {', '.join(days)}",
                    f"Max concurrent positions: {safe_max_pos} stocks",
                ],
                "it_scans": f"Scans all {num_stocks} stocks in {clean_universe}. Buys {product_type} with ₹{safe_capital_per_trade:,.0f} per stock (Max budget: ₹{total_budget:,.0f}).",
                "how_it_exits": exits_list,
            }

            strategy_config = {
                "name": name,
                "strategy_kind": "scanner",
                "direction": "both",
                "universe_tab": "stocks_fno",
                "underlying": clean_universe,
                "underlying_exchange": "NSE",
                "strategy_type": "scanner",
                "product": product_type,
                "pricetype": "MARKET",
                "legs": [],
                "overall_sl_mtm": float(safe_capital_per_trade * 0.05 * safe_max_pos),
                "overall_target_mtm": float(safe_capital_per_trade * 0.10 * safe_max_pos),
                "daily_loss_limit_inr": float(safe_capital_per_trade * 0.10 * safe_max_pos),
                "scheduler": {
                    "active_days": days,
                    "entry_time": when_time,
                    "exit_time": auto_exit_time,
                    "agent_metadata": {
                        "category": "scanner",
                        "strategy_category": "scanner",
                        "universe": clean_universe,
                        "timeframe": timeframe,
                        "num_stocks": num_stocks,
                        "indicator_rules": indicator_rules or {"rsi": "<25", "supertrend": "bullish"},
                        "exit_rules": exit_rules or {"target_pct": 10.0, "stop_loss_pct": 5.0, "rsi_exit": 75.0},
                        "capital_per_trade_inr": safe_capital_per_trade,
                        "max_concurrent_positions": safe_max_pos,
                        "product_type": product_type,
                        "plain_language": plain_language,
                    },
                },
            }

            summary_text = f"{clean_universe} Scanner ({num_stocks} stocks) | {rules_str} | Target: +10% | SL: -5%"

        else:
            # -------------------------------------------------------------
            # SINGLE-INDEX DERIVATIVES OPTIONS MODE (NIFTY / BANKNIFTY)
            # -------------------------------------------------------------
            safe_lots = max(1, min(int(max_lots), 2))
            safe_sl = min(float(stop_loss_inr), max(500.0, float(capital_inr) * 0.10))
            clean_underlying = underlying.upper().strip()
            exchange = "NSE_INDEX" if clean_underlying in ("NIFTY", "BANKNIFTY", "FINNIFTY") else "BSE_INDEX"

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
                        "strategy_category": "options",
                        "capital_inr": capital_inr,
                        "max_lots": safe_lots,
                        "plain_language": plain_language,
                    },
                },
            }

            summary_text = f"{clean_underlying} current_weekly | {safe_lots} lot | SL: ₹{safe_sl:,.0f} | Target: ₹{target_profit_inr:,.0f}"

        # Save to database
        payload, err = sm_store.create_strategy(user_id, strategy_config)
        if err and "already exists" in err:
            ts = datetime.datetime.now().strftime("%H%M%S")
            strategy_config["name"] = f"{name} ({ts})"
            payload, err = sm_store.create_strategy(user_id, strategy_config)

        strategy_id = payload["id"] if payload else 1

        # Emit draft frame via viz_sink side-channel
        sink = sink_of(self.context)
        draft_spec = {
            "strategy_id": strategy_id,
            "name": strategy_config["name"],
            "strategy_category": category,
            "underlying": strategy_config["underlying"],
            "strategy_type": strategy_type,
            "capital_inr": total_budget if category == "scanner" else capital_inr,
            "stop_loss_inr": strategy_config["overall_sl_mtm"],
            "target_profit_inr": strategy_config["overall_target_mtm"],
            "max_lots": 1 if category == "scanner" else safe_lots,
            "account": "AC Agarwal (DM933)",
            "summary": summary_text,
            "plain_language": plain_language,
        }

        if category == "scanner":
            draft_spec["universe"] = clean_universe
            draft_spec["capital_per_trade_inr"] = safe_capital_per_trade
            draft_spec["max_concurrent_positions"] = safe_max_pos

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
            "category": category,
            "summary": summary_text,
            "rendered_card": emitted,
            "plain_language": plain_language,
        }
        return wrap_tool_result("build_autonomous_agent", result)
