import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from app.llm.base import LLMProvider
from app.llm.local_chat_provider import LocalChatProvider
from app.schemas.document import DocumentInput, Position
from app.schemas.issue import Issue, IssueLocation, StandardReference


LOGIC_RULES = {
    "deployment_mode_conflict": StandardReference(
        source="logic_rules",
        rule_id="logic_rule_01",
        quote="The document must not contain mutually exclusive statements about one system's operating mode.",
    ),
    "automation_mode_conflict": StandardReference(
        source="logic_rules",
        rule_id="logic_rule_02",
        quote="The document must not contain mutually exclusive statements about automatic and manual execution of the same process.",
    ),
    "availability_conflict": StandardReference(
        source="logic_rules",
        rule_id="logic_rule_03",
        quote="The document must not simultaneously claim that the same element is present and absent.",
    ),
    "quantity_conflict": StandardReference(
        source="logic_rules",
        rule_id="logic_rule_04",
        quote="Quantitative characteristics of the same object must be consistent throughout the document.",
    ),
    "semantic_contradiction": StandardReference(
        source="logic_rules",
        rule_id="logic_rule_05",
        quote="Semantically related statements in the document must not contradict each other.",
    ),
    "goal_result_mismatch": StandardReference(
        source="logic_rules",
        rule_id="logic_rule_06",
        quote="The document goal, described solution, and final conclusions must be consistent.",
    ),
}

_ALLOWED_LLM_SUBTYPES = set(LOGIC_RULES)
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)
_TOKEN_RE = re.compile(r"[a-zA-Z?-??-?0-9]+", re.IGNORECASE)
_STOPWORDS = {
    "and", "the", "for", "with", "that", "this", "from", "into", "about", "same", "document",
    "?", "?", "??", "??", "??", "?", "??", "???", "??", "?", "??", "?", "?", "??", "??", "??",
    "???", "???", "???", "??", "??", "???", "???", "???", "???", "???", "??", "??", "?",
}


@dataclass
class TextUnit:
    id: str
    section_id: Optional[str]
    text: str
    position: Position


@dataclass
class ExtractedClaim:
    subject: str
    property_name: str
    value: str
    polarity: str
    claim_text: str
    unit: TextUnit


def run_logic_checks(document: DocumentInput, llm_provider: Optional[LLMProvider] = None) -> List[Issue]:
    if llm_provider is None:
        return []
    return _deduplicate_issues(_run_logic_checks_with_llm(document, llm_provider))


def build_logic_summary(document: DocumentInput, issues: Optional[List[Issue]] = None) -> Dict[str, object]:
    if issues is None:
        issues = []
    return {
        "issues_by_subtype": _count_subtypes(issues),
        "logic_conflicts": len(issues),
    }


def _run_logic_checks_with_llm(document: DocumentInput, llm_provider: LLMProvider) -> List[Issue]:
    units = _iter_text_units(document)
    if not units:
        return []

    local_mode = isinstance(llm_provider, LocalChatProvider)
    claims = _extract_claims_with_llm(units, llm_provider, local_mode=local_mode)
    issues = _compare_claims_with_llm(claims, llm_provider, local_mode=local_mode)
    if issues:
        return issues
    return _scan_document_directly_with_llm(units, llm_provider, local_mode=local_mode)


def _extract_claims_with_llm(units: List[TextUnit], llm_provider: LLMProvider, *, local_mode: bool) -> List[ExtractedClaim]:
    chunk_size = 6 if local_mode else 10
    claims: List[ExtractedClaim] = []
    for chunk in _chunk_units(units, chunk_size):
        prompt = _build_claim_extraction_prompt(chunk, local_mode=local_mode)
        try:
            response = llm_provider.chat(prompt)
        except Exception:
            continue
        payload = _extract_json_payload(response)
        claims.extend(_claims_from_payload(payload, chunk))
    return claims


def _compare_claims_with_llm(claims: List[ExtractedClaim], llm_provider: LLMProvider, *, local_mode: bool) -> List[Issue]:
    candidates = _build_claim_candidates(claims, local_mode=local_mode)
    issues: List[Issue] = []
    for index, (left, right) in enumerate(candidates, start=1):
        prompt = _build_claim_comparison_prompt(left, right)
        try:
            response = llm_provider.chat(prompt)
        except Exception:
            continue
        payload = _extract_json_payload(response)
        issue = _issue_from_comparison_payload(index, payload, left, right)
        if issue is not None:
            issues.append(issue)
    return issues


