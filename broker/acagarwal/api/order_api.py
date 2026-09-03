"""AC Agarwal Symphony XTS Order API."""

import json
import os
import threading
import time

from broker.acagarwal.baseurl import INTERACTIVE_URL
from broker.acagarwal.mapping.transform_data import (
    map_exchange,
    map_product_type,
    reverse_map_product_type,
    transform_data,
    transform_modify_order_data,
)
from database.auth_db import get_auth_token
from database.token_db import get_br_symbol, get_symbol, get_token
from utils.httpx_client import get_httpx_client
from utils.logging import get_logger

logger = get_logger(__name__)


def get_api_response(endpoint, auth, method="GET", payload=""):
    """
    Execute authenticated request to AC Agarwal Symphony XTS Interactive API.
    """
    AUTH_TOKEN = auth
    client = get_httpx_client()

    headers = {
        "authorization": AUTH_TOKEN,
        "Content-Type": "application/json",
    }
    url = f"{INTERACTIVE_URL}{endpoint}"

    if method == "GET":
        response = client.get(url, headers=headers)
    elif method == "POST":
        response = client.post(url, headers=headers, json=payload if payload else {})
    elif method == "PUT":
        response = client.put(url, headers=headers, json=payload if payload else {})
    elif method == "DELETE":
        response = client.delete(url, headers=headers)
    else:
        response = client.request(method, url, headers=headers, json=payload if payload else {})

    response.status = response.status_code
    logger.debug(f"AC Agarwal API Response [{endpoint}] Status: {response.status_code}")
    return response.json()


def get_order_book(auth):
    """Fetch daily orders from XTS."""
    return get_api_response("/orders", auth)


def get_trade_book(auth):
    """Fetch daily executed trades from XTS."""
    return get_api_response("/orders/trades", auth)


def get_positions(auth):
    """Fetch net positions from XTS."""
    return get_api_response("/portfolio/positions?dayOrNet=NetWise", auth)


def get_holdings(auth):
    """Fetch holdings portfolio from XTS."""
    return get_api_response("/portfolio/holdings", auth)


# --- Per-Symbol Smart Order Lock ---
_symbol_locks = {}
_symbol_locks_lock = threading.Lock()

# --- Position Book Cache ---
_position_cache = {}
_position_cache_lock = threading.Lock()
_POSITION_CACHE_TTL = 1.0


def _get_symbol_lock(symbol, exchange, product):
    """Get or create a per-symbol lock for serializing smart orders."""
    key = f"{symbol}:{exchange}:{product}"
    with _symbol_locks_lock:
        if key not in _symbol_locks:
            _symbol_locks[key] = threading.Lock()
        return _symbol_locks[key]


def _get_cached_positions(auth):
    """Get positions from cache if fresh, otherwise fetch from broker API."""
    with _position_cache_lock:
        now = time.monotonic()
        cached = _position_cache.get(auth)
        if cached and (now - cached["timestamp"]) < _POSITION_CACHE_TTL:
            return cached["data"]

    positions_data = get_positions(auth)
    with _position_cache_lock:
        _position_cache[auth] = {"data": positions_data, "timestamp": time.monotonic()}

    return positions_data


def _invalidate_position_cache(auth):
    """Invalidate the position cache so the next queued order fetches fresh data."""
    with _position_cache_lock:
        _position_cache.pop(auth, None)


