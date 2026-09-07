"""Universe & Basket Resolution Engine for OpenAlgo.

Resolves constituent equity stock symbols for standard market indices
(NIFTY 50, NIFTY 100, NIFTY 500, F&O Stocks) and custom user watchlists.
"""

from __future__ import annotations

import logging
from typing import Sequence

logger = logging.getLogger(__name__)

# Standard NIFTY 50 components (NSE Equity symbols)
NIFTY_50_SYMBOLS = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BPCL",
    "BHARTIARTL", "BRITANNIA", "CIPLA", "COALINDIA", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK",
    "INFY", "ITC", "JSWSTEEL", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SHRIRAMFIN", "SBIN",
    "SUNPHARMA", "TCS", "TATACONSUM", "TATAMOTORS", "TATASTEEL",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO"
]

# Standard NIFTY Next 50 components
NIFTY_NEXT_50_SYMBOLS = [
    "ABB", "ADANIENSOL", "ADANIGREEN", "ADANIPOWER", "ATGL",
    "AMBUJACEM", "BANKBARODA", "BOSCHLTD", "CANBK", "CHOLAFIN",
    "COLPAL", "DLF", "DABUR", "DIVISLAB", "GAIL",
    "GODREJCP", "HAL", "HAVELLS", "ICICIGI", "ICICIPRULI",
    "IOC", "IRCTC", "IRFC", "JINDALSTEL", "JIOFIN",
    "LICI", "LTIM", "MOTHERSON", "NAUKRI", "NHPC",
    "PIDILITIND", "PFC", "PNB", "RECLTD", "RVNL",
    "SIEMENS", "SRF", "SHREECEM", "SOLARINDS", "TVSMOTOR",
    "TATAPOWER", "TORNTPOWER", "UNITDSPR", "VBL", "VEDL",
    "ZYDUSLIFE", "MAXHEALTH", "BAJAJHLDNG", "CUMMINSIND", "PERSISTENT"
]

# Combined NIFTY 100
NIFTY_100_SYMBOLS = sorted(list(set(NIFTY_50_SYMBOLS + NIFTY_NEXT_50_SYMBOLS)))

# Curated liquid F&O stocks
FNO_STOCKS_SYMBOLS = sorted(list(set(NIFTY_100_SYMBOLS + [
    "AARTIIND", "ABCAPITAL", "ABFRL", "ACC", "ALKEM", "ASTRAL",
    "AUROPHARMA", "BALKRISIND", "BANDHANBNK", "BATAINDIA", "BHARATFORG",
    "BHEL", "BIOCON", "BSOFT", "CANFINHOME", "CHAMBLFERT", "COFORGE",
    "CONCOR", "COROMANDEL", "CROMPTON", "DEEPAKNTR", "DIXON", "ESCORTS",
    "EXIDEIND", "FEDERALBNK", "GLENMARK", "GMRINFRA", "GNFC", "GRANULES",
    "GUJGASLTD", "HINDPETRO", "IBULHSGFIN", "IDFCFIRSTB", "IEX", "INDHOTEL",
    "INDIAMART", "INDIGO", "IPCALAB", "JINDALSTEL", "JUBLFOOD", "L&TFH",
    "LALPATHLAB", "LICHSGFIN", "LTTS", "LUPIN", "M&MFIN", "MANAPPURAM",
    "MARICO", "MCDOWELL-N", "MCX", "METROPOLIS", "MFSL", "MGL", "MPHASIS",
    "MUTHOOTFIN", "NATIONALUM", "NAVINFLUOR", "OBEROIRLTY", "OFSS", "PAGEIND",
    "PEL", "PETRONET", "POLYCAB", "PVRINOX", "RAMCOCEM", "RBLBANK",
    "SAIL", "SYNGENE", "TATACHEM", "TATACOMM", "TATAPOWER", "TOWERS",
    "VOLTAS", "ZEEL"
])))

