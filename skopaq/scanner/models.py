"""Data models for the scanner engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ScannerMetrics:
    """Computed metrics for a single symbol during a scan cycle."""

    symbol: str
    ltp: float = 0.0
    change_pct: float = 0.0
    volume: int = 0
    volume_ratio: float = 0.0  # Today's volume / avg volume
    gap_pct: float = 0.0       # Open vs prev close


@dataclass
class ScannerCandidate:
    """A stock identified by the scanner as worth full analysis."""

    symbol: str
    reason: str
    urgency: str = "normal"  # "high", "normal", "low"
    metrics: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        raw_sources = self.metrics.get("sources")
        if raw_sources and isinstance(raw_sources, list):
            sources = [str(s).capitalize() for s in raw_sources]
        elif "source" in self.metrics:
            sources = [str(self.metrics["source"]).capitalize()]
        else:
            sources = ["Technicals"]

        return {
            "symbol": self.symbol,
            "exchange": self.metrics.get("exchange", "NSE"),
            "urgency": self.urgency,
            "sources": sources,
            "ltp": float(self.metrics.get("ltp", 0.0)),
            "change_pct": float(self.metrics.get("change_pct", 0.0)),
            "gap_pct": float(self.metrics.get("gap_pct", 0.0)),
            "volume_ratio": float(self.metrics.get("volume_ratio", 0.0)),
            "reason": self.reason,
            "reasoning": self.reason,
            "metrics": self.metrics,
            "timestamp": self.timestamp.isoformat(),
        }
