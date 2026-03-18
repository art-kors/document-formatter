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

FIGURE_CAPTION_PATTERN = re.compile(rf"^{FIGURE_WORD}\s+\d+(?:\.\d+)*\s*[\u2014\u2013-]\s*.+$")
FIGURE_DETECTION_PATTERN = re.compile(r'^(?:\u0420\u0438\u0441\u0443\u043d\u043e\u043a|\u0420\u0438\u0441\.?|\u0440\u0438\u0441\.?)\s*(?P<number>\d+(?:\.\d+)*)\s*[\u2014\u2013-]?\s*(?P<title>.*)$', re.IGNORECASE)
TABLE_CAPTION_PATTERN = re.compile(rf"^{TABLE_WORD}\s+\d+(?:\.\d+)*\s*[\u2014\u2013-]\s*.+$")
APPENDIX_TITLE_PATTERN = re.compile(f"^{APPENDIX_WORD}(?:\\s+[\u0410-\u042fA-Z])?(?:\\s*[-\u2013]\\s*.+|\\s+.+)?$")
REFERENCE_SECTION_HINTS = [
    _u("\u0441\u043f\u0438\u0441\u043e\u043a \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432"),
    _u("\u0441\u043f\u0438\u0441\u043e\u043a \u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u044b"),
    _u("\u0431\u0438\u0431\u043b\u0438\u043e\u0433\u0440\u0430\u0444"),
    _u("\u0431\u0438\u0431\u043b\u0438\u043e\u0433\u0440\u0430\u0444\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0441\u043f\u0438\u0441\u043e\u043a"),
    _u("\u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u0438 \u0438 \u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u0430"),
]
CONTENTS_SECTION_HINTS = [_u("\u0441\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435"), _u("\u043e\u0433\u043b\u0430\u0432\u043b\u0435\u043d\u0438\u0435")]
TITLE_PAGE_KEYWORDS = [_u("\u043e\u0442\u0447\u0435\u0442"), _u("\u0442\u0435\u043c\u0430"), _u("\u0432\u044b\u043f\u043e\u043b\u043d\u0438\u043b"), _u("\u043f\u0440\u043e\u0432\u0435\u0440\u0438\u043b"), _u("\u0440\u0443\u043a\u043e\u0432\u043e\u0434\u0438\u0442\u0435\u043b\u044c"), _u("\u0443\u043d\u0438\u0432\u0435\u0440\u0441\u0438\u0442\u0435\u0442"), _u("\u043a\u0430\u0444\u0435\u0434\u0440\u0430")]
TITLE_PAGE_RIGHT_HINTS = [_u("\u0432\u044b\u043f\u043e\u043b\u043d\u0438\u043b"), _u("\u043f\u0440\u043e\u0432\u0435\u0440\u0438\u043b"), _u("\u0440\u0443\u043a\u043e\u0432\u043e\u0434\u0438\u0442\u0435\u043b\u044c"), _u("\u043d\u043e\u0440\u043c\u043e\u043a\u043e\u043d\u0442\u0440\u043e\u043b\u044c"), _u("\u0441\u0442\u0443\u0434\u0435\u043d\u0442"), _u("\u0433\u0440\u0443\u043f\u043f\u0430")]
TITLE_PAGE_CENTER_HINTS = [_u("\u043e\u0442\u0447\u0435\u0442"), _u("\u0442\u0435\u043c\u0430"), _u("\u0440\u0430\u0431\u043e\u0442\u0430"), _u("\u043f\u0440\u043e\u0435\u043a\u0442")]
TITLE_PAGE_ORG_HINTS = [_u("\u043c\u0438\u043d\u0438\u0441\u0442\u0435\u0440\u0441\u0442\u0432\u043e"), _u("\u0443\u043d\u0438\u0432\u0435\u0440\u0441\u0438\u0442\u0435\u0442"), _u("\u0438\u043d\u0441\u0442\u0438\u0442\u0443\u0442"), _u("\u0430\u043a\u0430\u0434\u0435\u043c\u0438\u044f"), _u("\u043a\u0430\u0444\u0435\u0434\u0440\u0430"), _u("\u0444\u0430\u043a\u0443\u043b\u044c\u0442\u0435\u0442"), _u("\u043a\u043e\u043b\u043b\u0435\u0434\u0436")]
TITLE_PAGE_DOC_HINTS = [_u("\u043e\u0442\u0447\u0435\u0442"), _u("\u043f\u043e\u044f\u0441\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u0430\u044f \u0437\u0430\u043f\u0438\u0441\u043a\u0430"), _u("\u043a\u0443\u0440\u0441\u043e\u0432\u0430\u044f \u0440\u0430\u0431\u043e\u0442\u0430"), _u("\u0434\u0438\u043f\u043b\u043e\u043c\u043d\u0430\u044f \u0440\u0430\u0431\u043e\u0442\u0430"), _u("\u0432\u044b\u043f\u0443\u0441\u043a\u043d\u0430\u044f \u043a\u0432\u0430\u043b\u0438\u0444\u0438\u043a\u0430\u0446\u0438\u043e\u043d\u043d\u0430\u044f \u0440\u0430\u0431\u043e\u0442\u0430"), _u("\u043b\u0430\u0431\u043e\u0440\u0430\u0442\u043e\u0440\u043d\u0430\u044f \u0440\u0430\u0431\u043e\u0442\u0430"), _u("\u043f\u0440\u043e\u0435\u043a\u0442")]
TITLE_PAGE_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
UNNUMBERED_SECTION_TITLES = {_u("\u0432\u0432\u0435\u0434\u0435\u043d\u0438\u0435"), _u("\u0437\u0430\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435"), _u("\u0441\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435"), _u("\u0440\u0435\u0444\u0435\u0440\u0430\u0442"), _u("\u0441\u043f\u0438\u0441\u043e\u043a \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432"), _u("\u0441\u043f\u0438\u0441\u043e\u043a \u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u044b")}
FIGURE_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)*)")


