from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

from app.schemas.document import DocumentInput
from app.schemas.issue import Issue, IssueLocation, StandardReference


STRUCTURE_RULES = {
    "numbering_error": StandardReference(
        source="ГОСТ 7.32-2017",
        rule_id="structure_rule_numbering",
        quote="Разделы и подразделы должны иметь последовательную нумерацию.",
    ),
    "hierarchy_error": StandardReference(
        source="ГОСТ 7.32-2017",
        rule_id="structure_rule_hierarchy",
        quote="Подразделы должны входить в соответствующие разделы и отражать корректную иерархию документа.",
    ),
    "order_error": StandardReference(
        source="ГОСТ 7.32-2017",
        rule_id="structure_rule_order",
        quote="Разделы документа должны следовать в логически корректном и установленном порядке.",
    ),
    "missing_required_section": StandardReference(
        source="ГОСТ 7.32-2017",
        rule_id="structure_rule_required_sections",
        quote="Отчет должен содержать обязательные структурные элементы, предусмотренные стандартом.",
    ),
    "unrecognized_structure": StandardReference(
        source="ГОСТ 7.32-2017",
        rule_id="structure_rule_recognition",
        quote="Документ должен иметь выделенную структуру с заголовками, разделами и подразделами.",
    ),
}

REQUIRED_SECTION_GROUPS = {
    "Введение": ["введение"],
    "Заключение": ["заключение", "выводы"],
    "Список использованных источников": [
        "список использованных источников",
        "список литературы",
        "библиографический список",
        "источники",
    ],
}

MANDATORY_ORDER = [
    "Введение",
    "Заключение",
    "Список использованных источников",
]


@dataclass(frozen=True)
class StructureEntry:
    section_id: str
    number: str
    title: str
    level: int
    number_parts: Tuple[int, ...]
    parent_number: Optional[str]
    index: int
    page: Optional[int]
    paragraph_id: Optional[str]


def build_structure_map(document: DocumentInput) -> List[dict]:
    return [asdict(entry) for entry in _build_structure_entries(document)]


def build_structure_summary(document: DocumentInput, issues: Optional[List[Issue]] = None) -> Dict[str, object]:
    entries = _build_structure_entries(document)
    normalized_titles = _collect_normalized_required_titles(document, entries)
    missing_sections = [
        expected for expected, variants in REQUIRED_SECTION_GROUPS.items()
        if not any(any(variant in title for variant in variants) for title in normalized_titles)
    ]
    if issues is None:
        issues = run_structure_checks(document)

    return {
        "sections_found": [entry.title for entry in entries if entry.level == 1],
        "missing_sections": missing_sections,
        "critical_structure_error": any(issue.severity == "critical" for issue in issues),
        "structure_map": build_structure_map(document),
    }


def run_structure_checks(document: DocumentInput, standard_id: str = "") -> List[Issue]:
    entries = _build_structure_entries(document)
    if not entries:
        return [
            _make_issue(
                issue_id=1,
                subtype="unrecognized_structure",
                severity="critical",
                message="Не удалось распознать структуру документа",
                evidence="В документе не выделены заголовки и разделы.",
                suggestion="Добавить заголовки разделов и привести документ к иерархической структуре.",
            )
        ]

    issues: List[Issue] = []
    issue_id = 1

    for payload in _check_missing_numbers(entries):
        issues.append(_make_issue(issue_id=issue_id, **payload))
        issue_id += 1

    numbered_entries = [entry for entry in entries if entry.number_parts]
    if not numbered_entries:
        issues.append(
            _make_issue(
                issue_id=issue_id,
                subtype="unrecognized_structure",
                severity="critical",
                message="Не удалось распознать нумерованные разделы документа",
                evidence="В документе отсутствуют разделы с нумерацией вида 1, 1.1, 2.3.",
                suggestion="Добавить нумерацию разделов и подразделов в формате ГОСТ.",
            )
        )
        issue_id += 1
    else:
        for payload in _check_duplicate_numbers(numbered_entries):
            issues.append(_make_issue(issue_id=issue_id, **payload))
            issue_id += 1
        for payload in _check_parent_hierarchy(numbered_entries):
            issues.append(_make_issue(issue_id=issue_id, **payload))
            issue_id += 1
        for payload in _check_top_level_start(numbered_entries):
            issues.append(_make_issue(issue_id=issue_id, **payload))
            issue_id += 1
        for payload in _check_numbering_sequence(numbered_entries):
            issues.append(_make_issue(issue_id=issue_id, **payload))
            issue_id += 1
        for payload in _check_section_order(numbered_entries):
            issues.append(_make_issue(issue_id=issue_id, **payload))
            issue_id += 1

    for payload in _check_required_sections(document, entries):
        issues.append(_make_issue(issue_id=issue_id, **payload))
        issue_id += 1

    for payload in _check_required_section_order(entries):
        issues.append(_make_issue(issue_id=issue_id, **payload))
        issue_id += 1

    return _deduplicate_issues(issues)


