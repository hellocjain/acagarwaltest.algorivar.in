"""Unit tests for OpenAlgo One-Click Web Installer."""

import json
import os
import pytest
from install.web_installer import (
    XTS_BROKERS,
    ALL_BROKERS,
    get_system_diagnostics,
    check_domain_dns,
    wait_for_dpkg_lock,
    get_default_repo_url,
    run_installation_pipeline,
    _install_state,
    stream_log,
)
import install.web_installer as web_installer


def test_xts_brokers_contains_acagarwal():
    assert "acagarwal" in XTS_BROKERS
    broker_codes = [code for code, name in ALL_BROKERS]
    assert "acagarwal" in broker_codes
    assert "zerodha" in broker_codes
    assert "angel" in broker_codes


def test_system_diagnostics():
    diag = get_system_diagnostics()
    assert "os" in diag
    assert "total_ram_gb" in diag
    assert "free_disk_gb" in diag
    assert "cpu_cores" in diag
    assert "public_ip" in diag
    assert isinstance(diag["cpu_cores"], int)
    assert diag["total_ram_gb"] > 0


def test_check_domain_dns_empty():
    res = check_domain_dns("")
    assert res["resolves"] is False
    assert res["matches_server"] is False


def test_check_domain_dns_localhost():
    res = check_domain_dns("localhost")
    assert res["resolves"] is True
    assert res["ip"] == "127.0.0.1"


def test_wait_for_dpkg_lock_dry_run():
    web_installer._dry_run = True
    wait_for_dpkg_lock()


def test_get_default_repo_url_env_override(monkeypatch):
    monkeypatch.setenv("OPENALGO_REPO_URL", "https://github.com/mycustomuser/myopenalgo.git")
    url = get_default_repo_url()
    assert url == "https://github.com/mycustomuser/myopenalgo.git"


def test_dry_run_installation_pipeline_with_custom_repo():
    web_installer._dry_run = True

    config = {
        "domain": "algo.testdomain.com",
        "use_ssl": True,
        "broker": "acagarwal",
        "broker_api_key": "test_interactive_key",
        "broker_api_secret": "test_interactive_secret",
        "broker_api_key_market": "test_market_key",
        "broker_api_secret_market": "test_market_secret",
        "enable_mcp": True,
        "telegram_token": "12345:dummy",
        "telegram_chat_id": "98765",
        "repo_url": "https://github.com/mycustomuser/myopenalgo.git",
        "repo_branch": "feature/acagarwal",
    }

    run_installation_pipeline(config)

    assert _install_state["status"] == "success"
    assert _install_state["stage"] == 7
    assert "summary" in _install_state
    assert _install_state["summary"]["broker"] == "acagarwal"
    assert "acagarwal/callback" in _install_state["summary"]["redirect_url"]
