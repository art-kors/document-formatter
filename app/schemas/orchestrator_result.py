from typing import Dict, List

from pydantic import BaseModel, Field

from app.schemas.issue import Issue


class Summary(BaseModel):
    total_issues: int = 0
    critical: int = 0
    warning: int = 0
    info: int = 0
    by_type: Dict[str, int] = Field(default_factory=dict)
    fixable: int = 0


class OrchestratorResult(BaseModel):
    document_id: str
    standard_id: str = ""
    status: str
    summary: Summary = Field(default_factory=Summary)
    issues: List[Issue] = Field(default_factory=list)
    agents_run: List[str] = Field(default_factory=list)
    agents_failed: Dict[str, str] = Field(default_factory=dict)
    processing_time_ms: int = 0
