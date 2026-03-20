from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.schemas.issue import Issue


class AgentResult(BaseModel):
    agent: str
    issues: List[Issue] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)
