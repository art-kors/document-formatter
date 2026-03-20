from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentMeta(BaseModel):
    filename: str = ""
    title: str = ""
    language: str = "ru"
    extras: Dict[str, Any] = Field(default_factory=dict)


class Position(BaseModel):
    page: Optional[int] = None
    paragraph_index: Optional[int] = None


class Section(BaseModel):
    id: str
    number: str = ""
    title: str
    level: int = 1
    text: str = ""


class Paragraph(BaseModel):
    id: str
    section_id: Optional[str] = None
    text: str
    position: Position = Field(default_factory=Position)


class TableItem(BaseModel):
    id: str
    caption: str = ""
    position: Position = Field(default_factory=Position)


class FigureItem(BaseModel):
    id: str
    caption: str = ""
    position: Position = Field(default_factory=Position)


class DocumentInput(BaseModel):
    document_id: str
    standard_id: str
    meta: DocumentMeta = Field(default_factory=DocumentMeta)
    sections: List[Section] = Field(default_factory=list)
    paragraphs: List[Paragraph] = Field(default_factory=list)
    tables: List[TableItem] = Field(default_factory=list)
    figures: List[FigureItem] = Field(default_factory=list)