def analyze_document_against_standard(document: DocumentInput, standard_id: str) -> AgentResult:
    parsed_standard = _load_parsed_standard(standard_id)
    issues: List[Issue] = []
    issues.extend(_check_figures(document, parsed_standard, standard_id))
    issues.extend(_check_tables(document, parsed_standard, standard_id))
    issues.extend(_check_front_matter_and_layout(document, parsed_standard, standard_id))
    issues.extend(_check_page_size(document, parsed_standard, standard_id))
    issues.extend(_check_page_layout_and_typography(document, parsed_standard, standard_id))
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
        location = IssueLocation(page=figure.position.page, paragraph_id=figure.id)

        if not caption:
            issues.append(_build_issue('formatting', 'missing_figure_caption', 'warning', _u("\u0423 \u0440\u0438\u0441\u0443\u043d\u043a\u0430 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u043f\u043e\u0434\u043f\u0438\u0441\u044c"), f"{FIGURE_WORD} {figure.id} " + _u("\u043d\u0435 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u043f\u043e\u0434\u043f\u0438\u0441\u044c \u0432 \u0444\u043e\u0440\u043c\u0430\u0442\u0435 '") + f"{FIGURE_WORD} N - " + _u("\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435'."), location, _build_standard_reference(standard_id, caption_rule), _u("\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043f\u043e\u0434\u043f\u0438\u0441\u044c \u0432\u0438\u0434\u0430: ") + f"{FIGURE_WORD} 1 - " + _u("\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0440\u0438\u0441\u0443\u043d\u043a\u0430")))
            continue

        if not _is_valid_figure_caption(caption):
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
            issues.append(_build_issue('formatting', 'figure_numbering_error', 'warning', _u("\u041d\u0430\u0440\u0443\u0448\u0435\u043d\u0430 \u043f\u043e\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u044c \u043d\u0443\u043c\u0435\u0440\u0430\u0446\u0438\u0438 \u0440\u0438\u0441\u0443\u043d\u043a\u043e\u0432"), _u("\u041d\u043e\u043c\u0435\u0440 \u0440\u0438\u0441\u0443\u043d\u043a\u0430 ") + number + _u(" \u043f\u043e\u0432\u0442\u043e\u0440\u044f\u0435\u0442\u0441\u044f \u0432 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0435."), IssueLocation(page=figure.position.page, paragraph_id=figure.id), _build_standard_reference(standard_id, numbering_rule), _u("\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u043d\u0443\u043c\u0435\u0440\u0430\u0446\u0438\u044e \u0440\u0438\u0441\u0443\u043d\u043a\u043e\u0432")))
            continue
        seen.add(number)
        if number != str(expected):
            issues.append(_build_issue('formatting', 'figure_numbering_error', 'warning', _u("\u041d\u0430\u0440\u0443\u0448\u0435\u043d\u0430 \u043f\u043e\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u044c \u043d\u0443\u043c\u0435\u0440\u0430\u0446\u0438\u0438 \u0440\u0438\u0441\u0443\u043d\u043a\u043e\u0432"), _u("\u041e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d \u0440\u0438\u0441\u0443\u043d\u043e\u043a ") + number + _u(", \u043e\u0436\u0438\u0434\u0430\u0435\u0442\u0441\u044f \u0440\u0438\u0441\u0443\u043d\u043e\u043a ") + str(expected) + '.', IssueLocation(page=figure.position.page, paragraph_id=figure.id), _build_standard_reference(standard_id, numbering_rule), _u("\u0412\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c \u043f\u043e\u0441\u043b\u0435\u0434\u043e\u0432\u0430\u0442\u0435\u043b\u044c\u043d\u0443\u044e \u043d\u0443\u043c\u0435\u0440\u0430\u0446\u0438\u044e \u0440\u0438\u0441\u0443\u043d\u043a\u043e\u0432")))
            expected = _safe_int(number, expected) + 1
        else:
            expected += 1
    return issues


