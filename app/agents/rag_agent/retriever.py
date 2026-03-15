import hashlib
import math
import re
from typing import Dict, List, Optional, Tuple

try:
    from chromadb import PersistentClient
except ImportError:  # pragma: no cover - environment fallback
    PersistentClient = None

from app.agents.rag_agent.prompts import ANSWER_PROMPT
from app.llm.base import EmbeddingProvider, LLMProvider
from app.standards.graph_builder import KnowledgeGraph


GRAPH_RULE_EDGE_TYPES = [
    "contains",
    "applies_to",
    "constrains",
    "same_object_type",
    "same_constraint_type",
    "rule_follows",
    "mentions",
    "covers",
    "references",
    "depends_on",
    "prerequisite",
]
RULE_EDGE_WEIGHTS = {
    "depends_on": 2.3,
    "prerequisite": 1.9,
    "references": 1.5,
    "applies_to": 1.4,
    "constrains": 1.4,
    "contains": 1.2,
    "covers": 1.1,
    "same_constraint_type": 1.1,
    "same_object_type": 1.0,
    "rule_follows": 0.8,
    "mentions": 0.6,
}
SUPPORT_CONTEXT_EDGE_TYPES = [
    "applies_to",
    "constrains",
    "mentions",
    "contains",
    "references",
    "depends_on",
    "prerequisite",
]
OBJECT_QUERY_HINTS = {
    "figure": ["рисунок", "рисунка", "рисунке", "иллюстрац", "figure"],
    "table": ["таблица", "таблиц", "table"],
    "formula": ["формул", "уравнен", "formula"],
    "appendix": ["приложени", "appendix"],
    "title_page": ["титульн", "титул"],
    "contents": ["содержание", "оглавление"],
    "references": ["источник", "список литературы", "библиограф"],
    "heading": ["заголов", "подзаголов"],
    "section": ["раздел", "подраздел", "пункт"],
}
CONSTRAINT_QUERY_HINTS = {
    "caption_required": ["подпись", "наименование", "caption"],
    "required_presence": ["обязател", "должен", "должны", "наличие"],
    "formatting": ["оформлен", "шрифт", "абзац", "интервал", "выравнив"],
    "numbering": ["нумерац", "номер", "обозначен"],
    "reference_required": ["ссылка", "ссылки"],
    "placement": ["располаг", "размещ", "по центру"],
    "sequence": ["порядок", "последовательн"],
    "language_requirement": ["язык", "русск"],
}


class _InMemoryCollection:
    def __init__(self) -> None:
        self.rows: List[Dict] = []

    def add(self, ids: List[str], documents: List[str], embeddings: List[List[float]], metadatas: List[dict]) -> None:
        for item_id, document, embedding, metadata in zip(ids, documents, embeddings, metadatas):
            self.rows.append(
                {
                    "id": item_id,
                    "document": document,
                    "embedding": embedding,
                    "metadata": metadata,
                }
            )

    def query(self, query_embeddings: List[List[float]], n_results: int = 5) -> Dict:
        query_embedding = query_embeddings[0]
        ranked = sorted(
            self.rows,
            key=lambda item: _cosine_similarity(query_embedding, item["embedding"]),
            reverse=True,
        )[:n_results]
        return {
            "ids": [[item["id"] for item in ranked]],
            "documents": [[item["document"] for item in ranked]],
            "metadatas": [[item["metadata"] for item in ranked]],
        }


class VectorIndex:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        persist_directory: str = "./app/storage/chroma",
        collection_name: str = "document_rules",
        reset_collection: bool = False,
    ):
        self.embedding_provider = embedding_provider
        self.collection_name = collection_name

        if PersistentClient is None:
            self.client = None
            self.collection = _InMemoryCollection()
            return

        self.client = PersistentClient(path=persist_directory)
        if reset_collection:
            try:
                self.client.delete_collection(name=collection_name)
            except Exception:
                pass
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def add_documents(self, texts: List[str], metadatas: List[dict]) -> None:
        embeddings = [self.embedding_provider.embed(text) for text in texts]
        ids = [hashlib.md5(f"{self.collection_name}:{text}".encode("utf-8")).hexdigest() for text in texts]

        valid_ids = []
        valid_texts = []
        valid_embeddings = []
        valid_metadatas = []
        for idx, embedding in enumerate(embeddings):
            if embedding:
                valid_ids.append(ids[idx])
                valid_texts.append(texts[idx])
                valid_embeddings.append(embedding)
                valid_metadatas.append(metadatas[idx])

        if valid_ids:
            self.collection.add(
                ids=valid_ids,
                documents=valid_texts,
                embeddings=valid_embeddings,
                metadatas=valid_metadatas,
            )

    def query(self, query_text: str, n_results: int = 5) -> Optional[Dict]:
        query_embedding = self.embedding_provider.embed(query_text)
        if not query_embedding:
            return None
        return self.collection.query(query_embeddings=[query_embedding], n_results=n_results)


