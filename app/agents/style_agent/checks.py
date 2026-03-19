import json
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from app.llm.base import LLMProvider
from app.llm.local_chat_provider import LocalChatProvider
from app.schemas.document import DocumentInput, Paragraph, Position
from app.schemas.issue import Issue, IssueLocation, StandardReference, SuggestedFix


STYLE_RULES = {
    "spelling_error": StandardReference(
        source="style_rules",
        rule_id="style_rule_00",
        quote="Орфографические ошибки и явные опечатки следует исправлять.",
    ),
    "colloquial_phrase": StandardReference(
        source="style_rules",
        rule_id="style_rule_01",
        quote="Следует избегать явно разговорных и просторечных формулировок.",
    ),
    "informal_wording": StandardReference(
        source="style_rules",
        rule_id="style_rule_02",
        quote="Ненормативная лексика и грубые просторечия недопустимы в отчете.",
    ),
    "long_sentence": StandardReference(
        source="style_rules",
        rule_id="style_rule_03",
        quote="Чрезмерно длинные предложения следует разбивать на более короткие.",
    ),
}

HARD_COLLOQUIAL_REPLACEMENTS: Dict[str, str] = {
    "короче говоря": "таким образом",
    "ну короче": "таким образом",
    "блин": "",
    "офигенно": "значительно",
    "капец": "существенно",
}

HARD_INFORMAL_REPLACEMENTS: Dict[str, str] = {
    "хрень": "элемент",
    "фигня": "ошибка",
    "дебильный": "некорректный",
    "тупой": "неудачный",
    "жесть": "существенная проблема",
}

ALLOWED_SUBTYPES = set(STYLE_RULES)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9-]+")
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def run_style_checks(document: DocumentInput, llm_provider: Optional[LLMProvider] = None) -> List[Issue]:
    llm_issues = _try_run_style_checks_with_llm(document, llm_provider)
    if llm_issues is not None:
        fallback_issues = _run_style_checks_fallback(document, include_length_checks=False)
        return _deduplicate_issues(llm_issues + fallback_issues)
    return _deduplicate_issues(_run_style_checks_fallback(document, include_length_checks=True))


def build_style_summary(document: DocumentInput, issues: Optional[List[Issue]] = None) -> Dict[str, object]:
    if issues is None:
        issues = run_style_checks(document)
    subtype_counts = Counter(issue.subtype for issue in issues)
    return {
        "issues_by_subtype": dict(subtype_counts),
        "fixable_issues": sum(1 for issue in issues if issue.suggestion),
        "spelling_issues": subtype_counts.get("spelling_error", 0),
    }


def _try_run_style_checks_with_llm(document: DocumentInput, llm_provider: Optional[LLMProvider]) -> Optional[List[Issue]]:
    if llm_provider is None:
        return None

    prompt = _build_style_prompt(document, local_mode=isinstance(llm_provider, LocalChatProvider))
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


def _build_style_prompt(document: DocumentInput, local_mode: bool = False) -> str:
    paragraphs = _iter_text_units(document)
    serialized = _serialize_paragraphs_for_prompt(paragraphs, local_mode=local_mode)

    schema = {
        "issues": [
            {
                "paragraph_id": "string or null",
                "subtype": "spelling_error | long_sentence",
                "severity": "warning or info",
                "confidence": "high | medium | low",
                "message": "short Russian message",
                "evidence": "why this is a problem in Russian",
                "before": "original text fragment or null",
                "after": "improved fragment or null",
            }
        ]
    }

    limit_note = "Верни не более 6 замечаний." if local_mode else "Верни только JSON без пояснений."
    return (
        "Ты проверяешь текст отчета в очень консервативном режиме. "
        "Разрешено находить только два класса проблем: "
        "1) явные орфографические ошибки и опечатки, "
        "2) действительно чрезмерно длинные предложения, которые тянутся почти на полстраницы. "
        "Не переписывай нейтральную лексику на более научную. "
        "Не предлагай стилистические улучшения ради улучшения. "
        "Не трогай технические термины, если они уже нейтральны. "
        "Не помечай обычные длинные предложения, если они еще читаемы. "
        "Для сомнительных случаев ставь confidence=low. "
        f"{limit_note}\n\n"
        f"Формат ответа: {json.dumps(schema, ensure_ascii=False)}\n\n"
        f"Параграфы документа: {json.dumps(serialized, ensure_ascii=False)}"
    )


