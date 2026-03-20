from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class StandardDescriptor(BaseModel):
    standard_id: str
    title: str
    source_path: str = ""


class StandardSection(BaseModel):
    id: str
    number: str
    title: str
    level: int = 1
    text: str = ""
    parent_id: Optional[str] = None


class StandardRule(BaseModel):
    id: str
    number: str
    title: str
    section_id: str
    section_title: str = ""
    content: str
    object_type: str = "generic"
    constraint_type: str = "generic"
    keywords: List[str] = Field(default_factory=list)


class StandardNode(BaseModel):
    id: str
    name: str
    type: str
    content: str
    metadata: Dict = Field(default_factory=dict)


class StandardRelation(BaseModel):
    source: str
    target: str
    type: str
    properties: Dict = Field(default_factory=dict)


class ParsedStandard(BaseModel):
    front_matter: List[str] = Field(default_factory=list)
    sections: List[StandardSection] = Field(default_factory=list)
    rules: List[StandardRule] = Field(default_factory=list)
    annexes: List[str] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list)
