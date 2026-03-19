from typing import Optional

from app.agents.logic_agent.checks import build_logic_summary, run_logic_checks
from app.llm.base import LLMProvider
from app.schemas.agent_result import AgentResult
from app.schemas.document import DocumentInput


class LogicAgentService:
    agent_name = "logic_agent"

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider

    def analyze(self, document: DocumentInput, standard_id: str) -> AgentResult:
        issues = run_logic_checks(document, llm_provider=self.llm_provider)
        return AgentResult(agent=self.agent_name, issues=issues, details=build_logic_summary(document, issues))
