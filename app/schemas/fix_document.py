from typing import List

from pydantic import BaseModel, Field

from app.schemas.document import DocumentInput
from app.schemas.issue import Issue


class FixDocumentRequest(BaseModel):
    document: DocumentInput
    issues: List[Issue] = Field(default_factory=list)
    output_filename: str = "corrected_document.docx"
