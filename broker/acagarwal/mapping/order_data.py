"""Order, trade, position, and holdings data mapping for AC Agarwal XTS."""

from database.token_db import get_symbol
from utils.logging import get_logger

logger = get_logger(__name__)

EXCHANGE_MAPPING = {
    "NSECM": "NSE",
    "BSECM": "BSE",
    "NSEFO": "NFO",
    "BSEFO": "BFO",
    "MCXFO": "MCX",
    "NSECD": "CDS",
}


def map_order_data(order_data):
    """
    Processes and modifies order list from Symphony XTS.
    """
    if "result" not in order_data or not order_data["result"]:
        return []

    orders = order_data["result"]
    if isinstance(orders, list):
        for order in orders:
            symboltoken = order.get("ExchangeInstrumentID")
            exch = order.get("ExchangeSegment", "")
            exchange = EXCHANGE_MAPPING.get(exch, exch)

            symbol_from_db = get_symbol(symboltoken, exchange)
            if symbol_from_db:
                order["TradingSymbol"] = symbol_from_db

    return orders


def calculate_order_statistics(order_data):
    """
    Calculates order counts from order data.
    """
    total_buy_orders = total_sell_orders = 0
    total_completed_orders = total_open_orders = total_rejected_orders = 0

    if order_data:
        for order in order_data:
            if order.get("OrderSide") == "BUY":
                total_buy_orders += 1
            elif order.get("OrderSide") == "SELL":
                total_sell_orders += 1

            status = order.get("OrderStatus")
            if status == "Filled":
                total_completed_orders += 1
            elif status in ("New", "Open", "Pending"):
                total_open_orders += 1
            elif status in ("Rejected", "Cancelled", "Canceled"):
                total_rejected_orders += 1

    return {
        "total_buy_orders": total_buy_orders,
        "total_sell_orders": total_sell_orders,
        "total_completed_orders": total_completed_orders,
        "total_open_orders": total_open_orders,
        "total_rejected_orders": total_rejected_orders,
    }


def transform_order_data(orders):
    """
    Transforms XTS orders to OpenAlgo standardized format.
    """
    if isinstance(orders, dict):
        orders = [orders]

    order_type_mapping = {
        "Limit": "LIMIT",
        "Market": "MARKET",
        "StopLimit": "SL",
        "StopMarket": "SL-M",
        "LIMIT": "LIMIT",
        "MARKET": "MARKET",
    }
    order_status_mapping = {
        "Filled": "complete",
        "Rejected": "rejected",
        "Cancelled": "cancelled",
        "Canceled": "cancelled",
        "New": "open",
        "Open": "open",
        "Pending": "open",
    }

    transformed_orders = []
    for order in orders:
        if not isinstance(order, dict):
            continue

        exchange = order.get("ExchangeSegment", "")
        mapped_exchange = EXCHANGE_MAPPING.get(exchange, exchange)

        order_type = order.get("OrderType", "")
        mapped_order_type = order_type_mapping.get(order_type, order_type)

        order_status = order.get("OrderStatus", "")
        mapped_order_status = order_status_mapping.get(order_status, order_status.lower() if order_status else "unknown")

        app_order_id = str(order.get("AppOrderID") or order.get("appOrderID") or "0")

        transformed_order = {
            "symbol": order.get("TradingSymbol", ""),
            "exchange": mapped_exchange,
            "action": order.get("OrderSide", ""),
            "quantity": int(order.get("OrderQuantity", 0)),
            "price": float(order.get("OrderPrice", 0.0) or order.get("Price", 0.0) or 0.0),
            "trigger_price": float(order.get("OrderStopPrice", 0.0) or order.get("StopPrice", 0.0) or 0.0),
            "pricetype": mapped_order_type,
            "product": order.get("ProductType", ""),
            "orderid": app_order_id,
            "order_status": mapped_order_status,
            "status": mapped_order_status,
            "timestamp": str(order.get("LastUpdateDateTime", "") or order.get("OrderGeneratedDateTime", "")),
        }
        transformed_orders.append(transformed_order)

    return transformed_orders


def map_trade_data(trade_data):
    """
    Maps trading symbols in executed trades.
    """
    if "result" not in trade_data or not trade_data["result"]:
        return []

    trades = trade_data["result"]
    if isinstance(trades, list):
        for trade in trades:
            symboltoken = trade.get("ExchangeInstrumentID")
            exch = trade.get("ExchangeSegment", "")
            exchange = EXCHANGE_MAPPING.get(exch, exch)

            symbol_from_db = get_symbol(symboltoken, exchange)
            if symbol_from_db:
                trade["TradingSymbol"] = symbol_from_db

    return trades


def transform_tradebook_data(tradebook_data):
    """
    Transforms trade executions to OpenAlgo standardized format.
    """
    transformed_data = []
    for trade in tradebook_data:
        if not isinstance(trade, dict):
            continue

        exchange = trade.get("ExchangeSegment", "")
        mapped_exchange = EXCHANGE_MAPPING.get(exchange, exchange)

        quantity = int(trade.get("OrderQuantity", 0) or trade.get("TradedQuantity", 0) or trade.get("Quantity", 0))
        average_price = float(trade.get("OrderAverageTradedPrice", 0.0) or trade.get("TradePrice", 0.0) or 0.0)

        app_order_id = str(trade.get("AppOrderID") or trade.get("appOrderID") or "0")

        transformed_trade = {
            "symbol": trade.get("TradingSymbol", ""),
            "exchange": mapped_exchange,
            "product": trade.get("ProductType", ""),
            "action": trade.get("OrderSide", ""),
            "quantity": quantity,
            "average_price": average_price,
            "trade_value": quantity * average_price,
            "orderid": app_order_id,
            "timestamp": str(trade.get("OrderGeneratedDateTime", "") or trade.get("TradeExecutionTime", "")),
        }
        transformed_data.append(transformed_trade)
    return transformed_data