def get_open_position(tradingsymbol, exchange, producttype, auth):
    """
    Find net open position for a given symbol, exchange, and product type.
    """
    tradingsymbol = get_br_symbol(tradingsymbol, exchange)
    positions_data = _get_cached_positions(auth)

    exchange_mapping = {
        "NSE": "NSECM",
        "BSE": "BSECM",
        "NFO": "NSEFO",
        "BFO": "BSEFO",
        "MCX": "MCXFO",
        "CDS": "NSECD",
    }
    xts_exchange = exchange_mapping.get(exchange, exchange)
    net_qty = "0"

    if positions_data and positions_data.get("type") == "success":
        result = positions_data.get("result", [])
        if isinstance(result, dict):
            position_list = result.get("positionList", [])
        elif isinstance(result, list):
            position_list = result
        else:
            position_list = []

        for position in position_list:
            pos_symbol = position.get("TradingSymbol", "")
            pos_exchange = position.get("ExchangeSegment", "")
            pos_product = position.get("ProductType", "")
            if (
                pos_symbol == tradingsymbol
                and pos_exchange == xts_exchange
                and pos_product == producttype
            ):
                net_qty = str(position.get("Quantity", 0))
                break

    return net_qty


def place_order_api(data, auth):
    """
    Place an order via AC Agarwal Symphony XTS API.
    """
    AUTH_TOKEN = auth
    if all(
        key in data
        for key in ["exchangeSegment", "exchangeInstrumentID", "productType", "orderType"]
    ):
        newdata = data
    else:
        token = get_token(data["symbol"], data["exchange"])
        newdata = transform_data(data, token)

    headers = {
        "authorization": AUTH_TOKEN,
        "Content-Type": "application/json",
    }
    client = get_httpx_client()
    response = client.post(f"{INTERACTIVE_URL}/orders", headers=headers, json=newdata)
    response.status = response.status_code

    try:
        response_data = response.json()
    except json.JSONDecodeError:
        response_data = {
            "error": "Invalid JSON response from server",
            "raw_response": response.text,
        }

    orderid = (
        response_data.get("result", {}).get("AppOrderID")
        if response_data.get("type") == "success"
        else None
    )

    return response, response_data, orderid


def place_smartorder_api(data, auth):
    """
    Place a position-aware smart order.
    """
    AUTH_TOKEN = auth
    res = None

    symbol = data.get("symbol")
    exchange = data.get("exchange")
    product = data.get("product")
    symbol_lock = _get_symbol_lock(symbol, exchange, product)

    with symbol_lock:
        position_size = int(data.get("position_size", "0"))
        current_position = int(
            get_open_position(symbol, exchange, map_product_type(product), AUTH_TOKEN)
        )

        action = None
        quantity = 0

        if position_size == 0 and current_position == 0 and int(data.get("quantity", 0)) != 0:
            action = data["action"]
            quantity = data["quantity"]
            res, response, orderid = place_order_api(data, AUTH_TOKEN)
            _invalidate_position_cache(AUTH_TOKEN)
            return res, response, orderid

        elif position_size == current_position:
            if int(data.get("quantity", 0)) == 0:
                response = {
                    "status": "success",
                    "message": "No OpenPosition Found. Not placing Exit order.",
                }
            else:
                response = {
                    "status": "success",
                    "message": "No action needed. Position size matches current position",
                }
            orderid = None
            return res, response, orderid

        if position_size == 0 and current_position > 0:
            action = "SELL"
            quantity = abs(current_position)
        elif position_size == 0 and current_position < 0:
            action = "BUY"
            quantity = abs(current_position)
        elif current_position == 0:
            action = "BUY" if position_size > 0 else "SELL"
            quantity = abs(position_size)
        else:
            if position_size > current_position:
                action = "BUY"
                quantity = position_size - current_position
            elif position_size < current_position:
                action = "SELL"
                quantity = current_position - position_size

        if action:
            order_data = data.copy()
            order_data["action"] = action
            order_data["quantity"] = str(quantity)

            res, response, orderid = place_order_api(order_data, auth)
            _invalidate_position_cache(AUTH_TOKEN)
            return res, response, orderid

        return res, {"status": "error", "message": "Could not determine smart order action"}, None


