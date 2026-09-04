"""AC Agarwal Symphony XTS WebSocket Adapter for OpenAlgo."""

import base64
import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from broker.acagarwal.streaming.acagarwal_websocket import AcagarwalWebSocketClient
from database.auth_db import get_auth_token, get_feed_token
from database.token_db import get_symbol, get_token
from utils.logging import get_logger

sys.path.append(os.path.join(os.path.dirname(__file__), "../../../"))

from websocket_proxy.base_adapter import BaseBrokerWebSocketAdapter
from websocket_proxy.mapping import SymbolMapper

from .acagarwal_mapping import AcagarwalCapabilityRegistry, AcagarwalExchangeMapper


class AcagarwalWebSocketAdapter(BaseBrokerWebSocketAdapter):
    """AC Agarwal Symphony XTS WebSocket adapter for Unified WebSocket Proxy."""

    MAX_SYMBOLS_PER_CONNECTION = 50
    MAX_CONNECTIONS = 1

    def __init__(self):
        super().__init__()
        self.logger = get_logger("acagarwal_websocket")
        self.ws_client = None
        self.user_id = None
        self.broker_name = "acagarwal"
        self.reconnect_delay = 5
        self.max_reconnect_delay = 60
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.running = False
        self.lock = threading.Lock()
        self._reconnect_worker_lock = threading.Lock()
        self._reconnect_worker: threading.Thread | None = None
        self._stop_event = threading.Event()

    def initialize(
        self, broker_name: str, user_id: str, auth_data: dict[str, str] | None = None
    ) -> None:
        self.user_id = user_id
        self.broker_name = broker_name

        if not auth_data:
            auth_token = get_auth_token(user_id, bypass_cache=True)
            feed_token = get_feed_token(user_id)
            api_key = os.getenv("BROKER_API_KEY_MARKET", os.getenv("BROKER_API_KEY"))
            api_secret = os.getenv("BROKER_API_SECRET_MARKET", os.getenv("BROKER_API_SECRET"))
        else:
            auth_token = auth_data.get("auth_token")
            feed_token = auth_data.get("feed_token")
            api_key = auth_data.get("api_key", os.getenv("BROKER_API_KEY_MARKET", os.getenv("BROKER_API_KEY")))
            api_secret = auth_data.get("api_secret", os.getenv("BROKER_API_SECRET_MARKET", os.getenv("BROKER_API_SECRET")))

        if not api_key or not api_secret:
            raise ValueError("Missing AC Agarwal XTS API credentials in environment variables")

        if self.ws_client is not None:
            try:
                self.ws_client.close()
            except Exception:
                pass

        self.ws_client = AcagarwalWebSocketClient(
            api_key=api_key,
            api_secret=api_secret,
            user_id=user_id,
        )

        self.ws_client.on_open = self._on_open
        self.ws_client.on_data = self._on_data
        self.ws_client.on_error = self._on_error
        self.ws_client.on_close = self._on_close
        self.ws_client.on_message = self._on_message

        self.running = True

    def connect(self) -> None:
        if not self.ws_client:
            raise RuntimeError("Adapter not initialized. Call initialize() first.")

        self.logger.info("Connecting to AC Agarwal Symphony XTS Market Data WebSocket...")
        self.ws_client.connect()

    def disconnect(self) -> None:
        self.running = False
        self._stop_event.set()
        if self.ws_client:
            self.ws_client.close()
        self.cleanup_zmq()

    def subscribe(self, symbol: str, exchange: str, mode: int = 2, depth_level: int = 5) -> dict[str, Any]:
        exchange_type = AcagarwalExchangeMapper.get_exchange_type(exchange)
        token = get_token(symbol, exchange)

        if not token:
            return {"status": "error", "message": f"Token not found for {symbol} on {exchange}"}

        instruments = [{
            "exchangeSegment": exchange_type,
            "exchangeInstrumentID": int(token),
        }]

        success = self.ws_client.subscribe(instruments, mode=mode)
        if success:
            with self.lock:
                key = f"{symbol}:{exchange}:{mode}"
                self.subscriptions[key] = {
                    "symbol": symbol,
                    "exchange": exchange,
                    "token": token,
                    "mode": mode,
                    "depth_level": depth_level,
                }
            return {"status": "success", "actual_depth": depth_level}
        return {"status": "error", "message": "Subscription failed on broker feed"}

    def subscribe_batch(
        self,
        symbols_list: List[Dict[str, str]],
        mode: int = 2,
        depth_level: int = 5,
    ) -> List[Dict[str, Any]]:
        """Subscribe to a batch of symbols at once.

        Uses bulk token lookup and sends chunked batch requests to Symphony XTS.
        Returns a list of per-symbol result dicts compatible with websocket_proxy.
        """
        if not symbols_list:
            return []

        from database.token_db_enhanced import get_tokens_bulk

        lookup_pairs = []
        valid_items = []
        results = []

        for item in symbols_list:
            sym = item.get("symbol")
            ex = item.get("exchange")
            if not sym or not ex:
                results.append({
                    "symbol": sym or "",
                    "exchange": ex or "",
                    "status": "error",
                    "message": "Invalid symbol or exchange",
                })
                continue
            lookup_pairs.append((sym, ex))
            valid_items.append((sym, ex))

        if not lookup_pairs:
            return results

        tokens = get_tokens_bulk(lookup_pairs)

        instruments = []
        matched_symbols = []

        for (sym, ex), token in zip(valid_items, tokens):
            if not token:
                results.append({
                    "symbol": sym,
                    "exchange": ex,
                    "status": "error",
                    "message": f"Token not found for {sym} on {ex}",
                })
                continue

            exchange_type = AcagarwalExchangeMapper.get_exchange_type(ex)
            instruments.append({
                "exchangeSegment": exchange_type,
                "exchangeInstrumentID": int(token),
            })
            matched_symbols.append((sym, ex, token))

        if instruments:
            success = self.ws_client.subscribe(instruments, mode=mode)
            with self.lock:
                for sym, ex, token in matched_symbols:
                    key = f"{sym}:{ex}:{mode}"
                    if success:
                        self.subscriptions[key] = {
                            "symbol": sym,
                            "exchange": ex,
                            "token": token,
                            "mode": mode,
                            "depth_level": depth_level,
                        }
                        results.append({
                            "symbol": sym,
                            "exchange": ex,
                            "status": "success",
                            "actual_depth": depth_level,
                        })
                    else:
                        results.append({
                            "symbol": sym,
                            "exchange": ex,
                            "status": "error",
                            "message": "Subscription failed on broker feed",
                        })

        return results

    def unsubscribe(self, symbol: str, exchange: str, mode: int = 2) -> dict[str, Any]:
        exchange_type = AcagarwalExchangeMapper.get_exchange_type(exchange)
        token = get_token(symbol, exchange)

        if not token:
            return {"status": "error", "message": f"Token not found for {symbol} on {exchange}"}

        instruments = [{
            "exchangeSegment": exchange_type,
            "exchangeInstrumentID": int(token),
        }]

        self.ws_client.unsubscribe(instruments, mode=mode)
        with self.lock:
            key = f"{symbol}:{exchange}:{mode}"
            self.subscriptions.pop(key, None)
        return {"status": "success"}

    def unsubscribe_batch(
        self,
        symbols_list: List[Dict[str, str]],
        mode: int = 2,
    ) -> List[Dict[str, Any]]:
        if not symbols_list:
            return []

        from database.token_db_enhanced import get_tokens_bulk

        lookup_pairs = [
            (item.get("symbol"), item.get("exchange"))
            for item in symbols_list
            if item.get("symbol") and item.get("exchange")
        ]
        tokens = get_tokens_bulk(lookup_pairs)

        instruments = []
        with self.lock:
            for (sym, ex), token in zip(lookup_pairs, tokens):
                if token:
                    exchange_type = AcagarwalExchangeMapper.get_exchange_type(ex)
                    instruments.append({
                        "exchangeSegment": exchange_type,
                        "exchangeInstrumentID": int(token),
                    })
                key = f"{sym}:{ex}:{mode}"
                self.subscriptions.pop(key, None)

        if instruments:
            self.ws_client.unsubscribe(instruments, mode=mode)

        return [{"symbol": s[0], "exchange": s[1], "status": "success"} for s in lookup_pairs]

    def unsubscribe_all(self):
        with self.lock:
            subs = list(self.subscriptions.values())
            self.subscriptions.clear()

        for s in subs:
            try:
                self.unsubscribe(s["symbol"], s["exchange"], s["mode"])
            except Exception:
                pass

    def _on_open(self):
        self.logger.info("AC Agarwal WebSocket stream opened.")
        self.reconnect_attempts = 0
        # Resubscribe existing subscriptions in batches by mode
        with self.lock:
            subs = list(self.subscriptions.values())

        if subs:
            by_mode: Dict[int, List[Dict[str, str]]] = {}
            for s in subs:
                by_mode.setdefault(s["mode"], []).append(
                    {"symbol": s["symbol"], "exchange": s["exchange"]}
                )
            for m, syms in by_mode.items():
                try:
                    self.subscribe_batch(syms, mode=m)
                except Exception as e:
                    self.logger.error(f"Error re-subscribing batch for mode {m}: {e}")

    def _on_close(self):
        self.logger.info("AC Agarwal WebSocket stream closed.")

    def _on_error(self, error):
        self.logger.error(f"AC Agarwal WebSocket stream error: {error}")

    def _on_message(self, message):
        pass

    def _on_data(self, data, message_code: int):
        try:
            if not isinstance(data, dict):
                return

            exchange_seg = data.get("ExchangeSegment")
            token_id = str(data.get("ExchangeInstrumentID", ""))
            mapped_exchange = AcagarwalExchangeMapper.get_openalgo_exchange(exchange_seg)

            symbol = get_symbol(token_id, mapped_exchange)
            if not symbol:
                return

            touchline = data.get("Touchline", {})
            ltp = float(touchline.get("LastTradedPrice", 0.0) or data.get("LastTradedPrice", 0.0) or 0.0)

            # Publish LTP
            ltp_topic = f"{self.broker_name}_{mapped_exchange}_{symbol}_LTP"
            ltp_data = {
                "symbol": symbol,
                "exchange": mapped_exchange,
                "mode": 1,
                "ltp": ltp,
            }
            self.publish_market_data(ltp_topic, ltp_data)

            # Publish Quote
            quote_topic = f"{self.broker_name}_{mapped_exchange}_{symbol}_QUOTE"
            quote_data = {
                "symbol": symbol,
                "exchange": mapped_exchange,
                "mode": 2,
                "ltp": ltp,
                "open": float(touchline.get("Open", 0.0) or 0.0),
                "high": float(touchline.get("High", 0.0) or 0.0),
                "low": float(touchline.get("Low", 0.0) or 0.0),
                "close": float(touchline.get("Close", 0.0) or 0.0),
                "volume": int(touchline.get("TotalTradedQuantity", 0) or 0),
                "bid": float(touchline.get("BidInfo", {}).get("Price", 0.0) or 0.0),
                "ask": float(touchline.get("AskInfo", {}).get("Price", 0.0) or 0.0),
            }
            self.publish_market_data(quote_topic, quote_data)

            # Publish Depth if available (1502)
            if message_code == 1502 or "Bids" in data or "Asks" in data:
                bids = [{"price": b.get("Price", 0), "quantity": b.get("Size", 0)} for b in data.get("Bids", [])[:5]]
                asks = [{"price": a.get("Price", 0), "quantity": a.get("Size", 0)} for a in data.get("Asks", [])[:5]]
                while len(bids) < 5:
                    bids.append({"price": 0, "quantity": 0})
                while len(asks) < 5:
                    asks.append({"price": 0, "quantity": 0})

                depth_topic = f"{self.broker_name}_{mapped_exchange}_{symbol}_DEPTH"
                depth_data = dict(quote_data)
                depth_data["mode"] = 3
                depth_data["bids"] = bids
                depth_data["asks"] = asks
                self.publish_market_data(depth_topic, depth_data)

        except Exception as e:
            self.logger.error(f"Error processing and publishing market tick: {e}")
