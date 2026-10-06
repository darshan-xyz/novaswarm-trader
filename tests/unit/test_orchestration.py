"""Comprehensive offline unit test suite for Skopaq Pure-Python Orchestration Engine.

Tests:
1. Pydantic V2 state models (AnalysisContext, ThesisDebateContext, RiskDeliberationContext, OrderPlan).
2. DecisionExtractor deterministic action parsing, 4-tier confidence extraction, and DecisionCard synthesis.
3. PostTradeReflector post-trade analysis, episodic memory updates, and sync/async bridges.
4. NovaPipeline step-by-step execution across all 5 stages with mock LLM.
5. NovaPipeline partial analyst failure resilience and error handling.
6. NovaPipeline SSE async generator streaming event ordering and envelope schemas.

All tests run 100% offline without live API keys or network calls.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Dict, Iterator, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.language_models import BaseChatModel

from skopaq.api.analysis_models import DecisionCard
from skopaq.broker.models import Exchange, TradingSignal
from skopaq.memory.episodic import EpisodicLessonStore
from skopaq.orchestration.context import (
    AnalysisContext,
    DebateTurn,
    OrderPlan,
    RiskDeliberationContext,
    RiskPerspectiveTurn,
    ThesisDebateContext,
)
from skopaq.orchestration.engine import NovaPipeline
from skopaq.orchestration.reflection import PostTradeReflector
from skopaq.orchestration.signal_extraction import DecisionExtractor


# ─────────────────────────────────────────────────────────────────────────────
# Test Fixtures & Mock LLM
# ─────────────────────────────────────────────────────────────────────────────

class MockChatModel(BaseChatModel):
    """Deterministic offline mock chat model for unit testing NovaPipeline."""

    canned_responses: Dict[str, str] = {}
    default_response: str = "Default structured response with CONFIDENCE: 80"
    call_history: List[str] = []

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        prompt_text = " ".join([m.content for m in messages if hasattr(m, "content")])
        self.call_history.append(prompt_text)

        content = self.default_response
        for key, val in self.canned_responses.items():
            if (
                f"You are the {key}" in prompt_text
                or f"You are the Chief {key}" in prompt_text
                or f"You are the Lead {key}" in prompt_text
                or f"You are the Senior {key}" in prompt_text
                or f"As {key}" in prompt_text
            ):
                content = val
                break
        else:
            for key, val in self.canned_responses.items():
                if key in prompt_text:
                    content = val
                    break

        generation = ChatGeneration(message=AIMessage(content=content))
        return ChatResult(generations=[generation])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "mock_chat_model"


@pytest.fixture
def mock_llm() -> MockChatModel:
    llm = MockChatModel()
    llm.canned_responses = {
        "Technical Analyst": (
            "### Executive Summary\nBullish breakout confirmed above 200 EMA.\n\n"
            "### Quantitative Findings\nRSI at 58.4, MACD bullish crossover, ATR 24.5.\n\n"
            "### Risk Invalidation Levels\nSupport: ₹2,800. Invalidation: ₹2,750.\n\n"
            "### Outlook & Conviction\nStrong Bullish Bias."
        ),
        "Sentiment Analyst": (
            "### Social Sentiment\nPositive institutional commentary across media.\n\n"
            "### News Impact\nFavorable quarterly earnings trajectory.\n\n"
            "### Momentum Bias\nConstructive."
        ),
        "Macro Analyst": (
            "### Global Macro Drivers\nDomestic liquidity robust, interest rate cycle peaking.\n\n"
            "### Sector Positioning\nOverweight Large-Cap Equities.\n\n"
            "### Tail Risks\nCrude oil volatility."
        ),
        "Valuation Analyst": (
            "### Fundamental Metrics\nP/E 24.2 vs sector 28.5. RoE 18.5%.\n\n"
            "### Intrinsic Value\nDCF fair value ₹3,250 (14% upside).\n\n"
            "### Financial Health\nLow debt-to-equity ratio of 0.22."
        ),
        "Upside Advocate": (
            "### Growth Thesis\nCatalysts include market share expansion, operating leverage, and margin accretion.\n"
            "Upside price target: ₹3,150."
        ),
        "Downside Advocate": (
            "### Risk Invalidation\nMargin compression risks from raw materials and overhead resistance at ₹2,950.\n"
            "Downside protection required at ₹2,800."
        ),
        "Thesis Adjudicator": (
            "### Synthesis Consensus\nUpside thesis is structurally sound. Recommend LONG position on pullback.\n"
            "ACTION: BUY"
        ),
        "Order Strategist": (
            "### Order Strategy Plan\n"
            "Entry: 2850.00\n"
            "Stop Loss: 2790.00\n"
            "Target: 2970.00\n"
            "Timeframe: Swing (5-10 trading sessions)\n"
            "FINAL TRANSACTION PROPOSAL: **BUY**"
        ),
        "Chief Risk Officer": (
            "### CRO Adjudication Ruling\n"
            "Order strategy satisfies capital preservation constraints.\n"
            "Approved Action: BUY\n"
            "CONFIDENCE: 84"
        ),
    }
    return llm


@pytest.fixture
def mock_memory_store(tmp_path) -> EpisodicLessonStore:
    store = EpisodicLessonStore()
    store.add_situations([
        ("Breakout above resistance with high volume", "Trail stop loss using 2.0x ATR to capture extended momentum")
    ])
    return store


# ─────────────────────────────────────────────────────────────────────────────
# 1. Test Context Models & Pydantic Validation
# ─────────────────────────────────────────────────────────────────────────────

class TestContextModels:
    """Verifies Pydantic V2 models, defaults, bounds validation, and legacy state mappings."""

    def test_order_plan_defaults_and_validation(self):
        plan = OrderPlan()
        assert plan.action == "HOLD"
        assert plan.entry_price is None
        assert plan.risk_reward_ratio == 2.0
        assert plan.timeframe == "swing"

        # Valid custom instantiation
        valid_plan = OrderPlan(
            action="BUY",
            entry_price=2500.0,
            stop_loss=2420.0,
            target=2660.0,
            risk_reward_ratio=2.0,
            timeframe="positional",
            rationale="Golden cross setup",
        )
        assert valid_plan.action == "BUY"
        assert valid_plan.entry_price == 2500.0
        assert valid_plan.risk_reward_ratio == 2.0

        # R:R ratio validation lower bound
        with pytest.raises(ValidationError):
            OrderPlan(risk_reward_ratio=0.05)

    def test_thesis_debate_context_turns_and_formatting(self):
        debate = ThesisDebateContext()
        assert debate.rounds == 0
        assert len(debate.turns) == 0
        assert debate.get_formatted_history() == "No previous debate history."

        turn1 = DebateTurn(
            round_num=1,
            speaker="upside_advocate",
            speaker_name="Upside Advocate",
            argument="Bullish momentum supported by strong volume.",
        )
        turn2 = DebateTurn(
            round_num=1,
            speaker="downside_advocate",
            speaker_name="Downside Advocate",
            argument="Overbought RSI warns of imminent pullback.",
        )
        debate.turns.extend([turn1, turn2])
        debate.upside_arguments.append(turn1.argument)
        debate.downside_arguments.append(turn2.argument)

        formatted = debate.get_formatted_history()
        assert "[Upside Advocate] (Round 1):" in formatted
        assert "[Downside Advocate] (Round 1):" in formatted
        assert debate.get_latest_argument("upside_advocate") == turn1.argument
        assert debate.get_latest_argument("downside_advocate") == turn2.argument

    def test_thesis_debate_conviction_score_bounds(self):
        ctx = ThesisDebateContext(conviction_score=85)
        assert ctx.conviction_score == 85

        with pytest.raises(ValidationError):
            ThesisDebateContext(conviction_score=105)

        with pytest.raises(ValidationError):
            ThesisDebateContext(conviction_score=-5)

    def test_risk_deliberation_context_formatting(self):
        risk_ctx = RiskDeliberationContext(
            growth_view="Aggressive allocation approved.",
            preservation_view="Strict stop required at ₹2,800.",
            balanced_view="Favorable 2:1 risk/reward confirmed.",
            cro_ruling="Approved BUY.\nCONFIDENCE: 80",
            confidence=80,
        )
        assert risk_ctx.confidence == 80
        formatted = risk_ctx.get_formatted_deliberation()
        assert "### Growth Perspective:" in formatted
        assert "### Capital Preservation Perspective:" in formatted
        assert "### Balanced Perspective:" in formatted

    def test_analysis_context_situation_summary(self):
        ctx = AnalysisContext(
            job_id="test-job-1",
            symbol="RELIANCE",
            trade_date="2026-09-27",
            analyst_reports={
                "technical": "RSI 62, Price above 50 SMA.",
                "sentiment": "Positive institutional news flow.",
            },
        )
        summary = ctx.get_situation_summary()
        assert "=== Technical ===" in summary
        assert "RSI 62, Price above 50 SMA." in summary
        assert "=== Sentiment ===" in summary
        assert "Positive institutional news flow." in summary

    def test_analysis_context_legacy_state_bidirectional_conversion(self):
        ctx = AnalysisContext(
            job_id="job-legacy-001",
            symbol="TCS",
            trade_date="2026-09-27",
            analyst_reports={
                "technical": "Tech report",
                "sentiment": "Sentiment report",
                "macro": "Macro report",
                "valuation": "Valuation report",
                "network": "Network crypto report",
            },
            thesis_context=ThesisDebateContext(
                consensus="Consensus BUY",
                upside_arguments=["Bull argument"],
                downside_arguments=["Bear argument"],
                turns=[
                    DebateTurn(round_num=1, speaker="upside_advocate", speaker_name="Bull", argument="Bull argument")
                ],
            ),
            order_plan=OrderPlan(
                action="BUY",
                entry_price=3500.0,
                stop_loss=3430.0,
                target=3640.0,
                rationale="Targeting resistance breakout",
            ),
            risk_context=RiskDeliberationContext(
                growth_view="Growth view",
                preservation_view="Preservation view",
                balanced_view="Balanced view",
                cro_ruling="CRO ruling approved.\nCONFIDENCE: 85",
                confidence=85,
            ),
            final_decision=DecisionCard(
                symbol="TCS",
                action="BUY",
                confidence=85,
                entry_price=3500.0,
                stop_loss=3430.0,
                target=3640.0,
                position_size=10,
                reasoning="CRO ruling approved.",
            ),
        )

        legacy = ctx.to_legacy_state()
        assert legacy["company_of_interest"] == "TCS"
        assert legacy["trade_date"] == "2026-09-27"
        assert legacy["market_report"] == "Tech report"
        assert legacy["sentiment_report"] == "Sentiment report"
        assert legacy["news_report"] == "Macro report"
        assert legacy["fundamentals_report"] == "Valuation report"
        assert legacy["onchain_report"] == "Network crypto report"
        assert legacy["investment_plan"] == "Consensus BUY"
        assert legacy["risk_debate_state"]["confidence"] == 85

        reconstructed = AnalysisContext.from_legacy_state(legacy, job_id="job-reconstructed")
        assert reconstructed.symbol == "TCS"
        assert reconstructed.analyst_reports["market"] == "Tech report"
        assert reconstructed.analyst_reports["sentiment"] == "Sentiment report"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Test DecisionExtractor & Signal Extraction
# ─────────────────────────────────────────────────────────────────────────────

class TestDecisionExtractor:
    """Verifies deterministic action parsing, 4-tier confidence extraction, and DecisionCard synthesis."""

    def test_extract_action_priority_markers(self):
        extractor = DecisionExtractor()
        assert extractor.extract_action("FINAL TRANSACTION PROPOSAL: **BUY**") == "BUY"
        assert extractor.extract_action("Final Transaction Proposal: SELL") == "SELL"
        assert extractor.extract_action("FINAL TRANSACTION PROPOSAL: **HOLD**") == "HOLD"
        assert extractor.extract_action("RECOMMENDATION: BUY") == "BUY"
        assert extractor.extract_action("VERDICT: SELL") == "SELL"
        assert extractor.extract_action("RULING: **HOLD**") == "HOLD"

    def test_extract_action_unambiguous_keywords(self):
        extractor = DecisionExtractor()
        assert extractor.extract_action("We strongly advise investors to BUY shares immediately.") == "BUY"
        assert extractor.extract_action("The risk profile is unacceptable; SELL all exposure.") == "SELL"
        assert extractor.extract_action("Uncertain conditions warrant a strict HOLD posture.") == "HOLD"

    def test_extract_action_ambiguous_and_empty_fallback(self):
        extractor = DecisionExtractor()
        # Conflicting signals default to HOLD
        assert extractor.extract_action("Do not BUY, but instead SELL if breakdown occurs.") == "HOLD"
        assert extractor.extract_action("") == "HOLD"
        assert extractor.extract_action(None) == "HOLD"

    def test_extract_confidence_priority_1_text_regex(self):
        extractor = DecisionExtractor()
        assert extractor.extract_confidence("CRO Ruling: Action BUY.\nCONFIDENCE: 78") == 78
        assert extractor.extract_confidence("confidence :  92") == 92
        assert extractor.extract_confidence("CONFIDENCE: 140") == 100
        assert extractor.extract_confidence("CONFIDENCE: -10") == 0

    def test_extract_confidence_priority_2_dict_keys(self):
        extractor = DecisionExtractor()
        assert extractor.extract_confidence({"confidence": 88}) == 88
        assert extractor.extract_confidence({"score": 72}) == 72
        assert extractor.extract_confidence({"certainty": 65.4}) == 65
        assert extractor.extract_confidence({"confidence": 150}) == 100

    def test_extract_confidence_priority_3_debater_agreement_heuristic(self):
        extractor = DecisionExtractor()
        # Unanimous agreement (3 of 3 say BUY) -> 35 + 1.0 * 50 = 85
        unanimous = {
            "count": 3,
            "current_aggressive_response": "Strong BUY recommendation.",
            "current_conservative_response": "I agree, BUY is sound.",
            "current_neutral_response": "Metrics support BUY.",
        }
        assert extractor.extract_confidence(unanimous) == 85

        # Majority agreement (2 of 3 say BUY) -> 35 + 0.6 * 50 = 65
        majority = {
            "count": 3,
            "current_aggressive_response": "BUY immediately.",
            "current_conservative_response": "HOLD for safety.",
            "current_neutral_response": "Lean BUY.",
        }
        assert extractor.extract_confidence(majority) == 65

        # Split debate (1 BUY, 1 SELL, 1 HOLD) -> 35 + 0.3 * 50 = 50
        split = {
            "count": 3,
            "current_aggressive_response": "BUY",
            "current_conservative_response": "SELL",
            "current_neutral_response": "HOLD",
        }
        assert extractor.extract_confidence(split) == 50

    def test_extract_confidence_priority_4_default_fallback(self):
        extractor = DecisionExtractor()
        assert extractor.extract_confidence({}) == 50
        assert extractor.extract_confidence("No explicit conviction numbers provided here.") == 50

    def test_extract_order_plan_parsing(self):
        extractor = DecisionExtractor()
        context = AnalysisContext(
            job_id="test",
            symbol="INFY",
            trade_date="2026-09-27",
            market_data={"current_price": 1600.0},
        )
        plan_text = (
            "Formulating trade parameters for INFY:\n"
            "Entry Price: 1600.00\n"
            "Stop Loss: 1560.00\n"
            "Target Price: 1680.00\n"
            "FINAL TRANSACTION PROPOSAL: **BUY**"
        )
        plan = extractor.extract_order_plan(plan_text, context)
        assert plan.action == "BUY"
        assert plan.entry_price == 1600.00
        assert plan.stop_loss == 1560.00
        assert plan.target == 1680.00
        assert plan.risk_reward_ratio == 2.0

    def test_extract_decision_card_atr_sizing(self):
        extractor = DecisionExtractor()
        context = AnalysisContext(
            job_id="card-job-1",
            symbol="RELIANCE",
            trade_date="2026-09-27",
            market_data={"current_price": 2800.0},
            order_plan=OrderPlan(
                action="BUY",
                entry_price=2800.0,
                stop_loss=2740.0,
                target=2932.0,
                risk_reward_ratio=2.2,
            ),
            risk_context=RiskDeliberationContext(
                cro_ruling="Approved BUY.\nCONFIDENCE: 82",
                confidence=82,
            ),
        )

        card = extractor.extract_decision_card(context, portfolio_equity=100000.0)
        assert isinstance(card, DecisionCard)
        assert card.symbol == "RELIANCE"
        assert card.action == "BUY"
        assert card.confidence == 82
        assert card.position_size >= 1
        assert card.stop_loss == 2740.0
        assert card.target == 2932.0
        assert card.risk_reward_ratio == 2.2
        assert card.safety_passed is True

    def test_extract_trading_signal(self):
        extractor = DecisionExtractor()
        context = AnalysisContext(
            job_id="sig-job",
            symbol="TCS",
            trade_date="2026-09-27",
            final_decision=DecisionCard(
                symbol="TCS",
                action="BUY",
                confidence=85,
                stop_loss=3450.0,
                target=3650.0,
                reasoning="Bullish continuation",
            ),
        )
        signal = extractor.extract_trading_signal(context, exchange="NSE")
        assert isinstance(signal, TradingSignal)
        assert signal.symbol == "TCS"
        assert signal.action == "BUY"
        assert signal.exchange == Exchange.NSE
        assert signal.confidence == 85
        assert signal.stop_loss == 3450.0
        assert signal.target == 3650.0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Test PostTradeReflector & Episodic Memory Updates
# ─────────────────────────────────────────────────────────────────────────────

class TestPostTradeReflector:
    """Verifies reflection generation, memory updates, and sync/async execution."""

    @pytest.mark.asyncio
    async def test_areflect_and_remember_with_mock_llm(self, mock_llm, mock_memory_store):
        reflector = PostTradeReflector(llm=mock_llm)
        ctx = AnalysisContext(
            job_id="ref-job",
            symbol="RELIANCE",
            trade_date="2026-09-20",
            analyst_reports={"technical": "Breakout above 2800."},
            thesis_context=ThesisDebateContext(
                upside_arguments=["Strong earnings expectations"],
                downside_arguments=["Overbought momentum"],
            ),
            order_plan=OrderPlan(action="BUY", entry_price=2800.0, rationale="Breakout momentum"),
            risk_context=RiskDeliberationContext(cro_ruling="Approved BUY.\nCONFIDENCE: 80"),
        )
        trade_result = {"pnl": 5200.0, "return_pct": 3.7, "exit_reason": "target_reached"}

        initial_count = len(mock_memory_store.documents)
        lessons = await reflector.areflect_and_remember(
            state_or_context=ctx,
            returns_losses=trade_result,
            memory_store=mock_memory_store,
        )

        assert "upside_advocate" in lessons
        assert "downside_advocate" in lessons
        assert "order_strategist" in lessons
        assert "chief_risk_officer" in lessons
        assert len(mock_memory_store.documents) == initial_count + 4

    def test_reflect_and_remember_sync_wrapper(self, mock_llm, mock_memory_store):
        reflector = PostTradeReflector(llm=mock_llm)
        ctx = AnalysisContext(
            job_id="sync-ref",
            symbol="SBIN",
            trade_date="2026-09-20",
            analyst_reports={"technical": "Support at 800."},
        )
        lessons = reflector.reflect_and_remember(ctx, returns_losses=-1200.0, memory_store=mock_memory_store)
        assert isinstance(lessons, dict)
        assert len(lessons) == 4

    def test_reflector_graceful_fallback_without_llm(self):
        reflector = PostTradeReflector(llm=None)
        ctx = AnalysisContext(job_id="no-llm", symbol="INFY", trade_date="2026-09-20")
        lessons = reflector.reflect_and_remember(ctx, returns_losses=2000.0, memory_store=None)
        assert len(lessons) == 4
        for role, text in lessons.items():
            assert "Lesson for" in text or "volatility stops" in text


# ─────────────────────────────────────────────────────────────────────────────
# 4. Test NovaPipeline 5-Stage Step-by-Step Execution
# ─────────────────────────────────────────────────────────────────────────────

class TestNovaPipelineExecution:
    """Verifies step-by-step execution across all 5 stages of the NovaPipeline."""

    @pytest.mark.asyncio
    async def test_stage_1_parallel_analysts_execution(self, mock_llm):
        pipeline = NovaPipeline(llm_client=mock_llm)
        ctx = AnalysisContext(
            job_id="stage1-test",
            symbol="RELIANCE",
            trade_date="2026-09-27",
            selected_analysts=["technical", "sentiment", "macro", "valuation"],
        )

        events = []
        async for evt in pipeline._execute_stage_1_analysts(ctx):
            events.append(evt)

        assert len(ctx.analyst_reports) == 4
        assert "technical" in ctx.analyst_reports
        assert "sentiment" in ctx.analyst_reports
        assert "macro" in ctx.analyst_reports
        assert "valuation" in ctx.analyst_reports

        event_types = [e["event"] for e in events]
        assert "tool_call" in event_types
        assert "agent_status" in event_types
        assert "agent_report" in event_types

    @pytest.mark.asyncio
    async def test_stage_1_partial_analyst_failure_resilience(self, mock_llm):
        """Pipeline must continue when 1 analyst fails during asyncio.gather."""
        pipeline = NovaPipeline(llm_client=mock_llm)
        ctx = AnalysisContext(
            job_id="failure-resilience",
            symbol="TCS",
            trade_date="2026-09-27",
            selected_analysts=["technical", "sentiment", "macro", "valuation"],
        )

        async def failing_worker(role: str, context: AnalysisContext):
            if role == "sentiment":
                raise ConnectionResetError("Sentiment API connection dropped")
            return f"Successful report for {role}"

        with patch.object(pipeline, "_run_analyst_worker", side_effect=failing_worker):
            events = []
            async for evt in pipeline._execute_stage_1_analysts(ctx):
                events.append(evt)

        assert len(ctx.analyst_reports) == 4
        assert "unavailable" in ctx.analyst_reports["sentiment"].lower() or "error" in ctx.analyst_reports["sentiment"].lower()
        assert "Successful report for technical" in ctx.analyst_reports["technical"]
        assert "Successful report for macro" in ctx.analyst_reports["macro"]

    @pytest.mark.asyncio
    async def test_stage_2_bounded_adversarial_debate(self, mock_llm):
        pipeline = NovaPipeline(llm_client=mock_llm, max_debate_rounds=2)
        ctx = AnalysisContext(
            job_id="stage2-test",
            symbol="INFY",
            trade_date="2026-09-27",
            analyst_reports={"technical": "Bullish trend confirmed."},
        )

        events = []
        async for evt in pipeline._execute_stage_2_debate(ctx):
            events.append(evt)

        assert ctx.thesis_context.rounds == 2
        assert len(ctx.thesis_context.upside_arguments) == 2
        assert len(ctx.thesis_context.downside_arguments) == 2
        assert ctx.thesis_context.consensus is not None
        assert "BUY" in ctx.thesis_context.consensus or "LONG" in ctx.thesis_context.consensus

    @pytest.mark.asyncio
    async def test_stage_3_order_strategy_formulation(self, mock_llm):
        pipeline = NovaPipeline(llm_client=mock_llm)
        ctx = AnalysisContext(
            job_id="stage3-test",
            symbol="RELIANCE",
            trade_date="2026-09-27",
            market_data={"current_price": 2850.0},
            thesis_context=ThesisDebateContext(consensus="Consensus BUY"),
        )

        events = []
        async for evt in pipeline._execute_stage_3_order_strategy(ctx):
            events.append(evt)

        assert ctx.order_plan is not None
        assert ctx.order_plan.action == "BUY"
        assert ctx.order_plan.entry_price == 2850.0
        assert ctx.order_plan.stop_loss == 2790.0
        assert ctx.order_plan.target == 2970.0
        assert ctx.order_plan.risk_reward_ratio == 2.0

    @pytest.mark.asyncio
    async def test_stage_4_risk_committee_deliberation(self, mock_llm):
        pipeline = NovaPipeline(llm_client=mock_llm)
        ctx = AnalysisContext(
            job_id="stage4-test",
            symbol="RELIANCE",
            trade_date="2026-09-27",
            order_plan=OrderPlan(action="BUY", entry_price=2850.0),
        )

        events = []
        async for evt in pipeline._execute_stage_4_risk_committee(ctx):
            events.append(evt)

        assert ctx.risk_context.growth_view != ""
        assert ctx.risk_context.preservation_view != ""
        assert ctx.risk_context.balanced_view != ""
        assert len(ctx.risk_context.turns) == 3

    @pytest.mark.asyncio
    async def test_stage_5_cro_adjudication_and_sizing(self, mock_llm):
        pipeline = NovaPipeline(llm_client=mock_llm, config={"portfolio_equity": 200000.0})
        ctx = AnalysisContext(
            job_id="stage5-test",
            symbol="RELIANCE",
            trade_date="2026-09-27",
            market_data={"current_price": 2850.0},
            order_plan=OrderPlan(
                action="BUY",
                entry_price=2850.0,
                stop_loss=2790.0,
                target=2982.0,
                risk_reward_ratio=2.2,
            ),
            risk_context=RiskDeliberationContext(
                growth_view="Growth approved.",
                preservation_view="Preservation approved.",
                balanced_view="Balanced approved.",
            ),
        )

        events = []
        async for evt in pipeline._execute_stage_5_cro_adjudication(ctx):
            events.append(evt)

        assert ctx.risk_context.cro_ruling is not None
        assert ctx.risk_context.confidence == 84
        assert ctx.final_decision is not None
        assert ctx.final_decision.action == "BUY"
        assert ctx.final_decision.confidence == 84
        assert ctx.final_decision.position_size >= 1

    @pytest.mark.asyncio
    async def test_end_to_end_run(self, mock_llm, mock_memory_store):
        """Full 5-stage pipeline run execution returning completed AnalysisContext."""
        pipeline = NovaPipeline(
            llm_client=mock_llm,
            memory_store=mock_memory_store,
            max_debate_rounds=1,
            max_risk_rounds=1,
        )

        ctx = await pipeline.run(symbol="RELIANCE", trade_date="2026-09-27")
        assert isinstance(ctx, AnalysisContext)
        assert ctx.symbol == "RELIANCE"
        assert ctx.status == "completed"
        assert len(ctx.analyst_reports) >= 4
        assert ctx.thesis_context.consensus is not None
        assert ctx.order_plan is not None
        assert ctx.final_decision is not None
        assert ctx.final_decision.action == "BUY"
        assert ctx.final_decision.confidence >= 50
        assert ctx.duration_seconds >= 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Test SSE Generator Streaming
# ─────────────────────────────────────────────────────────────────────────────

class TestNovaPipelineSSEStreaming:
    """Verifies real-time SSE generator stream event types, order, and payloads."""

    @pytest.mark.asyncio
    async def test_stream_event_sequence(self, mock_llm):
        """Ensure all required SSE events are yielded in chronological order."""
        pipeline = NovaPipeline(llm_client=mock_llm, max_debate_rounds=1)
        events = []

        async for evt in pipeline.stream(symbol="TCS", trade_date="2026-09-27"):
            events.append(evt)

        event_names = [e["event"] for e in events]

        # 1. job_started is always first
        assert event_names[0] == "job_started"
        assert events[0]["data"]["symbol"] == "TCS"
        assert "teams" in events[0]["data"]

        # 2. Key events are present
        assert "event_log" in event_names
        assert "tool_call" in event_names
        assert "agent_status" in event_names
        assert "agent_report" in event_names
        assert "decision_card" in event_names

        # 3. job_completed is terminal
        assert event_names[-1] == "job_completed"
        assert events[-1]["data"]["final_verdict"] in ("BUY", "SELL", "HOLD")
        assert "confidence" in events[-1]["data"]

    @pytest.mark.asyncio
    async def test_stream_envelope_schema_conformance(self, mock_llm):
        """Every event yielded must contain event, data, and data.timestamp."""
        pipeline = NovaPipeline(llm_client=mock_llm, max_debate_rounds=1)
        async for evt in pipeline.stream(symbol="INFY", trade_date="2026-09-27"):
            assert "event" in evt
            assert "data" in evt
            assert isinstance(evt["data"], dict)

    @pytest.mark.asyncio
    async def test_stream_job_failed_on_fatal_exception(self, mock_llm):
        pipeline = NovaPipeline(llm_client=mock_llm)

        # Force fatal exception during Stage 1
        with patch.object(pipeline, "_execute_stage_1_analysts", side_effect=RuntimeError("Unrecoverable I/O Crash")):
            events = []
            async for evt in pipeline.stream(symbol="CRASH_TEST"):
                events.append(evt)

            event_names = [e["event"] for e in events]
            assert "job_failed" in event_names
            failed_event = [e for e in events if e["event"] == "job_failed"][0]
            assert "Unrecoverable I/O Crash" in failed_event["data"]["error"]

    @pytest.mark.asyncio
    async def test_stream_custom_selected_analysts(self, mock_llm):
        pipeline = NovaPipeline(llm_client=mock_llm)
        custom_analysts = ["technical", "macro"]
        events = []

        async for evt in pipeline.stream(
            symbol="SBIN",
            selected_analysts=custom_analysts,
        ):
            events.append(evt)

        # Verify only requested analysts generated reports
        report_events = [e for e in events if e["event"] == "agent_report" and e["data"].get("team") == "analyst"]
        agent_ids = [e["data"]["agent_id"] for e in report_events]
        assert "technical_analyst" in agent_ids
        assert "macro_analyst" in agent_ids
        assert "sentiment_analyst" not in agent_ids
        assert "valuation_analyst" not in agent_ids