def _scan_document_directly_with_llm(units: List[TextUnit], llm_provider: LLMProvider, *, local_mode: bool) -> List[Issue]:
    windows = _build_direct_windows(units, local_mode=local_mode)
    issues: List[Issue] = []
    issue_index = 1
    for window in windows:
        prompt = _build_direct_scan_prompt(window, local_mode=local_mode)
        try:
            response = llm_provider.chat(prompt)
        except Exception:
            continue
        payload = _extract_json_payload(response)
        raw_issues = payload.get("issues") if isinstance(payload, dict) else None
        if not isinstance(raw_issues, list):
            continue
        unit_map = {unit.id: unit for unit in window}
        for raw_issue in raw_issues:
            issue = _issue_from_llm_payload(issue_index, raw_issue, unit_map)
            if issue is not None:
                issues.append(issue)
                issue_index += 1
    return issues


def _build_claim_extraction_prompt(units: Sequence[TextUnit], *, local_mode: bool) -> str:
    schema = {
        "claims": [
            {
                "paragraph_id": "string",
                "subject": "short canonical subject in Russian",
                "property": "short property name in Russian",
                "value": "short value in Russian",
                "polarity": "positive | negative | unknown",
                "claim_text": "short Russian paraphrase of the claim",
                "confidence": "high | medium | low",
            }
        ]
    }
    max_claims = 6 if local_mode else 12
    return (
        "Extract only atomic factual claims from document fragments that may contradict other parts of the document. "
        "Keep only claims about operating mode, automation mode, presence or absence of elements, quantities, goals, results, requirements, or conclusions. "
        "Ignore style, formatting, definitions, and generic discussion. "
        "Return subjects, properties, values, and claim_text in Russian. "
        "If confidence is low, either skip the claim or set confidence=low. "
        f"Return at most {max_claims} claims. Return JSON only.\n\n"
        f"Schema: {json.dumps(schema, ensure_ascii=False)}\n\n"
        f"Fragments: {json.dumps(_serialize_units(units, max_chars=360 if local_mode else 800), ensure_ascii=False)}"
    )

def _build_claim_comparison_prompt(left: ExtractedClaim, right: ExtractedClaim) -> str:
    schema = {
        "has_conflict": True,
        "subtype": "deployment_mode_conflict | automation_mode_conflict | availability_conflict | quantity_conflict | semantic_contradiction | goal_result_mismatch",
        "severity": "warning | critical | info",
        "confidence": "high | medium | low",
        "message": "short Russian message",
        "evidence": "short Russian explanation with both conflicting claims",
        "suggestion": "short Russian recommendation or null",
    }
    return (
        "Compare two claims from the same document and decide whether they logically contradict each other. "
        "A contradiction exists only when both claims cannot be true at the same time. "
        "Do not treat paraphrases, broader/narrower wording, or stylistic differences as contradictions. "
        "Return message, evidence, and suggestion in Russian. "
        "If there is no contradiction, return JSON only: {\"has_conflict\": false}. "
        "If there is a contradiction, return JSON only using the schema below.\n\n"
        f"Schema: {json.dumps(schema, ensure_ascii=False)}\n\n"
        f"Claim A: {json.dumps(_serialize_claim(left), ensure_ascii=False)}\n"
        f"Claim B: {json.dumps(_serialize_claim(right), ensure_ascii=False)}"
    )

def _build_direct_scan_prompt(units: Sequence[TextUnit], *, local_mode: bool) -> str:
    schema = {
        "issues": [
            {
                "paragraph_id": "string",
                "related_paragraph_id": "string or null",
                "subtype": "deployment_mode_conflict | automation_mode_conflict | availability_conflict | quantity_conflict | semantic_contradiction | goal_result_mismatch",
                "severity": "warning | critical | info",
                "confidence": "high | medium | low",
                "message": "short Russian message",
                "evidence": "short Russian explanation with both conflicting fragments",
                "suggestion": "short Russian recommendation or null",
            }
        ]
    }
    cap = 4 if local_mode else 8
    return (
        "Find only clear logical contradictions between document fragments. "
        "Ignore style, grammar, formatting, and structure. "
        "Return message, evidence, and suggestion in Russian. "
        "If there are no contradictions, return JSON only: {\"issues\": []}. "
        f"Return at most {cap} issues and JSON only.\n\n"
        f"Schema: {json.dumps(schema, ensure_ascii=False)}\n\n"
        f"Fragments: {json.dumps(_serialize_units(units, max_chars=360 if local_mode else 800), ensure_ascii=False)}"
    )

