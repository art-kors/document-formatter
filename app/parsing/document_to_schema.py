import re
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.schemas.document import DocumentInput, DocumentMeta, FigureItem, Paragraph, Position, Section, TableItem


SECTION_PATTERN = re.compile(r'^(?P<number>\d+(?:\.\d+)*)\s+(?P<title>[^\n]{1,200})$')
APPENDIX_PATTERN = re.compile('^(?:\u041f\u0420\u0418\u041b\u041e\u0416\u0415\u041d\u0418\u0415|\u041f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435)\\s+(?P<number>[A-Z\u0410-\u042f\u0401])(?:\\s*[\u2013-]?\\s*(?P<title>.*))?$')
FIGURE_PATTERN = re.compile('^\u0420\u0438\u0441\u0443\u043d\u043e\u043a\\s+(?P<number>\\d+)\\s*[\u2013-]?\\s*(?P<title>.*)$', re.IGNORECASE)
TABLE_PATTERN = re.compile('^\u0422\u0430\u0431\u043b\u0438\u0446\u0430\\s+(?P<number>\\d+)\\s*[\u2013-]?\\s*(?P<title>.*)$', re.IGNORECASE)
_HEADING_STYLE_HINTS = ('heading', '\u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a')

_CANONICAL_UNNUMBERED_HEADINGS = {
    '????????',
    '??????????',
    '??????????',
    '??????????',
    '???????',
    '?????? ?????????????? ??????????',
    '?????? ??????????',
    '????????????????? ??????',
}


def parse_text_to_document(
    text: str,
    *,
    filename: str,
    standard_id: str,
    document_id: Optional[str] = None,
) -> DocumentInput:
    blocks = _split_blocks(text)
    sections: List[Section] = []
    paragraphs: List[Paragraph] = []
    figures: List[FigureItem] = []
    tables: List[TableItem] = []

    current_section: Optional[Section] = None

    for paragraph_index, block in enumerate(blocks, start=1):
        heading = _parse_heading(block)
        if heading is not None:
            if current_section is not None:
                current_section.text = current_section.text.strip()
            current_section = Section(**heading)
            sections.append(current_section)
            continue

        if current_section is not None:
            current_section.text = (current_section.text + "\n\n" + block).strip() if current_section.text else block

        figure = _parse_figure(block, len(figures) + 1, paragraph_index)
        if figure is not None:
            figures.append(figure)
            continue

        table = _parse_table(block, len(tables) + 1, paragraph_index)
        if table is not None:
            tables.append(table)
            continue

        paragraphs.append(
            Paragraph(
                id=f"p_{len(paragraphs) + 1}",
                section_id=current_section.id if current_section is not None else None,
                text=block,
                position=Position(page=None, paragraph_index=paragraph_index),
            )
        )

    if current_section is not None:
        current_section.text = current_section.text.strip()

    title = next((section.title for section in sections if section.title), Path(filename).stem)
    return DocumentInput(
        document_id=document_id or _build_document_id(filename),
        standard_id=standard_id,
        meta=DocumentMeta(filename=filename, title=title, language='ru', extras={'source_format': 'text'}),
        sections=sections,
        paragraphs=paragraphs,
        tables=tables,
        figures=figures,
    )


