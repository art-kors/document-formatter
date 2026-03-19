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
FIGURE_DETECTION_PATTERN = re.compile(r'^(?:\u0420\u0438\u0441\u0443\u043d\u043e(?:\u043a)?|\u0420\u0438\u0441\.?|\u0440\u0438\u0441\.?)\s*(?P<number>\d+(?:\.\d+)*)\s*[\u2014\u2013-]?\s*(?P<title>.*)$', re.IGNORECASE)
TABLE_CAPTION_PATTERN = re.compile(r'^(?:\u0422\u0430\u0431\u043b\u0438\u0446(?:\u0430)?)\s+\d+(?:\.\d+)*\s*[\u2014\u2013-]\s*.+$', re.IGNORECASE)
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
CENTERED_STRUCTURAL_TITLES = {
    _u("\u0441\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435"),
    _u("\u043e\u0433\u043b\u0430\u0432\u043b\u0435\u043d\u0438\u0435"),
    _u("\u0440\u0435\u0444\u0435\u0440\u0430\u0442"),
    _u("\u0441\u043f\u0438\u0441\u043e\u043a \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432"),
    _u("\u0441\u043f\u0438\u0441\u043e\u043a \u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u044b"),
    _u("\u0431\u0438\u0431\u043b\u0438\u043e\u0433\u0440\u0430\u0444\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0441\u043f\u0438\u0441\u043e\u043a"),
    _u("\u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u0438 \u0438 \u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u0430"),
}
FIGURE_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)*)")


