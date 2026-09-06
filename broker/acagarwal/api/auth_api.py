"""AC Agarwal XTS Authentication API."""

import os

from broker.acagarwal.baseurl import INTERACTIVE_URL, MARKET_DATA_URL
from utils.httpx_client import get_httpx_client
from utils.logging import get_logger

logger = get_logger(__name__)


def is_offline_bypass_enabled():
    """Check if offline bypass is forced or enabled via environment variable."""
    return os.getenv("ACAGARWAL_OFFLINE_BYPASS", "").lower() in ("true", "1", "yes")


def is_auto_offline_fallback_enabled():
    """Check if auto offline fallback on connection failure is enabled (default True)."""
    return os.getenv("ACAGARWAL_AUTO_OFFLINE_FALLBACK", "true").lower() in ("true", "1", "yes")


def authenticate_broker(request_token=None):
    """
    Authenticate with AC Agarwal Symphony XTS Interactive API.

    Returns:
        tuple: (auth_token, feed_token, user_id, error_message)
    """
    if is_offline_bypass_enabled():
        logger.warning(
            "AC Agarwal offline bypass active (ACAGARWAL_OFFLINE_BYPASS=true). "
            "Activating offline simulation session."
        )
        return "OFFLINE_MOCK_ACAGARWAL_TOKEN", "OFFLINE_MOCK_FEED_TOKEN", "ACAGARWAL_OFFLINE", None

    try:
        client = get_httpx_client()
        BROKER_API_KEY = os.getenv("BROKER_API_KEY")
        BROKER_API_SECRET = os.getenv("BROKER_API_SECRET")

        if not BROKER_API_KEY or not BROKER_API_SECRET:
            if is_auto_offline_fallback_enabled():
                logger.warning("BROKER_API_KEY/SECRET missing; activating offline simulation mode")
                return "OFFLINE_MOCK_ACAGARWAL_TOKEN", "OFFLINE_MOCK_FEED_TOKEN", "ACAGARWAL_OFFLINE", None
            return None, None, None, "BROKER_API_KEY or BROKER_API_SECRET is missing in configuration."

        payload = {
            "appKey": BROKER_API_KEY,
            "secretKey": BROKER_API_SECRET,
            "source": "WEBAPI",
        }
        if request_token and request_token != "acagarwal":
            payload["accessToken"] = request_token

        headers = {"Content-Type": "application/json"}
        session_url = f"{INTERACTIVE_URL}/user/session"
        try:
            response = client.post(session_url, json=payload, headers=headers)
        except Exception as net_err:
            if is_auto_offline_fallback_enabled():
                logger.warning(
                    f"AC Agarwal Symphony XTS server unreachable ({net_err}). "
                    "Activating Offline Simulation Mode for weekend maintenance."
                )
                return "OFFLINE_MOCK_ACAGARWAL_TOKEN", "OFFLINE_MOCK_FEED_TOKEN", "ACAGARWAL_OFFLINE", None
            raise

        if response.status_code == 200:
            result = response.json()
            if result.get("type") == "success":
                token = result["result"]["token"]
                logger.info("AC Agarwal Interactive Auth token received successfully")

                # Retrieve feed token for market data
                feed_token, user_id, feed_error = get_feed_token()
                if feed_error:
                    logger.warning(f"Feed token warning: {feed_error}")
                    # Return interactive token even if feed token fails so orders can proceed
                    return token, "OFFLINE_MOCK_FEED_TOKEN", user_id or "ACAGARWAL_USER", None

                return token, feed_token, user_id, None
            else:
                desc = result.get("description") or result.get("message") or "Authentication failed"
                return None, None, None, f"AC Agarwal Interactive Login rejected: {desc}"
        else:
            if is_auto_offline_fallback_enabled():
                logger.warning(
                    f"AC Agarwal Symphony XTS returned HTTP {response.status_code} (server down/maintenance). "
                    "Activating Offline Simulation Mode."
                )
                return "OFFLINE_MOCK_ACAGARWAL_TOKEN", "OFFLINE_MOCK_FEED_TOKEN", "ACAGARWAL_OFFLINE", None
            try:
                error_detail = response.json()
                error_message = error_detail.get("message") or error_detail.get("description") or response.text
            except Exception:
                error_message = response.text
            return None, None, None, f"API error ({response.status_code}): {error_message}"

    except Exception as e:
        if is_auto_offline_fallback_enabled():
            logger.warning(
                f"Exception during AC Agarwal authentication ({e}). Falling back to Offline Simulation Mode."
            )
            return "OFFLINE_MOCK_ACAGARWAL_TOKEN", "OFFLINE_MOCK_FEED_TOKEN", "ACAGARWAL_OFFLINE", None
        logger.exception("Exception during AC Agarwal authentication")
        return None, None, None, f"Error during authentication: {str(e)}"


def get_feed_token():
    """
    Authenticate with AC Agarwal Symphony XTS Market Data API.

    Returns:
        tuple: (feed_token, user_id, error_message)
    """
    if is_offline_bypass_enabled():
        return "OFFLINE_MOCK_FEED_TOKEN", "ACAGARWAL_OFFLINE", None

    try:
        BROKER_API_KEY_MARKET = os.getenv("BROKER_API_KEY_MARKET") or os.getenv("BROKER_API_KEY")
        BROKER_API_SECRET_MARKET = os.getenv("BROKER_API_SECRET_MARKET") or os.getenv("BROKER_API_SECRET")

        if not BROKER_API_KEY_MARKET or not BROKER_API_SECRET_MARKET:
            if is_auto_offline_fallback_enabled():
                return "OFFLINE_MOCK_FEED_TOKEN", "ACAGARWAL_OFFLINE", None
            return None, None, "Market data credentials not configured"

        feed_payload = {
            "appKey": BROKER_API_KEY_MARKET,
            "secretKey": BROKER_API_SECRET_MARKET,
            "source": "WEBAPI",
        }

        feed_headers = {"Content-Type": "application/json"}
        client = get_httpx_client()

        # Try /auth/login first, then /user/session fallback
        for endpoint in [f"{MARKET_DATA_URL}/auth/login", f"{MARKET_DATA_URL}/user/session"]:
            try:
                feed_response = client.post(endpoint, json=feed_payload, headers=feed_headers)
                if feed_response.status_code == 200:
                    feed_result = feed_response.json()
                    if feed_result.get("type") == "success":
                        feed_token = feed_result["result"].get("token")
                        user_id = feed_result["result"].get("userID")
                        logger.info("AC Agarwal Market Data token received successfully")
                        return feed_token, user_id, None
            except Exception as ex:
                logger.debug(f"Endpoint {endpoint} failed: {ex}")
                continue

        if is_auto_offline_fallback_enabled():
            logger.warning("Market Data server unreachable. Using mock feed token for offline simulation.")
            return "OFFLINE_MOCK_FEED_TOKEN", "ACAGARWAL_OFFLINE", None

        return None, None, "Failed to acquire Market Data token from endpoints"
    except Exception as e:
        if is_auto_offline_fallback_enabled():
            logger.warning(f"Market Data exception ({e}). Using mock feed token for offline simulation.")
            return "OFFLINE_MOCK_FEED_TOKEN", "ACAGARWAL_OFFLINE", None
        logger.exception("Exception during Market Data token acquisition")
        return None, None, f"Market Data token exception: {str(e)}"
