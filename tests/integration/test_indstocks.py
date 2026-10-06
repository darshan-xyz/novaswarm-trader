"""Integration tests — INDstocks API connectivity.

Tests real API calls to INDstocks for market data.
Requires: SKOPAQ_INDSTOCKS_TOKEN in .env
"""

import os
import pytest

from dotenv import load_dotenv
load_dotenv(override=True)

pytestmark = pytest.mark.integration


def _skip_if_no_token():
    token = os.environ.get("SKOPAQ_INDSTOCKS_TOKEN", "")
    if not token:
        pytest.skip("SKOPAQ_INDSTOCKS_TOKEN not set")


class TestINDstocksToken:
    """Verify token is present and looks valid."""

    def test_token_is_jwt(self):
        _skip_if_no_token()
        token = os.environ["SKOPAQ_INDSTOCKS_TOKEN"]
        parts = token.split(".")
        assert len(parts) == 3, f"Token should be JWT (3 dot-separated parts), got {len(parts)}"

    def test_token_not_expired(self):
        """Decode JWT payload and check expiry."""
        _skip_if_no_token()
        import base64
        import json
        import time

        token = os.environ["SKOPAQ_INDSTOCKS_TOKEN"]
        # Decode payload (second part)
        payload_b64 = token.split(".")[1]
        # Add padding
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))

        exp = payload.get("exp", 0)
        now = time.time()
        remaining_hours = (exp - now) / 3600

        assert exp > now, f"Token expired! exp={exp}, now={now}"
        print(f"  Token expires in {remaining_hours:.1f} hours (exp={exp})")
        print(f"  Client ID: {payload.get('clientID')}")
        print(f"  Partner ID: {payload.get('partnerID')}")


class TestINDstocksQuote:
    """Test fetching a real quote from INDstocks."""

    def test_fetch_reliance_quote(self):
        """Fetch real-time quote for RELIANCE."""
        _skip_if_no_token()
        from skopaq.data.pipeline import get_quote

        quote = get_quote("RELIANCE")
        print(f"\n  Quote result:\n{quote}")
        assert quote.symbol == "RELIANCE"
        assert quote.last_price > 0


class TestINDstocksHistorical:
    """Test fetching historical OHLCV data."""

    def test_fetch_reliance_historical(self):
        """Fetch 5-day OHLCV for RELIANCE."""
        _skip_if_no_token()
        from skopaq.data.pipeline import get_stock_data

        # Use recent dates (API max 1yr for daily candles)
        result = get_stock_data("RELIANCE", "2026-02-24", "2026-02-28")
        print(f"\n  Historical result:\n{result[:800]}")
        # Should contain CSV header
        assert "Date" in result or "date" in result.lower()
        assert "Close" in result or "close" in result.lower()


class TestINDstocksVendorFallback:
    """Test the vendor routing with INDstocks as primary."""

    def test_route_to_vendor_uses_indstocks_first(self):
        """UnifiedMarketData should configure INDstocks and fallback."""
        from skopaq.data.pipeline import get_unified_market_data

        pipeline = get_unified_market_data()
        assert pipeline.indstocks_provider is not None
        assert pipeline.yfinance_provider is not None