def close_all_positions(current_api_key, auth):
    """
    Square off all open positions.
    """
    AUTH_TOKEN = auth
    positions_response = get_positions(AUTH_TOKEN)

    if not positions_response or positions_response.get("type") != "success":
        return {"message": "No Open Positions Found"}, 200

    result = positions_response.get("result", [])
    if isinstance(result, dict):
        positions_list = result.get("positionList", [])
    elif isinstance(result, list):
        positions_list = result
    else:
        positions_list = []

    if not positions_list:
        return {"message": "No Open Positions Found"}, 200

    for position in positions_list:
        net_qty = int(position.get("Quantity", 0))
        if net_qty == 0:
            continue

        action = "SELL" if net_qty > 0 else "BUY"
        quantity = abs(net_qty)
        exchange_segment = position["ExchangeSegment"]
        instrument_id = position.get("ExchangeInstrumentID", position.get("ExchangeInstrumentId"))

        place_order_payload = {
            "exchangeSegment": exchange_segment,
            "exchangeInstrumentID": instrument_id,
            "productType": position.get("ProductType", "NRML"),
            "orderType": "MARKET",
            "orderSide": action,
            "timeInForce": "DAY",
            "disclosedQuantity": "0",
            "orderQuantity": str(quantity),
            "limitPrice": "0",
            "stopPrice": "0",
            "orderUniqueIdentifier": "openalgo",
        }
        place_order_api(place_order_payload, auth)

    return {"status": "success", "message": "All Open Positions SquaredOff"}, 200


def cancel_order(orderid, auth):
    """
    Cancel an active order by ID.
    """
    AUTH_TOKEN = auth
    client = get_httpx_client()
    headers = {
        "authorization": AUTH_TOKEN,
        "Content-Type": "application/json",
    }
    response = client.delete(f"{INTERACTIVE_URL}/orders?appOrderID={orderid}", headers=headers)
    response.status = response.status_code

    try:
        data = response.json()
    except Exception:
        data = {"status": False, "message": response.text}

    if data.get("type") == "success" or data.get("status"):
        return {"status": "success", "orderid": orderid}, 200
    else:
        return {
            "status": "error",
            "message": data.get("description") or data.get("message", "Failed to cancel order"),
        }, response.status


def modify_order(data, auth):
    """
    Modify price, quantity, or trigger price of an existing order.
    """
    AUTH_TOKEN = auth
    client = get_httpx_client()

    token = get_token(data["symbol"], data["exchange"])
    data["symbol"] = get_br_symbol(data["symbol"], data["exchange"])

    transformed_data = transform_modify_order_data(data, token)
    headers = {
        "authorization": AUTH_TOKEN,
        "Content-Type": "application/json",
    }
    response = client.put(f"{INTERACTIVE_URL}/orders", headers=headers, json=transformed_data)
    response.status = response.status_code

    try:
        data_resp = response.json()
    except Exception:
        data_resp = {"status": "false", "message": response.text}

    if data_resp.get("type") == "success" or data_resp.get("status") == "true" or data_resp.get("message") == "SUCCESS":
        ret_id = data_resp.get("result", {}).get("AppOrderID") or data_resp.get("data", {}).get("orderid", data.get("orderid"))
        return {"status": "success", "orderid": ret_id}, 200
    else:
        return {
            "status": "error",
            "message": data_resp.get("description") or data_resp.get("message", "Failed to modify order"),
        }, response.status


def cancel_all_orders_api(data, auth):
    """
    Cancel all open/trigger-pending orders.
    """
    order_book_response = get_order_book(auth)
    if not order_book_response or order_book_response.get("type") != "success":
        return [], []

    orders = order_book_response.get("result", [])
    orders_to_cancel = [
        order for order in orders if order.get("OrderStatus") in ["New", "Open", "Trigger Pending", "Pending"]
    ]

    canceled_orders = []
    failed_cancellations = []

    for order in orders_to_cancel:
        orderid = order.get("AppOrderID")
        if not orderid:
            continue
        cancel_response, status_code = cancel_order(orderid, auth)
        if status_code == 200:
            canceled_orders.append(orderid)
        else:
            failed_cancellations.append(orderid)

    return canceled_orders, failed_cancellations