def _build_structure_entries(document: DocumentInput) -> List[StructureEntry]:
    section_locations = _map_section_locations(document)
    entries: List[StructureEntry] = []

    for index, section in enumerate(document.sections):
        number_parts = _parse_number(section.number)
        parent_number = ".".join(str(part) for part in number_parts[:-1]) if len(number_parts) > 1 else None
        inferred_level = len(number_parts) if number_parts else section.level
        location = section_locations.get(section.id, {})
        entries.append(
            StructureEntry(
                section_id=section.id,
                number=section.number,
                title=section.title,
                level=inferred_level or section.level,
                number_parts=number_parts,
                parent_number=parent_number,
                index=index,
                page=location.get("page"),
                paragraph_id=location.get("paragraph_id"),
            )
        )

    return entries


def _map_section_locations(document: DocumentInput) -> Dict[str, Dict[str, Optional[object]]]:
    locations: Dict[str, Dict[str, Optional[object]]] = {}
    for paragraph in document.paragraphs:
        if paragraph.section_id and paragraph.section_id not in locations:
            locations[paragraph.section_id] = {
                "page": paragraph.position.page,
                "paragraph_id": paragraph.id,
            }
    return locations


def _parse_number(number: str) -> Tuple[int, ...]:
    if not number:
        return tuple()
    parts = number.split(".")
    if not all(part.isdigit() for part in parts):
        return tuple()
    return tuple(int(part) for part in parts)


def _check_missing_numbers(entries: List[StructureEntry]) -> List[dict]:
    issues: List[dict] = []
    has_numbered_top_level = any(entry.level == 1 and entry.number_parts for entry in entries)
    if not has_numbered_top_level:
        return issues

    for entry in entries:
        normalized_title = _normalize_title(entry.title)
        if entry.level != 1 or entry.number_parts or normalized_title.startswith("приложение"):
            continue
        issues.append({
            "subtype": "numbering_error",
            "severity": "critical",
            "message": "У раздела отсутствует обязательная нумерация",
            "location": _location_for(entry),
            "evidence": f"Раздел «{entry.title}» расположен среди нумерованных разделов, но не имеет номера.",
            "suggestion": f"Добавить номер для раздела «{entry.title}» в соответствии с общей структурой документа.",
        })
    return issues


def _check_duplicate_numbers(entries: List[StructureEntry]) -> List[dict]:
    issues: List[dict] = []
    seen: Dict[Tuple[int, ...], StructureEntry] = {}
    for entry in entries:
        previous = seen.get(entry.number_parts)
        if previous is not None:
            issues.append({
                "subtype": "numbering_error",
                "severity": "critical",
                "message": "Обнаружено дублирование номера раздела",
                "location": _location_for(entry),
                "evidence": f"Номер раздела {entry.number} уже использован в разделе «{previous.title}».",
                "suggestion": f"Переименовать раздел «{entry.title}» и восстановить уникальность нумерации.",
            })
        else:
            seen[entry.number_parts] = entry
    return issues


def _check_top_level_start(entries: List[StructureEntry]) -> List[dict]:
    top_level_entries = [entry for entry in entries if len(entry.number_parts) == 1]
    if not top_level_entries:
        return []

    first_entry = top_level_entries[0]
    if first_entry.number_parts != (1,):
        return [{
            "subtype": "numbering_error",
            "severity": "critical",
            "message": "????????? ???????? ?????????? ?? ? ??????? ???????",
            "location": _location_for(first_entry),
            "evidence": f"?????? ???????????? ?????? ????????? ????? ????? {first_entry.number}, ????????? ?????? 1.",
            "suggestion": "?????? ????????? ???????? ???????? ? 1 ? ???????????? ?????????????????? ????????? ?????????.",
        }]

    return []


