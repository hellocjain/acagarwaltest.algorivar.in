#!/usr/bin/env python3
"""
OpenAlgo One-Click Web Installer for Ubuntu/Debian Servers.
Zero external dependencies - runs on Python 3 standard library.
"""

import argparse
import cgi
import http.server
import json
import os
import queue
import re
import secrets
import shutil
import socket
import socketserver
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

INSTALL_DIR = "/var/python/openalgo"
DEFAULT_PORT = 5050


def get_default_repo_url() -> str:
    """Detect repo URL from environment, git origin, or default."""
    if "OPENALGO_REPO_URL" in os.environ and os.environ["OPENALGO_REPO_URL"].strip():
        return os.environ["OPENALGO_REPO_URL"].strip()
    try:
        res = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "https://github.com/hellocjain/acagarwaltest.algorivar.in.git"


REPO_URL = get_default_repo_url()

XTS_BROKERS = [
    "acagarwal",
    "fivepaisaxts",
    "compositedge",
    "ibulls",
    "iifl",
    "jainamxts",
    "rmoney",
    "wisdom",
]

ALL_BROKERS = [
    ("acagarwal", "AC Agarwal (Symphony XTS)"),
    ("zerodha", "Zerodha (Kite Connect)"),
    ("angel", "AngelOne (SmartAPI)"),
    ("dhan", "Dhan (Live)"),
    ("fyers", "Fyers API v3"),
    ("groww", "Groww API"),
    ("upstox", "Upstox API v2"),
    ("kotak", "Kotak Securities (Neo)"),
    ("motilal", "Motilal Oswal"),
    ("shoonya", "Shoonya (Finvasia)"),
    ("flattrade", "FlatTrade"),
    ("aliceblue", "AliceBlue"),
    ("fivepaisa", "5Paisa (Standard)"),
    ("fivepaisaxts", "5Paisa (XTS)"),
    ("compositedge", "CompositeEdge (XTS)"),
    ("rmoney", "RMoney (XTS)"),
    ("jainamxts", "Jainam (XTS)"),
    ("iifl", "IIFL (XTS)"),
    ("iiflcapital", "IIFL Capital"),
    ("ibulls", "IndiaBulls (XTS)"),
    ("wisdom", "Wisdom Capital (XTS)"),
    ("pocketful", "Pocketful"),
    ("indmoney", "IndMoney"),
    ("definedge", "Definedge"),
    ("firstock", "Firstock"),
    ("mstock", "Mstock (Mirae)"),
    ("nubra", "Nubra"),
    ("paytm", "Paytm Money"),
    ("samco", "Samco"),
    ("tradejini", "Tradejini"),
    ("tradesmart", "TradeSmart"),
    ("arrow", "Arrow"),
    ("zebu", "Zebu"),
    ("dhan_sandbox", "Dhan (Sandbox Paper Trading)"),
    ("deltaexchange", "Delta Exchange (Crypto)"),
]

# Global installation state
_install_state = {
    "status": "idle",  # idle, running, success, error
    "stage": 0,
    "total_stages": 7,
    "message": "",
    "error": None,
    "completed_url": None,
    "summary": {},
}
_log_queue = queue.Queue()
_security_token = ""
_dry_run = False


