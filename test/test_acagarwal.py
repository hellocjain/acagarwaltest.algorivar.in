"""Unit tests for AC Agarwal Symphony XTS Broker Plugin in OpenAlgo."""

import json
import pytest
from broker.acagarwal.baseurl import BASE_URL, INTERACTIVE_URL, MARKET_DATA_URL
from broker.acagarwal.mapping.transform_data import (
    map_exchange,
    map_exchange_numeric,
    map_order_type,
    map_product_type,
    transform_data,
    transform_modify_order_data,
)
from broker.acagarwal.mapping.order_data import (
    transform_order_data,
    transform_tradebook_data,
    transform_positions_data,
    transform_holdings_data,
)
from broker.acagarwal.mapping.margin_data import (
    parse_margin_response,
)
from broker.acagarwal.streaming.acagarwal_mapping import (
    AcagarwalExchangeMapper,
    AcagarwalCapabilityRegistry,
)
from broker.acagarwal.streaming.acagarwal_adapter import AcagarwalWebSocketAdapter
from websocket_proxy.broker_factory import _get_adapter_class


def test_acagarwal_plugin_json():
    with open("broker/acagarwal/plugin.json") as f:
        manifest = json.load(f)

    assert manifest["Plugin Name"] == "acagarwal"
    assert manifest["broker_type"] == "IN_stock"
    assert "NSE" in manifest["supported_exchanges"]
    assert "BSE" in manifest["supported_exchanges"]
    assert "NFO" in manifest["supported_exchanges"]
    assert "BFO" in manifest["supported_exchanges"]
    assert "CDS" in manifest["supported_exchanges"]
    assert "MCX" in manifest["supported_exchanges"]
    assert "NSE_INDEX" in manifest["supported_exchanges"]
    assert "BSE_INDEX" in manifest["supported_exchanges"]


def test_acagarwal_baseurls():
    assert BASE_URL == "https://symphony.acagarwal.com:3000"
    assert INTERACTIVE_URL == "https://symphony.acagarwal.com:3000/interactive"
    assert MARKET_DATA_URL == "https://symphony.acagarwal.com:3000/apimarketdata"


def test_transform_data_market_order():
    req = {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "action": "BUY",
        "quantity": "10",
        "product": "MIS",
        "pricetype": "MARKET",
        "price": "0",
        "trigger_price": "0",
        "disclosed_quantity": "0",
    }
    payload = transform_data(req, token="2885")

    assert payload["exchangeSegment"] == "NSECM"
    assert payload["exchangeInstrumentID"] == 2885
    assert payload["productType"] == "MIS"
    assert payload["orderType"] == "MARKET"
    assert payload["orderSide"] == "BUY"
    assert payload["orderQuantity"] == 10
    assert payload["limitPrice"] == 0.0
    assert payload["stopPrice"] == 0.0


def test_transform_data_limit_order():
    req = {
        "symbol": "CRUDEOIL24MARFUT",
        "exchange": "MCX",
        "action": "SELL",
        "quantity": "1",
        "product": "NRML",
        "pricetype": "LIMIT",
        "price": "6500.5",
        "trigger_price": "0",
        "disclosed_quantity": "0",
    }
    payload = transform_data(req, token="12345")

    assert payload["exchangeSegment"] == "MCXFO"
    assert payload["exchangeInstrumentID"] == 12345
    assert payload["productType"] == "NRML"
    assert payload["orderType"] == "LIMIT"
    assert payload["orderSide"] == "SELL"
    assert payload["orderQuantity"] == 1
    assert payload["limitPrice"] == 6500.5


def test_transform_data_sl_order():
    req = {
        "symbol": "NIFTY24MAR22000CE",
        "exchange": "NFO",
        "action": "BUY",
        "quantity": "50",
        "product": "NRML",
        "pricetype": "SL",
        "price": "150.0",
        "trigger_price": "145.0",
        "disclosed_quantity": "0",
    }
    payload = transform_data(req, token="67890")

    assert payload["exchangeSegment"] == "NSEFO"
    assert payload["orderType"] == "STOPLIMIT"
    assert payload["limitPrice"] == 150.0
    assert payload["stopPrice"] == 145.0


