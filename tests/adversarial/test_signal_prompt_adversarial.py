"""Adversarial stress and fuzzing test suite for DecisionExtractor and Prompt Formatting.

Milestone 3 Challenger M3-2 Test Suite:
1. DecisionExtractor action fuzzing: malformed strings, contradictory signals, unicode garbage, empty strings.
2. 4-tier confidence extraction edge cases: tier 1 regex, tier 2 explicit dict keys, tier 3 consensus heuristic, tier 4 default fallback.
3. OrderPlan extraction: currency symbol parsing (: ₹ and : $), tight target R:R boundary conditions.
4. DecisionCard synthesis: extreme ATR values, negative prices, NaN/Inf portfolio equity.
5. Prompt formatting fuzzing: all 16 roles and helper functions fuzzed with None, empty strings, missing indicators, extreme values.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List
import pytest
from pydantic import ValidationError

from skopaq.api.analysis_models import DecisionCard
from skopaq.broker.models import Exchange, TradingSignal
from skopaq.intelligence import (
    ALL_PROMPT_ROLES,
    ROLE_PROMPTS,
    AgentRole,
    get_adjudicator_prompt,
    get_balanced_perspective_prompt,
    get_conversational_prompt,
    get_cro_prompt,
    get_derivatives_analyst_prompt,
    get_downside_advocate_prompt,
    get_growth_perspective_prompt,
    get_macro_analyst_prompt,
    get_network_analyst_prompt,
    get_order_strategist_prompt,
    get_position_exit_prompt,
    get_preservation_perspective_prompt,
    get_prompt_for_role,
    get_reflector_prompt,
    get_sentiment_analyst_prompt,
    get_technical_analyst_prompt,
    get_tokenomics_analyst_prompt,
    get_upside_advocate_prompt,
    get_valuation_analyst_prompt,
    resolve_role,
)
from skopaq.intelligence.base import SafeFormatDict
from skopaq.orchestration.context import (
    AnalysisContext,
    OrderPlan,
    RiskDeliberationContext,
    ThesisDebateContext,
)
from skopaq.orchestration.signal_extraction import DecisionExtractor


# ─────────────────────────────────────────────────────────────────────────────
# 1. Action Extraction Adversarial Fuzzing
# ─────────────────────────────────────────────────────────────────────────────

class TestDecisionExtractorActionFuzzing:
    """Fuzzes DecisionExtractor.extract_action with malformed, contradictory, and edge-case inputs."""

    @pytest.fixture
    def extractor(self) -> DecisionExtractor:
        return DecisionExtractor()

    @pytest.mark.parametrize(
        "empty_input",
        [None, "", "   ", "\t\n", [], {}, ()],
    )
    def test_empty_and_falsy_inputs_default_to_hold(self, extractor, empty_input):
        assert extractor.extract_action(empty_input) == "HOLD"

    @pytest.mark.parametrize(
        "unicode_garbage",
        [
            "🚀🔥💎\x00\uffff\U0001f600",
            "निर्णय: खरीदना",  # Pure Devanagari without English words
            "\u200b\u200c\u200dZeroWidthSpace",
            "اللغة العربية لا تدعم الشراء",
            "<!DOCTYPE html><script>alert('xss')</script>",
            "'; DROP TABLE signals; --",
        ],
    )
    def test_unicode_and_injection_garbage_defaults_to_hold(self, extractor, unicode_garbage):
        assert extractor.extract_action(unicode_garbage) == "HOLD"

    def test_commentary_or_translation_notes_trigger_action_bug(self, extractor):
        """SUBSTRING / KEYWORD HAZARD: An innocent note '(Devanagari Buy)' triggers BUY."""
        text = "निर्णय: खरीदना (Devanagari Buy)"
        # Demonstrates that an unquoted mention of 'Buy' in commentary triggers a BUY action
        assert extractor.extract_action(text) == "BUY"


    def test_contradictory_signals_without_header_default_to_hold(self, extractor):
        contradictory_samples = [
            "We have a STRONG BUY signal but macro conditions suggest a CRITICAL SELL.",
            "BUY BUY BUY followed immediately by SELL SELL SELL.",
            "Is this a BUY or a SELL or perhaps a HOLD?",
            "SELL immediately, then BUY back lower.",
        ]
        for sample in contradictory_samples:
            assert extractor.extract_action(sample) == "HOLD"

    def test_priority_institutional_header_beats_subsequent_contradiction(self, extractor):
        # Priority 1 marker should win even if body contains conflicting words
        text1 = "FINAL TRANSACTION PROPOSAL: **BUY**\nRisk note: Bearish indicators suggest potential SELL."
        assert extractor.extract_action(text1) == "BUY"

        text2 = "FINAL TRANSACTION PROPOSAL: **SELL**\nBullish momentum indicates traders want to BUY."
        assert extractor.extract_action(text2) == "SELL"

        text3 = "RECOMMENDATION: BUY\nSome members wanted to SELL."
        assert extractor.extract_action(text3) == "BUY"

        text4 = "VERDICT: **HOLD**\nDebaters argued over BUY and SELL."
        assert extractor.extract_action(text4) == "HOLD"

    def test_substring_boundary_behavior(self, extractor):
        # "BUY" within "BUYOUT" or "BUYER"
        assert extractor.extract_action("Management announced a buyout agreement.") == "BUY"
        # "SELL" within "SELLER"
        assert extractor.extract_action("The seller completed the transaction.") == "SELL"


# ─────────────────────────────────────────────────────────────────────────────
# 2. 4-Tier Confidence Extraction Adversarial Fuzzing
# ─────────────────────────────────────────────────────────────────────────────

class TestConfidenceFourTierFuzzing:
    """Verifies all 4 tiers of confidence extraction, boundary clamping, and surfaces failure modes."""

    @pytest.fixture
    def extractor(self) -> DecisionExtractor:
        return DecisionExtractor()

    # ── Tier 1: Regex text extraction ────────────────────────────────────────

    def test_tier_1_valid_regex_formats(self, extractor):
        assert extractor.extract_confidence("CONFIDENCE: 85") == 85
        assert extractor.extract_confidence("confidence: 12") == 12
        assert extractor.extract_confidence("CONFIDENCE :  99") == 99
        assert extractor.extract_confidence("CONFIDENCE: 85%") == 85
        assert extractor.extract_confidence("CONFIDENCE: 0") == 0
        assert extractor.extract_confidence("CONFIDENCE: 100") == 100

    def test_tier_1_out_of_bounds_clamping(self, extractor):
        # >100 clamped to 100
        assert extractor.extract_confidence("CONFIDENCE: 150") == 100
        # Negative clamped to 0
        assert extractor.extract_confidence("CONFIDENCE: -25") == 0

    def test_tier_1_markdown_bold_bug_demonstration(self, extractor):
        """CRITICAL FINDING: Regex fails when confidence is bolded as instructed by CRO prompt.

        CRO prompt template: 'CRO VERDICT: **{VERDICT}** | ACTION: **{ACTION}** | CONFIDENCE: **{confidence}**'
        Expected: 85
        Actual: Fails regex because of '**', silently falls back to default 50.
        """
        bold_text = "CRO VERDICT: **APPROVE** | ACTION: **BUY** | CONFIDENCE: **85**"
        parsed = extractor.extract_confidence(bold_text, default=50)
        # Demonstrates the empirical flaw: parsed returns 50 instead of 85
        assert parsed == 50

        bold_pct_text = "CONFIDENCE: **85%**"
        assert extractor.extract_confidence(bold_pct_text, default=50) == 50

    def test_tier_1_list_payload_extraction(self, extractor):
        list_payload = [{"type": "text", "text": "Adjudication ruling\nCONFIDENCE: 88"}]
        assert extractor.extract_confidence(list_payload) == 88

        empty_list = []
        assert extractor.extract_confidence(empty_list) == 50

        non_dict_list = ["string in list"]
        assert extractor.extract_confidence(non_dict_list) == 50

    # ── Tier 2: Explicit dict keys ───────────────────────────────────────────

    def test_tier_2_dict_keys_and_precedence(self, extractor):
        assert extractor.extract_confidence({"confidence": 75}) == 75
        assert extractor.extract_confidence({"score": 60}) == 60
        assert extractor.extract_confidence({"certainty": 90}) == 90

        # Precedence: confidence > score > certainty
        assert extractor.extract_confidence({"confidence": 80, "score": 60, "certainty": 40}) == 80
        assert extractor.extract_confidence({"score": 60, "certainty": 40}) == 60

        # Judge decision in dict takes top priority
        assert extractor.extract_confidence({"judge_decision": "CONFIDENCE: 92", "confidence": 50}) == 92

    def test_tier_2_dict_key_clamping(self, extractor):
        assert extractor.extract_confidence({"confidence": 250}) == 100
        assert extractor.extract_confidence({"confidence": -50}) == 0
        assert extractor.extract_confidence({"confidence": "85"}) == 85
        assert extractor.extract_confidence({"confidence": 85.9}) == 85

    def test_tier_2_nan_and_malformed_key_fallback(self, extractor):
        # NaN is caught by ValueError and falls back to default
        assert extractor.extract_confidence({"confidence": float("nan")}) == 50
        assert extractor.extract_confidence({"confidence": None}) == 50
        assert extractor.extract_confidence({"confidence": "not_a_number"}) == 50

    def test_tier_2_infinity_overflow_bug_demonstration(self, extractor):
        """CRITICAL FINDING: float('inf') in dict raises unhandled OverflowError.

        int(float('inf')) raises OverflowError which is NOT caught by (ValueError, TypeError).
        """
        with pytest.raises(OverflowError):
            extractor.extract_confidence({"confidence": float("inf")})

        with pytest.raises(OverflowError):
            extractor.extract_confidence({"score": float("-inf")})

    # ── Tier 3: Debater consensus heuristic ──────────────────────────────────

    def test_tier_3_unanimous_majority_and_split(self, extractor):
        # Unanimous BUY: 35 + 1.0 * 50 = 85
        unanimous = {
            "count": 1,
            "current_aggressive_response": "Strong BUY recommendation.",
            "current_conservative_response": "BUY is safe and prudent.",
            "current_neutral_response": "BUY fits balanced criteria.",
        }
        assert extractor.extract_confidence(unanimous) == 85

        # Majority BUY: 35 + 0.6 * 50 = 65
        majority = {
            "count": 2,
            "current_aggressive_response": "BUY",
            "current_conservative_response": "HOLD",
            "current_neutral_response": "Lean BUY",
        }
        assert extractor.extract_confidence(majority) == 65

        # Split debate (1 BUY, 1 SELL, 1 HOLD): 35 + 0.3 * 50 = 50
        split = {
            "count": 1,
            "current_aggressive_response": "BUY",
            "current_conservative_response": "SELL",
            "current_neutral_response": "HOLD",
        }
        assert extractor.extract_confidence(split) == 50

    def test_tier_3_empty_debater_strings_fallback(self, extractor):
        # If any debater string is empty: returns 0.5 agreement -> 35 + 0.5 * 50 = 60
        incomplete = {
            "count": 1,
            "current_aggressive_response": "BUY",
            "current_conservative_response": "",
            "current_neutral_response": "BUY",
        }
        assert extractor.extract_confidence(incomplete) == 60

    # ── Tier 4: Default fallback ─────────────────────────────────────────────

    def test_tier_4_fallback_behavior(self, extractor):
        assert extractor.extract_confidence({}) == 50
        assert extractor.extract_confidence("No numbers here") == 50
        assert extractor.extract_confidence(None) == 50
        assert extractor.extract_confidence({}, default=33) == 33


# ─────────────────────────────────────────────────────────────────────────────
# 3. OrderPlan Extraction & Validation Adversarial Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestOrderPlanAdversarial:
    """Stress-tests OrderPlan extraction against prompt output formatting and validation bounds."""

    @pytest.fixture
    def extractor(self) -> DecisionExtractor:
        return DecisionExtractor()

    @pytest.fixture
    def context(self) -> AnalysisContext:
        return AnalysisContext(
            job_id="test-job",
            symbol="INFY",
            trade_date="2026-09-27",
            market_data={"current_price": 1000.0},
        )

    def test_order_plan_valid_extraction(self, extractor, context):
        text = "Entry Price: 1500.00\nStop Loss: 1450.00\nTarget Price: 1600.00\nACTION: BUY"
        plan = extractor.extract_order_plan(text, context)
        assert plan.action == "BUY"
        assert plan.entry_price == 1500.00
        assert plan.stop_loss == 1450.00
        assert plan.target == 1600.00
        assert plan.risk_reward_ratio == 2.0

    def test_currency_symbol_rupee_silently_dropped_bug_demonstration(self, extractor, context):
        """HIGH FINDING: ': ₹' causes regex to fail to parse entry, stop, and target.

        The Order Strategist prompt specifies:
        'FINAL TRANSACTION PROPOSAL: **{ACTION}** | ENTRY: ₹{entry_price} | STOP: ₹{stop_loss} | TARGET: ₹{target_1}'
        Because '[:=₹]?' only matches one character, ':' consumes it, leaving '₹' in the text,
        which fails to match [\\d,.].
        Result: Silently falls back to default 1000.0, 980.0, 1040.0.
        """
        prompt_formatted_text = (
            "FINAL TRANSACTION PROPOSAL: **BUY** | ENTRY: ₹1600.00 | STOP: ₹1560.00 | TARGET: ₹1680.00 | R:R: 2.0"
        )
        plan = extractor.extract_order_plan(prompt_formatted_text, context)
        # Demonstrates the empirical bug: the numbers 1600, 1560, 1680 were dropped!
        assert plan.entry_price != 1600.00
        assert plan.entry_price == 1000.00  # Default current_price fallback
        assert plan.stop_loss == 980.00
        assert plan.target == 1040.00

    def test_rr_ratio_validation_error_when_reward_is_zero_bug_demonstration(self, extractor, context):
        """CRITICAL FINDING: OrderPlan raises ValidationError when target == entry.

        If target == entry (reward = 0), rr = 0.0.
        OrderPlan.risk_reward_ratio has Field(..., ge=0.1).
        This raises an unhandled ValidationError inside extract_order_plan!
        """
        zero_reward_text = (
            "Entry Price: 1000.00\n"
            "Stop Loss: 950.00\n"
            "Target Price: 1000.00\n"  # Target == Entry
            "ACTION: BUY"
        )
        with pytest.raises(ValidationError) as excinfo:
            extractor.extract_order_plan(zero_reward_text, context)
        assert "risk_reward_ratio" in str(excinfo.value)
        assert "greater_than_equal" in str(excinfo.value)

    def test_missing_market_data_fallback(self, extractor):
        empty_context = AnalysisContext(
            job_id="test-job-empty",
            symbol="INFY",
            trade_date="2026-09-27",
            market_data={},
        )
        plan = extractor.extract_order_plan("No prices mentioned.", empty_context)
        # Falls back to default 1000.0
        assert plan.entry_price == 1000.0
        assert plan.stop_loss == 980.0
        assert plan.target == 1040.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. DecisionCard Synthesis Adversarial Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDecisionCardAdversarial:
    """Stress-tests DecisionCard synthesis and ATR volatility position sizing."""

    @pytest.fixture
    def extractor(self) -> DecisionExtractor:
        return DecisionExtractor()

    def test_extreme_atr_values_and_sizing_safety(self, extractor):
        # Very high price -> large ATR
        ctx_high = AnalysisContext(
            job_id="job-high",
            symbol="MRF",
            trade_date="2026-09-27",
            market_data={"current_price": 150000.0},
        )
        card_high = extractor.extract_decision_card(ctx_high, portfolio_equity=100000.0)
        assert card_high.position_size >= 1
        assert card_high.stop_loss is not None
        assert card_high.target is not None

        # Very low price -> tiny ATR
        ctx_low = AnalysisContext(
            job_id="job-low",
            symbol="PENNY",
            trade_date="2026-09-27",
            market_data={"current_price": 0.50},
        )
        card_low = extractor.extract_decision_card(ctx_low, portfolio_equity=100000.0)
        assert card_low.position_size >= 1

    def test_negative_price_handling(self, extractor):
        ctx_neg = AnalysisContext(
            job_id="job-neg",
            symbol="CRUDE",
            trade_date="2026-09-27",
            market_data={"current_price": -50.0},
        )
        card_neg = extractor.extract_decision_card(ctx_neg)
        assert card_neg.position_size >= 1

    def test_nan_portfolio_equity_bug_demonstration(self, extractor):
        """MEDIUM FINDING: NaN portfolio_equity raises ValueError in math.floor."""
        ctx = AnalysisContext(
            job_id="job-nan",
            symbol="TCS",
            trade_date="2026-09-27",
            market_data={"current_price": 3000.0},
        )
        with pytest.raises(ValueError, match="cannot convert float NaN to integer"):
            extractor.extract_decision_card(ctx, portfolio_equity=float("nan"))

    def test_inf_portfolio_equity_bug_demonstration(self, extractor):
        """MEDIUM FINDING: Inf portfolio_equity raises OverflowError in math.floor."""
        ctx = AnalysisContext(
            job_id="job-inf",
            symbol="TCS",
            trade_date="2026-09-27",
            market_data={"current_price": 3000.0},
        )
        with pytest.raises(OverflowError, match="cannot convert float infinity to integer"):
            extractor.extract_decision_card(ctx, portfolio_equity=float("inf"))

    def test_extract_trading_signal_nse_and_binance(self, extractor):
        ctx = AnalysisContext(
            job_id="job-sig",
            symbol="BTC/USDT",
            trade_date="2026-09-27",
            market_data={"current_price": 65000.0},
        )
        sig_binance = extractor.extract_trading_signal(ctx, exchange="BINANCE")
        assert sig_binance.exchange == Exchange.BINANCE
        assert sig_binance.confidence >= 0 and sig_binance.confidence <= 100

        sig_nse = extractor.extract_trading_signal(ctx, exchange="NSE")
        assert sig_nse.exchange == Exchange.NSE


# ─────────────────────────────────────────────────────────────────────────────
# 5. Prompt Formatters Fuzzing Suite
# ─────────────────────────────────────────────────────────────────────────────

class TestPromptFormattersFuzzing:
    """Exhaustive fuzzing of all 16 prompt contracts and helper functions."""

    ALL_PROMPT_GETTERS = [
        get_technical_analyst_prompt,
        get_sentiment_analyst_prompt,
        get_macro_analyst_prompt,
        get_valuation_analyst_prompt,
        get_network_analyst_prompt,
        get_tokenomics_analyst_prompt,
        get_derivatives_analyst_prompt,
        get_upside_advocate_prompt,
        get_downside_advocate_prompt,
        get_adjudicator_prompt,
        get_order_strategist_prompt,
        get_growth_perspective_prompt,
        get_preservation_perspective_prompt,
        get_balanced_perspective_prompt,
        get_cro_prompt,
        get_conversational_prompt,
        get_position_exit_prompt,
    ]

    @pytest.mark.parametrize("getter", ALL_PROMPT_GETTERS)
    def test_prompt_getter_with_none_and_empty_parameters(self, getter):
        for val in [None, "", "   "]:
            rendered = getter(symbol=val, trade_date=val)
            assert isinstance(rendered, str)
            assert len(rendered) > 50

    @pytest.mark.parametrize("getter", ALL_PROMPT_GETTERS)
    def test_prompt_getter_with_extreme_values(self, getter):
        extreme_kwargs = {
            "symbol": "A" * 500,
            "trade_date": "9999-12-31",
            "entry_price": 1e20,
            "stop_loss": -1e20,
            "target_1": float("inf"),
            "confidence": float("nan"),
            "res_1": 0.00000001,
        }
        rendered = getter(**extreme_kwargs)
        assert isinstance(rendered, str)
        assert len(rendered) > 50

    @pytest.mark.parametrize("getter", ALL_PROMPT_GETTERS)
    def test_prompt_getter_with_special_characters_and_garbage(self, getter):
        garbage_kwargs = {
            "symbol": "🚀<script>alert('x')</script>{evil_braces}",
            "trade_date": "2026-09-27\x00\uffff",
            "custom_arg": True,
        }
        rendered = getter(**garbage_kwargs)
        assert isinstance(rendered, str)
        assert len(rendered) > 50

    def test_reflector_prompt_fuzzing(self):
        for kw in [{}, {"extra_arg": None}, {"pnl_pct": -99.9, "net_pnl": 1e6}]:
            rendered = get_reflector_prompt(**kw)
            assert isinstance(rendered, str)
            assert len(rendered) > 50

    @pytest.mark.parametrize("role_name", ALL_PROMPT_ROLES)
    def test_get_prompt_for_role_all_roles_with_empty_kwargs(self, role_name):
        rendered = get_prompt_for_role(role_name)
        assert isinstance(rendered, str)
        assert len(rendered) > 50

    def test_get_prompt_for_role_invalid_role_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown agent role identifier"):
            get_prompt_for_role("non_existent_role")

        with pytest.raises(ValueError, match="Unknown agent role identifier"):
            get_prompt_for_role("")

    def test_safe_format_dict_missing_key_behavior(self):
        sfd = SafeFormatDict({"custom": "value"})
        assert sfd["custom"] == "value"
        # Known defaults
        assert sfd["symbol"] == "UNKNOWN"
        assert sfd["ACTION"] == "BUY/SELL/HOLD"
        assert sfd["min_profit_pct"] == "2.0"
        # Unknown keys return uppercase bracketed placeholder
        assert sfd["totally_unknown_key"] == "[TOTALLY_UNKNOWN_KEY]"