def get_public_ip() -> str:
    """Detect server public IPv4 address."""
    for service in [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://checkip.amazonaws.com",
    ]:
        try:
            req = urllib.request.Request(service, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                ip = resp.read().decode("utf-8").strip()
                if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
                    return ip
        except Exception:
            continue
    return "127.0.0.1"


def get_system_diagnostics() -> Dict[str, Any]:
    """Gather server hardware and OS metrics."""
    os_info = "Linux (Ubuntu/Debian)"
    if os.path.exists("/etc/os-release"):
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    os_info = line.split("=", 1)[1].strip().strip('"')
                    break

    # RAM in GB
    total_ram_gb = 1.0
    free_ram_gb = 1.0
    if os.path.exists("/proc/meminfo"):
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    mem[parts[0].strip()] = parts[1].strip()
        if "MemTotal" in mem:
            total_kb = int(mem["MemTotal"].split()[0])
            total_ram_gb = round(total_kb / 1024 / 1024, 2)
        if "MemAvailable" in mem:
            avail_kb = int(mem["MemAvailable"].split()[0])
            free_ram_gb = round(avail_kb / 1024 / 1024, 2)

    # Swap metrics
    swap_total_gb = 0.0
    if os.path.exists("/proc/meminfo"):
        if "SwapTotal" in mem:
            swap_kb = int(mem["SwapTotal"].split()[0])
            swap_total_gb = round(swap_kb / 1024 / 1024, 2)

    # Free Disk
    disk = shutil.disk_usage("/")
    free_disk_gb = round(disk.free / (1024**3), 2)
    total_disk_gb = round(disk.total / (1024**3), 2)

    # CPU Cores
    cpu_cores = os.cpu_count() or 1

    return {
        "os": os_info,
        "total_ram_gb": total_ram_gb,
        "free_ram_gb": free_ram_gb,
        "swap_total_gb": swap_total_gb,
        "free_disk_gb": free_disk_gb,
        "total_disk_gb": total_disk_gb,
        "cpu_cores": cpu_cores,
        "public_ip": get_public_ip(),
        "is_root": os.geteuid() == 0 if hasattr(os, "geteuid") else False,
    }


def is_cloudflare_ip(ip: str) -> bool:
    """Check if resolved IP belongs to known Cloudflare proxy ranges."""
    try:
        parts = [int(x) for x in ip.split(".")]
        if len(parts) == 4:
            if parts[0] == 104 and 16 <= parts[1] <= 31:
                return True
            if parts[0] == 172 and 64 <= parts[1] <= 71:
                return True
            if parts[0] == 108 and parts[1] == 162:
                return True
            if parts[0] == 162 and parts[1] == 158:
                return True
            if parts[0] == 198 and parts[1] == 41:
                return True
            if parts[0] == 197 and parts[1] == 234:
                return True
            if parts[0] == 188 and parts[1] == 114:
                return True
    except Exception:
        pass
    return False


def check_domain_dns(domain: str) -> Dict[str, Any]:
    """Check if domain resolves to this server's public IP."""
    if not domain:
        return {"resolves": False, "ip": "", "matches_server": False, "is_cloudflare": False}
    pub_ip = get_public_ip()
    try:
        resolved_ip = socket.gethostbyname(domain)
        is_cf = is_cloudflare_ip(resolved_ip)
        matches = (resolved_ip == pub_ip) or is_cf
        return {
            "resolves": True,
            "ip": resolved_ip,
            "server_ip": pub_ip,
            "matches_server": matches,
            "is_cloudflare": is_cf,
        }
    except Exception:
        return {
            "resolves": False,
            "ip": "",
            "server_ip": pub_ip,
            "matches_server": False,
            "is_cloudflare": False,
        }


def stream_log(msg: str, level: str = "INFO"):
    """Put log line into streaming queue."""
    ts = time.strftime("%H:%M:%S")
    entry = {"timestamp": ts, "level": level, "message": msg}
    _log_queue.put(entry)
    print(f"[{ts}] [{level}] {msg}")


def wait_for_dpkg_lock():
    """Wait for apt/dpkg lock on freshly booted Ubuntu systems."""
    if _dry_run:
        return
    lock_files = [
        "/var/lib/dpkg/lock-frontend",
        "/var/lib/dpkg/lock",
        "/var/lib/apt/lists/lock",
    ]
    max_wait = 180  # 3 minutes
    waited = 0
    while waited < max_wait:
        locked = False
        for lf in lock_files:
            if os.path.exists(lf):
                try:
                    res = subprocess.run(
                        ["fuser", lf],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    if res.returncode == 0:
                        locked = True
                        break
                except Exception:
                    pass
        if not locked:
            break
        if waited == 0:
            stream_log(
                "Ubuntu unattended-upgrades is running in background. Waiting for package manager lock to clear...",
                "INFO",
            )
        time.sleep(5)
        waited += 5

    if waited >= max_wait:
        stream_log("Lock wait timeout reached. Freeing lock files...", "WARN")
        subprocess.run(["killall", "-9", "unattended-upgrade", "apt", "apt-get", "dpkg"], stderr=subprocess.DEVNULL)
        for lf in lock_files:
            try:
                if os.path.exists(lf):
                    os.remove(lf)
            except Exception:
                pass


def execute_cmd(cmd: List[str] | str, desc: str, cwd: Optional[str] = None) -> bool:
    """Execute command and stream stdout/stderr live."""
    stream_log(f"Starting: {desc}", "STEP")
    if _dry_run:
        stream_log(f"[DRY-RUN] Executing: {cmd}", "INFO")
        time.sleep(0.3)
        return True

    try:
        proc = subprocess.Popen(
            cmd,
            shell=isinstance(cmd, str),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=cwd,
        )
        for line in iter(proc.stdout.readline, ""):
            line = line.strip()
            if line:
                stream_log(line, "EXEC")
        proc.stdout.close()
        rc = proc.wait()
        if rc == 0:
            stream_log(f"Completed successfully: {desc}", "SUCCESS")
            return True
        else:
            stream_log(f"Command failed (exit code {rc}): {desc}", "ERROR")
            return False
    except Exception as e:
        stream_log(f"Exception while executing {desc}: {e}", "ERROR")
        return False


def run_installation_pipeline(config: Dict[str, Any]):
    """Execute complete hardened Ubuntu Server installation pipeline."""
    global _install_state

    _install_state["status"] = "running"
    _install_state["error"] = None
    _install_state["stage"] = 1
    _install_state["message"] = "Starting installation..."

    diag = get_system_diagnostics()

    domain = config.get("domain", "").strip()
    use_ssl = config.get("use_ssl", True)
    broker = config.get("broker", "acagarwal").strip().lower()
    broker_api_key = config.get("broker_api_key", "").strip()
    broker_api_secret = config.get("broker_api_secret", "").strip()
    broker_api_key_market = config.get("broker_api_key_market", "").strip()
    broker_api_secret_market = config.get("broker_api_secret_market", "").strip()
    enable_mcp = config.get("enable_mcp", False)
    telegram_token = config.get("telegram_token", "").strip()
    telegram_chat_id = config.get("telegram_chat_id", "").strip()

    repo_url = config.get("repo_url", "").strip() or REPO_URL
    repo_branch = config.get("repo_branch", "").strip() or "main"

    app_key = config.get("app_key") or secrets.token_hex(32)
    api_key_pepper = config.get("api_key_pepper") or secrets.token_hex(32)
    import base64

    fernet_salt = config.get("fernet_salt") or base64.urlsafe_b64encode(
        secrets.token_bytes(16)
    ).decode("utf-8")

    stream_log(f"Git Repository: {repo_url} (Branch: {repo_branch})", "CONFIG")
    stream_log(f"Target Domain: {domain or 'IP-only'}", "CONFIG")
    stream_log(f"Selected Broker: {broker}", "CONFIG")
    stream_log(f"SSL Enabled: {use_ssl}", "CONFIG")

    # STAGE 1: Timezone, Package Locks & Base System Dependencies
    _install_state["stage"] = 1
    _install_state["message"] = "Configuring timezone, package locks, and installing base system packages..."

    # Configure Timezone to IST
    execute_cmd("timedatectl set-timezone Asia/Kolkata || true", "Setting server timezone to Asia/Kolkata (IST)")

    # Wait for background apt locks
    wait_for_dpkg_lock()

    sys_packages = (
        "apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y "
        "git curl wget nginx certbot python3-certbot-nginx build-essential sqlite3 chromium-browser ufw || "
        "apt-get install -y git curl wget nginx certbot python3-certbot-nginx build-essential sqlite3 chromium"
    )
    if not execute_cmd(sys_packages, "Installing Nginx, Certbot, Git, and system libraries"):
        _install_state["status"] = "error"
        _install_state["error"] = "Failed to install required system packages via apt-get."
        return

    # Check and configure 2GB swap space if total swap < 2GB
    stream_log("Checking server swap space...", "INFO")
    swap_cmd = (
        "SWAP_KB=$(grep SwapTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 0); "
        "if [ \"$SWAP_KB\" -lt 2000000 ] && [ ! -f /swapfile ]; then "
        "(fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none) && "
        "chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && "
        "grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab; "
        "sysctl vm.swappiness=10 || true; "
        "fi"
    )
    execute_cmd(swap_cmd, "Configuring 2GB persistent swap space")

    # STAGE 2: Install uv Python Package Manager
    _install_state["stage"] = 2
    _install_state["message"] = "Installing uv Python package manager..."
    install_uv_cmd = (
        "curl -LsSf https://astral.sh/uv/install.sh | sh && "
        "cp /root/.local/bin/uv /usr/local/bin/uv 2>/dev/null || "
        "cp $HOME/.local/bin/uv /usr/local/bin/uv 2>/dev/null || true"
    )
    if not execute_cmd(install_uv_cmd, "Installing Astral uv"):
        stream_log("Astral uv direct installer fallback to snap", "WARN")
        execute_cmd("snap install astral-uv --classic || true", "Installing uv via snap")

    # STAGE 3: Clone / Setup OpenAlgo
    _install_state["stage"] = 3
    _install_state["message"] = f"Cloning OpenAlgo repository from {repo_url} ({repo_branch})..."
    if not _dry_run:
        os.makedirs("/var/python", exist_ok=True)

    if os.path.exists(INSTALL_DIR):
        stream_log(f"Directory {INSTALL_DIR} already exists. Updating repo...", "INFO")
        clone_cmd = f"cd {INSTALL_DIR} && git remote set-url origin {repo_url} 2>/dev/null || true && git fetch --all && (git checkout {repo_branch} 2>/dev/null || git checkout -b {repo_branch} origin/{repo_branch}) && git reset --hard origin/{repo_branch}"
    else:
        clone_cmd = f"git clone -b {repo_branch} {repo_url} {INSTALL_DIR}"

    if not execute_cmd(clone_cmd, f"Cloning OpenAlgo from {repo_url}"):
        _install_state["status"] = "error"
        _install_state["error"] = f"Failed to clone OpenAlgo repo into {INSTALL_DIR}."
        return

    # Create db and logs directories
    if not _dry_run:
        os.makedirs(f"{INSTALL_DIR}/db", exist_ok=True)
        os.makedirs(f"{INSTALL_DIR}/logs", exist_ok=True)

    # STAGE 4: Build Python Environment
    _install_state["stage"] = 4
    _install_state["message"] = "Creating virtual environment and installing dependencies via uv sync..."
    uv_sync_cmd = f"cd {INSTALL_DIR} && uv sync"
    if not execute_cmd(uv_sync_cmd, "Installing Python 3.12 dependencies with uv"):
        _install_state["status"] = "error"
        _install_state["error"] = "Failed to sync Python environment via uv."
        return

    # STAGE 5: Write .env Configuration
    _install_state["stage"] = 5
    _install_state["message"] = "Generating production configuration .env..."

    redirect_url = (
        f"https://{domain}/{broker}/callback"
        if domain and use_ssl
        else f"http://{domain or diag['public_ip']}:5000/{broker}/callback"
    )

    host_server_val = (
        f"https://{domain}"
        if domain and use_ssl
        else (f"http://{domain}" if domain else f"http://{diag['public_ip']}:5000")
    )
    websocket_url_val = (
        f"wss://{domain}/ws"
        if domain and use_ssl
        else (f"ws://{domain}/ws" if domain else "ws://127.0.0.1:8765")
    )
    mcp_url_val = f"https://{domain}/mcp" if domain and enable_mcp else ""

    valid_brokers_str = "acagarwal,fivepaisa,fivepaisaxts,aliceblue,angel,arrow,compositedge,definedge,deltaexchange,dhan,dhan_sandbox,firstock,flattrade,fyers,groww,hdfcsecurities,hdfcsky,ibulls,iifl,iiflcapital,indmoney,jainamxts,kotak,motilal,mstock,nubra,paytm,pocketful,rmoney,samco,shoonya,tradejini,tradesmart,upstox,wisdom,zebu,zerodha"

    sample_env_path = os.path.join(INSTALL_DIR, ".sample.env")
    base_content = ""
    if os.path.exists(sample_env_path):
        try:
            with open(sample_env_path, "r") as sf:
                base_content = sf.read()
        except Exception:
            base_content = ""

    if base_content:
        env_content = base_content
        replacements = {
            "OPENALGO_PLACEHOLDER_APP_KEY_REGENERATE_BEFORE_USE": app_key,
            "OPENALGO_PLACEHOLDER_API_KEY_PEPPER_REGENERATE_BEFORE_USE": api_key_pepper,
            "OPENALGO_PLACEHOLDER_FERNET_SALT_REGENERATE_BEFORE_USE": fernet_salt,
            "YOUR_BROKER_API_KEY": broker_api_key,
            "YOUR_BROKER_API_SECRET": broker_api_secret,
            "YOUR_BROKER_MARKET_API_KEY": broker_api_key_market,
            "YOUR_BROKER_MARKET_API_SECRET": broker_api_secret_market,
            "http://127.0.0.1:5000/<broker>/callback": redirect_url,
        }
        for placeholder, val in replacements.items():
            env_content = env_content.replace(placeholder, val)

        env_content = re.sub(
            r"^HOST_SERVER\s*=.*$",
            f"HOST_SERVER = '{host_server_val}'",
            env_content,
            flags=re.MULTILINE,
        )
        env_content = re.sub(
            r"^WEBSOCKET_URL\s*=.*$",
            f"WEBSOCKET_URL = '{websocket_url_val}'",
            env_content,
            flags=re.MULTILINE,
        )
        env_content = re.sub(
            r"^REDIRECT_URL\s*=.*$",
            f"REDIRECT_URL = '{redirect_url}'",
            env_content,
            flags=re.MULTILINE,
        )

        if telegram_token:
            env_content = re.sub(
                r"TELEGRAM_BOT_TOKEN\s*=\s*'.*?'",
                f"TELEGRAM_BOT_TOKEN = '{telegram_token}'",
                env_content,
            )
        if telegram_chat_id:
            env_content = re.sub(
                r"TELEGRAM_CHAT_ID\s*=\s*'.*?'",
                f"TELEGRAM_CHAT_ID = '{telegram_chat_id}'",
                env_content,
            )
        if enable_mcp:
            env_content = re.sub(
                r"MCP_HTTP_ENABLED\s*=\s*'.*?'", "MCP_HTTP_ENABLED = 'True'", env_content
            )
            if mcp_url_val:
                env_content = re.sub(
                    r"MCP_PUBLIC_URL\s*=\s*'.*?'",
                    f"MCP_PUBLIC_URL = '{mcp_url_val}'",
                    env_content,
                )
    else:
        env_content = f"""# OpenAlgo Production Environment Configuration
ENV_CONFIG_VERSION = '1.0.7'
BROKER_API_KEY = '{broker_api_key}'
BROKER_API_SECRET = '{broker_api_secret}'
BROKER_API_KEY_MARKET = '{broker_api_key_market}'
BROKER_API_SECRET_MARKET = '{broker_api_secret_market}'
REDIRECT_URL = '{redirect_url}'
VALID_BROKERS = '{valid_brokers_str}'
APP_KEY = '{app_key}'
API_KEY_PEPPER = '{api_key_pepper}'
FERNET_SALT = '{fernet_salt}'
HOST_SERVER = '{host_server_val}'
FLASK_HOST_IP = '127.0.0.1'
FLASK_PORT = '5000'
FLASK_DEBUG = 'False'
FLASK_ENV = 'production'
WEBSOCKET_HOST = '127.0.0.1'
WEBSOCKET_PORT = '8765'
WEBSOCKET_URL = '{websocket_url_val}'
ZMQ_HOST = '127.0.0.1'
ZMQ_PORT = '5555'
DATABASE_URL = 'sqlite:///db/openalgo.db'
LATENCY_DATABASE_URL = 'sqlite:///db/latency.db'
LOGS_DATABASE_URL = 'sqlite:///db/logs.db'
HEALTH_DATABASE_URL = 'sqlite:///db/health.db'
SANDBOX_DATABASE_URL = 'sqlite:///db/sandbox.db'
HISTORIFY_DATABASE_URL = 'db/historify.duckdb'
TELEGRAM_BOT_TOKEN = '{telegram_token}'
TELEGRAM_CHAT_ID = '{telegram_chat_id}'
MCP_HTTP_ENABLED = '{str(enable_mcp)}'
MCP_PUBLIC_URL = '{mcp_url_val}'
"""

    env_path = os.path.join(INSTALL_DIR, ".env")
    if _dry_run:
        stream_log(f"[DRY-RUN] Would write production .env to {env_path}", "INFO")
    else:
        try:
            with open(env_path, "w") as f:
                f.write(env_content)
            os.chmod(env_path, 0o600)
            stream_log(f"Successfully wrote {env_path}", "SUCCESS")
        except Exception as e:
            stream_log(f"Failed to write .env file: {e}", "ERROR")

    # STAGE 6: Hardened Nginx Reverse Proxy & SSL
    _install_state["stage"] = 6
    _install_state["message"] = "Configuring hardened Nginx reverse proxy and SSL..."

    server_name = domain if domain else "_"
    nginx_conf = f"""# OpenAlgo Production Nginx VirtualHost
server {{
    listen 80;
    listen [::]:80;
    server_name {server_name};

    # OPENALGO_WEBHOOK_LOG_GUARD: Suppress URL secrets from leaking into access logs
    set $openalgo_loggable 1;
    if ($uri ~ ^/(strategy|flow|chartink)/webhook/) {{
        set $openalgo_loggable 0;
    }}
    access_log /var/log/nginx/openalgo_access.log combined if=$openalgo_loggable;

    client_max_body_size 50M;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    location / {{
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }}

    location = /ws {{
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        proxy_buffering off;
    }}

    location /ws/ {{
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        proxy_buffering off;
    }}
}}
"""
    nginx_available = "/etc/nginx/sites-available/openalgo.conf"
    nginx_enabled = "/etc/nginx/sites-enabled/openalgo.conf"
    default_enabled = "/etc/nginx/sites-enabled/default"

    if _dry_run:
        stream_log(f"[DRY-RUN] Would configure Nginx VirtualHost at {nginx_available}", "INFO")
    else:
        try:
            with open(nginx_available, "w") as f:
                f.write(nginx_conf)
            if os.path.exists(default_enabled):
                os.remove(default_enabled)
            if not os.path.exists(nginx_enabled):
                os.symlink(nginx_available, nginx_enabled)
            stream_log("Nginx configuration written and linked", "SUCCESS")
        except Exception as e:
            stream_log(f"Error configuring Nginx: {e}", "ERROR")

    execute_cmd("nginx -t && systemctl reload nginx", "Testing and reloading Nginx")

    # Certbot SSL with DNS check and Graceful Fallback
    ssl_acquired = False
    if domain and use_ssl:
        dns_res = check_domain_dns(domain)
        if dns_res["resolves"]:
            stream_log(f"Requesting Let's Encrypt SSL certificate for {domain}...", "INFO")
            certbot_cmd = f"certbot --nginx -d {domain} --non-interactive --agree-tos --register-unsafely-without-email --redirect"
            ssl_acquired = execute_cmd(certbot_cmd, f"Acquiring SSL for {domain}")
        else:
            stream_log(
                f"Notice: Domain {domain} does not resolve to this server IP ({diag['public_ip']}) yet. Running over HTTP; SSL can be enabled after DNS propagates.",
                "WARN",
            )

    # Reconcile .env with actual SSL status
    if domain and not _dry_run:
        actual_proto = "https" if (use_ssl and ssl_acquired) else "http"
        actual_ws_proto = "wss" if (use_ssl and ssl_acquired) else "ws"
        actual_host = f"{actual_proto}://{domain}"
        actual_ws = f"{actual_ws_proto}://{domain}/ws"
        actual_redirect = f"{actual_proto}://{domain}/{broker}/callback"

        try:
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    cur_env = f.read()
                cur_env = re.sub(r"^HOST_SERVER\s*=.*$", f"HOST_SERVER = '{actual_host}'", cur_env, flags=re.MULTILINE)
                cur_env = re.sub(r"^WEBSOCKET_URL\s*=.*$", f"WEBSOCKET_URL = '{actual_ws}'", cur_env, flags=re.MULTILINE)
                cur_env = re.sub(r"^REDIRECT_URL\s*=.*$", f"REDIRECT_URL = '{actual_redirect}'", cur_env, flags=re.MULTILINE)
                with open(env_path, "w") as f:
                    f.write(cur_env)
                os.chmod(env_path, 0o600)
                stream_log(f"Reconciled .env: HOST_SERVER={actual_host}, WEBSOCKET_URL={actual_ws}", "INFO")
        except Exception as e:
            stream_log(f"Notice: Could not reconcile .env SSL state: {e}", "WARN")

    # STAGE 7: Systemd Service & Startup
    _install_state["stage"] = 7
    _install_state["message"] = "Creating and starting openalgo systemd service..."

    systemd_unit = f"""[Unit]
Description=OpenAlgo Algorithmic Trading Platform
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={INSTALL_DIR}
Environment="PATH={INSTALL_DIR}/.venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart={INSTALL_DIR}/.venv/bin/python {INSTALL_DIR}/app.py
Restart=always
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
"""
    service_path = "/etc/systemd/system/openalgo.service"
    if _dry_run:
        stream_log(f"[DRY-RUN] Would create systemd service at {service_path}", "INFO")
    else:
        try:
            with open(service_path, "w") as f:
                f.write(systemd_unit)
            stream_log(f"Wrote systemd unit to {service_path}", "SUCCESS")
        except Exception as e:
            stream_log(f"Failed to write systemd unit: {e}", "ERROR")

    execute_cmd(
        "systemctl daemon-reload && systemctl enable openalgo && systemctl restart openalgo",
        "Starting openalgo service on port 5000",
    )

    # Final summary & completion
    completed_url = (
        f"https://{domain}" if domain and ssl_acquired else f"http://{domain or diag['public_ip']}"
    )
    _install_state["completed_url"] = completed_url
    _install_state["status"] = "success"
    _install_state["message"] = f"OpenAlgo installed successfully! Ready at {completed_url}"
    _install_state["summary"] = {
        "dashboard_url": completed_url,
        "broker": broker,
        "redirect_url": redirect_url,
        "app_key": app_key,
        "mcp_url": f"https://{domain}/mcp" if enable_mcp and domain else "",
    }
    stream_log(f"🎉 OpenAlgo installation complete! Access your dashboard at: {completed_url}", "SUCCESS")

    def auto_shutdown():
        time.sleep(3.0)
        print("\n" + "=" * 65)
        print("🎉 OpenAlgo is now live and running in the background!")
        print(f"👉 Access your dashboard at: {completed_url}")
        print("=" * 65 + "\n")
        os._exit(0)

    if not _dry_run:
        threading.Thread(target=auto_shutdown, daemon=True).start()


HTML_PAGE = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OpenAlgo One-Click Server Installer</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: { 50: '#f0fdf4', 500: '#22c55e', 600: '#16a34a', 700: '#15803d' },
            darkbg: '#0f172a',
            darkcard: '#1e293b'
          }
        }
      }
    }
  </script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    .glass { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.08); }
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: #0f172a; }
    ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
  </style>
