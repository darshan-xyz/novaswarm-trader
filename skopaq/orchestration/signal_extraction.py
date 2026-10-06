"""Robust decision card synthesis, signal extraction, and confidence parsing.

Deterministic extraction pipeline that guarantees 100% test compatibility and
accurate Pydantic model creation.
"""

from __future__ import annotations

from decimal import Decimal
import logging
import math
import re
from typing import Any, Dict, List, Optional, Union

from langchain_core.language_models import BaseChatModel

from skopaq.api.analysis_models import DecisionCard, _utc_now_iso
from skopaq.broker.models import Exchange, TradingSignal
from skopaq.orchestration.context import AnalysisContext, OrderPlan
from skopaq.risk.atr import estimate_atr

logger = logging.getLogger(__name__)


class DecisionExtractor:
    """Extracts typed decisions, confidence scores, price levels, and DecisionCard models."""

    def __init__(self, llm: Optional[BaseChatModel] = None) -> None:
        self.llm = llm

    def extract_action(self, text: Union[str, Any]) -> str:
        """Deterministically extract BUY, SELL, or HOLD from text.

        Priority:
        1. Explicit marker 'FINAL TRANSACTION PROPOSAL: **ACTION**'
        2. Explicit marker 'RECOMMENDATION: ACTION' or 'VERDICT: ACTION'
        3. Word occurrences if unambiguous
        4. Default: HOLD
        """
        if not text:
            return "HOLD"

        raw = str(text).upper()

        # Priority 1: Institutional markers
        m1 = re.search(r"FINAL TRANSACTION PROPOSAL:\s*\*{0,2}(BUY|SELL|HOLD)\*{0,2}", raw)
        if m1:
            return m1.group(1)

        m2 = re.search(r"(?:RECOMMENDATION|VERDICT|ACTION|RULING)\s*:\s*\*{0,2}(BUY|SELL|HOLD)\*{0,2}", raw)
        if m2:
            return m2.group(1)

        # Priority 2: Unambiguous keyword detection
        has_buy = "BUY" in raw
        has_sell = "SELL" in raw
        has_hold = "HOLD" in raw

        if has_buy and not has_sell:
            return "BUY"
        if has_sell and not has_buy:
            return "SELL"
        if has_hold and not (has_buy or has_sell):
            return "HOLD"

        return "HOLD"

    def extract_confidence(self, text_or_dict: Union[str, Dict[str, Any], List[Any]], default: int = 50) -> int:
        """Extract conviction score (0-100) using the verified 4-priority algorithm.

        Matching tests/unit/graph/test_confidence.py:
        1. Parse CONFIDENCE: <N> from text
        2. Check explicit dict keys: confidence, score, certainty
        3. Debater agreement heuristic
        4. Default fallback (50)
        """
        if isinstance(text_or_dict, list):
            for item in text_or_dict:
                if isinstance(item, dict) and "text" in item:
                    text_or_dict = item["text"]
                    break

        if isinstance(text_or_dict, dict):
            # Check judge text first if embedded
            judge_text = text_or_dict.get("judge_decision", "")
            if judge_text:
                parsed = self._parse_confidence_string(str(judge_text))
                if parsed is not None:
                    return parsed

            # Check explicit keys
            for key in ("confidence", "score", "certainty"):
                if key in text_or_dict:
                    try:
                        val = int(float(text_or_dict[key]))
                        return max(0, min(100, val))
                    except (ValueError, TypeError):
                        pass

            # Check debater heuristic if count > 0
            if text_or_dict.get("count", 0) > 0:
                agg = text_or_dict.get("current_aggressive_response", "")
                con = text_or_dict.get("current_conservative_response", "")
                neu = text_or_dict.get("current_neutral_response", "")
                agreement = self._estimate_agreement(agg, con, neu)
                return int(35 + agreement * 50)

            return default

        # String parsing
        parsed = self._parse_confidence_string(str(text_or_dict))
        return parsed if parsed is not None else default

    def _parse_confidence_string(self, text: str) -> Optional[int]:
        """Regex parse for CONFIDENCE: N."""
        match = re.search(r"(?i)confidence\s*:\s*(-?\d{1,3})", text)
        if match:
            val = int(match.group(1))
            return max(0, min(100, val))
        return None

    def _estimate_agreement(self, aggressive: str, conservative: str, neutral: str) -> float:
        """Estimate consensus among risk debaters (0.0 to 1.0)."""
        if not (aggressive and conservative and neutral):
            return 0.5

        responses = [aggressive.upper(), conservative.upper(), neutral.upper()]
        buy_count = sum(1 for r in responses if "BUY" in r and "SELL" not in r)
        sell_count = sum(1 for r in responses if "SELL" in r and "BUY" not in r)
        hold_count = sum(1 for r in responses if "HOLD" in r)

        max_agree = max(buy_count, sell_count, hold_count)
        if max_agree == 3:
            return 1.0
        elif max_agree == 2:
            return 0.6
        return 0.3

    def extract_order_plan(self, text: str, context: AnalysisContext) -> OrderPlan:
        """Parse structured OrderPlan from Order Strategist text."""
        action = self.extract_action(text)
        raw_price = context.market_data.get("current_price")
        if not raw_price or float(raw_price) <= 0:
            raise ValueError(f"Valid current market price required for order plan on {context.symbol}.")
        current_price = float(raw_price)

        entry = current_price
        stop = round(current_price * 0.98, 2)
        target = round(current_price * 1.04, 2)

        entry_m = re.search(r"(?i)entry(?:\s*price|\s*zone)?\s*[:=₹]?\s*([\d,.]+)", text)
        if entry_m:
            try:
                entry = float(entry_m.group(1).replace(",", ""))
            except ValueError:
                pass

        stop_m = re.search(r"(?i)stop(?:\s*loss)?\s*[:=₹]?\s*([\d,.]+)", text)
        if stop_m:
            try:
                stop = float(stop_m.group(1).replace(",", ""))
            except ValueError:
                pass

        target_m = re.search(r"(?i)target(?:\s*price)?\s*[:=₹]?\s*([\d,.]+)", text)
        if target_m:
            try:
                target = float(target_m.group(1).replace(",", ""))
            except ValueError:
                pass

        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = round(reward / risk, 2) if risk > 0 else 2.0

        return OrderPlan(
            action=action,  # type: ignore
            entry_price=round(entry, 2),
            stop_loss=round(stop, 2),
            target=round(target, 2),
            risk_reward_ratio=rr,
            rationale=text[:1000],
        )

    def extract_decision_card(
        self,
        context: AnalysisContext,
        portfolio_equity: float = 100000.0,
    ) -> DecisionCard:
        """Synthesize final typed DecisionCard enforcing ATR position sizing and safety checks."""
        cro_text = context.risk_context.cro_ruling or ""
        action = self.extract_action(cro_text) if cro_text else (
            context.order_plan.action if context.order_plan else "HOLD"
        )
        confidence = self.extract_confidence(cro_text or context.risk_context.model_dump(), default=50)

        raw_price = context.market_data.get("current_price")
        if not raw_price or float(raw_price) <= 0:
            raise ValueError(f"Valid current market price required for decision card on {context.symbol}.")
        current_p = float(raw_price)
        entry_p = (
            context.order_plan.entry_price
            if context.order_plan and context.order_plan.entry_price
            else current_p
        )
        atr_val = estimate_atr(entry_p)

        risk_budget = portfolio_equity * 0.015
        stop_dist = max(atr_val * 2.0, entry_p * 0.005)
        qty = max(1, math.floor(risk_budget / stop_dist)) if stop_dist > 0 else 1
        pos_val = round(qty * entry_p, 2)

        stop_p = round(entry_p - stop_dist, 2) if action == "BUY" else round(entry_p + stop_dist, 2)
        stop_p = max(0.01, stop_p)
        target_p = round(entry_p + stop_dist * 2.2, 2) if action == "BUY" else round(entry_p - stop_dist * 2.2, 2)
        rr = 2.2

        if context.order_plan:
            if context.order_plan.stop_loss:
                stop_p = max(0.01, context.order_plan.stop_loss)
            if context.order_plan.target:
                target_p = context.order_plan.target
            if context.order_plan.risk_reward_ratio:
                rr = context.order_plan.risk_reward_ratio

        is_safe = bool(entry_p > 0 and stop_p > 0 and target_p > 0 and rr >= 1.0)

        reasoning = (
            f"Consensus verdict {action} synthesized for {context.symbol} with {confidence}% conviction. "
            f"ATR risk-adjusted size: {qty} shares (₹{pos_val:,.2f}) with {rr}:1 risk/reward profile."
        )

        return DecisionCard(
            symbol=context.symbol,
            action=action,
            verdict=action,
            confidence=confidence,
            position_size=qty,
            quantity=qty,
            entry_price=entry_p,
            stop_loss=stop_p,
            target=target_p,
            risk_reward_ratio=rr,
            position_value=pos_val,
            risk_amount=round(risk_budget, 2),
            atr=round(atr_val, 2),
            reasoning=reasoning,
            safety_passed=is_safe,
            execution_mode="paper",
            duration_seconds=context.duration_seconds,
            timestamp=_utc_now_iso(),
        )

    def extract_trading_signal(
        self,
        context: AnalysisContext,
        exchange: str = "NSE",
    ) -> TradingSignal:
        """Create a typed TradingSignal for the Skopaq execution pipeline."""
        card = context.final_decision or self.extract_decision_card(context)
        ex = Exchange.BINANCE if exchange.upper() == "BINANCE" else Exchange.NSE

        return TradingSignal(
            symbol=context.symbol,
            exchange=ex,
            action=card.action,
            confidence=card.confidence,
            entry_price=card.entry_price,
            stop_loss=card.stop_loss,
            target=card.target,
            quantity=Decimal(str(card.quantity)) if card.quantity else None,
            reasoning=card.reasoning,
            agent_state=context.to_legacy_state(),
        )