def _serialize_units(units: Sequence[TextUnit], *, max_chars: int) -> List[dict]:
    payload = []
    for unit in units:
        text = unit.text.strip()
        if len(text) > max_chars:
            text = text[: max_chars - 1].rstrip() + "..."
        payload.append({
            "paragraph_id": unit.id,
            "section_id": unit.section_id,
            "page": unit.position.page,
            "paragraph_index": unit.position.paragraph_index,
            "text": text,
        })
    return payload


def _serialize_claim(claim: ExtractedClaim) -> dict:
    return {
        "paragraph_id": claim.unit.id,
        "section_id": claim.unit.section_id,
        "page": claim.unit.position.page,
        "subject": claim.subject,
        "property": claim.property_name,
        "value": claim.value,
        "polarity": claim.polarity,
        "claim_text": claim.claim_text,
        "source_text": claim.unit.text.strip(),
    }


def _claims_from_payload(payload: Optional[dict], units: Sequence[TextUnit]) -> List[ExtractedClaim]:
    if payload is None:
        return []
    raw_claims = payload.get("claims") if isinstance(payload, dict) else None
    if not isinstance(raw_claims, list):
        return []
    unit_map = {unit.id: unit for unit in units}
    claims: List[ExtractedClaim] = []
    for raw_claim in raw_claims:
        if not isinstance(raw_claim, dict):
            continue
        confidence = str(raw_claim.get("confidence") or "medium").strip().lower()
        if confidence == "low":
            continue
        paragraph_id = str(raw_claim.get("paragraph_id") or "").strip()
        unit = unit_map.get(paragraph_id)
        if unit is None:
            continue
        subject = _normalize_label(str(raw_claim.get("subject") or ""))
        property_name = _normalize_label(str(raw_claim.get("property") or ""))
        value = _normalize_label(str(raw_claim.get("value") or ""))
        polarity = str(raw_claim.get("polarity") or "unknown").strip().lower()
        if polarity not in {"positive", "negative", "unknown"}:
            polarity = "unknown"
        claim_text = str(raw_claim.get("claim_text") or "").strip() or unit.text.strip()
        if not subject or not property_name or not value:
            continue
        claims.append(ExtractedClaim(
            subject=subject,
            property_name=property_name,
            value=value,
            polarity=polarity,
            claim_text=claim_text,
            unit=unit,
        ))
    return claims


def _build_claim_candidates(claims: Sequence[ExtractedClaim], *, local_mode: bool) -> List[Tuple[ExtractedClaim, ExtractedClaim]]:
    candidates: List[Tuple[ExtractedClaim, ExtractedClaim, int]] = []
    for index, left in enumerate(claims):
        for right in claims[index + 1 :]:
            if left.unit.id == right.unit.id:
                continue
            score = _claim_pair_score(left, right)
            if score <= 0:
                continue
            candidates.append((left, right, score))
    candidates.sort(key=lambda item: (-item[2], _claim_distance(item[0], item[1])))
    limit = 10 if local_mode else 24
    return [(left, right) for left, right, _ in candidates[:limit]]


def _claim_pair_score(left: ExtractedClaim, right: ExtractedClaim) -> int:
    subject_overlap = _token_overlap(left.subject, right.subject)
    property_overlap = _token_overlap(left.property_name, right.property_name)
    exact_subject = int(_normalize_label(left.subject) == _normalize_label(right.subject))
    exact_property = int(_normalize_label(left.property_name) == _normalize_label(right.property_name))
    score = exact_subject * 4 + exact_property * 3 + subject_overlap * 2 + property_overlap
    if score == 0:
        return 0
    if _normalize_label(left.value) == _normalize_label(right.value) and left.polarity == right.polarity:
        return 0
    return score


