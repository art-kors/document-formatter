# entity_extractor.py
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
import json


class Entity(BaseModel):
    id: str
    name: str
    type: str
    content: str
    metadata: Dict = Field(default_factory=dict)


class Relation(BaseModel):
    source: str
    target: str
    type: str
    properties: Dict = Field(default_factory=dict)


class EntityExtractor:
    def __init__(self, llm_client=None):
        self.llm = llm_client
        self.entities: List[Entity] = []
        self.relations: List[Relation] = []

    def extract_from_parsed(self, parsed_doc: Dict) -> tuple:
        if 'sections' in parsed_doc:
            for idx, section in enumerate(parsed_doc['sections']):
                content = section.get('content', [])
                if isinstance(content, list):
                    content = '\n'.join(content)

                entity = Entity(
                    id=f"section_{idx}",
                    name=section.get('title', f'Section {idx}'),
                    type="section",
                    content=content,
                    metadata={'order': idx}
                )
                self.entities.append(entity)

        if 'rules' in parsed_doc:
            for idx, rule in enumerate(parsed_doc['rules']):
                entity = Entity(
                    id=f"rule_{idx}",
                    name=f"Правило {idx + 1}",
                    type="rule",
                    content=rule,
                    metadata={}
                )
                self.entities.append(entity)

        # Связи: секции идут друг за другом
        section_entities = [e for e in self.entities if e.type == 'section']
        for i in range(len(section_entities) - 1):
            relation = Relation(
                source=section_entities[i].id,
                target=section_entities[i + 1].id,
                type="follows",
                properties={'order': i}
            )
            self.relations.append(relation)

        return self.entities, self.relations