"""Skopaq Clean-Room LLM Client Factory.

Provides the unified `instantiate_model` entry point and legacy compatibility adapter
with zero upstream external library imports.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel

from skopaq.llm.gateway import (
    LLMGateway,
    LLMProvider,
    ModelConfig,
    ProviderKeyMissingError,
)

logger = logging.getLogger(__name__)


class LegacyLLMClientAdapter:
    """Drop-in adapter for any legacy code or test expecting client.get_llm().

    Guarantees 100% backward compatibility without any upstream imports.
    """

    def __init__(self, llm: BaseChatModel, model: str, provider: str) -> None:
        self._llm = llm
        self.model = model
        self.provider = provider

    def get_llm(self) -> BaseChatModel:
        """Return the instantiated LangChain chat model."""
        return self._llm

    def validate_model(self) -> bool:
        """Permissive model validation for backward compatibility."""
        return True


def instantiate_model(
    provider: str,
    model: str,
    temperature: float = 0.1,
    top_p: Optional[float] = None,
    thinking_level: Optional[str] = None,
    thinking_budget: Optional[int] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    max_tokens: Optional[int] = None,
    reasoning_effort: Optional[str] = None,
    timeout: Optional[float] = 60.0,
    max_retries: int = 2,
    callbacks: Optional[list[Any]] = None,
    extra_headers: Optional[dict[str, str]] = None,
    allow_fallback: bool = False,
    fallback_provider: Optional[str] = None,
    fallback_model: Optional[str] = None,
    **kwargs: Any,
) -> BaseChatModel:
    """Instantiate a LangChain chat model across any supported provider.

    Args:
        provider: Provider name ('google', 'anthropic', 'openai', 'xai', 'openrouter', 'ollama', 'perplexity').
        model: Model identifier string.
        temperature: Sampling temperature (auto-stripped for reasoning models).
        top_p: Nucleus sampling parameter.
        thinking_level: Thinking depth for Gemini 3 ("minimal", "low", "medium", "high").
        thinking_budget: Token budget for Gemini 2.5 / Claude 3.7.
        base_url: Custom API endpoint URL.
        api_key: Optional explicit API key override.
        max_tokens: Maximum token limit (auto-converted to max_completion_tokens for o-series).
        reasoning_effort: Reasoning effort for OpenAI/xAI models ("low", "medium", "high").
        timeout: Request timeout in seconds.
        max_retries: Maximum request retries.
        callbacks: Optional list of LangChain callback handlers.
        extra_headers: Optional custom HTTP headers (e.g. for OpenRouter routing).
        allow_fallback: If True, falls back to alternative provider if key is missing.
        fallback_provider: Specific fallback provider.
        fallback_model: Specific fallback model.
        **kwargs: Additional parameters forwarded to model constructor.

    Returns:
        Configured BaseChatModel instance.
    """
    config = ModelConfig(
        provider=provider,
        model=model,
        temperature=temperature,
        top_p=top_p,
        thinking_level=thinking_level,
        thinking_budget=thinking_budget,
        base_url=base_url,
        api_key=api_key,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        max_retries=max_retries,
        callbacks=callbacks,
        extra_headers=extra_headers,
        extra_kwargs=kwargs,
    )

    try:
        return LLMGateway.create(config)
    except ProviderKeyMissingError as exc:
        if not allow_fallback:
            raise

        logger.warning(
            "Primary model %s/%s unavailable due to missing key (%s). Attempting fallback.",
            provider,
            model,
            exc,
        )

        # Fallback 1: Caller-specified fallback
        if fallback_provider and fallback_model:
            fb_config = ModelConfig(
                provider=fallback_provider,
                model=fallback_model,
                temperature=temperature,
                top_p=top_p,
                base_url=base_url,
                timeout=timeout,
                max_retries=max_retries,
                callbacks=callbacks,
                extra_headers=extra_headers,
                extra_kwargs=kwargs,
            )
            return LLMGateway.create(fb_config)

        # Fallback 2: Google Gemini (default cloud workhorse)
        if LLMGateway.is_provider_available(LLMProvider.GOOGLE):
            logger.info("Falling back to default Google Gemini 3 Flash")
            fb_config = ModelConfig(
                provider=LLMProvider.GOOGLE.value,
                model="gemini-3-flash-preview",
                temperature=temperature,
                top_p=top_p,
                timeout=timeout,
                max_retries=max_retries,
                callbacks=callbacks,
                extra_kwargs=kwargs,
            )
            return LLMGateway.create(fb_config)

        # Fallback 3: Local Ollama
        if LLMGateway.is_provider_available(LLMProvider.OLLAMA):
            logger.info("Falling back to local Ollama")
            fb_config = ModelConfig(
                provider=LLMProvider.OLLAMA.value,
                model="auto",
                temperature=temperature,
                top_p=top_p,
                timeout=timeout,
                max_retries=max_retries,
                callbacks=callbacks,
                extra_kwargs=kwargs,
            )
            return LLMGateway.create(fb_config)

        raise


def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs: Any,
) -> LegacyLLMClientAdapter:
    """Clean-room drop-in replacement for any legacy create_llm_client call."""
    llm = instantiate_model(provider=provider, model=model, base_url=base_url, **kwargs)
    return LegacyLLMClientAdapter(llm=llm, model=model, provider=provider)
