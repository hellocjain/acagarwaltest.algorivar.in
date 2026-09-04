"""AC Agarwal XTS Socket.IO Client for Market Data Streaming."""

import json
import struct
from typing import Dict, List
from urllib.parse import urlencode

import requests
import socketio

from broker.acagarwal.baseurl import BASE_URL
from utils.logging import get_logger


class AcagarwalWebSocketClient:
    """
    AC Agarwal Symphony XTS Socket.IO client for market data streaming.
    """

    SOCKET_PATH = "/apimarketdata/socket.io"
    API_ROOT_PATH = "/apimarketdata"
    MIN_ENGINEIO_ACTIVITY_TIMEOUT = 300

    MODE_LTP = 1
    MODE_QUOTE = 2
    MODE_DEPTH = 3

    XTS_MESSAGE_CODES = {
        "TOUCHLINE": 1501,
        "MARKET_DEPTH": 1502,
        "CANDLE_DATA": 1505,
        "OPEN_INTEREST": 1510,
        "LTP": 1501,
    }

    MODE_TO_XTS_CODE = {
        1: 1501,
        2: 1501,
        3: 1502,
    }

    EXCHANGE_SEGMENTS = {
        "NSECM": 1,
        "NSEFO": 2,
        "NSECD": 3,
        "BSECM": 11,
        "BSEFO": 12,
        "MCXFO": 51,
    }

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        user_id: str,
        base_url: str = None,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.user_id = user_id
        self.base_url = (base_url or BASE_URL).rstrip("/")

        self.login_url = f"{self.base_url}{self.API_ROOT_PATH}/auth/login"
        self.subscription_url = f"{self.base_url}{self.API_ROOT_PATH}/instruments/subscription"

        self.market_data_token = None
        self.feed_token = None
        self.actual_user_id = None
        self.app_version = None
        self.expiry_date = None

        self.sio = None
        self.connected = False
        self.running = False

        self.on_open = None
        self.on_close = None
        self.on_error = None
        self.on_data = None
        self.on_message = None

        self.logger = get_logger("acagarwal_websocket")
        self.subscriptions = {}
        self._http_session = requests.Session()
        self._setup_socketio()

    def _setup_socketio(self):
        self.sio = socketio.Client(
            reconnection=False,
            logger=False,
            engineio_logger=False,
            request_timeout=30,
        )

        @self.sio.event
        def connect():
            self.connected = True
            self.logger.info("Socket.IO connected to AC Agarwal Market Data Stream")
            self._apply_engineio_timeout_floor()
            if self.on_open:
                self.on_open()

        @self.sio.event
        def disconnect():
            self.connected = False
            self.logger.info("Socket.IO disconnected from AC Agarwal Market Data Stream")
            if self.on_close:
                self.on_close()

        @self.sio.event
        def connect_error(data):
            self.connected = False
            self.logger.error(f"Socket.IO connection error: {data}")
            if self.on_error:
                self.on_error(data)

        @self.sio.on("1501-json-full")
        def on_1501_json_full(data):
            self._handle_json_market_data(data, 1501)

        @self.sio.on("1501-json-partial")
        def on_1501_json_partial(data):
            self._handle_json_market_data(data, 1501)

        @self.sio.on("1502-json-full")
        def on_1502_json_full(data):
            self._handle_json_market_data(data, 1502)

        @self.sio.on("1502-json-partial")
        def on_1502_json_partial(data):
            self._handle_json_market_data(data, 1502)

        @self.sio.on("1505-json-full")
        def on_1505_json_full(data):
            self._handle_json_market_data(data, 1505)

        @self.sio.on("1510-json-full")
        def on_1510_json_full(data):
            self._handle_json_market_data(data, 1510)

        @self.sio.on("1512-json-full")
        def on_1512_json_full(data):
            self._handle_json_market_data(data, 1512)

        @self.sio.on("1512-json-partial")
        def on_1512_json_partial(data):
            self._handle_json_market_data(data, 1512)

    def _apply_engineio_timeout_floor(self):
        try:
            eio = getattr(self.sio, "eio", None)
            if eio and hasattr(eio, "ping_timeout"):
                if eio.ping_timeout < self.MIN_ENGINEIO_ACTIVITY_TIMEOUT:
                    eio.ping_timeout = self.MIN_ENGINEIO_ACTIVITY_TIMEOUT
        except Exception:
            pass

    def _handle_json_market_data(self, data, message_code: int):
        if not data:
            return
        try:
            if isinstance(data, str):
                parsed = json.loads(data)
            else:
                parsed = data

            if self.on_data:
                self.on_data(parsed, message_code)
            if self.on_message:
                self.on_message(parsed)
        except Exception as e:
            self.logger.error(f"Error handling market data: {e}")

    def login(self) -> bool:
        try:
            payload = {
                "appKey": self.api_key,
                "secretKey": self.api_secret,
                "source": "WebAPI",
            }
            headers = {"Content-Type": "application/json"}
            response = self._http_session.post(
                self.login_url, json=payload, headers=headers, timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("type") == "success":
                    res_data = result.get("result", {})
                    self.market_data_token = res_data.get("token")
                    self.feed_token = self.market_data_token
                    self.actual_user_id = res_data.get("userID", self.user_id)
                    return True
                else:
                    self.logger.error(f"Login failed: {result}")
                    return False
            else:
                self.logger.error(f"Login HTTP {response.status_code}: {response.text}")
                return False
        except Exception as e:
            self.logger.error(f"Login exception: {e}")
            return False

    def connect(self) -> bool:
        if not self.market_data_token and not self.login():
            return False

        try:
            query_params = {
                "token": self.market_data_token,
                "userID": self.actual_user_id or self.user_id,
                "publishFormat": "JSON",
                "broadcastMode": "Full",
            }
            ws_url = f"{self.base_url}?{urlencode(query_params)}"

            self.sio.connect(
                ws_url,
                socketio_path=self.SOCKET_PATH,
                transports=["websocket", "polling"],
                wait=True,
                wait_timeout=15,
            )
            self.running = True
            return True
        except Exception as e:
            self.logger.error(f"Socket.IO connection exception: {e}")
            return False

    def subscribe(self, instruments: List[Dict], mode: int = 1) -> bool:
        if not self.market_data_token:
            return False

        if not instruments:
            return True

        xts_code = self.MODE_TO_XTS_CODE.get(mode, 1501)
        headers = {
            "Content-Type": "application/json",
            "authorization": self.market_data_token,
        }

        any_success = False
        # XTS supports batch subscriptions up to 50-100 instruments per request
        batch_size = 50
        for i in range(0, len(instruments), batch_size):
            chunk = instruments[i : i + batch_size]
            payload = {
                "instruments": chunk,
                "xtsMessageCode": xts_code,
            }

            try:
                response = self._http_session.post(
                    self.subscription_url, json=payload, headers=headers, timeout=10
                )
                if response.status_code == 200:
                    for inst in chunk:
                        key = f"{inst.get('exchangeSegment')}_{inst.get('exchangeInstrumentID')}"
                        self.subscriptions[key] = mode
                    any_success = True
                else:
                    self.logger.warning(
                        f"AC Agarwal XTS subscription HTTP {response.status_code}: {response.text}"
                    )
                    if "Exceeded Instrument Subscription Limit" in response.text:
                        self.logger.warning(
                            "Instrument subscription limit reached on AC Agarwal market data feed. "
                            "Halting additional subscription chunks."
                        )
                        break
            except Exception as e:
                self.logger.error(f"Subscription error: {e}")
                break

        return any_success

    def unsubscribe(self, instruments: List[Dict], mode: int = 1) -> bool:
        if not self.market_data_token:
            return False

        if not instruments:
            return True

        xts_code = self.MODE_TO_XTS_CODE.get(mode, 1501)
        headers = {
            "Content-Type": "application/json",
            "authorization": self.market_data_token,
        }

        any_success = False
        batch_size = 50
        for i in range(0, len(instruments), batch_size):
            chunk = instruments[i : i + batch_size]
            payload = {
                "instruments": chunk,
                "xtsMessageCode": xts_code,
            }

            try:
                response = self._http_session.put(
                    self.subscription_url, json=payload, headers=headers, timeout=10
                )
                if response.status_code == 200:
                    for inst in chunk:
                        key = f"{inst.get('exchangeSegment')}_{inst.get('exchangeInstrumentID')}"
                        self.subscriptions.pop(key, None)
                    any_success = True
                else:
                    self.logger.warning(
                        f"AC Agarwal XTS unsubscribe HTTP {response.status_code}: {response.text}"
                    )
            except Exception as e:
                self.logger.error(f"Unsubscription error: {e}")
                break

        return any_success

    def close(self):
        self.running = False
        try:
            if self.sio and self.sio.connected:
                self.sio.disconnect()
        except Exception:
            pass
        self.connected = False
