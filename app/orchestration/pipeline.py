from typing import Dict, List, Optional

from app.agents.logic_agent.service import LogicAgentService
from app.agents.rag_agent.service import GraphRAGService
from app.agents.structure_agent.service import StructureAgentService
from app.agents.style_agent.service import StyleAgentService
from app.llm.base import LLMProvider
from app.orchestration.aggregator import build_result, collect_issues
from app.orchestration.prioritizer import sort_issues
from app.schemas.document import DocumentInput
from app.schemas.orchestrator_result import OrchestratorResult
from app.standards.registry import StandardRegistry


class DocumentPipeline:
    def __init__(self, llm_provider: LLMProvider, registry: StandardRegistry):
        self.registry = registry
        self.rag_service = GraphRAGService(llm_provider=llm_provider, registry=registry)
        self.structure_agent = StructureAgentService()
        self.style_agent = StyleAgentService()
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
        results = [
            self.structure_agent.analyze(document, document.standard_id),
            self.rag_service.analyze(document, document.standard_id),
            self.style_agent.analyze(document, document.standard_id),
            self.logic_agent.analyze(document, document.standard_id),
        ]
        issues = sort_issues(collect_issues(results))
        return build_result(document.document_id, issues)
