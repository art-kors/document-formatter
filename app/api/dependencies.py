from typing import Optional

from app.llm.base import LLMProvider
from app.llm.local_provider import LocalProvider
from app.llm.mistral_provider import MistralProvider
from app.orchestration.pipeline import DocumentPipeline
from app.standards.registry import StandardRegistry


_llm_provider: Optional[LLMProvider] = None
_pipeline: Optional[DocumentPipeline] = None
_registry: Optional[StandardRegistry] = None


def get_llm_provider() -> LLMProvider:
    global _llm_provider
    if _llm_provider is None:
        try:
            _llm_provider = MistralProvider()
        except ValueError:
            _llm_provider = LocalProvider()
    return _llm_provider


def get_standard_registry() -> StandardRegistry:
    global _registry
    if _registry is None:
        _registry = StandardRegistry()
    return _registry


def get_pipeline() -> DocumentPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = DocumentPipeline(
            llm_provider=get_llm_provider(),
            registry=get_standard_registry(),
        )
    return _pipeline
