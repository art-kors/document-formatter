"""
GraphRAG Retriever with IndexRAG enhancements.

This module implements:
- Standard GraphRAG retrieval (unchanged)
- IndexRAG: Bridging Facts for Cross-Document Reasoning at Index Time
  Paper: https://arxiv.org/pdf/2603.16415

Key IndexRAG concepts:
- Atomic Knowledge Units (AKUs): minimal retrievable units extracted from documents
- Bridging Facts: pre-computed connections across documents for cross-document reasoning
- Index-time reasoning: shift reasoning from inference to indexing
- Balanced Context Selection: control proportion of AKUs vs bridging facts
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union, TYPE_CHECKING

try:
    from chromadb import PersistentClient
except ImportError:  # pragma: no cover - environment fallback
    PersistentClient = None

from .prompts import (
    AKU_EXTRACTION_PROMPT,
    AKU_EXTRACTION_PROMPT_RU,
    ANSWER_PROMPT,
    BRIDGING_FACT_PROMPT,
    BRIDGING_FACT_PROMPT_RU,
    ENTITY_EXTRACTION_PROMPT,
)


# =============================================================================
# Configuration (removing hardcoded values - paper-inspired defaults)
# =============================================================================

@dataclass
class IndexRAGConfig:
    """
    Configuration for IndexRAG components.

    Paper parameters:
    - τ (entity_max_document_frequency): upper bound threshold for bridge entities
    - kb (default_max_bridging_facts): maximum bridging facts in context

    These defaults match the paper's experimental setup.
    """

    # Entity frequency thresholds
    # Paper: "The lower bound ensures that bridge entities connect at least two documents,
    # while the upper bound τ excludes overly generic entities"
    entity_min_document_frequency: int = 2
    entity_max_document_frequency: int = 10  # τ in paper

    # Bridging fact generation limits
    # Paper: "We limit the number of source documents to 5 and facts per document to 8"
    max_source_documents: int = 5
    max_facts_per_document: int = 8

    # Balanced context selection
    # Paper: "bridging facts are considerably shorter than AKUs on average (166 vs. 634 characters),
    # they tend to dominate the top-k, crowding out the longer, information-dense AKUs"
    default_max_bridging_facts: int = 3  # kb in paper

    # Retrieval defaults
    default_top_k: int = 5
    default_context_items: int = 10

    # Language for prompts
    language: str = "ru"

    # Custom prompts (override defaults)
    custom_aku_prompt: Optional[str] = None
    custom_bridging_prompt: Optional[str] = None


@dataclass
class GraphRAGConfig:
    """
    Configuration for GraphRAG retrieval.

    Edge types and weights can be customized for different domains.
    These defaults are optimized for document standard checking.
    """

    edge_types: List[str] = field(default_factory=lambda: [
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
    ])

    edge_weights: Dict[str, float] = field(default_factory=lambda: {
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
    })

    support_context_edge_types: List[str] = field(default_factory=lambda: [
        "applies_to",
        "constrains",
        "mentions",
        "contains",
        "references",
        "depends_on",
        "prerequisite",
    ])

    # Signal matching bonuses (tunable)
    object_type_bonus: float = 1.8
    constraint_type_bonus: float = 1.0
    keyword_bonus: float = 0.8


# Default configurations
DEFAULT_INDEXRAG_CONFIG = IndexRAGConfig()
DEFAULT_GRAPH_CONFIG = GraphRAGConfig()

# Query hints for domain-specific matching (customizable, not hardcoded in methods)
DEFAULT_OBJECT_QUERY_HINTS: Dict[str, List[str]] = {
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

DEFAULT_CONSTRAINT_QUERY_HINTS: Dict[str, List[str]] = {
    "caption_required": ["подпись", "наименование", "caption"],
    "required_presence": ["обязател", "должен", "должны", "наличие"],
    "formatting": ["оформлен", "шрифт", "абзац", "интервал", "выравнив"],
    "numbering": ["нумерац", "номер", "обозначен"],
    "reference_required": ["ссылка", "ссылки"],
    "placement": ["располаг", "размещ", "по центру"],
    "sequence": ["порядок", "последовательн"],
    "language_requirement": ["язык", "русск"],
}


# =============================================================================
# IndexRAG Data Structures
# =============================================================================

@dataclass
class AtomicKnowledgeUnit:
    """
    Atomic Knowledge Unit (AKU) from IndexRAG paper.

    Paper: "we prompt an LLM to extract a set of atomic facts, structured as
    question-answer pairs... We retain only the answers, merging them into a
    single text unit per document as the minimal retrievable unit."
    """
    id: str
    document_id: str
    question: str
    answer: str
    content: str  # Combined Q&A for embedding
    entities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BridgingFact:
    """
    Bridging Fact from IndexRAG paper.

    Paper: "bridging facts that capture cross-document reasoning by linking
    related evidence from different sources... Unlike cross-document summaries,
    bridging facts are constructed to directly answer implicit cross-document
    questions."
    """
    id: str
    entity: str
    content: str
    source_document_ids: List[str] = field(default_factory=list)
    source_aku_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityInfo:
    """Tracks entity occurrences across documents for bridge entity identification."""
    name: str
    document_ids: Set[str] = field(default_factory=set)
    aku_ids: Set[str] = field(default_factory=set)

    @property
    def document_frequency(self) -> int:
        return len(self.document_ids)


# =============================================================================
# IndexRAG Components
# =============================================================================

class AKUExtractor:
    """
    Stage 1 of IndexRAG: Extracts Atomic Knowledge Units and entities from documents.

    Paper: "Given a corpus of n documents, we prompt an LLM to extract a set of
    atomic facts, structured as question-answer pairs, and associated entities
    from each document."
    """

    def __init__(
            self,
            llm_provider: 'LLMProvider',
            config: Optional[IndexRAGConfig] = None,
            custom_prompt: Optional[str] = None,
    ):
        self.llm_provider = llm_provider
        self.config = config or DEFAULT_INDEXRAG_CONFIG

        # Select prompt based on configuration
        if custom_prompt:
            self._prompt_template = custom_prompt
        elif self.config.custom_aku_prompt:
            self._prompt_template = self.config.custom_aku_prompt
        elif self.config.language == "ru":
            self._prompt_template = AKU_EXTRACTION_PROMPT_RU
        else:
            self._prompt_template = AKU_EXTRACTION_PROMPT

    def extract(
            self,
            document_id: str,
            text: str,
            additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[AtomicKnowledgeUnit], List[str]]:
        """
        Extract AKUs and entities from a single document.

        Returns:
            Tuple of (list of AKUs, list of unique entities)
        """
        prompt = self._prompt_template.format(text=text)
        response = self.llm_provider.chat(prompt)

        try:
            parsed = self._parse_response(response)
        except json.JSONDecodeError:
            parsed = {"akus": [], "entities": []}

        akus: List[AtomicKnowledgeUnit] = []
        all_entities: Set[str] = set()

        for idx, aku_data in enumerate(parsed.get("akus", [])):
            question = aku_data.get("question", "").strip()
            answer = aku_data.get("answer", "").strip()
            if not question or not answer:
                continue

            # Create content for embedding
            content = f"Q: {question}\nA: {answer}"
            aku_id = self._generate_aku_id(document_id, idx)

            # Extract entities from this AKU
            aku_entities = self._extract_entities_from_text(question + " " + answer)
            all_entities.update(aku_entities)

            metadata = dict(additional_metadata) if additional_metadata else {}
            metadata["extraction_idx"] = idx

            akus.append(AtomicKnowledgeUnit(
                id=aku_id,
                document_id=document_id,
                question=question,
                answer=answer,
                content=content,
                entities=aku_entities,
                metadata=metadata,
            ))

        # Add explicitly listed entities
        explicit_entities = parsed.get("entities", [])
        all_entities.update(explicit_entities)

        return akus, list(all_entities)

    def _parse_response(self, response: str) -> Dict:
        """Parse LLM response as JSON, handling various formats."""
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group())
        return {"akus": [], "entities": []}

    def _extract_entities_from_text(self, text: str) -> List[str]:
        """Extract potential entities using heuristics (capitalized, quoted)."""
        entities = []
        # Capitalized words (Russian and English)
        capitalized = re.findall(r'\b[А-ЯЁA-Z][а-яёa-zA-Z]*\b', text)
        entities.extend(capitalized)
        # Quoted phrases
        quoted = re.findall(r'["«]([^"»]+)["»]', text)
        entities.extend(quoted)
        return list(set(entities))

    def _generate_aku_id(self, document_id: str, idx: int) -> str:
        return f"aku:{document_id}:{idx}"


class BridgingFactGenerator:
    """
    Stage 2 of IndexRAG: Generates bridging facts for cross-document reasoning.

    Paper: "For each bridge entity e ∈ E_bridge, let D_e be the set of documents
    mentioning e. We collect the subset of facts in each AKU that mention entity e...
    We then prompt the LLM to generate bridging facts."
    """

    def __init__(
            self,
            llm_provider: 'LLMProvider',
            config: Optional[IndexRAGConfig] = None,
            custom_prompt: Optional[str] = None,
    ):
        self.llm_provider = llm_provider
        self.config = config or DEFAULT_INDEXRAG_CONFIG

        if custom_prompt:
            self._prompt_template = custom_prompt
        elif self.config.custom_bridging_prompt:
            self._prompt_template = self.config.custom_bridging_prompt
        elif self.config.language == "ru":
            self._prompt_template = BRIDGING_FACT_PROMPT_RU
        else:
            self._prompt_template = BRIDGING_FACT_PROMPT

    def identify_bridge_entities(
            self,
            entity_registry: Dict[str, EntityInfo],
    ) -> List[str]:
        """
        Identify bridge entities (appearing in multiple documents).

        Paper: "The lower bound ensures that bridge entities connect at least two
        documents, while the upper bound τ excludes overly generic entities."
        """
        bridge_entities = []
        for entity_name, entity_info in entity_registry.items():
            df = entity_info.document_frequency
            min_df = self.config.entity_min_document_frequency
            max_df = self.config.entity_max_document_frequency
            if min_df <= df <= max_df:
                bridge_entities.append(entity_name)
        return bridge_entities

    def generate(
            self,
            entity: str,
            akus_by_document: Dict[str, List[AtomicKnowledgeUnit]],
            entity_info: Optional[EntityInfo] = None,
    ) -> Optional[BridgingFact]:
        """
        Generate a bridging fact for a given entity based on AKUs from multiple documents.

        Paper: "B_e = LLM(e, {a_i[e] : d_i ∈ D_e})"
        """
        # Collect AKUs mentioning this entity
        relevant_akus: List[Tuple[str, AtomicKnowledgeUnit]] = []
        max_total = self.config.max_source_documents * self.config.max_facts_per_document

        for doc_id, akus in akus_by_document.items():
            for aku in akus:
                if self._aku_mentions_entity(aku, entity):
                    relevant_akus.append((doc_id, aku))
                    if len(relevant_akus) >= max_total:
                        break
            if len(relevant_akus) >= max_total:
                break

        # Need at least 2 documents to create a bridge
        doc_ids_with_entity = set(doc_id for doc_id, _ in relevant_akus)
        if len(doc_ids_with_entity) < 2:
            return None

        # Limit source documents
        limited_docs = list(doc_ids_with_entity)[:self.config.max_source_documents]
        filtered_akus = [(doc_id, aku) for doc_id, aku in relevant_akus if doc_id in limited_docs]

        # Build prompt sections
        doc_sections = self._build_doc_sections(filtered_akus, entity)
        prompt = self._prompt_template.format(entity=entity, doc_sections=doc_sections)

        response = self.llm_provider.chat(prompt)

        try:
            facts = json.loads(response)
            if isinstance(facts, str):
                facts = json.loads(facts)
        except json.JSONDecodeError:
            return None

        if not facts or not isinstance(facts, list) or len(facts) == 0:
            return None

        # Combine all facts
        combined_content = " ".join(str(f) for f in facts if f)

        return BridgingFact(
            id=self._generate_bridging_fact_id(entity),
            entity=entity,
            content=combined_content,
            source_document_ids=list(limited_docs),
            source_aku_ids=[aku.id for _, aku in filtered_akus],
        )

    def _aku_mentions_entity(self, aku: AtomicKnowledgeUnit, entity: str) -> bool:
        """Check if AKU mentions the given entity."""
        text = (aku.question + " " + aku.answer + " " + aku.content).lower()
        return entity.lower() in text

    def _build_doc_sections(
            self,
            akus: List[Tuple[str, AtomicKnowledgeUnit]],
            entity: str,
    ) -> str:
        """Build document sections for the bridging fact prompt."""
        sections = []
        seen_docs = set()

        for doc_id, aku in akus:
            if doc_id not in seen_docs:
                sections.append(f"\n--- Document: {doc_id} ---")
                seen_docs.add(doc_id)
            sections.append(f"- {aku.content}")

        return "\n".join(sections)

    def _generate_bridging_fact_id(self, entity: str) -> str:
        return f"bridge:{entity}:{hashlib.md5(entity.encode()).hexdigest()[:8]}"


class BalancedContextSelector:
    """
    Balanced Context Selection from IndexRAG paper.

    Paper Algorithm 1: "We greedily build the context C by iterating over R in order.
    Each entry is included if it is an AKU or if the number of bridging facts already
    in C is below k_b, until |C| = k."
    """

    def __init__(self, max_bridging_facts: int = 3):
        self.max_bridging_facts = max_bridging_facts

    def select(
            self,
            ranked_entries: List[Dict],
            max_context_size: int = 10,
    ) -> List[Dict]:
        """
        Select context entries with balanced AKU/bridging fact proportion.

        Implements Algorithm 1 from the paper.
        """
        context: List[Dict] = []
        bridging_fact_count = 0

        for entry in ranked_entries:
            if len(context) >= max_context_size:
                break

            entry_type = entry.get("metadata", {}).get("entry_type", "aku")

            if entry_type == "bridging_fact":
                if bridging_fact_count < self.max_bridging_facts:
                    context.append(entry)
                    bridging_fact_count += 1
            else:
                context.append(entry)

        return context


# =============================================================================
# Core Classes (original names preserved, functionality extended)
# =============================================================================

class _InMemoryCollection:
    """In-memory fallback for ChromaDB."""

    def __init__(self) -> None:
        self.rows: List[Dict] = []

    def add(
            self,
            ids: List[str],
            documents: List[str],
            embeddings: List[List[float]],
            metadatas: List[dict],
    ) -> None:
        for item_id, document, embedding, metadata in zip(ids, documents, embeddings, metadatas):
            self.rows.append({
                "id": item_id,
                "document": document,
                "embedding": embedding,
                "metadata": metadata,
            })

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
    """
    Vector index with IndexRAG support.

    Extended to track AKUs, bridging facts, and entity registry.
    Original add_documents() and query() methods unchanged.
    """

    def __init__(
            self,
            embedding_provider: 'EmbeddingProvider',
            persist_directory: str = "./app/storage/chroma",
            collection_name: str = "document_rules",
            reset_collection: bool = False,
    ):
        self.embedding_provider = embedding_provider
        self.collection_name = collection_name

        # IndexRAG: Track AKUs, bridging facts, and entities
        self._akus: Dict[str, AtomicKnowledgeUnit] = {}
        self._bridging_facts: Dict[str, BridgingFact] = {}
        self._entity_registry: Dict[str, EntityInfo] = {}

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
        """Add documents to the vector index (original method, unchanged)."""
        embeddings = [self.embedding_provider.embed(text) for text in texts]
        ids: List[str] = []
        for idx, text in enumerate(texts):
            metadata = metadatas[idx] if idx < len(metadatas) else {}
            entity_id = metadata.get("entity_id")
            if entity_id:
                ids.append(f"{self.collection_name}:{entity_id}")
            else:
                ids.append(hashlib.md5(f"{self.collection_name}:{idx}:{text}".encode("utf-8")).hexdigest())

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

    def add_aku(self, aku: AtomicKnowledgeUnit) -> None:
        """Add an Atomic Knowledge Unit to the index."""
        self._akus[aku.id] = aku
        embedding = self.embedding_provider.embed(aku.content)
        if embedding:
            self.collection.add(
                ids=[aku.id],
                documents=[aku.content],
                embeddings=[embedding],
                metadatas=[{
                    "entity_id": aku.id,
                    "entry_type": "aku",
                    "document_id": aku.document_id,
                    "entities": ",".join(aku.entities),
                    **aku.metadata,
                }],
            )

    def add_bridging_fact(self, fact: BridgingFact) -> None:
        """Add a bridging fact to the index."""
        self._bridging_facts[fact.id] = fact
        embedding = self.embedding_provider.embed(fact.content)
        if embedding:
            self.collection.add(
                ids=[fact.id],
                documents=[fact.content],
                embeddings=[embedding],
                metadatas=[{
                    "entity_id": fact.id,
                    "entry_type": "bridging_fact",
                    "entity": fact.entity,
                    "source_document_ids": ",".join(fact.source_document_ids),
                    **fact.metadata,
                }],
            )

    def register_entity(
            self,
            entity_name: str,
            document_id: str,
            aku_id: Optional[str] = None,
    ) -> None:
        """Register an entity occurrence for bridge entity identification."""
        if entity_name not in self._entity_registry:
            self._entity_registry[entity_name] = EntityInfo(name=entity_name)

        entity_info = self._entity_registry[entity_name]
        entity_info.document_ids.add(document_id)
        if aku_id:
            entity_info.aku_ids.add(aku_id)

    def get_bridge_entities(
            self,
            config: Optional[IndexRAGConfig] = None,
    ) -> List[str]:
        """Get list of bridge entities (appearing in multiple documents)."""
        config = config or DEFAULT_INDEXRAG_CONFIG
        return [
            name for name, info in self._entity_registry.items()
            if config.entity_min_document_frequency <= info.document_frequency <= config.entity_max_document_frequency
        ]

    def get_akus_by_document(self) -> Dict[str, List[AtomicKnowledgeUnit]]:
        """Get AKUs grouped by document ID."""
        result: Dict[str, List[AtomicKnowledgeUnit]] = {}
        for aku in self._akus.values():
            if aku.document_id not in result:
                result[aku.document_id] = []
            result[aku.document_id].append(aku)
        return result

    def query(self, query_text: str, n_results: int = 5) -> Optional[Dict]:
        """Query the vector index (original method, unchanged)."""
        query_embedding = self.embedding_provider.embed(query_text)
        if not query_embedding:
            return None
        return self.collection.query(query_embeddings=[query_embedding], n_results=n_results)

    @property
    def aku_count(self) -> int:
        return len(self._akus)

    @property
    def bridging_fact_count(self) -> int:
        return len(self._bridging_facts)

    @property
    def entity_count(self) -> int:
        return len(self._entity_registry)


class GraphRAGRetriever:
    """
    GraphRAG retriever with IndexRAG enhancements.

    Original functionality preserved, extended with:
    - IndexRAG retrieval with bridging facts
    - Cross-document reasoning support
    - Single-pass retrieval with pre-computed bridging

    Original methods (unchanged):
    - retrieve()
    - answer()

    New methods:
    - retrieve_with_bridging()
    - answer_with_bridging()
    - index_document()
    - generate_bridging_facts()
    """

    def __init__(
            self,
            graph: 'KnowledgeGraph',
            vector_index: VectorIndex,
            llm_provider: 'LLMProvider',
            graph_config: Optional[GraphRAGConfig] = None,
            indexrag_config: Optional[IndexRAGConfig] = None,
            object_query_hints: Optional[Dict[str, List[str]]] = None,
            constraint_query_hints: Optional[Dict[str, List[str]]] = None,
    ):
        self.graph = graph
        self.vector_index = vector_index
        self.llm_provider = llm_provider

        # Configurations (removing hardcoded values)
        self._graph_config = graph_config or DEFAULT_GRAPH_CONFIG
        self._indexrag_config = indexrag_config or DEFAULT_INDEXRAG_CONFIG

        # Query hints (can be customized)
        self._object_query_hints = object_query_hints or DEFAULT_OBJECT_QUERY_HINTS
        self._constraint_query_hints = constraint_query_hints or DEFAULT_CONSTRAINT_QUERY_HINTS

        # IndexRAG components
        self._aku_extractor = AKUExtractor(llm_provider, self._indexrag_config)
        self._bridging_generator = BridgingFactGenerator(llm_provider, self._indexrag_config)
        self._context_selector = BalancedContextSelector(
            max_bridging_facts=self._indexrag_config.default_max_bridging_facts
        )

        # Track IndexRAG state
        self._indexrag_ready = False

    def retrieve(self, query: str, top_k: int = 5) -> Dict:
        """Original retrieve method (unchanged)."""
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

        matched_object_types = self._match_signal_nodes(
            query, "object_type", self._object_query_hints, rule_scores, support_scores,
            bonus=self._graph_config.object_type_bonus
        )
        matched_constraint_types = self._match_signal_nodes(
            query, "constraint", self._constraint_query_hints, rule_scores, support_scores,
            bonus=self._graph_config.constraint_type_bonus
        )
        matched_keywords = self._match_keyword_nodes(
            query, rule_scores, support_scores,
            bonus=self._graph_config.keyword_bonus
        )

        ranked_rule_ids = [
            rule_id
            for rule_id, _ in sorted(
                rule_scores.items(),
                key=lambda item: self._rule_rank_key(
                    item[0],
                    item[1],
                    matched_object_types,
                    matched_constraint_types,
                    matched_keywords,
                ),
                reverse=True,
            )[:top_k]
        ]
        candidate_rules = [self._build_context_item(rule_id, score=rule_scores[rule_id]) for rule_id in ranked_rule_ids]

        support_ids: List[str] = []
        for rule_id in ranked_rule_ids:
            support_ids.extend(
                self.graph.get_related_nodes(
                    rule_id,
                    edge_types=self._graph_config.support_context_edge_types,
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
        supporting_entities = [self._build_context_item(node_id, score=support_scores.get(node_id, 0.0)) for node_id in
                               ordered_support_ids]

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

    def retrieve_with_bridging(
            self,
            query: str,
            top_k: int = 5,
            max_bridging_facts: Optional[int] = None,
    ) -> Dict:
        """
        IndexRAG-enhanced retrieval with bridging facts.

        Paper: "At inference time, a single retrieval pass and a single LLM call
        suffice, without graph traversal, query decomposition, or iterative
        retrieval-generation loops."
        """
        max_bridging_facts = max_bridging_facts or self._indexrag_config.default_max_bridging_facts

        # Get vector results (includes AKUs and bridging facts)
        vector_results = self.vector_index.query(query, n_results=top_k * 2)

        if not vector_results:
            return {
                "query": query,
                "context": [],
                "candidate_rules": [],
                "supporting_entities": [],
                "bridging_facts": [],
                "vector_results": [],
                "graph_entities": [],
                "matched_signals": {"object_types": [], "constraint_types": [], "keywords": []},
            }

        # Extract and categorize hits
        all_entries = self._extract_all_entries(vector_results)

        # Apply balanced context selection
        self._context_selector.max_bridging_facts = max_bridging_facts
        selected_entries = self._context_selector.select(
            all_entries,
            max_context_size=top_k * 2
        )

        # Separate AKUs and bridging facts
        aku_entries = [e for e in selected_entries if e.get("metadata", {}).get("entry_type") != "bridging_fact"]
        bridging_entries = [e for e in selected_entries if e.get("metadata", {}).get("entry_type") == "bridging_fact"]

        # Build context with graph-based reasoning for AKUs
        vector_hits = [(e["id"], e.get("metadata", {})) for e in aku_entries]
        rule_scores: Dict[str, float] = {}
        support_scores: Dict[str, float] = {}

        for rank, (entity_id, metadata) in enumerate(vector_hits, start=1):
            base_score = max(0.0, (top_k + 1 - rank) / max(top_k, 1))
            self._apply_seed(entity_id, base_score, rule_scores, support_scores)

        matched_object_types = self._match_signal_nodes(
            query, "object_type", self._object_query_hints, rule_scores, support_scores,
            bonus=self._graph_config.object_type_bonus
        )
        matched_constraint_types = self._match_signal_nodes(
            query, "constraint", self._constraint_query_hints, rule_scores, support_scores,
            bonus=self._graph_config.constraint_type_bonus
        )
        matched_keywords = self._match_keyword_nodes(
            query, rule_scores, support_scores,
            bonus=self._graph_config.keyword_bonus
        )

        # Rank rules
        ranked_rule_ids = [
            rule_id
            for rule_id, _ in sorted(
                rule_scores.items(),
                key=lambda item: self._rule_rank_key(
                    item[0],
                    item[1],
                    matched_object_types,
                    matched_constraint_types,
                    matched_keywords,
                ),
                reverse=True,
            )[:top_k]
        ]

        candidate_rules = [self._build_context_item(rule_id, score=rule_scores.get(rule_id, 0.0)) for rule_id in
                           ranked_rule_ids]

        # Get supporting entities
        support_ids: List[str] = []
        for rule_id in ranked_rule_ids:
            support_ids.extend(
                self.graph.get_related_nodes(
                    rule_id,
                    edge_types=self._graph_config.support_context_edge_types,
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
        supporting_entities = [self._build_context_item(node_id, score=support_scores.get(node_id, 0.0)) for node_id in
                               ordered_support_ids]

        # Combine context: rules + supporting entities + bridging facts
        context = candidate_rules + supporting_entities + bridging_entries
        graph_entities = list(dict.fromkeys([e["id"] for e in aku_entries] + ranked_rule_ids + ordered_support_ids))

        return {
            "query": query,
            "context": context,
            "candidate_rules": candidate_rules,
            "supporting_entities": supporting_entities,
            "bridging_facts": bridging_entries,
            "vector_results": vector_results,
            "graph_entities": graph_entities,
            "matched_signals": {
                "object_types": matched_object_types,
                "constraint_types": matched_constraint_types,
                "keywords": matched_keywords,
            },
        }

    def answer(self, question: str) -> Dict:
        """Original answer method (unchanged)."""
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

    def answer_with_bridging(
            self,
            question: str,
            max_bridging_facts: Optional[int] = None,
    ) -> Dict:
        """
        IndexRAG-enhanced answer with bridging facts.

        Paper: "IndexRAG identifies bridge entities shared across documents and
        generates bridging facts as independently retrievable units."
        """
        max_bridging_facts = max_bridging_facts or self._indexrag_config.default_max_bridging_facts
        retrieval_results = self.retrieve_with_bridging(question, max_bridging_facts=max_bridging_facts)

        context_text = "\n\n".join(
            self._format_context_item(item)
            for item in retrieval_results["context"][:self._indexrag_config.default_context_items]
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

        bridging_sources = [
            {
                "id": item.get("id", ""),
                "content": item.get("content", ""),
                "entity": item.get("metadata", {}).get("entity", ""),
                "source_documents": item.get("metadata", {}).get("source_document_ids", "").split(","),
            }
            for item in retrieval_results.get("bridging_facts", [])[:3]
        ]

        return {
            "answer": answer,
            "sources": sources,
            "bridging_facts": bridging_sources,
            "graph_entities_count": len(retrieval_results["graph_entities"]),
            "matched_signals": retrieval_results["matched_signals"],
        }

    # =========================================================================
    # IndexRAG Indexing Methods
    # =========================================================================

    def index_document(
            self,
            document_id: str,
            text: str,
            metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """
        Index a document using IndexRAG Stage 1 (AKU extraction).

        Paper Stage 1: "Extract AKUs and entities from each document"
        """
        akus, entities = self._aku_extractor.extract(document_id, text, metadata)

        # Add AKUs to vector index and register entities
        for aku in akus:
            self.vector_index.add_aku(aku)
            for entity in aku.entities:
                self.vector_index.register_entity(entity, document_id, aku.id)

        # Register all entities
        for entity in entities:
            self.vector_index.register_entity(entity, document_id)

        return {
            "document_id": document_id,
            "akus_extracted": len(akus),
            "entities_found": len(entities),
        }

    def generate_bridging_facts(self) -> Dict:
        """
        Generate bridging facts for all bridge entities (IndexRAG Stage 2).

        Paper Stage 2: "Identify bridge entities and generate bridging facts"
        """
        bridge_entities = self.vector_index.get_bridge_entities(self._indexrag_config)
        akus_by_document = self.vector_index.get_akus_by_document()

        generated_facts: List[BridgingFact] = []
        for entity in bridge_entities:
            entity_info = self.vector_index._entity_registry.get(entity)
            fact = self._bridging_generator.generate(entity, akus_by_document, entity_info)
            if fact:
                self.vector_index.add_bridging_fact(fact)
                generated_facts.append(fact)

        self._indexrag_ready = True

        return {
            "bridge_entities_identified": len(bridge_entities),
            "bridging_facts_generated": len(generated_facts),
        }

    # =========================================================================
    # Internal Methods
    # =========================================================================

    def _extract_all_entries(self, vector_results: Dict) -> List[Dict]:
        """Extract all entries from vector results."""
        entries: List[Dict] = []

        ids = vector_results.get("ids", [[]])[0]
        documents = vector_results.get("documents", [[]])[0]
        metadatas = vector_results.get("metadatas", [[]])[0]

        for idx, (entry_id, document, metadata) in enumerate(zip(ids, documents, metadatas)):
            entries.append({
                "id": entry_id,
                "content": document,
                "metadata": metadata or {},
                "rank": idx,
            })

        return entries

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
            # Check if it's an AKU or bridging fact
            if entity_id in self.vector_index._akus:
                support_scores[entity_id] = max(support_scores.get(entity_id, 0.0), base_score)
            elif entity_id in self.vector_index._bridging_facts:
                support_scores[entity_id] = max(support_scores.get(entity_id, 0.0), base_score)
            return

        support_scores[entity_id] = max(support_scores.get(entity_id, 0.0), base_score)
        if node.get("type") == "rule":
            rule_scores[entity_id] = rule_scores.get(entity_id, 0.0) + base_score * 2.0

        related_edges = self.graph.get_related_edges(
            entity_id,
            edge_types=self._graph_config.edge_types
        )
        for edge in related_edges:
            neighbor_id = edge["neighbor_id"]
            edge_type = edge["type"]
            weight = self._graph_config.edge_weights.get(edge_type, 1.0)
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
                for edge in self.graph.get_related_edges(
                        node_id,
                        edge_types=self._graph_config.edge_types,
                        neighbor_types=["rule"]
                ):
                    weight = self._graph_config.edge_weights.get(edge["type"], 1.0)
                    rule_scores[edge["neighbor_id"]] = rule_scores.get(edge["neighbor_id"], 0.0) + bonus * weight
        return matched

    def _rule_rank_key(
            self,
            rule_id: str,
            score: float,
            matched_object_types: List[str],
            matched_constraint_types: List[str],
            matched_keywords: List[str],
    ) -> tuple:
        node = self.graph.get_node(rule_id) or {}
        metadata = node.get("metadata", {}) or {}
        object_match = 1 if metadata.get("object_type") in matched_object_types else 0
        constraint_match = 1 if metadata.get("constraint_type") in matched_constraint_types else 0
        keyword_overlap = 0
        if matched_keywords:
            keyword_overlap = len(set(metadata.get("keywords", [])) & set(matched_keywords))
        return (object_match, constraint_match, keyword_overlap, score)

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
                for edge in self.graph.get_related_edges(
                        node_id,
                        edge_types=self._graph_config.edge_types,
                        neighbor_types=["rule"]
                ):
                    weight = self._graph_config.edge_weights.get(edge["type"], 1.0)
                    rule_scores[edge["neighbor_id"]] = rule_scores.get(edge["neighbor_id"], 0.0) + bonus * weight
        return matched

    def _build_context_item(self, node_id: str, score: float) -> Dict:
        node = self.graph.get_node(node_id)
        if not node:
            # Check if it's an AKU or bridging fact
            if node_id in self.vector_index._akus:
                aku = self.vector_index._akus[node_id]
                return {
                    "id": node_id,
                    "name": aku.question[:50],
                    "type": "aku",
                    "content": aku.content,
                    "metadata": {"document_id": aku.document_id, **aku.metadata},
                    "score": round(score, 4),
                }
            elif node_id in self.vector_index._bridging_facts:
                fact = self.vector_index._bridging_facts[node_id]
                return {
                    "id": node_id,
                    "name": f"Bridge: {fact.entity}",
                    "type": "bridging_fact",
                    "content": fact.content,
                    "metadata": {
                        "entity": fact.entity,
                        "source_document_ids": fact.source_document_ids,
                        **fact.metadata
                    },
                    "score": round(score, 4),
                }
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
        for key in ["number", "section_title", "object_type", "constraint_type", "entity"]:
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
