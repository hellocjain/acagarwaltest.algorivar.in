#!/usr/bin/env bash
# ==============================================================================
# OpenAlgo Ubuntu Container Smoke Test Script
# Tests the one-click installer in a clean Ubuntu 22.04 container.
# Usage: ./test/test_ubuntu_docker.sh
# ==============================================================================

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}================================================================${NC}"
echo -e "${GREEN}      🧪 OpenAlgo Ubuntu Docker Container Smoke Test${NC}"
echo -e "${CYAN}================================================================${NC}"

if ! command -v docker >/dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not installed or not in PATH.${NC}"
    echo "Please install Docker Desktop or start the Docker daemon."
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}Error: Docker daemon is not running.${NC}"
    echo "Please start Docker Desktop and rerun this test."
    exit 1
fi

echo -e "${YELLOW}[1/3] Spinning up clean Ubuntu 22.04 container...${NC}"
CONTAINER_NAME="openalgo-test-$(date +%s)"

docker run -d --name "$CONTAINER_NAME" \
    -p 5500:5000 \
    ubuntu:22.04 \
    sleep 300

cleanup() {
    echo -e "${YELLOW}Cleaning up test container...${NC}"
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo -e "${YELLOW}[2/3] Executing bootstrap script inside Ubuntu container...${NC}"
docker exec "$CONTAINER_NAME" bash -c "
    apt-get update -qq && apt-get install -y -qq curl python3 git ufw &&
    curl -sSL https://raw.githubusercontent.com/hellocjain/acagarwaltest.algorivar.in/main/install/web-install.sh -o /tmp/web-install.sh &&
    chmod +x /tmp/web-install.sh
"

echo -e "${YELLOW}[3/3] Testing installer --dry-run mode...${NC}"
docker exec "$CONTAINER_NAME" python3 /tmp/openalgo-web-installer/web_installer.py --dry-run &
INSTALLER_PID=$!
sleep 2

echo -e "${GREEN}Testing HTTP response from Web Installer...${NC}"
HTTP_CODE=$(docker exec "$CONTAINER_NAME" python3 -c "
import urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:5000/') as r:
        print(r.status)
except urllib.error.HTTPError as e:
    print(e.code)
")

if [ "$HTTP_CODE" -eq 403 ]; then
    echo -e "${GREEN}✅ Security Check Passed: Root without token returned HTTP 403 Forbidden as expected.${NC}"
else
    echo -e "${RED}❌ Unexpected response code: $HTTP_CODE${NC}"
    exit 1
fi

echo -e "${GREEN}🎉 All Ubuntu container checks passed successfully!${NC}"
