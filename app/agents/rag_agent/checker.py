import re
from pathlib import Path
from typing import Iterable, List, Optional

from app.schemas.agent_result import AgentResult
from app.schemas.document import DocumentInput, Section
from app.schemas.issue import Issue, IssueLocation, StandardReference
from app.schemas.standard import ParsedStandard, StandardRule
from app.standards.storage import standard_parsed_path_for
from app.utils.ids import make_id
from app.utils.text import normalize_whitespace

FIGURE_CAPTION_PATTERN = re.compile(r"^Рисунок\s+[A-Za-zА-Яа-я0-9.]+\s*-\s*.+$")
TABLE_CAPTION_PATTERN = re.compile(r"^Таблица\s+[A-Za-zА-Яа-я0-9.]+\s*-\s*.+$")
APPENDIX_TITLE_PATTERN = re.compile(r"^Приложение\s+[А-ЯA-Z](?:\s*[-–]\s*.+)?$")
REFERENCE_SECTION_HINTS = [
    "список использованных источников",
    "список литературы",
    "библиограф",
]
UNNUMBERED_SECTION_TITLES = {
    "введение",
    "заключение",
    "содержание",
    "реферат",
    "список использованных источников",
    "список литературы",
}


def analyze_document_against_standard(document: DocumentInput, standard_id: str) -> AgentResult:
    parsed_standard = _load_parsed_standard(standard_id)
    issues: List[Issue] = []
    issues.extend(_check_figures(document, parsed_standard, standard_id))
    issues.extend(_check_tables(document, parsed_standard, standard_id))
    issues.extend(_check_references_section(document, parsed_standard, standard_id))
    issues.extend(_check_headings(document, parsed_standard, standard_id))
    issues.extend(_check_section_numbering(document, parsed_standard, standard_id))
    issues.extend(_check_appendix_sections(document, parsed_standard, standard_id))
    return AgentResult(agent="rag_agent", issues=issues)


