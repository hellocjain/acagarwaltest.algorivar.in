"""AC Agarwal broker base URLs configuration."""

import os

# Base URL for AC Agarwal Symphony XTS Interactive and Market Data endpoints
BASE_URL = os.getenv("ACAGARWAL_BASE_URL", "https://symphony.acagarwal.com:3000")

# Derived URLs for specific API endpoints
INTERACTIVE_URL = os.getenv("ACAGARWAL_INTERACTIVE_URL", f"{BASE_URL}/interactive")
MARKET_DATA_URL = os.getenv("ACAGARWAL_MARKET_DATA_URL", f"{BASE_URL}/apimarketdata")
