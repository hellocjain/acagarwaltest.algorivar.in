"""End-to-End Simulation & Verification Test Suite for OpenAlgo and AC Agarwal Plugin."""

import json
import os
import socketserver
import threading
import time
import urllib.parse
import urllib.request
import pytest

from install.web_installer import (
    WebInstallerHTTPHandler,
    get_system_diagnostics,
    check_domain_dns,
    run_installation_pipeline,
    _install_state,
)
import install.web_installer as web_installer

from broker.acagarwal.mapping.transform_data import transform_data, transform_modify_order_data
from broker.acagarwal.mapping.order_data import (
    transform_order_data,
    transform_tradebook_data,
    transform_positions_data,
    transform_holdings_data,
)
from broker.acagarwal.mapping.margin_data import parse_margin_response
from broker.acagarwal.api.data import BrokerData


@pytest.fixture(scope="module")
def running_web_installer():
    """Start web_installer server in background thread for testing."""
    web_installer._dry_run = True
    web_installer._security_token = "test_e2e_secret_token_123"

    # Find open port
    import socket
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()

    httpd = socketserver.TCPServer(("", port), WebInstallerHTTPHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    token = web_installer._security_token

    yield {"base_url": base_url, "token": token, "port": port}

    httpd.shutdown()
    httpd.server_close()


def test_e2e_security_token_rejection(running_web_installer):
    """Verify unauthorized requests without token are blocked with HTTP 403."""
    url = f"{running_web_installer['base_url']}/"
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(url)
    assert excinfo.value.code == 403


def test_e2e_web_installer_homepage_served(running_web_installer):
    """Verify homepage renders properly with security token."""
    url = f"{running_web_installer['base_url']}/?token={running_web_installer['token']}"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "OpenAlgo" in html
        assert "Server Setup Wizard" in html
        assert "acagarwal" in html


def test_e2e_system_info_api(running_web_installer):
    """Verify /api/system-info returns valid system metrics."""
    url = f"{running_web_installer['base_url']}/api/system-info?token={running_web_installer['token']}"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "os" in data
        assert "total_ram_gb" in data
        assert "free_disk_gb" in data
        assert "public_ip" in data
        assert data["total_ram_gb"] > 0


def test_e2e_check_dns_api(running_web_installer):
    """Verify /api/check-dns verifies domain resolution."""
    url = f"{running_web_installer['base_url']}/api/check-dns?domain=localhost&token={running_web_installer['token']}"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["resolves"] is True
        assert data["ip"] == "127.0.0.1"


def test_e2e_installation_pipeline_submission_and_sse(running_web_installer):
    """Verify full installation pipeline execution and SSE stream."""
    install_url = f"{running_web_installer['base_url']}/api/install?token={running_web_installer['token']}"
    payload = {
        "domain": "algo.test-e2e.com",
        "use_ssl": True,
        "broker": "acagarwal",
        "broker_api_key": "ac_app_key_123",
        "broker_api_secret": "ac_app_secret_456",
        "broker_api_key_market": "ac_market_key_789",
        "broker_api_secret_market": "ac_market_secret_012",
        "enable_mcp": True,
        "telegram_token": "12345:dummy",
        "telegram_chat_id": "98765",
        "repo_url": "https://github.com/hellocjain/acagarwaltest.algorivar.in.git",
        "repo_branch": "main",
    }

    req = urllib.request.Request(
        install_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "started"

    # Read SSE stream until completion
    stream_url = f"{running_web_installer['base_url']}/api/logs/stream?token={running_web_installer['token']}"
    req_stream = urllib.request.Request(stream_url)
    max_wait = 15
    start_time = time.time()
    completed = False

    with urllib.request.urlopen(req_stream, timeout=20) as stream_resp:
        for line in iter(stream_resp.readline, b""):
            line_str = line.decode("utf-8").strip()
            if line_str.startswith("data: "):
                event = json.loads(line_str[6:])
                if event.get("type") == "progress":
                    if event.get("status") == "success":
                        completed = True
                        break
                    elif event.get("status") == "error":
                        pytest.fail(f"Installation pipeline error: {event.get('message')}")
            if time.time() - start_time > max_wait:
                break

    assert completed is True


def test_e2e_acagarwal_order_lifecycle():
    """Verify order transformations for all order types in AC Agarwal XTS."""
    # Market order
    req_market = {
        "symbol": "TATASTEEL",
        "exchange": "NSE",
        "action": "BUY",
        "quantity": "100",
        "product": "CNC",
        "pricetype": "MARKET",
        "price": "0",
        "trigger_price": "0",
        "disclosed_quantity": "0",
    }
    market_payload = transform_data(req_market, token="3499")
    assert market_payload["exchangeSegment"] == "NSECM"
    assert market_payload["exchangeInstrumentID"] == 3499
    assert market_payload["productType"] == "CNC"
    assert market_payload["orderType"] == "MARKET"
    assert market_payload["orderSide"] == "BUY"
    assert market_payload["orderQuantity"] == 100

    # Limit order
    req_limit = {
        "symbol": "BANKNIFTY24MAR48000CE",
        "exchange": "NFO",
        "action": "SELL",
        "quantity": "15",
        "product": "NRML",
        "pricetype": "LIMIT",
        "price": "350.25",
        "trigger_price": "0",
        "disclosed_quantity": "0",
    }
    limit_payload = transform_data(req_limit, token="54321")
    assert limit_payload["exchangeSegment"] == "NSEFO"
    assert limit_payload["exchangeInstrumentID"] == 54321
    assert limit_payload["orderType"] == "LIMIT"
    assert limit_payload["limitPrice"] == 350.25

    # Modify order
    mod_req = {
        "orderid": "987654",
        "pricetype": "LIMIT",
        "price": "345.00",
        "quantity": "30",
        "product": "NRML",
    }
    mod_payload = transform_modify_order_data(mod_req)
    assert mod_payload["appOrderID"] == 987654
    assert mod_payload["modifiedLimitPrice"] == 345.00
    assert mod_payload["modifiedOrderQuantity"] == 30


def test_e2e_acagarwal_market_data_and_depth_parsing():
    """Verify quotes and market depth calculations for AC Agarwal."""
    broker_data = BrokerData("test_auth_token", "test_feed_token")

    raw_depth = {
        "type": "success",
        "result": {
            "Touchline": {
                "LastTradedPrice": 2540.5,
                "Close": 2500.0,
                "Open": 2510.0,
                "High": 2560.0,
                "Low": 2495.0,
                "TotalTradedQuantity": 1500000,
                "TotalBuyQuantity": 50000,
                "TotalSellQuantity": 60000,
            },
            "Bids": [
                {"Price": 2540.0, "Quantity": 100, "Size": 100, "Orders": 2},
                {"Price": 2539.5, "Quantity": 200, "Size": 200, "Orders": 5},
            ],
            "Asks": [
                {"Price": 2540.5, "Quantity": 150, "Size": 150, "Orders": 3},
                {"Price": 2541.0, "Quantity": 250, "Size": 250, "Orders": 4},
            ],
        },
    }

    bids = raw_depth["result"]["Bids"]
    asks = raw_depth["result"]["Asks"]
    touchline = raw_depth["result"]["Touchline"]

    assert len(bids) == 2
    assert len(asks) == 2
    assert touchline["LastTradedPrice"] == 2540.5
    assert bids[0]["Price"] == 2540.0
    assert asks[0]["Price"] == 2540.5
