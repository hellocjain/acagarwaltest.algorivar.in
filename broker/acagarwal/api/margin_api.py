"""AC Agarwal XTS Margin Calculator API."""

import json

from broker.acagarwal.baseurl import INTERACTIVE_URL
from broker.acagarwal.mapping.margin_data import parse_margin_response, transform_margin_positions
from utils.httpx_client import get_httpx_client
from utils.logging import get_logger

logger = get_logger(__name__)


def calculate_margin_api(positions, auth):
    """
    Calculate margin requirement for a basket of positions using AC Agarwal Symphony XTS API.
    """
    AUTH_TOKEN = auth
    portfolio = transform_margin_positions(positions)

    if not portfolio:
        error_response = {
            "status": "error",
            "message": "No valid positions to calculate margin. Check if symbols are valid.",
        }

        class MockResponse:
            status_code = 400
            status = 400

        return MockResponse(), error_response

    margin_request = {
        "portfolio": portfolio,
    }

    headers = {
        "authorization": AUTH_TOKEN,
        "Content-Type": "application/json",
    }
    client = get_httpx_client()

    try:
        response = client.post(
            f"{INTERACTIVE_URL}/orders/margindetails",
            headers=headers,
            json=margin_request,
        )
        response.status = response.status_code

        try:
            response_data = response.json()
        except json.JSONDecodeError:
            error_response = {"status": "error", "message": "Invalid response from broker API"}
            return response, error_response

        standardized_response = parse_margin_response(response_data)
        return response, standardized_response
    except Exception as e:
        logger.exception("Error calling AC Agarwal margin API")
        error_response = {"status": "error", "message": "Failed to calculate margin"}

        class MockResponse:
            status_code = 500
            status = 500

        return MockResponse(), error_response
