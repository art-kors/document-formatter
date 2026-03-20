import json
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from app.llm.base import LLMProvider
from app.schemas.document import DocumentInput, Paragraph, Position
from app.schemas.issue import Issue, IssueLocation, StandardReference, SuggestedFix


STYLE_RULES = {
    "spelling_error": StandardReference(
        source="style_rules",
        rule_id="style_rule_00",
        quote="\u041e\u0440\u0444\u043e\u0433\u0440\u0430\u0444\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u043e\u0448\u0438\u0431\u043a\u0438 \u0438 \u044f\u0432\u043d\u044b\u0435 \u043e\u043f\u0435\u0447\u0430\u0442\u043a\u0438 \u0441\u043b\u0435\u0434\u0443\u0435\u0442 \u0438\u0441\u043f\u0440\u0430\u0432\u043b\u044f\u0442\u044c.",
    ),
    "colloquial_phrase": StandardReference(
        source="style_rules",
        rule_id="style_rule_01",
        quote="\u0421\u043b\u0435\u0434\u0443\u0435\u0442 \u0438\u0437\u0431\u0435\u0433\u0430\u0442\u044c \u044f\u0432\u043d\u043e \u0440\u0430\u0437\u0433\u043e\u0432\u043e\u0440\u043d\u044b\u0445 \u0438 \u043f\u0440\u043e\u0441\u0442\u043e\u0440\u0435\u0447\u043d\u044b\u0445 \u0444\u043e\u0440\u043c\u0443\u043b\u0438\u0440\u043e\u0432\u043e\u043a.",
    ),
    "informal_wording": StandardReference(
        source="style_rules",
        rule_id="style_rule_02",
        quote="\u041d\u0435\u043d\u043e\u0440\u043c\u0430\u0442\u0438\u0432\u043d\u0430\u044f \u043b\u0435\u043a\u0441\u0438\u043a\u0430 \u0438 \u0433\u0440\u0443\u0431\u044b\u0435 \u043f\u0440\u043e\u0441\u0442\u043e\u0440\u0435\u0447\u0438\u044f \u043d\u0435\u0434\u043e\u043f\u0443\u0441\u0442\u0438\u043c\u044b \u0432 \u043e\u0442\u0447\u0435\u0442\u0435.",
    ),
    "long_sentence": StandardReference(
        source="style_rules",
        rule_id="style_rule_03",
        quote="\u0427\u0440\u0435\u0437\u043c\u0435\u0440\u043d\u043e \u0434\u043b\u0438\u043d\u043d\u044b\u0435 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u044f \u0441\u043b\u0435\u0434\u0443\u0435\u0442 \u0440\u0430\u0437\u0431\u0438\u0432\u0430\u0442\u044c \u043d\u0430 \u0431\u043e\u043b\u0435\u0435 \u043a\u043e\u0440\u043e\u0442\u043a\u0438\u0435.",
    ),
}

HARD_COLLOQUIAL_REPLACEMENTS: Dict[str, str] = {
    "\u043a\u043e\u0440\u043e\u0447\u0435 \u0433\u043e\u0432\u043e\u0440\u044f": "\u0442\u0430\u043a\u0438\u043c \u043e\u0431\u0440\u0430\u0437\u043e\u043c",
    "\u043d\u0443 \u043a\u043e\u0440\u043e\u0447\u0435": "\u0442\u0430\u043a\u0438\u043c \u043e\u0431\u0440\u0430\u0437\u043e\u043c",
    "\u0431\u043b\u0438\u043d": "",
    "\u043e\u0444\u0438\u0433\u0435\u043d\u043d\u043e": "\u0437\u043d\u0430\u0447\u0438\u0442\u0435\u043b\u044c\u043d\u043e",
    "\u043a\u0430\u043f\u0435\u0446": "\u0441\u0443\u0449\u0435\u0441\u0442\u0432\u0435\u043d\u043d\u043e",
}

HARD_INFORMAL_REPLACEMENTS: Dict[str, str] = {
    "\u0445\u0440\u0435\u043d\u044c": "\u044d\u043b\u0435\u043c\u0435\u043d\u0442",
    "\u0444\u0438\u0433\u043d\u044f": "\u043e\u0448\u0438\u0431\u043a\u0430",
    "\u0434\u0435\u0431\u0438\u043b\u044c\u043d\u044b\u0439": "\u043d\u0435\u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u044b\u0439",
    "\u0442\u0443\u043f\u043e\u0439": "\u043d\u0435\u0443\u0434\u0430\u0447\u043d\u044b\u0439",
    "\u0436\u0435\u0441\u0442\u044c": "\u0441\u0443\u0449\u0435\u0441\u0442\u0432\u0435\u043d\u043d\u0430\u044f \u043f\u0440\u043e\u0431\u043b\u0435\u043c\u0430",
}