def _check_parent_hierarchy(entries: List[StructureEntry]) -> List[dict]:
    issues: List[dict] = []
    seen_numbers = set()

    for entry in entries:
        if entry.number_parts and len(entry.number_parts) != entry.level:
            issues.append({
                "subtype": "hierarchy_error",
                "severity": "critical",
                "message": "Нарушена вложенность разделов документа",
                "location": _location_for(entry),
                "evidence": f"Раздел {entry.number} имеет уровень {entry.level}, который не соответствует глубине нумерации.",
                "suggestion": f"Проверить уровень вложенности заголовка раздела {entry.number}.",
            })

        if len(entry.number_parts) > 1:
            parent = entry.number_parts[:-1]
            if parent not in seen_numbers:
                parent_number = ".".join(str(part) for part in parent)
                issues.append({
                    "subtype": "hierarchy_error",
                    "severity": "critical",
                    "message": "Подраздел расположен без родительского раздела",
                    "location": _location_for(entry),
                    "evidence": f"Обнаружен подраздел {entry.number}, но раздел {parent_number} перед ним отсутствует.",
                    "suggestion": f"Добавить родительский раздел {parent_number} или исправить нумерацию подраздела {entry.number}.",
                })

            if len(parent) >= 2 and parent not in seen_numbers:
                parent_number = ".".join(str(part) for part in parent)
                issues.append({
                    "subtype": "hierarchy_error",
                    "severity": "critical",
                    "message": "Обнаружен скачок уровня вложенности",
                    "location": _location_for(entry),
                    "evidence": f"Раздел {entry.number} использует вложенность глубины {len(entry.number_parts)}, но промежуточный уровень {parent_number} отсутствует.",
                    "suggestion": f"Добавить промежуточный раздел {parent_number} или понизить уровень вложенности заголовка {entry.number}.",
                })

        if entry.number_parts:
            seen_numbers.add(entry.number_parts)

    return issues


def _check_numbering_sequence(entries: List[StructureEntry]) -> List[dict]:
    issues: List[dict] = []
    last_seen_by_parent: Dict[Tuple[int, ...], int] = {}

    for entry in entries:
        parent = entry.number_parts[:-1]
        current = entry.number_parts[-1]
        previous = last_seen_by_parent.get(parent)

        if previous is None:
            if current != 1:
                expected = 1
                prefix = ".".join(str(p) for p in parent)
                expected_display = f"{prefix}.{expected}" if prefix else str(expected)
                issues.append({
                    "subtype": "numbering_error",
                    "severity": "critical",
                    "message": "Нарушена последовательность нумерации разделов",
                    "location": _location_for(entry),
                    "evidence": f"Раздел {entry.number} начинается с номера {current}, ожидается {expected_display}.",
                    "suggestion": f"Проверить нумерацию раздела {entry.number} и восстановить последовательность.",
                })
        elif current != previous + 1:
            expected_number = parent + (previous + 1,)
            issues.append({
                "subtype": "numbering_error",
                "severity": "critical",
                "message": "Нарушена последовательность нумерации разделов",
                "location": _location_for(entry),
                "evidence": f"После раздела {'.'.join(str(p) for p in parent + (previous,))} обнаружен раздел {entry.number}, отсутствует {'.'.join(str(p) for p in expected_number)}.",
                "suggestion": "Проверить нумерацию разделов и подразделов и восстановить пропущенные номера.",
            })

        last_seen_by_parent[parent] = current

    return issues


def _check_section_order(entries: List[StructureEntry]) -> List[dict]:
    issues: List[dict] = []
    previous: Optional[StructureEntry] = None

    for entry in entries:
        if previous is not None and not _is_valid_transition(previous.number_parts, entry.number_parts):
            issues.append({
                "subtype": "order_error",
                "severity": "critical",
                "message": "Нарушен порядок следования разделов",
                "location": _location_for(entry),
                "evidence": f"После раздела {previous.number} следует раздел {entry.number}, что нарушает ожидаемый порядок структуры.",
                "suggestion": f"Проверить расположение раздела {entry.number} и привести структуру документа к последовательному порядку.",
            })
        previous = entry

    return issues


