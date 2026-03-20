from dataclasses import dataclass
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

from app.llm.base import EmbeddingProvider
from app.parsing.document_parser import extract_text_from_pdf
from app.schemas.standard import ParsedStandard, StandardNode, StandardRelation, StandardRule
from app.standards.graph_builder import KnowledgeGraph
from app.standards.parser import parse_standard_text
from app.standards.storage import (
    graph_path_for,
    standard_cleaned_text_path_for,
    standard_parsed_path_for,
    standard_raw_text_path_for,
    standard_source_pdf_path_for,
)


ANNEX_LINE_PATTERN = re.compile(r"^Приложение\s+[А-ЯA-Z]$")
BIBLIOGRAPHY_LINE = "Библиография"
INTERNAL_REF_PATTERN = re.compile(r"\b\d+(?:\.\d+)+\b")
DEPENDENCY_CUE_PATTERN = re.compile(
    r"(?:в соответствии с|согласно|в порядке, установленном|в порядке, установленным|с учетом)\s+(\d+(?:\.\d+)*)",
    re.IGNORECASE,
)
REFERENCE_CUE_PATTERN = re.compile(
    r"(?:см\.?|смотри|в разделе|в подразделе|в пункте|раздел(?:е|ом)?|подраздел(?:е|ом)?|пункт(?:е|ом)?)\s+(\d+(?:\.\d+)*)",
    re.IGNORECASE,
)
CONSTRAINT_PREREQUISITES: Dict[str, List[str]] = {
    "caption_required": ["reference_required", "required_presence", "numbering", "generic"],
    "formatting": ["required_presence", "generic", "reference_required"],
    "placement": ["reference_required", "required_presence", "generic"],
    "numbering": ["required_presence", "generic"],
    "reference_required": ["required_presence", "generic"],
    "optional_allowed": ["generic"],
    "definition": ["generic"],
}


@dataclass
class StandardArtifacts:
    standard_id: str
    nodes: List[StandardNode]
    relations: List[StandardRelation]
    graph: KnowledgeGraph
    graph_path: str


@dataclass
class StandardIngestBundle:
    standard_id: str
    raw_text_path: str
    cleaned_text_path: str
    parsed_path: str
    graph_path: str
    nodes_count: int
    relations_count: int
    parsed: ParsedStandard


