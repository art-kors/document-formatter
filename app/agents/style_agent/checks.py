import json
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from app.llm.base import LLMProvider
from app.schemas.document import DocumentInput, Paragraph, Position
from app.schemas.issue import Issue, IssueLocation, StandardReference, SuggestedFix


STYLE_RULES = {
    "style_mismatch": StandardReference(
        source="style_rules",
        rule_id="style_rule_00",
        quote="Текст должен соответствовать научному или деловому стилю изложения.",
    ),
    "colloquial_phrase": StandardReference(
        source="style_rules",
        rule_id="style_rule_01",
        quote="Следует избегать разговорных и неформальных формулировок.",
    ),
    "informal_wording": StandardReference(
        source="style_rules",
        rule_id="style_rule_02",
        quote="Формулировки должны быть точными и нейтральными.",
    ),
    "term_inconsistency": StandardReference(
        source="style_rules",
        rule_id="style_rule_03",
        quote="Термины должны использоваться последовательно по всему тексту.",
    ),
    "long_sentence": StandardReference(
        source="style_rules",
        rule_id="style_rule_04",
        quote="Слишком длинные предложения ухудшают читаемость текста.",
    ),
    "overloaded_sentence": StandardReference(
        source="style_rules",
        rule_id="style_rule_05",
        quote="Перегруженные предложения следует упрощать и разбивать.",
    ),
}

COLLOQUIAL_REPLACEMENTS: Dict[str, str] = {
    "короче говоря": "таким образом",
    "в общем": "в итоге",
    "как бы": "",
    "типа": "типа",
    "ну можно сказать": "можно заключить",
    "по сути": "по существу",
}

INFORMAL_REPLACEMENTS: Dict[str, str] = {
    "штука": "механизм",
    "круто": "эффективно",
    "ок": "корректно",
    "баг": "ошибка",
    "прикольно": "показательно",
}

TERM_VARIANTS: Dict[str, List[str]] = {
    "API": ["api", "апи"],
    "RAG": ["rag", "раг"],
    "ГОСТ": ["гост", "gost"],
}

ALLOWED_SUBTYPES = set(STYLE_RULES)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9-]+")
COMMA_CONNECTOR_RE = re.compile(
    r"\b(который|которая|которые|которое|поскольку|поэтому|следовательно|если|когда|хотя|кроме|однако|причем|потому что)\b",
    re.IGNORECASE,
)
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def run_style_checks(document: DocumentInput, llm_provider: Optional[LLMProvider] = None) -> List[Issue]:
    llm_issues = _try_run_style_checks_with_llm(document, llm_provider)
    if llm_issues is not None:
        return _deduplicate_issues(llm_issues)
    return _deduplicate_issues(_run_style_checks_fallback(document))


def build_style_summary(document: DocumentInput, issues: Optional[List[Issue]] = None) -> Dict[str, object]:
    if issues is None:
        issues = run_style_checks(document)
    subtype_counts = Counter(issue.subtype for issue in issues)
    return {
        "issues_by_subtype": dict(subtype_counts),
        "fixable_issues": sum(1 for issue in issues if issue.suggestion),
        "term_conflicts": [issue.evidence for issue in issues if issue.subtype == "term_inconsistency"],
    }


def _try_run_style_checks_with_llm(document: DocumentInput, llm_provider: Optional[LLMProvider]) -> Optional[List[Issue]]:
    if llm_provider is None:
        return None

    prompt = _build_style_prompt(document)
    try:
        response = llm_provider.chat(prompt)
    except Exception:
        return None

    payload = _extract_json_payload(response)
    if payload is None:
        return None

    raw_issues = payload.get("issues") if isinstance(payload, dict) else None
    if not isinstance(raw_issues, list):
        return None

    paragraph_map = {paragraph.id: paragraph for paragraph in _iter_text_units(document)}
    issues: List[Issue] = []
    for index, raw_issue in enumerate(raw_issues, start=1):
        issue = _issue_from_llm_payload(index, raw_issue, paragraph_map)
        if issue is not None:
            issues.append(issue)
    return issues


