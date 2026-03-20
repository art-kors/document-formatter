# pipeline.py
from typing import Dict, List
from store.entity_extractor import EntityExtractor
from store.graph import KnowledgeGraph
from store.vector_store import VectorStore
from store.engine import GraphRAGEngine
from core.parsers import simple_text_parser
from core.llm import MistralLLM
import os


class DocumentPipeline:
    def __init__(self, llm: MistralLLM):
        self.llm = llm
        self.rag_engine = None
        self.kg = None

        # pipeline/pipeline.py

    def process_instruction(self, text: str):
        parsed_doc = simple_text_parser(text)

        extractor = EntityExtractor(llm_client=self.llm)
        entities, relations = extractor.extract_from_parsed(parsed_doc)

        self.kg = KnowledgeGraph()
        self.kg.build_from_entities(entities, relations)

        self.kg.save("knowledge_graph.json")
        print(f"Graph saved to knowledge_graph.json with {len(entities)} entities.")

        vs = VectorStore(llm_client=self.llm)

        # 4. Векторное индексирование
        vs = VectorStore(llm_client=self.llm)
        vs.create_collection("document_rules")
        for entity in entities:
            vs.add_entity(entity)

        # 5. Инициализация RAG движка
        self.rag_engine = GraphRAGEngine(self.kg, vs, self.llm)

        os.makedirs("storage", exist_ok=True)
        self.kg.save("storage/knowledge_graph.json")
        return {
            "status": "indexed",
            "entities_count": len(entities),
            "relations_count": len(relations)
        }

    def query(self, question: str) -> dict:
        if not self.rag_engine:
            return {"answer": "Ошибка: База знаний не инициализирована.", "sources": []}
        return self.rag_engine.query(question)

    def get_structure(self) -> List[Dict]:
        if not self.rag_engine:
            return []
        return self.rag_engine.get_document_structure()