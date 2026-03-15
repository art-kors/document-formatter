import re
from typing import Dict, List, Tuple


TOP_LEVEL_PATTERN = re.compile(r"^(\d+)\s+(.+)$")
SUBSECTION_PATTERN = re.compile(r"^(\d+\.\d+(?:\.\d+)*)\s+(.+)$")
ANNEX_START_PATTERN = re.compile(
    r"(?m)(^|\s)(Приложение\s+[А-ЯA-Z]|Библиография)\b"
)

OBJECT_PATTERNS = {
    "title_page": ["титульн", "титул"],
    "executors_list": ["список исполнител"],
    "abstract": ["реферат"],
    "contents": ["содержание"],
    "terms": ["термин", "определени"],
    "abbreviations": ["сокращен", "обозначен"],
    "introduction": ["введение"],
    "conclusion": ["заключени"],
    "references": ["список использованных источников", "библиографическ", "источник"],
    "appendix": ["приложени"],
    "figure": ["рисунк", "иллюстрац"],
    "table": ["таблиц"],
    "formula": ["формул", "уравнен"],
    "footnote": ["сноск"],
    "page_numbering": ["страниц", "лист", "нумерац страниц"],
    "heading": ["заголов", "подзаголов"],
    "section": ["раздел", "подраздел", "пункт"],
    "report": ["отчет", "отчета", "отчете"],
}

CONSTRAINT_PATTERNS = {
    "definition": ["это", "является"],
    "required_presence": ["должен содержать", "должен включать", "обязательн", "приводят следующие сведения"],
    "formatting": ["оформля", "печата", "шрифт", "полужир", "абзац", "интервал"],
    "numbering": ["нумерац", "обозначают", "арабскими цифрами"],
    "caption_required": ["должен иметь наименование", "должны иметь наименование", "подпись"],
    "reference_required": ["должны быть даны ссылки", "ссылк"],
    "placement": ["располага", "размеща", "следует помещать", "по центру"],
    "sequence": ["в порядке", "последовательн"],
    "language_requirement": ["языке", "русском языке", "национальном языке"],
    "optional_allowed": ["допускается", "могут включать", "могут быть"],
}

KEYWORD_CANDIDATES = [
    "рисунок",
    "иллюстрация",
    "таблица",
    "формула",
    "заголовок",
    "раздел",
    "подраздел",
    "приложение",
    "источник",
    "ссылка",
    "нумерация",
    "шрифт",
    "подпись",
    "страница",
    "абзац",
    "титульный лист",
    "реферат",
    "содержание",
    "заключение",
    "введение",
]


def _split_blocks(text: str) -> List[str]:
    blocks: List[str] = []
    for raw_block in text.split("\n\n"):
        stripped = raw_block.strip()
        if not stripped:
            continue
        blocks.extend(_split_inline_annexes(stripped))
    return blocks


def _split_inline_annexes(block: str) -> List[str]:
    match = ANNEX_START_PATTERN.search(block)
    if not match or match.start(2) == 0:
        return [block]

    head = block[: match.start(2)].strip()
    tail = block[match.start(2) :].strip()

    parts: List[str] = []
    if head:
        parts.append(head)
    if tail:
        parts.append(tail)
    return parts or [block]


def _count_cyrillic(text: str) -> int:
    return sum(1 for ch in text if 0x0400 <= ord(ch) <= 0x04FF)


def _count_latin(text: str) -> int:
    return sum(1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))


def _looks_like_heading(title: str) -> bool:
    if not title or len(title) > 140:
        return False
    lowered = title.lower()
    if "http" in lowered or "www." in lowered or "//" in title:
        return False

    cyrillic = _count_cyrillic(title)
    latin = _count_latin(title)
    if latin > cyrillic and cyrillic == 0:
        return False

    return True


def _split_heading_tail(rest: str) -> Tuple[str, str]:
    words = rest.split()
    if not words:
        return rest.strip(), ""

    title_words: List[str] = []
    seen_lowercase = False
    for index, word in enumerate(words):
        clean = word.strip('".,;:()[]')
        if index > 0 and seen_lowercase and clean and clean[0].isupper():
            return " ".join(title_words).strip(), " ".join(words[index:]).strip()

        title_words.append(word)
        if clean and clean[0].islower():
            seen_lowercase = True

    return " ".join(title_words).strip(), ""


def _parse_top_level_heading(block: str):
    match = TOP_LEVEL_PATTERN.match(block)
    if not match:
        return None

    number = match.group(1)
    title, tail = _split_heading_tail(match.group(2).strip())
    first_word = title.split()[0].strip('".,;:()[]') if title.split() else ""
    if first_word.isupper():
        return None
    if not _looks_like_heading(title):
        return None
    return number, title, tail


