import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from app.schemas.document import DocumentInput, Paragraph, Position
from app.schemas.issue import Issue, IssueLocation, StandardReference, SuggestedFix


STYLE_RULES = {
    "style_mismatch": StandardReference(
        source="style_rules",
        rule_id="style_rule_00",
        quote="Для научного текста рекомендуется нейтральный деловой стиль изложения.",
    ),
    "colloquial_phrase": StandardReference(
        source="style_rules",
        rule_id="style_rule_01",
        quote="Следует избегать разговорных и неформальных формулировок.",
    ),
    "informal_wording": StandardReference(
        source="style_rules",
        rule_id="style_rule_02",
        quote="Формулировки отчета должны быть точными и нейтральными.",
    ),
    "term_inconsistency": StandardReference(
        source="style_rules",
        rule_id="style_rule_03",
        quote="Терминология документа должна использоваться последовательно по всему тексту.",
    ),
    "long_sentence": StandardReference(
        source="style_rules",
        rule_id="style_rule_04",
        quote="Слишком длинные предложения затрудняют восприятие текста и должны быть упрощены.",
    ),
    "overloaded_sentence": StandardReference(
        source="style_rules",
        rule_id="style_rule_05",
        quote="Перегруженные конструкции рекомендуется разделять на более простые смысловые единицы.",
    ),
}

COLLOQUIAL_REPLACEMENTS: Dict[str, str] = {
    "короче говоря": "таким образом",
    "в общем": "в целом",
    "как бы": "",
    "типа": "например",
    "на самом деле": "фактически",
    "по сути": "по существу",
}

INFORMAL_REPLACEMENTS: Dict[str, str] = {
    "штука": "механизм",
    "куча": "множество",
    "плюс": "кроме того",
    "мега": "значительно",
    "огромный": "значительный",
}

TERM_VARIANTS: Dict[str, List[str]] = {
    "API": ["api", "апи"],
    "RAG": ["rag", "раг"],
    "ГОСТ": ["гост", "gost"],
}

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9-]+")
COMMA_CONNECTOR_RE = re.compile(r"\b(который|которая|которые|поскольку|однако|поэтому|следовательно|если|когда|чтобы|которого|которая|котором|которым)\b", re.IGNORECASE)


def run_style_checks(document: DocumentInput) -> List[Issue]:
    issues: List[Issue] = []
    issue_id = 1
    colloquial_hits = 0
    informal_hits = 0

    for paragraph in _iter_text_units(document):
        for phrase, replacement in COLLOQUIAL_REPLACEMENTS.items():
            if phrase not in _normalize(paragraph.text):
                continue
            before, after = _replace_fragment(paragraph.text, phrase, replacement)
            issues.append(_make_issue(
                issue_id=issue_id,
                subtype="colloquial_phrase",
                severity="warning",
                message="Обнаружена разговорная формулировка",
                location=_location_from_paragraph(paragraph),
                evidence=f"Фраза: '{_extract_fragment(paragraph.text, phrase)}'",
                suggestion=SuggestedFix(before=before, after=after),
            ))
            issue_id += 1
            colloquial_hits += 1

        for word, replacement in INFORMAL_REPLACEMENTS.items():
            if not re.search(rf"\b{re.escape(word)}\b", _normalize(paragraph.text)):
                continue
            before, after = _replace_fragment(paragraph.text, word, replacement)
            issues.append(_make_issue(
                issue_id=issue_id,
                subtype="informal_wording",
                severity="warning",
                message="Обнаружена слишком простая или неформальная формулировка",
                location=_location_from_paragraph(paragraph),
                evidence=f"Слово или оборот: '{_extract_fragment(paragraph.text, word)}'",
                suggestion=SuggestedFix(before=before, after=after),
            ))
            issue_id += 1
            informal_hits += 1

        for sentence in _split_sentences(paragraph.text):
            word_count = len(WORD_RE.findall(sentence))
            if word_count >= 35 or len(sentence) >= 240:
                issues.append(_make_issue(
                    issue_id=issue_id,
                    subtype="long_sentence",
                    severity="info",
                    message="Обнаружено слишком длинное предложение",
                    location=_location_from_paragraph(paragraph),
                    evidence=f"Предложение содержит {word_count} слов.",
                    suggestion="Разделить предложение на 2-3 более короткие фразы и оставить в каждой одну основную мысль.",
                ))
                issue_id += 1

            comma_count = sentence.count(",")
            connector_count = len(COMMA_CONNECTOR_RE.findall(sentence))
            if len(sentence) >= 180 and (comma_count >= 4 or connector_count >= 3):
                issues.append(_make_issue(
                    issue_id=issue_id,
                    subtype="overloaded_sentence",
                    severity="info",
                    message="Предложение выглядит перегруженным и трудным для восприятия",
                    location=_location_from_paragraph(paragraph),
                    evidence=f"Предложение содержит {comma_count} запятых и {connector_count} сложных связок.",
                    suggestion="Упростить синтаксис: сократить число придаточных частей и вынести второстепенные пояснения в отдельные предложения.",
                ))
                issue_id += 1

    for payload in _check_term_consistency(document):
        issues.append(_make_issue(issue_id=issue_id, **payload))
        issue_id += 1

    if colloquial_hits + informal_hits >= 2:
        first_issue = next(issue for issue in issues if issue.subtype in {"colloquial_phrase", "informal_wording"})
        issues.append(_make_issue(
            issue_id=issue_id,
            subtype="style_mismatch",
            severity="warning",
            message="Текст частично не соответствует научному или деловому стилю",
            location=first_issue.location,
            evidence="В документе обнаружено несколько разговорных или неформальных формулировок.",
            suggestion="Привести формулировки к нейтральному деловому стилю и исключить разговорные обороты.",
        ))

    return _deduplicate_issues(issues)


