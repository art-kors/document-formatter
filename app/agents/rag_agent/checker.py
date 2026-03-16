import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from app.schemas.agent_result import AgentResult
from app.schemas.document import DocumentInput, FigureItem, Section
from app.schemas.issue import Issue, IssueLocation, StandardReference
from app.schemas.standard import ParsedStandard, StandardRule
from app.standards.storage import standard_parsed_path_for
from app.utils.ids import make_id
from app.utils.text import normalize_whitespace


def _u(value: str) -> str:
    return value


FIGURE_WORD = _u("\u0420\u0438\u0441\u0443\u043d\u043e\u043a")
TABLE_WORD = _u("\u0422\u0430\u0431\u043b\u0438\u0446\u0430")
APPENDIX_WORD = _u("\u041f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435")
GOST_NAME = _u("\u0413\u041e\u0421\u0422 7.32-2017")

FIGURE_CAPTION_PATTERN = re.compile(f"^{FIGURE_WORD}\\s+[A-Za-z\u0410-\u042f\u0430-\u044f0-9.]+\\s*-\\s*.+$")
TABLE_CAPTION_PATTERN = re.compile(f"^{TABLE_WORD}\\s+[A-Za-z\u0410-\u042f\u0430-\u044f0-9.]+\\s*-\\s*.+$")
APPENDIX_TITLE_PATTERN = re.compile(f"^{APPENDIX_WORD}(?:\\s+[\u0410-\u042fA-Z])?(?:\\s*[-\u2013]\\s*.+|\\s+.+)?$")
REFERENCE_SECTION_HINTS = [
    _u("\u0441\u043f\u0438\u0441\u043e\u043a \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432"),
    _u("\u0441\u043f\u0438\u0441\u043e\u043a \u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u044b"),
    _u("\u0431\u0438\u0431\u043b\u0438\u043e\u0433\u0440\u0430\u0444"),
]
CONTENTS_SECTION_HINTS = [_u("\u0441\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435"), _u("\u043e\u0433\u043b\u0430\u0432\u043b\u0435\u043d\u0438\u0435")]
TITLE_PAGE_KEYWORDS = [_u("\u043e\u0442\u0447\u0435\u0442"), _u("\u0442\u0435\u043c\u0430"), _u("\u0432\u044b\u043f\u043e\u043b\u043d\u0438\u043b"), _u("\u043f\u0440\u043e\u0432\u0435\u0440\u0438\u043b"), _u("\u0440\u0443\u043a\u043e\u0432\u043e\u0434\u0438\u0442\u0435\u043b\u044c"), _u("\u0443\u043d\u0438\u0432\u0435\u0440\u0441\u0438\u0442\u0435\u0442"), _u("\u043a\u0430\u0444\u0435\u0434\u0440\u0430")]
TITLE_PAGE_RIGHT_HINTS = [_u("\u0432\u044b\u043f\u043e\u043b\u043d\u0438\u043b"), _u("\u043f\u0440\u043e\u0432\u0435\u0440\u0438\u043b"), _u("\u0440\u0443\u043a\u043e\u0432\u043e\u0434\u0438\u0442\u0435\u043b\u044c"), _u("\u043d\u043e\u0440\u043c\u043e\u043a\u043e\u043d\u0442\u0440\u043e\u043b\u044c"), _u("\u0441\u0442\u0443\u0434\u0435\u043d\u0442"), _u("\u0433\u0440\u0443\u043f\u043f\u0430")]
TITLE_PAGE_CENTER_HINTS = [_u("\u043e\u0442\u0447\u0435\u0442"), _u("\u0442\u0435\u043c\u0430"), _u("\u0440\u0430\u0431\u043e\u0442\u0430"), _u("\u043f\u0440\u043e\u0435\u043a\u0442")]
UNNUMBERED_SECTION_TITLES = {_u("\u0432\u0432\u0435\u0434\u0435\u043d\u0438\u0435"), _u("\u0437\u0430\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435"), _u("\u0441\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435"), _u("\u0440\u0435\u0444\u0435\u0440\u0430\u0442"), _u("\u0441\u043f\u0438\u0441\u043e\u043a \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432"), _u("\u0441\u043f\u0438\u0441\u043e\u043a \u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u044b")}
FIGURE_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)*)")


def analyze_document_against_standard(document: DocumentInput, standard_id: str) -> AgentResult:
    parsed_standard = _load_parsed_standard(standard_id)
    issues: List[Issue] = []
    issues.extend(_check_figures(document, parsed_standard, standard_id))
    issues.extend(_check_tables(document, parsed_standard, standard_id))
    issues.extend(_check_front_matter_and_layout(document, parsed_standard, standard_id))
    issues.extend(_check_references_section(document, parsed_standard, standard_id))
    issues.extend(_check_headings(document, parsed_standard, standard_id))
    issues.extend(_check_section_numbering(document, parsed_standard, standard_id))
    issues.extend(_check_appendix_sections(document, parsed_standard, standard_id))
    return AgentResult(agent='rag_agent', issues=issues)