def _build_direct_windows(units: Sequence[TextUnit], *, local_mode: bool) -> List[List[TextUnit]]:
    if not units:
        return []
    window = 6 if local_mode else 12
    if len(units) <= window:
        return [list(units)]
    windows: List[List[TextUnit]] = []
    step = max(3, window // 2)
    for start in range(0, len(units), step):
        chunk = list(units[start : start + window])
        if len(chunk) >= 2:
            windows.append(chunk)
        if start + window >= len(units):
            break
    first = list(units[:window])
    last = list(units[-window:])
    if first not in windows:
        windows.insert(0, first)
    if last not in windows:
        windows.append(last)
    return windows[: 6 if local_mode else 10]


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


def _issue_from_comparison_payload(index: int, payload: Optional[dict], left: ExtractedClaim, right: ExtractedClaim) -> Optional[Issue]:
    if not isinstance(payload, dict) or not payload.get("has_conflict"):
        return None
    raw_issue = {
        "paragraph_id": left.unit.id,
        "related_paragraph_id": right.unit.id,
        "subtype": payload.get("subtype"),
        "severity": payload.get("severity"),
        "confidence": payload.get("confidence"),
        "message": payload.get("message"),
        "evidence": payload.get("evidence"),
        "suggestion": payload.get("suggestion"),
    }
    return _issue_from_llm_payload(index, raw_issue, {left.unit.id: left.unit, right.unit.id: right.unit})


def _issue_from_llm_payload(index: int, raw_issue: object, unit_map: Dict[str, TextUnit]) -> Optional[Issue]:
    if not isinstance(raw_issue, dict):
        return None

    subtype = str(raw_issue.get("subtype") or "").strip()
    if subtype not in _ALLOWED_LLM_SUBTYPES:
        return None

    confidence = str(raw_issue.get("confidence") or "medium").strip().lower()
    if confidence == "low":
        return None

    severity = str(raw_issue.get("severity") or "warning").strip().lower()
    if severity not in {"critical", "warning", "info"}:
        severity = "warning"

    paragraph_id = str(raw_issue.get("paragraph_id") or "").strip()
    related_paragraph_id = str(raw_issue.get("related_paragraph_id") or "").strip() or None
    primary = unit_map.get(paragraph_id)
    related = unit_map.get(related_paragraph_id) if related_paragraph_id else None
    if primary is None:
        return None

    message = str(raw_issue.get("message") or "").strip() or "Found a logical contradiction in the document"
    evidence = str(raw_issue.get("evidence") or "").strip() or primary.text.strip()
    suggestion = str(raw_issue.get("suggestion") or "").strip() or None

    return Issue(
        id=f"issue_logic_llm_{index:03d}",
        type="logic",
        subtype=subtype,
        severity=severity,
        message=message,
        location=IssueLocation(
            section_id=primary.section_id,
            paragraph_id=primary.id,
            paragraph_index=primary.position.paragraph_index,
            page=primary.position.page,
        ),
        evidence=evidence if not related else f"{evidence} Conflict fragment: '{related.text.strip()}'",
        standard_reference=LOGIC_RULES.get(subtype, StandardReference(source="logic_rules", rule_id="logic_rule_generic", quote="The document must not contain logical contradictions.")),
        suggestion=suggestion,
        agent="logic_agent",
    )


def _iter_text_units(document: DocumentInput) -> List[TextUnit]:
    units: List[TextUnit] = []
    seen: set[Tuple[str, str]] = set()

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        signature = (paragraph.section_id or "", text)
        if signature in seen:
            continue
        seen.add(signature)
        units.append(TextUnit(
            id=paragraph.id,
            section_id=paragraph.section_id,
            text=text,
            position=paragraph.position,
        ))

    base_index = len(units) + 1
    for offset, section in enumerate(document.sections, start=0):
        for text in (section.title.strip(), section.text.strip()):
            if not text:
                continue
            signature = (section.id, text)
            if signature in seen:
                continue
            seen.add(signature)
            units.append(TextUnit(
                id=f"section::{section.id}::{offset}",
                section_id=section.id,
                text=text,
                position=Position(paragraph_index=base_index + offset),
            ))
    return units


def _chunk_units(units: Sequence[TextUnit], chunk_size: int) -> List[List[TextUnit]]:
    return [list(units[index : index + chunk_size]) for index in range(0, len(units), chunk_size)]


def _claim_distance(left: ExtractedClaim, right: ExtractedClaim) -> int:
    left_index = left.unit.position.paragraph_index or 10_000
    right_index = right.unit.position.paragraph_index or 10_000
    return abs(left_index - right_index)


def _token_overlap(left: str, right: str) -> int:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0
    return len(left_tokens & right_tokens)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(_normalize_label(text))
        if len(token) > 2 and token.lower() not in _STOPWORDS
    }


def _normalize_label(text: str) -> str:
    normalized = text.lower().replace("?", "?").replace("?", "-").replace("?", "-")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip(" .,:;!?-()[]{}\"'")


def _count_subtypes(issues: Sequence[Issue]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for issue in issues:
        counts[issue.subtype] = counts.get(issue.subtype, 0) + 1
    return counts


def _deduplicate_issues(issues: Sequence[Issue]) -> List[Issue]:
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