</head>
<body class="bg-darkbg text-slate-100 min-h-screen flex flex-col font-sans antialiased selection:bg-brand-500 selection:text-white">

  <!-- Header -->
  <header class="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur sticky top-0 z-50">
    <div class="max-w-6xl mx-auto px-4 py-3.5 flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 to-emerald-400 flex items-center justify-center shadow-lg shadow-brand-500/20">
          <i class="fa-solid fa-chart-line text-white text-xl"></i>
        </div>
        <div>
          <h1 class="font-bold text-lg text-white leading-tight">OpenAlgo</h1>
          <p class="text-xs text-slate-400">Server Setup Wizard</p>
        </div>
      </div>
      <div class="flex items-center space-x-2 text-xs">
        <span class="px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono flex items-center">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse mr-1.5"></span>
          Ubuntu Auto-Installer
        </span>
      </div>
    </div>
  </header>

  <main class="max-w-6xl mx-auto px-4 py-8 flex-1 w-full grid grid-cols-1 lg:grid-cols-12 gap-8">

    <!-- Left Column: Form & Config -->
    <div class="lg:col-span-7 space-y-6" id="setupFormContainer">

      <!-- Server Health Metrics Banner -->
      <div class="glass rounded-2xl p-5" id="diagBox">
        <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center">
          <i class="fa-solid fa-server mr-2 text-brand-500"></i> Host Environment
        </h3>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center" id="diagGrid">
          <div class="bg-slate-800/60 p-2.5 rounded-xl border border-slate-700/50">
            <span class="text-xs text-slate-400 block">OS</span>
            <span class="font-semibold text-sm text-slate-200" id="diagOS">DIAG_OS_PLACEHOLDER</span>
          </div>
          <div class="bg-slate-800/60 p-2.5 rounded-xl border border-slate-700/50">
            <span class="text-xs text-slate-400 block">RAM</span>
            <span class="font-semibold text-sm text-slate-200" id="diagRAM">DIAG_RAM_PLACEHOLDER</span>
          </div>
          <div class="bg-slate-800/60 p-2.5 rounded-xl border border-slate-700/50">
            <span class="text-xs text-slate-400 block">Free Disk</span>
            <span class="font-semibold text-sm text-slate-200" id="diagDisk">DIAG_DISK_PLACEHOLDER</span>
          </div>
          <div class="bg-slate-800/60 p-2.5 rounded-xl border border-slate-700/50">
            <span class="text-xs text-slate-400 block">Public IP</span>
            <span class="font-semibold text-sm text-emerald-400 font-mono" id="diagIP">DIAG_IP_PLACEHOLDER</span>
          </div>
        </div>
      </div>

      <!-- Main Form -->
      <form id="installForm" class="space-y-6">

        <!-- 1. Domain & Network -->
        <div class="glass rounded-2xl p-6">
          <div class="flex items-center space-x-3 mb-4">
            <div class="w-7 h-7 rounded-lg bg-blue-500/20 text-blue-400 flex items-center justify-center font-bold text-sm">1</div>
            <h2 class="text-base font-semibold text-white">Domain & SSL Configuration</h2>
          </div>

          <div class="space-y-4">
            <div>
              <label class="block text-xs font-medium text-slate-300 mb-1.5">Domain Name (Recommended)</label>
              <div class="relative">
                <input type="text" id="domain" name="domain" placeholder="algo.yourdomain.com"
                  oninput="updateCallbackPreview(); debounceDnsCheck();"
                  class="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 transition">
              </div>
              <div id="dnsStatus" class="text-xs mt-1.5 hidden flex items-center"></div>
              <p class="text-xs text-slate-400 mt-1">Make sure an DNS <b>A record</b> for this domain points to your server's Public IP.</p>
            </div>

            <div class="flex items-center justify-between pt-2 border-t border-slate-800">
              <div>
                <span class="text-sm font-medium text-slate-200 block">Automatic Let's Encrypt SSL</span>
                <span class="text-xs text-slate-400">Provisions free HTTPS SSL certificate with auto-renewal</span>
              </div>
              <label class="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" id="use_ssl" name="use_ssl" checked onchange="updateCallbackPreview()" class="sr-only peer">
                <div class="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand-600"></div>
              </label>
            </div>
          </div>
        </div>

        <!-- 2. Broker Configuration -->
        <div class="glass rounded-2xl p-6">
          <div class="flex items-center space-x-3 mb-4">
            <div class="w-7 h-7 rounded-lg bg-brand-500/20 text-brand-400 flex items-center justify-center font-bold text-sm">2</div>
            <h2 class="text-base font-semibold text-white">Broker Selection & Credentials</h2>
          </div>

          <div class="space-y-4">
            <div>
              <label class="block text-xs font-medium text-slate-300 mb-1.5">Choose Broker</label>
              <select id="broker" name="broker" onchange="updateXtsVisibility(); updateCallbackPreview();" class="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 transition">