def _parse_subsection_heading(block: str):
    match = SUBSECTION_PATTERN.match(block)
    if not match:
        return None
    number = match.group(1)
    title, tail = _split_heading_tail(match.group(2).strip())
    return number, title, tail


def _is_annex_start(block: str) -> bool:
    match = ANNEX_START_PATTERN.search(block)
    return bool(match and match.start(2) == 0)


def _pick_best_match(text: str, patterns: Dict[str, List[str]], default: str) -> str:
    lowered = text.lower()
    for key, variants in patterns.items():
        if any(variant in lowered for variant in variants):
            return key
    return default


def _extract_keywords(text: str) -> List[str]:
    lowered = text.lower()
    keywords: List[str] = []
    for keyword in KEYWORD_CANDIDATES:
        if keyword in lowered:
            keywords.append(keyword)
    return keywords


def _infer_object_type(title: str, content: str, section_title: str) -> str:
    combined = " ".join([section_title, title, content]).strip()
    return _pick_best_match(combined, OBJECT_PATTERNS, "generic")


def _infer_constraint_type(title: str, content: str) -> str:
    combined = " ".join([title, content]).strip()
    lowered = combined.lower()

    if ("рисунк" in lowered or "иллюстрац" in lowered or "таблиц" in lowered) and (
        "наименование" in lowered or "подпись" in lowered
    ):
        return "caption_required"
    if "ссыл" in lowered and "долж" in lowered:
        return "reference_required"
    if "нумерац" in lowered:
        return "numbering"
    if "допускается" in lowered or "могут" in lowered:
        return "optional_allowed"

    return _pick_best_match(combined, CONSTRAINT_PATTERNS, "generic")


def parse_standard_text(text: str) -> Dict:
    blocks = _split_blocks(text)

    sections: List[Dict] = []
    rules: List[Dict] = []
    front_matter: List[str] = []
    annexes: List[str] = []
    examples: List[str] = []

    state = "front_matter"
    current_section = None
    section_index = 0
    rule_index = 0
    last_top_level_number = 0

    for block in blocks:
        if state == "annexes":
            annexes.append(block)
            continue

        if _is_annex_start(block):
            state = "annexes"
            annexes.append(block)
            current_section = None
            continue

        top_level = _parse_top_level_heading(block)
        if state == "front_matter":
            if top_level is None or int(top_level[0]) != 1:
                front_matter.append(block)
                continue
            state = "normative_body"

        if top_level is not None:
            number, title, tail = top_level
            number_int = int(number)
            if number_int == last_top_level_number + 1:
                last_top_level_number = number_int
                current_section = {
                    "id": f"std_sec_{section_index}",
                    "number": number,
                    "title": title,
                    "level": 1,
                    "content": [],
                }
                if tail:
                    current_section["content"].append(tail)
                sections.append(current_section)
                section_index += 1
                continue

            examples.append(block)
            continue

        subsection = _parse_subsection_heading(block)
        if subsection is not None and current_section is not None:
            number, title, tail = subsection
            content = tail or title
            section_title = current_section["title"]
            rule = {
                "id": f"gost_rule_{rule_index}",
                "number": number,
                "title": title,
                "section_id": current_section["id"],
                "section_title": section_title,
                "content": content,
                "object_type": _infer_object_type(title, content, section_title),
                "constraint_type": _infer_constraint_type(title, content),
                "keywords": _extract_keywords(" ".join([section_title, title, content])),
            }
            rules.append(rule)
            current_section["content"].append(block)
            rule_index += 1
            continue

        if current_section is not None:
            current_section["content"].append(block)
            if rules and rules[-1]["section_id"] == current_section["id"] and rules[-1]["content"] == rules[-1]["title"]:
                rules[-1]["content"] = block
                rules[-1]["object_type"] = _infer_object_type(
                    rules[-1]["title"],
                    block,
                    rules[-1]["section_title"],
                )
                rules[-1]["constraint_type"] = _infer_constraint_type(rules[-1]["title"], block)
                rules[-1]["keywords"] = _extract_keywords(
                    " ".join([rules[-1]["section_title"], rules[-1]["title"], block])
                )
        elif state == "front_matter":
            front_matter.append(block)
        else:
            examples.append(block)

    for section in sections:
        section["text"] = "\n\n".join(section.pop("content", []))

    return {
        "front_matter": front_matter,
        "sections": sections,
        "rules": rules,
        "annexes": annexes,
        "examples": examples,
    }
