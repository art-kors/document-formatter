from collections import Counter
from typing import Dict, Iterable, List, Tuple

from app.schemas.agent_result import AgentResult
from app.schemas.issue import Issue
from app.schemas.orchestrator_result import OrchestratorResult, Summary


def collect_issues(results: Iterable[AgentResult]) -> List[Issue]:
    issues: List[Issue] = []
    seen: set[Tuple] = set()
    for result in results:
        for issue in result.issues:
            signature = _issue_signature(issue)
            if signature in seen:
                continue
            seen.add(signature)
            issues.append(issue)
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


def build_result(
    document_id: str,
    issues: List[Issue],
    standard_id: str = "",
    agents_run: List[str] | None = None,
    agents_failed: Dict[str, str] | None = None,
    processing_time_ms: int = 0,
) -> OrchestratorResult:
    agents_failed = agents_failed or {}
    return OrchestratorResult(
        document_id=document_id,
        standard_id=standard_id,
        status="done" if not agents_failed else "partial_success",
        summary=build_summary(issues),
        issues=issues,
        agents_run=agents_run or [],
        agents_failed=agents_failed,
        processing_time_ms=processing_time_ms,
    )


def _issue_signature(issue: Issue) -> Tuple:
    location = issue.location
    return (
        issue.type,
        issue.subtype,
        issue.severity,
        issue.message,
        location.section_id,
        location.paragraph_id,
        location.page,
        issue.agent,
        issue.standard_reference.rule_id,
    )
