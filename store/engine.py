from typing import List, Dict
from knowledge_graph import KnowledgeGraph
from vector_store import VectorStore


class GraphRAGEngine:
    def __init__(self, knowledge_graph: KnowledgeGraph, vector_store: VectorStore):
        self.graph = knowledge_graph
        self.vector_store = vector_store
        self.context_window = 2000

    def retrieve(self, query: str, top_k: int = 5) -> Dict:
        """
        Гибридный поиск: векторный + графовый
        """
        # 1. Векторный поиск
        vector_results = self.vector_store.query(query, n_results=top_k)

        # 2. Извлекаем entity_id из результатов
        entity_ids = []
        if vector_results and 'metadatas' in vector_results:
            for metadata_list in vector_results['metadatas']:
                for metadata in metadata_list:
                    if 'entity_id' in metadata:
                        entity_ids.append(metadata['entity_id'])

        # 3. Графовый поиск - расширяем контекст через связи
        expanded_entities = set(entity_ids)
        for entity_id in entity_ids:
            neighbors = self.graph.get_neighbors(entity_id, depth=2)
            expanded_entities.update(neighbors)

        # 4. Собираем контекст
        context = []
        for entity_id in expanded_entities:
            if entity_id in self.graph.graph.nodes():
                node_data = self.graph.graph.nodes[entity_id]
                context.append({
                    'id': entity_id,
                    'name': node_data.get('name', ''),
                    'type': node_data.get('type', ''),
                    'content': node_data.get('content', '')
                })

        return {
            'query': query,
            'context': context,
            'vector_results': vector_results,
            'graph_entities': list(expanded_entities)
        }

    def generate_answer(self, query: str, context: List[Dict]) -> str:
        """
        Генерация ответа с использованием LLM
        """
        # Формируем промпт
        context_text = "\n\n".join([
            f"[{item['type'].upper()}] {item['name']}:\n{item['content']}"
            for item in context[:10]  # Ограничиваем контекст
        ])

        prompt = f"""
        Ты помощник по правилам оформления документов.

        КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ:
        {context_text}

        ВОПРОС ПОЛЬЗОВАТЕЛЯ:
        {query}

        Дай точный ответ на основе предоставленного контекста.
        Если информации недостаточно, скажи об этом.

        ОТВЕТ:
        """

        # Здесь вызов к LLM
        # response = llm.generate(prompt)
        # return response

        return f"[LLM ответ на основе {len(context)} сущностей]"

    def query(self, question: str) -> str:
        """Полный цикл RAG запроса"""
        retrieval_results = self.retrieve(question)
        answer = self.generate_answer(question, retrieval_results['context'])
        return answer

    def get_document_structure(self) -> List[Dict]:
        """Получение структуры документа из графа"""
        sections = []
        for node_id, data in self.graph.graph.nodes(data=True):
            if data.get('type') == 'section':
                sections.append({
                    'id': node_id,
                    'name': data.get('name', ''),
                    'order': data.get('metadata', {}).get('order', 0)
                })

        return sorted(sections, key=lambda x: x.get('order', 0))