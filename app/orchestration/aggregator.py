from collections import Counter
from typing import Iterable, List

from app.schemas.agent_result import AgentResult
from app.schemas.issue import Issue
from app.schemas.orchestrator_result import OrchestratorResult, Summary


def collect_issues(results: Iterable[AgentResult]) -> List[Issue]:
    issues: List[Issue] = []
    for result in results:
        issues.extend(result.issues)
    return issues


def build_summary(issues: List[Issue]) -> Summary:
    severity_counts = Counter(issue.severity for issue in issues)
    type_counts = Counter(issue.type for issue in issues)
    fixable = sum(1 for issue in issues if issue.suggestion)
    return Summary(
        total_issues=len(issues),
        critical=severity_counts.get("critical", 0),
        warning=severity_counts.get("warning", 0),
        info=severity_counts.get("info", 0),
        by_type=dict(type_counts),
        fixable=fixable,
    )


def build_result(document_id: str, issues: List[Issue]) -> OrchestratorResult:
    return OrchestratorResult(
        document_id=document_id,
        status="done",
        summary=build_summary(issues),
        issues=issues,
    )
