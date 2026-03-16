import copy
import html
import re
import zipfile
from io import BytesIO
from typing import Dict, List, Optional

from app.schemas.document import DocumentInput, Paragraph, Position, Section
from app.schemas.issue import Issue, SuggestedFix


FIGURE_CAPTION_RE = re.compile(r"^Рисунок\s+(?P<number>\d+)\s*[—-]?\s*(?P<title>.*)$", re.IGNORECASE)
TABLE_CAPTION_RE = re.compile(r"^Таблица\s+(?P<number>\d+)\s*[—-]?\s*(?P<title>.*)$", re.IGNORECASE)
APPENDIX_RE = re.compile(r"^Приложение\s+([А-ЯA-Z])(?:\s*[—-]?\s*(.*))?$", re.IGNORECASE)

CONTENT_TYPES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
'''
ROOT_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
'''
DOC_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships" />
'''


def apply_fixes(document: DocumentInput, issues: List[Issue]) -> DocumentInput:
    fixed = copy.deepcopy(document)
    sections_by_id: Dict[str, Section] = {section.id: section for section in fixed.sections}
    paragraphs_by_id: Dict[str, Paragraph] = {paragraph.id: paragraph for paragraph in fixed.paragraphs}

    for issue in issues:
        suggestion = issue.suggestion
        if isinstance(suggestion, SuggestedFix):
            _apply_suggested_fix(fixed, sections_by_id, paragraphs_by_id, issue, suggestion)

    _apply_structural_fixes(fixed, issues, sections_by_id, paragraphs_by_id)
    _apply_rag_fixes(fixed, issues, sections_by_id, paragraphs_by_id)
    _refresh_sections_text(fixed)
    return fixed


def build_corrected_docx(document: DocumentInput) -> bytes:
    paragraphs = _document_to_lines(document)
    xml = _to_document_xml(paragraphs)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', CONTENT_TYPES)
        archive.writestr('_rels/.rels', ROOT_RELS)
        archive.writestr('word/document.xml', xml)
        archive.writestr('word/_rels/document.xml.rels', DOC_RELS)
    return buffer.getvalue()


def _apply_suggested_fix(
    document: DocumentInput,
    sections_by_id: Dict[str, Section],
    paragraphs_by_id: Dict[str, Paragraph],
    issue: Issue,
    suggestion: SuggestedFix,
) -> None:
    location = issue.location
    target_paragraph = paragraphs_by_id.get(location.paragraph_id or '')
    if target_paragraph is not None:
        target_paragraph.text = _replace_or_assign(target_paragraph.text, suggestion.before, suggestion.after)
        return

    target_section = sections_by_id.get(location.section_id or '')
    if target_section is not None:
        target_section.text = _replace_or_assign(target_section.text, suggestion.before, suggestion.after)
        target_section.title = _replace_or_assign(target_section.title, suggestion.before, suggestion.after)


def _apply_structural_fixes(
    document: DocumentInput,
    issues: List[Issue],
    sections_by_id: Dict[str, Section],
    paragraphs_by_id: Dict[str, Paragraph],
) -> None:
    need_renumber = any(issue.type == 'structure' and issue.subtype in {'numbering_error', 'order_error'} for issue in issues)
    if need_renumber:
        _renumber_sections(document)

    missing_required = [issue for issue in issues if issue.type == 'structure' and issue.subtype == 'missing_required_section']
    for issue in missing_required:
        match = re.search(r'«(.+?)»', issue.evidence)
        if not match:
            continue
        required_title = match.group(1)
        if any(section.title.strip().lower() == required_title.lower() for section in document.sections):
            continue
        _append_required_section(document, required_title)


def _apply_rag_fixes(
    document: DocumentInput,
    issues: List[Issue],
    sections_by_id: Dict[str, Section],
    paragraphs_by_id: Dict[str, Paragraph],
) -> None:
    for section in document.sections:
        if section.title.endswith('.'):
            section.title = section.title.rstrip('.').strip()

    for index, figure in enumerate(document.figures, start=1):
        number = _extract_number(index, figure.caption, FIGURE_CAPTION_RE)
        title = _extract_title(figure.caption, f'Иллюстрация {number}', FIGURE_CAPTION_RE)
        figure.caption = f'Рисунок {number} - {title}'

    for index, table in enumerate(document.tables, start=1):
        number = _extract_number(index, table.caption, TABLE_CAPTION_RE)
        title = _extract_title(table.caption, f'Сравнение показателей {number}', TABLE_CAPTION_RE)
        table.caption = f'Таблица {number} - {title}'

    if any(issue.subtype == 'invalid_appendix_heading' for issue in issues):
        for section in document.sections:
            if section.title.lower().startswith('приложение'):
                suffix = APPENDIX_RE.match(section.title)
                title_tail = suffix.group(2).strip() if suffix and suffix.group(2) else 'Материалы'
                section.number = 'А'
                section.title = f'Приложение А - {title_tail}'
                break

    if any(issue.subtype == 'missing_references_section' for issue in issues):
        if not any('источ' in section.title.lower() or 'литератур' in section.title.lower() for section in document.sections):
            _append_required_section(document, 'Список использованных источников', body='1. Добавьте используемые источники.')

    if any(issue.subtype == 'missing_figure_reference' for issue in issues):
        _append_reference_sentence(document, 'На рисунке 1 представлена ключевая схема решения.')
    if any(issue.subtype == 'missing_table_reference' for issue in issues):
        _append_reference_sentence(document, 'В таблице 1 приведены основные сравнительные показатели.')
    if any(issue.subtype == 'missing_appendix_reference' for issue in issues):
        _append_reference_sentence(document, 'Дополнительные материалы приведены в приложении А.')


def _replace_or_assign(source: str, before: str, after: str) -> str:
    before = (before or '').strip()
    after = (after or '').strip()
    if not before:
        return after or source
    if before in source:
        return source.replace(before, after, 1)
    return after or source


def _renumber_sections(document: DocumentInput) -> None:
    counters: Dict[tuple, int] = {}
    for section in document.sections:
        normalized_title = section.title.lower().strip()
        if normalized_title.startswith('приложение'):
            section.number = 'А'
            section.level = 1
            continue

        if section.level <= 1:
            parent = tuple()
        else:
            parent = tuple(int(part) for part in section.number.split('.')[:-1] if part.isdigit()) if section.number else tuple()
            if len(parent) != section.level - 1:
                parent = tuple()

        if section.level == 1:
            counters[tuple()] = counters.get(tuple(), 0) + 1
            section.number = str(counters[tuple()])
        else:
            if parent and parent not in counters:
                parent = tuple()
            counters[parent] = counters.get(parent, 0) + 1
            prefix = '.'.join(str(part) for part in parent)
            section.number = f'{prefix}.{counters[parent]}' if prefix else str(counters[parent])

        if section.number:
            current_tuple = tuple(int(part) for part in section.number.split('.') if part.isdigit())
            counters.setdefault(current_tuple, 0)


def _append_required_section(document: DocumentInput, title: str, body: str = 'Заполните содержимое раздела.') -> None:
    next_number = _next_top_level_number(document)
    section_id = f'sec_auto_{len(document.sections) + 1}'
    section = Section(id=section_id, number=str(next_number), title=title, level=1, text=body)
    document.sections.append(section)
    document.paragraphs.append(
        Paragraph(
            id=f'p_auto_{len(document.paragraphs) + 1}',
            section_id=section_id,
            text=body,
            position=Position(page=None, paragraph_index=len(document.paragraphs) + 1),
        )
    )


def _next_top_level_number(document: DocumentInput) -> int:
    numbers = []
    for section in document.sections:
        if section.number.isdigit():
            numbers.append(int(section.number))
    return max(numbers, default=0) + 1


def _append_reference_sentence(document: DocumentInput, sentence: str) -> None:
    if not document.sections:
        return
    first_section = document.sections[0]
    if sentence in first_section.text:
        return
    first_section.text = (first_section.text + '\n\n' + sentence).strip() if first_section.text else sentence
    document.paragraphs.append(
        Paragraph(
            id=f'p_auto_{len(document.paragraphs) + 1}',
            section_id=first_section.id,
            text=sentence,
            position=Position(page=None, paragraph_index=len(document.paragraphs) + 1),
        )
    )


def _extract_number(default: int, caption: str, pattern: re.Pattern[str]) -> int:
    match = pattern.match((caption or '').strip())
    if match and match.group('number').isdigit():
        return int(match.group('number'))
    return default


def _extract_title(caption: str, fallback: str, pattern: re.Pattern[str]) -> str:
    match = pattern.match((caption or '').strip())
    if match:
        title = (match.group('title') or '').strip(' -—')
        if title:
            return title
    return fallback


def _refresh_sections_text(document: DocumentInput) -> None:
    section_paragraphs: Dict[str, List[str]] = {section.id: [] for section in document.sections}
    for paragraph in document.paragraphs:
        if paragraph.section_id in section_paragraphs:
            section_paragraphs[paragraph.section_id].append(paragraph.text)

    for section in document.sections:
        texts = section_paragraphs.get(section.id) or [section.text] if section.text else []
        section.text = '\n\n'.join(text for text in texts if text).strip()


def _document_to_lines(document: DocumentInput) -> List[str]:
    lines: List[str] = []
    paragraphs_by_section: Dict[str, List[str]] = {section.id: [] for section in document.sections}
    for paragraph in document.paragraphs:
        if paragraph.section_id in paragraphs_by_section:
            paragraphs_by_section[paragraph.section_id].append(paragraph.text)

    for section in document.sections:
        heading = f'{section.number} {section.title}'.strip() if section.number else section.title
        lines.append(heading)
        body_lines = paragraphs_by_section.get(section.id) or ([section.text] if section.text else [])
        lines.extend(line for line in body_lines if line)

    if document.figures:
        lines.append('')
        lines.extend(figure.caption for figure in document.figures if figure.caption)
    if document.tables:
        lines.append('')
        lines.extend(table.caption for table in document.tables if table.caption)

    return [line for line in lines if line is not None]


def _to_document_xml(paragraphs: List[str]) -> str:
    body = []
    for paragraph in paragraphs:
        escaped = html.escape(paragraph)
        body.append(f'<w:p><w:r><w:t xml:space="preserve">{escaped}</w:t></w:r></w:p>')
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"
    xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
    xmlns:o="urn:schemas-microsoft-com:office:office"
    xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
    xmlns:v="urn:schemas-microsoft-com:vml"
    xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
    xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
    xmlns:w10="urn:schemas-microsoft-com:office:word"
    xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
    xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup"
    xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk"
    xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml"
    xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
    mc:Ignorable="w14 wp14">
  <w:body>
    %s
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1417" w:right="1134" w:bottom="1417" w:left="1134" w:header="708" w:footer="708" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>
''' % ''.join(body)