def _build_style_prompt(document: DocumentInput) -> str:
    paragraphs = _iter_text_units(document)
    serialized = []
    for paragraph in paragraphs[:40]:
        serialized.append({
            "paragraph_id": paragraph.id,
            "section_id": paragraph.section_id,
            "page": paragraph.position.page,
            "text": paragraph.text,
        })

    schema = {
        "issues": [
            {
                "paragraph_id": "string or null",
                "subtype": "style_mismatch | colloquial_phrase | informal_wording | term_inconsistency | long_sentence | overloaded_sentence",
                "severity": "warning or info",
                "message": "short Russian message",
                "evidence": "why this is a problem in Russian",
                "before": "original text fragment or null",
                "after": "improved fragment or null",
            }
        ]
    }

    return (
        "Ты проверяешь текст отчета на соответствие научному или деловому стилю. "
        "Не считай слово ошибкой само по себе: оценивай его только в контексте предложения. "
        "Если предложение слишком длинное, предложи более короткую и ясную формулировку. "
        "Если термин используется непоследовательно, укажи это. "
        "Верни только JSON без пояснений.\n\n"
        f"Формат ответа: {json.dumps(schema, ensure_ascii=False)}\n\n"
        f"Параграфы документа: {json.dumps(serialized, ensure_ascii=False)}"
    )


def _extract_json_payload(response: str) -> Optional[dict]:
    if not response or not response.strip():
        return None

    text = response.strip()
    fenced = _JSON_BLOCK_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None

    return payload if isinstance(payload, dict) else None


def _issue_from_llm_payload(index: int, raw_issue: object, paragraph_map: Dict[str, Paragraph]) -> Optional[Issue]:
    if not isinstance(raw_issue, dict):
        return None

    subtype = str(raw_issue.get("subtype") or "").strip()
    if subtype not in ALLOWED_SUBTYPES:
        return None

    confidence = str(raw_issue.get("confidence") or "medium").strip().lower()
    if confidence == "low":
        return None

    severity = str(raw_issue.get("severity") or "warning").strip().lower()
    if severity not in {"warning", "info"}:
        severity = "warning"

    paragraph_id = raw_issue.get("paragraph_id")
    paragraph = paragraph_map.get(str(paragraph_id)) if paragraph_id else None
    location = _location_from_paragraph(paragraph) if paragraph is not None else IssueLocation()

    before = _normalize_optional_text(raw_issue.get("before"))
    after = _normalize_optional_text(raw_issue.get("after"))
    suggestion = None
    if before and after and before != after:
        suggestion = SuggestedFix(before=before, after=after)
    elif after:
        suggestion = after

    message = _normalize_optional_text(raw_issue.get("message")) or "Обнаружено стилистическое замечание"
    evidence = _normalize_optional_text(raw_issue.get("evidence")) or "LLM обнаружила стилистическую проблему в тексте документа."

    return Issue(
        id=f"issue_style_llm_{index:03d}",
        type="style",
        subtype=subtype,
        severity=severity,
        message=message,
        location=location,
        evidence=evidence,
        standard_reference=STYLE_RULES.get(subtype, STYLE_RULES["style_mismatch"]),
        suggestion=suggestion,
        agent="style_agent",
    )


def _normalize_optional_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _run_style_checks_fallback(document: DocumentInput) -> List[Issue]:
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
                evidence=f"Фрагмент: '{_extract_fragment(paragraph.text, phrase)}'",
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
                message="Обнаружено слишком простое или неформальное слово",
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
                    suggestion="Разбейте предложение на 2-3 более короткие части и оставьте в каждой одно ключевое утверждение.",
                ))
                issue_id += 1

            comma_count = sentence.count(",")
            connector_count = len(COMMA_CONNECTOR_RE.findall(sentence))
            if len(sentence) >= 180 and (comma_count >= 4 or connector_count >= 3):
                issues.append(_make_issue(
                    issue_id=issue_id,
                    subtype="overloaded_sentence",
                    severity="info",
                    message="Предложение перегружено и трудно для восприятия",
                    location=_location_from_paragraph(paragraph),
                    evidence=f"Предложение содержит {comma_count} запятых и {connector_count} сложных связок.",
                    suggestion="Упростите конструкцию: разделите смысловые части и уберите лишние придаточные обороты.",
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
            evidence="В документе обнаружены разговорные или неформальные формулировки.",
            suggestion="Замените разговорные и бытовые выражения на нейтральные формулировки.",
        ))

    return issues


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
            "location": IssueLocation(),
            "message": "Обнаружена терминологическая несогласованность",
            "evidence": f"В документе используются варианты '{example_variant}' и '{conflicting_variant}' для термина {canonical}.",
            "suggestion": SuggestedFix(
                before=f"Используемые варианты: {', '.join(present)}",
                after=f"Используйте один вариант термина: {canonical}",
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


def _location_from_paragraph(paragraph: Optional[Paragraph]) -> IssueLocation:
    if paragraph is None:
        return IssueLocation()
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
