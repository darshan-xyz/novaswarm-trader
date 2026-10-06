"""Unit tests for native crypto data fetching and LangChain tools in novaswarm.data.

Tests:
- Symbol stripping and chain mapping
- Blockchain stats and address activity (mocked HTTP)
- DeFi token fundamentals and chain TVL (mocked HTTP)
- Derivatives funding rates, open interest, and long/short ratio (mocked HTTP)
- Crypto LangChain tools registration in novaswarm.data.tools
- Crypto analyst roles in novaswarm.intelligence.analysts
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from novaswarm.data.crypto import (
    CHAIN_MAP,
    _strip_coin,
    get_blockchain_stats,
    get_address_activity,
    get_token_fundamentals,
    get_defi_tvl,
    get_chain_tvl_overview,
    get_funding_rates,
    get_open_interest,
    get_long_short_ratio,
)
from novaswarm.data.tools import (
    get_blockchain_stats as tool_blockchain_stats,
    get_address_activity as tool_address_activity,
    get_token_fundamentals as tool_token_fundamentals,
    get_defi_tvl as tool_defi_tvl,
    get_chain_tvl_overview as tool_chain_tvl_overview,
    get_funding_rates as tool_funding_rates,
    get_open_interest as tool_open_interest,
    get_long_short_ratio as tool_long_short_ratio,
)


def _mock_response(json_data, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


# ── Symbol and Chain Map ──────────────────────────────────────────────────────


class TestCryptoHelpers:
    def test_strip_coin(self):
        assert _strip_coin("BTCUSDT") == "BTC"
        assert _strip_coin("BTC") == "BTC"
        assert _strip_coin("BTC-USD") == "BTC"
        assert _strip_coin("ethusdt") == "ETH"
        assert _strip_coin("SOLBUSD") == "SOL"

    def test_chain_map(self):
        assert CHAIN_MAP["BTC"] == "bitcoin"
        assert CHAIN_MAP["ETH"] == "ethereum"
        assert CHAIN_MAP["SOL"] == "solana"


# ── On-chain Metrics ─────────────────────────────────────────────────────────


class TestOnchainMetrics:
    @patch("novaswarm.data.crypto.httpx.Client")
    def test_blockchain_stats_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response({
            "data": {
                "blocks": 850000,
                "transactions_24h": 350000,
                "tps": 7.5,
                "hashrate_24h": "5.5E+20",
                "difficulty": 8.5e13,
                "market_price_usd": 67500.0,
            }
        })

        result = get_blockchain_stats("BTCUSDT")
        assert "Blockchain Stats for BTC" in result
        assert "350000" in result
        assert "67500.0" in result

    @patch("novaswarm.data.crypto.httpx.Client")
    def test_blockchain_stats_error_handled(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = RuntimeError("Network timeout")

        result = get_blockchain_stats("BTCUSDT")
        assert "error" in result.lower() or "failed" in result.lower()

    @patch("novaswarm.data.crypto.httpx.Client")
    def test_address_activity_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response({
            "data": {
                "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa": {
                    "address": {
                        "balance": 5000000000,  # satoshis = 50 BTC
                        "received": 10000000000,
                        "transaction_count": 42,
                    }
                }
            }
        })

        result = get_address_activity("BTC", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
        assert "Address Summary" in result
        assert "50.0000 BTC" in result
        assert "42" in result


# ── DeFi Metrics ──────────────────────────────────────────────────────────────


class TestDefiMetrics:
    @patch("novaswarm.data.crypto.httpx.Client")
    def test_token_fundamentals_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response({
            "name": "Uniswap",
            "category": "Dexes",
            "chains": ["Ethereum", "Polygon", "Arbitrum"],
            "tvl": 5500000000.0,
            "description": "Decentralized automated liquidity protocol.",
        })

        result = get_token_fundamentals("UNI")
        assert "Uniswap" in result
        assert "Dexes" in result
        assert "5,500,000,000.00" in result

    @patch("novaswarm.data.crypto.httpx.Client")
    def test_defi_tvl_alias(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response({
            "name": "Aave",
            "category": "Lending",
            "chains": ["Ethereum"],
            "tvl": 12000000000.0,
            "description": "Money market protocol.",
        })

        result = get_defi_tvl("aave")
        assert "Aave" in result
        assert "12,000,000,000.00" in result

    @patch("novaswarm.data.crypto.httpx.Client")
    def test_chain_tvl_overview_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response([
            {"name": "Ethereum", "tvl": 60000000000, "tokenSymbol": "ETH"},
            {"name": "Solana", "tvl": 4500000000, "tokenSymbol": "SOL"},
        ])

        result = get_chain_tvl_overview("Solana")
        assert "Chain TVL: Solana" in result
        assert "4,500,000,000.00" in result


# ── Derivatives Metrics ───────────────────────────────────────────────────────


class TestDerivativesMetrics:
    @patch("novaswarm.data.crypto.httpx.Client")
    def test_funding_rates_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response([
            {"fundingRate": "0.0001", "fundingTime": 1700000000000},
            {"fundingRate": "0.00015", "fundingTime": 1700028800000},
        ])

        result = get_funding_rates("BTCUSDT")
        assert "Funding Rates: BTCUSDT" in result
        assert "0.0150%" in result

    @patch("novaswarm.data.crypto.httpx.Client")
    def test_open_interest_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response({
            "openInterest": "85000.5"
        })

        result = get_open_interest("BTCUSDT")
        assert "Open Interest: BTCUSDT" in result
        assert "85,000.50 contracts" in result

    @patch("novaswarm.data.crypto.httpx.Client")
    def test_long_short_ratio_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = _mock_response([
            {
                "longAccount": "0.55",
                "shortAccount": "0.45",
                "longShortRatio": "1.22",
            }
        ])

        result = get_long_short_ratio("BTCUSDT")
        assert "Top Trader Long/Short Ratio: BTCUSDT" in result
        assert "55.0%" in result
        assert "45.0%" in result


# ── LangChain Tool Wrappers ───────────────────────────────────────────────────


class TestCryptoToolsRegistration:
    def test_tools_are_callable_and_named(self):
        for tool in [
            tool_blockchain_stats,
            tool_address_activity,
            tool_token_fundamentals,
            tool_defi_tvl,
            tool_chain_tvl_overview,
            tool_funding_rates,
            tool_open_interest,
            tool_long_short_ratio,
        ]:
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert hasattr(tool, "invoke")
            assert callable(tool.func)
