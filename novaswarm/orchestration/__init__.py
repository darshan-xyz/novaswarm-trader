"""NovaSwarm Clean-Room Pure-Python Orchestration Engine.

Exports:
- NovaPipeline: Pure-Python async multi-agent 5-stage orchestrator
- AnalysisContext, OrderPlan, ThesisDebateContext, RiskDeliberationContext: Pydantic V2 state models
- PostTradeReflector: Post-trade episodic reflection engine
- DecisionExtractor: Institutional decision parsing and DecisionCard synthesis
"""

from novaswarm.orchestration.context import (
    AnalysisContext,
    DebateTurn,
    OrderPlan,
    RiskDeliberationContext,
    RiskPerspectiveTurn,
    ThesisDebateContext,
)
from novaswarm.orchestration.engine import NovaPipeline
from novaswarm.orchestration.reflection import PostTradeReflector
from novaswarm.orchestration.signal_extraction import DecisionExtractor

__all__ = [
    "AnalysisContext",
    "DebateTurn",
    "OrderPlan",
    "RiskDeliberationContext",
    "RiskPerspectiveTurn",
    "ThesisDebateContext",
    "NovaPipeline",
    "PostTradeReflector",
    "DecisionExtractor",
]