def test_transform_modify_order_data():
    req = {
        "orderid": "1001",
        "action": "BUY",
        "pricetype": "LIMIT",
        "price": "2900.0",
        "quantity": "20",
        "disclosed_quantity": "0",
        "trigger_price": "0",
    }
    payload = transform_modify_order_data(req, token="2885")

    assert payload["appOrderID"] == 1001
    assert payload["modifiedOrderType"] == "LIMIT"
    assert payload["modifiedOrderQuantity"] == 20
    assert payload["modifiedLimitPrice"] == 2900.0


def test_transform_order_book():
    raw_orders = [
        {
            "AppOrderID": 12345678,
            "TradingSymbol": "RELIANCE-EQ",
            "ExchangeSegment": "NSECM",
            "ProductType": "MIS",
            "OrderPrice": 2500.0,
            "OrderQuantity": 10,
            "CumulativeQuantity": 10,
            "OrderSide": "BUY",
            "OrderStatus": "Filled",
            "OrderAverageTradedPrice": "2500.0",
            "LeavesQuantity": 0,
            "OrderGeneratedDateTime": "03-09-2026 10:00:00",
            "OrderType": "LIMIT",
            "CancelRejectReason": "",
        }
    ]
    transformed = transform_order_data(raw_orders)
    assert len(transformed) == 1
    assert transformed[0]["orderid"] == "12345678"
    assert transformed[0]["symbol"] == "RELIANCE-EQ"
    assert transformed[0]["exchange"] == "NSE"
    assert transformed[0]["status"] == "complete"
    assert transformed[0]["action"] == "BUY"
    assert transformed[0]["quantity"] == 10


def test_transform_positions():
    raw_positions = {
        "positionList": [
            {
                "TradingSymbol": "SBIN-EQ",
                "ExchangeSegment": "NSECM",
                "ProductType": "MIS",
                "Quantity": 50,
                "BuyAveragePrice": 600.0,
                "SellAveragePrice": 0.0,
                "BuyQuantity": 50,
                "SellQuantity": 0,
            }
        ]
    }
    transformed = transform_positions_data(raw_positions)
    assert len(transformed) == 1
    assert transformed[0]["symbol"] == "SBIN-EQ"
    assert transformed[0]["exchange"] == "NSE"
    assert transformed[0]["product"] == "MIS"
    assert transformed[0]["quantity"] == 50


def test_margin_response_parsing():
    raw_margin = {
        "type": "success",
        "result": {
            "brokerageDeatils": {
                "IsValid": True,
                "MarginRequired": 25000.5,
                "MarginAvailable": 100000.0,
                "MarginShortfall": 0.0,
            }
        },
    }
    parsed = parse_margin_response(raw_margin)
    assert parsed["status"] == "success"
    assert parsed["margin_required"] == 25000.5
    assert parsed["margin_available"] == 100000.0
    assert parsed["margin_shortfall"] == 0.0


def test_streaming_exchange_mapper():
    assert AcagarwalExchangeMapper.get_exchange_type("NSE") == 1
    assert AcagarwalExchangeMapper.get_exchange_type("NFO") == 2
    assert AcagarwalExchangeMapper.get_exchange_type("CDS") == 3
    assert AcagarwalExchangeMapper.get_exchange_type("BSE") == 11
    assert AcagarwalExchangeMapper.get_exchange_type("BFO") == 12
    assert AcagarwalExchangeMapper.get_exchange_type("MCX") == 51

    assert AcagarwalExchangeMapper.get_openalgo_exchange(1) == "NSE"
    assert AcagarwalExchangeMapper.get_openalgo_exchange(2) == "NFO"
    assert AcagarwalExchangeMapper.get_openalgo_exchange(51) == "MCX"


def test_adapter_factory_resolution():
    adapter_cls = _get_adapter_class("acagarwal")
    assert adapter_cls == AcagarwalWebSocketAdapter
