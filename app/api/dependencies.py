import os
from typing import Optional

from app.llm.base import EmbeddingProvider, LLMProvider
from app.llm.local_provider import LocalProvider
from app.llm.mistral_provider import MistralProvider
from app.orchestration.pipeline import DocumentPipeline
from app.standards.registry import StandardRegistry


_chat_provider: Optional[LLMProvider] = None
_embedding_provider: Optional[EmbeddingProvider] = None
_pipeline: Optional[DocumentPipeline] = None
_registry: Optional[StandardRegistry] = None


def _resolve_mode(primary_env: str, legacy_env: str = "MODEL_MODE") -> str:
    primary = os.getenv(primary_env, "").strip().lower()
    if primary:
        return primary
    legacy = os.getenv(legacy_env, "").strip().lower()
    if legacy:
        return legacy
    return ""


def _build_chat_provider(mode: str) -> LLMProvider:
    if mode == "local":
        return LocalProvider()
    if mode == "api":
        return MistralProvider()
    if not mode:
        try:
            return MistralProvider()
        except ValueError:
            return LocalProvider()
    raise ValueError("Unsupported CHAT_MODE. Use 'local' or 'api'.")


def _build_embedding_provider(mode: str) -> EmbeddingProvider:
    if mode == "local":
        return LocalProvider()
    if mode == "api":
        return MistralProvider()
    if not mode:
        try:
            return MistralProvider()
        except ValueError:
            return LocalProvider()
    raise ValueError("Unsupported EMBED_MODE. Use 'local' or 'api'.")


def get_chat_provider() -> LLMProvider:
    global _chat_provider
    if _chat_provider is None:
        _chat_provider = _build_chat_provider(_resolve_mode("CHAT_MODE"))
    return _chat_provider


def get_embedding_provider() -> EmbeddingProvider:
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = _build_embedding_provider(_resolve_mode("EMBED_MODE"))
    return _embedding_provider


def get_llm_provider() -> LLMProvider:
    return get_chat_provider()


def get_standard_registry() -> StandardRegistry:
    global _registry
    if _registry is None:
        _registry = StandardRegistry()
    return _registry


def get_pipeline() -> DocumentPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = DocumentPipeline(
            llm_provider=get_chat_provider(),
            embedding_provider=get_embedding_provider(),
            registry=get_standard_registry(),
        )
    return _pipeline