def _check_figures(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    issues: List[Issue] = []
    caption_rule = _pick_rule(parsed_standard.rules, object_type='figure', constraint_type='caption_required')
    reference_rule = _pick_rule(parsed_standard.rules, object_type='figure', constraint_type='reference_required')
    numbering_rule = _pick_rule(parsed_standard.rules, object_type='figure', constraint_type='numbering')
    paragraph_meta = _paragraph_meta_by_index(document)
    observed_numbers: List[Tuple[FigureItem, Optional[str]]] = []

    for figure in document.figures:
        caption = normalize_whitespace(figure.caption)
        figure_number = _extract_number_from_caption(caption)
        observed_numbers.append((figure, figure_number))
        location = IssueLocation(page=figure.position.page)

        if not caption:
            issues.append(_build_issue('formatting', 'missing_figure_caption', 'warning', _u("\u0423 \u0440\u0438\u0441\u0443\u043d\u043a\u0430 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u043f\u043e\u0434\u043f\u0438\u0441\u044c"), f"{FIGURE_WORD} {figure.id} " + _u("\u043d\u0435 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u043f\u043e\u0434\u043f\u0438\u0441\u044c \u0432 \u0444\u043e\u0440\u043c\u0430\u0442\u0435 '") + f"{FIGURE_WORD} N - " + _u("\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435'."), location, _build_standard_reference(standard_id, caption_rule), _u("\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043f\u043e\u0434\u043f\u0438\u0441\u044c \u0432\u0438\u0434\u0430: ") + f"{FIGURE_WORD} 1 - " + _u("\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0440\u0438\u0441\u0443\u043d\u043a\u0430")))
            continue

        if not FIGURE_CAPTION_PATTERN.match(caption):
            issues.append(_build_issue('formatting', 'invalid_figure_caption_format', 'warning', _u("\u041f\u043e\u0434\u043f\u0438\u0441\u044c \u0440\u0438\u0441\u0443\u043d\u043a\u0430 \u043e\u0444\u043e\u0440\u043c\u043b\u0435\u043d\u0430 \u043d\u0435 \u043f\u043e \u0413\u041e\u0421\u0422\u0443"), _u("\u041e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d\u0430 \u043f\u043e\u0434\u043f\u0438\u0441\u044c: '") + caption + _u("'. \u041e\u0436\u0438\u0434\u0430\u0435\u0442\u0441\u044f \u0444\u043e\u0440\u043c\u0430\u0442 '") + f"{FIGURE_WORD} N - " + _u("\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435'."), location, _build_standard_reference(standard_id, caption_rule), _u("\u041f\u0440\u0438\u0432\u0435\u0441\u0442\u0438 \u043f\u043e\u0434\u043f\u0438\u0441\u044c \u043a \u0444\u043e\u0440\u043c\u0430\u0442\u0443: ") + f"{FIGURE_WORD} N - " + _u("\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0440\u0438\u0441\u0443\u043d\u043a\u0430")))

        if caption.endswith('.'):
            issues.append(_build_issue('formatting', 'figure_caption_trailing_period', 'info', _u("\u041f\u043e\u0434\u043f\u0438\u0441\u044c \u0440\u0438\u0441\u0443\u043d\u043a\u0430 \u0437\u0430\u043a\u0430\u043d\u0447\u0438\u0432\u0430\u0435\u0442\u0441\u044f \u0442\u043e\u0447\u043a\u043e\u0439"), _u("\u041f\u043e\u0434\u043f\u0438\u0441\u044c \u0440\u0438\u0441\u0443\u043d\u043a\u0430 '") + caption + _u("' \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u0442\u043e\u0447\u043a\u0443 \u0432 \u043a\u043e\u043d\u0446\u0435."), location, _build_standard_reference(standard_id, caption_rule), _u("\u0423\u0431\u0440\u0430\u0442\u044c \u0442\u043e\u0447\u043a\u0443 \u0432 \u043a\u043e\u043d\u0446\u0435 \u043f\u043e\u0434\u043f\u0438\u0441\u0438 \u0440\u0438\u0441\u0443\u043d\u043a\u0430")))

        if figure.position.paragraph_index is not None:
            meta = paragraph_meta.get(figure.position.paragraph_index)
            if meta and meta.get('alignment') != 'center':
                issues.append(_build_issue('formatting', 'figure_caption_not_centered', 'info', _u("\u041f\u043e\u0434\u043f\u0438\u0441\u044c \u0440\u0438\u0441\u0443\u043d\u043a\u0430 \u0432\u044b\u0440\u043e\u0432\u043d\u0435\u043d\u0430 \u043d\u0435 \u043f\u043e \u0446\u0435\u043d\u0442\u0440\u0443"), _u("\u041f\u043e\u0434\u043f\u0438\u0441\u044c \u0440\u0438\u0441\u0443\u043d\u043a\u0430 '") + caption + _u("' \u0438\u043c\u0435\u0435\u0442 \u0432\u044b\u0440\u0430\u0432\u043d\u0438\u0432\u0430\u043d\u0438\u0435 '") + str(meta.get('alignment')) + _u("'."), location, _build_standard_reference(standard_id, caption_rule), _u("\u0412\u044b\u0440\u043e\u0432\u043d\u044f\u0442\u044c \u043f\u043e\u0434\u043f\u0438\u0441\u044c \u0440\u0438\u0441\u0443\u043d\u043a\u0430 \u043f\u043e \u0446\u0435\u043d\u0442\u0440\u0443")))

        if reference_rule and not _has_figure_reference_before(document, figure):
            issues.append(_build_issue('formatting', 'missing_figure_reference', 'info', _u("\u041d\u0430 \u0440\u0438\u0441\u0443\u043d\u043e\u043a \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u0441\u0441\u044b\u043b\u043a\u0430 \u0434\u043e \u0435\u0433\u043e \u0440\u0430\u0437\u043c\u0435\u0449\u0435\u043d\u0438\u044f"), _u("\u0414\u043e \u043f\u043e\u0434\u043f\u0438\u0441\u0438 '") + caption + _u("' \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e \u0443\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435 \u0440\u0438\u0441\u0443\u043d\u043a\u0430 \u0432 \u0442\u0435\u043a\u0441\u0442\u0435 \u0434\u043e \u0435\u0433\u043e \u0440\u0430\u0437\u043c\u0435\u0449\u0435\u043d\u0438\u044f."), location, _build_standard_reference(standard_id, reference_rule), _u("\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0432 \u0442\u0435\u043a\u0441\u0442 \u0441\u0441\u044b\u043b\u043a\u0443 \u043d\u0430 \u0440\u0438\u0441\u0443\u043d\u043e\u043a \u0434\u043e \u0435\u0433\u043e \u0440\u0430\u0437\u043c\u0435\u0449\u0435\u043d\u0438\u044f")))

    issues.extend(_check_figure_numbering_sequence(observed_numbers, standard_id, numbering_rule or caption_rule))
    return issues


def _check_figure_numbering_sequence(observed_numbers: List[Tuple[FigureItem, Optional[str]]], standard_id: str, numbering_rule: Optional[StandardRule]) -> List[Issue]:
    issues: List[Issue] = []
    expected = 1
    seen: set[str] = set()
    for figure, number in observed_numbers:
        if number is None:
            continue
        if number in seen:
            issues.append(_build_issue('formatting', 'figure_numbering_error', 'warning', _u("\u041d\u0430\u0440\u0443\u0448\u0435\u043d\u0430 \u043f\u043e\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u044c \u043d\u0443\u043c\u0435\u0440\u0430\u0446\u0438\u0438 \u0440\u0438\u0441\u0443\u043d\u043a\u043e\u0432"), _u("\u041d\u043e\u043c\u0435\u0440 \u0440\u0438\u0441\u0443\u043d\u043a\u0430 ") + number + _u(" \u043f\u043e\u0432\u0442\u043e\u0440\u044f\u0435\u0442\u0441\u044f \u0432 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0435."), IssueLocation(page=figure.position.page), _build_standard_reference(standard_id, numbering_rule), _u("\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u043d\u0443\u043c\u0435\u0440\u0430\u0446\u0438\u044e \u0440\u0438\u0441\u0443\u043d\u043a\u043e\u0432")))
            continue
        seen.add(number)
        if number != str(expected):
            issues.append(_build_issue('formatting', 'figure_numbering_error', 'warning', _u("\u041d\u0430\u0440\u0443\u0448\u0435\u043d\u0430 \u043f\u043e\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u044c \u043d\u0443\u043c\u0435\u0440\u0430\u0446\u0438\u0438 \u0440\u0438\u0441\u0443\u043d\u043a\u043e\u0432"), _u("\u041e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d \u0440\u0438\u0441\u0443\u043d\u043e\u043a ") + number + _u(", \u043e\u0436\u0438\u0434\u0430\u0435\u0442\u0441\u044f \u0440\u0438\u0441\u0443\u043d\u043e\u043a ") + str(expected) + '.', IssueLocation(page=figure.position.page), _build_standard_reference(standard_id, numbering_rule), _u("\u0412\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c \u043f\u043e\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u0442\u0435\u043b\u044c\u043d\u0443\u044e \u043d\u0443\u043c\u0435\u0440\u0430\u0446\u0438\u044e \u0440\u0438\u0441\u0443\u043d\u043a\u043e\u0432")))
            expected = _safe_int(number, expected) + 1
        else:
            expected += 1
    return issues


def _check_tables(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    issues: List[Issue] = []
    caption_rule = _pick_rule(parsed_standard.rules, object_type='table', constraint_type='caption_required')
    reference_rule = _pick_rule(parsed_standard.rules, object_type='table', constraint_type='reference_required')
    for table in document.tables:
        caption = normalize_whitespace(table.caption)
        location = IssueLocation(page=table.position.page)
        if not caption:
            issues.append(_build_issue('formatting', 'missing_table_caption', 'warning', _u("\u0423 \u0442\u0430\u0431\u043b\u0438\u0446\u044b \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u043d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435"), f"{TABLE_WORD} {table.id} " + _u("\u043d\u0435 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u0441\u0442\u0440\u043e\u043a\u0443 \u0432\u0438\u0434\u0430 '") + f"{TABLE_WORD} N - " + _u("\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0442\u0430\u0431\u043b\u0438\u0446\u044b'."), location, _build_standard_reference(standard_id, caption_rule), _u("\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0442\u0430\u0431\u043b\u0438\u0446\u044b")))
            continue
        if not TABLE_CAPTION_PATTERN.match(caption):
            issues.append(_build_issue('formatting', 'invalid_table_caption_format', 'warning', _u("\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0442\u0430\u0431\u043b\u0438\u0446\u044b \u043e\u0444\u043e\u0440\u043c\u043b\u0435\u043d\u043e \u043d\u0435 \u043f\u043e \u0413\u041e\u0421\u0422\u0443"), _u("\u041e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d\u043e \u043d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435: '") + caption + _u("'."), location, _build_standard_reference(standard_id, caption_rule), _u("\u041f\u0440\u0438\u0432\u0435\u0441\u0442\u0438 \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a \u0442\u0430\u0431\u043b\u0438\u0446\u044b \u043a \u0444\u043e\u0440\u043c\u0430\u0442\u0443")))
        if reference_rule and not _document_has_reference(document, [_u("\u0442\u0430\u0431\u043b\u0438\u0446\u0430"), caption]):
            issues.append(_build_issue('formatting', 'missing_table_reference', 'info', _u("\u041d\u0430 \u0442\u0430\u0431\u043b\u0438\u0446\u0443 \u043c\u043e\u0436\u0435\u0442 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u043e\u0432\u0430\u0442\u044c \u0441\u0441\u044b\u043b\u043a\u0430 \u0432 \u0442\u0435\u043a\u0441\u0442\u0435"), _u("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e \u0443\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435 \u0442\u0430\u0431\u043b\u0438\u0446\u044b '") + caption + _u("'."), location, _build_standard_reference(standard_id, reference_rule), _u("\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0441\u0441\u044b\u043b\u043a\u0443 \u043d\u0430 \u0442\u0430\u0431\u043b\u0438\u0446\u0443")))
    return issues


def _check_front_matter_and_layout(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    issues: List[Issue] = []
    title_rule = _pick_rule(parsed_standard.rules, object_type='title_page', constraint_type='required_presence')
    contents_rule = _pick_rule(parsed_standard.rules, object_type='contents', constraint_type='required_presence')
    formatting_rule = _pick_rule(parsed_standard.rules, object_type='title_page', constraint_type='formatting')
    paragraph_meta = document.meta.extras.get('docx_paragraphs', []) if document.meta.extras else []
    if not _has_contents_block(document, paragraph_meta):
        issues.append(_build_issue('formatting', 'missing_contents_section', 'warning', _u("\u0412 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0435 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u0441\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435"), _u("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0440\u0430\u0437\u0434\u0435\u043b \u0438\u043b\u0438 \u0431\u043b\u043e\u043a \u0441 \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043a\u043e\u043c '\u0421\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435'."), _fallback_document_location(document), _build_standard_reference(standard_id, contents_rule), _u("\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0441\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435")))
    if paragraph_meta and not _looks_like_title_page(paragraph_meta):
        issues.append(_build_issue('formatting', 'missing_title_page', 'warning', _u("\u041d\u0435 \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u043d \u0442\u0438\u0442\u0443\u043b\u044c\u043d\u044b\u0439 \u043b\u0438\u0441\u0442 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430"), _u("\u0412 \u043f\u0435\u0440\u0432\u044b\u0445 \u0430\u0431\u0437\u0430\u0446\u0430\u0445 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u043d\u0430\u0431\u043e\u0440 \u043f\u0440\u0438\u0437\u043d\u0430\u043a\u043e\u0432 \u0442\u0438\u0442\u0443\u043b\u044c\u043d\u043e\u0433\u043e \u043b\u0438\u0441\u0442\u0430."), IssueLocation(page=1), _build_standard_reference(standard_id, title_rule), _u("\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0442\u0438\u0442\u0443\u043b\u044c\u043d\u044b\u0439 \u043b\u0438\u0441\u0442")))
    elif paragraph_meta:
        signer_lines = [item for item in paragraph_meta[:15] if any(token in item['text'].lower() for token in TITLE_PAGE_RIGHT_HINTS)]
        if signer_lines and any(item.get('alignment') != 'right' for item in signer_lines):
            issues.append(_build_issue('formatting', 'title_page_right_alignment', 'info', _u("\u041d\u0430 \u0442\u0438\u0442\u0443\u043b\u044c\u043d\u043e\u043c \u043b\u0438\u0441\u0442\u0435 \u0431\u043b\u043e\u043a\u0438 \u043f\u043e\u0434\u043f\u0438\u0441\u0435\u0439 \u0432\u044b\u0440\u043e\u0432\u043d\u0435\u043d\u044b \u043d\u0435 \u043f\u043e \u043f\u0440\u0430\u0432\u043e\u043c\u0443 \u043a\u0440\u0430\u044e"), _u("\u0421\u0442\u0440\u043e\u043a\u0438 \u0441 \u0434\u0430\u043d\u043d\u044b\u043c\u0438 \u043e\u0431 \u0438\u0441\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u0435 \u0438\u043b\u0438 \u0440\u0443\u043a\u043e\u0432\u043e\u0434\u0438\u0442\u0435\u043b\u0435 \u043d\u0435 \u0432\u044b\u0440\u043e\u0432\u043d\u0435\u043d\u044b \u043f\u043e \u043f\u0440\u0430\u0432\u043e\u043c\u0443 \u043a\u0440\u0430\u044e."), IssueLocation(page=1), _build_standard_reference(standard_id, formatting_rule or title_rule), _u("\u0412\u044b\u0440\u043e\u0432\u043d\u044f\u0442\u044c \u0438\u0445 \u043f\u043e \u043f\u0440\u0430\u0432\u043e\u043c\u0443 \u043a\u0440\u0430\u044e")))
        centered_core = [item for item in paragraph_meta[:10] if any(token in item['text'].lower() for token in TITLE_PAGE_CENTER_HINTS)]
        if centered_core and any(item.get('alignment') != 'center' for item in centered_core):
            issues.append(_build_issue('formatting', 'title_page_center_alignment', 'info', _u("\u041a\u043b\u044e\u0447\u0435\u0432\u044b\u0435 \u0441\u0442\u0440\u043e\u043a\u0438 \u0442\u0438\u0442\u0443\u043b\u044c\u043d\u043e\u0433\u043e \u043b\u0438\u0441\u0442\u0430 \u043d\u0435 \u043f\u043e \u0446\u0435\u043d\u0442\u0440\u0443"), _u("\u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u043e\u0442\u0447\u0435\u0442\u0430 \u0438\u043b\u0438 \u0442\u0435\u043c\u0430 \u0440\u0430\u0431\u043e\u0442\u044b \u043d\u0435 \u0438\u043c\u0435\u044e\u0442 \u0446\u0435\u043d\u0442\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f."), IssueLocation(page=1), _build_standard_reference(standard_id, formatting_rule or title_rule), _u("\u0412\u044b\u0440\u043e\u0432\u043d\u044f\u0442\u044c \u0438\u0445 \u043f\u043e \u0446\u0435\u043d\u0442\u0440\u0443")))
        body_lines = [item for item in paragraph_meta if len(item['text']) >= 80 and item.get('alignment') not in {'center', 'right'}]
        if body_lines and sum(1 for item in body_lines if item.get('alignment') != 'justify') >= max(3, len(body_lines) // 2):
            issues.append(_build_issue('formatting', 'body_text_not_justified', 'info', _u("\u041e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u0442\u0435\u043a\u0441\u0442 \u043c\u043e\u0436\u0435\u0442 \u0431\u044b\u0442\u044c \u0432\u044b\u0440\u043e\u0432\u043d\u0435\u043d \u043d\u0435 \u043f\u043e \u0448\u0438\u0440\u0438\u043d\u0435"), _u("\u0411\u043e\u043b\u044c\u0448\u0430\u044f \u0447\u0430\u0441\u0442\u044c \u0434\u043b\u0438\u043d\u043d\u044b\u0445 \u0430\u0431\u0437\u0430\u0446\u0435\u0432 \u043d\u0435 \u0438\u043c\u0435\u0435\u0442 \u0432\u044b\u0440\u0430\u0432\u043d\u0438\u0432\u0430\u043d\u0438\u044f \u043f\u043e \u0448\u0438\u0440\u0438\u043d\u0435."), IssueLocation(page=1), _build_standard_reference(standard_id, formatting_rule), _u("\u0412\u044b\u0440\u043e\u0432\u043d\u044f\u0442\u044c \u0430\u0431\u0437\u0430\u0446\u044b \u043f\u043e \u0448\u0438\u0440\u0438\u043d\u0435")))
    return issues


def _check_references_section(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    reference_rule = _pick_rule(parsed_standard.rules, object_type='references', constraint_type='required_presence')
    formatting_rule = _pick_rule(parsed_standard.rules, object_type='references', constraint_type='formatting')
    reference_section = _find_reference_section(document.sections)
    if reference_section is None:
        return [_build_issue('formatting', 'missing_references_section', 'warning', _u("\u0412 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0435 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u0441\u043f\u0438\u0441\u043e\u043a \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432"), _u("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0440\u0430\u0437\u0434\u0435\u043b, \u0441\u0432\u044f\u0437\u0430\u043d\u043d\u044b\u0439 \u0441\u043e \u0441\u043f\u0438\u0441\u043a\u043e\u043c \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432."), _fallback_document_location(document), _build_standard_reference(standard_id, reference_rule), _u("\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0440\u0430\u0437\u0434\u0435\u043b \u0441\u043e \u0441\u043f\u0438\u0441\u043a\u043e\u043c \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432"))]
    if len(normalize_whitespace(reference_section.text)) < 20:
        return [_build_issue('formatting', 'empty_references_section', 'warning', _u("\u0420\u0430\u0437\u0434\u0435\u043b \u0441\u043e \u0441\u043f\u0438\u0441\u043a\u043e\u043c \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432 \u0432\u044b\u0433\u043b\u044f\u0434\u0438\u0442 \u043f\u0443\u0441\u0442\u044b\u043c"), _u("\u0420\u0430\u0437\u0434\u0435\u043b '") + reference_section.title + _u("' \u043d\u0435 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u0441\u043f\u0438\u0441\u043a\u0430 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432."), IssueLocation(section_id=reference_section.id), _build_standard_reference(standard_id, formatting_rule or reference_rule), _u("\u0417\u0430\u043f\u043e\u043b\u043d\u0438\u0442\u044c \u0440\u0430\u0437\u0434\u0435\u043b \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u0430\u043c\u0438"))]
    return []


def _check_headings(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    issues: List[Issue] = []
    heading_rule = _pick_rule(parsed_standard.rules, object_type='heading', constraint_type='optional_allowed')
    punctuation_rule = _pick_rule(parsed_standard.rules, object_type='heading', constraint_type='generic')
    for section in document.sections:
        title = normalize_whitespace(section.title)
        if not title:
            issues.append(_build_issue('formatting', 'empty_section_heading', 'warning', _u("\u0423 \u0440\u0430\u0437\u0434\u0435\u043b\u0430 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a"), _u("\u041d\u0435 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a \u0440\u0430\u0437\u0434\u0435\u043b\u0430."), IssueLocation(section_id=section.id), _build_standard_reference(standard_id, heading_rule), _u("\u0417\u0430\u043f\u043e\u043b\u043d\u0438\u0442\u044c \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a")))
            continue
        if title.endswith('.'):
            issues.append(_build_issue('formatting', 'heading_trailing_period', 'info', _u("\u0417\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a \u0440\u0430\u0437\u0434\u0435\u043b\u0430 \u0437\u0430\u043a\u0430\u043d\u0447\u0438\u0432\u0430\u0435\u0442\u0441\u044f \u0442\u043e\u0447\u043a\u043e\u0439"), _u("\u0417\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a '") + title + _u("' \u0437\u0430\u043a\u0430\u043d\u0447\u0438\u0432\u0430\u0435\u0442\u0441\u044f \u0442\u043e\u0447\u043a\u043e\u0439."), IssueLocation(section_id=section.id), _build_standard_reference(standard_id, punctuation_rule or heading_rule), _u("\u0423\u0431\u0440\u0430\u0442\u044c \u0442\u043e\u0447\u043a\u0443")))
    return issues


def _check_section_numbering(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    issues: List[Issue] = []
    numbering_rule = _pick_rule(parsed_standard.rules, object_type='section', constraint_type='numbering')
    level_groups: Dict[int, List[Section]] = {}
    for section in document.sections:
        level_groups.setdefault(section.level, []).append(section)
    for level_sections in level_groups.values():
        numbered_count = sum(1 for section in level_sections if normalize_whitespace(section.number))
        if numbered_count < 2:
            continue
        for section in level_sections:
            if normalize_whitespace(section.title).lower() in UNNUMBERED_SECTION_TITLES:
                continue
            if not normalize_whitespace(section.number):
                issues.append(_build_issue('formatting', 'missing_section_number', 'warning', _u("\u0423 \u0440\u0430\u0437\u0434\u0435\u043b\u0430 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u043d\u043e\u043c\u0435\u0440"), _u("\u0420\u0430\u0437\u0434\u0435\u043b '") + section.title + _u("' \u0440\u0430\u0441\u043f\u043e\u043b\u043e\u0436\u0435\u043d \u0441\u0440\u0435\u0434\u0438 \u043d\u0443\u043c\u0435\u0440\u0443\u0435\u043c\u044b\u0445 \u0440\u0430\u0437\u0434\u0435\u043b\u043e\u0432."), IssueLocation(section_id=section.id), _build_standard_reference(standard_id, numbering_rule), _u("\u041f\u0440\u0438\u0441\u0432\u043e\u0438\u0442\u044c \u043d\u043e\u043c\u0435\u0440")))
    return issues


def _check_appendix_sections(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    issues: List[Issue] = []
    appendix_format_rule = _pick_rule(parsed_standard.rules, object_type='appendix', constraint_type='formatting')
    appendix_reference_rule = _pick_rule(parsed_standard.rules, object_type='appendix', constraint_type='reference_required')
    appendix_sections = [section for section in document.sections if _u("\u043f\u0440\u0438\u043b\u043e\u0436") in normalize_whitespace(section.title).lower()]
    for section in appendix_sections:
        title = normalize_whitespace(section.title)
        if not APPENDIX_TITLE_PATTERN.match(title):
            issues.append(_build_issue('formatting', 'invalid_appendix_heading', 'warning', _u("\u0417\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f \u043e\u0444\u043e\u0440\u043c\u043b\u0435\u043d \u043d\u0435 \u043f\u043e \u0413\u041e\u0421\u0422\u0443"), _u("\u041e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f '") + title + _u("'."), IssueLocation(section_id=section.id), _build_standard_reference(standard_id, appendix_format_rule), _u("\u041f\u0440\u0438\u0432\u0435\u0441\u0442\u0438 \u043a \u0444\u043e\u0440\u043c\u0430\u0442\u0443 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f")))
        if appendix_reference_rule and not _document_has_reference(document, [title, _u("\u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435")]):
            issues.append(_build_issue('formatting', 'missing_appendix_reference', 'info', _u("\u041d\u0430 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u043c\u043e\u0436\u0435\u0442 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u043e\u0432\u0430\u0442\u044c \u0441\u0441\u044b\u043b\u043a\u0430 \u0432 \u0442\u0435\u043a\u0441\u0442\u0435"), _u("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e \u0443\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f '") + title + _u("'."), IssueLocation(section_id=section.id), _build_standard_reference(standard_id, appendix_reference_rule), _u("\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0441\u0441\u044b\u043b\u043a\u0443 \u043d\u0430 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435")))
    return issues


def _load_parsed_standard(standard_id: str) -> ParsedStandard:
    path = Path(standard_parsed_path_for(standard_id))
    if not path.exists():
        raise FileNotFoundError(f"Parsed standard not found for {standard_id}: {path}")
    return ParsedStandard.model_validate_json(path.read_text(encoding='utf-8'))


def _pick_rule(rules: Iterable[StandardRule], *, object_type: Optional[str] = None, constraint_type: Optional[str] = None) -> Optional[StandardRule]:
    filtered = list(rules)
    if object_type:
        filtered = [rule for rule in filtered if rule.object_type == object_type]
    if constraint_type:
        exact = [rule for rule in filtered if rule.constraint_type == constraint_type]
        if exact:
            filtered = exact
    if not filtered:
        return None
    return sorted(filtered, key=lambda rule: _rule_sort_key(rule.number))[0]


def _rule_sort_key(number: str) -> List[int]:
    return [int(''.join(ch for ch in part if ch.isdigit()) or 0) for part in number.split('.')]


def _build_standard_reference(standard_id: str, rule: Optional[StandardRule]) -> StandardReference:
    if rule is None:
        return StandardReference(source=_format_standard_name(standard_id), rule_id='', quote='')
    quote_source = normalize_whitespace(rule.content or rule.title)
    return StandardReference(source=_format_standard_name(standard_id), rule_id=rule.id, quote=quote_source[:280])


def _format_standard_name(standard_id: str) -> str:
    return GOST_NAME if standard_id.lower() == 'gost_7_32_2017' else standard_id.replace('_', ' ').upper()


def _paragraph_meta_by_index(document: DocumentInput) -> Dict[int, dict]:
    paragraph_meta = document.meta.extras.get('docx_paragraphs', []) if document.meta.extras else []
    return {int(item['paragraph_index']): item for item in paragraph_meta if item.get('paragraph_index') is not None}


def _extract_number_from_caption(caption: str) -> Optional[str]:
    match = FIGURE_NUMBER_RE.search(caption or '')
    return match.group(1) if match else None


def _safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except ValueError:
        return default


def _has_figure_reference_before(document: DocumentInput, figure: FigureItem) -> bool:
    number = _extract_number_from_caption(normalize_whitespace(figure.caption))
    if figure.position.paragraph_index is None:
        return _document_has_reference(document, [FIGURE_WORD.lower(), figure.caption])
    candidates = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph.position.paragraph_index is not None and paragraph.position.paragraph_index < figure.position.paragraph_index
    ]
    haystack = normalize_whitespace(' '.join(paragraph.text for paragraph in candidates)).lower()
    if not haystack:
        return False
    if number:
        figure_in = _u(r'\u0440\u0438\u0441\u0443\u043d\u043a\u0435')
        figure_gen = _u(r'\u0440\u0438\u0441\u0443\u043d\u043a\u0430')
        if any(token in haystack for token in [f"{FIGURE_WORD.lower()} {number}", f"{figure_in} {number}", f"{figure_gen} {number}"]):
            return True
    return FIGURE_WORD.lower() in haystack and (number is None or str(number) in haystack)


def _build_issue(issue_type: str, subtype: str, severity: str, message: str, evidence: str, location: IssueLocation, standard_reference: StandardReference, suggestion: Optional[str]) -> Issue:
    return Issue(id=make_id('issue_rag'), type=issue_type, subtype=subtype, severity=severity, message=message, location=location, evidence=evidence, standard_reference=standard_reference, suggestion=suggestion, agent='rag_agent')


def _find_reference_section(sections: Iterable[Section]) -> Optional[Section]:
    for section in sections:
        normalized_title = normalize_whitespace(section.title).lower()
        if any(hint in normalized_title for hint in REFERENCE_SECTION_HINTS):
            return section
    return None


def _fallback_document_location(document: DocumentInput) -> IssueLocation:
    if document.sections:
        return IssueLocation(section_id=document.sections[-1].id)
    if document.paragraphs:
        paragraph = document.paragraphs[-1]
        return IssueLocation(section_id=paragraph.section_id, paragraph_id=paragraph.id, page=paragraph.position.page)
    return IssueLocation()


def _has_contents_block(document: DocumentInput, paragraph_meta: List[dict]) -> bool:
    for section in document.sections:
        normalized_title = normalize_whitespace(section.title).lower()
        if any(hint in normalized_title for hint in CONTENTS_SECTION_HINTS):
            return True
    for item in paragraph_meta[:20]:
        normalized_text = normalize_whitespace(str(item.get('text', ''))).lower()
        if any(hint == normalized_text for hint in CONTENTS_SECTION_HINTS):
            return True
    return False


def _looks_like_title_page(paragraph_meta: List[dict]) -> bool:
    first_page_lines = [item for item in paragraph_meta[:20] if item.get('text')]
    if not first_page_lines:
        return False

    matched_keywords = 0
    for token in TITLE_PAGE_KEYWORDS:
        if any(token in str(item.get('text', '')).lower() for item in first_page_lines):
            matched_keywords += 1

    has_centered_core = any(
        item.get('alignment') == 'center'
        and any(token in str(item.get('text', '')).lower() for token in TITLE_PAGE_CENTER_HINTS)
        for item in first_page_lines
    )
    has_right_signature = any(
        item.get('alignment') == 'right'
        and any(token in str(item.get('text', '')).lower() for token in TITLE_PAGE_RIGHT_HINTS)
        for item in first_page_lines
    )
    return matched_keywords >= 3 and (has_centered_core or has_right_signature)



def _document_has_reference(document: DocumentInput, fragments: List[str]) -> bool:
    paragraph_text = ' '.join(paragraph.text for paragraph in document.paragraphs)
    section_text = ' '.join(section.text for section in document.sections)
    haystack = normalize_whitespace(f"{paragraph_text} {section_text}").lower()
    normalized_fragments = [normalize_whitespace(fragment).lower() for fragment in fragments if fragment]
    for fragment in normalized_fragments:
        if len(fragment) >= 8 and fragment in haystack:
            return True
    generic_tokens = [FIGURE_WORD.lower(), TABLE_WORD.lower(), APPENDIX_WORD.lower()]
    return any(token in haystack for token in generic_tokens if any(token in fragment for fragment in normalized_fragments))
