"""AC Agarwal XTS Margin Calculator API mappings."""

from broker.acagarwal.mapping.transform_data import map_exchange_numeric, map_order_type, map_product_type
from database.token_db import get_token
from utils.logging import get_logger

logger = get_logger(__name__)


def _safe_float(value, field_name, default=0.0):
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        logger.warning(f"Invalid AC Agarwal margin field {field_name}: {value!r}. Using {default}.")
        return float(default)


def transform_margin_positions(positions):
    """
    Transform OpenAlgo margin position format to AC Agarwal XTS margin API format.
    """
    transformed_positions = []
    skipped_positions = []

    for position in positions:
        try:
            symbol = position.get("symbol")
            exchange = position.get("exchange")

            token = get_token(symbol, exchange)
            if not token:
                logger.warning(f"Token not found for: {symbol} on {exchange}")
                skipped_positions.append(f"{symbol} ({exchange})")
                continue

            transformed = {
                "exchange": map_exchange_numeric(exchange),
                "exchangeInstrumentId": int(token),
                "productType": map_product_type(position.get("product", "MIS")),
                "orderType": map_order_type(position.get("pricetype", "MARKET")),
                "orderSide": position.get("action", "BUY").upper(),
                "quantity": int(position.get("quantity", 1)),
                "price": float(position.get("price", 0)),
                "stopPrice": float(position.get("trigger_price", 0)),
                "orderSessionType": 1,  # DAY
            }
            transformed_positions.append(transformed)
        except Exception as e:
            logger.error(f"Error transforming position {position}: {e}")
            skipped_positions.append(f"{position.get('symbol', 'unknown')} - Error: {str(e)}")
            continue

    if skipped_positions:
        logger.warning(f"Skipped {len(skipped_positions)} position(s): {', '.join(skipped_positions)}")

    return transformed_positions


def parse_margin_response(response_data):
    """
    Parse AC Agarwal XTS margin calculator response to OpenAlgo standard format.
    """
    if not response_data or not isinstance(response_data, dict):
        return {
            "status": "error",
            "message": "Invalid response from broker",
        }

    if response_data.get("type") != "success":
        return {
            "status": "error",
            "message": response_data.get("description", "Unknown error"),
        }

    brokerage_details = response_data.get("result", {}).get("brokerageDeatils", {})
    if not brokerage_details:
        return {
            "status": "error",
            "message": "No margin details in response",
        }

    margin_required = _safe_float(brokerage_details.get("MarginRequired", 0), "MarginRequired")
    margin_available = _safe_float(brokerage_details.get("MarginAvailable", 0), "MarginAvailable")
    margin_shortfall = _safe_float(brokerage_details.get("MarginShortfall", 0), "MarginShortfall")

    return {
        "status": "success",
        "margin_required": margin_required,
        "margin_available": margin_available,
        "margin_shortfall": margin_shortfall,
    }
