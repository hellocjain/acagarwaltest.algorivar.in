"""AC Agarwal Symphony XTS Market Data API."""

import json
import os
import urllib.parse
from datetime import datetime, timedelta

import pandas as pd
import pytz
from flask import session

from broker.acagarwal.api.auth_api import get_feed_token as refresh_feed_token
from broker.acagarwal.baseurl import MARKET_DATA_URL
from broker.acagarwal.database.master_contract_db import SymToken, db_session
from database.auth_db import get_feed_token
from database.token_db import get_br_symbol, get_brexchange, get_oa_symbol
from utils.httpx_client import get_httpx_client
from utils.logging import get_logger

logger = get_logger(__name__)


def get_api_response(endpoint, auth, method="GET", payload="", feed_token=None, params=None):
    """
    Execute request to AC Agarwal Market Data API.
    """
    AUTH_TOKEN = auth
    FEED_TOKEN = feed_token if feed_token else AUTH_TOKEN
    client = get_httpx_client()

    headers = {
        "authorization": FEED_TOKEN,
        "Content-Type": "application/json",
    }
    url = f"{MARKET_DATA_URL}{endpoint}"

    try:
        if method.upper() == "GET":
            response = client.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            response = client.post(url, headers=headers, json=payload if payload else {})
        else:
            response = client.request(method, url, headers=headers, json=payload if payload else {})

        response.status = response.status_code
        return response.json()
    except Exception as e:
        logger.error(f"Market Data API request failed: {str(e)}")
        raise


