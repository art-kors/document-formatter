# pipeline.py
from typing import Dict, List
from store.entity_extractor import EntityExtractor
from store.graph import KnowledgeGraph
from store.vector_store import VectorStore
from store.engine import GraphRAGEngine
from core.parsers import simple_text_parser
from core.llm import MistralLLM


class DocumentPipeline:
    def __init__(self, llm: MistralLLM):
        self.llm = llm
        self.rag_engine = None
        self.kg = None

    def process_instruction(self, text: str):
        """Обработка инструкции и построение базы знаний."""

        # 1. Парсинг текста
        parsed_doc = simple_text_parser(text)

        # 2. Извлечение сущностей
        extractor = EntityExtractor(llm_client=self.llm)
        entities, relations = extractor.extract_from_parsed(parsed_doc)

        # 3. Построение графа
        self.kg = KnowledgeGraph()
        self.kg.build_from_entities(entities, relations)

        # 4. Векторное индексирование
        vs = VectorStore(llm_client=self.llm)
        vs.create_collection("document_rules")
        for entity in entities:
            vs.add_entity(entity)

        # 5. Инициализация RAG движка
        self.rag_engine = GraphRAGEngine(self.kg, vs, self.llm)

        return {
            "status": "indexed",
            "entities_count": len(entities),
            "relations_count": len(relations)
        }

    def query(self, question: str) -> str:
        if not self.rag_engine:
            return "Ошибка: База знаний не инициализирована."
        return self.rag_engine.query(question)

    def get_structure(self) -> List[Dict]:
        if not self.rag_engine:
            return []
        return self.rag_engine.get_document_structure()