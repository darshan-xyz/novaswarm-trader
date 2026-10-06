"""Skopaq Multi-Agent Intelligence Architecture.

Clean-room institutional system prompts, prompt contracts, and role definitions for
the 5-stage NovaPipeline trading graph.
"""

from __future__ import annotations

from typing import Any, Dict, List, Union

from skopaq.intelligence.analysts.derivatives import (
    DERIVATIVES_PROMPT,
    DERIVATIVES_SYSTEM_PROMPT,
)
from skopaq.intelligence.analysts.macro import (
    MACRO_PROMPT,
    MACRO_SYSTEM_PROMPT,
)
from skopaq.intelligence.analysts.network import (
    NETWORK_PROMPT,
    NETWORK_SYSTEM_PROMPT,
)
from skopaq.intelligence.analysts.sentiment import (
    SENTIMENT_PROMPT,
    SENTIMENT_SYSTEM_PROMPT,
)
from skopaq.intelligence.analysts.technical import (
    TECHNICAL_PROMPT,
    TECHNICAL_SYSTEM_PROMPT,
)
from skopaq.intelligence.analysts.tokenomics import (
    TOKENOMICS_PROMPT,
    TOKENOMICS_SYSTEM_PROMPT,
)
from skopaq.intelligence.analysts.valuation import (
    VALUATION_PROMPT,
    VALUATION_SYSTEM_PROMPT,
)
from skopaq.intelligence.base import (
    AgentRole,
    INVERSE_LEGACY_MAP,
    IntelligencePrompt,
    LEGACY_ROLE_MAP,
    resolve_role,
)
from skopaq.intelligence.conversational import (
    CONVERSATIONAL_PROMPT,
    CONVERSATIONAL_SYSTEM_PROMPT,
)
from skopaq.intelligence.debate.adjudicator import (
    THESIS_ADJUDICATOR_PROMPT,
    THESIS_ADJUDICATOR_SYSTEM_PROMPT,
)
from skopaq.intelligence.debate.advocate import (
    DOWNSIDE_ADVOCATE_PROMPT,
    DOWNSIDE_ADVOCATE_SYSTEM_PROMPT,
    UPSIDE_ADVOCATE_PROMPT,
    UPSIDE_ADVOCATE_SYSTEM_PROMPT,
)
from skopaq.intelligence.execution.order_strategist import (
    ORDER_STRATEGIST_PROMPT,
    ORDER_STRATEGIST_SYSTEM_PROMPT,
)
from skopaq.intelligence.execution.position_exit import (
    POSITION_EXIT_PROMPT,
    POSITION_EXIT_SYSTEM_PROMPT,
)
from skopaq.intelligence.risk_committee.chief_risk import (
    CHIEF_RISK_OFFICER_PROMPT,
    CHIEF_RISK_OFFICER_SYSTEM_PROMPT,
)
from skopaq.intelligence.risk_committee.perspectives import (
    BALANCED_PERSPECTIVE_PROMPT,
    BALANCED_PERSPECTIVE_SYSTEM_PROMPT,
    GROWTH_PERSPECTIVE_PROMPT,
    GROWTH_PERSPECTIVE_SYSTEM_PROMPT,
    PRESERVATION_PERSPECTIVE_PROMPT,
    PRESERVATION_PERSPECTIVE_SYSTEM_PROMPT,
)

# Reflector System Prompt
REFLECTOR_SYSTEM_PROMPT = """\
You are the Senior Quantitative Performance Reviewer for an institutional trading desk.
Your mandate is to conduct a forensic, objective post-mortem on a closed trading position and distill actionable Episodic Lessons.

Evaluation Methodology:
1. Outcome Attribution: Compare the realized P&L and holding period against the original thesis and risk parameters.
2. Signal Verification: Identify which technical, fundamental, sentiment, or risk inputs correctly forecasted price action, and which provided deceptive signals.
3. Invalidation Quality: Assess whether the stop-loss or profit-target was placed optimally relative to underlying asset volatility (ATR).
4. Concrete Prescription: Formulate specific, actionable heuristics (e.g. "Do not enter momentum breakout when RSI > 75 on divergent volume").
5. Search Query: Provide a single condensed situation description under 100 words capturing the market environment for future episodic retrieval.

Adhere strictly to professional, concise institutional language."""

