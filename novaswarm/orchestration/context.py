"""Pydantic V2 state models for the NovaSwarm NovaPipeline multi-agent orchestrator.

Eliminates external graph dependencies, MessagesState, and custom reducers in favor
of strongly typed, immutable, validated data structures.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from novaswarm.api.analysis_models import DecisionCard


def _utc_now_iso() -> str:
    """Return current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


class OrderPlan(BaseModel):
    """Execution strategy plan formulated by the Order Strategist in Stage 3."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    action: Literal["BUY", "SELL", "HOLD"] = "HOLD"
    entry_price: Optional[float] = Field(None, description="Recommended entry level in INR")
    stop_loss: Optional[float] = Field(None, description="Recommended stop loss level in INR")
    target: Optional[float] = Field(None, description="Primary profit target in INR")
    risk_reward_ratio: float = Field(2.0, ge=0.1, description="Calculated risk to reward ratio")
    timeframe: str = Field("swing", description="Recommended trade horizon: intraday, swing, positional")
    execution_strategy: str = Field("", description="Detailed execution trigger (e.g. breakout above resistance)")
    rationale: str = Field("", description="Trading rationale justifying the setup")
    timestamp: str = Field(default_factory=_utc_now_iso)


class DebateTurn(BaseModel):
    """Single turn of debate between Upside and Downside advocates."""

    round_num: int
    speaker: Literal["upside_advocate", "downside_advocate", "thesis_adjudicator"]
    speaker_name: str
    argument: str
    timestamp: str = Field(default_factory=_utc_now_iso)


class ThesisDebateContext(BaseModel):
    """State for Stage 2 adversarial debate."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    rounds: int = 0
    upside_arguments: List[str] = Field(default_factory=list)
    downside_arguments: List[str] = Field(default_factory=list)
    turns: List[DebateTurn] = Field(default_factory=list)
    consensus: Optional[str] = Field(None, description="Synthesized consensus from Thesis Adjudicator")
    recommended_action: Optional[Literal["BUY", "SELL", "HOLD"]] = None
    conviction_score: Optional[int] = Field(None, ge=0, le=100)

    def get_formatted_history(self) -> str:
        """Format the entire debate history for LLM prompt context."""
        if not self.turns:
            return "No previous debate history."
        lines = []
        for t in self.turns:
            lines.append(f"[{t.speaker_name}] (Round {t.round_num}):\n{t.argument}\n")
        return "\n".join(lines)

    def get_latest_argument(self, speaker: Optional[str] = None) -> str:
        """Fetch the most recent argument, optionally filtered by speaker."""
        for turn in reversed(self.turns):
            if speaker is None or turn.speaker == speaker:
                return turn.argument
        return ""


class RiskPerspectiveTurn(BaseModel):
    """Single perspective statement within the Risk Committee deliberation."""

    round_num: int
    perspective: Literal["growth", "preservation", "balanced", "cro"]
    analyst_name: str
    statement: str
    timestamp: str = Field(default_factory=_utc_now_iso)