def _is_valid_figure_caption(caption: str) -> bool:
    normalized = normalize_whitespace(caption)
    if not normalized.lower().startswith(FIGURE_WORD.lower()):
        return False
    if not any(dash in normalized for dash in (' - ', ' \u2014 ', ' \u2013 ')):
        return False
    match = FIGURE_DETECTION_PATTERN.match(normalized)
    if not match:
        return False
    return bool((match.group('title') or '').strip(' .-\u2014\u2013'))


def _is_valid_table_caption(caption: str) -> bool:
    normalized = normalize_whitespace(caption)
    if not normalized.lower().startswith(TABLE_WORD.lower()):
        return False
    if not any(dash in normalized for dash in (' - ', ' \u2014 ', ' \u2013 ')):
        return False
    match = re.match(rf'^{TABLE_WORD}\s+\d+(?:\.\d+)*\s*[\u2014\u2013-]\s*(?P<title>.+)$', normalized)
    if not match:
        return False
    return bool((match.group('title') or '').strip(' .-\u2014\u2013'))


def _check_tables(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    issues: List[Issue] = []
    caption_rule = _pick_rule(parsed_standard.rules, object_type='table', constraint_type='caption_required')
    reference_rule = _pick_rule(parsed_standard.rules, object_type='table', constraint_type='reference_required')
    for table in document.tables:
        caption = normalize_whitespace(table.caption)
        location = IssueLocation(page=table.position.page, paragraph_id=table.id)
        if not caption:
            issues.append(_build_issue('formatting', 'missing_table_caption', 'warning', _u("\u0423 \u0442\u0430\u0431\u043b\u0438\u0446\u044b \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u043d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435"), f"{TABLE_WORD} {table.id} " + _u("\u043d\u0435 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u0441\u0442\u0440\u043e\u043a\u0443 \u0432\u0438\u0434\u0430 '") + f"{TABLE_WORD} N - " + _u("\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0442\u0430\u0431\u043b\u0438\u0446\u044b'."), location, _build_standard_reference(standard_id, caption_rule), _u("\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0442\u0430\u0431\u043b\u0438\u0446\u044b")))
            continue
        if not _is_valid_table_caption(caption):
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
    paragraph_meta = paragraph_meta + (document.meta.extras.get('docx_table_paragraphs', []) if document.meta.extras else [])
    if not _has_contents_block(document, paragraph_meta):
        issues.append(_build_issue('formatting', 'missing_contents_section', 'warning', _u("\u0412 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0435 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u043e\u0433\u043b\u0430\u0432\u043b\u0435\u043d\u0438\u0435"), _u("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0440\u0430\u0437\u0434\u0435\u043b \u0438\u043b\u0438 \u0431\u043b\u043e\u043a \u0441 \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043a\u043e\u043c '\u041e\u0433\u043b\u0430\u0432\u043b\u0435\u043d\u0438\u0435' \u0438\u043b\u0438 '\u0421\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435'."), _fallback_document_location(document), _build_standard_reference(standard_id, contents_rule), _u("\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043e\u0433\u043b\u0430\u0432\u043b\u0435\u043d\u0438\u0435 (\u0441\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435)")))
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


def _check_page_size(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    section_meta = document.meta.extras.get('docx_sections', []) if document.meta.extras else []
    if not section_meta:
        return []

    formatting_rule = _pick_rule(parsed_standard.rules, object_type='report', constraint_type='formatting')
    if formatting_rule is None:
        formatting_rule = _pick_rule(parsed_standard.rules, object_type='appendix', constraint_type='formatting')

    invalid_sections = []
    for item in section_meta:
        width = item.get('page_width_mm')
        height = item.get('page_height_mm')
        if width is None or height is None:
            continue
        page_format = _classify_page_format(width, height)
        if page_format not in {'A4', 'A3'}:
            invalid_sections.append((item.get('section_index'), width, height))

    if not invalid_sections:
        return []

    details = '; '.join(
        _u('секция ') + str(index) + f': {width:.1f}x{height:.1f} ' + _u('мм')
        for index, width, height in invalid_sections
    )
    return [
        _build_issue(
            'formatting',
            'invalid_page_size',
            'warning',
            _u('Размер листа не соответствует допустимым форматам ГОСТ'),
            _u('Обнаружены секции с недопустимым форматом страницы: ') + details + '.',
            IssueLocation(page=1),
            _build_standard_reference(standard_id, formatting_rule),
            _u('Использовать листы формата A4. Для крупных таблиц и иллюстраций допустим формат A3.'),
        )
    ]


def _check_page_layout_and_typography(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    section_meta = document.meta.extras.get('docx_sections', []) if document.meta.extras else []
    paragraph_meta = document.meta.extras.get('docx_paragraphs', []) if document.meta.extras else []
    if not section_meta and not paragraph_meta:
        return []

    issues: List[Issue] = []
    formatting_rule = _pick_rule(parsed_standard.rules, object_type='report', constraint_type='formatting')
    if formatting_rule is None:
        formatting_rule = _pick_rule(parsed_standard.rules, object_type='appendix', constraint_type='formatting')

    invalid_margins = []
    for item in section_meta:
        if not _margins_match_gost(item):
            invalid_margins.append(item)
    if invalid_margins:
        details = '; '.join(
            _u('секция ') + str(item.get('section_index')) + ': '
            + _u('левое ') + str(item.get('left_margin_mm')) + ' ' + _u('мм') + ', '
            + _u('правое ') + str(item.get('right_margin_mm')) + ' ' + _u('мм') + ', '
            + _u('верхнее ') + str(item.get('top_margin_mm')) + ' ' + _u('мм') + ', '
            + _u('нижнее ') + str(item.get('bottom_margin_mm')) + ' ' + _u('мм')
            for item in invalid_margins
        )
        issues.append(
            _build_issue(
                'formatting',
                'invalid_page_margins',
                'warning',
                _u('Поля страницы не соответствуют ГОСТу'),
                _u('Обнаружены секции с некорректными полями: ') + details + '.',
                IssueLocation(page=1),
                _build_standard_reference(standard_id, formatting_rule),
                _u('Установить поля: левое 30 мм, правое 15 мм, верхнее и нижнее 20 мм.'),
            )
        )

    body_paragraphs = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph.section_id and paragraph.position.paragraph_index is not None and len(normalize_whitespace(paragraph.text)) >= 20
    ]
    paragraph_meta_map = {
        int(item['paragraph_index']): item
        for item in paragraph_meta
        if item.get('paragraph_index') is not None
    }

    invalid_indents = []
    invalid_line_spacing = []
    invalid_font_sizes = []
    invalid_font_families = []
    invalid_font_colors = []
    invalid_bold = []

    for paragraph in body_paragraphs:
        meta = paragraph_meta_map.get(paragraph.position.paragraph_index)
        if not meta:
            continue
        indent = meta.get('first_line_indent_mm')
        if indent is not None and abs(float(indent) - 12.5) > 1.5:
            invalid_indents.append((paragraph, indent))
        spacing = meta.get('line_spacing')
        if spacing is not None and abs(float(spacing) - 1.5) > 0.15:
            invalid_line_spacing.append((paragraph, spacing))
        font_size = meta.get('font_size_pt_min')
        if font_size is not None and float(font_size) < 12.0:
            invalid_font_sizes.append((paragraph, font_size))
        font_family = str(meta.get('font_family') or '').strip()
        if font_family and font_family.lower() != 'times new roman':
            invalid_font_families.append((paragraph, font_family))
        if meta.get('has_non_black_text'):
            invalid_font_colors.append(paragraph)
        if meta.get('has_bold_text'):
            invalid_bold.append(paragraph)

    if invalid_indents:
        paragraph, indent = invalid_indents[0]
        issues.append(
            _build_issue(
                'formatting',
                'invalid_first_line_indent',
                'warning',
                _u('Абзацный отступ не соответствует ГОСТу'),
                _u('В абзаце обнаружен отступ ') + f"{indent:.1f}" + ' ' + _u('мм вместо 12,5 мм.'),
                IssueLocation(section_id=paragraph.section_id, paragraph_id=paragraph.id, paragraph_index=paragraph.position.paragraph_index, page=paragraph.position.page),
                _build_standard_reference(standard_id, formatting_rule),
                _u('Установить абзацный отступ 1,25 см.'),
            )
        )

    if invalid_line_spacing:
        paragraph, spacing = invalid_line_spacing[0]
        issues.append(
            _build_issue(
                'formatting',
                'invalid_line_spacing',
                'warning',
                _u('Межстрочный интервал не соответствует ГОСТу'),
                _u('В абзаце обнаружен межстрочный интервал ') + f"{spacing:.2f}" + _u(' вместо 1,5.'),
                IssueLocation(section_id=paragraph.section_id, paragraph_id=paragraph.id, paragraph_index=paragraph.position.paragraph_index, page=paragraph.position.page),
                _build_standard_reference(standard_id, formatting_rule),
                _u('Установить межстрочный интервал 1,5.'),
            )
        )

    if invalid_font_sizes:
        paragraph, font_size = invalid_font_sizes[0]
        issues.append(
            _build_issue(
                'formatting',
                'invalid_font_size',
                'warning',
                _u('Размер шрифта меньше допустимого'),
                _u('В абзаце обнаружен шрифт ') + f"{font_size:.1f}" + _u(' pt, что меньше 12 pt.'),
                IssueLocation(section_id=paragraph.section_id, paragraph_id=paragraph.id, paragraph_index=paragraph.position.paragraph_index, page=paragraph.position.page),
                _build_standard_reference(standard_id, formatting_rule),
                _u('Использовать размер шрифта не менее 12 pt.'),
            )
        )

    if invalid_font_families:
        paragraph, font_family = invalid_font_families[0]
        issues.append(
            _build_issue(
                'formatting',
                'invalid_font_family',
                'warning',
                _u('\u0413\u0430\u0440\u043d\u0438\u0442\u0443\u0440\u0430 \u0448\u0440\u0438\u0444\u0442\u0430 \u043d\u0435 \u0441\u043e\u043e\u0442\u0432\u0435\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u0440\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u043e\u0432\u0430\u043d\u043d\u043e\u0439'),
                _u('\u0412 \u0430\u0431\u0437\u0430\u0446\u0435 \u043e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d \u0448\u0440\u0438\u0444\u0442 ') + font_family + '.',
                IssueLocation(section_id=paragraph.section_id, paragraph_id=paragraph.id, paragraph_index=paragraph.position.paragraph_index, page=paragraph.position.page),
                _build_standard_reference(standard_id, formatting_rule),
                _u('\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u044c Times New Roman \u0434\u043b\u044f \u043e\u0441\u043d\u043e\u0432\u043d\u043e\u0433\u043e \u0442\u0435\u043a\u0441\u0442\u0430.'),
            )
        )

    if invalid_font_colors:
        paragraph = invalid_font_colors[0]
        issues.append(
            _build_issue(
                'formatting',
                'invalid_font_color',
                'warning',
                _u('Цвет текста отличается от черного'),
                _u('В абзаце обнаружен текст не черного цвета.'),
                IssueLocation(section_id=paragraph.section_id, paragraph_id=paragraph.id, paragraph_index=paragraph.position.paragraph_index, page=paragraph.position.page),
                _build_standard_reference(standard_id, formatting_rule),
                _u('Использовать черный цвет шрифта.'),
            )
        )

    if invalid_bold:
        paragraph = invalid_bold[0]
        issues.append(
            _build_issue(
                'formatting',
                'unexpected_bold_text',
                'info',
                _u('Основной текст содержит полужирное начертание'),
                _u('В основном тексте обнаружен полужирный шрифт вне заголовков.'),
                IssueLocation(section_id=paragraph.section_id, paragraph_id=paragraph.id, paragraph_index=paragraph.position.paragraph_index, page=paragraph.position.page),
                _build_standard_reference(standard_id, formatting_rule),
                _u('Убрать полужирное начертание из основного текста.'),
            )
        )

    return issues


def _check_references_section(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    reference_rule = _pick_rule(parsed_standard.rules, object_type='references', constraint_type='required_presence')
    formatting_rule = _pick_rule(parsed_standard.rules, object_type='references', constraint_type='formatting')
    paragraph_meta = document.meta.extras.get('docx_paragraphs', []) if document.meta.extras else []
    paragraph_meta = paragraph_meta + (document.meta.extras.get('docx_table_paragraphs', []) if document.meta.extras else [])
    reference_section = _find_reference_section(document, paragraph_meta)
    if reference_section is None:
        return [_build_issue('formatting', 'missing_references_section', 'warning', _u("\u0412 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0435 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u0441\u043f\u0438\u0441\u043e\u043a \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432"), _u("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d \u0440\u0430\u0437\u0434\u0435\u043b, \u0441\u0432\u044f\u0437\u0430\u043d\u043d\u044b\u0439 \u0441\u043e \u0441\u043f\u0438\u0441\u043a\u043e\u043c \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432."), _fallback_document_location(document), _build_standard_reference(standard_id, reference_rule), _u("\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0440\u0430\u0437\u0434\u0435\u043b \u0441\u043e \u0441\u043f\u0438\u0441\u043a\u043e\u043c \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432"))]
    if len(normalize_whitespace(reference_section.text)) < 20:
        return [_build_issue('formatting', 'empty_references_section', 'warning', _u("\u0420\u0430\u0437\u0434\u0435\u043b \u0441\u043e \u0441\u043f\u0438\u0441\u043a\u043e\u043c \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432 \u0432\u044b\u0433\u043b\u044f\u0434\u0438\u0442 \u043f\u0443\u0441\u0442\u044b\u043c"), _u("\u0420\u0430\u0437\u0434\u0435\u043b '") + reference_section.title + _u("' \u043d\u0435 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u0441\u043f\u0438\u0441\u043a\u0430 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432."), IssueLocation(section_id=reference_section.id), _build_standard_reference(standard_id, formatting_rule or reference_rule), _u("\u0417\u0430\u043f\u043e\u043b\u043d\u0438\u0442\u044c \u0440\u0430\u0437\u0434\u0435\u043b \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u0430\u043c\u0438"))]
    return []


def _check_headings(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    issues: List[Issue] = []
    heading_rule = _pick_rule(parsed_standard.rules, object_type='heading', constraint_type='optional_allowed')
    punctuation_rule = _pick_rule(parsed_standard.rules, object_type='heading', constraint_type='generic')
    paragraph_meta = _paragraph_meta_by_index(document)
    section_heading_meta = document.meta.extras.get('section_headings', {}) if document.meta and document.meta.extras else {}
    for section in document.sections:
        title = normalize_whitespace(section.title)
        payload = section_heading_meta.get(section.id, {})
        paragraph_index = payload.get('paragraph_index')
        meta = paragraph_meta.get(paragraph_index, payload)
        location = IssueLocation(section_id=section.id, paragraph_index=paragraph_index)
        if not title:
            issues.append(_build_issue('formatting', 'empty_section_heading', 'warning', _u("У раздела отсутствует заголовок"), _u("Не заполнен заголовок раздела."), location, _build_standard_reference(standard_id, heading_rule), _u("Заполнить заголовок")))
            continue
        if title.endswith('.'):
            issues.append(_build_issue('formatting', 'heading_trailing_period', 'info', _u("Заголовок раздела заканчивается точкой"), _u("Заголовок '") + title + _u("' заканчивается точкой."), location, _build_standard_reference(standard_id, punctuation_rule or heading_rule), _u("Убрать точку")))
        if meta:
            alignment = meta.get('alignment')
            if alignment and alignment != 'center':
                issues.append(_build_issue('formatting', 'heading_not_centered', 'info', _u("Заголовок раздела выровнен не по центру"), _u("Заголовок '") + _format_heading_for_display(section) + _u("' имеет выравнивание '") + str(alignment) + _u("'."), location, _build_standard_reference(standard_id, heading_rule), _u("Выровнять заголовок по центру")))
            indent = meta.get('first_line_indent_mm')
            if indent is not None and abs(float(indent)) > 0.5:
                issues.append(_build_issue('formatting', 'heading_has_indent', 'info', _u("У заголовка раздела есть абзацный отступ"), _u("Заголовок '") + _format_heading_for_display(section) + _u("' имеет отступ ") + f"{float(indent):.1f}" + _u(" мм."), location, _build_standard_reference(standard_id, heading_rule), _u("Убрать абзацный отступ у заголовка")))
            if meta.get('has_non_black_text'):
                issues.append(_build_issue('formatting', 'heading_invalid_font_color', 'info', _u("Цвет заголовка отличается от черного"), _u("Заголовок '") + _format_heading_for_display(section) + _u("' оформлен нечерным цветом."), location, _build_standard_reference(standard_id, heading_rule), _u("Использовать черный цвет для заголовка")))
    return issues


def _format_heading_for_display(section: Section) -> str:
    if normalize_whitespace(section.number):
        return f"{normalize_whitespace(section.number)} {normalize_whitespace(section.title)}".strip()
    return normalize_whitespace(section.title)

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






def _margins_match_gost(item: dict, tolerance_mm: float = 1.5) -> bool:
    expected = {
        'left_margin_mm': 30.0,
        'right_margin_mm': 15.0,
        'top_margin_mm': 20.0,
        'bottom_margin_mm': 20.0,
    }
    for key, target in expected.items():
        value = item.get(key)
        if value is None:
            return True
        if abs(float(value) - target) > tolerance_mm:
            return False
    return True

def _classify_page_format(width_mm: float, height_mm: float, tolerance_mm: float = 3.0) -> str:
    normalized = tuple(sorted((round(width_mm, 1), round(height_mm, 1))))
    known_formats = {
        'A4': (210.0, 297.0),
        'A3': (297.0, 420.0),
    }
    for name, expected in known_formats.items():
        if abs(normalized[0] - expected[0]) <= tolerance_mm and abs(normalized[1] - expected[1]) <= tolerance_mm:
            return name
    return 'other'

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
    paragraph_meta = paragraph_meta + (document.meta.extras.get('docx_table_paragraphs', []) if document.meta.extras else [])
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
        return _document_has_reference(
            document,
            [FIGURE_WORD.lower(), 'рис.', 'рис', figure.caption],
        )

    candidates = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph.position.paragraph_index is not None
        and paragraph.position.paragraph_index < figure.position.paragraph_index
    ]
    haystack = normalize_whitespace(' '.join(paragraph.text for paragraph in candidates)).lower()
    if not haystack:
        return False

    if number:
        figure_ref_pattern = re.compile(
            rf'\b(?:{re.escape(FIGURE_WORD.lower())}|рис\.?|рисунка|рисунке)\s*{re.escape(str(number))}\b',
            re.IGNORECASE,
        )
        if figure_ref_pattern.search(haystack):
            return True

    return any(
        token in haystack for token in [FIGURE_WORD.lower(), 'рис.', 'рис']
    ) and (number is None or str(number) in haystack)


def _build_issue(issue_type: str, subtype: str, severity: str, message: str, evidence: str, location: IssueLocation, standard_reference: StandardReference, suggestion: Optional[str]) -> Issue:
    return Issue(id=make_id('issue_rag'), type=issue_type, subtype=subtype, severity=severity, message=message, location=location, evidence=evidence, standard_reference=standard_reference, suggestion=suggestion, agent='rag_agent')


def _find_reference_section(document: DocumentInput, paragraph_meta: List[dict]) -> Optional[Section]:
    for section in document.sections:
        normalized_title = normalize_whitespace(section.title).lower()
        if any(hint in normalized_title for hint in REFERENCE_SECTION_HINTS):
            return section

    paragraph_pool = [paragraph.text for paragraph in document.paragraphs]
    paragraph_pool.extend(str(item.get('text', '')) for item in paragraph_meta)
    for text in paragraph_pool:
        normalized_text = normalize_whitespace(text).lower()
        if any(hint in normalized_text for hint in REFERENCE_SECTION_HINTS):
            return Section(id='sec_references_detected', number='', title=normalized_text, text='detected')
    return None


def _fallback_document_location(document: DocumentInput) -> IssueLocation:
    if document.sections:
        return IssueLocation(section_id=document.sections[-1].id)
    if document.paragraphs:
        paragraph = document.paragraphs[-1]
        return IssueLocation(section_id=paragraph.section_id, paragraph_id=paragraph.id, paragraph_index=paragraph.position.paragraph_index, page=paragraph.position.page)
    return IssueLocation()


def _has_contents_block(document: DocumentInput, paragraph_meta: List[dict]) -> bool:
    for section in document.sections:
        normalized_title = normalize_whitespace(section.title).lower()
        if any(hint in normalized_title for hint in CONTENTS_SECTION_HINTS):
            return True

    paragraph_pool = [paragraph.text for paragraph in document.paragraphs]
    paragraph_pool.extend(str(item.get('text', '')) for item in paragraph_meta[:40])
    for text in paragraph_pool:
        normalized_text = normalize_whitespace(text).lower()
        if any(hint in normalized_text for hint in CONTENTS_SECTION_HINTS):
            return True
    return False


def _looks_like_title_page(paragraph_meta: List[dict]) -> bool:
    first_page_lines = [item for item in paragraph_meta[:30] if normalize_whitespace(str(item.get('text', '')))]
    if not first_page_lines:
        return False

    lowered_lines = [normalize_whitespace(str(item.get('text', ''))).lower() for item in first_page_lines]

    org_score = 1 if any(any(token in line for token in TITLE_PAGE_ORG_HINTS) for line in lowered_lines) else 0
    doc_score = 1 if any(any(token in line for token in TITLE_PAGE_DOC_HINTS) for line in lowered_lines) else 0
    signature_score = 1 if any(any(token in line for token in TITLE_PAGE_RIGHT_HINTS) for line in lowered_lines) else 0
    centered_lines = sum(1 for item in first_page_lines if item.get('alignment') == 'center')
    right_aligned_lines = sum(1 for item in first_page_lines if item.get('alignment') == 'right')
    center_score = 1 if any(
        item.get('alignment') == 'center' and any(token in normalize_whitespace(str(item.get('text', ''))).lower() for token in TITLE_PAGE_CENTER_HINTS)
        for item in first_page_lines
    ) else 0
    right_score = 1 if any(
        item.get('alignment') == 'right' and any(token in normalize_whitespace(str(item.get('text', ''))).lower() for token in TITLE_PAGE_RIGHT_HINTS)
        for item in first_page_lines
    ) else 0
    year_score = 1 if any(TITLE_PAGE_YEAR_RE.search(line) for line in lowered_lines) else 0
    keyword_score = sum(1 for token in TITLE_PAGE_KEYWORDS if any(token in line for line in lowered_lines))

    total_score = org_score + doc_score + signature_score + center_score + right_score + year_score
    if keyword_score >= 4:
        total_score += 1

    has_core = bool(org_score or doc_score or signature_score)
    structural_fallback = (
        len(first_page_lines) >= 6
        and (centered_lines >= 2 or right_aligned_lines >= 1)
        and (year_score or org_score or doc_score or signature_score)
    )
    return (has_core and total_score >= 3) or structural_fallback



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
