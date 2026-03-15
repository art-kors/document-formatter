from typing import List

from pydantic import BaseModel, Field

from app.schemas.issue import Issue


class AgentResult(BaseModel):
    agent: str
    issues: List[Issue] = Field(default_factory=list)
