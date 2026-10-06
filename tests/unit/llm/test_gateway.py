"""Unit tests for novaswarm.llm.gateway and novaswarm.llm.client_factory.

Tests provider dispatch, parameter adaptation, reasoning model normalization,
legacy adapter backward compatibility, and clean-room decoupling. All external API calls are mocked.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest

from novaswarm.llm.gateway import (
    LLMGateway,
    LLMProvider,
    ModelConfig,
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


class TestProviderResolution:
    """Tests for LLMProvider enumeration and alias parsing."""

    def test_provider_from_str_standard(self):
        assert LLMProvider.from_str("google") == LLMProvider.GOOGLE
        assert LLMProvider.from_str("anthropic") == LLMProvider.ANTHROPIC
        assert LLMProvider.from_str("openai") == LLMProvider.OPENAI
        assert LLMProvider.from_str("xai") == LLMProvider.XAI
        assert LLMProvider.from_str("openrouter") == LLMProvider.OPENROUTER
        assert LLMProvider.from_str("ollama") == LLMProvider.OLLAMA
        assert LLMProvider.from_str("perplexity") == LLMProvider.PERPLEXITY

    def test_provider_from_str_aliases(self):
        assert LLMProvider.from_str("gemini") == LLMProvider.GOOGLE
        assert LLMProvider.from_str("google_genai") == LLMProvider.GOOGLE
        assert LLMProvider.from_str("claude") == LLMProvider.ANTHROPIC
        assert LLMProvider.from_str("grok") == LLMProvider.XAI
        assert LLMProvider.from_str("local") == LLMProvider.OLLAMA

    def test_provider_from_str_case_insensitive_and_whitespace(self):
        assert LLMProvider.from_str("  Google  ") == LLMProvider.GOOGLE
        assert LLMProvider.from_str("OpenAI") == LLMProvider.OPENAI
        assert LLMProvider.from_str("CLAUDE") == LLMProvider.ANTHROPIC

    def test_provider_from_str_invalid(self):
        with pytest.raises(UnsupportedProviderError, match="Unsupported LLM provider"):
            LLMProvider.from_str("unknown_cloud")


class TestReasoningModelAdapter:
    """Tests for reasoning model detection and parameter adaptation."""

    def test_openai_reasoning_detection(self):
        assert ReasoningModelAdapter.is_openai_reasoning("o1") is True
        assert ReasoningModelAdapter.is_openai_reasoning("o1-mini") is True
        assert ReasoningModelAdapter.is_openai_reasoning("o3") is True
        assert ReasoningModelAdapter.is_openai_reasoning("o3-mini") is True
        assert ReasoningModelAdapter.is_openai_reasoning("o4-mini") is True
        assert ReasoningModelAdapter.is_openai_reasoning("gpt-5") is True
        assert ReasoningModelAdapter.is_openai_reasoning("openai/o3-mini") is True
        assert ReasoningModelAdapter.is_openai_reasoning("gpt-4o") is False
        assert ReasoningModelAdapter.is_openai_reasoning("claude-3-5-sonnet") is False

    def test_adapt_openai_reasoning_kwargs(self):
        kwargs = {"temperature": 0.7, "top_p": 0.9, "max_tokens": 4096, "timeout": 30.0}
        adapted = ReasoningModelAdapter.adapt_openai_kwargs("o3-mini", kwargs)
        assert "temperature" not in adapted
        assert "top_p" not in adapted
        assert "max_tokens" not in adapted
        assert adapted["max_completion_tokens"] == 4096
        assert adapted["timeout"] == 30.0

    def test_adapt_openai_standard_kwargs_untouched(self):
        kwargs = {"temperature": 0.7, "max_tokens": 4096}
        adapted = ReasoningModelAdapter.adapt_openai_kwargs("gpt-4o", kwargs)
        assert adapted["temperature"] == 0.7
        assert adapted["max_tokens"] == 4096

    def test_adapt_deepseek_reasoning_kwargs(self):
        assert ReasoningModelAdapter.is_deepseek_reasoning("deepseek-r1") is True
        assert ReasoningModelAdapter.is_deepseek_reasoning("deepseek-reasoner") is True
        kwargs = {"temperature": 0.05, "thinking_level": "high"}
        adapted = ReasoningModelAdapter.adapt_deepseek_kwargs("deepseek-r1", kwargs)
        assert "temperature" not in adapted
        assert "thinking_level" not in adapted

    def test_adapt_google_gemini_kwargs(self):
        # Gemini 3 Pro minimal clamped to low
        kwargs = {"thinking_level": "minimal"}
        adapted = ReasoningModelAdapter.adapt_google_kwargs("gemini-3-pro-preview", kwargs)
        assert adapted["thinking_level"] == "low"

        # Gemini 3 Flash preserves minimal
        kwargs_flash = {"thinking_level": "minimal"}
        adapted_flash = ReasoningModelAdapter.adapt_google_kwargs("gemini-3-flash-preview", kwargs_flash)
        assert adapted_flash["thinking_level"] == "minimal"

        # Gemini 2.5 thinking_level mapped to thinking_budget
        kwargs2 = {"thinking_level": "high"}
        adapted2 = ReasoningModelAdapter.adapt_google_kwargs("gemini-2.5-flash", kwargs2)
        assert adapted2["thinking_budget"] == -1

    def test_adapt_anthropic_thinking_kwargs(self):
        kwargs = {"temperature": 0.2, "thinking_budget": 2048}
        adapted = ReasoningModelAdapter.adapt_anthropic_kwargs("claude-3-7-sonnet", kwargs)
        assert adapted["temperature"] == 1.0  # Must be 1.0 when thinking is active
        assert adapted["thinking"] == {"type": "enabled", "budget_tokens": 2048}


class TestContentNormalizers:
    """Tests for response content extraction and tag stripping."""

    def test_extract_clean_text_string(self):
        assert extract_clean_text("Hello World") == "Hello World"
        assert extract_clean_text("  trimmed  ") == "trimmed"

    def test_extract_clean_text_gemini_list(self):
        content = [
            {"type": "text", "text": "First paragraph."},
            {"type": "text", "text": "Second paragraph."},
        ]
        assert extract_clean_text(content) == "First paragraph.\nSecond paragraph."

    def test_extract_clean_text_mixed_list(self):
        content = [
            "Leading text",
            {"type": "text", "text": "Structured text"},
        ]
        assert extract_clean_text(content) == "Leading text\nStructured text"

    def test_strip_reasoning_tags(self):
        raw = "<think>Analyzing market fundamentals...\nHigh P/E ratio.</think>Final verdict: SELL."
        assert strip_reasoning_tags(raw) == "Final verdict: SELL."


class TestLLMGatewayProviderDispatch:
    """Tests for multi-provider instantiation via LLMGateway."""

    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    def test_instantiate_google(self, mock_cls):
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        llm = instantiate_model("google", "gemini-3-flash-preview", api_key="fake-key", temperature=0.1)
        assert llm is mock_instance
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["model"] == "gemini-3-flash-preview"
        assert call_kwargs["google_api_key"] == "fake-key"
        assert call_kwargs["temperature"] == 0.1

    @patch("langchain_anthropic.ChatAnthropic")
    def test_instantiate_anthropic(self, mock_cls):
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        llm = instantiate_model("anthropic", "claude-opus-4-6", api_key="fake-key", temperature=0.2, max_tokens=2048)
        assert llm is mock_instance
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["model"] == "claude-opus-4-6"
        assert call_kwargs["api_key"] == "fake-key"
        assert call_kwargs["max_tokens"] == 2048

    @patch("langchain_openai.ChatOpenAI")
    def test_instantiate_openai_reasoning(self, mock_cls):
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        llm = instantiate_model("openai", "o3-mini", api_key="fake-key", temperature=0.7, max_tokens=2000)
        assert llm is mock_instance
        call_kwargs = mock_cls.call_args[1]
        assert "temperature" not in call_kwargs
        assert call_kwargs["max_completion_tokens"] == 2000

    @patch("langchain_openai.ChatOpenAI")
    def test_instantiate_xai(self, mock_cls):
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        llm = instantiate_model("xai", "grok-3-mini", api_key="fake-key")
        assert llm is mock_instance
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["base_url"] == "https://api.x.ai/v1"

    @patch("langchain_openai.ChatOpenAI")
    def test_instantiate_openrouter(self, mock_cls):
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        llm = instantiate_model("openrouter", "deepseek/deepseek-r1", api_key="fake-key")
        assert llm is mock_instance
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["base_url"] == "https://openrouter.ai/api/v1"
        assert "default_headers" in call_kwargs

    @patch("langchain_openai.ChatOpenAI")
    def test_instantiate_perplexity(self, mock_cls):
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        llm = instantiate_model("perplexity", "sonar-pro", api_key="fake-key")
        assert llm is mock_instance
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["base_url"] == "https://api.perplexity.ai"

    def test_instantiate_ollama(self):
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"langchain_ollama": mock_module}):
            instantiate_model("ollama", "mistral", base_url="http://localhost:11434")
            mock_module.ChatOllama.assert_called_once()

    def test_unsupported_provider_raises(self):
        with pytest.raises(UnsupportedProviderError, match="Unsupported LLM provider"):
            instantiate_model("quantum_ai", "q-model")

    def test_missing_api_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ProviderKeyMissingError, match="Missing API key"):
                instantiate_model("anthropic", "claude-opus-4-6")

    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    def test_fallback_to_google_on_missing_key(self, mock_cls):
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "g-key"}, clear=True):
            llm = instantiate_model("anthropic", "claude-opus-4-6", allow_fallback=True)
            assert llm is mock_instance

    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    def test_legacy_client_adapter(self, mock_cls):
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        client = create_llm_client("google", "gemini-3-flash-preview", api_key="fake-key")
        assert isinstance(client, LegacyLLMClientAdapter)
        assert client.get_llm() is mock_instance
        assert client.validate_model() is True
        assert client.model == "gemini-3-flash-preview"
        assert client.provider == "google"


class TestCleanRoomDecoupling:
    """Verifies complete decoupling from tradingagents."""

    def test_zero_tradingagents_imports_in_source_files(self):
        from pathlib import Path

        for fname in ["gateway.py", "client_factory.py", "model_tier.py", "__init__.py"]:
            py_file = Path("novaswarm/llm") / fname
            content = py_file.read_text(encoding="utf-8")
            assert "tradingagents" not in content.lower(), f"Found 'tradingagents' in {py_file}"


class TestHardeningFindings:
    """Tests for Milestone 2 Challenger findings 1-6."""

    @patch("langchain_openai.ChatOpenAI")
    def test_instantiate_model_extra_headers_propagation(self, mock_openai):
        mock_instance = MagicMock()
        mock_openai.return_value = mock_instance
        custom_headers = {"X-Title": "CustomApp", "X-Routing": "priority"}
        instantiate_model(
            "openrouter",
            "openai/gpt-4o",
            api_key="sk-or-test",
            extra_headers=custom_headers,
            top_p=0.9,
            timeout=45.0,
            max_retries=3,
        )
        mock_openai.assert_called_once()
        call_kwargs = mock_openai.call_args[1]
        assert call_kwargs["default_headers"]["X-Title"] == "CustomApp"
        assert call_kwargs["default_headers"]["X-Routing"] == "priority"
        assert "extra_headers" not in call_kwargs
        assert call_kwargs["top_p"] == 0.9
        assert call_kwargs["timeout"] == 45.0
        assert call_kwargs["max_retries"] == 3

    def test_extract_clean_text_none_and_non_string(self):
        assert extract_clean_text(None) == ""
        assert extract_clean_text([{"type": "text", "text": 42}]) == "42"
        assert extract_clean_text([{"type": "text", "text": None}]) == ""

    def test_strip_reasoning_tags_case_and_unclosed(self):
        assert strip_reasoning_tags("<THINK>Secret</THINK>Output") == "Output"
        assert strip_reasoning_tags("<Think>Secret</Think>Output") == "Output"
        assert strip_reasoning_tags("<think>Truncated") == ""

    def test_gemini_3_pro_minimal_case_insensitive(self):
        kwargs = {"thinking_level": "MINIMAL"}
        adapted = ReasoningModelAdapter.adapt_google_kwargs("gemini-3-pro-preview", kwargs)
        assert adapted["thinking_level"] == "low"

    def test_ollama_base_url_deduplication(self):
        with patch.dict("sys.modules", {"langchain_ollama": None}):
            with patch("langchain_openai.ChatOpenAI") as mock_openai:
                instantiate_model("ollama", "mistral", base_url="http://localhost:11434/v1")
                mock_openai.assert_called_once()
                assert mock_openai.call_args[1]["base_url"] == "http://localhost:11434/v1"

    def test_claude_thinking_unsupported_model_guard(self):
        kwargs = {"temperature": 0.2, "thinking_budget": 2048}
        adapted = ReasoningModelAdapter.adapt_anthropic_kwargs("claude-3-5-sonnet", kwargs)
        assert "thinking" not in adapted
        assert adapted["temperature"] == 0.2
