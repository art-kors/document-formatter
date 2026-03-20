import hashlib
import os
import warnings
from typing import Any, List, Optional

from app.llm.base import EmbeddingProvider, LLMProvider


class LocalProvider(LLMProvider, EmbeddingProvider):
    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        encoder: Optional[Any] = None,
        backend: Optional[str] = None,
        embedding_dim: int = 256,
    ):
        self.model_name = model_name or os.getenv(
            "LOCAL_EMBEDDING_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        )
        self.device = device or os.getenv("LOCAL_EMBEDDING_DEVICE")
        self.backend = (backend or os.getenv("LOCAL_EMBEDDING_BACKEND") or "fastembed").strip().lower()
        self.embedding_dim = embedding_dim
        self._encoder = encoder
        self._runtime_backend = "injected" if encoder is not None else self.backend

    def chat(self, message: str) -> str:
        return (
            "LocalProvider is running in retrieval-only mode. "
            "Automatic document analysis and graph retrieval are available locally, "
            "but chat generation is not enabled in this mode."
        )

    def embed(self, text: str) -> List[float]:
        normalized_text = " ".join(text.split())
        if not normalized_text:
            return []

        if self._encoder is None and self.backend != "hash":
            self._load_encoder_with_fallback()

        if self._encoder is not None:
            embedding = self._encoder.encode(
                normalized_text,
                normalize_embeddings=True,
            )
            if hasattr(embedding, "tolist"):
                embedding = embedding.tolist()
            if not embedding:
                return []
            return [float(value) for value in embedding]

        return self._hash_embed(normalized_text)

    def _load_encoder_with_fallback(self) -> None:
        if self._encoder is not None:
            return

        loaders = {
            "sentence-transformers": self._load_sentence_transformer,
            "fastembed": self._load_fastembed,
            "hash": lambda: None,
        }
        if self.backend not in loaders:
            raise ValueError(
                "Unsupported LOCAL_EMBEDDING_BACKEND. Use 'sentence-transformers', 'fastembed', or 'hash'."
            )

        try:
            loaders[self.backend]()
            self._runtime_backend = self.backend
        except Exception as exc:  # pragma: no cover - depends on local environment
            self._encoder = None
            self._runtime_backend = "hash"
            warnings.warn(
                f"Local embedding backend '{self.backend}' is unavailable ({exc}). Falling back to hash embeddings.",
                RuntimeWarning,
                stacklevel=2,
            )

    def _load_sentence_transformer(self) -> None:
        from sentence_transformers import SentenceTransformer

        init_kwargs = {}
        if self.device:
            init_kwargs["device"] = self.device
        self._encoder = SentenceTransformer(self.model_name, **init_kwargs)

    def _load_fastembed(self) -> None:
        from fastembed import TextEmbedding

        self._encoder = _FastEmbedAdapter(TextEmbedding(model_name=self.model_name))

    def _hash_embed(self, text: str) -> List[float]:
        features = self._tokenize(text)
        if not features:
            return []

        vector = [0.0] * self.embedding_dim
        for token in features:
            bucket = self._stable_hash(token) % self.embedding_dim
            sign = 1.0 if self._stable_hash(f"sign::{token}") % 2 == 0 else -1.0
            weight = 1.0 + min(len(token), 12) / 12.0
            vector[bucket] += sign * weight

        norm = sum(value * value for value in vector) ** 0.5
        if norm == 0.0:
            return []
        return [value / norm for value in vector]

    def _tokenize(self, text: str) -> List[str]:
        normalized = text.lower().replace("\u0451", "\u0435")
        words = [token for token in ''.join(char if char.isalnum() else ' ' for char in normalized).split() if len(token) >= 2]
        if not words:
            return []

        features = list(words)
        for word in words:
            if len(word) >= 4:
                features.extend(word[index : index + 3] for index in range(len(word) - 2))
        return features

    def _stable_hash(self, token: str) -> int:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, byteorder="big", signed=False)


class _FastEmbedAdapter:
    def __init__(self, model: Any):
        self.model = model

    def encode(self, text: str, normalize_embeddings: bool = True) -> List[float]:
        embedding = list(self.model.embed([text]))[0]
        if hasattr(embedding, "tolist"):
            embedding = embedding.tolist()
        values = [float(value) for value in embedding]
        if not normalize_embeddings:
            return values
        norm = sum(value * value for value in values) ** 0.5
        if norm == 0.0:
            return values
        return [value / norm for value in values]
