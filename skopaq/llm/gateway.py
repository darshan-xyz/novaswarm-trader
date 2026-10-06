"""Skopaq Multi-Provider LLM Gateway.

Clean-room multi-provider LLM abstraction layer supporting Google Gemini,
Anthropic Claude, OpenAI, xAI Grok, OpenRouter, Ollama, and Perplexity with
automatic reasoning model adaptation and content normalization.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Union

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base exception for Skopaq LLM Gateway errors."""


class UnsupportedProviderError(LLMError):
    """Raised when an unrecognized LLM provider is requested."""


class ProviderKeyMissingError(LLMError):
    """Raised when the required API key for a provider is absent."""


class ModelInstantiationError(LLMError):
    """Raised when model instantiation fails."""


class LLMProvider(str, Enum):
    """Canonical supported LLM providers."""

    GOOGLE = "google"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    XAI = "xai"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    PERPLEXITY = "perplexity"

    @classmethod
    def from_str(cls, value: str) -> LLMProvider:
        """Parse provider string with alias normalization."""
        val = value.lower().strip()
        alias_map = {
            "gemini": cls.GOOGLE,
            "google_genai": cls.GOOGLE,
            "claude": cls.ANTHROPIC,
            "grok": cls.XAI,
            "local": cls.OLLAMA,
        }
        if val in alias_map:
            return alias_map[val]
        for item in cls:
            if item.value == val:
                return item
        raise UnsupportedProviderError(f"Unsupported LLM provider: '{value}'")


@dataclass(frozen=True)
class ModelConfig:
    """Unified configuration specification for an LLM instance."""

    provider: str
    model: str
    temperature: Optional[float] = 0.1
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    reasoning_effort: Optional[str] = None  # "low" | "medium" | "high" (OpenAI o-series)
    thinking_level: Optional[str] = None  # "minimal" | "low" | "medium" | "high" (Gemini 3)
    thinking_budget: Optional[int] = None  # Token budget or -1/0 (Gemini 2.5 / Claude 3.7)
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout: Optional[float] = 60.0
    max_retries: int = 2
    callbacks: Optional[list[Any]] = None
    extra_headers: Optional[dict[str, str]] = None
    extra_kwargs: dict[str, Any] = field(default_factory=dict)


