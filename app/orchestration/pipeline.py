from time import perf_counter
from typing import Dict, List, Optional, Tuple

from app.agents.logic_agent.service import LogicAgentService
from app.agents.rag_agent.service import GraphRAGService
from app.agents.structure_agent.service import StructureAgentService
from app.agents.style_agent.service import StyleAgentService
from app.llm.base import EmbeddingProvider, LLMProvider
from app.orchestration.aggregator import build_result, collect_issues
from app.orchestration.prioritizer import sort_issues
from app.schemas.agent_result import AgentResult
from app.schemas.document import DocumentInput
from app.schemas.orchestrator_result import OrchestratorResult
from app.standards.registry import StandardRegistry


class DocumentPipeline:
    def __init__(
        self,
        llm_provider: LLMProvider,
        registry: StandardRegistry,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ):
        self.registry = registry
        self.embedding_provider = embedding_provider or (
            llm_provider if isinstance(llm_provider, EmbeddingProvider) else None
        )
        if self.embedding_provider is None:
            raise RuntimeError("Configured providers do not support embeddings")
        self.rag_service = GraphRAGService(
            llm_provider=llm_provider,
            embedding_provider=self.embedding_provider,
            registry=registry,
        )
        self.structure_agent = StructureAgentService()
        self.style_agent = StyleAgentService(llm_provider=llm_provider)
        self.logic_agent = LogicAgentService()

    def process_instruction(self, standard_text: str, standard_name: str) -> Dict:
        return self.rag_service.process_instruction(
            standard_text=standard_text,
            standard_name=standard_name,
        )

    def query(self, question: str) -> Dict:
        if not self.rag_service.is_ready:
            raise RuntimeError("Knowledge base is not initialized yet")
        return self.rag_service.query(question)

    def get_structure(self) -> List[Dict]:
        return self.rag_service.get_structure()

    def get_graph_path(self) -> Optional[str]:
        return self.rag_service.get_graph_path()

    def analyze_document(self, document: DocumentInput) -> OrchestratorResult:
        self._validate_standard(document.standard_id)

        started_at = perf_counter()
        agent_results: List[AgentResult] = []
        agents_run: List[str] = []
        agents_failed: Dict[str, str] = {}

        for agent_name, agent in self._get_agents():
            try:
                result = agent.analyze(document, document.standard_id)
                agent_results.append(result)
                agents_run.append(agent_name)
            except Exception as exc:
                agents_failed[agent_name] = str(exc)

        issues = sort_issues(collect_issues(agent_results))
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        return build_result(
            document_id=document.document_id,
            standard_id=document.standard_id,
            issues=issues,
            agents_run=agents_run,
            agents_failed=agents_failed,
            processing_time_ms=elapsed_ms,
        )

    def _get_agents(self) -> List[Tuple[str, object]]:
        return [
            (self.structure_agent.agent_name, self.structure_agent),
            ('rag_agent', self.rag_service),
            (self.style_agent.agent_name, self.style_agent),
            (self.logic_agent.agent_name, self.logic_agent),
        ]

    def _validate_standard(self, standard_id: str) -> None:
        if not self.registry.get(standard_id):
            raise FileNotFoundError(f"Unknown standard_id: {standard_id}")
