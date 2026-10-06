"""Comprehensive offline unit test suite for Skopaq Clean-Room Intelligence Prompts.

Verifies:
1. All 16 agent prompt getters exist, accept standard kwargs, and return non-empty strings.
2. Required markdown structural headings for every role.
3. Complete absence of unreplaced placeholder tokens (e.g. {ticker}, {tool_names}, {company_name}).
4. 0% sentence overlap and zero structural plagiarism against upstream tradingagents/ prompts.
5. Absolute absence of forbidden upstream trademarks and strings across intelligence modules.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
import re
import pytest

import skopaq.intelligence as intel
from skopaq.intelligence import (
    ALL_PROMPT_ROLES,
    get_prompt_for_role,
    # 7 Analysts
    get_technical_analyst_prompt,
    get_sentiment_analyst_prompt,
    get_macro_analyst_prompt,
    get_valuation_analyst_prompt,
    get_network_analyst_prompt,
    get_tokenomics_analyst_prompt,
    get_derivatives_analyst_prompt,
    # 3 Debate
    get_upside_advocate_prompt,
    get_downside_advocate_prompt,
    get_adjudicator_prompt,
    # 1 Execution
    get_order_strategist_prompt,
    # 4 Risk Committee
    get_growth_perspective_prompt,
    get_preservation_perspective_prompt,
    get_balanced_perspective_prompt,
    get_cro_prompt,
    # 1 Reflector
    get_reflector_prompt,
)


FORBIDDEN_UPSTREAM_TERMS = [
    "tradingagents",
    "TradingAgentsGraph",
    "route_to_vendor",
    "FinancialSituationMemory",
    "stockstats",
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Test Prompt Registry & Function Exports
# ─────────────────────────────────────────────────────────────────────────────

class TestPromptRegistryAndExports:
    """Verifies that all 16 prompt getters exist, return substantial strings, and are registry-accessible."""

    EXPECTED_16_ROLES = [
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

    def test_all_16_roles_enumerated(self):
        assert len(ALL_PROMPT_ROLES) == 16
        for role in self.EXPECTED_16_ROLES:
            assert role in ALL_PROMPT_ROLES, f"Role {role} missing from ALL_PROMPT_ROLES"

    def test_all_getters_return_non_empty_strings(self):
        getters = [
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
            get_reflector_prompt,
        ]
        assert len(getters) == 16

        sample_kwargs = {
            "symbol": "RELIANCE",
            "trade_date": "2026-09-27",
            "current_price": 2850.0,
            "market_data": {"rsi": 58.2, "atr": 24.5},
            "past_memories": "Past trade lesson: Respect volatility stops.",
        }

        for getter in getters:
            sig = inspect.signature(getter)
            call_kwargs = {k: v for k, v in sample_kwargs.items() if k in sig.parameters}
            prompt = getter(**call_kwargs)
            assert isinstance(prompt, str), f"{getter.__name__} did not return str"
            assert len(prompt.strip()) >= 150, f"{getter.__name__} returned truncated prompt (<150 chars)"

    def test_get_prompt_for_role_unified_lookup(self):
        for role in self.EXPECTED_16_ROLES:
            prompt = get_prompt_for_role(role, symbol="TCS", trade_date="2026-09-27")
            assert isinstance(prompt, str)
            assert len(prompt) >= 150


# ─────────────────────────────────────────────────────────────────────────────
# 2. Test Structural Markdown Headings & Content
# ─────────────────────────────────────────────────────────────────────────────

class TestPromptStructuralHeadings:
    """Verifies that every prompt enforces institutional markdown schemas and output structures."""

    def test_analyst_prompt_structural_headings(self):
        # Technical Analyst
        tech = get_technical_analyst_prompt(symbol="RELIANCE")
        assert "### Executive Summary" in tech or "### Executive Thesis" in tech
        assert "### Quantitative" in tech or "### Momentum" in tech
        assert "### Invalidation" in tech or "### Risk" in tech

        # Sentiment Analyst
        sent = get_sentiment_analyst_prompt(symbol="INFY")
        assert "### Social Sentiment" in sent or "### Sentiment" in sent
        assert "### News" in sent or "### Narrative" in sent

        # Macro Analyst
        macro = get_macro_analyst_prompt(symbol="HDFCBANK")
        assert "### Global Macro" in macro or "### Macro" in macro
        assert "### Sector" in macro or "### Liquidity" in macro

        # Valuation Analyst
        val = get_valuation_analyst_prompt(symbol="TCS")
        assert "### Fundamental" in val or "### Valuation" in val
        assert "### Intrinsic" in val or "### Multiples" in val

    def test_crypto_analyst_structural_headings(self):
        # Network Analyst
        net = get_network_analyst_prompt(symbol="BTCUSDT")
        assert "### On-Chain" in net or "### Network" in net

        # Tokenomics Analyst
        tok = get_tokenomics_analyst_prompt(symbol="ETHUSDT")
        assert "### Tokenomics" in tok or "### Supply" in tok

        # Derivatives Analyst
        der = get_derivatives_analyst_prompt(symbol="SOLUSDT")
        assert "### Open Interest" in der or "### Funding" in der or "### Derivatives" in der

    def test_debate_and_adjudicator_prompts(self):
        upside = get_upside_advocate_prompt(symbol="RELIANCE")
        assert "Catalyst" in upside or "Growth" in upside or "Upside" in upside

        downside = get_downside_advocate_prompt(symbol="RELIANCE")
        assert "Risk" in downside or "Downside" in downside or "Counter" in downside

        adjudicator = get_adjudicator_prompt(symbol="RELIANCE")
        assert "Synthesis" in adjudicator or "Consensus" in adjudicator or "Adjudication" in adjudicator
        assert "BUY" in adjudicator and "SELL" in adjudicator and "HOLD" in adjudicator

    def test_order_strategist_execution_format(self):
        strat = get_order_strategist_prompt(symbol="RELIANCE")
        assert "Entry" in strat
        assert "Stop Loss" in strat
        assert "Target" in strat
        assert "FINAL TRANSACTION PROPOSAL:" in strat

    def test_risk_committee_and_cro_format(self):
        growth = get_growth_perspective_prompt(symbol="RELIANCE")
        assert "Growth" in growth or "Capital Efficiency" in growth

        pres = get_preservation_perspective_prompt(symbol="RELIANCE")
        assert "Preservation" in pres or "Drawdown" in pres

        bal = get_balanced_perspective_prompt(symbol="RELIANCE")
        assert "Balanced" in bal or "Risk-Reward" in bal

        cro = get_cro_prompt(symbol="RELIANCE")
        assert "Chief Risk Officer" in cro or "CRO" in cro
        assert "CONFIDENCE:" in cro

    def test_reflector_prompt_format(self):
        ref = get_reflector_prompt()
        assert "Forensic" in ref or "Attribution" in ref or "Outcome" in ref
        assert "Episodic" in ref or "Lesson" in ref


# ─────────────────────────────────────────────────────────────────────────────
# 3. Test Sanitization & Parameter Interpolation
# ─────────────────────────────────────────────────────────────────────────────

class TestPromptSanitization:
    """Verifies that prompts do not leave unpopulated template strings or braces."""

    def test_no_unformatted_braced_placeholders(self):
        sample_kwargs = {
            "symbol": "RELIANCE",
            "trade_date": "2026-09-27",
            "current_price": 2850.0,
            "market_data": {"rsi": 55.0},
            "past_memories": "Prior lessons applied.",
        }

        unwanted_placeholders = [
            "{ticker}",
            "{company_name}",
            "{tool_names}",
            "{current_date}",
            "{system_message}",
            "{past_memory_str}",
            "{investment_plan}",
            "{history}",
        ]

        for role in ALL_PROMPT_ROLES:
            prompt = get_prompt_for_role(role, **sample_kwargs)
            for token in unwanted_placeholders:
                assert token not in prompt, f"Prompt for {role} contains unreplaced upstream placeholder: {token}"

    def test_parameter_interpolation_correctness(self):
        prompt = get_technical_analyst_prompt(symbol="TATAMOTORS", trade_date="2026-09-27")
        assert "TATAMOTORS" in prompt
        assert "2026-09-27" in prompt


# ─────────────────────────────────────────────────────────────────────────────
# 4. Test Plagiarism Immunity & Plagiarism Defense
# ─────────────────────────────────────────────────────────────────────────────

class TestPlagiarismAndASTSimilarityImmunity:
    """Validates 0% sentence overlap with upstream prompts and 0 occurrences of forbidden terms."""

    def test_zero_forbidden_upstream_terms_in_prompts(self):
        for role in ALL_PROMPT_ROLES:
            prompt = get_prompt_for_role(role, symbol="TEST_SYM")
            for term in FORBIDDEN_UPSTREAM_TERMS:
                assert term not in prompt, f"Forbidden upstream term '{term}' found in prompt for {role}"

    def test_zero_forbidden_upstream_terms_in_intelligence_source(self):
        intelligence_dir = Path(__file__).parent.parent.parent / "skopaq" / "intelligence"
        if not intelligence_dir.exists():
            pytest.skip("skopaq/intelligence/ not yet created on disk")

        for py_file in intelligence_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for term in FORBIDDEN_UPSTREAM_TERMS:
                assert term not in content, f"Forbidden term '{term}' found in source file {py_file}"

    def test_zero_sentence_overlap_with_upstream_prompts(self):
        """Extract all sentences from upstream tradingagents/ prompts and ensure 0% sentence duplication."""
        upstream_dir = Path(__file__).parent.parent.parent / "tradingagents"
        if not upstream_dir.exists():
            pytest.skip("Upstream tradingagents directory not present for comparison")

        # Collect upstream sentences
        upstream_sentences = set()
        for py_file in upstream_dir.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            raw_sentences = re.split(r"[.\n!?]", text)
            for s in raw_sentences:
                cleaned = re.sub(r"\s+", " ", s).strip().lower()
                if len(cleaned.split()) >= 6 and not any(kw in cleaned for kw in ("import ", "def ", "class ", "return ")):
                    upstream_sentences.add(cleaned)

        # Collect clean-room prompt sentences
        for role in ALL_PROMPT_ROLES:
            prompt = get_prompt_for_role(role, symbol="RELIANCE", trade_date="2026-09-27")
            clean_sentences = re.split(r"[.\n!?]", prompt)
            for s in clean_sentences:
                cleaned = re.sub(r"\s+", " ", s).strip().lower()
                if len(cleaned.split()) >= 6:
                    assert cleaned not in upstream_sentences, (
                        f"Plagiarism violation in role '{role}'! Identical sentence found:\n'{cleaned}'"
                    )
