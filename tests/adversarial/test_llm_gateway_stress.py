"""Adversarial stress and edge case test suite for NovaSwarm Multi-Provider LLM Gateway.

Milestone 2 Challenger Suite:
1. Malformed provider names, invalid model strings, case insensitivity.
2. Missing API keys, custom base URLs with trailing slashes, missing optional packages (mock ImportError on langchain_ollama).
3. Reasoning model adaptation extremes (o1 negative temperature, Claude 3.7 zero thinking budget, Gemini 3 Pro minimal thinking, DeepSeek-R1 near-zero temperature).
4. Content normalization extremes (multimodal output structures, nested dicts, empty string contents, <think> tag stripping).
5. Thread safety and concurrency stress.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import re
import sys
import time
from typing import Any
from unittest.mock import MagicMock, patch
import pytest

from novaswarm.llm.gateway import (
    LLMError,
    LLMGateway,
    LLMProvider,
    ModelConfig,
    ModelInstantiationError,
    ProviderKeyMissingError,
    ReasoningModelAdapter,
    UnsupportedProviderError,
    extract_clean_text,
    strip_reasoning_tags,
)
from novaswarm.llm.client_factory import (
    LegacyLLMClientAdapter,
    create_llm_client,
    instantiate_model,
)


# ==============================================================================
# 1. PROVIDER RESOLUTION, CASE INSENSITIVITY & MALFORMED NAMES
# ==============================================================================

class TestProviderResolutionStress:
    """Stress tests for provider parsing, case permutations, and invalid inputs."""

    @pytest.mark.parametrize(
        "provider_input,expected_enum",
        [
            ("google", LLMProvider.GOOGLE),
            ("GOOGLE", LLMProvider.GOOGLE),
            ("gOoGlE", LLMProvider.GOOGLE),
            ("  google  \n\t", LLMProvider.GOOGLE),
            ("gemini", LLMProvider.GOOGLE),
            ("GEMINI", LLMProvider.GOOGLE),
            ("GeMiNi", LLMProvider.GOOGLE),
            ("google_genai", LLMProvider.GOOGLE),
            ("GOOGLE_GENAI", LLMProvider.GOOGLE),
            ("anthropic", LLMProvider.ANTHROPIC),
            ("ANTHROPIC", LLMProvider.ANTHROPIC),
            ("AnThRoPiC", LLMProvider.ANTHROPIC),
            ("claude", LLMProvider.ANTHROPIC),
            ("CLAUDE", LLMProvider.ANTHROPIC),
            ("openai", LLMProvider.OPENAI),
            ("OPENAI", LLMProvider.OPENAI),
            ("OpEnAi", LLMProvider.OPENAI),
            ("xai", LLMProvider.XAI),
            ("XAI", LLMProvider.XAI),
            ("grok", LLMProvider.XAI),
            ("GROK", LLMProvider.XAI),
            ("openrouter", LLMProvider.OPENROUTER),
            ("OPENROUTER", LLMProvider.OPENROUTER),
            ("OpenRouter", LLMProvider.OPENROUTER),
            ("ollama", LLMProvider.OLLAMA),
            ("OLLAMA", LLMProvider.OLLAMA),
            ("local", LLMProvider.OLLAMA),
            ("LOCAL", LLMProvider.OLLAMA),
            ("perplexity", LLMProvider.PERPLEXITY),
            ("PERPLEXITY", LLMProvider.PERPLEXITY),
            ("Perplexity", LLMProvider.PERPLEXITY),
        ],
    )
    def test_provider_case_insensitivity_and_aliases(self, provider_input, expected_enum):
        """Verify complete case insensitivity, whitespace tolerance, and alias mapping."""
        assert LLMProvider.from_str(provider_input) == expected_enum

    @pytest.mark.parametrize(
        "malformed_input",
        [
            "",
            "   ",
            "\n\t",
            "aws_bedrock",
            "bedrock",
            "azure",
            "azure_openai",
            "cohere",
            "mistral",
            "deepseek",
            "google!",
            "openai_api",
            "12345",
            "---",
            "null",
        ],
    )
    def test_malformed_provider_names_raise_unsupported(self, malformed_input):
        """Verify invalid or unmapped provider strings raise UnsupportedProviderError."""
        with pytest.raises(UnsupportedProviderError, match="Unsupported LLM provider"):
            LLMProvider.from_str(malformed_input)

    def test_non_string_provider_handling(self):
        """Verify non-string provider types are rejected or fail predictably."""
        with pytest.raises(AttributeError):
            LLMProvider.from_str(None)  # type: ignore

        with pytest.raises(AttributeError):
            LLMProvider.from_str(12345)  # type: ignore

    def test_is_provider_available_robustness(self):
        """Verify is_provider_available safely returns False for invalid or None providers without crashing."""
        assert LLMGateway.is_provider_available(None) is False  # type: ignore
        assert LLMGateway.is_provider_available("") is False
        assert LLMGateway.is_provider_available("   ") is False
        assert LLMGateway.is_provider_available("nonexistent_cloud") is False
        assert LLMGateway.is_provider_available(12345) is False  # type: ignore


# ==============================================================================
# 2. MODEL STRING DETECTION & REASONING MODEL ADAPTATION EXTREMES
# ==============================================================================

class TestModelStringAndReasoningStress:
    """Stress tests for reasoning engine detection, parameter stripping, and clamping."""

    # --------------------------------------------------------------------------
    # OpenAI o-series / reasoning detection
    # --------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "model_name,expected_result",
        [
            ("o1", True),
            ("O1", True),
            ("o1-mini", True),
            ("O1-MINI", True),
            ("o1-preview", True),
            ("o1-2024-12-17", True),
            ("o3", True),
            ("o3-mini", True),
            ("o3-mini-2025-01-31", True),
            ("o3-mini-high", True),
            ("o4-mini", True),
            ("gpt-5", True),
            ("GPT-5", True),
            ("gpt-5-preview", True),
            ("gpt-5-turbo", True),
            ("openai/o1", True),
            ("openai/o3-mini", True),
            ("custom/nested/prefix/o1-mini", True),
            # Negative test cases (should NOT be detected as OpenAI reasoning)
            ("o12", False),
            ("o1-", False),
            ("o1_mini", False),  # underscore is not hyphenated
            ("gpt-4o", False),
            ("gpt-4o-mini", False),
            ("gpt-4-turbo", False),
            ("claude-3-7-sonnet", False),
            ("deepseek-r1", False),
            ("", False),
            ("   ", False),
        ],
    )
    def test_openai_reasoning_detection_patterns(self, model_name, expected_result):
        """Verify boundary precision for OpenAI o1/o3/o4/gpt-5 detection pattern."""
        assert ReasoningModelAdapter.is_openai_reasoning(model_name) is expected_result

    def test_openai_reasoning_negative_temperature_and_extremes(self):
        """Stress: o1/o3 must strip negative temperatures, zero temperature, high temperature, and top_p."""
        for temp in [-1.0, -0.01, 0.0, 0.0001, 0.7, 1.0, 2.0, 100.0]:
            kwargs = {"temperature": temp, "top_p": 0.5, "max_tokens": 8192, "stream": True}
            adapted = ReasoningModelAdapter.adapt_openai_kwargs("o3-mini", kwargs)
            assert "temperature" not in adapted, f"Failed to strip temperature={temp}"
            assert "top_p" not in adapted, "Failed to strip top_p"
            assert "max_tokens" not in adapted, "Failed to remove max_tokens"
            assert adapted["max_completion_tokens"] == 8192
            assert adapted["stream"] is True

    def test_openai_reasoning_max_tokens_collision(self):
        """Stress: when both max_tokens and max_completion_tokens exist, max_tokens takes precedence."""
        kwargs = {"max_tokens": 4096, "max_completion_tokens": 1024}
        adapted = ReasoningModelAdapter.adapt_openai_kwargs("o1", kwargs)
        assert adapted["max_completion_tokens"] == 4096

    def test_openai_standard_model_preserves_temperature_and_tokens(self):
        """Verify non-reasoning OpenAI model (gpt-4o) keeps temperature and max_tokens intact."""
        kwargs = {"temperature": 0.0, "top_p": 0.1, "max_tokens": 2048}
        adapted = ReasoningModelAdapter.adapt_openai_kwargs("gpt-4o", kwargs)
        assert adapted["temperature"] == 0.0
        assert adapted["top_p"] == 0.1
        assert adapted["max_tokens"] == 2048
        assert "max_completion_tokens" not in adapted

    # --------------------------------------------------------------------------
    # Claude 3.7 Thinking Adaptation
    # --------------------------------------------------------------------------
    def test_claude_thinking_zero_or_negative_budget(self):
        """Stress: Claude 3.7 with thinking_budget <= 0 must NOT enable thinking and must NOT force temp=1.0."""
        for budget in [0, -1, -500, None]:
            kwargs = {"temperature": 0.2, "thinking_budget": budget}
            adapted = ReasoningModelAdapter.adapt_anthropic_kwargs("claude-3-7-sonnet", kwargs)
            assert "thinking" not in adapted, f"Thinking should not be enabled for budget={budget}"
            assert adapted["temperature"] == 0.2, f"Temperature should remain 0.2 for budget={budget}"
            assert "thinking_budget" not in adapted

    def test_claude_thinking_positive_budget_enforces_temperature_one(self):
        """Stress: Claude 3.7 with positive thinking_budget must enable thinking and force temperature=1.0."""
        for budget in [1024, 2048, 8192, 32000]:
            kwargs = {"temperature": 0.05, "thinking_budget": budget}
            adapted = ReasoningModelAdapter.adapt_anthropic_kwargs("claude-3-7-sonnet", kwargs)
            assert adapted["thinking"] == {"type": "enabled", "budget_tokens": budget}
            assert adapted["temperature"] == 1.0, f"Anthropic API requires temp=1.0 when thinking is active (budget={budget})"
            assert "thinking_budget" not in adapted

    # --------------------------------------------------------------------------
    # Gemini 3 & Gemini 2.5 Adaptation
    # --------------------------------------------------------------------------
    def test_gemini_3_pro_minimal_clamped_to_low(self):
        """Stress: Gemini 3 Pro cannot accept minimal thinking; must be clamped to low."""
        kwargs = {"thinking_level": "minimal"}
        adapted = ReasoningModelAdapter.adapt_google_kwargs("gemini-3-pro-preview", kwargs)
        assert adapted["thinking_level"] == "low"

    def test_gemini_3_flash_minimal_preserved(self):
        """Gemini 3 Flash natively supports minimal thinking; must NOT be clamped."""
        kwargs = {"thinking_level": "minimal"}
        adapted = ReasoningModelAdapter.adapt_google_kwargs("gemini-3-flash-preview", kwargs)
        assert adapted["thinking_level"] == "minimal"

    def test_gemini_3_pro_high_or_medium_preserved(self):
        """Gemini 3 Pro supports high and medium thinking without modification."""
        for level in ["medium", "high"]:
            kwargs = {"thinking_level": level}
            adapted = ReasoningModelAdapter.adapt_google_kwargs("gemini-3-pro-preview", kwargs)
            assert adapted["thinking_level"] == level

    def test_gemini_3_pro_uppercase_minimal_casing_gap(self):
        """Hardened: uppercase MINIMAL is clamped to low on Gemini 3 Pro."""
        kwargs = {"thinking_level": "MINIMAL"}
        adapted = ReasoningModelAdapter.adapt_google_kwargs("gemini-3-pro-preview", kwargs)
        assert adapted["thinking_level"] == "low"

    def test_claude_thinking_budget_on_unsupported_model_gap(self):
        """Hardened: adapt_anthropic_kwargs checks CLAUDE_THINKING_PATTERN and strips budget on unsupported model."""
        kwargs = {"temperature": 0.2, "thinking_budget": 2048}
        adapted = ReasoningModelAdapter.adapt_anthropic_kwargs("claude-3-5-sonnet", kwargs)
        assert "thinking" not in adapted
        assert adapted["temperature"] == 0.2

    def test_gemini_25_thinking_level_to_budget_mapping(self):
        """Gemini 2.5 uses thinking_budget (-1 for high/medium, 0 for minimal/low)."""
        # High/medium -> -1 (dynamic/unlimited)
        for level in ["high", "medium"]:
            kwargs = {"thinking_level": level}
            adapted = ReasoningModelAdapter.adapt_google_kwargs("gemini-2.5-flash", kwargs)
            assert adapted["thinking_budget"] == -1
            assert "thinking_level" not in adapted

        # Minimal/low -> 0 (disabled)
        for level in ["minimal", "low"]:
            kwargs = {"thinking_level": level}
            adapted = ReasoningModelAdapter.adapt_google_kwargs("gemini-2.5-flash", kwargs)
            assert adapted["thinking_budget"] == 0
            assert "thinking_level" not in adapted

    def test_gemini_25_explicit_thinking_budget_preserved(self):
        """Gemini 2.5 preserves explicit numeric thinking_budget."""
        kwargs = {"thinking_budget": 5000}
        adapted = ReasoningModelAdapter.adapt_google_kwargs("gemini-2.5-pro", kwargs)
        assert adapted["thinking_budget"] == 5000

    def test_gemini_legacy_ignores_thinking_parameters(self):
        """Gemini 1.5 does not support thinking; parameters must be stripped."""
        kwargs = {"thinking_level": "high", "thinking_budget": 2048}
        adapted = ReasoningModelAdapter.adapt_google_kwargs("gemini-1.5-pro", kwargs)
        assert "thinking_level" not in adapted
        assert "thinking_budget" not in adapted

    # --------------------------------------------------------------------------
    # DeepSeek Reasoning Detection and Adaptation
    # --------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "model_name,is_reasoning",
        [
            ("deepseek-r1", True),
            ("DEEPSEEK-R1", True),
            ("deepseek/deepseek-r1", True),
            ("deepseek-reasoner", True),
            ("deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", True),
            ("deepseek-v3", False),
            ("deepseek-chat", False),
            ("mistral-small", False),
        ],
    )
    def test_deepseek_reasoning_detection(self, model_name, is_reasoning):
        """DeepSeek-R1 and DeepSeek-Reasoner must be detected; DeepSeek-V3/chat must not."""
        assert ReasoningModelAdapter.is_deepseek_reasoning(model_name) is is_reasoning

    def test_deepseek_near_zero_temperature_stripped(self):
        """DeepSeek-R1 requires temp > 0.1 for CoT; near-zero temperatures must be stripped."""
        for temp in [0.0, 0.05, 0.1, -0.5]:
            kwargs = {"temperature": temp, "thinking_level": "high"}
            adapted = ReasoningModelAdapter.adapt_deepseek_kwargs("deepseek-r1", kwargs)
            assert "temperature" not in adapted, f"Failed to strip near-zero temp={temp}"
            assert "thinking_level" not in adapted

    def test_deepseek_normal_temperature_preserved(self):
        """DeepSeek-R1 normal temperature (e.g. 0.6) must be preserved."""
        kwargs = {"temperature": 0.6}
        adapted = ReasoningModelAdapter.adapt_deepseek_kwargs("deepseek-r1", kwargs)
        assert adapted["temperature"] == 0.6


# ==============================================================================
# 3. FAULT INJECTION: MISSING API KEYS & FALLBACK CASCADES
# ==============================================================================

class TestApiKeysAndFallbackFaultInjection:
    """Fault injection tests for credential validation and resilient failover."""

    @pytest.mark.parametrize(
        "provider,model",
        [
            ("google", "gemini-3-flash-preview"),
            ("anthropic", "claude-3-7-sonnet"),
            ("openai", "gpt-4o"),
            ("xai", "grok-3-mini"),
            ("openrouter", "deepseek/deepseek-r1"),
            ("perplexity", "sonar-pro"),
        ],
    )
    def test_missing_api_key_raises_for_all_cloud_providers(self, provider, model):
        """Verify every cloud provider raises ProviderKeyMissingError when key is absent."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ProviderKeyMissingError, match="Missing API key"):
                instantiate_model(provider, model, allow_fallback=False)

    def test_explicit_api_key_takes_precedence_over_env(self):
        """Explicitly passed API key must be used instead of environment variable."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}, clear=True):
            with patch("langchain_openai.ChatOpenAI") as mock_openai:
                instantiate_model("openai", "gpt-4o", api_key="explicit-key")
                mock_openai.assert_called_once()
                assert mock_openai.call_args[1]["api_key"] == "explicit-key"

    def test_novaswarm_prefixed_env_keys_accepted(self):
        """All providers must accept NOVASWARM_<PROVIDER>_API_KEY as fallback."""
        key_pairs = [
            (LLMProvider.GOOGLE, "NOVASWARM_GOOGLE_API_KEY"),
            (LLMProvider.ANTHROPIC, "NOVASWARM_ANTHROPIC_API_KEY"),
            (LLMProvider.OPENAI, "NOVASWARM_OPENAI_API_KEY"),
            (LLMProvider.XAI, "NOVASWARM_XAI_API_KEY"),
            (LLMProvider.OPENROUTER, "NOVASWARM_OPENROUTER_API_KEY"),
            (LLMProvider.PERPLEXITY, "NOVASWARM_PERPLEXITY_API_KEY"),
        ]
        for prov, env_name in key_pairs:
            with patch.dict(os.environ, {env_name: f"novaswarm-token-for-{prov.value}"}, clear=True):
                resolved = LLMGateway.get_api_key(prov)
                assert resolved == f"novaswarm-token-for-{prov.value}"

    def test_empty_string_api_key_treated_as_missing(self):
        """Passing api_key='' or whitespace must trigger ProviderKeyMissingError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ProviderKeyMissingError):
                instantiate_model("anthropic", "claude-3-7-sonnet", api_key="")

    # --------------------------------------------------------------------------
    # Fallback Cascade Verification
    # --------------------------------------------------------------------------
    @patch("langchain_openai.ChatOpenAI")
    def test_caller_specified_fallback_success(self, mock_openai):
        """When primary fails, user-specified fallback_provider/model is instantiated."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-token"}, clear=True):
            llm = instantiate_model(
                provider="anthropic",
                model="claude-3-7-sonnet",
                allow_fallback=True,
                fallback_provider="openai",
                fallback_model="gpt-4o-mini",
            )
            mock_openai.assert_called_once()
            assert mock_openai.call_args[1]["model"] == "gpt-4o-mini"

    def test_caller_specified_fallback_fails_if_its_key_is_also_missing(self):
        """When caller-specified fallback key is also absent, raise ProviderKeyMissingError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ProviderKeyMissingError, match="anthropic"):
                instantiate_model(
                    provider="openai",
                    model="gpt-4o",
                    allow_fallback=True,
                    fallback_provider="anthropic",
                    fallback_model="claude-3-haiku",
                )

    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    def test_fallback_cascade_to_google_gemini(self, mock_google):
        """When primary key is missing, fall back to default Google Gemini 3 Flash."""
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "g-key"}, clear=True):
            llm = instantiate_model("anthropic", "claude-3-7-sonnet", allow_fallback=True)
            mock_google.assert_called_once()
            assert mock_google.call_args[1]["model"] == "gemini-3-flash-preview"

    def test_fallback_cascade_to_ollama_when_google_unavailable(self):
        """When primary and Google are unavailable, fall back to local Ollama."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("novaswarm.llm.model_tier._is_ollama_available", return_value=True):
                with patch("novaswarm.llm.gateway.LLMGateway._build_ollama") as mock_ollama:
                    mock_instance = MagicMock()
                    mock_ollama.return_value = mock_instance

                    llm = instantiate_model("openai", "gpt-4o", allow_fallback=True)
                    assert llm is mock_instance
                    mock_ollama.assert_called_once()
                    assert mock_ollama.call_args[0][0].provider == "ollama"

    def test_fallback_cascade_exhaustion_raises(self):
        """When primary and all fallbacks fail, raise ProviderKeyMissingError."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("novaswarm.llm.model_tier._is_ollama_available", return_value=False):
                with pytest.raises(ProviderKeyMissingError):
                    instantiate_model("openai", "gpt-4o", allow_fallback=True)


