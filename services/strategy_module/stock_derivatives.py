"""Stock Derivatives Resolution Engine (F&O Options & Futures).

Resolves single-stock options (ATM/OTM/ITM Call/Put) and futures contracts
for NSE F&O equities with:
1. Dynamic ATM strike calculation based on stock LTP and strike interval.
2. Next-Month Rollover Shield: Automatically rolls to next monthly expiry if within
   4 days of monthly expiry to prevent NSE physical settlement risk.
3. Master contracts lookup with offline fallback for top F&O symbols.
"""

from __future__ import annotations

import calendar
import datetime
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Curated standard NSE F&O stock lot sizes & typical strike intervals
# Verified for major liquid F&O stocks
FNO_STOCK_SPECS: dict[str, dict[str, Any]] = {
    "RELIANCE": {"lot_size": 250, "strike_step": 20.0, "tick_size": 0.05},
    "TCS": {"lot_size": 175, "strike_step": 20.0, "tick_size": 0.05},
    "INFY": {"lot_size": 400, "strike_step": 20.0, "tick_size": 0.05},
    "HDFCBANK": {"lot_size": 550, "strike_step": 10.0, "tick_size": 0.05},
    "ICICIBANK": {"lot_size": 700, "strike_step": 10.0, "tick_size": 0.05},
    "SBIN": {"lot_size": 1500, "strike_step": 5.0, "tick_size": 0.05},
    "TATAMOTORS": {"lot_size": 550, "strike_step": 10.0, "tick_size": 0.05},
    "TATASTEEL": {"lot_size": 5500, "strike_step": 1.0, "tick_size": 0.05},
    "MARUTI": {"lot_size": 50, "strike_step": 100.0, "tick_size": 0.05},
    "BAJFINANCE": {"lot_size": 125, "strike_step": 50.0, "tick_size": 0.05},
    "BAJAJFINSV": {"lot_size": 500, "strike_step": 10.0, "tick_size": 0.05},
    "AXISBANK": {"lot_size": 625, "strike_step": 10.0, "tick_size": 0.05},
    "KOTAKBANK": {"lot_size": 400, "strike_step": 10.0, "tick_size": 0.05},
    "LT": {"lot_size": 150, "strike_step": 20.0, "tick_size": 0.05},
    "ITC": {"lot_size": 1600, "strike_step": 5.0, "tick_size": 0.05},
    "WIPRO": {"lot_size": 1500, "strike_step": 5.0, "tick_size": 0.05},
    "HINDALCO": {"lot_size": 1400, "strike_step": 5.0, "tick_size": 0.05},
    "COALINDIA": {"lot_size": 2100, "strike_step": 5.0, "tick_size": 0.05},
    "NTPC": {"lot_size": 1500, "strike_step": 5.0, "tick_size": 0.05},
    "ONGC": {"lot_size": 3850, "strike_step": 2.5, "tick_size": 0.05},
    "POWERGRID": {"lot_size": 1800, "strike_step": 5.0, "tick_size": 0.05},
    "SUNPHARMA": {"lot_size": 350, "strike_step": 10.0, "tick_size": 0.05},
    "TITAN": {"lot_size": 175, "strike_step": 20.0, "tick_size": 0.05},
    "ULTRACEMCO": {"lot_size": 50, "strike_step": 100.0, "tick_size": 0.05},
    "ADANIENT": {"lot_size": 300, "strike_step": 20.0, "tick_size": 0.05},
    "ADANIPORTS": {"lot_size": 400, "strike_step": 20.0, "tick_size": 0.05},
    "BHARTIARTL": {"lot_size": 475, "strike_step": 10.0, "tick_size": 0.05},
    "HEROMOTOCO": {"lot_size": 150, "strike_step": 50.0, "tick_size": 0.05},
    "EICHERMOT": {"lot_size": 175, "strike_step": 50.0, "tick_size": 0.05},
    "DRREDDY": {"lot_size": 125, "strike_step": 50.0, "tick_size": 0.05},
    "CIPLA": {"lot_size": 650, "strike_step": 10.0, "tick_size": 0.05},
    "TECHM": {"lot_size": 600, "strike_step": 10.0, "tick_size": 0.05},
    "HCLTECH": {"lot_size": 350, "strike_step": 10.0, "tick_size": 0.05},
    "BPCL": {"lot_size": 1800, "strike_step": 5.0, "tick_size": 0.05},
    "BEL": {"lot_size": 2850, "strike_step": 2.5, "tick_size": 0.05},
    "DLF": {"lot_size": 825, "strike_step": 10.0, "tick_size": 0.05},
    "INDIGO": {"lot_size": 150, "strike_step": 50.0, "tick_size": 0.05},
    "IDEA": {"lot_size": 80000, "strike_step": 0.5, "tick_size": 0.05},
    "ZOMATO": {"lot_size": 2000, "strike_step": 5.0, "tick_size": 0.05},
}


