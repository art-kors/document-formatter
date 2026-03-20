import json
import os
from typing import Dict, List, Optional
from urllib import error, request

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
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        if not self.api_key:
            raise ValueError("Mistral API key not found")

        self.base_url = (base_url or os.getenv("MISTRAL_BASE_URL") or "https://api.mistral.ai").rstrip("/")
        self.model = model
        self.embedding_model = embedding_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.history: List[Dict[str, str]] = []

        if system_prompt:
            self.history.append({"role": "system", "content": system_prompt})

    def chat(self, message: str) -> str:
        payload = {
            "model": self.model,
            "messages": self.history + [{"role": "user", "content": message}],
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens

        response = self._post_json("/v1/chat/completions", payload)
        try:
            return str(response["choices"][0]["message"]["content"])
        except Exception as exc:
            raise ValueError(f"Mistral chat response is invalid: {response}") from exc

    def embed(self, text: str) -> List[float]:
        payload = {
            "model": self.embedding_model,
            "inputs": [text],
        }
        response = self._post_json("/v1/embeddings", payload)
        try:
            embedding = response["data"][0]["embedding"]
        except Exception as exc:
            raise ValueError(f"Mistral embedding response is invalid: {response}") from exc
        return [float(value) for value in embedding]

    def _post_json(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url}{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"Mistral API request failed: {exc.code} {raw}") from exc
        except error.URLError as exc:
            raise ValueError(f"Mistral API is unreachable: {exc.reason}") from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Mistral API returned invalid JSON: {raw[:200]}") from exc