# ==============================================================================
# 4. BASE URL TRAILING SLASHES & MISSING OPTIONAL PACKAGES
# ==============================================================================

class TestBaseUrlAndOptionalPackageFaultInjection:
    """Stress tests for custom endpoints, URL trailing slashes, and missing libraries."""

    @patch("langchain_openai.ChatOpenAI")
    def test_openai_custom_base_url_variations(self, mock_openai):
        """Custom base URLs for OpenAI proxy (with and without trailing slashes)."""
        urls = [
            "https://my-proxy.internal/v1",
            "https://my-proxy.internal/v1/",
            "http://127.0.0.1:8080",
        ]
        for url in urls:
            mock_openai.reset_mock()
            instantiate_model("openai", "gpt-4o", api_key="test-key", base_url=url)
            mock_openai.assert_called_once()
            assert mock_openai.call_args[1]["base_url"] == url

    @patch("langchain_openai.ChatOpenAI")
    def test_openrouter_custom_headers_and_base_url_via_model_config(self, mock_openai):
        """OpenRouter default headers HTTP-Referer, X-Title, and custom base_url via ModelConfig."""
        config = ModelConfig(
            provider="openrouter",
            model="deepseek/deepseek-r1",
            api_key="test-key",
            base_url="https://custom.openrouter.ai/v1/",
            extra_headers={"X-Custom-Route": "high-priority"},
        )
        LLMGateway.create(config)
        mock_openai.assert_called_once()
        kwargs = mock_openai.call_args[1]
        assert kwargs["base_url"] == "https://custom.openrouter.ai/v1/"
        assert kwargs["default_headers"]["HTTP-Referer"] == "https://novaswarm.ai"
        assert kwargs["default_headers"]["X-Title"] == "NovaSwarm Trader"
        assert kwargs["default_headers"]["X-Custom-Route"] == "high-priority"

    @patch("langchain_openai.ChatOpenAI")
    def test_instantiate_model_extra_headers_passthrough_gap(self, mock_openai):
        """Hardened: instantiate_model routes extra_headers to config.extra_headers and default_headers."""
        instantiate_model(
            "openrouter",
            "deepseek/deepseek-r1",
            api_key="test-key",
            base_url="https://custom.openrouter.ai/v1/",
            extra_headers={"X-Custom-Route": "high-priority"},
        )
        mock_openai.assert_called_once()
        kwargs = mock_openai.call_args[1]
        assert "extra_headers" not in kwargs
        assert kwargs["default_headers"]["X-Custom-Route"] == "high-priority"

    # --------------------------------------------------------------------------
    # Ollama Base URL & Missing Package Fallback
    # --------------------------------------------------------------------------
    def test_ollama_with_langchain_ollama_installed(self):
        """When langchain_ollama is installed, ChatOllama is instantiated directly."""
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"langchain_ollama": mock_module}):
            instantiate_model(
                "ollama",
                "llama3:8b",
                base_url="http://192.168.1.100:11434/",
                temperature=0.5,
            )
            mock_module.ChatOllama.assert_called_once()
            call_kwargs = mock_module.ChatOllama.call_args[1]
            assert call_kwargs["model"] == "llama3:8b"
            assert call_kwargs["base_url"] == "http://192.168.1.100:11434/"
            assert call_kwargs["temperature"] == 0.5

    def test_ollama_missing_langchain_ollama_fallback_to_chat_openai(self):
        """Fault injection: mock ImportError on langchain_ollama -> falls back to ChatOpenAI with /v1."""
        with patch.dict("sys.modules", {"langchain_ollama": None}):
            with patch("langchain_openai.ChatOpenAI") as mock_openai:
                instantiate_model(
                    "ollama",
                    "mistral:7b",
                    base_url="http://localhost:11434",
                    temperature=0.8,
                )
                mock_openai.assert_called_once()
                call_kwargs = mock_openai.call_args[1]
                assert call_kwargs["model"] == "mistral:7b"
                assert call_kwargs["base_url"] == "http://localhost:11434/v1"
                assert call_kwargs["api_key"] == "ollama"
                assert call_kwargs["temperature"] == 0.8

    def test_ollama_missing_package_with_trailing_slash_base_url(self):
        """When base_url has trailing slash and langchain_ollama is missing, rstrip preserves single /v1."""
        with patch.dict("sys.modules", {"langchain_ollama": None}):
            with patch("langchain_openai.ChatOpenAI") as mock_openai:
                instantiate_model(
                    "ollama",
                    "mistral:7b",
                    base_url="http://localhost:11434///",
                )
                mock_openai.assert_called_once()
                assert mock_openai.call_args[1]["base_url"] == "http://localhost:11434/v1"

    def test_ollama_missing_package_double_v1_path_gap(self):
        """Document empirical finding: if base_url ends in /v1, fallback creates /v1/v1 duplicate."""
        with patch.dict("sys.modules", {"langchain_ollama": None}):
            with patch("langchain_openai.ChatOpenAI") as mock_openai:
                instantiate_model(
                    "ollama",
                    "mistral:7b",
                    base_url="http://localhost:11434/v1",
                )
                # Deduplicates trailing /v1
                assert mock_openai.call_args[1]["base_url"] == "http://localhost:11434/v1"

    def test_ollama_deepseek_reasoning_temp_floor_on_ollama(self):
        """DeepSeek reasoning models on Ollama must have temperature raised to 0.6 if <= 0.1."""
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"langchain_ollama": mock_module}):
            instantiate_model(
                "ollama",
                "deepseek-r1:14b",
                temperature=0.05,
            )
            mock_module.ChatOllama.assert_called_once()
            call_kwargs = mock_module.ChatOllama.call_args[1]
            assert call_kwargs["temperature"] == 0.6, "DeepSeek temp <= 0.1 must be raised to 0.6 on Ollama"