def map_position_data(position_data):
    """
    Extracts position data from XTS response.
    """
    if not position_data or "result" not in position_data or not position_data["result"]:
        return []

    return position_data["result"]


def transform_positions_data(positions_data):
    """
    Transforms position list into OpenAlgo standard format.
    """
    if isinstance(positions_data, dict):
        positions_list = positions_data.get("positionList", [])
    elif isinstance(positions_data, list):
        positions_list = positions_data
    else:
        return []

    transformed_data = []
    for position in positions_list:
        if not isinstance(position, dict):
            continue

        symboltoken = position.get("ExchangeInstrumentID", position.get("ExchangeInstrumentId"))
        exchange = position.get("ExchangeSegment", "")
        mapped_exchange = EXCHANGE_MAPPING.get(exchange, exchange)

        symbol_from_db = get_symbol(symboltoken, mapped_exchange)
        trading_symbol = symbol_from_db or position.get("TradingSymbol", "")

        netqty = float(position.get("Quantity", 0))
        if netqty > 0:
            avg_price = float(position.get("BuyAveragePrice", 0) or position.get("ActualBuyAveragePrice", 0) or 0)
        elif netqty < 0:
            avg_price = float(position.get("SellAveragePrice", 0) or position.get("ActualSellAveragePrice", 0) or 0)
        else:
            avg_price = float(position.get("BuyAveragePrice", 0) or 0)

        transformed_position = {
            "symbol": trading_symbol,
            "exchange": mapped_exchange,
            "product": position.get("ProductType", ""),
            "quantity": int(netqty),
            "average_price": f"{avg_price:.2f}",
            "ltp": float(position.get("LastTradedPrice", 0.0) or position.get("ltp", 0.0) or 0.0),
            "pnl": float(position.get("MTM", 0.0) or position.get("pnl", 0.0) or 0.0),
        }
        transformed_data.append(transformed_position)

    return transformed_data


def map_portfolio_data(portfolio_data):
    """
    Maps holdings from Symphony XTS portfolio response.
    """
    if not portfolio_data or portfolio_data.get("type") != "success" or "result" not in portfolio_data:
        return {"holdings": [], "totalholding": None}

    result = portfolio_data["result"]
    rms_holdings = result.get("RMSHoldings", {}) if isinstance(result, dict) else {}
    holdings_dict = rms_holdings.get("Holdings", {}) if isinstance(rms_holdings, dict) else {}

    holdings_list = []
    total_holding_value = 0.0
    total_inv_value = 0.0
    total_pnl = 0.0

    for isin, holding in holdings_dict.items():
        nse_instrument_id = holding.get("ExchangeNSEInstrumentId")
        exchange = "NSE"
        trading_symbol = get_symbol(nse_instrument_id, exchange) or isin

        quantity = int(holding.get("HoldingQuantity", 0))
        buy_avg_price = float(holding.get("BuyAvgPrice", 0) or 0.0)
        inv_value = quantity * buy_avg_price

        entry = {
            "tradingsymbol": trading_symbol,
            "exchange": exchange,
            "quantity": quantity,
            "product": "CNC",
            "buy_price": buy_avg_price,
            "investment_value": inv_value,
            "current_value": inv_value,
            "profitandloss": 0.0,
            "pnlpercentage": 0.0,
        }
        holdings_list.append(entry)
        total_inv_value += inv_value
        total_holding_value += inv_value

    totalholding = {
        "totalholdingvalue": total_holding_value,
        "totalinvvalue": total_inv_value,
        "totalprofitandloss": total_pnl,
        "totalpnlpercentage": 0.0 if total_inv_value == 0 else (total_pnl / total_inv_value) * 100,
    }

    return {"holdings": holdings_list, "totalholding": totalholding}


def transform_holdings_data(holdings_data):
    """
    Transforms holdings into OpenAlgo standard list.
    """
    if not holdings_data or "holdings" not in holdings_data:
        return []

    transformed = []
    for h in holdings_data["holdings"]:
        transformed.append({
            "symbol": h.get("tradingsymbol", ""),
            "exchange": h.get("exchange", ""),
            "quantity": h.get("quantity", 0),
            "product": h.get("product", ""),
            "pnl": h.get("profitandloss", 0.0),
            "pnlpercent": h.get("pnlpercentage", 0.0),
        })
    return transformed


def calculate_portfolio_statistics(holdings_data):
    """
    Calculates portfolio summary statistics.
    """
    if not holdings_data or "totalholding" not in holdings_data or holdings_data["totalholding"] is None:
        return {
            "totalholdingvalue": 0,
            "totalinvvalue": 0,
            "totalprofitandloss": 0,
            "totalpnlpercentage": 0,
        }

    th = holdings_data["totalholding"]
    return {
        "totalholdingvalue": th.get("totalholdingvalue", 0),
        "totalinvvalue": th.get("totalinvvalue", 0),
        "totalprofitandloss": th.get("totalprofitandloss", 0),
        "totalpnlpercentage": th.get("totalpnlpercentage", 0),
    }