def analyze_document_against_standard(document: DocumentInput, standard_id: str) -> AgentResult:
    parsed_standard = _load_parsed_standard(standard_id)
    issues: List[Issue] = []
    issues.extend(_check_figures(document, parsed_standard, standard_id))
    issues.extend(_check_tables(document, parsed_standard, standard_id))
    issues.extend(_check_formulas(document, parsed_standard, standard_id))
    issues.extend(_check_front_matter_and_layout(document, parsed_standard, standard_id))
    issues.extend(_check_page_size(document, parsed_standard, standard_id))
    issues.extend(_check_page_numbering(document, parsed_standard, standard_id))
    issues.extend(_check_page_layout_and_typography(document, parsed_standard, standard_id))
    issues.extend(_check_enumerations(document, parsed_standard, standard_id))
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
    appendix_format_rule = _pick_rule(parsed_standard.rules, object_type='appendix', constraint_type='formatting')
    tables_meta = document.meta.extras.get('docx_tables_meta', []) if document.meta and document.meta.extras else []
    table_paragraphs = document.meta.extras.get('docx_table_paragraphs', []) if document.meta and document.meta.extras else []
    meta_by_caption_index = {
        item.get('caption_paragraph_index'): item
        for item in tables_meta
        if item.get('caption_paragraph_index') is not None
    }

    for index, table in enumerate(document.tables, start=1):
        caption = normalize_whitespace(table.caption)
        location = IssueLocation(page=table.position.page, paragraph_id=table.id, paragraph_index=table.position.paragraph_index)
        meta = meta_by_caption_index.get(table.position.paragraph_index)
        if meta is None and index <= len(tables_meta):
            meta = tables_meta[index - 1]

        if not caption:
            issues.append(_build_issue('formatting', 'missing_table_caption', 'warning', _u("У таблицы отсутствует наименование"), f"{TABLE_WORD} {table.id} " + _u("не содержит строку вида '") + f"{TABLE_WORD} N - " + _u("Наименование таблицы'."), location, _build_standard_reference(standard_id, caption_rule), _u("Добавить наименование таблицы")))
            continue
        if not _is_valid_table_caption(caption):
            issues.append(_build_issue('formatting', 'invalid_table_caption_format', 'warning', _u("Наименование таблицы оформлено не по ГОСТу"), _u("Обнаружено наименование: '") + caption + _u("'."), location, _build_standard_reference(standard_id, caption_rule), _u("Привести заголовок таблицы к формату 'Таблица N - Наименование'")))
        if reference_rule and not _document_has_reference(document, [_u("таблица"), caption]):
            issues.append(_build_issue('formatting', 'missing_table_reference', 'info', _u("На таблицу может отсутствовать ссылка в тексте"), _u("Не найдено упоминание таблицы '") + caption + _u("'."), location, _build_standard_reference(standard_id, reference_rule), _u("Добавить ссылку на таблицу")))

        if meta:
            if meta.get('caption_position') == 'below':
                issues.append(_build_issue('formatting', 'table_caption_below_table', 'warning', _u("Подпись таблицы расположена под таблицей"), _u("Подпись '") + caption + _u("' расположена после таблицы, а не перед ней."), location, _build_standard_reference(standard_id, caption_rule), _u("Переместить подпись таблицы над таблицей")))

            header_cells = [normalize_whitespace(cell) for cell in meta.get('header_cells', []) if normalize_whitespace(cell)]
            invalid_headers = [cell for cell in header_cells if cell.endswith('.')]
            if invalid_headers:
                issues.append(_build_issue('formatting', 'invalid_table_header_punctuation', 'warning', _u("Заголовки столбцов таблицы содержат точки"), _u("В первой строке таблицы обнаружены заголовки с точкой: ") + '; '.join(invalid_headers) + '.', location, _build_standard_reference(standard_id, caption_rule), _u("Убрать точки в заголовках столбцов таблицы")))

            header_paragraphs = [item for item in table_paragraphs if item.get('table_index') == index and item.get('row_index') == 1 and normalize_whitespace(item.get('text', ''))]
            if header_paragraphs and any(item.get('alignment') != 'center' for item in header_paragraphs):
                issues.append(_build_issue('formatting', 'table_header_alignment', 'info', _u("Заголовки столбцов таблицы должны быть по центру"), _u("В первой строке таблицы обнаружено нецентрованное выравнивание заголовков столбцов."), location, _build_standard_reference(standard_id, caption_rule), _u("Выровнять заголовки столбцов по центру")))

            appendix_letter = meta.get('appendix_letter')
            if appendix_letter and not _is_valid_appendix_table_caption(caption, appendix_letter):
                issues.append(_build_issue('formatting', 'appendix_table_caption_format', 'warning', _u("Подпись таблицы в приложении оформлена не по ГОСТу"), _u("Таблица в приложении '") + str(appendix_letter) + _u("' имеет подпись '") + caption + _u("'."), location, _build_standard_reference(standard_id, appendix_format_rule or caption_rule), _u("Оформить подпись в виде 'Таблица ") + str(appendix_letter) + _u(".1 - Наименование'")))
    return issues


def _is_valid_appendix_table_caption(caption: str, appendix_letter: str) -> bool:
    normalized = normalize_whitespace(caption)
    return bool(re.match(rf'^{re.escape(TABLE_WORD)}\s+{re.escape(str(appendix_letter))}\.\d+\s*[—–-]\s*.+$', normalized, re.IGNORECASE))

