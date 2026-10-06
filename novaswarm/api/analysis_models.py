"""Pydantic schemas and data models for multi-agent stock analysis jobs and SSE events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalysisStartRequest(BaseModel):
    """Request payload to initiate a multi-agent analysis run."""

    symbol: str = Field(..., min_length=1, max_length=30, description="Stock ticker (e.g. RELIANCE, TCS)")
    trade_date: Optional[str] = Field(None, description="Trade date in YYYY-MM-DD format. Defaults to today.")
    urgency: Optional[str] = Field("medium", description="Analysis urgency: low, medium, high.")
    lookback_days: Optional[int] = Field(30, description="Historical data lookback in days.")
    asset_class: Optional[str] = Field(None, description="Asset class: equity or crypto.")
    selected_analysts: Optional[List[str]] = Field(None, description="Subset of analysts to run.")

    @field_validator("symbol")
    @classmethod
    def validate_symbol_format(cls, v: str) -> str:
        s = (v or "").strip().upper()
        if not s:
            raise ValueError("Symbol cannot be empty.")
        if len(s) > 20:
            raise ValueError("Symbol exceeds maximum length of 20 characters.")
        import re
        if not re.match(r"^[A-Z0-9&-]+$", s):
            raise ValueError("Symbol contains invalid characters. Use alphanumeric, hyphen, or ampersand.")
        return s


class AnalysisStartResponse(BaseModel):
    """Response returned when an analysis job is accepted."""

    job_id: str
    symbol: str
    status: str = "pending"
    created_at: str = Field(default_factory=_utc_now_iso)


class DecisionCard(BaseModel):
    """Final synthesis decision card produced by the agent pipeline."""

    symbol: str
    action: str = "HOLD"  # BUY, SELL, HOLD
    verdict: Optional[str] = None  # Alias for action
    confidence: int = 0  # 0 to 100
    position_size: Optional[int] = None  # Synonym for quantity
    quantity: Optional[int] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    risk_reward_ratio: float = 2.0
    position_value: Optional[float] = None
    risk_amount: Optional[float] = None
    atr: Optional[float] = None
    reasoning: str = ""
    safety_passed: bool = True
    execution_mode: str = "paper"
    duration_seconds: float = 0.0
    timestamp: str = Field(default_factory=_utc_now_iso)

    def model_post_init(self, __context: Any) -> None:
        if not self.verdict:
            self.verdict = self.action
        if self.position_size is None and self.quantity is not None:
            self.position_size = self.quantity
        elif self.quantity is None and self.position_size is not None:
            self.quantity = self.position_size


class AnalysisJobStatus(BaseModel):
    """Full snapshot of an analysis job state."""

    job_id: str
    status: str  # pending, running, completed, failed
    symbol: str
    trade_date: Optional[str] = None
    agent_statuses: Dict[str, str] = Field(default_factory=dict)
    reports: Dict[str, str] = Field(default_factory=dict)
    decision: Optional[DecisionCard] = None
    duration_seconds: float = 0.0
    error: Optional[str] = None
    created_at: str
    updated_at: str


class SSEEventData(BaseModel):
    """Structured data container for server-sent events."""

    event: str
    data: Dict[str, Any]
    timestamp: str = Field(default_factory=_utc_now_iso)