# ==============================================================================
# 5. CONTENT NORMALIZATION EXTREMES & TAG STRIPPING
# ==============================================================================

class TestContentNormalizationStress:
    """Stress tests for extract_clean_text and strip_reasoning_tags under extreme inputs."""

    # --------------------------------------------------------------------------
    # extract_clean_text
    # --------------------------------------------------------------------------
    def test_extract_clean_text_string_extremes(self):
        """Pure string boundary handling."""
        assert extract_clean_text("") == ""
        assert extract_clean_text("   ") == ""
        assert extract_clean_text("\n\t\r\n") == ""
        assert extract_clean_text("Alpha\nBeta") == "Alpha\nBeta"
        # Very large text (100,000 chars)
        large_text = "BUY AAPL " * 10000
        assert extract_clean_text(large_text) == large_text.strip()

    def test_extract_clean_text_empty_and_whitespace_lists(self):
        """Empty list and whitespace-only list boundary handling."""
        assert extract_clean_text([]) == ""
        assert extract_clean_text(["", "   ", "\n"]) == ""

    def test_extract_clean_text_multimodal_list(self):
        """List containing text, images, and other structured items."""
        content = [
            {"type": "text", "text": "Signal generated: BUY TCS."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo..."}},
            {"type": "tool_use", "name": "get_indicators", "args": {"symbol": "TCS"}},
            {"type": "text", "text": "Stop-loss: 3800. Target: 4100."},
        ]
        result = extract_clean_text(content)
        assert result == "Signal generated: BUY TCS.\nStop-loss: 3800. Target: 4100."

    def test_extract_clean_text_with_none_text_attribute(self):
        """List with {'type': 'text', 'text': None} must not crash."""
        content = [{"type": "text", "text": None}, {"type": "text", "text": "Valid message"}]
        result = extract_clean_text(content)
        assert result == "Valid message"

    def test_extract_clean_text_primitive_fallbacks(self):
        """Non-string, non-list objects fallback via str()."""
        assert extract_clean_text(12345) == "12345"
        assert extract_clean_text(3.14159) == "3.14159"
        assert extract_clean_text(True) == "True"
        assert extract_clean_text({"summary": "bullish"}) == "{'summary': 'bullish'}"

    def test_extract_clean_text_non_string_type_error_gap(self):
        """Hardened: non-string 'text' in dictionary is safely coerced to string."""
        content = [{"type": "text", "text": 42}]
        assert extract_clean_text(content) == "42"

    def test_extract_clean_text_none_input(self):
        """Hardened: extract_clean_text(None) returns empty string."""
        assert extract_clean_text(None) == ""

    # --------------------------------------------------------------------------
    # strip_reasoning_tags
    # --------------------------------------------------------------------------
    def test_strip_reasoning_tags_standard(self):
        """Standard <think>...</think> block removal."""
        text = "<think>Analyzing momentum indicators.\nRSI is at 28 (oversold).\nMACD crossed bullishly.</think>RECOMMENDATION: BUY RELIANCE"
        assert strip_reasoning_tags(text) == "RECOMMENDATION: BUY RELIANCE"

    def test_strip_reasoning_tags_multiple_blocks(self):
        """Multiple independent thinking blocks."""
        text = "<think>First thought</think>Part 1 <think>Second thought</think>Part 2"
        assert strip_reasoning_tags(text) == "Part 1 Part 2"

    def test_strip_reasoning_tags_case_sensitivity_gap(self):
        """Hardened: uppercase <THINK> tags are stripped because re.IGNORECASE is present."""
        text = "<THINK>Hidden reasoning</THINK>Visible answer"
        assert strip_reasoning_tags(text) == "Visible answer"

    def test_strip_reasoning_tags_unclosed_block_gap(self):
        """Hardened: unclosed <think> tag (e.g. truncated generation) is stripped."""
        text = "<think>Generation cut off by max tokens..."
        assert strip_reasoning_tags(text) == ""

    def test_strip_reasoning_tags_multiline_with_code_and_quotes(self):
        """Thinking block containing multiline code, quotes, and markdown."""
        text = (
            "<think>\n"
            "def calculate_atr(df):\n"
            "    return df['tr'].rolling(14).mean()\n"
            "```python\nprint('inside thinking')\n```\n"
            "\"He said 'sell'\"\n"
            "</think>\n"
            "Verdict: Neutral"
        )
        assert strip_reasoning_tags(text) == "Verdict: Neutral"

    def test_strip_reasoning_tags_empty_block(self):
        """Empty <think></think> tags."""
        text = "<think></think>Clean Text"
        assert strip_reasoning_tags(text) == "Clean Text"

    def test_strip_reasoning_tags_all_thinking(self):
        """Input that consists entirely of a thinking block."""
        text = "<think>Only internal monologue here without final output.</think>"
        assert strip_reasoning_tags(text) == ""

    def test_strip_reasoning_tags_no_tags_intact(self):
        """Text without tags is returned stripped and untouched."""
        text = "  Just standard market analysis.  "
        assert strip_reasoning_tags(text) == "Just standard market analysis."

    def test_strip_reasoning_tags_massive_thinking_payload(self):
        """Stress: very large thinking block (100k chars) stripped efficiently."""
        start_time = time.perf_counter()
        huge_think = "<think>" + ("thinking deeply about market dynamics " * 2500) + "</think>EXECUTE BUY"
        result = strip_reasoning_tags(huge_think)
        duration = time.perf_counter() - start_time
        assert result == "EXECUTE BUY"
        assert duration < 0.1, f"Stripping took too long: {duration:.4f}s"


# ==============================================================================
# 6. CONCURRENCY, THREAD-SAFETY & ADAPTER STRESS
# ==============================================================================

class TestConcurrencyAndAdapterStress:
    """Stress tests for concurrent factory invocations and legacy adapter contract."""

    @patch("langchain_openai.ChatOpenAI")
    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    @patch("langchain_anthropic.ChatAnthropic")
    def test_concurrent_instantiations_thread_safety(self, mock_anthropic, mock_google, mock_openai):
        """Concurrently instantiate 50 models across threads with varying configs."""
        providers = [
            ("google", "gemini-3-flash-preview", {"api_key": "g-key"}),
            ("anthropic", "claude-3-7-sonnet", {"api_key": "a-key", "thinking_budget": 2048}),
            ("openai", "o3-mini", {"api_key": "o-key", "temperature": 0.7, "max_tokens": 4096}),
            ("xai", "grok-3-mini", {"api_key": "x-key"}),
            ("openrouter", "deepseek/deepseek-r1", {"api_key": "or-key", "temperature": 0.05}),
        ]

        def worker_task(idx: int):
            prov, model, extra = providers[idx % len(providers)]
            llm = instantiate_model(provider=prov, model=model, **extra)
            return (idx, prov, llm is not None)

        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker_task, i) for i in range(50)]
            for f in as_completed(futures):
                results.append(f.result())

        assert len(results) == 50
        assert all(success for _, _, success in results)

    @patch("langchain_openai.ChatOpenAI")
    def test_legacy_client_adapter_contract(self, mock_openai):
        """Verify LegacyLLMClientAdapter perfectly preserves legacy tradingagents interface."""
        mock_instance = MagicMock()
        mock_openai.return_value = mock_instance

        client = create_llm_client("openai", "gpt-4o", api_key="test-key", base_url="https://api.openai.com/v1")
        assert isinstance(client, LegacyLLMClientAdapter)
        assert client.get_llm() is mock_instance
        assert client.validate_model() is True
        assert client.model == "gpt-4o"
        assert client.provider == "openai"