def _serialize_paragraphs_for_prompt(paragraphs: List[Paragraph], *, local_mode: bool) -> List[dict]:
    max_paragraphs = 12 if local_mode else 40
    max_chars = 450 if local_mode else 1200
    selected = _select_paragraphs_for_prompt(paragraphs, max_paragraphs=max_paragraphs, local_mode=local_mode)

    serialized = []
    for paragraph in selected:
        text = paragraph.text.strip()
        if len(text) > max_chars:
            text = text[: max_chars - 1].rstrip() + "…"
        serialized.append({
            "paragraph_id": paragraph.id,
            "text": text,
        })
    return serialized


def _select_paragraphs_for_prompt(paragraphs: List[Paragraph], *, max_paragraphs: int, local_mode: bool) -> List[Paragraph]:
    if len(paragraphs) <= max_paragraphs:
        return paragraphs
    if not local_mode:
        return paragraphs[:max_paragraphs]

    indexed = list(enumerate(paragraphs))
    selected_indexes = {index for index, _ in indexed[:3]}
    selected_indexes.update(index for index, _ in indexed[-2:])

    for index, _ in sorted(indexed, key=lambda item: len(item[1].text or ""), reverse=True):
        if len(selected_indexes) >= max_paragraphs:
            break
        selected_indexes.add(index)

    if len(selected_indexes) < max_paragraphs:
        step = max(1, len(paragraphs) // max_paragraphs)
        for index in range(0, len(paragraphs), step):
            selected_indexes.add(index)
            if len(selected_indexes) >= max_paragraphs:
                break

    return [paragraph for index, paragraph in indexed if index in selected_indexes][:max_paragraphs]


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
    if subtype not in {"spelling_error", "long_sentence"}:
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
    evidence = _normalize_optional_text(raw_issue.get("evidence")) or "LLM обнаружила проблему в тексте документа."

    return Issue(
        id=f"issue_style_llm_{index:03d}",
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


def _normalize_optional_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _run_style_checks_fallback(document: DocumentInput, *, include_length_checks: bool) -> List[Issue]:
    issues: List[Issue] = []
    issue_id = 1

    for paragraph in _iter_text_units(document):
        normalized_text = _normalize(paragraph.text)
        for phrase, replacement in HARD_COLLOQUIAL_REPLACEMENTS.items():
            if phrase not in normalized_text:
                continue
            before, after = _replace_fragment(paragraph.text, phrase, replacement)
            issues.append(_make_issue(
                issue_id=issue_id,
                subtype="colloquial_phrase",
                severity="warning",
                message="Обнаружена грубо разговорная формулировка",
                location=_location_from_paragraph(paragraph),
                evidence=f"Фрагмент: '{_extract_fragment(paragraph.text, phrase)}'",
                suggestion=SuggestedFix(before=before, after=after),
            ))
            issue_id += 1

        for word, replacement in HARD_INFORMAL_REPLACEMENTS.items():
            if not re.search(rf"\b{re.escape(word)}\b", normalized_text):
                continue
            before, after = _replace_fragment(paragraph.text, word, replacement)
            issues.append(_make_issue(
                issue_id=issue_id,
                subtype="informal_wording",
                severity="warning",
                message="Обнаружено просторечное или ненормативное слово",
                location=_location_from_paragraph(paragraph),
                evidence=f"Слово или оборот: '{_extract_fragment(paragraph.text, word)}'",
                suggestion=SuggestedFix(before=before, after=after),
            ))
            issue_id += 1

        if not include_length_checks:
            continue
        for sentence in _split_sentences(paragraph.text):
            word_count = len(WORD_RE.findall(sentence))
            if word_count >= 55 or len(sentence) >= 420:
                issues.append(_make_issue(
                    issue_id=issue_id,
                    subtype="long_sentence",
                    severity="info",
                    message="Предложение слишком длинное и его стоит разбить",
                    location=_location_from_paragraph(paragraph),
                    evidence=f"Предложение содержит {word_count} слов.",
                    suggestion="Разбейте предложение на 2-3 более короткие части и оставьте в каждой одно ключевое утверждение.",
                ))
                issue_id += 1

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