class ReasoningModelAdapter:
    """Classifies models and adapts configuration parameters for reasoning engines."""

    OPENAI_REASONING_PATTERN = re.compile(r"^(o1|o3|o4|gpt-5)(-[a-z0-9]+)*$", re.IGNORECASE)
    DEEPSEEK_REASONING_PATTERN = re.compile(r"(deepseek-r1|deepseek-reasoner)", re.IGNORECASE)
    CLAUDE_THINKING_PATTERN = re.compile(r"claude-(3-7|opus-4|sonnet-4)", re.IGNORECASE)
    GEMINI_3_PATTERN = re.compile(r"gemini-3", re.IGNORECASE)
    GEMINI_25_PATTERN = re.compile(r"gemini-2\.5", re.IGNORECASE)

    @classmethod
    def is_openai_reasoning(cls, model: str) -> bool:
        """Detect OpenAI o1, o3, o3-mini, o4-mini, gpt-5 series."""
        m = model.lower().strip()
        if "/" in m:
            m = m.split("/")[-1]
        return bool(cls.OPENAI_REASONING_PATTERN.match(m))

    @classmethod
    def is_deepseek_reasoning(cls, model: str) -> bool:
        """Detect DeepSeek-R1 / DeepSeek-Reasoner models."""
        return bool(cls.DEEPSEEK_REASONING_PATTERN.search(model))

    @classmethod
    def adapt_openai_kwargs(cls, model: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Strip temperature/top_p and map max_tokens -> max_completion_tokens for o-series."""
        adapted = dict(kwargs)
        if cls.is_openai_reasoning(model):
            adapted.pop("temperature", None)
            adapted.pop("top_p", None)
            if "max_tokens" in adapted:
                adapted["max_completion_tokens"] = adapted.pop("max_tokens")
        return adapted

    @classmethod
    def adapt_deepseek_kwargs(cls, model: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Ensure DeepSeek-R1 does not receive near-zero temperatures which break CoT."""
        adapted = dict(kwargs)
        if cls.is_deepseek_reasoning(model):
            temp = adapted.get("temperature")
            if temp is not None and temp <= 0.1:
                adapted.pop("temperature", None)
            adapted.pop("thinking_level", None)
        return adapted

    @classmethod
    def adapt_google_kwargs(cls, model: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Handle thinking_level vs thinking_budget and clamp Gemini 3 Pro 'minimal' -> 'low'."""
        adapted = dict(kwargs)
        model_lower = model.lower()
        thinking_level = adapted.pop("thinking_level", None)
        thinking_budget = adapted.pop("thinking_budget", None)

        if "gemini-3" in model_lower:
            if thinking_level:
                level_lower = thinking_level.strip().lower()
                if "pro" in model_lower and level_lower == "minimal":
                    adapted["thinking_level"] = "low"
                else:
                    adapted["thinking_level"] = level_lower
        elif "gemini-2.5" in model_lower or "gemini-2.0" in model_lower:
            if thinking_level:
                level_lower = thinking_level.strip().lower()
                adapted["thinking_budget"] = -1 if level_lower in ("high", "medium") else 0
            elif thinking_budget is not None:
                adapted["thinking_budget"] = thinking_budget
        return adapted

    @classmethod
    def adapt_anthropic_kwargs(cls, model: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Handle Anthropic extended thinking parameters (enforce temperature=1.0).

        Extended thinking is only enabled if the model matches CLAUDE_THINKING_PATTERN
        (Claude 3.7+ or Claude 4+). For unsupported models, thinking_budget is safely
        stripped and the original temperature is preserved.
        """
        adapted = dict(kwargs)
        thinking_budget = adapted.pop("thinking_budget", None)
        if thinking_budget and thinking_budget > 0 and cls.CLAUDE_THINKING_PATTERN.search(model):
            adapted["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
            adapted["temperature"] = 1.0
        return adapted


_CLOSED_THINK_PATTERN = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)
_UNCLOSED_THINK_PATTERN = re.compile(r"<think>.*$", flags=re.DOTALL | re.IGNORECASE)


def extract_clean_text(content: Any) -> str:
    """Normalize LangChain response content (string or Gemini list-of-dicts) to a string.

    Safely handles None, non-string text blocks, multimodal dictionaries, and primitives.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_val = item.get("text")
                    if text_val is not None:
                        parts.append(str(text_val))
                elif "text" in item and item["text"] is not None:
                    parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
            elif item is not None:
                parts.append(str(item))
        return "\n".join(p for p in parts if p.strip()).strip()
    return str(content).strip()


def strip_reasoning_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks (e.g. from DeepSeek-R1).

    Handles case insensitivity (<THINK>, <Think>) and unclosed tags resulting
    from generation token-limit truncation.
    """
    if not text:
        return ""
    cleaned = _CLOSED_THINK_PATTERN.sub("", text)
    cleaned = _UNCLOSED_THINK_PATTERN.sub("", cleaned)
    return cleaned.strip()


class LLMGateway:
    """Clean-room multi-provider LLM instantiation engine."""

    PROVIDER_ENV_KEYS: dict[LLMProvider, str] = {
        LLMProvider.GOOGLE: "GOOGLE_API_KEY",
        LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
        LLMProvider.OPENAI: "OPENAI_API_KEY",
        LLMProvider.XAI: "XAI_API_KEY",
        LLMProvider.OPENROUTER: "OPENROUTER_API_KEY",
        LLMProvider.PERPLEXITY: "PERPLEXITY_API_KEY",
    }

    @classmethod
    def get_api_key(cls, provider: LLMProvider, explicit_key: Optional[str] = None) -> Optional[str]:
        """Resolve API key from explicit param, standard env var, or bridged Skopaq var."""
        if explicit_key:
            return explicit_key
        if provider == LLMProvider.OLLAMA:
            return "ollama"
        env_var = cls.PROVIDER_ENV_KEYS.get(provider, "")
        return os.environ.get(env_var) or os.environ.get(f"SKOPAQ_{env_var}")

    @classmethod
    def is_provider_available(cls, provider: Union[LLMProvider, str]) -> bool:
        """Check if provider credentials/daemon are available."""
        if isinstance(provider, str):
            try:
                prov = LLMProvider.from_str(provider)
            except UnsupportedProviderError:
                return False
        else:
            prov = provider

        if prov == LLMProvider.OLLAMA:
            from skopaq.llm.model_tier import _is_ollama_available
            return _is_ollama_available()

        return bool(cls.get_api_key(prov))

    @classmethod
    def create(cls, config: ModelConfig) -> BaseChatModel:
        """Instantiate a BaseChatModel according to ModelConfig."""
        provider = LLMProvider.from_str(config.provider)
        api_key = cls.get_api_key(provider, config.api_key)

        if provider != LLMProvider.OLLAMA and not api_key:
            env_var = cls.PROVIDER_ENV_KEYS.get(provider, f"{provider.value.upper()}_API_KEY")
            raise ProviderKeyMissingError(
                f"Missing API key for provider '{provider.value}'. "
                f"Set {env_var} or SKOPAQ_{env_var} in environment or config."
            )

        dispatch_table: dict[LLMProvider, Callable[[ModelConfig, str], BaseChatModel]] = {
            LLMProvider.GOOGLE: cls._build_google,
            LLMProvider.ANTHROPIC: cls._build_anthropic,
            LLMProvider.OPENAI: cls._build_openai,
            LLMProvider.XAI: cls._build_xai,
            LLMProvider.OPENROUTER: cls._build_openrouter,
            LLMProvider.OLLAMA: cls._build_ollama,
            LLMProvider.PERPLEXITY: cls._build_perplexity,
        }

        builder = dispatch_table.get(provider)
        if not builder:
            raise UnsupportedProviderError(f"No builder implemented for provider: {provider.value}")

        return builder(config, api_key or "")

    @staticmethod
    def _build_google(config: ModelConfig, api_key: str) -> BaseChatModel:
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs: dict[str, Any] = {
            "model": config.model,
            "google_api_key": api_key,
            "temperature": config.temperature if config.temperature is not None else 0.1,
            "max_retries": max(config.max_retries, 4),
            "timeout": config.timeout,
        }
        if config.top_p is not None:
            kwargs["top_p"] = config.top_p
        if config.callbacks:
            kwargs["callbacks"] = config.callbacks
        if config.thinking_level:
            kwargs["thinking_level"] = config.thinking_level
        if config.thinking_budget is not None:
            kwargs["thinking_budget"] = config.thinking_budget
        kwargs.update(config.extra_kwargs)

        adapted_kwargs = ReasoningModelAdapter.adapt_google_kwargs(config.model, kwargs)
        return ChatGoogleGenerativeAI(**adapted_kwargs)

    @staticmethod
    def _build_anthropic(config: ModelConfig, api_key: str) -> BaseChatModel:
        from langchain_anthropic import ChatAnthropic

        kwargs: dict[str, Any] = {
            "model": config.model,
            "api_key": api_key,
            "temperature": config.temperature if config.temperature is not None else 0.1,
            "max_tokens": config.max_tokens or 4096,
            "max_retries": config.max_retries,
            "timeout": config.timeout,
        }
        if config.top_p is not None:
            kwargs["top_p"] = config.top_p
        if config.base_url:
            kwargs["base_url"] = config.base_url
        if config.callbacks:
            kwargs["callbacks"] = config.callbacks
        if config.thinking_budget:
            kwargs["thinking_budget"] = config.thinking_budget
        kwargs.update(config.extra_kwargs)

        adapted_kwargs = ReasoningModelAdapter.adapt_anthropic_kwargs(config.model, kwargs)
        return ChatAnthropic(**adapted_kwargs)

    @staticmethod
    def _build_openai(config: ModelConfig, api_key: str) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": config.model,
            "api_key": api_key,
            "temperature": config.temperature if config.temperature is not None else 0.1,
            "max_retries": config.max_retries,
            "timeout": config.timeout,
        }
        if config.top_p is not None:
            kwargs["top_p"] = config.top_p
        if config.max_tokens is not None:
            kwargs["max_tokens"] = config.max_tokens
        if config.reasoning_effort:
            kwargs["reasoning_effort"] = config.reasoning_effort
        if config.base_url:
            kwargs["base_url"] = config.base_url
        if config.callbacks:
            kwargs["callbacks"] = config.callbacks
        kwargs.update(config.extra_kwargs)

        adapted_kwargs = ReasoningModelAdapter.adapt_openai_kwargs(config.model, kwargs)
        return ChatOpenAI(**adapted_kwargs)

    @staticmethod
    def _build_xai(config: ModelConfig, api_key: str) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": config.model,
            "api_key": api_key,
            "base_url": config.base_url or "https://api.x.ai/v1",
            "temperature": config.temperature if config.temperature is not None else 0.1,
            "max_retries": config.max_retries,
            "timeout": config.timeout,
        }
        if config.callbacks:
            kwargs["callbacks"] = config.callbacks
        if config.reasoning_effort:
            kwargs["reasoning_effort"] = config.reasoning_effort
        kwargs.update(config.extra_kwargs)

        return ChatOpenAI(**kwargs)

    @staticmethod
    def _build_openrouter(config: ModelConfig, api_key: str) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        headers = {
            "HTTP-Referer": "https://skopaq.ai",
            "X-Title": "SkopaqTrader",
        }
        if config.extra_headers:
            headers.update(config.extra_headers)

        extra_kwargs = dict(config.extra_kwargs)
        if "extra_headers" in extra_kwargs:
            extra_h = extra_kwargs.pop("extra_headers")
            if isinstance(extra_h, dict):
                headers.update(extra_h)

        kwargs: dict[str, Any] = {
            "model": config.model,
            "api_key": api_key,
            "base_url": config.base_url or "https://openrouter.ai/api/v1",
            "default_headers": headers,
            "temperature": config.temperature if config.temperature is not None else 0.1,
            "max_retries": config.max_retries,
            "timeout": config.timeout,
        }
        if config.top_p is not None:
            kwargs["top_p"] = config.top_p
        if config.callbacks:
            kwargs["callbacks"] = config.callbacks
        kwargs.update(extra_kwargs)

        if ReasoningModelAdapter.is_deepseek_reasoning(config.model):
            kwargs = ReasoningModelAdapter.adapt_deepseek_kwargs(config.model, kwargs)
        elif ReasoningModelAdapter.is_openai_reasoning(config.model):
            kwargs = ReasoningModelAdapter.adapt_openai_kwargs(config.model, kwargs)

        return ChatOpenAI(**kwargs)

    @staticmethod
    def _build_ollama(config: ModelConfig, api_key: str) -> BaseChatModel:
        base_url = config.base_url or os.environ.get("SKOPAQ_OLLAMA_BASE_URL", "http://localhost:11434")
        model = config.model

        if model == "auto":
            from skopaq.llm.model_tier import _get_ollama_model
            model = _get_ollama_model()

        temp = config.temperature if config.temperature is not None else 0.1
        if ReasoningModelAdapter.is_deepseek_reasoning(model) and temp <= 0.1:
            temp = 0.6

        try:
            from langchain_ollama import ChatOllama
            return ChatOllama(
                model=model,
                base_url=base_url,
                temperature=temp,
                **config.extra_kwargs,
            )
        except ImportError:
            from langchain_openai import ChatOpenAI
            logger.info("langchain-ollama not installed; using OpenAI-compatible Ollama endpoint")
            clean_url = base_url.rstrip("/")
            if not clean_url.endswith("/v1"):
                clean_url = f"{clean_url}/v1"
            return ChatOpenAI(
                model=model,
                base_url=clean_url,
                api_key="ollama",
                temperature=temp,
                **config.extra_kwargs,
            )

    @staticmethod
    def _build_perplexity(config: ModelConfig, api_key: str) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": config.model,
            "api_key": api_key,
            "base_url": config.base_url or "https://api.perplexity.ai",
            "temperature": config.temperature if config.temperature is not None else 0.1,
            "max_retries": config.max_retries,
            "timeout": config.timeout,
        }
        if config.callbacks:
            kwargs["callbacks"] = config.callbacks
        kwargs.update(config.extra_kwargs)
        return ChatOpenAI(**kwargs)
