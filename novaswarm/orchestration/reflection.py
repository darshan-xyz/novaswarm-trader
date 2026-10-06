"""Post-trade reflection and continuous episodic learning engine.

Clean-room, pure Python component that evaluates realized trade outcomes and writes
structured lessons into EpisodicLessonStore.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
from typing import Any, Dict, Optional, Union

from langchain_core.language_models import BaseChatModel

from novaswarm.memory.episodic import EpisodicLessonStore
from novaswarm.orchestration.context import AnalysisContext

logger = logging.getLogger(__name__)

CLEAN_ROOM_REFLECTION_SYSTEM_PROMPT = """You are the Senior Quantitative Performance Reviewer for an institutional trading desk.
Your mandate is to conduct a forensic, objective post-mortem on a closed trading position and distill actionable Episodic Lessons.

Evaluation Methodology:
1. Outcome Attribution: Compare the realized P&L and holding period against the original thesis and risk parameters.
2. Signal Verification: Identify which technical, fundamental, sentiment, or risk inputs correctly forecasted price action, and which provided deceptive signals.
3. Invalidation Quality: Assess whether the stop-loss or profit-target was placed optimally relative to underlying asset volatility (ATR).
4. Concrete Prescription: Formulate specific, actionable heuristics (e.g. "Do not enter momentum breakout when RSI > 75 on divergent volume").
5. Search Query: Provide a single condensed situation description under 100 words capturing the market environment for future episodic retrieval.

Adhere strictly to professional, concise institutional language."""


class PostTradeReflector:
    """Evaluates completed trades and generates persistent lessons for episodic memory."""

    def __init__(self, llm: Optional[BaseChatModel] = None) -> None:
        self.llm = llm

    async def areflect_and_remember(
        self,
        state_or_context: Union[AnalysisContext, Dict[str, Any]],
        returns_losses: Union[Dict[str, Any], float],
        memory_store: Optional[EpisodicLessonStore] = None,
    ) -> Dict[str, str]:
        """Asynchronously reflect on a closed position and update memory store."""
        situation = self._extract_situation(state_or_context)
        trade_summary = self._format_trade_result(returns_losses)

        roles_to_review = [
            ("upside_advocate", "Bull Thesis / Upside Advocate"),
            ("downside_advocate", "Bear Thesis / Downside Advocate"),
            ("order_strategist", "Order Strategy & Execution"),
            ("chief_risk_officer", "CRO & Risk Committee"),
        ]

        lessons: Dict[str, str] = {}
        for role_key, role_label in roles_to_review:
            analysis_text = self._extract_role_text(state_or_context, role_key)
            lesson = await self._generate_reflection(role_label, analysis_text, situation, trade_summary)
            lessons[role_key] = lesson

            if memory_store is not None:
                meta = {
                    "role": role_key,
                    "trade_result": str(returns_losses),
                    "timestamp": time.time(),
                }
                if hasattr(memory_store, "add_situations"):
                    memory_store.add_situations([(situation, lesson)], metadata=[meta])
                elif hasattr(memory_store, "add_lesson"):
                    memory_store.add_lesson(situation=situation, recommendation=lesson, metadata=meta)

        return lessons

    def reflect_and_remember(
        self,
        state_or_context: Union[AnalysisContext, Dict[str, Any]],
        returns_losses: Union[Dict[str, Any], float],
        memory_store: Optional[EpisodicLessonStore] = None,
    ) -> Dict[str, str]:
        """Synchronous wrapper for backward compatibility with NovaSwarmTradingGraph.reflect()."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    self.areflect_and_remember(state_or_context, returns_losses, memory_store),
                )
                return future.result(timeout=60.0)
        else:
            return asyncio.run(
                self.areflect_and_remember(state_or_context, returns_losses, memory_store)
            )

    def _extract_situation(self, state_or_context: Union[AnalysisContext, Dict[str, Any]]) -> str:
        """Extract objective market situation string."""
        if isinstance(state_or_context, AnalysisContext):
            return state_or_context.get_situation_summary()
        elif isinstance(state_or_context, dict):
            m = state_or_context.get("market_report", "")
            s = state_or_context.get("sentiment_report", "")
            n = state_or_context.get("news_report", "")
            f = state_or_context.get("fundamentals_report", "")
            return f"{m}\n\n{s}\n\n{n}\n\n{f}".strip()
        return "Market situation context unavailable."

    def _extract_role_text(self, state_or_context: Union[AnalysisContext, Dict[str, Any]], role: str) -> str:
        """Extract decision text associated with a specific role."""
        if isinstance(state_or_context, AnalysisContext):
            if role == "upside_advocate":
                return "\n".join(state_or_context.thesis_context.upside_arguments)
            elif role == "downside_advocate":
                return "\n".join(state_or_context.thesis_context.downside_arguments)
            elif role == "order_strategist":
                return state_or_context.order_plan.rationale if state_or_context.order_plan else ""
            elif role == "chief_risk_officer":
                return state_or_context.risk_context.cro_ruling or ""
        elif isinstance(state_or_context, dict):
            if role == "upside_advocate":
                return state_or_context.get("investment_debate_state", {}).get("bull_history", "")
            elif role == "downside_advocate":
                return state_or_context.get("investment_debate_state", {}).get("bear_history", "")
            elif role == "order_strategist":
                return state_or_context.get("trader_investment_plan", "")
            elif role == "chief_risk_officer":
                return state_or_context.get("risk_debate_state", {}).get("judge_decision", "")
        return ""

    def _format_trade_result(self, res: Union[Dict[str, Any], float]) -> str:
        if isinstance(res, (int, float)):
            return f"Realized Return/P&L: ₹{res:+.2f}"
        if isinstance(res, dict):
            return f"Realized P&L: ₹{res.get('pnl', '0.0')} | Return: {res.get('return_pct', '0.0')}% | Exit Reason: {res.get('exit_reason', 'N/A')}"
        return str(res)

    async def _generate_reflection(self, role: str, analysis: str, situation: str, result: str) -> str:
        """Generate reflection text using LLM or structured fallback."""
        if not self.llm:
            return f"Lesson for {role}: When trade outcome is {result}, re-evaluate volatility stops and confirmation filters."

        prompt = (
            f"{CLEAN_ROOM_REFLECTION_SYSTEM_PROMPT}\n\n"
            f"Role Being Evaluated: {role}\n"
            f"Original Analysis/Decision:\n{analysis}\n\n"
            f"Trade Outcome:\n{result}\n\n"
            f"Market Context at Time of Trade:\n{situation}"
        )
        try:
            res = await self.llm.ainvoke(prompt)
            return res.content if hasattr(res, "content") else str(res)
        except Exception as exc:
            logger.warning("LLM reflection failed: %s", exc)
            return f"Heuristic Lesson: Align entry timing with market regime to optimize {result}."
