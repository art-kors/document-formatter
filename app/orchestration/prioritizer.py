from typing import Iterable, List

from app.schemas.issue import Issue


SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
TYPE_ORDER = {"structure": 0, "formatting": 1, "style": 2, "logic": 3}


def sort_issues(issues: Iterable[Issue]) -> List[Issue]:
    return sorted(
        issues,
        key=lambda issue: (
            SEVERITY_ORDER.get(issue.severity, 99),
            TYPE_ORDER.get(issue.type, 99),
            issue.id,
        ),
    )
