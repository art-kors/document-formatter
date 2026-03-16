from io import BytesIO
from typing import Iterable, List, Optional

from app.fixing.document_fixer import apply_fixes
from app.schemas.document import DocumentInput
from app.schemas.issue import Issue


def apply_fixes_to_source_docx(file_bytes: bytes, document: DocumentInput, issues: List[Issue]) -> bytes:
    from docx import Document
    from docx.document import Document as DocumentType
    from docx.table import _Cell, Table
    from docx.text.paragraph import Paragraph

    source = Document(BytesIO(file_bytes))
    fixed = apply_fixes(document, issues)

    old_sections = {section.id: section for section in document.sections}
    new_sections = {section.id: section for section in fixed.sections}
    old_paragraphs = {paragraph.id: paragraph for paragraph in document.paragraphs}

    # 1. Apply explicit before/after fixes to source paragraphs.
    for issue in issues:
        suggestion = issue.suggestion
        if not hasattr(suggestion, 'before') or not hasattr(suggestion, 'after'):
            continue
        target_text = None
        if issue.location.paragraph_id and issue.location.paragraph_id in old_paragraphs:
            target_text = old_paragraphs[issue.location.paragraph_id].text
        elif suggestion.before:
            target_text = suggestion.before
        if target_text:
            paragraph = _find_paragraph_by_text(source, target_text)
            if paragraph is not None and not _paragraph_contains_drawing(paragraph):
                _replace_paragraph_text(paragraph, _replace_first(paragraph.text, suggestion.before, suggestion.after))

    # 2. Update section headings according to fixed parsed structure.
    existing_section_ids = [section.id for section in document.sections]
    for section_id in existing_section_ids:
        old_section = old_sections[section_id]
        new_section = new_sections.get(section_id)
        if new_section is None:
            continue
        old_heading = _format_heading(old_section)
        new_heading = _format_heading(new_section)
        if old_heading != new_heading:
            paragraph = _find_paragraph_by_text(source, old_heading)
            if paragraph is not None and not _paragraph_contains_drawing(paragraph):
                _replace_paragraph_text(paragraph, new_heading)

    # 3. Update captions that already exist in the document.
    for old_caption, new_caption in _caption_changes(document, fixed):
        if not old_caption:
            continue
        paragraph = _find_paragraph_by_text(source, old_caption)
        if paragraph is not None and not _paragraph_contains_drawing(paragraph):
            _replace_paragraph_text(paragraph, new_caption)

    # 4. Append missing captions that were synthesized.
    for caption in _missing_captions(document, fixed):
        if not _paragraph_exists(source, caption):
            source.add_paragraph(caption)

    # 5. Append new sections that appeared only after fixes.
    old_ids = set(old_sections)
    for section in fixed.sections:
        if section.id in old_ids:
            continue
        source.add_paragraph(_format_heading(section))
        if section.text:
            for block in [part.strip() for part in section.text.split('\n\n') if part.strip()]:
                source.add_paragraph(block)

    output = BytesIO()
    source.save(output)
    return output.getvalue()


def _caption_changes(original: DocumentInput, fixed: DocumentInput) -> List[tuple[str, str]]:
    changes: List[tuple[str, str]] = []
    for old_item, new_item in zip(original.figures, fixed.figures):
        if old_item.caption and new_item.caption and old_item.caption != new_item.caption:
            changes.append((old_item.caption, new_item.caption))
    for old_item, new_item in zip(original.tables, fixed.tables):
        if old_item.caption and new_item.caption and old_item.caption != new_item.caption:
            changes.append((old_item.caption, new_item.caption))
    return changes


def _missing_captions(original: DocumentInput, fixed: DocumentInput) -> List[str]:
    captions: List[str] = []
    for old_item, new_item in zip(original.figures, fixed.figures):
        if not old_item.caption and new_item.caption:
            captions.append(new_item.caption)
    for old_item, new_item in zip(original.tables, fixed.tables):
        if not old_item.caption and new_item.caption:
            captions.append(new_item.caption)
    return captions


def _replace_first(source: str, before: str, after: str) -> str:
    if before and before in source:
        return source.replace(before, after, 1)
    return after or source


def _format_heading(section) -> str:
    if section.number:
        return f'{section.number} {section.title}'.strip()
    return section.title.strip()


def _paragraph_exists(document, text: str) -> bool:
    return _find_paragraph_by_text(document, text) is not None


def _find_paragraph_by_text(document, text: str):
    target = ' '.join((text or '').split())
    if not target:
        return None
    for paragraph in _iter_paragraphs(document):
        current = ' '.join(paragraph.text.split())
        if current == target:
            return paragraph
    return None


def _iter_paragraphs(parent) -> Iterable:
    from docx.document import Document as DocumentType
    from docx.table import _Cell, Table

    if isinstance(parent, DocumentType):
        for paragraph in parent.paragraphs:
            yield paragraph
        for table in parent.tables:
            yield from _iter_table_paragraphs(table)
    elif isinstance(parent, _Cell):
        for paragraph in parent.paragraphs:
            yield paragraph
        for table in parent.tables:
            yield from _iter_table_paragraphs(table)


def _iter_table_paragraphs(table) -> Iterable:
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                yield paragraph
            for nested_table in cell.tables:
                yield from _iter_table_paragraphs(nested_table)


def _paragraph_contains_drawing(paragraph) -> bool:
    return bool(paragraph._p.xpath('.//*[local-name()="drawing" or local-name()="object" or local-name()="pict"]'))


def _replace_paragraph_text(paragraph, new_text: str) -> None:
    p = paragraph._p
    for child in list(p):
        if child.tag.endswith('}pPr'):
            continue
        p.remove(child)
    paragraph.add_run(new_text)
