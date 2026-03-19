import hashlib
import json
import os
from pathlib import Path
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
        timeout_s: Optional[int] = None,
        num_predict: Optional[int] = None,
        num_ctx: Optional[int] = None,
        num_thread: Optional[int] = None,
        keep_alive: Optional[str] = None,
        use_cache: Optional[bool] = None,
        cache_dir: Optional[str] = None,
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
        self.timeout_s = int(timeout_s or os.getenv("LOCAL_CHAT_TIMEOUT", "120"))
        self.num_predict = int(num_predict or os.getenv("LOCAL_CHAT_NUM_PREDICT", "192"))
        self.num_ctx = int(num_ctx or os.getenv("LOCAL_CHAT_NUM_CTX", "2048"))

        default_threads = min(os.cpu_count() or 4, 8)
        raw_num_thread = num_thread or os.getenv("LOCAL_CHAT_NUM_THREAD") or default_threads
        self.num_thread = int(raw_num_thread)
        self.keep_alive = keep_alive or os.getenv("LOCAL_CHAT_KEEP_ALIVE", "10m")

        if use_cache is None:
            raw_use_cache = (os.getenv("LOCAL_CHAT_CACHE", "1") or "1").strip().lower()
            self.use_cache = raw_use_cache not in {"0", "false", "no"}
        else:
            self.use_cache = use_cache

        cache_path = cache_dir or os.getenv("LOCAL_CHAT_CACHE_DIR") or ".cache/local_chat"
        self.cache_dir = Path(cache_path)
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def chat(self, message: str) -> str:
        cache_key = self._cache_key(message)
        if self.use_cache:
            cached = self._read_cache(cache_key)
            if cached is not None:
                return cached

        payload = {
            "model": self.model,
            "prompt": message,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.num_predict,
                "num_ctx": self.num_ctx,
                "num_thread": self.num_thread,
            },
        }
        if self.system_prompt:
            payload["system"] = self.system_prompt

        response = self._post_json("/api/generate", payload)
        text = str(response.get("response") or "").strip()
        if not text:
            raise ValueError(f"Local chat response is invalid: {response}")
        if self.use_cache:
            self._write_cache(cache_key, text)
        return text

    def _cache_key(self, message: str) -> str:
        digest = hashlib.sha256()
        digest.update(self.backend.encode("utf-8"))
        digest.update(self.base_url.encode("utf-8"))
        digest.update(self.model.encode("utf-8"))
        digest.update(str(self.temperature).encode("utf-8"))
        digest.update(str(self.num_predict).encode("utf-8"))
        digest.update(str(self.num_ctx).encode("utf-8"))
        digest.update(str(self.num_thread).encode("utf-8"))
        digest.update(self.keep_alive.encode("utf-8"))
        digest.update(self.system_prompt.encode("utf-8"))
        digest.update(message.encode("utf-8"))
        return digest.hexdigest()

    def _read_cache(self, cache_key: str) -> Optional[str]:
        path = self.cache_dir / f"{cache_key}.txt"
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None

    def _write_cache(self, cache_key: str, text: str) -> None:
        path = self.cache_dir / f"{cache_key}.txt"
        try:
            path.write_text(text, encoding="utf-8")
        except OSError:
            pass

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
            with request.urlopen(req, timeout=self.timeout_s) as response:
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