def _check_formulas(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    formula_meta = document.meta.extras.get('docx_formulas', []) if document.meta and document.meta.extras else []
    if not formula_meta:
        return []

    issues: List[Issue] = []
    formula_rule = _pick_rule(parsed_standard.rules, object_type='formula')
    numbering_rule = _pick_rule(parsed_standard.rules, object_type='formula', constraint_type='numbering') or formula_rule
    explanation_rule = _pick_rule(parsed_standard.rules, object_type='formula', constraint_type='generic') or formula_rule

    observed_numbers: List[Tuple[dict, str]] = []
    appendix_counters: Dict[str, int] = {}

    for item in formula_meta:
        location = IssueLocation(
            section_id=item.get('section_id'),
            paragraph_index=item.get('paragraph_index'),
        )
        text = normalize_whitespace(str(item.get('text', '')))
        number = str(item.get('equation_number') or '').strip()
        raw_number = str(item.get('raw_equation_number') or '').strip()
        appendix_letter = str(item.get('appendix_letter') or '').strip().upper()
        next_text = normalize_whitespace(str(item.get('next_text', '')))

        if not item.get('is_standalone', False):
            issues.append(_build_issue(
                'formatting',
                'formula_not_standalone',
                'warning',
                _u('Формула должна быть вынесена в отдельную строку'),
                _u('Формула ') + f"'{text}' " + _u('выглядит встроенной в текст, а не отдельным формульным блоком.'),
                location,
                _build_standard_reference(standard_id, formula_rule),
                _u('Вынести формулу в отдельную строку.')
            ))

        if item.get('alignment') != 'center':
            issues.append(_build_issue(
                'formatting',
                'formula_not_centered',
                'info',
                _u('Формула должна быть выровнена по центру'),
                _u('Формула ') + f"'{text}' " + _u('имеет выравнивание ') + f"'{item.get('alignment')}'.",
                location,
                _build_standard_reference(standard_id, formula_rule),
                _u('Выровнять формулу по центру.')
            ))

        has_blank_above = bool(item.get('prev_blank'))
        has_blank_below = bool(item.get('next_blank')) or _starts_with_where(next_text)
        if not has_blank_above or not has_blank_below:
            issues.append(_build_issue(
                'formatting',
                'formula_missing_blank_lines',
                'info',
                _u('Около формулы должны быть свободные строки'),
                _u('Для формулы ') + f"'{text}' " + _u('не обнаружены свободные строки сверху или снизу.'),
                location,
                _build_standard_reference(standard_id, formula_rule),
                _u('Оставить пустую строку перед и после формулы.')
            ))

        if raw_number and not number:
            issues.append(_build_issue(
                'formatting',
                'formula_number_format_error',
                'warning',
                _u('Номер формулы оформлен неверно'),
                _u('У формулы ') + f"'{text}' " + _u('номер указан как ') + f"'{raw_number}', " + _u('но должен быть в круглых скобках.'),
                location,
                _build_standard_reference(standard_id, numbering_rule),
                _u('Оформить номер в виде (1), (3.1) или (А.1).')
            ))
        elif not number:
            issues.append(_build_issue(
                'formatting',
                'missing_formula_number',
                'warning',
                _u('У формулы отсутствует номер'),
                _u('Формула ') + f"'{text}' " + _u('не имеет номера в круглых скобках.'),
                location,
                _build_standard_reference(standard_id, numbering_rule),
                _u('Пронумеровать формулу в формате (1), (3.1) или (А.1).')
            ))
        else:
            observed_numbers.append((item, number))
            if appendix_letter:
                appendix_counters.setdefault(appendix_letter, 0)
                appendix_counters[appendix_letter] += 1
                expected_appendix_number = f'{appendix_letter}.{appendix_counters[appendix_letter]}'
                if number != expected_appendix_number:
                    issues.append(_build_issue(
                        'formatting',
                        'appendix_formula_numbering_error',
                        'warning',
                        _u('Нумерация формулы в приложении оформлена неверно'),
                        _u('В приложении ') + appendix_letter + _u(' обнаружена формула ') + f'({number}), ' + _u('ожидается ') + f'({expected_appendix_number}).',
                        location,
                        _build_standard_reference(standard_id, numbering_rule),
                        _u('Использовать номер в виде ') + f'({expected_appendix_number}).'
                    ))

            reference_status = _formula_reference_status(document, number, item.get('paragraph_index'))
            if reference_status == 'invalid':
                issues.append(_build_issue(
                    'formatting',
                    'invalid_formula_reference_format',
                    'info',
                    _u('Ссылка на формулу оформлена неверно'),
                    _u('До формулы ') + f'({number}) ' + _u('найдена ссылка на формулу, но не в формате "в формуле (n)".'),
                    location,
                    _build_standard_reference(standard_id, numbering_rule),
                    _u('Оформить ссылку в виде "в формуле (n)".')
                ))
            elif reference_status == 'missing':
                issues.append(_build_issue(
                    'formatting',
                    'missing_formula_reference',
                    'info',
                    _u('На формулу отсутствует ссылка в тексте'),
                    _u('До формулы ') + f'({number}) ' + _u('не найдена ссылка в тексте.'),
                    location,
                    _build_standard_reference(standard_id, numbering_rule),
                    _u('Добавить в тексте ссылку на формулу в виде "в формуле (n)".')
                ))

        if next_text.startswith(_u('где:')):
            issues.append(_build_issue(
                'formatting',
                'formula_where_colon',
                'info',
                _u('Пояснение к формуле начинается неверно'),
                _u('Первая строка пояснения к формуле начинается со слова "где:".'),
                location,
                _build_standard_reference(standard_id, explanation_rule),
                _u('Использовать слово "где" без двоеточия.')
            ))
        elif _looks_like_formula_explanation(next_text) and not _starts_with_where(next_text):
            issues.append(_build_issue(
                'formatting',
                'formula_explanation_format_error',
                'warning',
                _u('Пояснения к формуле оформлены некорректно'),
                _u('После формулы идет строка ') + f"'{next_text}', " + _u('но пояснение должно начинаться со слова "где".'),
                location,
                _build_standard_reference(standard_id, explanation_rule),
                _u('Начать пояснение со слова "где" и перечислить обозначения с новой строки.')
            ))

        if _has_formula_break_issue(text, next_text):
            issues.append(_build_issue(
                'formatting',
                'formula_break_invalid',
                'warning',
                _u('Перенос многострочной формулы оформлен некорректно'),
                _u('Формула ') + f"'{text}' " + _u('и ее продолжение ') + f"'{next_text}' " + _u('выглядят как неправильный перенос.'),
                location,
                _build_standard_reference(standard_id, formula_rule),
                _u('Переносить формулу после математического знака с повторением знака в следующей строке.')
            ))

    issues.extend(_check_formula_numbering_sequence(observed_numbers, standard_id, numbering_rule))
    return issues


def _check_formula_numbering_sequence(observed_numbers: List[Tuple[dict, str]], standard_id: str, numbering_rule: Optional[StandardRule]) -> List[Issue]:
    simple_numbers = [(item, number) for item, number in observed_numbers if re.fullmatch(r'\d+', number)]
    if len(simple_numbers) < 2:
        return []

    issues: List[Issue] = []
    expected = 1
    seen = set()
    for item, number in simple_numbers:
        location = IssueLocation(section_id=item.get('section_id'), paragraph_index=item.get('paragraph_index'))
        if number in seen:
            issues.append(_build_issue(
                'formatting',
                'formula_numbering_error',
                'warning',
                _u('Нарушена нумерация формул'),
                _u('Номер формулы ') + f'({number}) ' + _u('повторяется в документе.'),
                location,
                _build_standard_reference(standard_id, numbering_rule),
                _u('Восстановить последовательную нумерацию формул.')
            ))
            continue
        seen.add(number)
        if int(number) != expected:
            issues.append(_build_issue(
                'formatting',
                'formula_numbering_error',
                'warning',
                _u('Нарушена нумерация формул'),
                _u('Обнаружена формула ') + f'({number}), ' + _u('хотя ожидалась формула ') + f'({expected}).',
                location,
                _build_standard_reference(standard_id, numbering_rule),
                _u('Восстановить последовательную нумерацию формул.')
            ))
            expected = int(number) + 1
        else:
            expected += 1
    return issues


def _formula_reference_status(document: DocumentInput, number: str, formula_paragraph_index: Optional[int]) -> str:
    candidates = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph.position.paragraph_index is not None
        and (formula_paragraph_index is None or paragraph.position.paragraph_index < formula_paragraph_index)
    ]
    haystack = normalize_whitespace(' '.join(paragraph.text for paragraph in candidates)).lower()
    if not haystack:
        return 'missing'

    proper_patterns = [
        re.compile(rf'\b(?:\u0432|\u043f\u043e)?\s*\u0444\u043e\u0440\u043c\u0443\u043b(?:\u0435|\u044b|\u0443)?\s*\({re.escape(number)}\)', re.IGNORECASE),
        re.compile(rf'\bformula\s*\({re.escape(number)}\)', re.IGNORECASE),
    ]
    if any(pattern.search(haystack) for pattern in proper_patterns):
        return 'ok'

    invalid_patterns = [
        re.compile(rf'\b(?:\u0432|\u043f\u043e)?\s*\u0444\u043e\u0440\u043c\u0443\u043b(?:\u0435|\u044b|\u0443)?\s+{re.escape(number)}\b', re.IGNORECASE),
        re.compile(rf'\bformula\s+{re.escape(number)}\b', re.IGNORECASE),
    ]
    if any(pattern.search(haystack) for pattern in invalid_patterns):
        return 'invalid'
    return 'missing'


