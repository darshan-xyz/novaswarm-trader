"""Pure-Python asynchronous orchestrator replacing LangGraph StateGraph.

Coordinates the 5-stage institutional multi-agent trading pipeline:
1. Stage 1: Parallel Analysts (asyncio.gather)
2. Stage 2: Adversarial Thesis Debate (Upside Advocate vs Downside Advocate, Adjudicator)
3. Stage 3: Order Strategy Formulation (Order Strategist)
4. Stage 4: Risk Committee Deliberation (Growth, Preservation, Balanced perspectives)
5. Stage 5: Chief Risk Officer (CRO) Adjudication & ATR Position Sizing
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

from langchain_core.language_models import BaseChatModel

from novaswarm.memory.episodic import EpisodicLessonStore
from novaswarm.orchestration.context import (
    AnalysisContext,
    DebateTurn,
    RiskPerspectiveTurn,
    _utc_now_iso,
)
from novaswarm.orchestration.signal_extraction import DecisionExtractor

logger = logging.getLogger(__name__)

# Naming aliases for backwards compatibility with legacy analyst identifiers
ROLE_ALIASES = {
    "market": "technical",
    "social": "sentiment",
    "news": "macro",
    "fundamentals": "valuation",
    "onchain": "network",
    "defi": "tokenomics",
    "funding": "derivatives",
}


def _extract_text(res: Any) -> str:
    """Robustly extract text content from LangChain / Google GenAI responses."""
    content = getattr(res, "content", res)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
            elif hasattr(item, "text"):
                parts.append(str(getattr(item, "text")))
            else:
                parts.append(str(item))
        return "\n".join(parts).strip()
    return str(content).strip()


class NovaPipeline:
    """Pure async multi-agent orchestrator for institutional stock analysis."""

    def __init__(
        self,
        llm_client: Optional[BaseChatModel] = None,
        memory_store: Optional[EpisodicLessonStore] = None,
        max_debate_rounds: int = 2,
        max_risk_rounds: int = 1,
        config: Optional[Dict[str, Any]] = None,
        extractor: Optional[DecisionExtractor] = None,
    ) -> None:
        self.llm = llm_client
        self.memory_store = memory_store
        self.max_debate_rounds = max(1, min(5, max_debate_rounds))
        self.max_risk_rounds = max(1, min(5, max_risk_rounds))
        self.config = config or {}
        self.extractor = extractor or DecisionExtractor(llm=llm_client)

    async def run(
        self,
        symbol: str,
        trade_date: Optional[str] = None,
        selected_analysts: Optional[List[str]] = None,
        asset_class: str = "equity",
        urgency: str = "medium",
        lookback_days: int = 30,
        **kwargs: Any,
    ) -> AnalysisContext:
        """Execute end-to-end multi-agent pipeline and return the completed context."""
        context: Optional[AnalysisContext] = None
        async for event in self.stream(
            symbol=symbol,
            trade_date=trade_date,
            selected_analysts=selected_analysts,
            asset_class=asset_class,
            urgency=urgency,
            lookback_days=lookback_days,
            **kwargs,
        ):
            if event["event"] == "job_completed":
                context = event["data"].get("context")
            elif event["event"] == "job_failed":
                err_msg = event["data"].get("error", "Unknown pipeline error")
                raise RuntimeError(f"Pipeline execution failed for {symbol}: {err_msg}")

        if context is None:
            raise RuntimeError(f"Pipeline execution did not complete normally for {symbol}")
        return context

    async def stream(
        self,
        symbol: str,
        trade_date: Optional[str] = None,
        selected_analysts: Optional[List[str]] = None,
        asset_class: str = "equity",
        urgency: str = "medium",
        lookback_days: int = 30,
        **kwargs: Any,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream real-time Server-Sent Events (SSE) across all 5 execution stages."""
        job_id = kwargs.get("job_id") or str(uuid4())
        sym = symbol.strip().upper()
        date_str = trade_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start_time = time.monotonic()

        # Normalize analyst selection
        raw_analysts = selected_analysts or ["technical", "sentiment", "macro", "valuation"]
        norm_analysts = [ROLE_ALIASES.get(a, a) for a in raw_analysts]

        # Initialize AnalysisContext
        context = AnalysisContext(
            job_id=job_id,
            symbol=sym,
            trade_date=date_str,
            asset_class=asset_class,  # type: ignore
            urgency=urgency,          # type: ignore
            lookback_days=lookback_days,
            selected_analysts=norm_analysts,
            status="running",
        )

        try:
            # 1. Emit job_started
            yield {
                "event": "job_started",
                "data": {
                    "job_id": job_id,
                    "symbol": sym,
                    "trade_date": date_str,
                    "teams": ["analyst", "research", "trading", "risk", "portfolio"],
                    "timestamp": _utc_now_iso(),
                },
            }

            yield {
                "event": "event_log",
                "data": {
                    "level": "INFO",
                    "message": f"Starting 5-stage NovaPipeline for {sym} ({len(norm_analysts)} analysts selected)",
                    "timestamp": _utc_now_iso(),
                },
            }

            # ─────────────────────────────────────────────────────────────
            # STAGE 1: Parallel Analysts Execution (asyncio.gather)
            # ─────────────────────────────────────────────────────────────
            async for evt in self._execute_stage_1_analysts(context):
                yield evt

            # ─────────────────────────────────────────────────────────────
            # STAGE 2: Adversarial Thesis Debate (Upside vs Downside)
            # ─────────────────────────────────────────────────────────────
            async for evt in self._execute_stage_2_debate(context):
                yield evt

            # ─────────────────────────────────────────────────────────────
            # STAGE 3: Order Strategy Formulation (Order Strategist)
            # ─────────────────────────────────────────────────────────────
            async for evt in self._execute_stage_3_order_strategy(context):
                yield evt

            # ─────────────────────────────────────────────────────────────
            # STAGE 4: Risk Committee Deliberation
            # ─────────────────────────────────────────────────────────────
            async for evt in self._execute_stage_4_risk_committee(context):
                yield evt

            # ─────────────────────────────────────────────────────────────
            # STAGE 5: CRO Final Adjudication & Position Sizing
            # ─────────────────────────────────────────────────────────────
            async for evt in self._execute_stage_5_cro_adjudication(context):
                yield evt

            # Finalize Job
            duration = round(time.monotonic() - start_time, 2)
            context.duration_seconds = duration
            context.status = "completed"
            context.updated_at = _utc_now_iso()

            card = context.final_decision
            verdict = card.action if card else "HOLD"
            confidence = card.confidence if card else 50

            yield {
                "event": "job_completed",
                "data": {
                    "job_id": job_id,
                    "final_verdict": verdict,
                    "confidence": confidence,
                    "duration_seconds": duration,
                    "timestamp": _utc_now_iso(),
                    "context": context,  # internal handle for run()
                },
            }

        except Exception as exc:
            duration = round(time.monotonic() - start_time, 2)
            context.status = "failed"
            context.duration_seconds = duration
            context.errors.append(str(exc))
            logger.exception("NovaPipeline execution failed for job %s: %s", job_id, exc)

            yield {
                "event": "job_failed",
                "data": {
                    "job_id": job_id,
                    "error": str(exc),
                    "timestamp": _utc_now_iso(),
                },
            }

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 1 Implementation: Parallel Analysts
    # ─────────────────────────────────────────────────────────────────────────
    async def _execute_stage_1_analysts(
        self, context: AnalysisContext
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch market data and run all selected analysts concurrently via asyncio.gather."""
        # 1. Fetch market data & compute indicators
        yield {
            "event": "tool_call",
            "data": {
                "agent_id": "market_data_pipeline",
                "tool_name": "fetch_unified_market_data",
                "tool_args": {"symbol": context.symbol, "lookback": context.lookback_days},
                "timestamp": _utc_now_iso(),
            },
        }

        market_data = await self._fetch_market_data(context.symbol, context.lookback_days)
        context.market_data = market_data

        # Emit running status for all analysts
        for role in context.selected_analysts:
            yield {
                "event": "agent_status",
                "data": {
                    "agent_id": f"{role}_analyst",
                    "team": "analyst",
                    "status": "running",
                    "timestamp": _utc_now_iso(),
                },
            }

        # 2. Execute analysts with bounded concurrency to protect API rate limits
        sem = asyncio.Semaphore(1)

        async def _bounded_worker(r: str) -> str:
            async with sem:
                res = await self._run_analyst_worker(r, context)
                await asyncio.sleep(0.5)
                return res

        tasks = [
            asyncio.create_task(_bounded_worker(role))
            for role in context.selected_analysts
        ]
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except BaseException:
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        for role, res in zip(context.selected_analysts, results):
            if isinstance(res, Exception):
                logger.error("Analyst %s failed: %s", role, res)
                report_md = f"### {role.capitalize()} Analyst Report\n\n*Analysis unavailable due to upstream error: {res}*"
            else:
                report_md = str(res)

            context.analyst_reports[role] = report_md

            yield {
                "event": "agent_report",
                "data": {
                    "agent_id": f"{role}_analyst",
                    "team": "analyst",
                    "report_markdown": report_md,
                    "timestamp": _utc_now_iso(),
                },
            }

            yield {
                "event": "agent_status",
                "data": {
                    "agent_id": f"{role}_analyst",
                    "team": "analyst",
                    "status": "completed",
                    "timestamp": _utc_now_iso(),
                },
            }

        yield {
            "event": "event_log",
            "data": {
                "level": "INFO",
                "message": f"Stage 1 Fan-in complete: {len(context.analyst_reports)} reports aggregated.",
                "timestamp": _utc_now_iso(),
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 2 Implementation: Adversarial Debate
    # ─────────────────────────────────────────────────────────────────────────
    async def _execute_stage_2_debate(
        self, context: AnalysisContext
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute bounded adversarial debate between Upside Advocate and Downside Advocate."""
        past_memories = ""
        if self.memory_store:
            matches = self.memory_store.get_memories(context.get_situation_summary(), n_matches=2)
            if matches:
                past_memories = "\n\n".join([str(m) for m in matches])

        for round_idx in range(1, self.max_debate_rounds + 1):
            context.thesis_context.rounds = round_idx

            # 1. Upside Advocate
            yield {
                "event": "agent_status",
                "data": {"agent_id": "bull_researcher", "team": "research", "status": "running", "timestamp": _utc_now_iso()},
            }
            upside_arg = await self._run_upside_advocate(context, past_memories, round_idx)
            context.thesis_context.upside_arguments.append(upside_arg)
            context.thesis_context.turns.append(
                DebateTurn(round_num=round_idx, speaker="upside_advocate", speaker_name="Upside Advocate", argument=upside_arg)
            )
            yield {
                "event": "agent_report",
                "data": {"agent_id": "bull_researcher", "team": "research", "report_markdown": upside_arg, "timestamp": _utc_now_iso()},
            }
            yield {
                "event": "agent_status",
                "data": {"agent_id": "bull_researcher", "team": "research", "status": "completed", "timestamp": _utc_now_iso()},
            }

            # 2. Downside Advocate
            yield {
                "event": "agent_status",
                "data": {"agent_id": "bear_researcher", "team": "research", "status": "running", "timestamp": _utc_now_iso()},
            }
            downside_arg = await self._run_downside_advocate(context, past_memories, round_idx)
            context.thesis_context.downside_arguments.append(downside_arg)
            context.thesis_context.turns.append(
                DebateTurn(round_num=round_idx, speaker="downside_advocate", speaker_name="Downside Advocate", argument=downside_arg)
            )
            yield {
                "event": "agent_report",
                "data": {"agent_id": "bear_researcher", "team": "research", "report_markdown": downside_arg, "timestamp": _utc_now_iso()},
            }
            yield {
                "event": "agent_status",
                "data": {"agent_id": "bear_researcher", "team": "research", "status": "completed", "timestamp": _utc_now_iso()},
            }

        # 3. Thesis Adjudicator
        yield {
            "event": "agent_status",
            "data": {"agent_id": "research_manager", "team": "research", "status": "running", "timestamp": _utc_now_iso()},
        }
        consensus_text = await self._run_thesis_adjudicator(context, past_memories)
        context.thesis_context.consensus = consensus_text
        context.thesis_context.turns.append(
            DebateTurn(
                round_num=self.max_debate_rounds,
                speaker="thesis_adjudicator",
                speaker_name="Thesis Adjudicator",
                argument=consensus_text,
            )
        )
        yield {
            "event": "agent_report",
            "data": {"agent_id": "research_manager", "team": "research", "report_markdown": consensus_text, "timestamp": _utc_now_iso()},
        }
        yield {
            "event": "agent_status",
            "data": {"agent_id": "research_manager", "team": "research", "status": "completed", "timestamp": _utc_now_iso()},
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 3 Implementation: Order Strategy
    # ─────────────────────────────────────────────────────────────────────────
    async def _execute_stage_3_order_strategy(
        self, context: AnalysisContext
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Formulate execution order strategy based on thesis consensus."""
        yield {
            "event": "agent_status",
            "data": {"agent_id": "trader", "team": "trading", "status": "running", "timestamp": _utc_now_iso()},
        }

        order_plan_text = await self._run_order_strategist(context)
        parsed_plan = self.extractor.extract_order_plan(order_plan_text, context)
        context.order_plan = parsed_plan

        yield {
            "event": "agent_report",
            "data": {"agent_id": "trader", "team": "trading", "report_markdown": order_plan_text, "timestamp": _utc_now_iso()},
        }
        yield {
            "event": "agent_status",
            "data": {"agent_id": "trader", "team": "trading", "status": "completed", "timestamp": _utc_now_iso()},
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 4 Implementation: Risk Committee Deliberation
    # ─────────────────────────────────────────────────────────────────────────
    async def _execute_stage_4_risk_committee(
        self, context: AnalysisContext
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Deliberate order plan across Growth, Preservation, and Balanced perspectives."""
        perspectives = [
            ("aggressive_debator", "Growth Perspective", self._run_growth_perspective),
            ("conservative_debator", "Capital Preservation", self._run_preservation_perspective),
            ("neutral_debator", "Balanced Perspective", self._run_balanced_perspective),
        ]

        for agent_id, name, runner in perspectives:
            yield {
                "event": "agent_status",
                "data": {"agent_id": agent_id, "team": "risk", "status": "running", "timestamp": _utc_now_iso()},
            }
            statement = await runner(context)
            if "Growth" in name:
                context.risk_context.growth_view = statement
                persp_key = "growth"
            elif "Preservation" in name:
                context.risk_context.preservation_view = statement
                persp_key = "preservation"
            else:
                context.risk_context.balanced_view = statement
                persp_key = "balanced"

            context.risk_context.turns.append(
                RiskPerspectiveTurn(
                    round_num=1,
                    perspective=persp_key,  # type: ignore
                    analyst_name=name,
                    statement=statement,
                )
            )

            yield {
                "event": "agent_report",
                "data": {"agent_id": agent_id, "team": "risk", "report_markdown": statement, "timestamp": _utc_now_iso()},
            }
            yield {
                "event": "agent_status",
                "data": {"agent_id": agent_id, "team": "risk", "status": "completed", "timestamp": _utc_now_iso()},
            }

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 5 Implementation: CRO Final Adjudication & Sizing
    # ─────────────────────────────────────────────────────────────────────────
    async def _execute_stage_5_cro_adjudication(
        self, context: AnalysisContext
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Chief Risk Officer issues final ruling, calculates ATR position sizing, and synthesizes DecisionCard."""
        yield {
            "event": "agent_status",
            "data": {"agent_id": "risk_judge", "team": "risk", "status": "running", "timestamp": _utc_now_iso()},
        }

        cro_ruling = await self._run_chief_risk_officer(context)
        context.risk_context.cro_ruling = cro_ruling

        confidence = self.extractor.extract_confidence(cro_ruling, default=50)
        action = self.extractor.extract_action(cro_ruling)
        context.risk_context.confidence = confidence
        context.risk_context.approved_action = action  # type: ignore

        decision_card = self.extractor.extract_decision_card(
            context=context,
            portfolio_equity=float(self.config.get("portfolio_equity", 100000.0)),
        )
        context.final_decision = decision_card

        yield {
            "event": "agent_report",
            "data": {"agent_id": "risk_judge", "team": "risk", "report_markdown": cro_ruling, "timestamp": _utc_now_iso()},
        }
        yield {
            "event": "agent_status",
            "data": {"agent_id": "risk_judge", "team": "risk", "status": "completed", "timestamp": _utc_now_iso()},
        }

        # Portfolio Management Final Event
        yield {
            "event": "agent_status",
            "data": {"agent_id": "portfolio_manager", "team": "portfolio", "status": "completed", "timestamp": _utc_now_iso()},
        }

        # Emit decision_card
        yield {
            "event": "decision_card",
            "data": decision_card.model_dump(),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Helper LLM Invocations
    # ─────────────────────────────────────────────────────────────────────────
    async def _fetch_market_data(self, symbol: str, lookback: int) -> Dict[str, Any]:
        """Fetch market data via novaswarm.data.

        Raises RuntimeError if real market quotes cannot be retrieved.
        """
        from novaswarm.data import get_news, get_quote
        try:
            quote = get_quote(symbol)
            if not quote or quote.ltp is None or float(quote.ltp) <= 0:
                raise RuntimeError(f"No valid price quote available for {symbol}")
            news = get_news(symbol, look_back_days=lookback)
            return {
                "symbol": symbol,
                "current_price": float(quote.ltp),
                "news_count": len(news) if news else 0,
                "summary": f"Market Data for {symbol}: Price Rs. {quote.ltp:,.2f}",
            }
        except Exception as e:
            logger.error("Unified market data fetch failed for %s: %s", symbol, e)
            raise RuntimeError(f"Unable to fetch real market data for {symbol}: {e}") from e

    async def _run_analyst_worker(self, role: str, context: AnalysisContext) -> str:
        """Invoke analyst agent using prompt template or LLM."""
        prompt = (
            f"You are the Lead {role.capitalize()} Analyst for Indian Equities. "
            f"Provide a rigorous, institutional analysis for {context.symbol} on {context.trade_date}.\n\n"
            f"Market Context:\n{context.market_data}\n\n"
            f"Structure your response with:\n"
            f"### Executive Summary\n"
            f"### Quantitative Findings\n"
            f"### Catalyst & Risk Invalidation Levels\n"
            f"### Outlook & Conviction"
        )
        if self.llm:
            res = await self.llm.ainvoke(prompt)
            return _extract_text(res)
        raise RuntimeError(f"LLM client required to execute {role} analyst report for {context.symbol}.")

    async def _run_upside_advocate(self, context: AnalysisContext, memories: str, round_num: int) -> str:
        prompt = (
            f"You are the Upside Advocate presenting the Bull Thesis for {context.symbol} (Round {round_num}).\n"
            f"Analyst Reports:\n{context.get_situation_summary()}\n\n"
            f"Past Lessons Learned:\n{memories}\n\n"
            f"Present a high-conviction, evidence-backed bull thesis highlighting catalysts, margin expansion, and valuation upside."
        )
        if self.llm:
            res = await self.llm.ainvoke(prompt)
            return _extract_text(res)
        raise RuntimeError(f"LLM client required to execute upside advocate debate for {context.symbol}.")

    async def _run_downside_advocate(self, context: AnalysisContext, memories: str, round_num: int) -> str:
        prompt = (
            f"You are the Downside Advocate presenting the Bear Counter-Thesis for {context.symbol} (Round {round_num}).\n"
            f"Latest Bull Argument:\n{context.thesis_context.get_latest_argument('upside_advocate')}\n\n"
            f"Present rigorous downside counterpoints focusing on valuation friction, sector headwinds, and risk of false breakout."
        )
        if self.llm:
            res = await self.llm.ainvoke(prompt)
            return _extract_text(res)
        raise RuntimeError(f"LLM client required to execute downside advocate debate for {context.symbol}.")

    async def _run_thesis_adjudicator(self, context: AnalysisContext, memories: str) -> str:
        prompt = (
            f"You are the Chief Thesis Adjudicator reviewing the debate between Upside and Downside advocates for {context.symbol}.\n"
            f"Debate History:\n{context.thesis_context.get_formatted_history()}\n\n"
            f"Past Lessons:\n{memories}\n\n"
            f"Deliver an unambiguous synthesis with a clear investment recommendation: BUY, SELL, or HOLD, and strategic guidance."
        )
        if self.llm:
            res = await self.llm.ainvoke(prompt)
            return _extract_text(res)
        raise RuntimeError(f"LLM client required to execute thesis adjudication for {context.symbol}.")

    async def _run_order_strategist(self, context: AnalysisContext) -> str:
        curr_p = context.market_data.get("current_price")
        if not curr_p or float(curr_p) <= 0:
            raise RuntimeError(f"Valid current market price required for order strategy on {context.symbol}.")
        prompt = (
            f"You are the Senior Order Strategist. Formulate a precise execution plan for {context.symbol} (Current Price: ₹{curr_p}).\n"
            f"Consensus Thesis:\n{context.thesis_context.consensus}\n\n"
            f"Specify:\n"
            f"- Action: BUY, SELL, or HOLD\n"
            f"- Entry Price: specific level\n"
            f"- Stop Loss: ATR-based invalidation level\n"
            f"- Target: profit target (minimum 2:1 R:R)\n"
            f"- Timeframe and execution trigger.\n"
            f"Conclude with: FINAL TRANSACTION PROPOSAL: **BUY/SELL/HOLD**"
        )
        if self.llm:
            res = await self.llm.ainvoke(prompt)
            return _extract_text(res)
        raise RuntimeError(f"LLM client required to formulate order strategy for {context.symbol}.")

    async def _run_growth_perspective(self, context: AnalysisContext) -> str:
        if self.llm:
            prompt = f"You represent the Growth Perspective on the risk committee for {context.symbol}."
            res = await self.llm.ainvoke(prompt)
            return _extract_text(res)
        raise RuntimeError(f"LLM client required for Growth Perspective on {context.symbol}.")

    async def _run_preservation_perspective(self, context: AnalysisContext) -> str:
        if self.llm:
            prompt = f"You represent the Capital Preservation Perspective on the risk committee for {context.symbol}."
            res = await self.llm.ainvoke(prompt)
            return _extract_text(res)
        raise RuntimeError(f"LLM client required for Capital Preservation Perspective on {context.symbol}.")

    async def _run_balanced_perspective(self, context: AnalysisContext) -> str:
        if self.llm:
            prompt = f"You represent the Balanced Perspective on the risk committee for {context.symbol}."
            res = await self.llm.ainvoke(prompt)
            return _extract_text(res)
        raise RuntimeError(f"LLM client required for Balanced Perspective on {context.symbol}.")

    async def _run_chief_risk_officer(self, context: AnalysisContext) -> str:
        prompt = (
            f"As Chief Risk Officer (CRO), review the Order Strategy and Risk Committee Deliberations for {context.symbol}.\n"
            f"Order Plan:\n{context.order_plan.model_dump() if context.order_plan else 'N/A'}\n\n"
            f"Risk Committee Opinions:\n{context.risk_context.get_formatted_deliberation()}\n\n"
            f"Issue a binding ruling: BUY, SELL, or HOLD.\n"
            f"Conclude with your conviction on the final line in this exact format:\n"
            f"CONFIDENCE: <0-100>"
        )
        if self.llm:
            res = await self.llm.ainvoke(prompt)
            return _extract_text(res)
        raise RuntimeError(f"LLM client required for Chief Risk Officer adjudication on {context.symbol}.")
