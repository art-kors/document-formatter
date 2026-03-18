from typing import Optional

from app.agents.style_agent.checks import build_style_summary, run_style_checks
from app.llm.base import LLMProvider
from app.schemas.agent_result import AgentResult
from app.schemas.document import DocumentInput


class StyleAgentService:
    agent_name = "style_agent"

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider

    def analyze(self, document: DocumentInput, standard_id: str) -> AgentResult:
        issues = run_style_checks(document, llm_provider=self.llm_provider)
        return AgentResult(
            agent=self.agent_name,
            issues=issues,
            details=build_style_summary(document, issues),
        )
