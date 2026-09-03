"""AC Agarwal Funds & Margin Data API."""

from broker.acagarwal.baseurl import INTERACTIVE_URL
from utils.httpx_client import get_httpx_client
from utils.logging import get_logger

logger = get_logger(__name__)


def get_margin_data(auth_token):
    """
    Fetch account margin / balance data from AC Agarwal XTS API.
    """
    client = get_httpx_client()
    headers = {"authorization": auth_token, "Content-Type": "application/json"}

    try:
        response = client.get(f"{INTERACTIVE_URL}/user/balance", headers=headers)
        margin_data = response.json()
        logger.debug(f"AC Agarwal Funds Raw Response: {margin_data}")

        if (
            margin_data.get("result")
            and margin_data["result"].get("BalanceList")
            and margin_data["result"]["BalanceList"]
        ):
            balance_list = margin_data["result"]["BalanceList"]
            balance_entry = balance_list[0]
            for entry in balance_list:
                if entry.get("limitHeader") == "ALL|ALL|ALL":
                    balance_entry = entry
                    break

            rms_sublimits = balance_entry.get("limitObject", {}).get("RMSSubLimits", {})
            required_keys = [
                "netMarginAvailable",
                "collateral",
                "UnrealizedMTM",
                "RealizedMTM",
                "marginUtilized",
            ]

            filtered_data = {}
            for key in required_keys:
                value = rms_sublimits.get(key, 0)
                try:
                    formatted_value = f"{float(value):.2f}" if str(value).lower() != "nan" else "0.00"
                except (ValueError, TypeError):
                    formatted_value = "0.00"
                filtered_data[key] = formatted_value

            processed_margin_data = {
                "availablecash": filtered_data.get("netMarginAvailable", "0.00"),
                "collateral": filtered_data.get("collateral", "0.00"),
                "m2munrealized": filtered_data.get("UnrealizedMTM", "0.00"),
                "m2mrealized": filtered_data.get("RealizedMTM", "0.00"),
                "utiliseddebits": filtered_data.get("marginUtilized", "0.00"),
            }
            return processed_margin_data
        else:
            return {}
    except Exception as e:
        logger.exception("Failed to fetch AC Agarwal margin data")
        return {}