class GraphRAGRetriever:
    def __init__(self, graph: KnowledgeGraph, vector_index: VectorIndex, llm_provider: LLMProvider):
        self.graph = graph
        self.vector_index = vector_index
        self.llm_provider = llm_provider

    def retrieve(self, query: str, top_k: int = 5) -> Dict:
        vector_results = self.vector_index.query(query, n_results=top_k)
        if not vector_results:
            return {
                "query": query,
                "context": [],
                "candidate_rules": [],
                "supporting_entities": [],
                "vector_results": [],
                "graph_entities": [],
                "matched_signals": {"object_types": [], "constraint_types": [], "keywords": []},
            }

        vector_hits = self._extract_vector_hits(vector_results)
        seed_ids = [hit[0] for hit in vector_hits]
        rule_scores: Dict[str, float] = {}
        support_scores: Dict[str, float] = {}

        for rank, (entity_id, _metadata) in enumerate(vector_hits, start=1):
            base_score = max(0.0, (top_k + 1 - rank) / max(top_k, 1))
            self._apply_seed(entity_id, base_score, rule_scores, support_scores)

        matched_object_types = self._match_signal_nodes(query, "object_type", OBJECT_QUERY_HINTS, rule_scores, support_scores, bonus=1.2)
        matched_constraint_types = self._match_signal_nodes(query, "constraint", CONSTRAINT_QUERY_HINTS, rule_scores, support_scores, bonus=1.0)
        matched_keywords = self._match_keyword_nodes(query, rule_scores, support_scores, bonus=0.8)

        ranked_rule_ids = [rule_id for rule_id, _ in sorted(rule_scores.items(), key=lambda item: item[1], reverse=True)[:top_k]]
        candidate_rules = [self._build_context_item(rule_id, score=rule_scores[rule_id]) for rule_id in ranked_rule_ids]

        support_ids: List[str] = []
        for rule_id in ranked_rule_ids:
            support_ids.extend(
                self.graph.get_related_nodes(
                    rule_id,
                    edge_types=SUPPORT_CONTEXT_EDGE_TYPES,
                )
            )
        ordered_support_ids = [
            node_id
            for node_id, _ in sorted(
                ((node_id, support_scores.get(node_id, 0.0)) for node_id in dict.fromkeys(support_ids)),
                key=lambda item: item[1],
                reverse=True,
            )
            if node_id not in ranked_rule_ids
        ][: top_k * 2]
        supporting_entities = [self._build_context_item(node_id, score=support_scores.get(node_id, 0.0)) for node_id in ordered_support_ids]

        context = candidate_rules + supporting_entities
        graph_entities = list(dict.fromkeys(seed_ids + ranked_rule_ids + ordered_support_ids))
        return {
            "query": query,
            "context": context,
            "candidate_rules": candidate_rules,
            "supporting_entities": supporting_entities,
            "vector_results": vector_results,
            "graph_entities": graph_entities,
            "matched_signals": {
                "object_types": matched_object_types,
                "constraint_types": matched_constraint_types,
                "keywords": matched_keywords,
            },
        }

    def answer(self, question: str) -> Dict:
        retrieval_results = self.retrieve(question)
        context_text = "\n\n".join(
            self._format_context_item(item)
            for item in retrieval_results["context"][:10]
        )

        answer = self.llm_provider.chat(
            ANSWER_PROMPT.format(context=context_text, question=question)
        )
        sources = [
            {
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "type": item.get("type", ""),
                "score": item.get("score", 0.0),
                "metadata": item.get("metadata", {}),
                "content": f"{item.get('content', '')[:200]}...",
            }
            for item in retrieval_results["candidate_rules"][:5]
        ]
        return {
            "answer": answer,
            "sources": sources,
            "graph_entities_count": len(retrieval_results["graph_entities"]),
            "matched_signals": retrieval_results["matched_signals"],
        }

    def _extract_vector_hits(self, vector_results: Dict) -> List[Tuple[str, Dict]]:
        hits: List[Tuple[str, Dict]] = []
        for metadata_list in vector_results.get("metadatas", []):
            for metadata in metadata_list:
                entity_id = metadata.get("entity_id")
                if entity_id:
                    hits.append((entity_id, metadata))
        return hits

    def _apply_seed(
        self,
        entity_id: str,
        base_score: float,
        rule_scores: Dict[str, float],
        support_scores: Dict[str, float],
    ) -> None:
        node = self.graph.get_node(entity_id)
        if not node:
            return

        support_scores[entity_id] = max(support_scores.get(entity_id, 0.0), base_score)
        if node.get("type") == "rule":
            rule_scores[entity_id] = rule_scores.get(entity_id, 0.0) + base_score * 2.0

        related_edges = self.graph.get_related_edges(entity_id, edge_types=GRAPH_RULE_EDGE_TYPES)
        for edge in related_edges:
            neighbor_id = edge["neighbor_id"]
            edge_type = edge["type"]
            weight = RULE_EDGE_WEIGHTS.get(edge_type, 1.0)
            support_scores[neighbor_id] = max(support_scores.get(neighbor_id, 0.0), base_score * min(weight, 1.4))
            if edge.get("neighbor_type") == "rule":
                if node.get("type") == "rule":
                    weight *= 1.1
                rule_scores[neighbor_id] = rule_scores.get(neighbor_id, 0.0) + base_score * weight

    def _match_signal_nodes(
        self,
        query: str,
        node_type: str,
        hint_map: Dict[str, List[str]],
        rule_scores: Dict[str, float],
        support_scores: Dict[str, float],
        bonus: float,
    ) -> List[str]:
        lowered = query.lower()
        matched: List[str] = []
        for node in self.graph.find_nodes_by_type(node_type):
            node_name = node.get("name", "")
            hints = hint_map.get(node_name, [node_name.replace("_", " ")])
            if any(hint in lowered for hint in hints if hint):
                matched.append(node_name)
                node_id = node["id"]
                support_scores[node_id] = max(support_scores.get(node_id, 0.0), bonus)
                for edge in self.graph.get_related_edges(node_id, edge_types=GRAPH_RULE_EDGE_TYPES, neighbor_types=["rule"]):
                    weight = RULE_EDGE_WEIGHTS.get(edge["type"], 1.0)
                    rule_scores[edge["neighbor_id"]] = rule_scores.get(edge["neighbor_id"], 0.0) + bonus * weight
        return matched

    def _match_keyword_nodes(
        self,
        query: str,
        rule_scores: Dict[str, float],
        support_scores: Dict[str, float],
        bonus: float,
    ) -> List[str]:
        tokens = set(self._tokenize(query))
        matched: List[str] = []
        for node in self.graph.find_nodes_by_type("keyword"):
            keyword = node.get("name", "")
            keyword_tokens = set(self._tokenize(keyword))
            if not keyword_tokens:
                continue
            if tokens & keyword_tokens:
                matched.append(keyword)
                node_id = node["id"]
                support_scores[node_id] = max(support_scores.get(node_id, 0.0), bonus)
                for edge in self.graph.get_related_edges(node_id, edge_types=GRAPH_RULE_EDGE_TYPES, neighbor_types=["rule"]):
                    weight = RULE_EDGE_WEIGHTS.get(edge["type"], 1.0)
                    rule_scores[edge["neighbor_id"]] = rule_scores.get(edge["neighbor_id"], 0.0) + bonus * weight
        return matched

    def _build_context_item(self, node_id: str, score: float) -> Dict:
        node = self.graph.get_node(node_id)
        if not node:
            return {"id": node_id, "score": score, "type": "unknown", "name": node_id, "content": "", "metadata": {}}
        return {
            "id": node_id,
            "name": node.get("name", ""),
            "type": node.get("type", ""),
            "content": node.get("content", ""),
            "metadata": node.get("metadata", {}),
            "score": round(score, 4),
        }

    def _format_context_item(self, item: Dict) -> str:
        metadata = item.get("metadata", {}) or {}
        meta_parts = []
        for key in ["number", "section_title", "object_type", "constraint_type"]:
            value = metadata.get(key)
            if value:
                meta_parts.append(f"{key}={value}")
        meta_suffix = f" ({', '.join(meta_parts)})" if meta_parts else ""
        return f"[{item['type'].upper()}] {item['name']}{meta_suffix}:\n{item['content']}"

    def _tokenize(self, text: str) -> List[str]:
        return [token for token in re.split(r"[^\wа-яА-Я]+", text.lower()) if len(token) >= 3]


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(l * r for l, r in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)
