"""Base classes, role enumerations, and standardized execution protocols for Skopaq Intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Type, Union
from pydantic import BaseModel


class AgentRole(str, Enum):
    """Canonical role enumeration for all Skopaq Intelligence agents."""

    # Stage 1: Analysts
    TECHNICAL_ANALYST = "technical_analyst"
    SENTIMENT_ANALYST = "sentiment_analyst"
    MACRO_ANALYST = "macro_analyst"
    VALUATION_ANALYST = "valuation_analyst"
    NETWORK_ANALYST = "network_analyst"
    TOKENOMICS_ANALYST = "tokenomics_analyst"
    DERIVATIVES_ANALYST = "derivatives_analyst"

    # Stage 2: Debate
    UPSIDE_ADVOCATE = "upside_advocate"
    DOWNSIDE_ADVOCATE = "downside_advocate"
    THESIS_ADJUDICATOR = "thesis_adjudicator"

    # Stage 3: Execution
    ORDER_STRATEGIST = "order_strategist"

    # Stage 4: Risk Committee
    GROWTH_PERSPECTIVE = "growth_perspective"
    PRESERVATION_PERSPECTIVE = "preservation_perspective"
    BALANCED_PERSPECTIVE = "balanced_perspective"
    CHIEF_RISK_OFFICER = "chief_risk_officer"

    # Reflection
    POST_TRADE_REFLECTOR = "post_trade_reflector"

    # Supporting Intelligence
    CONVERSATIONAL_INTELLIGENCE = "conversational_intelligence"
    POSITION_EXIT_ANALYST = "position_exit_analyst"


LEGACY_ROLE_MAP: Dict[AgentRole, str] = {
    AgentRole.TECHNICAL_ANALYST: "market_analyst",
    AgentRole.SENTIMENT_ANALYST: "social_analyst",
    AgentRole.MACRO_ANALYST: "news_analyst",
    AgentRole.VALUATION_ANALYST: "fundamentals_analyst",
    AgentRole.NETWORK_ANALYST: "onchain_analyst",
    AgentRole.TOKENOMICS_ANALYST: "defi_analyst",
    AgentRole.DERIVATIVES_ANALYST: "funding_analyst",
    AgentRole.UPSIDE_ADVOCATE: "bull_researcher",
    AgentRole.DOWNSIDE_ADVOCATE: "bear_researcher",
    AgentRole.THESIS_ADJUDICATOR: "research_manager",
    AgentRole.ORDER_STRATEGIST: "trader",
    AgentRole.GROWTH_PERSPECTIVE: "aggressive_debator",
    AgentRole.PRESERVATION_PERSPECTIVE: "conservative_debator",
    AgentRole.BALANCED_PERSPECTIVE: "neutral_debator",
    AgentRole.CHIEF_RISK_OFFICER: "risk_manager",
    AgentRole.POST_TRADE_REFLECTOR: "reflector",
    AgentRole.CONVERSATIONAL_INTELLIGENCE: "chat_brain",
    AgentRole.POSITION_EXIT_ANALYST: "sell_analyst",
}

INVERSE_LEGACY_MAP: Dict[str, AgentRole] = {v: k for k, v in LEGACY_ROLE_MAP.items()}


def resolve_role(role_name: Union[AgentRole, str]) -> AgentRole:
    """Resolve an input role string (canonical or legacy) into an AgentRole enum."""
    if isinstance(role_name, AgentRole):
        return role_name
    role_str = str(role_name).strip().lower()
    if role_str in INVERSE_LEGACY_MAP:
        return INVERSE_LEGACY_MAP[role_str]
    for r in AgentRole:
        if r.value == role_str:
            return r
    raise ValueError(f"Unknown agent role identifier: '{role_name}'")


class SafeFormatDict(dict):
    """Dictionary providing sensible default replacements for missing template keys."""

    def __missing__(self, key: str) -> str:
        defaults = {
            "symbol": "UNKNOWN",
            "trade_date": "",
            "res_1": "N/A",
            "res_2": "N/A",
            "sup_1": "N/A",
            "sup_2": "N/A",
            "liq_upper": "N/A",
            "liq_lower": "N/A",
            "target_price": "N/A",
            "downside_target": "N/A",
            "p_bull": "N/A",
            "p_base": "N/A",
            "p_bear": "N/A",
            "entry_price": "N/A",
            "stop_loss": "N/A",
            "target_1": "N/A",
            "target_2": "N/A",
            "rr_ratio": "N/A",
            "atr_val": "N/A",
            "ACTION": "BUY/SELL/HOLD",
            "VERDICT": "APPROVE/REVISE/VETO",
            "entry": "N/A",
            "stop": "N/A",
            "target": "N/A",
            "fair_val_bear": "N/A",
            "fair_val_base": "N/A",
            "fair_val_bull": "N/A",
            "min_profit_pct": "2.0",
            "est_brokerage": "20.0",
            "net_pnl": "0.0",
            "pnl_pct": "0.0",
        }
        return defaults.get(key, f"[{key.upper()}]")


@dataclass(frozen=True)
class IntelligencePrompt:
    """Defines a standardized, institutional prompt contract for an intelligence agent."""

    role: AgentRole
    system_template: str
    required_sections: List[str]
    output_schema: Optional[Type[BaseModel]] = None

    def format_system_prompt(self, **kwargs: Any) -> str:
        """Render the system prompt with given parameter substitutions."""
        return self.system_template.format_map(SafeFormatDict(kwargs))

    def format_user_prompt(self, symbol: str, trade_date: str, context: str = "", **kwargs: Any) -> str:
        """Render a standardized contextual user prompt."""
        header = f"Analysis Target: {symbol} | Trade Date: {trade_date}\n\n"
        return f"{header}{context}".strip()
