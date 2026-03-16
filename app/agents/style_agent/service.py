from app.agents.style_agent.checks import build_style_summary, run_style_checks
from app.schemas.agent_result import AgentResult
from app.schemas.document import DocumentInput


class StyleAgentService:
    agent_name = "style_agent"

    def analyze(self, document: DocumentInput, standard_id: str) -> AgentResult:
        issues = run_style_checks(document)
        return AgentResult(
            agent=self.agent_name,
            issues=issues,
            details=build_style_summary(document, issues),
        )
