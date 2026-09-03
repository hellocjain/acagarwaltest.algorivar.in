"""Maps between OpenAlgo exchange codes and AC Agarwal XTS specific exchange types."""

from utils.logging import get_logger

logger = get_logger(__name__)


class AcagarwalExchangeMapper:
    """Maps between OpenAlgo exchange codes and AC Agarwal XTS specific exchange types."""

    EXCHANGE_TYPES = {
        "NSE": 1,
        "NFO": 2,
        "NSE_INDEX": 1,
        "CDS": 3,
        "BSE": 11,
        "BFO": 12,
        "BSE_INDEX": 11,
        "MCX": 51,
        "NSECM": 1,
        "NSEFO": 2,
        "NSECD": 3,
        "BSECM": 11,
        "BSEFO": 12,
        "MCXFO": 51,
    }

    REVERSE_EXCHANGE_TYPES = {
        1: "NSE",
        2: "NFO",
        3: "CDS",
        11: "BSE",
        12: "BFO",
        51: "MCX",
    }

    @staticmethod
    def get_exchange_type(exchange):
        if exchange is None:
            return 1

        exchange_str = str(exchange).upper().strip()
        all_exchange_mappings = {
            "NSE": 1,
            "NFO": 2,
            "CDS": 3,
            "BSE": 11,
            "BFO": 12,
            "MCX": 51,
            "NSECM": 1,
            "NSEFO": 2,
            "NSECD": 3,
            "BSECM": 11,
            "BSEFO": 12,
            "MCXFO": 51,
            "NSE_INDEX": 1,
            "BSE_INDEX": 11,
            "1": 1,
            "2": 2,
            "3": 3,
            "11": 11,
            "12": 12,
            "51": 51,
        }
        return all_exchange_mappings.get(exchange_str, 1)

    @staticmethod
    def get_openalgo_exchange(code):
        return AcagarwalExchangeMapper.REVERSE_EXCHANGE_TYPES.get(code, "NSE")


class AcagarwalCapabilityRegistry:
    """
    Registry of AC Agarwal XTS broker capabilities.
    """
    exchanges = ["NSE", "NFO", "CDS", "BSE", "BFO", "MCX"]
    subscription_modes = [1, 2, 3]  # 1: LTP, 2: Quote, 3: Depth
    depth_support = {
        "NSE": [5, 20],
        "NFO": [5, 20],
        "CDS": [5],
        "BSE": [5],
        "BFO": [5],
        "MCX": [5],
    }

    @classmethod
    def get_supported_depth_levels(cls, exchange):
        return cls.depth_support.get(exchange, [5])

    @classmethod
    def is_depth_level_supported(cls, exchange, depth_level):
        supported_depths = cls.get_supported_depth_levels(exchange)
        return depth_level in supported_depths

    @classmethod
    def get_fallback_depth_level(cls, exchange, requested_depth):
        supported_depths = cls.get_supported_depth_levels(exchange)
        fallbacks = [d for d in supported_depths if d <= requested_depth]
        if fallbacks:
            return max(fallbacks)
        return 5