class BrokerData:
    def __init__(self, auth_token, feed_token=None, user_id=None):
        self.auth_token = auth_token
        self.feed_token = feed_token
        self.user_id = user_id

        self.timeframe_map = {
            "1s": "1",
            "1m": "60",
            "2m": "120",
            "3m": "180",
            "5m": "300",
            "10m": "600",
            "15m": "900",
            "30m": "1800",
            "60m": "3600",
            "D": "D",
        }

    def _refresh_feed_token(self):
        try:
            new_feed_token, user_id, error = refresh_feed_token()
            if error:
                logger.error(f"Failed to refresh feed token: {error}")
                return False
            self.feed_token = new_feed_token
            if user_id:
                self.user_id = user_id
            return True
        except Exception as e:
            logger.error(f"Error refreshing feed token: {e}")
            return False

    def _get_instrument_token(self, symbol: str, exchange: str) -> tuple:
        exchange_segment_map = {
            "NSE": 1,
            "NSE_INDEX": 1,
            "NFO": 2,
            "CDS": 3,
            "BSE": 11,
            "BSE_INDEX": 11,
            "BFO": 12,
            "MCX": 51,
        }

        br_symbol = get_br_symbol(symbol, exchange)
        brexchange = exchange_segment_map.get(exchange)
        if brexchange is None:
            raise Exception(f"Unknown exchange segment: {exchange}")

        with db_session() as s:
            symbol_info = (
                s.query(SymToken)
                .filter(SymToken.exchange == exchange, SymToken.brsymbol == br_symbol)
                .first()
            )

            if not symbol_info:
                # Fallback matching on symbol
                symbol_info = (
                    s.query(SymToken)
                    .filter(SymToken.exchange == exchange, SymToken.symbol == symbol)
                    .first()
                )

            if not symbol_info:
                raise Exception(f"Could not find exchange token for {exchange}:{br_symbol}")

            return symbol_info, brexchange

    def _fetch_market_data(self, token: dict, message_code: int, retry_on_invalid_token: bool = True) -> dict:
        try:
            payload = {
                "instruments": [token],
                "xtsMessageCode": message_code,
                "publishFormat": "JSON",
            }

            response = get_api_response(
                "/instruments/quotes",
                self.auth_token,
                method="POST",
                payload=payload,
                feed_token=self.feed_token,
            )

            if not response or response.get("type") != "success":
                error_msg = response.get("description", "Unknown error") if response else "No response"
                if retry_on_invalid_token and any(kw in str(error_msg).lower() for kw in ("token", "session", "auth", "invalid")):
                    if self._refresh_feed_token():
                        return self._fetch_market_data(token, message_code, retry_on_invalid_token=False)
                return None

            list_quotes = response.get("result", {}).get("listQuotes", [])
            if not list_quotes:
                return None

            raw_data = list_quotes[0]
            if not raw_data:
                return None

            return json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except Exception as e:
            logger.error(f"Error fetching quote (code {message_code}): {e}")
            return None

    def get_quotes(self, symbol: str, exchange: str) -> dict:
        """
        Get quotes including LTP, open, high, low, close, volume, and OI.
        """
        try:
            symbol_info, brexchange = self._get_instrument_token(symbol, exchange)
            token = {"exchangeSegment": brexchange, "exchangeInstrumentID": int(symbol_info.token)}

            market_data = self._fetch_market_data(token, 1502)
            if not market_data:
                raise Exception("Failed to fetch market data")

            oi = 0
            try:
                oi_data = self._fetch_market_data(token, 1510)
                if oi_data and "OpenInterest" in oi_data:
                    oi = oi_data["OpenInterest"]
            except Exception:
                pass

            touchline = market_data.get("Touchline", {})
            return {
                "ask": touchline.get("AskInfo", {}).get("Price", 0),
                "ask_qty": touchline.get("AskInfo", {}).get("Size", 0),
                "bid": touchline.get("BidInfo", {}).get("Price", 0),
                "bid_qty": touchline.get("BidInfo", {}).get("Size", 0),
                "high": touchline.get("High", 0),
                "low": touchline.get("Low", 0),
                "ltp": touchline.get("LastTradedPrice", 0),
                "open": touchline.get("Open", 0),
                "prev_close": touchline.get("Close", 0),
                "volume": touchline.get("TotalTradedQuantity", 0),
                "oi": oi,
            }
        except Exception as e:
            logger.error(f"Error in get_quotes for {symbol}:{exchange}: {e}")
            raise

    def get_market_depth(self, symbol: str, exchange: str) -> dict:
        """
        Get Level 2 market depth.
        """
        try:
            symbol_info, brexchange = self._get_instrument_token(symbol, exchange)
            token = {"exchangeSegment": brexchange, "exchangeInstrumentID": int(symbol_info.token)}

            market_data = self._fetch_market_data(token, 1502)
            if not market_data:
                raise Exception("Failed to fetch market data for depth")

            oi = 0
            try:
                oi_data = self._fetch_market_data(token, 1510)
                if oi_data and "OpenInterest" in oi_data:
                    oi = oi_data["OpenInterest"]
            except Exception:
                pass

            touchline = market_data.get("Touchline", {})
            bids = [
                {"price": b.get("Price", 0), "quantity": b.get("Size", 0)}
                for b in market_data.get("Bids", [])[:5]
            ]
            asks = [
                {"price": a.get("Price", 0), "quantity": a.get("Size", 0)}
                for a in market_data.get("Asks", [])[:5]
            ]

            while len(bids) < 5:
                bids.append({"price": 0, "quantity": 0})
            while len(asks) < 5:
                asks.append({"price": 0, "quantity": 0})

            return {
                "bids": bids,
                "asks": asks,
                "high": touchline.get("High", 0),
                "low": touchline.get("Low", 0),
                "ltp": touchline.get("LastTradedPrice", 0),
                "ltq": touchline.get("LastTradedQunatity", 0),
                "open": touchline.get("Open", 0),
                "prev_close": touchline.get("Close", 0),
                "volume": touchline.get("TotalTradedQuantity", 0),
                "oi": oi,
                "totalbuyqty": touchline.get("TotalBuyQuantity", 0),
                "totalsellqty": touchline.get("TotalSellQuantity", 0),
            }
        except Exception as e:
            logger.error(f"Error in get_market_depth for {symbol}:{exchange}: {e}")
            return {
                "bids": [{"price": 0, "quantity": 0} for _ in range(5)],
                "asks": [{"price": 0, "quantity": 0} for _ in range(5)],
                "totalbuyqty": 0,
                "totalsellqty": 0,
                "ltp": 0,
                "ltq": 0,
                "volume": 0,
                "open": 0,
                "high": 0,
                "low": 0,
                "prev_close": 0,
                "oi": 0,
            }

    def get_depth(self, symbol: str, exchange: str) -> dict:
        return self.get_market_depth(symbol, exchange)

    def get_history(self, symbol, exchange, timeframe, from_date, to_date):
        """
        Get historical OHLCV candle data.
        """
        try:
            compression_map = {
                "1s": "1",
                "1m": "60",
                "2m": "120",
                "3m": "180",
                "5m": "300",
                "10m": "600",
                "15m": "900",
                "30m": "1800",
                "60m": "3600",
                "D": "D",
            }
            compression_value = compression_map.get(timeframe)
            if not compression_value:
                raise Exception(f"Unsupported timeframe: {timeframe}")

            symbol_info, brexchange = self._get_instrument_token(symbol, exchange)

            params = {
                "exchangeSegment": brexchange,
                "exchangeInstrumentID": int(symbol_info.token),
                "startTime": from_date,
                "endTime": to_date,
                "compressionValue": compression_value,
            }

            response = get_api_response(
                "/instruments/historical/chart",
                self.auth_token,
                method="GET",
                params=params,
                feed_token=self.feed_token,
            )

            if response and response.get("type") == "success":
                data_points = response.get("result", {}).get("dataReponse", "")
                if data_points:
                    rows = data_points.split(",")
                    parsed_candles = []
                    for row in rows:
                        parts = row.strip().split("|")
                        if len(parts) >= 6:
                            try:
                                ts = int(parts[0])
                                open_p = float(parts[1])
                                high_p = float(parts[2])
                                low_p = float(parts[3])
                                close_p = float(parts[4])
                                vol = int(float(parts[5]))
                                oi = int(float(parts[6])) if len(parts) > 6 else 0
                                parsed_candles.append({
                                    "timestamp": ts,
                                    "open": open_p,
                                    "high": high_p,
                                    "low": low_p,
                                    "close": close_p,
                                    "volume": vol,
                                    "oi": oi,
                                })
                            except Exception:
                                continue
                    return parsed_candles
            return []
        except Exception as e:
            logger.error(f"Error fetching history for {symbol}:{exchange}: {e}")
            return []

    def get_intervals(self):
        return ["1s", "1m", "2m", "3m", "5m", "10m", "15m", "30m", "60m", "D"]


def get_quotes(symbol, exchange, auth=None):
    feed_token = get_feed_token()
    bd = BrokerData(auth_token=auth, feed_token=feed_token)
    return bd.get_quotes(symbol, exchange)


def get_market_depth(symbol, exchange, auth=None):
    feed_token = get_feed_token()
    bd = BrokerData(auth_token=auth, feed_token=feed_token)
    return bd.get_market_depth(symbol, exchange)


def get_depth(symbol, exchange):
    feed_token = get_feed_token()
    bd = BrokerData(auth_token=None, feed_token=feed_token)
    return bd.get_depth(symbol, exchange)


def get_history(symbol, exchange, interval, from_date, to_date, auth=None):
    feed_token = get_feed_token()
    bd = BrokerData(auth_token=auth, feed_token=feed_token)
    return bd.get_history(symbol, exchange, interval, from_date, to_date)


def get_intervals():
    return ["1s", "1m", "2m", "3m", "5m", "10m", "15m", "30m", "60m", "D"]
