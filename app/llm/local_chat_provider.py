import json
import os
from typing import Optional
from urllib import error, request

from app.llm.base import LLMProvider


class LocalChatProvider(LLMProvider):
    def __init__(
        self,
        backend: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        system_prompt: Optional[str] = None,
    ):
        self.backend = (backend or os.getenv("LOCAL_CHAT_BACKEND") or "ollama").strip().lower()
        if self.backend != "ollama":
            raise ValueError("Unsupported LOCAL_CHAT_BACKEND. Use 'ollama'.")

        self.base_url = (base_url or os.getenv("LOCAL_CHAT_BASE_URL") or "http://ollama:11434").rstrip("/")
        self.model = (model or os.getenv("LOCAL_CHAT_MODEL") or "qwen2.5:3b").strip()
        if not self.model:
            raise ValueError("LOCAL_CHAT_MODEL must not be empty")

        raw_temperature = temperature
        if raw_temperature is None:
            raw_temperature = os.getenv("LOCAL_CHAT_TEMPERATURE", "0.2")
        self.temperature = float(raw_temperature)
        self.system_prompt = system_prompt or os.getenv("LOCAL_CHAT_SYSTEM_PROMPT") or ""

    def chat(self, message: str) -> str:
        payload = {
            "model": self.model,
            "prompt": message,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        if self.system_prompt:
            payload["system"] = self.system_prompt

        response = self._post_json("/api/generate", payload)
        text = str(response.get("response") or "").strip()
        if not text:
            raise ValueError(f"Local chat response is invalid: {response}")
        return text

    def _post_json(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url}{path}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"Local chat request failed: {exc.code} {raw}") from exc
        except error.URLError as exc:
            raise ValueError(
                "Local chat backend is unreachable. Ensure Ollama is running and LOCAL_CHAT_BASE_URL is correct. "
                f"Details: {exc.reason}"
            ) from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Local chat backend returned invalid JSON: {raw[:200]}") from exc
