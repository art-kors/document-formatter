import argparse
from collections import Counter
from pathlib import Path
import sys
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.rag_agent.retriever import GraphRAGRetriever, VectorIndex
from app.llm.base import EmbeddingProvider, LLMProvider
from app.standards.ingest import StandardIngestor


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
        return "FakeProvider: answer generation is disabled in smoke mode."

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


def build_retriever(standard_id: str) -> GraphRAGRetriever:
    ingestor = StandardIngestor()
    bundle = ingestor.ingest_pdf(standard_id)
    cleaned_text = Path(bundle.cleaned_text_path).read_text(encoding="utf-8")
    artifacts = ingestor.ingest_text(
        standard_id=f"{standard_id}_smoke",
        standard_text=cleaned_text,
        embedding_provider=FakeProvider(),
    )

    vector_index = VectorIndex(
        FakeProvider(),
        collection_name=f"smoke_{standard_id}",
        reset_collection=True,
    )
    vector_index.add_documents(
        texts=[node.content for node in artifacts.nodes],
        metadatas=[
            {
                "entity_id": node.id,
                "entity_type": node.type,
                "entity_name": node.name,
            }
            for node in artifacts.nodes
        ],
    )
    return GraphRAGRetriever(artifacts.graph, vector_index, FakeProvider())


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for graph-aware RAG retrieval")
    parser.add_argument("query", nargs="?", default="Какая подпись должна быть у рисунка?")
    parser.add_argument("--standard-id", default="gost_7_32_2017")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    retriever = build_retriever(args.standard_id)
    result = retriever.retrieve(args.query, top_k=args.top_k)

    print(f"Query: {args.query}")
    print(f"Matched signals: {result['matched_signals']}")
    print("Top candidate rules:")
    for item in result["candidate_rules"][: args.top_k]:
        metadata = item.get("metadata", {})
        print(
            "- "
            f"{metadata.get('number', '?')} | "
            f"object={metadata.get('object_type', '')} | "
            f"constraint={metadata.get('constraint_type', '')} | "
            f"score={item.get('score', 0.0)} | "
            f"{item.get('name', '')}"
        )

    print("Supporting entities:")
    for item in result["supporting_entities"][: args.top_k]:
        print(f"- {item.get('type')} | {item.get('name')} | score={item.get('score', 0.0)}")


if __name__ == "__main__":
    main()
