from app.agents.logic_agent.checks import run_logic_checks
from app.schemas.agent_result import AgentResult
from app.schemas.document import DocumentInput


class LogicAgentService:
    agent_name = "logic_agent"

    def analyze(self, document: DocumentInput, standard_id: str) -> AgentResult:
        return AgentResult(agent=self.agent_name, issues=run_logic_checks(document))