def _check_required_sections(document: DocumentInput, entries: List[StructureEntry]) -> List[dict]:
    issues: List[dict] = []
    titles = _collect_normalized_required_titles(document, entries)

    for expected_title, variants in REQUIRED_SECTION_GROUPS.items():
        if not any(any(variant in title for variant in variants) for title in titles):
            issues.append({
                "subtype": "missing_required_section",
                "severity": "warning",
                "message": "Отсутствует обязательный раздел документа",
                "location": IssueLocation(),
                "evidence": f"В документе не найден раздел «{expected_title}».",
                "suggestion": f"Добавить обязательный раздел «{expected_title}» в структуру документа.",
            })

    return issues


def _check_required_section_order(entries: List[StructureEntry]) -> List[dict]:
    issues: List[dict] = []
    positions: Dict[str, StructureEntry] = {}
    top_level_entries = [entry for entry in entries if entry.level == 1]

    for expected_title, variants in REQUIRED_SECTION_GROUPS.items():
        for entry in top_level_entries:
            title = _normalize_title(entry.title)
            if any(variant in title for variant in variants):
                positions[expected_title] = entry
                break

    for previous_title, current_title in zip(MANDATORY_ORDER, MANDATORY_ORDER[1:]):
        previous_entry = positions.get(previous_title)
        current_entry = positions.get(current_title)
        if previous_entry and current_entry and previous_entry.index > current_entry.index:
            issues.append({
                "subtype": "order_error",
                "severity": "warning",
                "message": "Нарушен порядок обязательных разделов",
                "location": _location_for(previous_entry),
                "evidence": f"Раздел «{previous_entry.title}» расположен после раздела «{current_entry.title}», что нарушает ожидаемый порядок обязательных частей отчета.",
                "suggestion": f"Переместить раздел «{previous_entry.title}» перед разделом «{current_entry.title}».",
            })

    return issues


def _is_valid_transition(previous: Tuple[int, ...], current: Tuple[int, ...]) -> bool:
    if current == previous:
        return False

    if len(current) == len(previous) + 1 and current[:-1] == previous and current[-1] == 1:
        return True

    if len(current) == len(previous) and current[:-1] == previous[:-1] and current[-1] == previous[-1] + 1:
        return True

    for depth in range(len(previous) - 1, -1, -1):
        candidate = previous[:depth] + (previous[depth] + 1,)
        if current == candidate:
            return True

    return False


def _normalize_title(title: str) -> str:
    return " ".join(title.lower().replace("ё", "е").split())


def _location_for(entry: StructureEntry) -> IssueLocation:
    return IssueLocation(section_id=entry.section_id, paragraph_id=entry.paragraph_id, page=entry.page)


def _make_issue(
    *,
    issue_id: int,
    subtype: str,
    severity: str,
    message: str,
    evidence: str,
    suggestion,
    location: Optional[IssueLocation] = None,
) -> Issue:
    return Issue(
        id=f"issue_structure_{issue_id:03d}",
        type="structure",
        subtype=subtype,
        severity=severity,
        message=message,
        location=location or IssueLocation(),
        evidence=evidence,
        standard_reference=STRUCTURE_RULES[subtype],
        suggestion=suggestion,
        agent="structure_agent",
    )


def _deduplicate_issues(issues: List[Issue]) -> List[Issue]:
    unique: List[Issue] = []
    seen = set()
    for issue in issues:
        key = (
            issue.subtype,
            issue.location.section_id,
            issue.location.paragraph_id,
            issue.location.page,
            issue.evidence,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique


def _collect_normalized_required_titles(document: DocumentInput, entries: List[StructureEntry]) -> List[str]:
    titles = [_normalize_title(entry.title) for entry in entries if entry.level == 1]
    paragraph_meta = document.meta.extras.get('docx_paragraphs', []) if document.meta.extras else []
    table_meta = document.meta.extras.get('docx_table_paragraphs', []) if document.meta.extras else []
    for item in paragraph_meta[:60] + table_meta[:60]:
        normalized = _normalize_title(str(item.get('text', '')))
        if normalized:
            titles.append(normalized)
    for paragraph in document.paragraphs[:80]:
        normalized = _normalize_title(paragraph.text)
        if normalized:
            titles.append(normalized)
    return titles
