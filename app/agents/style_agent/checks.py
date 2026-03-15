from typing import List

from app.schemas.document import DocumentInput
from app.schemas.issue import Issue


def run_style_checks(document: DocumentInput) -> List[Issue]:
    return []