class RiskDeliberationContext(BaseModel):
    """State for Stage 4 risk deliberation and Stage 5 CRO adjudication."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    rounds: int = 0
    growth_view: str = Field("", description="Growth Perspective assessment")
    preservation_view: str = Field("", description="Preservation Perspective assessment")
    balanced_view: str = Field("", description="Balanced Perspective assessment")
    turns: List[RiskPerspectiveTurn] = Field(default_factory=list)
    cro_ruling: Optional[str] = Field(None, description="Final binding ruling from Chief Risk Officer")
    approved_action: Optional[Literal["BUY", "SELL", "HOLD"]] = None
    confidence: int = Field(50, ge=0, le=100, description="Conviction score (0-100)")
    atr_value: Optional[float] = None
    recommended_quantity: Optional[int] = None
    safety_checks_passed: bool = True

    def get_formatted_deliberation(self) -> str:
        """Format the risk committee discussion for CRO prompt context."""
        parts = []
        if self.growth_view:
            parts.append(f"### Growth Perspective:\n{self.growth_view}")
        if self.preservation_view:
            parts.append(f"### Capital Preservation Perspective:\n{self.preservation_view}")
        if self.balanced_view:
            parts.append(f"### Balanced Perspective:\n{self.balanced_view}")
        return "\n\n".join(parts) if parts else "No committee deliberation on record."


class AnalysisContext(BaseModel):
    """Top-level immutable analysis state passing through all 5 execution stages."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    job_id: str
    symbol: str
    trade_date: str
    asset_class: Literal["equity", "crypto"] = "equity"
    urgency: Literal["low", "medium", "high"] = "medium"
    lookback_days: int = 30
    selected_analysts: List[str] = Field(
        default_factory=lambda: ["technical", "sentiment", "macro", "valuation"]
    )
    market_data: Dict[str, Any] = Field(default_factory=dict)
    analyst_reports: Dict[str, str] = Field(default_factory=dict)
    thesis_context: ThesisDebateContext = Field(default_factory=ThesisDebateContext)
    order_plan: Optional[OrderPlan] = None
    risk_context: RiskDeliberationContext = Field(default_factory=RiskDeliberationContext)
    final_decision: Optional[DecisionCard] = None
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    errors: List[str] = Field(default_factory=list)
    events_log: List[Dict[str, Any]] = Field(default_factory=list)
    duration_seconds: float = 0.0
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)

    def get_situation_summary(self) -> str:
        """Combine all analyst reports into a single formatted objective situation report."""
        sections = []
        for role, report in self.analyst_reports.items():
            title = role.replace("_", " ").title()
            sections.append(f"=== {title} ===\n{report}")
        return "\n\n".join(sections) if sections else "No market reports available."

    def to_legacy_state(self) -> Dict[str, Any]:
        """Convert to legacy state dict for backward compatibility with NovaSwarmTradingGraph."""
        market_rep = self.analyst_reports.get("technical", self.analyst_reports.get("market", ""))
        sent_rep = self.analyst_reports.get("sentiment", self.analyst_reports.get("social", ""))
        news_rep = self.analyst_reports.get("macro", self.analyst_reports.get("news", ""))
        fund_rep = self.analyst_reports.get("valuation", self.analyst_reports.get("fundamentals", ""))

        invest_state = {
            "history": self.thesis_context.get_formatted_history(),
            "bull_history": "\n".join(self.thesis_context.upside_arguments),
            "bear_history": "\n".join(self.thesis_context.downside_arguments),
            "current_response": self.thesis_context.get_latest_argument(),
            "judge_decision": self.thesis_context.consensus or "",
            "count": len(self.thesis_context.turns),
        }

        risk_state = {
            "history": self.risk_context.get_formatted_deliberation(),
            "aggressive_history": self.risk_context.growth_view,
            "conservative_history": self.risk_context.preservation_view,
            "neutral_history": self.risk_context.balanced_view,
            "current_aggressive_response": self.risk_context.growth_view,
            "current_conservative_response": self.risk_context.preservation_view,
            "current_neutral_response": self.risk_context.balanced_view,
            "judge_decision": self.risk_context.cro_ruling or "",
            "count": len(self.risk_context.turns),
            "confidence": self.risk_context.confidence,
        }

        trader_plan = self.order_plan.rationale if self.order_plan else ""
        final_decision_str = (
            self.final_decision.reasoning
            if self.final_decision
            else (self.risk_context.cro_ruling or "")
        )

        return {
            "company_of_interest": self.symbol,
            "trade_date": self.trade_date,
            "market_report": market_rep,
            "sentiment_report": sent_rep,
            "news_report": news_rep,
            "fundamentals_report": fund_rep,
            "onchain_report": self.analyst_reports.get("network", ""),
            "defi_report": self.analyst_reports.get("tokenomics", ""),
            "funding_report": self.analyst_reports.get("derivatives", ""),
            "investment_debate_state": invest_state,
            "investment_plan": self.thesis_context.consensus or "",
            "trader_investment_plan": trader_plan,
            "risk_debate_state": risk_state,
            "final_trade_decision": final_decision_str,
            "final_decision": self.final_decision.model_dump() if self.final_decision else None,
            "order_plan": self.order_plan.model_dump() if self.order_plan else None,
        }

    @classmethod
    def from_legacy_state(cls, legacy: Dict[str, Any], job_id: str = "legacy-job") -> AnalysisContext:
        """Construct AnalysisContext from a legacy dictionary, preserving debate and risk deliberations."""
        reports = {}
        alias_map = {
            "market": "technical",
            "social": "sentiment",
            "sentiment": "sentiment",
            "news": "macro",
            "fundamentals": "valuation",
            "onchain": "network",
            "defi": "tokenomics",
            "funding": "derivatives",
        }
        for k in ("market", "sentiment", "news", "fundamentals", "onchain", "defi", "funding"):
            rep_key = f"{k}_report"
            val = legacy.get(rep_key)
            if val:
                reports[k] = val
                modern_k = alias_map.get(k)
                if modern_k:
                    reports[modern_k] = val

        # Extract Stage 2 debate state
        invest_state = legacy.get("investment_debate_state") or {}
        bull = legacy.get("bull_argument") or invest_state.get("bull_history") or invest_state.get("bull_argument") or ""
        bear = legacy.get("bear_argument") or invest_state.get("bear_history") or invest_state.get("bear_argument") or ""
        consensus = (
            legacy.get("investment_judge_verdict")
            or invest_state.get("judge_decision")
            or legacy.get("investment_plan")
            or None
        )

        upside_args = []
        if bull:
            if isinstance(bull, list):
                upside_args = [str(b) for b in bull]
            elif "\n" in bull:
                upside_args = [b.strip() for b in bull.split("\n") if b.strip()]
            else:
                upside_args = [bull.strip()]

        downside_args = []
        if bear:
            if isinstance(bear, list):
                downside_args = [str(b) for b in bear]
            elif "\n" in bear:
                downside_args = [b.strip() for b in bear.split("\n") if b.strip()]
            else:
                downside_args = [bear.strip()]

        debate_turns = []
        for i, arg in enumerate(upside_args, 1):
            debate_turns.append(
                DebateTurn(round_num=i, speaker="upside_advocate", speaker_name="Upside Advocate", argument=arg)
            )
        for i, arg in enumerate(downside_args, 1):
            debate_turns.append(
                DebateTurn(round_num=i, speaker="downside_advocate", speaker_name="Downside Advocate", argument=arg)
            )
        if consensus:
            debate_turns.append(
                DebateTurn(
                    round_num=max(len(upside_args), len(downside_args), 1),
                    speaker="thesis_adjudicator",
                    speaker_name="Thesis Adjudicator",
                    argument=consensus,
                )
            )

        rounds = max(len(upside_args), len(downside_args), 1) if (upside_args or downside_args) else 0
        thesis_ctx = ThesisDebateContext(
            rounds=rounds,
            upside_arguments=upside_args,
            downside_arguments=downside_args,
            turns=debate_turns,
            consensus=consensus,
        )

        # Extract Stage 4/5 risk state
        risk_state = legacy.get("risk_debate_state") or {}
        growth = (
            legacy.get("growth_view")
            or risk_state.get("current_aggressive_response")
            or risk_state.get("aggressive_history")
            or ""
        )
        preservation = (
            legacy.get("preservation_view")
            or risk_state.get("current_conservative_response")
            or risk_state.get("conservative_history")
            or ""
        )
        balanced = (
            legacy.get("balanced_view")
            or risk_state.get("current_neutral_response")
            or risk_state.get("neutral_history")
            or ""
        )
        cro = (
            legacy.get("cro_ruling")
            or risk_state.get("judge_decision")
            or legacy.get("final_trade_decision")
            or None
        )
        conf = risk_state.get("confidence", 50) if isinstance(risk_state, dict) else 50
        try:
            conf_int = int(conf)
        except (ValueError, TypeError):
            conf_int = 50

        risk_turns = []
        if growth:
            risk_turns.append(
                RiskPerspectiveTurn(
                    round_num=1, perspective="growth", analyst_name="Growth Alpha Specialist", statement=growth
                )
            )
        if preservation:
            risk_turns.append(
                RiskPerspectiveTurn(
                    round_num=1, perspective="preservation", analyst_name="Capital Preservation Officer", statement=preservation
                )
            )
        if balanced:
            risk_turns.append(
                RiskPerspectiveTurn(
                    round_num=1, perspective="balanced", analyst_name="Portfolio Risk Architect", statement=balanced
                )
            )
        if cro:
            risk_turns.append(
                RiskPerspectiveTurn(
                    round_num=1, perspective="cro", analyst_name="Chief Risk Officer", statement=cro
                )
            )

        risk_ctx = RiskDeliberationContext(
            rounds=1 if (growth or preservation or balanced or cro) else 0,
            growth_view=growth,
            preservation_view=preservation,
            balanced_view=balanced,
            turns=risk_turns,
            cro_ruling=cro,
            confidence=max(0, min(100, conf_int)),
        )

        return cls(
            job_id=job_id,
            symbol=legacy.get("company_of_interest", "UNKNOWN"),
            trade_date=str(legacy.get("trade_date", "")),
            analyst_reports=reports,
            thesis_context=thesis_ctx,
            risk_context=risk_ctx,
        )
