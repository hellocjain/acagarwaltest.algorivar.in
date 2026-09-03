#!/usr/bin/env bash
# ==============================================================================
# OpenAlgo One-Click Web Installer Launcher for Ubuntu / Debian
# ==============================================================================

set -e

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default to custom repository if not provided
export OPENALGO_REPO_URL="${OPENALGO_REPO_URL:-https://github.com/hellocjain/acagarwaltest.algorivar.in.git}"

echo -e "${CYAN}================================================================${NC}"
echo -e "${GREEN}          🚀 OpenAlgo One-Click Web Installer Launcher${NC}"
echo -e "${CYAN}================================================================${NC}"

# Check for root / sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root or with sudo.${NC}"
    echo "Please rerun: sudo bash $0"
    exit 1
fi

if [ -n "$OPENALGO_REPO_URL" ]; then
    echo -e "${BLUE}Using Custom Repository:${NC} ${OPENALGO_REPO_URL}"
fi

# Detect Package Manager
echo -e "${YELLOW}[1/3] Checking base prerequisites...${NC}"
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq >/dev/null 2>&1 || true
    apt-get install -y -qq python3 curl ufw git >/dev/null 2>&1 || true
elif command -v dnf >/dev/null 2>&1; then
    dnf install -y -q python3 curl git >/dev/null 2>&1 || true
elif command -v yum >/dev/null 2>&1; then
    yum install -y -q python3 curl git >/dev/null 2>&1 || true
fi

# Check Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${RED}Error: Python 3 could not be installed automatically.${NC}"
    exit 1
fi

# Allow port 5000 in firewall if UFW is active
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    echo -e "${YELLOW}[2/3] Opening ports 5000, 80, 443 in UFW firewall...${NC}"
    ufw allow 5000/tcp >/dev/null 2>&1 || true
    ufw allow 80/tcp >/dev/null 2>&1 || true
    ufw allow 443/tcp >/dev/null 2>&1 || true
fi

# Setup working directory and fetch web_installer.py
INSTALL_TMP="/tmp/openalgo-web-installer"
mkdir -p "$INSTALL_TMP"

# If running locally from repo, use existing web_installer.py
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/web_installer.py" ]; then
    cp "$SCRIPT_DIR/web_installer.py" "$INSTALL_TMP/web_installer.py"
else
    echo -e "${YELLOW}[3/3] Downloading OpenAlgo Web Setup Wizard...${NC}"
    RAW_BASE="https://raw.githubusercontent.com/marketcalls/openalgo/main"
    if [ -n "$OPENALGO_REPO_URL" ]; then
        # If custom GitHub URL, convert https://github.com/USER/REPO.git -> https://raw.githubusercontent.com/USER/REPO/main
        CLEAN_REPO=$(echo "$OPENALGO_REPO_URL" | sed -e 's|https://github.com/||' -e 's|\.git$||')
        RAW_BASE="https://raw.githubusercontent.com/${CLEAN_REPO}/main"
    fi
    curl -sSL "${RAW_BASE}/install/web_installer.py" -o "$INSTALL_TMP/web_installer.py" || \
    curl -sSL "https://raw.githubusercontent.com/marketcalls/openalgo/main/install/web_installer.py" -o "$INSTALL_TMP/web_installer.py"
fi

chmod +x "$INSTALL_TMP/web_installer.py"

# Start the Web Installer Server
echo -e "${GREEN}Starting OpenAlgo Web Setup Wizard...${NC}"
cd "$INSTALL_TMP"
exec python3 "$INSTALL_TMP/web_installer.py" "$@"