@dataclass
class ResolvedStockOption:
    ok: bool
    symbol: str
    underlying: str
    underlying_ltp: float
    strike: float
    option_type: str  # 'CE' | 'PE'
    expiry: str  # e.g. '24-SEP-26'
    expiry_symbol: str  # e.g. '26SEP' or '24SEP26'
    lot_size: int
    lots: int
    quantity: int
    tick_size: float
    estimated_premium: float
    total_capital_required: float
    rolled_over: bool
    error: str | None = None


@dataclass
class ResolvedStockFuture:
    ok: bool
    symbol: str
    underlying: str
    underlying_ltp: float
    expiry: str
    expiry_symbol: str
    lot_size: int
    lots: int
    quantity: int
    tick_size: float
    estimated_margin_required: float
    rolled_over: bool
    error: str | None = None


def get_last_thursday(year: int, month: int) -> date:
    """Calculate the last Thursday date of the given month and year."""
    num_days = calendar.monthrange(year, month)[1]
    last_day = date(year, month, num_days)
    offset = (last_day.weekday() - 3) % 7
    return last_day - timedelta(days=offset)


def resolve_monthly_expiry(
    as_of: date | None = None,
    buffer_days: int = 4,
) -> tuple[date, str, str, bool]:
    """Resolve the active monthly expiry for stock derivatives.

    Implements Next-Month Rollover Shield:
    If current date is within `buffer_days` (default 4 days) of current month's
    last Thursday, automatically rolls to the next month to avoid mandatory NSE
    physical delivery settlement risk.

    Returns:
        tuple of (expiry_date, formatted_expiry_str, symbol_expiry_str, rolled_over)
    """
    today = as_of or date.today()
    this_month_thursday = get_last_thursday(today.year, today.month)

    days_until_expiry = (this_month_thursday - today).days

    if days_until_expiry < buffer_days:
        # Roll over to next month
        rolled_over = True
        next_year = today.year + (1 if today.month == 12 else 0)
        next_month = 1 if today.month == 12 else today.month + 1
        target_expiry = get_last_thursday(next_year, next_month)
    else:
        rolled_over = False
        target_expiry = this_month_thursday

    formatted_str = target_expiry.strftime("%d-%b-%y").upper()
    symbol_str = target_expiry.strftime("%d%b%y").upper()
    return target_expiry, formatted_str, symbol_str, rolled_over


def get_stock_specs(symbol: str, ltp: float = 1000.0) -> dict[str, Any]:
    """Return lot size and strike step for an NSE F&O stock, with dynamic fallback."""
    clean = symbol.upper().strip()
    if clean in FNO_STOCK_SPECS:
        return FNO_STOCK_SPECS[clean]

    # Dynamic heuristic for F&O stocks not explicitly hardcoded
    # Standard contract value on NSE F&O is approximately 7.5 - 10 Lakhs
    if ltp <= 0:
        ltp = 500.0

    target_contract_value = 850000.0
    approx_lot = max(25, int(target_contract_value / ltp))
    # Round lot to nearest 25 or 50
    lot_size = round(approx_lot / 25) * 25 if approx_lot > 50 else max(10, approx_lot)

    if ltp < 50:
        strike_step = 1.0
    elif ltp < 150:
        strike_step = 2.5
    elif ltp < 500:
        strike_step = 5.0
    elif ltp < 1500:
        strike_step = 10.0
    elif ltp < 3000:
        strike_step = 20.0
    elif ltp < 6000:
        strike_step = 50.0
    else:
        strike_step = 100.0

    return {"lot_size": lot_size, "strike_step": strike_step, "tick_size": 0.05}


