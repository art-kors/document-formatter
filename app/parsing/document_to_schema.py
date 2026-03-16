import re
from pathlib import Path
from typing import List, Optional

from app.schemas.document import DocumentInput, DocumentMeta, FigureItem, Paragraph, Position, Section, TableItem


SECTION_PATTERN = re.compile(r'^(?P<number>\d+(?:\.\d+)*)\s+(?P<title>[^\n]{1,200})$')
APPENDIX_PATTERN = re.compile(r'^(?:\u041f\u0420\u0418\u041b\u041e\u0416\u0415\u041d\u0418\u0415|\u041f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435)\s+(?P<number>[A-Z\u0410-\u042f\u0401])(?:\s*[\u2013-]?\s*(?P<title>.*))?$')
FIGURE_PATTERN = re.compile(r'^\u0420\u0438\u0441\u0443\u043d\u043e\u043a\s+(?P<number>\d+)\s*[\u2013-]?\s*(?P<title>.*)$', re.IGNORECASE)
TABLE_PATTERN = re.compile(r'^\u0422\u0430\u0431\u043b\u0438\u0446\u0430\s+(?P<number>\d+)\s*[\u2013-]?\s*(?P<title>.*)$', re.IGNORECASE)


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
    untitled_section_counter = 0

    for paragraph_index, block in enumerate(blocks, start=1):
        heading = _parse_heading(block)
        if heading is not None:
            if current_section is not None:
                current_section.text = current_section.text.strip()
            current_section = Section(**heading)
            sections.append(current_section)
            continue

        if current_section is None:
            untitled_section_counter += 1
            current_section = Section(
                id=f"sec_auto_{untitled_section_counter}",
                number="",
                title="\u0411\u0435\u0437 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u044f",
                level=1,
                text="",
            )
            sections.append(current_section)

        current_section.text = (current_section.text + "\n\n" + block).strip() if current_section.text else block

        figure = _parse_figure(block, len(figures) + 1)
        if figure is not None:
            figures.append(figure)
            continue

        table = _parse_table(block, len(tables) + 1)
        if table is not None:
            tables.append(table)
            continue

        paragraphs.append(
            Paragraph(
                id=f"p_{len(paragraphs) + 1}",
                section_id=current_section.id,
                text=block,
                position=Position(page=None, paragraph_index=paragraph_index),
            )
        )

    if current_section is not None:
        current_section.text = current_section.text.strip()

    title = next(
        (section.title for section in sections if section.title and section.title != "\u0411\u0435\u0437 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u044f"),
        Path(filename).stem,
    )
    return DocumentInput(
        document_id=document_id or _build_document_id(filename),
        standard_id=standard_id,
        meta=DocumentMeta(filename=filename, title=title, language="ru"),
        sections=sections,
        paragraphs=paragraphs,
        tables=tables,
        figures=figures,
    )


def _split_blocks(text: str) -> List[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return [block.strip() for block in re.split(r"\n\s*\n", normalized) if block.strip()]


def _parse_heading(block: str) -> Optional[dict]:
    single_line = " ".join(line.strip() for line in block.splitlines() if line.strip())
    appendix_match = APPENDIX_PATTERN.match(single_line)
    if appendix_match:
        suffix = appendix_match.group("title") or ""
        title = single_line if suffix else f"\u041f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435 {appendix_match.group('number')}"
        return {
            "id": f"sec_appendix_{appendix_match.group('number').lower()}",
            "number": appendix_match.group("number"),
            "title": title,
            "level": 1,
            "text": "",
        }

    match = SECTION_PATTERN.match(single_line)
    if not match:
        return None

    number = match.group("number")
    title = match.group("title").strip()
    level = number.count(".") + 1
    return {
        "id": f"sec_{number.replace('.', '_')}",
        "number": number,
        "title": title,
        "level": level,
        "text": "",
    }


def _parse_figure(block: str, index: int) -> Optional[FigureItem]:
    single_line = " ".join(line.strip() for line in block.splitlines() if line.strip())
    match = FIGURE_PATTERN.match(single_line)
    if not match:
        return None
    return FigureItem(
        id=f"fig_{index}",
        caption=single_line,
        position=Position(page=None, paragraph_index=None),
    )


def _parse_table(block: str, index: int) -> Optional[TableItem]:
    single_line = " ".join(line.strip() for line in block.splitlines() if line.strip())
    match = TABLE_PATTERN.match(single_line)
    if not match:
        return None
    return TableItem(
        id=f"tbl_{index}",
        caption=single_line,
        position=Position(page=None, paragraph_index=None),
    )


def _build_document_id(filename: str) -> str:
    stem = Path(filename).stem.lower()
    slug = re.sub(r"[^a-z0-9\u0430-\u044f\u0451]+", "_", stem, flags=re.IGNORECASE).strip("_")
    return slug or "document"