def _starts_with_where(text: str) -> bool:
    normalized = normalize_whitespace(str(text or '')).lower()
    return normalized.startswith('где')


def _looks_like_formula_explanation(text: str) -> bool:
    normalized = normalize_whitespace(str(text or ''))
    if not normalized:
        return False
    if normalized.lower().startswith(_u('где')):
        return True
    return bool(re.match(r'^[A-Za-z?-??-?][A-Za-z?-??-?0-9_]*\s*[??-]\s*.+$', normalized))


def _has_formula_break_issue(text: str, next_text: str) -> bool:
    normalized = normalize_whitespace(text)
    continuation = normalize_whitespace(next_text)
    if not normalized or not continuation:
        return False
    if continuation.lower().startswith(_u('где')):
        return False
    trailing_match = re.search(r'([=+\-*/])\s*$', normalized)
    if not trailing_match:
        return False
    sign = trailing_match.group(1)
    return not continuation.startswith(sign)


def _check_front_matter_and_layout(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    issues: List[Issue] = []
    title_rule = _pick_rule(parsed_standard.rules, object_type='title_page', constraint_type='required_presence')
    contents_rule = _pick_rule(parsed_standard.rules, object_type='contents', constraint_type='required_presence')
    paragraph_meta = document.meta.extras.get('docx_paragraphs', []) if document.meta.extras else []
    paragraph_meta = paragraph_meta + (document.meta.extras.get('docx_table_paragraphs', []) if document.meta.extras else [])
    if not _has_contents_block(document, paragraph_meta):
        issues.append(
            _build_issue(
                'formatting',
                'missing_contents_section',
                'warning',
                _u('Отсутствует оглавление или содержание'),
                _u("В первых частях документа не найден блок с заголовком 'Оглавление' или 'Содержание'."),
                _fallback_document_location(document),
                _build_standard_reference(standard_id, contents_rule),
                _u('Добавить оглавление (содержание).'),
            )
        )
    if paragraph_meta and not _looks_like_title_page(paragraph_meta):
        issues.append(
            _build_issue(
                'formatting',
                'missing_title_page',
                'warning',
                _u('Не обнаружен титульный лист'),
                _u('В первом блоке документа не найдены признаки титульного листа.'),
                IssueLocation(page=1),
                _build_standard_reference(standard_id, title_rule),
                _u('Добавить титульный лист.'),
            )
        )
    elif paragraph_meta:
        body_lines = [item for item in paragraph_meta if len(item['text']) >= 80 and item.get('alignment') not in {'center', 'right'}]
        formatting_rule = _pick_rule(parsed_standard.rules, object_type='title_page', constraint_type='formatting')
        if body_lines and sum(1 for item in body_lines if item.get('alignment') != 'justify') >= max(3, len(body_lines) // 2):
            issues.append(
                _build_issue(
                    'formatting',
                    'body_text_not_justified',
                    'info',
                    _u('Основной текст визуально не выровнен по ширине'),
                    _u('Заметная часть длинных абзацев не имеет выравнивания по ширине.'),
                    IssueLocation(page=1),
                    _build_standard_reference(standard_id, formatting_rule),
                    _u('Выровнять текст по ширине'),
                )
            )
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


def _check_page_numbering(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    numbering_meta = document.meta.extras.get('docx_page_numbering', []) if document.meta.extras else []
    if not numbering_meta:
        return []

    formatting_rule = _pick_rule(parsed_standard.rules, object_type='report', constraint_type='formatting')
    if formatting_rule is None:
        formatting_rule = _pick_rule(parsed_standard.rules, object_type='report')

    issues: List[Issue] = []
    if not any(item.get('default_footer_has_page_field') for item in numbering_meta):
        issues.append(
            _build_issue(
                'formatting',
                'missing_page_numbering',
                'warning',
                _u('В документе отсутствует автоматическая нумерация страниц'),
                _u('В нижнем колонтитуле не найдено поле нумерации PAGE.'),
                IssueLocation(page=1),
                _build_standard_reference(standard_id, formatting_rule),
                _u('Добавить нумерацию страниц в нижний колонтитул по центру.'),
            )
        )
        return issues

    not_centered_sections = [
        item.get('section_index')
        for item in numbering_meta
        if item.get('default_footer_has_page_field') and item.get('default_footer_alignment') != 'center'
    ]
    if not_centered_sections:
        issues.append(
            _build_issue(
                'formatting',
                'page_number_not_centered',
                'warning',
                _u('Номер страницы должен стоять по центру внизу страницы'),
                _u('Выравнивание номера не по центру в секциях: ') + ', '.join(str(value) for value in not_centered_sections) + '.',
                IssueLocation(page=1),
                _build_standard_reference(standard_id, formatting_rule),
                _u('Выровнять номер страницы по центру нижнего колонтитула.'),
            )
        )

    sections_with_header_numbers = [
        item.get('section_index')
        for item in numbering_meta
        if item.get('default_header_has_page_field') or item.get('first_header_has_page_field') or item.get('even_header_has_page_field')
    ]
    if sections_with_header_numbers:
        issues.append(
            _build_issue(
                'formatting',
                'page_number_in_header',
                'warning',
                _u('Номер страницы не должен стоять в верхнем колонтитуле'),
                _u('Поле PAGE обнаружено в верхнем колонтитуле секций: ') + ', '.join(str(value) for value in sections_with_header_numbers) + '.',
                IssueLocation(page=1),
                _build_standard_reference(standard_id, formatting_rule),
                _u('Убрать номер из верхнего колонтитула и оставить его только в нижнем колонтитуле.'),
            )
        )

    first_section = numbering_meta[0]
    title_page_visible = False
    if first_section.get('first_footer_has_page_field') or first_section.get('first_header_has_page_field'):
        title_page_visible = True
    elif (first_section.get('default_footer_has_page_field') or first_section.get('default_header_has_page_field')) and not first_section.get('different_first_page'):
        title_page_visible = True
    if title_page_visible:
        issues.append(
            _build_issue(
                'formatting',
                'title_page_number_visible',
                'warning',
                _u('На титульном листе виден номер страницы'),
                _u('В первой секции номер страницы видим на титуле.'),
                IssueLocation(page=1),
                _build_standard_reference(standard_id, formatting_rule),
                _u('Убрать номер с титульной страницы, но оставить ее в общей нумерации.'),
            )
        )

    restarted_sections = [
        item.get('section_index')
        for item in numbering_meta[1:]
        if item.get('page_number_start') not in (None, 0)
    ]
    if restarted_sections:
        issues.append(
            _build_issue(
                'formatting',
                'page_numbering_restart',
                'warning',
                _u('Сквозная нумерация страниц не должна начинаться заново'),
                _u('Перезапуск нумерации найден в секциях: ') + ', '.join(str(value) for value in restarted_sections) + '.',
                IssueLocation(page=1),
                _build_standard_reference(standard_id, formatting_rule),
                _u('Убрать перезапуск нумерации и оставить единую сквозную нумерацию.'),
            )
        )

    return issues

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


def _check_enumerations(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    paragraph_meta = document.meta.extras.get('docx_paragraphs', []) if document.meta.extras else []
    if not paragraph_meta:
        return []

    formatting_rule = _pick_rule(parsed_standard.rules, object_type='report', constraint_type='formatting')
    section_heading_indexes = {
        payload.get('paragraph_index')
        for payload in (document.meta.extras.get('section_headings', {}) or {}).values()
        if payload.get('paragraph_index') is not None
    }
    issues: List[Issue] = []
    for item in paragraph_meta:
        text_value = normalize_whitespace(str(item.get('text', '')))
        if not text_value:
            continue
        paragraph_index = item.get('paragraph_index')
        if paragraph_index in section_heading_indexes:
            continue
        if _looks_like_invalid_enumeration_marker(text_value):
            issues.append(
                _build_issue(
                    'formatting',
                    'invalid_enumeration_marker',
                    'warning',
                    _u('Маркер перечисления оформлен не по ГОСТу'),
                    _u('Обнаружен некорректный маркер перечисления: ') + text_value + '.',
                    IssueLocation(paragraph_index=paragraph_index),
                    _build_standard_reference(standard_id, formatting_rule),
                    _u('Использовать тире, букву со скобкой или цифру со скобкой по правилам ГОСТа.'),
                )
            )
        elif _looks_like_enumeration_item(text_value):
            indent = item.get('first_line_indent_mm')
            if indent is not None and abs(float(indent) - 12.5) > 1.5:
                issues.append(
                    _build_issue(
                        'formatting',
                        'enumeration_indent_invalid',
                        'info',
                        _u('Элемент перечисления должен иметь абзацный отступ'),
                        _u('У элемента перечисления найден отступ ') + f'{float(indent):.1f} ' + _u('мм.'),
                        IssueLocation(paragraph_index=paragraph_index),
                        _build_standard_reference(standard_id, formatting_rule),
                        _u('Установить абзацный отступ 1,25 см для элемента перечисления.'),
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


def _looks_like_invalid_enumeration_marker(text: str) -> bool:
    normalized = normalize_whitespace(text)
    if _looks_like_heading_like_numbered_line(normalized):
        return False
    return bool(re.match(r'^(?:[????]|\d+\.|[A-Za-z?-??-???]\.)\s+', normalized))


def _looks_like_enumeration_item(text: str) -> bool:
    normalized = normalize_whitespace(text)
    if _looks_like_heading_like_numbered_line(normalized):
        return False
    return bool(re.match(r'^(?:[-??]|\d+\)|[?-??]\))\s+', normalized, re.IGNORECASE))


def _looks_like_heading_like_numbered_line(text: str) -> bool:
    normalized = normalize_whitespace(text)
    return bool(re.match(r'^\d+(?:\.\d+)*\.?\s+[?-??A-Z].+$', normalized))


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
        normalized_title = title.lower()
        is_appendix = normalized_title.startswith(APPENDIX_WORD.lower())
        is_structural = normalized_title in CENTERED_STRUCTURAL_TITLES

        if not title:
            issues.append(_build_issue('formatting', 'empty_section_heading', 'warning', _u("У раздела отсутствует заголовок"), _u("Не заполнен заголовок раздела."), location, _build_standard_reference(standard_id, heading_rule), _u("Заполнить заголовок")))
            continue
        if title.endswith('.'):
            issues.append(_build_issue('formatting', 'heading_trailing_period', 'info', _u("Заголовок раздела заканчивается точкой"), _u("Заголовок '") + title + _u("' заканчивается точкой."), location, _build_standard_reference(standard_id, punctuation_rule or heading_rule), _u("Убрать точку")))

        if is_appendix:
            if meta and meta.get('alignment') != 'center':
                issues.append(_build_issue('formatting', 'appendix_heading_not_centered', 'info', _u("Заголовок приложения выровнен не по центру"), _u("Заголовок приложения '") + title + _u("' не выровнен по центру."), location, _build_standard_reference(standard_id, heading_rule), _u("Выровнять заголовок приложения по центру")))
            appendix_match = re.match(rf'^{re.escape(APPENDIX_WORD)}\s+([\u0410-\u042fA-Z])(?:\s*[—–-]\s*(.+)|\s+(.+))?$', title, re.IGNORECASE)
            appendix_tail = normalize_whitespace((appendix_match.group(2) or appendix_match.group(3) or '') if appendix_match else '')
            if appendix_tail:
                issues.append(_build_issue('formatting', 'appendix_heading_single_line', 'warning', _u("Заголовок приложения оформлен в одной строке"), _u("Для приложения строка 'ПРИЛОЖЕНИЕ А' и заголовок должны быть на разных строках."), location, _build_standard_reference(standard_id, heading_rule), _u("Вынести 'ПРИЛОЖЕНИЕ А' и заголовок приложения на отдельные строки")))
            continue

        if is_structural:
            if normalize_whitespace(section.number):
                issues.append(_build_issue('formatting', 'structural_heading_numbered', 'warning', _u("Структурный элемент не должен иметь номер"), _u("Структурный элемент '") + title + _u("' ошибочно имеет номер '") + normalize_whitespace(section.number) + _u("'."), location, _build_standard_reference(standard_id, heading_rule), _u("Убрать номер у структурного элемента")))
            if title != title.upper():
                issues.append(_build_issue('formatting', 'structural_heading_not_uppercase', 'info', _u("Структурный заголовок должен быть прописным"), _u("Заголовок '") + title + _u("' должен быть написан прописными буквами."), location, _build_standard_reference(standard_id, heading_rule), _u("Привести заголовок к верхнему регистру")))
            if meta:
                if meta.get('alignment') != 'center':
                    issues.append(_build_issue('formatting', 'structural_heading_not_centered', 'info', _u("Структурный заголовок не по центру"), _u("Заголовок '") + title + _u("' должен быть расположен по центру."), location, _build_standard_reference(standard_id, heading_rule), _u("Расположить заголовок по центру")))
                indent = meta.get('first_line_indent_mm')
                if indent is not None and abs(float(indent)) > 0.5:
                    issues.append(_build_issue('formatting', 'structural_heading_has_indent', 'info', _u("У структурного заголовка есть абзацный отступ"), _u("Структурный заголовок '") + title + _u("' не должен иметь абзацного отступа."), location, _build_standard_reference(standard_id, heading_rule), _u("Убрать абзацный отступ")))
                if meta.get('has_non_black_text'):
                    issues.append(_build_issue('formatting', 'structural_heading_invalid_font_color', 'info', _u("Структурный заголовок должен быть черного цвета"), _u("Заголовок '") + title + _u("' оформлен не черным цветом."), location, _build_standard_reference(standard_id, heading_rule), _u("Сделать заголовок черным")))
            continue

        if meta:
            if meta.get('alignment') == 'center':
                issues.append(_build_issue('formatting', 'main_heading_centered', 'info', _u("Заголовок раздела основной части не должен быть по центру"), _u("Заголовок '") + _format_heading_for_display(section) + _u("' должен начинаться с абзацного отступа, а не располагаться по центру."), location, _build_standard_reference(standard_id, heading_rule), _u("Выровнять заголовок по левому краю с абзацного отступа")))
            indent = meta.get('first_line_indent_mm')
            if indent is None or abs(float(indent) - 12.5) > 1.5:
                issues.append(_build_issue('formatting', 'main_heading_indent_invalid', 'info', _u("Абзацный отступ заголовка раздела некорректен"), _u("Заголовок '") + _format_heading_for_display(section) + _u("' должен иметь абзацный отступ 1,25 см."), location, _build_standard_reference(standard_id, heading_rule), _u("Установить абзацный отступ 1,25 см")))
            if meta.get('has_non_black_text'):
                issues.append(_build_issue('formatting', 'heading_invalid_font_color', 'info', _u("Заголовок раздела должен быть черного цвета"), _u("Заголовок '") + _format_heading_for_display(section) + _u("' оформлен не черным цветом."), location, _build_standard_reference(standard_id, heading_rule), _u("Сделать заголовок черным")))
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
            if normalize_whitespace(section.title).lower() in CENTERED_STRUCTURAL_TITLES:
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
