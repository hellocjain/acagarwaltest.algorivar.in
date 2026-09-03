"""Mapping OpenAlgo API requests to AC Agarwal Symphony XTS parameters."""

from database.token_db import get_br_symbol, get_token
from utils.logging import get_logger

logger = get_logger(__name__)


def transform_data(data, token):
    """
    Transforms the OpenAlgo order request to Symphony XTS structure.
    """
    transformed = {
        "exchangeSegment": map_exchange(data["exchange"]),
        "exchangeInstrumentID": int(token),
        "productType": map_product_type(data["product"]),
        "orderType": map_order_type(data["pricetype"]),
        "orderSide": data["action"].upper(),
        "timeInForce": "DAY",
        "disclosedQuantity": int(data.get("disclosed_quantity", "0")),
        "orderQuantity": int(data["quantity"]),
        "limitPrice": float(data.get("price", "0")),
        "stopPrice": float(data.get("trigger_price", "0")),
        "orderUniqueIdentifier": "openalgo",
    }
    logger.debug(f"Transformed order payload: {transformed}")
    return transformed


def transform_modify_order_data(data, token=None):
    """
    Transforms the OpenAlgo modify order request to Symphony XTS structure.
    """
    app_order_id = data.get("orderid") or data.get("appOrderID")
    if str(app_order_id).isdigit():
        app_order_id = int(app_order_id)

    transformed = {
        "appOrderID": app_order_id,
        "modifiedProductType": map_product_type(data.get("product", "MIS")),
        "modifiedOrderType": map_order_type(data.get("pricetype", "LIMIT")),
        "modifiedOrderQuantity": int(data.get("quantity", 0)),
        "modifiedDisclosedQuantity": int(data.get("disclosed_quantity", "0")),
        "modifiedLimitPrice": float(data.get("price", "0")),
        "modifiedStopPrice": float(data.get("trigger_price", "0")),
        "modifiedTimeInForce": "DAY",
        "orderUniqueIdentifier": "openalgo",
    }
    logger.debug(f"Transformed modify order payload: {transformed}")
    return transformed


def map_exchange(exchange):
    """
    Maps OpenAlgo exchange code to XTS exchange segment string.
    """
    exchange_mapping = {
        "NSE": "NSECM",
        "BSE": "BSECM",
        "MCX": "MCXFO",
        "NFO": "NSEFO",
        "BFO": "BSEFO",
        "CDS": "NSECD",
    }
    if exchange not in exchange_mapping:
        raise ValueError(f"Unsupported exchange: {exchange}")
    return exchange_mapping[exchange]


def map_exchange_numeric(exchange):
    """
    Maps OpenAlgo exchange code to XTS numeric exchange segment code.
    - NSECM = 1
    - NSEFO = 2
    - NSECD = 3
    - BSECM = 11
    - BSEFO = 12
    - BSECD = 13
    - MCXFO = 51
    - NCDEX = 21
    """
    exchange_numeric_mapping = {
        "NSE": 1,
        "NFO": 2,
        "CDS": 3,
        "BSE": 11,
        "BFO": 12,
        "MCX": 51,
    }
    if exchange not in exchange_numeric_mapping:
        raise ValueError(f"Unsupported exchange: {exchange}")
    return exchange_numeric_mapping[exchange]


def map_order_type(pricetype):
    """
    Maps OpenAlgo price type to XTS order type.
    """
    order_type_mapping = {
        "MARKET": "MARKET",
        "LIMIT": "LIMIT",
        "SL": "STOPLIMIT",
        "SL-M": "STOPMARKET",
    }
    return order_type_mapping.get(pricetype, "MARKET")


def map_product_type(product):
    """
    Maps OpenAlgo product type to XTS product type.
    """
    product_type_mapping = {
        "CNC": "CNC",
        "NRML": "NRML",
        "MIS": "MIS",
    }
    return product_type_mapping.get(product, "MIS")


def reverse_map_product_type(exchange, product):
    """
    Reverse maps XTS product type to OpenAlgo product type.
    """
    exchange_mapping = {
        "CNC": "CNC",
        "NRML": "NRML",
        "MIS": "MIS",
    }
    return exchange_mapping.get(product, product)