class StandardIngestor:
    def ingest_pdf(self, standard_id: str) -> StandardIngestBundle:
        self.extract_raw_text_from_pdf(standard_id)
        self.create_cleaned_text(standard_id)
        parsed = ParsedStandard.model_validate(self.create_parsed_standard(standard_id))
        artifacts = self._build_graph_artifacts(standard_id, parsed)
        return StandardIngestBundle(
            standard_id=standard_id,
            raw_text_path=standard_raw_text_path_for(standard_id),
            cleaned_text_path=standard_cleaned_text_path_for(standard_id),
            parsed_path=standard_parsed_path_for(standard_id),
            graph_path=artifacts.graph_path,
            nodes_count=len(artifacts.nodes),
            relations_count=len(artifacts.relations),
            parsed=parsed,
        )

    def extract_raw_text_from_pdf(self, standard_id: str) -> str:
        source_path = standard_source_pdf_path_for(standard_id)
        if not Path(source_path).exists():
            raise FileNotFoundError(f"Standard PDF not found: {source_path}")

        file_bytes = Path(source_path).read_bytes()
        raw_text = extract_text_from_pdf(file_bytes)
        Path(standard_raw_text_path_for(standard_id)).write_text(raw_text, encoding="utf-8")
        return raw_text

    def create_cleaned_text(self, standard_id: str) -> str:
        raw_path = Path(standard_raw_text_path_for(standard_id))
        if not raw_path.exists():
            raw_text = self.extract_raw_text_from_pdf(standard_id)
        else:
            raw_text = raw_path.read_text(encoding="utf-8")

        cleaned_text = self.clean_standard_text(raw_text)
        Path(standard_cleaned_text_path_for(standard_id)).write_text(cleaned_text, encoding="utf-8")
        return cleaned_text

    def create_parsed_standard(self, standard_id: str) -> dict:
        cleaned_path = Path(standard_cleaned_text_path_for(standard_id))
        if not cleaned_path.exists():
            cleaned_text = self.create_cleaned_text(standard_id)
        else:
            cleaned_text = cleaned_path.read_text(encoding="utf-8")

        parsed = parse_standard_text(cleaned_text)
        validated = ParsedStandard.model_validate(parsed)
        Path(standard_parsed_path_for(standard_id)).write_text(
            validated.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return validated.model_dump()

    def clean_standard_text(self, raw_text: str) -> str:
        text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("-\n", "")
        text = re.sub(r"\n{3,}", "\n\n", text)

        cleaned_lines: list[str] = []
        for original_line in text.split("\n"):
            line = re.sub(r"\s+", " ", original_line).strip()
            if not line:
                cleaned_lines.append("")
                continue
            if self._is_service_line(line):
                continue
            cleaned_lines.append(line)

        merged_blocks: list[str] = []
        buffer = ""
        for line in cleaned_lines:
            if not line:
                if buffer:
                    merged_blocks.append(buffer.strip())
                    buffer = ""
                continue

            if self._starts_new_block(line):
                if buffer:
                    merged_blocks.append(buffer.strip())
                    buffer = ""
                merged_blocks.append(line.strip())
                continue

            if not buffer:
                buffer = line
                continue

            buffer = f"{buffer} {line}"

        if buffer:
            merged_blocks.append(buffer.strip())

        normalized_blocks: list[str] = []
        for block in merged_blocks:
            normalized_blocks.extend(self._split_inline_markers(block))

        cleaned_text = "\n\n".join(block for block in normalized_blocks if block)
        cleaned_text = re.sub(r"[ \t]+", " ", cleaned_text)
        cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)
        return cleaned_text.strip()

    def _split_inline_markers(self, block: str) -> list[str]:
        parts = [block]
        for marker in [r"Приложение\s+[А-ЯA-Z]", r"Библиография"]:
            next_parts: list[str] = []
            pattern = re.compile(rf"(?<!^)({marker})")
            for part in parts:
                match = pattern.search(part)
                if not match:
                    next_parts.append(part)
                    continue
                head = part[: match.start(1)].strip()
                tail = part[match.start(1) :].strip()
                if head:
                    next_parts.append(head)
                if tail:
                    next_parts.append(tail)
            parts = next_parts
        return parts

    def _is_service_line(self, line: str) -> bool:
        ascii_patterns = [
            r"^For Staff Page \d+$",
            r"^INTERSTATE COUNCIL FOR STANDARDIZATION,$",
            r"^METROLOGY AND CERTIFICATION$",
            r"^\d{1,2}:\d{2}$",
            r"^[\"'`]+$",
        ]
        if any(re.match(pattern, line) for pattern in ascii_patterns):
            return True

        lowered = line.lower()
        if lowered.startswith("system of standards on information"):
            return True
        if line.startswith("Документ предоставлен"):
            return True
        if line.startswith("Дата сохранения:"):
            return True

        return False

    def _starts_new_block(self, line: str) -> bool:
        if re.match(r"^\d+(\.\d+)*\s+.+$", line):
            return True
        if ANNEX_LINE_PATTERN.match(line) or line == BIBLIOGRAPHY_LINE:
            return True
        if len(line) <= 120 and line.upper() == line and any(ch.isalpha() for ch in line):
            return True
        return False

    def ingest_text(
        self,
        standard_id: str,
        standard_text: str,
        embedding_provider: EmbeddingProvider,
    ) -> StandardArtifacts:
        del embedding_provider
        parsed = ParsedStandard.model_validate(parse_standard_text(standard_text))
        return self._build_graph_artifacts(standard_id, parsed)

    def _build_graph_artifacts(self, standard_id: str, parsed: ParsedStandard) -> StandardArtifacts:
        nodes: List[StandardNode] = []
        relations: List[StandardRelation] = []

        for idx, section in enumerate(parsed.sections):
            nodes.append(
                StandardNode(
                    id=section.id,
                    name=section.title or f"Section {idx}",
                    type="section",
                    content=section.text,
                    metadata={"order": idx, "number": section.number},
                )
            )

        for idx, rule in enumerate(parsed.rules):
            nodes.append(
                StandardNode(
                    id=rule.id,
                    name=rule.title or f"Rule {idx + 1}",
                    type="rule",
                    content=rule.content or rule.title,
                    metadata={
                        "section_id": rule.section_id,
                        "section_title": rule.section_title,
                        "number": rule.number,
                        "object_type": rule.object_type,
                        "constraint_type": rule.constraint_type,
                        "keywords": rule.keywords,
                    },
                )
            )

        object_types = sorted({rule.object_type for rule in parsed.rules if rule.object_type != "generic"})
        for object_type in object_types:
            nodes.append(
                StandardNode(
                    id=f"object_type::{object_type}",
                    name=object_type,
                    type="object_type",
                    content=f"Rules applicable to {object_type}",
                    metadata={"object_type": object_type},
                )
            )

        constraint_types = sorted({rule.constraint_type for rule in parsed.rules if rule.constraint_type != "generic"})
        for constraint_type in constraint_types:
            nodes.append(
                StandardNode(
                    id=f"constraint::{constraint_type}",
                    name=constraint_type,
                    type="constraint",
                    content=f"Constraint group {constraint_type}",
                    metadata={"constraint_type": constraint_type},
                )
            )

        keyword_nodes_added = set()
        for rule in parsed.rules:
            for keyword in rule.keywords:
                keyword_id = f"keyword::{keyword}"
                if keyword_id in keyword_nodes_added:
                    continue
                nodes.append(
                    StandardNode(
                        id=keyword_id,
                        name=keyword,
                        type="keyword",
                        content=keyword,
                        metadata={"keyword": keyword},
                    )
                )
                keyword_nodes_added.add(keyword_id)

        section_nodes = [node for node in nodes if node.type == "section"]
        for idx in range(len(section_nodes) - 1):
            relations.append(
                StandardRelation(
                    source=section_nodes[idx].id,
                    target=section_nodes[idx + 1].id,
                    type="follows",
                    properties={"order": idx},
                )
            )

        rules_by_section: Dict[str, List[StandardRule]] = {}
        rules_by_object: Dict[str, List[StandardRule]] = {}
        rules_by_constraint: Dict[str, List[StandardRule]] = {}
        rule_number_to_id = {rule.number: rule.id for rule in parsed.rules}
        section_number_to_id = {section.number: section.id for section in parsed.sections}

        for rule in parsed.rules:
            relations.append(
                StandardRelation(
                    source=rule.section_id,
                    target=rule.id,
                    type="contains",
                    properties={},
                )
            )

            rules_by_section.setdefault(rule.section_id, []).append(rule)

            if rule.object_type != "generic":
                object_node_id = f"object_type::{rule.object_type}"
                relations.append(
                    StandardRelation(
                        source=rule.id,
                        target=object_node_id,
                        type="applies_to",
                        properties={},
                    )
                )
                relations.append(
                    StandardRelation(
                        source=rule.section_id,
                        target=object_node_id,
                        type="covers",
                        properties={},
                    )
                )
                rules_by_object.setdefault(rule.object_type, []).append(rule)

            if rule.constraint_type != "generic":
                constraint_node_id = f"constraint::{rule.constraint_type}"
                relations.append(
                    StandardRelation(
                        source=rule.id,
                        target=constraint_node_id,
                        type="constrains",
                        properties={},
                    )
                )
                rules_by_constraint.setdefault(rule.constraint_type, []).append(rule)

            for keyword in rule.keywords:
                relations.append(
                    StandardRelation(
                        source=rule.id,
                        target=f"keyword::{keyword}",
                        type="mentions",
                        properties={},
                    )
                )

        for section_rules in rules_by_section.values():
            ordered_rules = sorted(section_rules, key=lambda item: _rule_sort_key(item.number))
            for left, right in zip(ordered_rules, ordered_rules[1:]):
                relations.append(
                    StandardRelation(
                        source=left.id,
                        target=right.id,
                        type="rule_follows",
                        properties={},
                    )
                )

        for rule_group, relation_type in ((rules_by_object, "same_object_type"), (rules_by_constraint, "same_constraint_type")):
            for grouped_rules in rule_group.values():
                ordered_rules = sorted(grouped_rules, key=lambda item: _rule_sort_key(item.number))
                for left, right in zip(ordered_rules, ordered_rules[1:]):
                    relations.append(
                        StandardRelation(
                            source=left.id,
                            target=right.id,
                            type=relation_type,
                            properties={},
                        )
                    )

        for rule in parsed.rules:
            for target_id, relation_type, reference_number in self._extract_logical_links(
                rule,
                rule_number_to_id=rule_number_to_id,
                section_number_to_id=section_number_to_id,
            ):
                relations.append(
                    StandardRelation(
                        source=rule.id,
                        target=target_id,
                        type=relation_type,
                        properties={"reference_number": reference_number},
                    )
                )

        for object_rules in rules_by_object.values():
            relations.extend(self._build_prerequisite_relations(object_rules))

        graph = KnowledgeGraph()
        graph.build_from_entities(nodes, relations)
        graph_path = graph_path_for(standard_id)
        graph.save(graph_path)
        return StandardArtifacts(
            standard_id=standard_id,
            nodes=nodes,
            relations=relations,
            graph=graph,
            graph_path=graph_path,
        )

    def _extract_logical_links(
        self,
        rule: StandardRule,
        *,
        rule_number_to_id: Dict[str, str],
        section_number_to_id: Dict[str, str],
    ) -> List[Tuple[str, str, str]]:
        text = f"{rule.title} {rule.content}"
        links: List[Tuple[str, str, str]] = []
        seen = set()

        for pattern, relation_type in ((DEPENDENCY_CUE_PATTERN, "depends_on"), (REFERENCE_CUE_PATTERN, "references")):
            for match in pattern.finditer(text):
                reference_number = match.group(1)
                target_id = _resolve_reference_target(reference_number, rule_number_to_id, section_number_to_id)
                if not target_id or target_id == rule.id:
                    continue
                key = (target_id, relation_type, reference_number)
                if key in seen:
                    continue
                links.append((target_id, relation_type, reference_number))
                seen.add(key)
                if relation_type == "depends_on":
                    ref_key = (target_id, "references", reference_number)
                    if ref_key not in seen:
                        links.append((target_id, "references", reference_number))
                        seen.add(ref_key)

        for reference_number in INTERNAL_REF_PATTERN.findall(text):
            target_id = _resolve_reference_target(reference_number, rule_number_to_id, section_number_to_id)
            if not target_id or target_id == rule.id:
                continue
            key = (target_id, "references", reference_number)
            if key in seen:
                continue
            links.append((target_id, "references", reference_number))
            seen.add(key)

        return links

    def _build_prerequisite_relations(self, object_rules: List[StandardRule]) -> List[StandardRelation]:
        relations: List[StandardRelation] = []
        ordered_rules = sorted(object_rules, key=lambda item: _rule_sort_key(item.number))
        for index, rule in enumerate(ordered_rules):
            desired_constraints = CONSTRAINT_PREREQUISITES.get(rule.constraint_type, [])
            if not desired_constraints:
                continue
            prerequisites = self._find_prerequisite_candidates(ordered_rules[:index], desired_constraints)
            seen_targets = set()
            for prerequisite_rule in prerequisites:
                if prerequisite_rule.id in seen_targets or prerequisite_rule.id == rule.id:
                    continue
                relations.append(
                    StandardRelation(
                        source=rule.id,
                        target=prerequisite_rule.id,
                        type="prerequisite",
                        properties={"object_type": rule.object_type},
                    )
                )
                seen_targets.add(prerequisite_rule.id)
        return relations

    def _find_prerequisite_candidates(
        self,
        previous_rules: List[StandardRule],
        desired_constraints: List[str],
    ) -> List[StandardRule]:
        candidates: List[StandardRule] = []
        for constraint in desired_constraints:
            matched = [rule for rule in previous_rules if rule.constraint_type == constraint]
            if matched:
                candidates.append(matched[-1])
        return candidates


def _resolve_reference_target(
    reference_number: str,
    rule_number_to_id: Dict[str, str],
    section_number_to_id: Dict[str, str],
) -> Optional[str]:
    if reference_number in rule_number_to_id:
        return rule_number_to_id[reference_number]
    if reference_number in section_number_to_id:
        return section_number_to_id[reference_number]
    return None


def _rule_sort_key(number: str) -> List[int]:
    parts: List[int] = []
    for part in number.split('.'):
        digits = ''.join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return parts
