"""LLM utilities — environment bridging, multi-model tiering, caching, and clean-room gateway."""

from novaswarm.llm.cache import init_langcache
from novaswarm.llm.client_factory import (
    LegacyLLMClientAdapter,
    create_llm_client,
    instantiate_model,
)
from novaswarm.llm.env_bridge import bridge_env_vars
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
from novaswarm.llm.model_tier import build_llm_map


def extract_text(content) -> str:
    """Extract plain text from a LangChain response's ``.content`` attribute.

    Backward-compatible alias for ``extract_clean_text``.
    """
    return extract_clean_text(content)


__all__ = [
    "LLMError",
    "LLMGateway",
    "LLMProvider",
    "LegacyLLMClientAdapter",
    "ModelConfig",
    "ModelInstantiationError",
    "ProviderKeyMissingError",
    "ReasoningModelAdapter",
    "UnsupportedProviderError",
    "bridge_env_vars",
    "build_llm_map",
    "create_llm_client",
    "extract_clean_text",
    "extract_text",
    "init_langcache",
    "instantiate_model",
    "strip_reasoning_tags",
]
