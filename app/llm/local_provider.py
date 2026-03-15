from typing import List

from app.llm.base import EmbeddingProvider, LLMProvider


class LocalProvider(LLMProvider, EmbeddingProvider):
    def __init__(self, model_name: str = "local-placeholder"):
        self.model_name = model_name

    def chat(self, message: str) -> str:
        return (
            "LocalProvider is configured as a placeholder. "
            "Connect a local model implementation to enable chat responses."
        )

    def embed(self, text: str) -> List[float]:
        return []