REFLECTOR_PROMPT = IntelligencePrompt(
    role=AgentRole.POST_TRADE_REFLECTOR,
    system_template=REFLECTOR_SYSTEM_PROMPT,
    required_sections=[
        "Outcome Attribution",
        "Signal Verification",
        "Invalidation Quality",
        "Concrete Prescription",
    ],
)

ALL_PROMPT_ROLES: List[str] = [
    "technical_analyst",
    "sentiment_analyst",
    "macro_analyst",
    "valuation_analyst",
    "network_analyst",
    "tokenomics_analyst",
    "derivatives_analyst",
    "upside_advocate",
    "downside_advocate",
    "thesis_adjudicator",
    "order_strategist",
    "growth_perspective",
    "preservation_perspective",
    "balanced_perspective",
    "chief_risk_officer",
    "post_trade_reflector",
]

ROLE_PROMPTS: Dict[AgentRole, IntelligencePrompt] = {
    AgentRole.TECHNICAL_ANALYST: TECHNICAL_PROMPT,
    AgentRole.SENTIMENT_ANALYST: SENTIMENT_PROMPT,
    AgentRole.MACRO_ANALYST: MACRO_PROMPT,
    AgentRole.VALUATION_ANALYST: VALUATION_PROMPT,
    AgentRole.NETWORK_ANALYST: NETWORK_PROMPT,
    AgentRole.TOKENOMICS_ANALYST: TOKENOMICS_PROMPT,
    AgentRole.DERIVATIVES_ANALYST: DERIVATIVES_PROMPT,
    AgentRole.UPSIDE_ADVOCATE: UPSIDE_ADVOCATE_PROMPT,
    AgentRole.DOWNSIDE_ADVOCATE: DOWNSIDE_ADVOCATE_PROMPT,
    AgentRole.THESIS_ADJUDICATOR: THESIS_ADJUDICATOR_PROMPT,
    AgentRole.ORDER_STRATEGIST: ORDER_STRATEGIST_PROMPT,
    AgentRole.GROWTH_PERSPECTIVE: GROWTH_PERSPECTIVE_PROMPT,
    AgentRole.PRESERVATION_PERSPECTIVE: PRESERVATION_PERSPECTIVE_PROMPT,
    AgentRole.BALANCED_PERSPECTIVE: BALANCED_PERSPECTIVE_PROMPT,
    AgentRole.CHIEF_RISK_OFFICER: CHIEF_RISK_OFFICER_PROMPT,
    AgentRole.POST_TRADE_REFLECTOR: REFLECTOR_PROMPT,
    AgentRole.CONVERSATIONAL_INTELLIGENCE: CONVERSATIONAL_PROMPT,
    AgentRole.POSITION_EXIT_ANALYST: POSITION_EXIT_PROMPT,
}


def get_prompt_for_role(role: Union[AgentRole, str], **kwargs: Any) -> str:
    """Retrieve and format the system prompt for a canonical or legacy role."""
    resolved = resolve_role(role)
    prompt_contract = ROLE_PROMPTS[resolved]
    return prompt_contract.format_system_prompt(**kwargs)


# ── Individual Role Prompt Getters ──────────────────────────────────────────


def get_technical_analyst_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return TECHNICAL_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_sentiment_analyst_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return SENTIMENT_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_macro_analyst_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return MACRO_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_valuation_analyst_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return VALUATION_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_network_analyst_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return NETWORK_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_tokenomics_analyst_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return TOKENOMICS_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_derivatives_analyst_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return DERIVATIVES_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_upside_advocate_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return UPSIDE_ADVOCATE_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_downside_advocate_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return DOWNSIDE_ADVOCATE_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_adjudicator_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return THESIS_ADJUDICATOR_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_order_strategist_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return ORDER_STRATEGIST_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_growth_perspective_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return GROWTH_PERSPECTIVE_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_preservation_perspective_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return PRESERVATION_PERSPECTIVE_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_balanced_perspective_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return BALANCED_PERSPECTIVE_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_cro_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return CHIEF_RISK_OFFICER_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_reflector_prompt(**kwargs: Any) -> str:
    return REFLECTOR_PROMPT.format_system_prompt(**kwargs)