# Full NIFTY 500 symbols mapping (Standard Top liquid NSE equities)
NIFTY_500_SYMBOLS = sorted(list(set(FNO_STOCKS_SYMBOLS + [
    "360ONE", "3MINDIA", "AAVAS", "ACE", "ACTIONCONST", "AETHER",
    "AFFLE", "AJANTPHARM", "ALKYLAMINE", "ALLCARGO", "AMBER", "ANANDRATHI",
    "ANGELONE", "ANURAS", "APARINDS", "APLAPOLLO", "APTUS", "ARCHEAN",
    "ARE&M", "ASAHIINDIA", "ASTERDM", "ASTRAL", "ASTRAZEN", "ATUL",
    "AVANTIFEED", "AWL", "BALAMINES", "BALRAMCHIN", "BBL", "BDL",
    "BEML", "BERGEPAINT", "BLS", "BLUESTARCO", "BSE", "CAMPUS",
    "CASTROLIND", "CDSL", "CENTRALBK", "CENTURYTEX", "CEATLTD", "CESC",
    "CGPOWER", "CHALET", "CLEAN", "COCHINSHIP", "CRAFTSMAN", "CREDITACC",
    "CYIENT", "DATAPATTNS", "DEVYANI", "ECLERX", "ELGIEQUIP", "EMAMILTD",
    "ENDURANCE", "ENGINERSIN", "EQUITASBNK", "ERIS", "FACT", "FDC",
    "FINCABLES", "FINPIPE", "FIVESTAR", "FORTIS", "GLS", "GMMPFAUDLR",
    "GODFRYPHLP", "GODREJIND", "GODREJPROP", "GPIL", "GRINFRA", "GSFC",
    "GSPL", "HAPPSTMNDS", "HATHWAY", "HDFCAMC", "HEG", "HIKAL",
    "HINDCOPPER", "HOMEFIRST", "HONAUT", "HUDCO", "IDBI", "IDFC",
    "IIFL", "INDIACEM", "INDIANB", "INDIGOPNTS", "IOB", "IONEXCHANG",
    "JBCHEPHARM", "J&KBANK", "JBMA", "JCHAC", "JKCEMENT", "JKLAKSHMI",
    "JKPAPER", "JMFINANCIL", "JSL", "JUBLINGREA", "JUBLPHARMA", "JUSTDIAL",
    "JYOTHYLAB", "KAJARIACER", "KALYANKJIL", "KEC", "KEI", "KIMS",
    "KPITTECH", "KRBL", "KSB", "LATENTVIEW", "LAURUSLABS", "LEMONTREE",
    "LINDEINDIA", "LLOYDSME", "MAHABANK", "MAHLIFE", "MAHLOG", "MANINFRA",
    "MAPMYINDIA", "MASTEK", "MEDANTA", "METROBRAND", "MINDACORP", "MMTC",
    "MOTILALOFS", "MRF", "MRPL", "MSTCLTD", "MTARTECH", "NATCOPHARM",
    "NBCC", "NCC", "NETWORK18", "NH", "NLCINDIA", "NMDC", "NOCIL",
    "NUVAMA", "NYKAA", "OIL", "OLECTRA", "PAYTM", "PNCINFRA", "POLICYBZR",
    "POONAWALLA", "PPLPHARMA", "PRESTIGE", "PRINCEPIPE", "PRUDENT", "RBA",
    "RADICO", "RAIN", "RAJESHEXPO", "RALLIS", "RATNAMANI", "RAYMOND",
    "RCF", "REDINGTON", "RITES", "ROUTE", "RPOWER", "RTNINDIA", "SANOFI",
    "SAPPHIRE", "SCHAEFFLER", "SFL", "SHOPERSTOP", "SHYAMMETL", "SOBHA",
    "SONACOMS", "STARHEALTH", "SUNDARMFIN", "SUNDRMFAST", "SUNTECK", "SUNTV",
    "SUPRAJIT", "SUZLON", "SWANENERGY", "SYMPHONY", "TANLA", "TATAELXSI",
    "TATAINVEST", "TATATECH", "TEJASNET", "THERMAX", "TIMKEN", "TRIDENT",
    "TRITURBINE", "TTKPRESTIG", "UBL", "UCOBANK", "UNIONBANK", "UNOMINDA",
    "USHAMART", "UTIAMC", "VAIBHAVGBL", "VGUARD", "VIJAYA", "VINATIORGA",
    "VIPIND", "VRLLOG", "WELCORP", "WELSPUNLIV", "WESTLIFE", "WHIRLPOOL",
    "ZENSARTECH", "ZOMATO"
])))


def resolve_universe_symbols(universe: str, limit: int | None = None) -> list[str]:
    """Resolve a universe identifier into a list of tradable NSE equity symbols.

    Args:
        universe: The universe name ('NIFTY50', 'NIFTY100', 'NIFTY500', 'FNO_STOCKS',
                  or a comma-separated list of symbols like 'RELIANCE, TCS, INFY').
        limit: Optional maximum number of symbols to return.

    Returns:
        List of uppercase, trimmed NSE equity symbols.
    """
    cleaned = (universe or "").strip().upper()
    
    if cleaned in ("NIFTY50", "NIFTY_50", "NIFTY 50"):
        symbols = list(NIFTY_50_SYMBOLS)
    elif cleaned in ("NIFTY100", "NIFTY_100", "NIFTY 100"):
        symbols = list(NIFTY_100_SYMBOLS)
    elif cleaned in ("NIFTY500", "NIFTY_500", "NIFTY 500"):
        symbols = list(NIFTY_500_SYMBOLS)
    elif cleaned in ("FNO", "FNO_STOCKS", "FNOSTOCKS", "F&O", "F&O STOCKS"):
        symbols = list(FNO_STOCKS_SYMBOLS)
    else:
        # Custom comma-separated list or single symbol
        parts = [p.strip().upper() for p in cleaned.replace(";", ",").split(",") if p.strip()]
        symbols = parts if parts else list(NIFTY_50_SYMBOLS)

    if limit and limit > 0:
        return symbols[:limit]
    return symbols


def get_supported_universes() -> list[dict[str, str | int]]:
    """Return catalog of standard universes with display names and symbol counts."""
    return [
        {"id": "NIFTY50", "name": "NIFTY 50", "description": "Top 50 large-cap blue chips on NSE", "count": len(NIFTY_50_SYMBOLS)},
        {"id": "NIFTY100", "name": "NIFTY 100", "description": "Top 100 liquid equities on NSE", "count": len(NIFTY_100_SYMBOLS)},
        {"id": "NIFTY500", "name": "NIFTY 500", "description": "Broad market index of 500 NSE companies", "count": len(NIFTY_500_SYMBOLS)},
        {"id": "FNO_STOCKS", "name": "F&O Liquid Stocks", "description": "~180 derivatives-eligible NSE stocks", "count": len(FNO_STOCKS_SYMBOLS)},
    ]
