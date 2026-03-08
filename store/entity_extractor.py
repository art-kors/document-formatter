from typing import List, Dict, Optional
from pydantic import BaseModel, Field
import json


class Entity(BaseModel):
    """Сущность в графе знаний"""
    id: str
    name: str
    type: str  # rule, section, requirement, example, etc.
    content: str
    metadata: Dict = Field(default_factory=dict)


class Relation(BaseModel):
    """Связь между сущностями"""
    source: str
    target: str
    type: str  # requires, contains, example_of, etc.
    properties: Dict = Field(default_factory=dict)


class EntityExtractor:
    def __init__(self, llm_client=None):
        self.llm = llm_client
        self.entities: List[Entity] = []
        self.relations: List[Relation] = []

    def extract_from_parsed(self, parsed_doc: Dict) -> tuple:
        """Извлечение сущностей из распарсенного документа"""

        # Извлекаем секции как сущности
        if 'sections' in parsed_doc:
            for idx, section in enumerate(parsed_doc['sections']):
                entity = Entity(
                    id=f"section_{idx}",
                    name=section['title'],
                    type="section",
                    content='\n'.join(section['content']),
                    metadata={'order': idx}
                )
                self.entities.append(entity)

        # Извлекаем правила
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

        # Создаем связи между секциями
        for i in range(len(self.entities) - 1):
            if self.entities[i].type == 'section' and self.entities[i + 1].type == 'section':
                relation = Relation(
                    source=self.entities[i].id,
                    target=self.entities[i + 1].id,
                    type="follows",
                    properties={'order': i}
                )
                self.relations.append(relation)

        return self.entities, self.relations

    def extract_with_llm(self, text: str) -> tuple:
        """Извлечение сущностей с помощью LLM (более точное)"""
        prompt = f"""
        Извлеки сущности и связи из следующего текста о правилах оформления:

        {text[:3000]}  # Ограничиваем длину

        Верни JSON в формате:
        {{
            "entities": [
                {{"id": "unique_id", "name": "название", "type": "rule|section|requirement", "content": "текст"}}
            ],
            "relations": [
                {{"source": "id1", "target": "id2", "type": "requires|contains|example_of"}}
            ]
        }}
        """

        # Здесь будет вызов к LLM
        # response = self.llm.generate(prompt)
        # return self._parse_llm_response(response)

        pass