def _check_figures(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    issues: List[Issue] = []
    caption_rule = _pick_rule(parsed_standard.rules, object_type="figure", constraint_type="caption_required")
    reference_rule = _pick_rule(parsed_standard.rules, object_type="figure", constraint_type="reference_required")

    for figure in document.figures:
        caption = normalize_whitespace(figure.caption)
        if not caption:
            issues.append(
                _build_issue(
                    issue_type="formatting",
                    subtype="missing_figure_caption",
                    severity="warning",
                    message="У рисунка отсутствует подпись",
                    evidence=f"Рисунок {figure.id} не содержит подпись в формате 'Рисунок N - Наименование'.",
                    location=IssueLocation(page=figure.position.page),
                    standard_reference=_build_standard_reference(standard_id, caption_rule),
                    suggestion="Добавить подпись вида: Рисунок 1 - Наименование рисунка",
                )
            )
            continue

        if not FIGURE_CAPTION_PATTERN.match(caption):
            issues.append(
                _build_issue(
                    issue_type="formatting",
                    subtype="invalid_figure_caption_format",
                    severity="warning",
                    message="Подпись рисунка оформлена не по ГОСТу",
                    evidence=f"Обнаружена подпись: '{caption}'. Ожидается формат 'Рисунок N - Наименование'.",
                    location=IssueLocation(page=figure.position.page),
                    standard_reference=_build_standard_reference(standard_id, caption_rule),
                    suggestion="Привести подпись к формату: Рисунок N - Наименование рисунка",
                )
            )

        if reference_rule and not _document_has_reference(document, ["рисунок", caption]):
            issues.append(
                _build_issue(
                    issue_type="formatting",
                    subtype="missing_figure_reference",
                    severity="info",
                    message="На рисунок может отсутствовать ссылка в тексте",
                    evidence=f"Не найдено упоминание рисунка '{caption}' в тексте документа.",
                    location=IssueLocation(page=figure.position.page),
                    standard_reference=_build_standard_reference(standard_id, reference_rule),
                    suggestion="Добавить в текст ссылку на рисунок до или сразу после его размещения",
                )
            )
    return issues


def _check_tables(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    issues: List[Issue] = []
    caption_rule = _pick_rule(parsed_standard.rules, object_type="table", constraint_type="caption_required")
    reference_rule = _pick_rule(parsed_standard.rules, object_type="table", constraint_type="reference_required")

    for table in document.tables:
        caption = normalize_whitespace(table.caption)
        if not caption:
            issues.append(
                _build_issue(
                    issue_type="formatting",
                    subtype="missing_table_caption",
                    severity="warning",
                    message="У таблицы отсутствует наименование",
                    evidence=f"Таблица {table.id} не содержит строку вида 'Таблица N - Наименование таблицы'.",
                    location=IssueLocation(page=table.position.page),
                    standard_reference=_build_standard_reference(standard_id, caption_rule),
                    suggestion="Добавить наименование таблицы в формате: Таблица 1 - Наименование таблицы",
                )
            )
            continue

        if not TABLE_CAPTION_PATTERN.match(caption):
            issues.append(
                _build_issue(
                    issue_type="formatting",
                    subtype="invalid_table_caption_format",
                    severity="warning",
                    message="Наименование таблицы оформлено не по ГОСТу",
                    evidence=f"Обнаружено наименование: '{caption}'. Ожидается формат 'Таблица N - Наименование таблицы'.",
                    location=IssueLocation(page=table.position.page),
                    standard_reference=_build_standard_reference(standard_id, caption_rule),
                    suggestion="Привести заголовок таблицы к формату: Таблица N - Наименование таблицы",
                )
            )

        if reference_rule and not _document_has_reference(document, ["таблица", caption]):
            issues.append(
                _build_issue(
                    issue_type="formatting",
                    subtype="missing_table_reference",
                    severity="info",
                    message="На таблицу может отсутствовать ссылка в тексте",
                    evidence=f"Не найдено упоминание таблицы '{caption}' в тексте документа.",
                    location=IssueLocation(page=table.position.page),
                    standard_reference=_build_standard_reference(standard_id, reference_rule),
                    suggestion="Добавить в текст ссылку на таблицу до или рядом с ее размещением",
                )
            )
    return issues


def _check_references_section(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    reference_rule = _pick_rule(parsed_standard.rules, object_type="references", constraint_type="required_presence")
    formatting_rule = _pick_rule(parsed_standard.rules, object_type="references", constraint_type="formatting")

    reference_section = _find_reference_section(document.sections)
    if reference_section is None:
        return [
            _build_issue(
                issue_type="formatting",
                subtype="missing_references_section",
                severity="warning",
                message="В документе отсутствует список использованных источников",
                evidence="Не найден раздел с названием, связанным со списком использованных источников.",
                location=_fallback_document_location(document),
                standard_reference=_build_standard_reference(standard_id, reference_rule),
                suggestion="Добавить раздел 'Список использованных источников' в структуру документа",
            )
        ]

    section_text = normalize_whitespace(reference_section.text)
    if len(section_text) < 20:
        return [
            _build_issue(
                issue_type="formatting",
                subtype="empty_references_section",
                severity="warning",
                message="Раздел со списком источников найден, но выглядит пустым",
                evidence=f"Раздел '{reference_section.title}' не содержит оформленного списка источников.",
                location=IssueLocation(section_id=reference_section.id),
                standard_reference=_build_standard_reference(standard_id, formatting_rule or reference_rule),
                suggestion="Заполнить раздел библиографическими описаниями использованных источников",
            )
        ]

    return []


def _check_headings(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    issues: List[Issue] = []
    heading_rule = _pick_rule(parsed_standard.rules, object_type="heading", constraint_type="optional_allowed")
    punctuation_rule = _pick_rule(parsed_standard.rules, object_type="heading", constraint_type="generic")

    for section in document.sections:
        title = normalize_whitespace(section.title)
        if not title:
            issues.append(
                _build_issue(
                    issue_type="formatting",
                    subtype="empty_section_heading",
                    severity="warning",
                    message="У раздела отсутствует заголовок",
                    evidence=f"У раздела с номером '{section.number}' не заполнен заголовок.",
                    location=IssueLocation(section_id=section.id),
                    standard_reference=_build_standard_reference(standard_id, heading_rule),
                    suggestion="Заполнить краткий и понятный заголовок раздела",
                )
            )
            continue

        if title.endswith('.'):
            issues.append(
                _build_issue(
                    issue_type="formatting",
                    subtype="heading_trailing_period",
                    severity="info",
                    message="Заголовок раздела заканчивается точкой",
                    evidence=f"Заголовок '{title}' заканчивается точкой.",
                    location=IssueLocation(section_id=section.id),
                    standard_reference=_build_standard_reference(standard_id, punctuation_rule or heading_rule),
                    suggestion="Убрать точку в конце заголовка раздела",
                )
            )
    return issues


def _check_section_numbering(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    issues: List[Issue] = []
    numbering_rule = _pick_rule(parsed_standard.rules, object_type="section", constraint_type="numbering")
    level_groups = {}
    for section in document.sections:
        level_groups.setdefault(section.level, []).append(section)

    for level_sections in level_groups.values():
        numbered_count = sum(1 for section in level_sections if normalize_whitespace(section.number))
        if numbered_count < 2:
            continue
        for section in level_sections:
            title = normalize_whitespace(section.title).lower()
            if title in UNNUMBERED_SECTION_TITLES:
                continue
            if not normalize_whitespace(section.number):
                issues.append(
                    _build_issue(
                        issue_type="formatting",
                        subtype="missing_section_number",
                        severity="warning",
                        message="У раздела отсутствует номер",
                        evidence=f"Раздел '{section.title}' расположен среди нумеруемых разделов, но не имеет номера.",
                        location=IssueLocation(section_id=section.id),
                        standard_reference=_build_standard_reference(standard_id, numbering_rule),
                        suggestion="Присвоить разделу номер в соответствии с иерархией документа",
                    )
                )
    return issues


def _check_appendix_sections(document: DocumentInput, parsed_standard: ParsedStandard, standard_id: str) -> List[Issue]:
    issues: List[Issue] = []
    appendix_format_rule = _pick_rule(parsed_standard.rules, object_type="appendix", constraint_type="formatting")
    appendix_reference_rule = _pick_rule(parsed_standard.rules, object_type="appendix", constraint_type="reference_required")

    appendix_sections = [section for section in document.sections if "прилож" in normalize_whitespace(section.title).lower()]
    for section in appendix_sections:
        title = normalize_whitespace(section.title)
        if not APPENDIX_TITLE_PATTERN.match(title):
            issues.append(
                _build_issue(
                    issue_type="formatting",
                    subtype="invalid_appendix_heading",
                    severity="warning",
                    message="Заголовок приложения оформлен не по ГОСТу",
                    evidence=f"Обнаружен заголовок приложения '{title}'. Ожидается формат 'Приложение А' или 'Приложение А - ...'.",
                    location=IssueLocation(section_id=section.id),
                    standard_reference=_build_standard_reference(standard_id, appendix_format_rule),
                    suggestion="Привести заголовок приложения к формату: Приложение А - Наименование",
                )
            )

        if appendix_reference_rule and not _document_has_reference(document, [title, "приложение"]):
            issues.append(
                _build_issue(
                    issue_type="formatting",
                    subtype="missing_appendix_reference",
                    severity="info",
                    message="На приложение может отсутствовать ссылка в тексте",
                    evidence=f"Не найдено явное упоминание приложения '{title}' в основном тексте документа.",
                    location=IssueLocation(section_id=section.id),
                    standard_reference=_build_standard_reference(standard_id, appendix_reference_rule),
                    suggestion="Добавить в основной текст ссылку на приложение",
                )
            )
    return issues


def _load_parsed_standard(standard_id: str) -> ParsedStandard:
    path = Path(standard_parsed_path_for(standard_id))
    if not path.exists():
        raise FileNotFoundError(f"Parsed standard not found for {standard_id}: {path}")
    return ParsedStandard.model_validate_json(path.read_text(encoding="utf-8"))


def _pick_rule(
    rules: Iterable[StandardRule],
    *,
    object_type: Optional[str] = None,
    constraint_type: Optional[str] = None,
) -> Optional[StandardRule]:
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
    parts = []
    for part in number.split('.'):
        digits = ''.join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return parts


def _build_standard_reference(standard_id: str, rule: Optional[StandardRule]) -> StandardReference:
    if rule is None:
        return StandardReference(source=_format_standard_name(standard_id), rule_id="", quote="")
    quote_source = normalize_whitespace(rule.content or rule.title)
    return StandardReference(
        source=_format_standard_name(standard_id),
        rule_id=rule.id,
        quote=quote_source[:280],
    )


def _format_standard_name(standard_id: str) -> str:
    if standard_id.lower() == "gost_7_32_2017":
        return "ГОСТ 7.32-2017"
    return standard_id.replace('_', ' ').upper()


def _build_issue(
    *,
    issue_type: str,
    subtype: str,
    severity: str,
    message: str,
    evidence: str,
    location: IssueLocation,
    standard_reference: StandardReference,
    suggestion: Optional[str],
) -> Issue:
    return Issue(
        id=make_id("issue_rag"),
        type=issue_type,
        subtype=subtype,
        severity=severity,
        message=message,
        location=location,
        evidence=evidence,
        standard_reference=standard_reference,
        suggestion=suggestion,
        agent="rag_agent",
    )


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


def _document_has_reference(document: DocumentInput, fragments: List[str]) -> bool:
    paragraph_text = " ".join(paragraph.text for paragraph in document.paragraphs)
    section_text = " ".join(section.text for section in document.sections)
    haystack = normalize_whitespace(f"{paragraph_text} {section_text}").lower()
    normalized_fragments = [normalize_whitespace(fragment).lower() for fragment in fragments if fragment]
    for fragment in normalized_fragments:
        if len(fragment) >= 8 and fragment in haystack:
            return True
    generic_tokens = ["рисунок", "таблица", "приложение"]
    return any(token in haystack for token in generic_tokens if any(token in fragment for fragment in normalized_fragments))
