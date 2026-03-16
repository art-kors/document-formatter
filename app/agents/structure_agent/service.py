from app.agents.structure_agent.checks import build_structure_summary, run_structure_checks
from app.schemas.agent_result import AgentResult
from app.schemas.document import DocumentInput


class StructureAgentService:
    agent_name = "structure_agent"

    def analyze(self, document: DocumentInput, standard_id: str) -> AgentResult:
        issues = run_structure_checks(document, standard_id)
        return AgentResult(
            agent=self.agent_name,
            issues=issues,
            details=build_structure_summary(document, issues),
        )
