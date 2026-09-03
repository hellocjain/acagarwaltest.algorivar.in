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
        "authorization": FEED_TOKEN if FEED_TOKEN else "",
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
        try:
            return response.json()
        except Exception:
            logger.error(f"Non-JSON response from {url} (status {response.status_code}): {response.text[:200]}")
            return {"type": "error", "description": f"HTTP {response.status_code}: {response.text[:200]}"}
    except Exception as e:
        logger.error(f"Market Data API request failed: {str(e)}")
        raise


class BrokerData:
    def __init__(self, auth_token, feed_token=None, user_id=None):
        self.auth_token = auth_token
        self.feed_token = feed_token
        self.user_id = user_id

        if not self.feed_token:
            try:
                from database.auth_db import get_feed_token as db_get_feed_token
                user = None
                try:
                    user = session.get("user")
                except Exception:
                    pass
                self.feed_token = db_get_feed_token(user or self.user_id or "Chinmaya")
            except Exception:
                pass

        if not self.feed_token:
            self._refresh_feed_token()

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
            try:
                from database.auth_db import store_feed_token
                store_feed_token(self.user_id or "Chinmaya", new_feed_token)
            except Exception:
                pass
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
        Get historical OHLCV candle data as a pandas DataFrame.
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

            br_symbol = get_br_symbol(symbol, exchange)

            segment_map = {
                "NSE": "NSECM",
                "BSE": "BSECM",
                "NFO": "NSEFO",
                "BFO": "BSEFO",
                "CDS": "NSECD",
                "MCX": "MCXFO",
                "NSE_INDEX": "NSECM",
                "BSE_INDEX": "BSECM",
            }
            exchange_segment = segment_map.get(exchange)
            if not exchange_segment:
                raise Exception(f"Unsupported exchange: {exchange}")

            symbol_info, _ = self._get_instrument_token(symbol, exchange)
            token = symbol_info.token

            # Convert dates to datetime objects with IST timezone
            start_date = pd.to_datetime(from_date).tz_localize("Asia/Kolkata")
            end_date = pd.to_datetime(to_date).tz_localize("Asia/Kolkata")

            from_dt = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            to_dt = end_date.replace(hour=23, minute=59, second=59, microsecond=0)

            dfs = []
            current_start = from_dt

            while current_start <= to_dt:
                current_end = min(current_start + timedelta(days=6), to_dt)

                from_str = current_start.strftime("%b %d %Y %H%M%S")
                to_str = current_end.strftime("%b %d %Y %H%M%S")

                params = {
                    "exchangeSegment": exchange_segment,
                    "exchangeInstrumentID": int(token),
                    "startTime": from_str,
                    "endTime": to_str,
                    "compressionValue": compression_value,
                }

                response = get_api_response(
                    "/instruments/ohlc",
                    self.auth_token,
                    method="GET",
                    feed_token=self.feed_token,
                    params=params,
                )

                if not response or response.get("type") != "success":
                    error_msg = response.get("description", "Unknown error") if response else "No response"
                    if any(kw in str(error_msg).lower() for kw in ("invalid token", "session", "token")):
                        if self._refresh_feed_token():
                            response = get_api_response(
                                "/instruments/ohlc",
                                self.auth_token,
                                method="GET",
                                feed_token=self.feed_token,
                                params=params,
                            )
                    if not response or response.get("type") != "success":
                        logger.warning(f"Failed to fetch OHLC for {from_str} to {to_str}: {response}")
                        current_start = current_end + timedelta(days=1)
                        continue

                raw_data = response.get("result", {}).get("dataReponse", "")
                if not raw_data:
                    current_start = current_end + timedelta(days=1)
                    continue

                rows = raw_data.strip().split(",")
                data = []
                for row in rows:
                    fields = row.split("|")
                    if len(fields) < 6:
                        continue
                    try:
                        oi_val = int(float(fields[6])) if len(fields) > 6 else 0
                        data.append(
                            {
                                "timestamp": int(fields[0]),
                                "open": float(fields[1]),
                                "high": float(fields[2]),
                                "low": float(fields[3]),
                                "close": float(fields[4]),
                                "volume": int(float(fields[5])),
                                "oi": oi_val,
                            }
                        )
                    except (ValueError, IndexError):
                        continue

                if data:
                    dfs.append(pd.DataFrame(data))

                current_start = current_end + timedelta(days=1)

            if not dfs:
                return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])

            final_df = pd.concat(dfs, ignore_index=True)
            final_df = (
                final_df.sort_values("timestamp")
                .drop_duplicates("timestamp")
                .reset_index(drop=True)
            )

            final_df["timestamp"] = pd.to_datetime(final_df["timestamp"], unit="s")

            if compression_value == "D":
                final_df["timestamp"] = final_df["timestamp"].apply(
                    lambda x: x.replace(hour=0, minute=0, second=0)
                )
            else:
                final_df["timestamp"] = final_df["timestamp"] - pd.Timedelta(hours=5, minutes=30)
                interval_minutes = int(compression_value) // 60 if compression_value != "D" else 0
                if interval_minutes > 0:
                    final_df["timestamp"] = final_df["timestamp"].dt.floor(f"{interval_minutes}min")

            final_df["timestamp"] = final_df["timestamp"].astype("int64") // 10**9

            numeric_columns = ["open", "high", "low", "close", "volume"]
            final_df[numeric_columns] = final_df[numeric_columns].apply(pd.to_numeric)
            if "oi" not in final_df.columns:
                final_df["oi"] = 0
            else:
                final_df["oi"] = pd.to_numeric(final_df["oi"]).fillna(0).astype(int)

            return final_df

        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}:{exchange}: {str(e)}")
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])

    def get_intervals(self):
        return ["1s", "1m", "2m", "3m", "5m", "10m", "15m", "30m", "60m", "D"]


def _get_context_feed_token():
    try:
        from database.auth_db import get_feed_token as db_get_feed_token
        user = None
        try:
            user = session.get("user")
        except Exception:
            pass
        return db_get_feed_token(user or "Chinmaya")
    except Exception:
        return None


def get_quotes(symbol, exchange, auth=None):
    feed_token = _get_context_feed_token()
    bd = BrokerData(auth_token=auth, feed_token=feed_token)
    return bd.get_quotes(symbol, exchange)


def get_market_depth(symbol, exchange, auth=None):
    feed_token = _get_context_feed_token()
    bd = BrokerData(auth_token=auth, feed_token=feed_token)
    return bd.get_market_depth(symbol, exchange)


def get_depth(symbol, exchange):
    feed_token = _get_context_feed_token()
    bd = BrokerData(auth_token=None, feed_token=feed_token)
    return bd.get_depth(symbol, exchange)


def get_history(symbol, exchange, interval, from_date, to_date, auth=None):
    feed_token = _get_context_feed_token()
    bd = BrokerData(auth_token=auth, feed_token=feed_token)
    return bd.get_history(symbol, exchange, interval, from_date, to_date)


def get_intervals():
    return ["1s", "1m", "2m", "3m", "5m", "10m", "15m", "30m", "60m", "D"]