def parse_docx_to_document(
    file_bytes: bytes,
    *,
    filename: str,
    standard_id: str,
    document_id: Optional[str] = None,
) -> DocumentInput:
    from docx import Document

    doc = Document(BytesIO(file_bytes))
    sections: List[Section] = []
    paragraphs: List[Paragraph] = []
    figures: List[FigureItem] = []
    tables: List[TableItem] = []
    paragraph_meta: List[Dict[str, Any]] = []
    current_section: Optional[Section] = None

    for index, paragraph in enumerate(doc.paragraphs, start=1):
        text = ' '.join(paragraph.text.split())
        if not text:
            continue

        alignment = _alignment_name(paragraph.alignment)
        style_name = (getattr(paragraph.style, 'name', '') or '').strip()
        paragraph_meta.append(
            {
                'paragraph_index': index,
                'text': text,
                'alignment': alignment,
                'style': style_name,
            }
        )

        heading = _parse_heading(text)
        if heading is None and _looks_like_word_heading(style_name, text):
            heading = _fallback_heading_from_style(text, len(sections) + 1)
        if heading is not None:
            if current_section is not None:
                current_section.text = current_section.text.strip()
            current_section = Section(**heading)
            sections.append(current_section)
            continue

        if current_section is not None:
            current_section.text = (current_section.text + "\n\n" + text).strip() if current_section.text else text

        figure = _parse_figure(text, len(figures) + 1, index)
        if figure is not None:
            figures.append(figure)
            continue

        table = _parse_table(text, len(tables) + 1, index)
        if table is not None:
            tables.append(table)
            continue

        paragraphs.append(
            Paragraph(
                id=f"p_{len(paragraphs) + 1}",
                section_id=current_section.id if current_section is not None else None,
                text=text,
                position=Position(page=None, paragraph_index=index),
            )
        )

    if current_section is not None:
        current_section.text = current_section.text.strip()

    title = next((section.title for section in sections if section.title), Path(filename).stem)
    extras = {
        'source_format': 'docx',
        'docx_paragraphs': paragraph_meta,
        'has_tables': bool(doc.tables),
        'inline_shapes_count': len(getattr(doc, 'inline_shapes', [])),
    }
    return DocumentInput(
        document_id=document_id or _build_document_id(filename),
        standard_id=standard_id,
        meta=DocumentMeta(filename=filename, title=title, language='ru', extras=extras),
        sections=sections,
        paragraphs=paragraphs,
        tables=tables,
        figures=figures,
    )


def _split_blocks(text: str) -> List[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return [block.strip() for block in re.split(r"\n\s*\n", normalized) if block.strip()]


def _parse_heading(block: str) -> Optional[dict]:
    single_line = ' '.join(line.strip() for line in block.splitlines() if line.strip())
    appendix_match = APPENDIX_PATTERN.match(single_line)
    if appendix_match:
        suffix = appendix_match.group('title') or ''
        title = single_line if suffix else f"\u041f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435 {appendix_match.group('number')}"
        return {
            'id': f"sec_appendix_{appendix_match.group('number').lower()}",
            'number': appendix_match.group('number'),
            'title': title,
            'level': 1,
            'text': '',
        }

    match = SECTION_PATTERN.match(single_line)
    if not match:
        return None

    number = match.group('number')
    title = match.group('title').strip()
    level = number.count('.') + 1
    return {
        'id': f"sec_{number.replace('.', '_')}",
        'number': number,
        'title': title,
        'level': level,
        'text': '',
    }


def _parse_figure(block: str, index: int, paragraph_index: int) -> Optional[FigureItem]:
    single_line = ' '.join(line.strip() for line in block.splitlines() if line.strip())
    match = FIGURE_PATTERN.match(single_line)
    if not match:
        return None
    return FigureItem(
        id=f'fig_{index}',
        caption=single_line,
        position=Position(page=None, paragraph_index=paragraph_index),
    )


def _parse_table(block: str, index: int, paragraph_index: int) -> Optional[TableItem]:
    single_line = ' '.join(line.strip() for line in block.splitlines() if line.strip())
    match = TABLE_PATTERN.match(single_line)
    if not match:
        return None
    return TableItem(
        id=f'tbl_{index}',
        caption=single_line,
        position=Position(page=None, paragraph_index=paragraph_index),
    )


def _looks_like_word_heading(style_name: str, text: str) -> bool:
    normalized_style = style_name.strip().lower()
    if any(hint in normalized_style for hint in _HEADING_STYLE_HINTS):
        return True

    normalized_text = ' '.join(text.lower().replace('?', '?').split())
    if normalized_text in _CANONICAL_UNNUMBERED_HEADINGS:
        return True

    return False


def _fallback_heading_from_style(text: str, sequence: int) -> dict:
    return {
        'id': f'sec_auto_{sequence}',
        'number': '',
        'title': text.strip(),
        'level': 1,
        'text': '',
    }


def _alignment_name(value: Any) -> str:
    if value is None:
        return 'unspecified'
    mapping = {
        0: 'left',
        1: 'center',
        2: 'right',
        3: 'justify',
        4: 'distribute',
    }
    try:
        return mapping.get(int(value), str(value).lower())
    except (TypeError, ValueError):
        return str(value).lower()


def _build_document_id(filename: str) -> str:
    stem = Path(filename).stem.lower()
    slug = re.sub(r"[^a-z0-9\u0430-\u044f\u0451]+", "_", stem, flags=re.IGNORECASE).strip('_')
    return slug or 'document'
