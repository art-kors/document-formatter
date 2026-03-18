from typing import Optional, Union

from pydantic import BaseModel, Field


class IssueLocation(BaseModel):
    section_id: Optional[str] = None
    paragraph_id: Optional[str] = None
    paragraph_index: Optional[int] = None
    page: Optional[int] = None


class StandardReference(BaseModel):
    source: str = ""
    rule_id: str = ""
    quote: str = ""


class SuggestedFix(BaseModel):
    before: str = ""
    after: str = ""


class Issue(BaseModel):
    id: str
    type: str
    subtype: str = ""
    severity: str
    message: str
    location: IssueLocation = Field(default_factory=IssueLocation)
    evidence: str = ""
    standard_reference: StandardReference = Field(default_factory=StandardReference)
    suggestion: Optional[Union[str, SuggestedFix]] = None
    agent: str
