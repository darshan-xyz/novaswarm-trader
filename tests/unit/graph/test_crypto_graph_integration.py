"""Unit tests for crypto wiring in the multi-agent graph and state context.

Tests:
- Crypto report fields preservation in AnalysisContext legacy bridge
- NovaSwarmTradingGraph auto-selection of crypto analysts for asset_class='crypto'
- Analyst explicit overrides
"""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from novaswarm.graph.novaswarm_graph import NovaSwarmTradingGraph
from novaswarm.orchestration.context import AnalysisContext


class TestAnalysisContextCryptoReports:
    def test_legacy_state_includes_crypto_reports(self):
        ctx = AnalysisContext(
            job_id="test-job",
            symbol="BTCUSDT",
            trade_date="2026-03-01",
            asset_class="crypto",
            analyst_reports={
                "network": "Network hash rate up 12%",
                "tokenomics": "TVL steady at 50B",
                "derivatives": "Funding rate positive at 0.01%",
            },
        )
        legacy = ctx.to_legacy_state()
        assert legacy["onchain_report"] == "Network hash rate up 12%"
        assert legacy["defi_report"] == "TVL steady at 50B"
        assert legacy["funding_report"] == "Funding rate positive at 0.01%"

    def test_from_legacy_state_restores_crypto_reports(self):
        legacy = {
            "onchain_report": "Hashrate: 550 EH/s",
            "defi_report": "TVL: $60B",
            "funding_report": "Rate: 0.01%",
        }
        ctx = AnalysisContext.from_legacy_state(legacy, job_id="test-restore")
        assert ctx.analyst_reports.get("onchain") == "Hashrate: 550 EH/s"
        assert ctx.analyst_reports.get("defi") == "TVL: $60B"
        assert ctx.analyst_reports.get("funding") == "Rate: 0.01%"


class TestNovaSwarmTradingGraphCryptoAnalystSelection:
    def _make_graph(self, asset_class="equity", selected_analysts=None):
        executor = MagicMock()
        config = {"asset_class": asset_class}
        return NovaSwarmTradingGraph(
            upstream_config=config,
            executor=executor,
            selected_analysts=selected_analysts,
        )

    def test_equity_defaults_to_4_analysts(self):
        graph = self._make_graph(asset_class="equity")
        assert graph._selected_analysts == ["market", "social", "news", "fundamentals"]

    def test_crypto_defaults_to_7_analysts(self):
        graph = self._make_graph(asset_class="crypto")
        assert len(graph._selected_analysts) == 7
        assert "onchain" in graph._selected_analysts
        assert "defi" in graph._selected_analysts
        assert "funding" in graph._selected_analysts

    def test_explicit_override_respected(self):
        graph = self._make_graph(
            asset_class="crypto",
            selected_analysts=["market", "news"],
        )
        assert graph._selected_analysts == ["market", "news"]

    def test_empty_config_defaults_to_equity_analysts(self):
        graph = NovaSwarmTradingGraph(
            upstream_config={},
            executor=MagicMock(),
        )
        assert graph._selected_analysts == ["market", "social", "news", "fundamentals"]