def build_style_summary(document: DocumentInput, issues: Optional[List[Issue]] = None) -> Dict[str, object]:
    if issues is None:
        issues = run_style_checks(document)
    subtype_counts = Counter(issue.subtype for issue in issues)
    return {
        "issues_by_subtype": dict(subtype_counts),
        "fixable_issues": sum(1 for issue in issues if isinstance(issue.suggestion, (str, SuggestedFix)) and issue.suggestion),
        "term_conflicts": [issue.evidence for issue in issues if issue.subtype == "term_inconsistency"],
    }


def _iter_text_units(document: DocumentInput) -> List[Paragraph]:
    if document.paragraphs:
        return document.paragraphs
    return [
        Paragraph(
            id=f"style_section_{index + 1}",
            section_id=section.id,
            text=section.text or section.title,
            position=Position(),
        )
        for index, section in enumerate(document.sections)
        if (section.text or section.title).strip()
    ]


def _check_term_consistency(document: DocumentInput) -> List[dict]:
    text = "\n".join(unit.text for unit in _iter_text_units(document))
    normalized = _normalize(text)
    issues: List[dict] = []
    for canonical, variants in TERM_VARIANTS.items():
        present = [variant for variant in variants if re.search(rf"\b{re.escape(variant)}\b", normalized)]
        if len(present) <= 1:
            continue
        example_variant = present[0]
        conflicting_variant = present[1]
        issues.append({
            "subtype": "term_inconsistency",
            "severity": "warning",
            "message": "Обнаружена неконсистентность терминологии",
            "location": IssueLocation(),
            "evidence": f"В документе одновременно используются варианты '{example_variant}' и '{conflicting_variant}' для термина {canonical}.",
            "suggestion": SuggestedFix(
                before=f"Используются варианты: {', '.join(present)}",
                after=f"Использовать единый вариант: {canonical}",
            ),
        })
    return issues


def _normalize(text: str) -> str:
    return " ".join(text.lower().replace("ё", "е").split())


def _split_sentences(text: str) -> List[str]:
    sentences = [sentence.strip() for sentence in SENTENCE_SPLIT_RE.split(text.strip()) if sentence.strip()]
    return sentences or ([text.strip()] if text.strip() else [])


def _replace_fragment(text: str, needle: str, replacement: str) -> Tuple[str, str]:
    before = text.strip()
    pattern = re.compile(re.escape(needle), re.IGNORECASE)
    after = pattern.sub(replacement, before, count=1)
    after = re.sub(r"\s{2,}", " ", after).strip(" ,")
    return before, after


def _extract_fragment(text: str, needle: str) -> str:
    match = re.search(re.escape(needle), text, re.IGNORECASE)
    return match.group(0) if match else needle


def _location_from_paragraph(paragraph: Paragraph) -> IssueLocation:
    return IssueLocation(
        section_id=paragraph.section_id,
        paragraph_id=paragraph.id,
        page=paragraph.position.page,
    )


def _make_issue(
    *,
    issue_id: int,
    subtype: str,
    severity: str,
    message: str,
    location: IssueLocation,
    evidence: str,
    suggestion,
) -> Issue:
    return Issue(
        id=f"issue_style_{issue_id:03d}",
        type="style",
        subtype=subtype,
        severity=severity,
        message=message,
        location=location,
        evidence=evidence,
        standard_reference=STYLE_RULES[subtype],
        suggestion=suggestion,
        agent="style_agent",
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