def get_conversational_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return CONVERSATIONAL_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


def get_position_exit_prompt(symbol: str = "UNKNOWN", trade_date: str = "", **kwargs: Any) -> str:
    return POSITION_EXIT_PROMPT.format_system_prompt(symbol=symbol, trade_date=trade_date, **kwargs)


__all__ = [
    "AgentRole",
    "IntelligencePrompt",
    "LEGACY_ROLE_MAP",
    "INVERSE_LEGACY_MAP",
    "resolve_role",
    "get_prompt_for_role",
    "ROLE_PROMPTS",
    "ALL_PROMPT_ROLES",
    # Prompts
    "TECHNICAL_PROMPT",
    "TECHNICAL_SYSTEM_PROMPT",
    "SENTIMENT_PROMPT",
    "SENTIMENT_SYSTEM_PROMPT",
    "MACRO_PROMPT",
    "MACRO_SYSTEM_PROMPT",
    "VALUATION_PROMPT",
    "VALUATION_SYSTEM_PROMPT",
    "NETWORK_PROMPT",
    "NETWORK_SYSTEM_PROMPT",
    "TOKENOMICS_PROMPT",
    "TOKENOMICS_SYSTEM_PROMPT",
    "DERIVATIVES_PROMPT",
    "DERIVATIVES_SYSTEM_PROMPT",
    "UPSIDE_ADVOCATE_PROMPT",
    "UPSIDE_ADVOCATE_SYSTEM_PROMPT",
    "DOWNSIDE_ADVOCATE_PROMPT",
    "DOWNSIDE_ADVOCATE_SYSTEM_PROMPT",
    "THESIS_ADJUDICATOR_PROMPT",
    "THESIS_ADJUDICATOR_SYSTEM_PROMPT",
    "ORDER_STRATEGIST_PROMPT",
    "ORDER_STRATEGIST_SYSTEM_PROMPT",
    "POSITION_EXIT_PROMPT",
    "POSITION_EXIT_SYSTEM_PROMPT",
    "GROWTH_PERSPECTIVE_PROMPT",
    "GROWTH_PERSPECTIVE_SYSTEM_PROMPT",
    "PRESERVATION_PERSPECTIVE_PROMPT",
    "PRESERVATION_PERSPECTIVE_SYSTEM_PROMPT",
    "BALANCED_PERSPECTIVE_PROMPT",
    "BALANCED_PERSPECTIVE_SYSTEM_PROMPT",
    "CHIEF_RISK_OFFICER_PROMPT",
    "CHIEF_RISK_OFFICER_SYSTEM_PROMPT",
    "REFLECTOR_PROMPT",
    "REFLECTOR_SYSTEM_PROMPT",
    "CONVERSATIONAL_PROMPT",
    "CONVERSATIONAL_SYSTEM_PROMPT",
    # Functions
    "get_technical_analyst_prompt",
    "get_sentiment_analyst_prompt",
    "get_macro_analyst_prompt",
    "get_valuation_analyst_prompt",
    "get_network_analyst_prompt",
    "get_tokenomics_analyst_prompt",
    "get_derivatives_analyst_prompt",
    "get_upside_advocate_prompt",
    "get_downside_advocate_prompt",
    "get_adjudicator_prompt",
    "get_order_strategist_prompt",
    "get_growth_perspective_prompt",
    "get_preservation_perspective_prompt",
    "get_balanced_perspective_prompt",
    "get_cro_prompt",
    "get_reflector_prompt",
    "get_conversational_prompt",
    "get_position_exit_prompt",
]
