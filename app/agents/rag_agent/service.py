from typing import Dict, List, Optional

from app.agents.rag_agent.checker import analyze_document_against_standard
from app.agents.rag_agent.retriever import GraphRAGRetriever, VectorIndex
from app.llm.base import EmbeddingProvider, LLMProvider
from app.schemas.agent_result import AgentResult
from app.schemas.document import DocumentInput
from app.standards.ingest import StandardArtifacts, StandardIngestor
from app.standards.registry import StandardRegistry


class GraphRAGService:
    def __init__(
        self,
        llm_provider: LLMProvider,
        embedding_provider: EmbeddingProvider,
        registry: StandardRegistry,
    ):
        self.llm_provider = llm_provider
        self.embedding_provider = embedding_provider
        self.registry = registry
        self.ingestor = StandardIngestor()
        self.artifacts: Optional[StandardArtifacts] = None
        self.retriever: Optional[GraphRAGRetriever] = None

    @property
    def is_ready(self) -> bool:
        return self.retriever is not None and self.artifacts is not None

    def process_instruction(self, standard_text: str, standard_name: str) -> Dict:
        standard_id = self.registry.register_uploaded_standard(standard_name)
        self.artifacts = self.ingestor.ingest_text(
            standard_id=standard_id,
            standard_text=standard_text,
            embedding_provider=self.embedding_provider,
        )
        vector_index = VectorIndex(
            self.embedding_provider,
            collection_name=f"standard_{standard_id}",
            reset_collection=True,
        )
        vector_index.add_documents(
            texts=[node.content for node in self.artifacts.nodes],
            metadatas=[
                {
                    "entity_id": node.id,
                    "entity_type": node.type,
                    "entity_name": node.name,
                }
                for node in self.artifacts.nodes
            ],
        )
        self.retriever = GraphRAGRetriever(
            graph=self.artifacts.graph,
            vector_index=vector_index,
            llm_provider=self.llm_provider,
        )
        return {
            "status": "indexed",
            "standard_id": standard_id,
            "entities_count": len(self.artifacts.nodes),
            "relations_count": len(self.artifacts.relations),
        }

    def query(self, question: str) -> Dict:
        if not self.retriever:
            raise RuntimeError("Knowledge base is not initialized yet")
        return self.retriever.answer(question)

    def get_structure(self) -> List[Dict]:
        if not self.artifacts:
            return []
        sections = []
        for node in self.artifacts.nodes:
            if node.type == "section":
                sections.append(
                    {
                        "id": node.id,
                        "name": node.name,
                        "order": node.metadata.get("order", 0),
                    }
                )
        return sorted(sections, key=lambda item: item["order"])

    def get_graph_path(self) -> Optional[str]:
        if not self.artifacts:
            return None
        return self.artifacts.graph_path

    def analyze(self, document: DocumentInput, standard_id: str) -> AgentResult:
        return analyze_document_against_standard(document, standard_id)
