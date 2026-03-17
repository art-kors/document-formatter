from io import BytesIO
import re
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
            paragraph = _find_section_heading_paragraph(source, document, section_id)
            if paragraph is None:
                paragraph = _find_paragraph_by_text(source, old_heading)
            if paragraph is not None and not _paragraph_contains_drawing(paragraph):
                _replace_paragraph_text(paragraph, new_heading)

    # 2b. Apply paragraph-level layout fixes before text replacements.
    _apply_alignment_fixes(source, document, issues)

    # 3. Update captions that already exist in the document.
    for old_item, new_item in zip(document.figures, fixed.figures):
        _apply_caption_change(source, old_item.caption, new_item.caption, old_item.position.paragraph_index)
    for old_item, new_item in zip(document.tables, fixed.tables):
        _apply_caption_change(source, old_item.caption, new_item.caption, old_item.position.paragraph_index)

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


def _find_section_heading_paragraph(source_doc, parsed_document: DocumentInput, section_id: str):
    section_headings = parsed_document.meta.extras.get('section_headings', {}) if parsed_document.meta and parsed_document.meta.extras else {}
    payload = section_headings.get(section_id) or {}
    paragraph_index = payload.get('paragraph_index')
    paragraph = _find_docx_paragraph_by_index(source_doc, paragraph_index)
    if paragraph is not None:
        return paragraph
    heading_text = payload.get('text')
    if heading_text:
        return _find_paragraph_by_text(source_doc, heading_text)
    return None


def _apply_caption_change(source_doc, old_caption: str, new_caption: str, paragraph_index: Optional[int]) -> None:
    if not old_caption or not new_caption or old_caption == new_caption:
        return

    paragraph = None
    if paragraph_index is not None:
        paragraph = _find_docx_paragraph_by_index(source_doc, paragraph_index)
    if paragraph is None:
        paragraph = _find_paragraph_by_text(source_doc, old_caption)
    if paragraph is None or _paragraph_contains_drawing(paragraph):
        return
    _replace_paragraph_text(paragraph, new_caption)


def _find_docx_paragraph_by_index(document, paragraph_index: Optional[int]):
    if paragraph_index is None or paragraph_index <= 0:
        return None
    paragraphs = getattr(document, 'paragraphs', None) or []
    if paragraph_index > len(paragraphs):
        return None
    return paragraphs[paragraph_index - 1]


def _missing_captions(original: DocumentInput, fixed: DocumentInput) -> List[str]:
    captions: List[str] = []
    for old_item, new_item in zip(original.figures, fixed.figures):
        if not old_item.caption and new_item.caption:
            captions.append(new_item.caption)
    for old_item, new_item in zip(original.tables, fixed.tables):
        if not old_item.caption and new_item.caption:
            captions.append(new_item.caption)
    return captions


def _apply_alignment_fixes(source_doc, parsed_document: DocumentInput, issues: List[Issue]) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    for issue in issues:
        target_alignment = None
        if issue.subtype == 'figure_caption_not_centered':
            target_alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif issue.subtype == 'title_page_right_alignment':
            target_alignment = WD_ALIGN_PARAGRAPH.RIGHT
        elif issue.subtype == 'title_page_center_alignment':
            target_alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif issue.subtype == 'body_text_not_justified':
            target_alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        if target_alignment is None:
            continue

        paragraph = _find_docx_paragraph_by_index(source_doc, getattr(issue.location, 'paragraph_index', None))
        target_text = _extract_quoted_fragment(issue.evidence)
        if paragraph is None and target_text:
            paragraph = _find_paragraph_by_text(source_doc, target_text)
        if paragraph is None and issue.subtype == 'figure_caption_not_centered':
            paragraph = _find_paragraph_by_text(source_doc, _find_figure_caption_for_issue(parsed_document, issue))
        if paragraph is None or _paragraph_contains_drawing(paragraph):
            continue
        paragraph.alignment = target_alignment


def _extract_quoted_fragment(text: str) -> Optional[str]:
    match = re.search(r"'([^']+)'", text or '')
    if match:
        return ' '.join(match.group(1).split())
    return None


def _find_figure_caption_for_issue(document: DocumentInput, issue: Issue) -> Optional[str]:
    target_page = issue.location.page
    for figure in document.figures:
        if target_page is not None and figure.position.page == target_page and figure.caption:
            return figure.caption
    if document.figures:
        return document.figures[0].caption or None
    return None


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