def snap_to_strike(ltp: float, strike_step: float, mode: str = "atm") -> float:
    """Snap a stock LTP to ATM, OTM1, or ITM1 strike based on step."""
    atm = round(ltp / strike_step) * strike_step
    mode_clean = mode.lower().strip()

    if mode_clean == "otm1":
        return round(atm + strike_step, 2)
    elif mode_clean == "itm1":
        return round(atm - strike_step, 2)
    elif mode_clean == "otm2":
        return round(atm + (2 * strike_step), 2)
    elif mode_clean == "itm2":
        return round(atm - (2 * strike_step), 2)
    return round(atm, 2)


def resolve_stock_option(
    symbol: str,
    ltp: float,
    option_type: str = "CE",
    strike_mode: str = "atm",
    lots: int = 1,
    as_of: date | None = None,
) -> ResolvedStockOption:
    """Resolve a single-stock option contract.

    Args:
        symbol: NSE stock symbol (e.g. 'TATAMOTORS', 'RELIANCE').
        ltp: Current market price of the underlying equity.
        option_type: 'CE' (Call) or 'PE' (Put).
        strike_mode: 'atm', 'otm1', 'itm1'.
        lots: Number of derivative lots.
        as_of: Optional evaluation date for testing or backtesting.
    """
    clean_sym = symbol.upper().strip()
    clean_opt = option_type.upper().strip()
    if clean_opt not in ("CE", "PE"):
        clean_opt = "CE"

    specs = get_stock_specs(clean_sym, ltp)
    lot_size = specs["lot_size"]
    strike_step = specs["strike_step"]
    tick_size = specs["tick_size"]

    # Calculate strike
    strike = snap_to_strike(ltp, strike_step, mode=strike_mode)

    # Expiry with Next-Month Rollover Shield
    exp_date, formatted_exp, symbol_exp, rolled_over = resolve_monthly_expiry(as_of)

    # Strike formatting: format integer if no decimals
    strike_str = f"{int(strike)}" if strike.is_integer() else f"{strike}"
    contract_symbol = f"{clean_sym}{symbol_exp}{strike_str}{clean_opt}"

    # Estimate premium: ATM premium is roughly 2.0% - 3.5% of stock price
    moneyness_diff = (ltp - strike) if clean_opt == "CE" else (strike - ltp)
    intrinsic = max(0.0, moneyness_diff)
    time_value = max(1.5, ltp * 0.025)
    est_premium = round(max(tick_size, intrinsic + time_value), 2)

    total_qty = lots * lot_size
    total_capital = round(total_qty * est_premium, 2)

    return ResolvedStockOption(
        ok=True,
        symbol=contract_symbol,
        underlying=clean_sym,
        underlying_ltp=ltp,
        strike=strike,
        option_type=clean_opt,
        expiry=formatted_exp,
        expiry_symbol=symbol_exp,
        lot_size=lot_size,
        lots=lots,
        quantity=total_qty,
        tick_size=tick_size,
        estimated_premium=est_premium,
        total_capital_required=total_capital,
        rolled_over=rolled_over,
    )


def resolve_stock_future(
    symbol: str,
    ltp: float,
    lots: int = 1,
    as_of: date | None = None,
) -> ResolvedStockFuture:
    """Resolve a single-stock futures contract."""
    clean_sym = symbol.upper().strip()
    specs = get_stock_specs(clean_sym, ltp)
    lot_size = specs["lot_size"]
    tick_size = specs["tick_size"]

    exp_date, formatted_exp, symbol_exp, rolled_over = resolve_monthly_expiry(as_of)
    contract_symbol = f"{clean_sym}{symbol_exp}FUT"

    total_qty = lots * lot_size
    # Margin on stock futures in India is ~20% of contract value
    est_margin = round(total_qty * ltp * 0.20, 2)

    return ResolvedStockFuture(
        ok=True,
        symbol=contract_symbol,
        underlying=clean_sym,
        underlying_ltp=ltp,
        expiry=formatted_exp,
        expiry_symbol=symbol_exp,
        lot_size=lot_size,
        lots=lots,
        quantity=total_qty,
        tick_size=tick_size,
        estimated_margin_required=est_margin,
        rolled_over=rolled_over,
    )