ALLOWED_SUBTYPES = set(STYLE_RULES)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[A-Za-z\u0410-\u042f\u0430-\u044f\u0401\u04510-9-]+")
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

    return (
        "\u0422\u044b \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u0435\u0448\u044c \u0442\u0435\u043a\u0441\u0442 \u043e\u0442\u0447\u0435\u0442\u0430 \u0432 \u043e\u0447\u0435\u043d\u044c \u043a\u043e\u043d\u0441\u0435\u0440\u0432\u0430\u0442\u0438\u0432\u043d\u043e\u043c \u0440\u0435\u0436\u0438\u043c\u0435. "
        "\u0420\u0430\u0437\u0440\u0435\u0448\u0435\u043d\u043e \u043d\u0430\u0445\u043e\u0434\u0438\u0442\u044c \u0442\u043e\u043b\u044c\u043a\u043e \u0442\u0440\u0438 \u043a\u043b\u0430\u0441\u0441\u0430 \u043f\u0440\u043e\u0431\u043b\u0435\u043c: "
        "1) \u044f\u0432\u043d\u044b\u0435 \u043e\u0440\u0444\u043e\u0433\u0440\u0430\u0444\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u043e\u0448\u0438\u0431\u043a\u0438 \u0438 \u043e\u043f\u0435\u0447\u0430\u0442\u043a\u0438, "
        "2) \u0433\u0440\u0443\u0431\u044b\u0435 \u0440\u0430\u0437\u0433\u043e\u0432\u043e\u0440\u043d\u044b\u0435, \u043f\u0440\u043e\u0441\u0442\u043e\u0440\u0435\u0447\u043d\u044b\u0435 \u0438\u043b\u0438 \u043d\u0435\u043d\u043e\u0440\u043c\u0430\u0442\u0438\u0432\u043d\u044b\u0435 \u0441\u043b\u043e\u0432\u0430, "
        "3) \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0442\u0435\u043b\u044c\u043d\u043e \u0447\u0440\u0435\u0437\u043c\u0435\u0440\u043d\u043e \u0434\u043b\u0438\u043d\u043d\u044b\u0435 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u044f, \u043a\u043e\u0442\u043e\u0440\u044b\u0435 \u0442\u044f\u043d\u0443\u0442\u0441\u044f \u043f\u043e\u0447\u0442\u0438 \u043d\u0430 \u043f\u043e\u043b\u0441\u0442\u0440\u0430\u043d\u0438\u0446\u044b. "
        "\u041d\u0435 \u043f\u0435\u0440\u0435\u043f\u0438\u0441\u044b\u0432\u0430\u0439 \u043d\u0435\u0439\u0442\u0440\u0430\u043b\u044c\u043d\u0443\u044e \u043b\u0435\u043a\u0441\u0438\u043a\u0443 \u043d\u0430 \u0431\u043e\u043b\u0435\u0435 \u043d\u0430\u0443\u0447\u043d\u0443\u044e. "
        "\u041d\u0435 \u043f\u0440\u0435\u0434\u043b\u0430\u0433\u0430\u0439 \u0441\u0442\u0438\u043b\u0438\u0441\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u0443\u043b\u0443\u0447\u0448\u0435\u043d\u0438\u044f \u0440\u0430\u0434\u0438 \u0443\u043b\u0443\u0447\u0448\u0435\u043d\u0438\u044f. "
        "\u041d\u0435 \u0442\u0440\u043e\u0433\u0430\u0439 \u0442\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u0442\u0435\u0440\u043c\u0438\u043d\u044b, \u0435\u0441\u043b\u0438 \u043e\u043d\u0438 \u0443\u0436\u0435 \u043d\u0435\u0439\u0442\u0440\u0430\u043b\u044c\u043d\u044b. "
        "\u041d\u0435 \u043f\u043e\u043c\u0435\u0447\u0430\u0439 \u043e\u0431\u044b\u0447\u043d\u044b\u0435 \u0434\u043b\u0438\u043d\u043d\u044b\u0435 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u044f, \u0435\u0441\u043b\u0438 \u043e\u043d\u0438 \u0435\u0449\u0435 \u0447\u0438\u0442\u0430\u0435\u043c\u044b. "
        "\u0414\u043b\u044f \u0441\u043e\u043c\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0445 \u0441\u043b\u0443\u0447\u0430\u0435\u0432 \u0441\u0442\u0430\u0432\u044c confidence=low. "
        "\u0412\u0435\u0440\u043d\u0438 \u0442\u043e\u043b\u044c\u043a\u043e JSON \u0431\u0435\u0437 \u043f\u043e\u044f\u0441\u043d\u0435\u043d\u0438\u0439.\n\n"
        f"\u0424\u043e\u0440\u043c\u0430\u0442 \u043e\u0442\u0432\u0435\u0442\u0430: {json.dumps(schema, ensure_ascii=False)}\n\n"
        f"\u041f\u0430\u0440\u0430\u0433\u0440\u0430\u0444\u044b \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430: {json.dumps(serialized, ensure_ascii=False)}"
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

    message = _normalize_optional_text(raw_issue.get("message")) or "\u041e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d\u043e \u0441\u0442\u0438\u043b\u0438\u0441\u0442\u0438\u0447\u0435\u0441\u043a\u043e\u0435 \u0437\u0430\u043c\u0435\u0447\u0430\u043d\u0438\u0435"
    evidence = _normalize_optional_text(raw_issue.get("evidence")) or "LLM \u043e\u0431\u043d\u0430\u0440\u0443\u0436\u0438\u043b\u0430 \u043f\u0440\u043e\u0431\u043b\u0435\u043c\u0443 \u0432 \u0442\u0435\u043a\u0441\u0442\u0435 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430."

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
                message="\u041e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d\u0430 \u0433\u0440\u0443\u0431\u043e \u0440\u0430\u0437\u0433\u043e\u0432\u043e\u0440\u043d\u0430\u044f \u0444\u043e\u0440\u043c\u0443\u043b\u0438\u0440\u043e\u0432\u043a\u0430",
                location=_location_from_paragraph(paragraph),
                evidence=f"\u0424\u0440\u0430\u0433\u043c\u0435\u043d\u0442: '{_extract_fragment(paragraph.text, phrase)}'",
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
                message="\u041e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d\u043e \u043f\u0440\u043e\u0441\u0442\u043e\u0440\u0435\u0447\u043d\u043e\u0435 \u0438\u043b\u0438 \u043d\u0435\u043d\u043e\u0440\u043c\u0430\u0442\u0438\u0432\u043d\u043e\u0435 \u0441\u043b\u043e\u0432\u043e",
                location=_location_from_paragraph(paragraph),
                evidence=f"\u0421\u043b\u043e\u0432\u043e \u0438\u043b\u0438 \u043e\u0431\u043e\u0440\u043e\u0442: '{_extract_fragment(paragraph.text, word)}'",
                suggestion=SuggestedFix(before=before, after=after),
            ))
            issue_id += 1

        for sentence in _split_sentences(paragraph.text):
            word_count = len(WORD_RE.findall(sentence))
            if word_count >= 55 or len(sentence) >= 420:
                issues.append(_make_issue(
                    issue_id=issue_id,
                    subtype="long_sentence",
                    severity="info",
                    message="\u041f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u0441\u043b\u0438\u0448\u043a\u043e\u043c \u0434\u043b\u0438\u043d\u043d\u043e\u0435 \u0438 \u0435\u0433\u043e \u0441\u0442\u043e\u0438\u0442 \u0440\u0430\u0437\u0431\u0438\u0442\u044c",
                    location=_location_from_paragraph(paragraph),
                    evidence=f"\u041f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 {word_count} \u0441\u043b\u043e\u0432.",
                    suggestion="\u0420\u0430\u0437\u0431\u0435\u0439\u0442\u0435 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u043d\u0430 2-3 \u0431\u043e\u043b\u0435\u0435 \u043a\u043e\u0440\u043e\u0442\u043a\u0438\u0435 \u0447\u0430\u0441\u0442\u0438 \u0438 \u043e\u0441\u0442\u0430\u0432\u044c\u0442\u0435 \u0432 \u043a\u0430\u0436\u0434\u043e\u0439 \u043e\u0434\u043d\u043e \u043a\u043b\u044e\u0447\u0435\u0432\u043e\u0435 \u0443\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u0435.",
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
    return " ".join(text.lower().replace("\u0451", "\u0435").split())


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
