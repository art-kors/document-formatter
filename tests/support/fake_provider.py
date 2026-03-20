from collections import Counter
from typing import List

from app.llm.base import EmbeddingProvider, LLMProvider


class FakeProvider(LLMProvider, EmbeddingProvider):
    BASIS = [
        "рисунок",
        "подпись",
        "таблица",
        "заголовок",
        "источник",
        "приложение",
        "нумерация",
        "наименование",
        "титульный",
        "реферат",
        "содержание",
        "раздел",
    ]

    def chat(self, message: str) -> str:
        return "ok"

    def embed(self, text: str) -> List[float]:
        normalized = text.lower()
        replacements = {
            "иллюстрации": "рисунок",
            "иллюстрация": "рисунок",
            "рисунка": "рисунок",
            "рисунке": "рисунок",
            "таблицы": "таблица",
            "таблице": "таблица",
            "источников": "источник",
            "источники": "источник",
            "титульного": "титульный",
            "титульном": "титульный",
            "разделов": "раздел",
            "раздела": "раздел",
        }
        for source, target in replacements.items():
            normalized = normalized.replace(source, target)
        counts = Counter(normalized.split())
        return [float(counts.get(token, 0)) for token in self.BASIS]