BROKER_OPTIONS_PLACEHOLDER
              </select>
            </div>

            <!-- Standard Interactive API Credentials -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-xs font-medium text-slate-300 mb-1.5">Interactive API Key (AppKey)</label>
                <input type="text" id="broker_api_key" name="broker_api_key" placeholder="Enter API Key"
                  class="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 font-mono transition">
              </div>
              <div>
                <label class="block text-xs font-medium text-slate-300 mb-1.5">Interactive API Secret</label>
                <input type="password" id="broker_api_secret" name="broker_api_secret" placeholder="Enter API Secret"
                  class="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 font-mono transition">
              </div>
            </div>

            <!-- XTS Specific Market Data Credentials (Conditional) -->
            <div id="xtsCredentialsSection" class="p-4 rounded-xl bg-slate-900/90 border border-amber-500/30 space-y-3">
              <div class="flex items-center text-amber-400 text-xs font-semibold">
                <i class="fa-solid fa-bolt mr-2"></i> XTS Dual-Authentication Required
              </div>
              <p class="text-xs text-slate-400">This broker uses separate credentials for real-time market data streaming.</p>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label class="block text-xs font-medium text-slate-300 mb-1">Market Data API Key</label>
                  <input type="text" id="broker_api_key_market" name="broker_api_key_market" placeholder="Market Data AppKey"
                    class="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 font-mono focus:border-brand-500">
                </div>
                <div>
                  <label class="block text-xs font-medium text-slate-300 mb-1">Market Data API Secret</label>
                  <input type="password" id="broker_api_secret_market" name="broker_api_secret_market" placeholder="Market Data Secret"
                    class="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 font-mono focus:border-brand-500">
                </div>
              </div>
            </div>

            <!-- Generated Callback URL helper -->
            <div class="p-3 bg-slate-900/60 rounded-xl border border-slate-800 flex items-center justify-between text-xs">
              <div class="overflow-hidden mr-2">
                <span class="text-slate-400 block mb-0.5">Your Broker Redirect / Callback URL:</span>
                <span id="callbackPreview" class="font-mono text-emerald-400 truncate block">https://algo.yourdomain.com/acagarwal/callback</span>
              </div>
              <button type="button" id="copyBtn" onclick="copyCallbackUrl()" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg border border-slate-700 flex items-center shrink-0 transition">
                <i class="fa-regular fa-copy mr-1.5"></i> Copy
              </button>
            </div>
          </div>
        </div>

        <!-- 3. Remote MCP & Security -->
        <div class="glass rounded-2xl p-6">
          <div class="flex items-center space-x-3 mb-4">
            <div class="w-7 h-7 rounded-lg bg-purple-500/20 text-purple-400 flex items-center justify-center font-bold text-sm">3</div>
            <h2 class="text-base font-semibold text-white">Security & Features</h2>
          </div>

          <div class="space-y-4">
            <div class="flex items-center justify-between pb-3 border-b border-slate-800">
              <div>
                <span class="text-sm font-medium text-slate-200 block">Enable Remote MCP (AI Trading)</span>
                <span class="text-xs text-slate-400">Exposes /mcp for Claude.ai, ChatGPT, Cursor, and hosted AI agents</span>
              </div>
              <label class="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" id="enable_mcp" name="enable_mcp" class="sr-only peer">
                <div class="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600"></div>
              </label>
            </div>

            <!-- Telegram Alerts (Optional) -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
              <div>
                <label class="block text-xs font-medium text-slate-300 mb-1">Telegram Bot Token (Optional)</label>
                <input type="text" id="telegram_token" name="telegram_token" placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
                  class="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 font-mono">
              </div>
              <div>
                <label class="block text-xs font-medium text-slate-300 mb-1">Telegram Chat ID (Optional)</label>
                <input type="text" id="telegram_chat_id" name="telegram_chat_id" placeholder="-100123456789"
                  class="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 font-mono">
              </div>
            </div>
          </div>
        </div>

        <!-- 4. Custom Git Repository Source (Optional) -->
        <details class="glass rounded-2xl p-5 text-xs group">
          <summary class="font-semibold text-slate-300 flex items-center justify-between cursor-pointer select-none">
            <span class="flex items-center"><i class="fa-brands fa-github mr-2 text-brand-500 text-sm"></i> Custom Git Repository Source (Optional)</span>
            <i class="fa-solid fa-chevron-down text-slate-500 group-open:rotate-180 transition-transform"></i>
          </summary>
          <div class="space-y-3 pt-4 border-t border-slate-800 mt-3">
            <p class="text-slate-400 text-[11px]">Install from your own GitHub repository or fork containing your customized code.</p>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div class="sm:col-span-2">
                <label class="block text-xs font-medium text-slate-300 mb-1">Repository URL</label>
                <input type="text" id="repo_url" name="repo_url" value="REPO_URL_PLACEHOLDER"
                  class="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 font-mono">
              </div>
              <div>
                <label class="block text-xs font-medium text-slate-300 mb-1">Branch</label>
                <input type="text" id="repo_branch" name="repo_branch" value="main"
                  class="w-full bg-slate-900/80 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 font-mono">
              </div>
            </div>
          </div>
        </details>

        <!-- Submit Button -->
        <button type="submit" id="submitBtn"
          class="w-full py-3.5 px-6 rounded-2xl bg-gradient-to-r from-brand-600 to-emerald-500 hover:from-brand-500 hover:to-emerald-400 text-white font-bold text-base shadow-xl shadow-brand-500/25 transition transform active:scale-[0.99] flex items-center justify-center space-x-2">
          <i class="fa-solid fa-play"></i>
          <span>Start One-Click Installation</span>
        </button>

      </form>
    </div>

    <!-- Right Column: Live Installation Terminal -->
    <div class="lg:col-span-5 space-y-6">

      <!-- Progress Card -->
      <div class="glass rounded-2xl p-6 sticky top-24">
        <h3 class="text-base font-semibold text-white mb-4 flex items-center justify-between">
          <span>Installation Progress</span>
          <span id="stageBadge" class="text-xs px-2.5 py-1 rounded-full bg-slate-800 text-slate-400 border border-slate-700">Ready</span>
        </h3>

        <!-- Progress Bar -->
        <div class="w-full bg-slate-900 rounded-full h-2.5 mb-6 overflow-hidden border border-slate-800">
          <div id="progressBar" class="bg-gradient-to-r from-brand-500 to-emerald-400 h-2.5 rounded-full transition-all duration-500 w-0"></div>
        </div>

        <!-- Stages Checklist -->
        <div class="space-y-3 mb-6 text-xs" id="stageList">
          <div class="flex items-center space-x-2.5 text-slate-400" id="step1">
            <i class="fa-regular fa-circle text-slate-500"></i>
            <span>1. Timezone (IST), package locks & system packages</span>
          </div>
          <div class="flex items-center space-x-2.5 text-slate-400" id="step2">
            <i class="fa-regular fa-circle text-slate-500"></i>
            <span>2. Astral uv Python package manager</span>
          </div>
          <div class="flex items-center space-x-2.5 text-slate-400" id="step3">
            <i class="fa-regular fa-circle text-slate-500"></i>
            <span>3. Clone OpenAlgo & build venv</span>
          </div>
          <div class="flex items-center space-x-2.5 text-slate-400" id="step4">
            <i class="fa-regular fa-circle text-slate-500"></i>
            <span>4. Generate production .env & keys</span>
          </div>
          <div class="flex items-center space-x-2.5 text-slate-400" id="step5">
            <i class="fa-regular fa-circle text-slate-500"></i>
            <span>5. Hardened Nginx reverse proxy configuration</span>
          </div>
          <div class="flex items-center space-x-2.5 text-slate-400" id="step6">
            <i class="fa-regular fa-circle text-slate-500"></i>
            <span>6. Let's Encrypt SSL certificate</span>
          </div>
          <div class="flex items-center space-x-2.5 text-slate-400" id="step7">
            <i class="fa-regular fa-circle text-slate-500"></i>
            <span>7. Create & start systemd service</span>
          </div>
        </div>

        <!-- Terminal Output -->
        <div class="rounded-xl bg-slate-950 border border-slate-800 p-3 font-mono text-[11px] leading-relaxed h-72 overflow-y-auto" id="terminal">
          <div class="text-slate-500">[System] OpenAlgo Web Setup Wizard initialized. Waiting for input...</div>
        </div>

        <!-- Success Complete Banner (Hidden by default) -->
        <div id="successCard" class="hidden mt-4 p-5 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-left space-y-4">
          <div class="flex items-center space-x-3">
            <div class="w-9 h-9 rounded-full bg-emerald-500 text-slate-950 flex items-center justify-center text-base font-bold shrink-0">
              <i class="fa-solid fa-check"></i>
            </div>
            <div>
              <h4 class="font-bold text-white text-sm">OpenAlgo is Live!</h4>
              <p class="text-xs text-slate-400">Services are active and running in background.</p>
            </div>
          </div>

          <div class="bg-slate-900/80 p-3 rounded-xl border border-slate-800 text-xs space-y-2 font-mono">
            <div><span class="text-slate-500">Dashboard: </span><span id="sumDashboard" class="text-emerald-400 font-bold"></span></div>
            <div><span class="text-slate-500">Broker: </span><span id="sumBroker" class="text-slate-200"></span></div>
            <div><span class="text-slate-500">Callback: </span><span id="sumCallback" class="text-slate-300 break-all"></span></div>
          </div>

          <a id="dashboardLink" href="#" target="_blank" class="block text-center w-full py-3 px-4 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs rounded-xl transition shadow-lg shadow-emerald-500/20">
            Open Dashboard & Login <i class="fa-solid fa-arrow-up-right-from-square ml-1"></i>
          </a>
        </div>
      </div>

    </div>

  </main>

  <script>
    const xtsBrokers = ["acagarwal", "fivepaisaxts", "compositedge", "ibulls", "iifl", "jainamxts", "rmoney", "wisdom"];
    const securityToken = 'SECURITY_TOKEN_PLACEHOLDER';

    let serverIp = 'DIAG_IP_PLACEHOLDER';
    let dnsTimer = null;

    // Initialize UI
    window.addEventListener('DOMContentLoaded', () => {
      setupEventListeners();
      updateXtsVisibility();
      updateCallbackPreview();
      fetchSystemInfo();
    });

    async function fetchSystemInfo() {
      try {
        const res = await fetch(`/api/system-info?token=${securityToken}`);
        const data = await res.json();
        if (data.os) document.getElementById('diagOS').textContent = data.os;
        if (data.total_ram_gb) document.getElementById('diagRAM').textContent = `${data.total_ram_gb} GB`;
        if (data.free_disk_gb) document.getElementById('diagDisk').textContent = `${data.free_disk_gb} GB`;
        if (data.public_ip) {
          document.getElementById('diagIP').textContent = data.public_ip;
          serverIp = data.public_ip;
          updateCallbackPreview();
        }
      } catch (err) {
        console.error('Diagnostics refresh:', err);
      }
    }

    function setupEventListeners() {
      document.getElementById('broker').addEventListener('change', () => {
        updateXtsVisibility();
        updateCallbackPreview();
      });
      document.getElementById('domain').addEventListener('input', () => {
        updateCallbackPreview();
        debounceDnsCheck();
      });
      document.getElementById('use_ssl').addEventListener('change', updateCallbackPreview);

      document.getElementById('installForm').addEventListener('submit', handleInstallSubmit);
    }

    function debounceDnsCheck() {
      clearTimeout(dnsTimer);
      dnsTimer = setTimeout(checkDomainDns, 600);
    }

    async function checkDomainDns() {
      const domain = document.getElementById('domain').value.trim();
      const dnsStatus = document.getElementById('dnsStatus');
      if (!domain) {
        dnsStatus.className = 'text-xs mt-1.5 hidden flex items-center';
        return;
      }

      dnsStatus.className = 'text-xs mt-1.5 flex items-center text-slate-400';
      dnsStatus.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1.5"></i> Checking DNS resolution...';

      try {
        const res = await fetch(`/api/check-dns?domain=${encodeURIComponent(domain)}&token=${securityToken}`);
        const data = await res.json();
        if (data.is_cloudflare) {
          dnsStatus.className = 'text-xs mt-1.5 flex items-center text-amber-300';
          dnsStatus.innerHTML = `<i class="fa-solid fa-cloud mr-1.5 text-amber-400"></i> Cloudflare Proxy (Orange Cloud) detected. <b>Important:</b> Switch to <b>DNS only</b> (Grey Cloud) in Cloudflare for Let's Encrypt SSL issuance.`;
        } else if (data.resolves && data.matches_server) {
          dnsStatus.className = 'text-xs mt-1.5 flex items-center text-emerald-400';
          dnsStatus.innerHTML = `<i class="fa-solid fa-circle-check mr-1.5"></i> DNS verified! Resolves directly to server IP (${data.ip}).`;
        } else if (data.resolves && !data.matches_server) {
          dnsStatus.className = 'text-xs mt-1.5 flex items-center text-amber-400';
          dnsStatus.innerHTML = `<i class="fa-solid fa-triangle-exclamation mr-1.5"></i> Domain resolves to ${data.ip}, but your server IP is ${data.server_ip}.`;
        } else {
          dnsStatus.className = 'text-xs mt-1.5 flex items-center text-rose-400';
          dnsStatus.innerHTML = `<i class="fa-solid fa-circle-xmark mr-1.5"></i> DNS record not found for ${domain}. (Add an A record pointing to ${data.server_ip})`;
        }
      } catch (e) {
        dnsStatus.className = 'text-xs mt-1.5 hidden flex items-center';
      }
    }

    function updateXtsVisibility() {
      const broker = document.getElementById('broker').value;
      const isXts = xtsBrokers.includes(broker);
      const xtsSec = document.getElementById('xtsCredentialsSection');
      if (isXts) {
        xtsSec.classList.remove('hidden');
      } else {
        xtsSec.classList.add('hidden');
      }
    }

    function updateCallbackPreview() {
      const brokerEl = document.getElementById('broker');
      const broker = (brokerEl && brokerEl.value) ? brokerEl.value : 'acagarwal';
      const domainEl = document.getElementById('domain');
      const domain = domainEl ? domainEl.value.trim() : '';
      const useSslEl = document.getElementById('use_ssl');
      const useSsl = useSslEl ? useSslEl.checked : true;

      let base = '';
      if (domain) {
        base = `${useSsl ? 'https' : 'http'}://${domain}`;
      } else {
        base = `http://${serverIp}:5000`;
      }
      const previewEl = document.getElementById('callbackPreview');
      if (previewEl) {
        previewEl.textContent = `${base}/${broker}/callback`;
      }
    }

    function copyCallbackUrl() {
      const previewEl = document.getElementById('callbackPreview');
      const url = previewEl ? previewEl.textContent : '';
      if (!url) return;
      navigator.clipboard.writeText(url).then(() => {
        const btn = document.getElementById('copyBtn');
        if (btn) {
          const orig = btn.innerHTML;
          btn.innerHTML = '<i class="fa-solid fa-check text-emerald-400 mr-1.5"></i> Copied!';
          setTimeout(() => { btn.innerHTML = orig; }, 2000);
        }
      }).catch(() => {
        prompt('Copy your Callback URL:', url);
      });
    }

    async function handleInstallSubmit(e) {
      e.preventDefault();
      const form = e.target;
      const submitBtn = document.getElementById('submitBtn');

      submitBtn.disabled = true;
      submitBtn.classList.add('opacity-50', 'cursor-not-allowed');
      submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i> Installing OpenAlgo...';

      const payload = {
        domain: form.domain.value,
        use_ssl: form.use_ssl.checked,
        broker: form.broker.value,
        broker_api_key: form.broker_api_key.value,
        broker_api_secret: form.broker_api_secret.value,
        broker_api_key_market: form.broker_api_key_market ? form.broker_api_key_market.value : '',
        broker_api_secret_market: form.broker_api_secret_market ? form.broker_api_secret_market.value : '',
        enable_mcp: form.enable_mcp.checked,
        telegram_token: form.telegram_token.value,
        telegram_chat_id: form.telegram_chat_id.value,
        repo_url: form.repo_url ? form.repo_url.value.trim() : '',
        repo_branch: form.repo_branch ? form.repo_branch.value.trim() : 'main',
      };

      try {
        const res = await fetch(`/api/install?token=${securityToken}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.status === 'started') {
          startLogStreaming();
        } else {
          alert('Error starting installation: ' + (data.message || 'Unknown error'));
        }
      } catch (err) {
        alert('Request failed: ' + err.message);
      }
    }

    function startLogStreaming() {
      const evtSource = new EventSource(`/api/logs/stream?token=${securityToken}`);
      const terminal = document.getElementById('terminal');
      const progressBar = document.getElementById('progressBar');
      const stageBadge = document.getElementById('stageBadge');

      evtSource.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.type === 'log') {
          const div = document.createElement('div');
          if (data.level === 'SUCCESS') div.className = 'text-emerald-400 font-bold';
          else if (data.level === 'ERROR') div.className = 'text-rose-400 font-bold';
          else if (data.level === 'STEP') div.className = 'text-amber-400';
          else if (data.level === 'CONFIG') div.className = 'text-purple-400';
          else if (data.level === 'WARN') div.className = 'text-yellow-400';
          else div.className = 'text-slate-300';

          div.textContent = `[${data.timestamp}] ${data.message}`;
          terminal.appendChild(div);
          terminal.scrollTop = terminal.scrollHeight;
        } else if (data.type === 'progress') {
          const pct = Math.round((data.stage / data.total_stages) * 100);
          progressBar.style.width = `${pct}%`;
          stageBadge.textContent = `Stage ${data.stage} of ${data.total_stages}`;
          stageBadge.className = 'text-xs px-2.5 py-1 rounded-full bg-brand-500/20 text-brand-400 border border-brand-500/30';

          for (let i = 1; i <= 7; i++) {
            const stepEl = document.getElementById(`step${i}`);
            if (i < data.stage) {
              stepEl.className = 'flex items-center space-x-2.5 text-emerald-400 font-medium';
              stepEl.querySelector('i').className = 'fa-solid fa-circle-check text-emerald-400';
            } else if (i === data.stage) {
              stepEl.className = 'flex items-center space-x-2.5 text-brand-400 font-bold';
              stepEl.querySelector('i').className = 'fa-solid fa-spinner fa-spin text-brand-400';
            }
          }

          if (data.status === 'success') {
            evtSource.close();
            progressBar.style.width = '100%';
            stageBadge.textContent = 'Installed';
            stageBadge.className = 'text-xs px-2.5 py-1 rounded-full bg-emerald-500 text-slate-950 font-bold';
            document.getElementById('step7').className = 'flex items-center space-x-2.5 text-emerald-400 font-medium';
            document.getElementById('step7').querySelector('i').className = 'fa-solid fa-circle-check text-emerald-400';

            const successCard = document.getElementById('successCard');
            successCard.classList.remove('hidden');

            const sum = data.summary || {};
            document.getElementById('sumDashboard').textContent = sum.dashboard_url || data.completed_url;
            document.getElementById('sumBroker').textContent = sum.broker || '';
            document.getElementById('sumCallback').textContent = sum.redirect_url || '';

            const link = document.getElementById('dashboardLink');
            link.href = data.completed_url;

            const submitBtn = document.getElementById('submitBtn');
            if (submitBtn) {
              submitBtn.disabled = true;
              submitBtn.className = 'w-full py-3.5 px-6 rounded-2xl bg-emerald-600 text-white font-bold text-base shadow-xl flex items-center justify-center space-x-2 opacity-90 cursor-default';
              submitBtn.innerHTML = '<i class="fa-solid fa-circle-check mr-2"></i> OpenAlgo Installed & Running';
            }
          } else if (data.status === 'error') {
            evtSource.close();
            stageBadge.textContent = 'Failed';
            stageBadge.className = 'text-xs px-2.5 py-1 rounded-full bg-rose-500 text-white font-bold';
          }
        }
      };

      evtSource.onerror = () => {
        // Auto-reconnect or handle close
      };
    }
  </script>
</body>
</html>
"""


class WebInstallerHTTPHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for OpenAlgo setup wizard."""

    def log_message(self, format, *args):
        pass

    def _verify_token(self) -> bool:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        token = params.get("token", [""])[0]
        return token == _security_token

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if not self._verify_token():
            self.send_response(403)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<h1>403 Forbidden</h1><p>Invalid or missing security token. Please use the exact URL printed in your server terminal.</p>"
            )
            return

        if path == "/" or path == "/index.html":
            diag = get_system_diagnostics()
            broker_options = "\n".join(
                [
                    f'                <option value="{code}" {"selected" if code == "acagarwal" else ""}>{name}</option>'
                    for code, name in ALL_BROKERS
                ]
            )
            html = (
                HTML_PAGE.replace("BROKER_OPTIONS_PLACEHOLDER", broker_options)
                .replace("SECURITY_TOKEN_PLACEHOLDER", _security_token)
                .replace("REPO_URL_PLACEHOLDER", REPO_URL)
                .replace("DIAG_OS_PLACEHOLDER", str(diag.get("os", "Linux (Ubuntu)")))
                .replace("DIAG_RAM_PLACEHOLDER", f'{diag.get("total_ram_gb", 1.0)} GB')
                .replace("DIAG_DISK_PLACEHOLDER", f'{diag.get("free_disk_gb", 10.0)} GB')
                .replace("DIAG_IP_PLACEHOLDER", str(diag.get("public_ip", "127.0.0.1")))
            )
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path == "/api/system-info":
            diag = get_system_diagnostics()
            self._send_json(diag)

        elif path == "/api/check-dns":
            domain = params.get("domain", [""])[0]
            res = check_domain_dns(domain)
            self._send_json(res)

        elif path == "/api/status":
            self._send_json(_install_state)

        elif path == "/api/logs/stream":
            # Server-Sent Events (SSE)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            try:
                while True:
                    # Flush pending logs
                    while not _log_queue.empty():
                        log_item = _log_queue.get_nowait()
                        event_payload = {"type": "log", **log_item}
                        self.wfile.write(
                            f"data: {json.dumps(event_payload)}\n\n".encode("utf-8")
                        )
                        self.wfile.flush()

                    # Send progress update
                    progress_payload = {
                        "type": "progress",
                        "status": _install_state["status"],
                        "stage": _install_state["stage"],
                        "total_stages": _install_state["total_stages"],
                        "message": _install_state["message"],
                        "completed_url": _install_state["completed_url"],
                        "summary": _install_state.get("summary", {}),
                    }
                    self.wfile.write(
                        f"data: {json.dumps(progress_payload)}\n\n".encode("utf-8")
                    )
                    self.wfile.flush()

                    if _install_state["status"] in ("success", "error"):
                        break

                    time.sleep(0.5)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if not self._verify_token():
            self._send_json({"error": "Forbidden: Invalid token"}, 403)
            return

        if path == "/api/install":
            if _install_state["status"] == "running":
                self._send_json({"error": "Installation is already in progress"}, 400)
                return

            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                config = json.loads(body)
            except Exception:
                self._send_json({"error": "Invalid JSON"}, 400)
                return

            thread = threading.Thread(
                target=run_installation_pipeline, args=(config,), daemon=True
            )
            thread.start()

            self._send_json({"status": "started", "message": "Installation pipeline launched"})
        else:
            self.send_response(404)
            self.end_headers()


def start_server(port: int = DEFAULT_PORT):
    global _security_token

    _security_token = secrets.token_hex(16)
    pub_ip = get_public_ip()

    server_address = ("", port)
    httpd = socketserver.TCPServer(server_address, WebInstallerHTTPHandler)

    print("\n" + "=" * 65)
    print("        🚀 OPENALGO ONE-CLICK SERVER INSTALLER WIZARD")
    print("=" * 65)
    print(f"\n👉 Open this URL in your web browser to configure your server:\n")
    print(f"   http://{pub_ip}:{port}/?token={_security_token}")
    print(f"   (or http://localhost:{port}/?token={_security_token} if local)")
    print("\n" + "=" * 65)
    print("Press Ctrl+C to terminate the installer server anytime.\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nInstaller server stopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenAlgo One-Click Server Installer")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help="Port to bind web installer"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate installation without modifying host"
    )
    args = parser.parse_args()

    if args.dry_run:
        _dry_run = True
        print("[Notice] Running in DRY-RUN mode. System changes will be simulated.")

    start_server(args.port)
