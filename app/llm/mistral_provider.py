import os
from typing import Dict, List, Optional

from mistralai import Mistral

from app.llm.base import EmbeddingProvider, LLMProvider


class MistralProvider(LLMProvider, EmbeddingProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "mistral-small-latest",
        embedding_model: str = "mistral-embed",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        if not self.api_key:
            raise ValueError("Mistral API key not found")

        self.client = Mistral(api_key=self.api_key)
        self.model = model
        self.embedding_model = embedding_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.history: List[Dict[str, str]] = []

        if system_prompt:
            self.history.append({"role": "system", "content": system_prompt})

    def chat(self, message: str) -> str:
        response = self.client.chat.complete(
            model=self.model,
            messages=self.history + [{"role": "user", "content": message}],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content

    def embed(self, text: str) -> List[float]:
        response = self.client.embeddings.create(
            model=self.embedding_model,
            inputs=[text],
        )
        return response.data[0].embedding
