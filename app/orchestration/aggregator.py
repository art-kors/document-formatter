from collections import Counter
from typing import Dict, Iterable, List, Tuple

from app.schemas.agent_result import AgentResult
from app.schemas.issue import Issue
from app.schemas.orchestrator_result import OrchestratorResult, Summary


SEVERITY_PRIORITY = {
    "critical": 3,
    "warning": 2,
    "info": 1,
}


def collect_issues(results: Iterable[AgentResult]) -> List[Issue]:
    merged: Dict[Tuple, Issue] = {}
    for result in results:
        for issue in result.issues:
            signature = _issue_signature(issue)
            current = merged.get(signature)
            if current is None:
                merged[signature] = issue
                continue
            merged[signature] = _pick_better_issue(current, issue)
    return list(merged.values())


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
    rule_id = issue.standard_reference.rule_id or ""
    return (
        issue.type,
        issue.subtype or issue.message,
        location.section_id,
        location.paragraph_id,
        location.page,
        rule_id,
    )


def _pick_better_issue(left: Issue, right: Issue) -> Issue:
    if _issue_rank(right) > _issue_rank(left):
        return right
    return left


def _issue_rank(issue: Issue) -> Tuple[int, int, int, int]:
    return (
        SEVERITY_PRIORITY.get(issue.severity, 0),
        1 if issue.suggestion else 0,
        len(issue.evidence or ""),
        len(issue.standard_reference.quote or ""),
    )
