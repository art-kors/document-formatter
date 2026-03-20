# engine.py
from typing import List, Dict, TYPE_CHECKING
from store.graph import KnowledgeGraph
from store.vector_store import VectorStore

if TYPE_CHECKING:
    from core.llm import MistralLLM


class GraphRAGEngine:
    def __init__(self, knowledge_graph: KnowledgeGraph, vector_store: VectorStore, llm_client: "MistralLLM"):
        self.graph = knowledge_graph
        self.vector_store = vector_store
        self.llm = llm_client
        self.context_window = 2000

    def retrieve(self, query: str, top_k: int = 5) -> Dict:
        vector_results = self.vector_store.query(query, n_results=top_k)
        if not vector_results:
            return {'context': [], 'vector_results': []}

        entity_ids = []
        if vector_results and 'metadatas' in vector_results:
            for metadata_list in vector_results['metadatas']:
                for metadata in metadata_list:
                    if 'entity_id' in metadata:
                        entity_ids.append(metadata['entity_id'])

        expanded_entities = set(entity_ids)
        for entity_id in entity_ids:
            neighbors = self.graph.get_neighbors(entity_id, depth=2)
            expanded_entities.update(neighbors)

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
        context_text = "\n\n".join([
            f"[{item['type'].upper()}] {item['name']}:\n{item['content']}"
            for item in context[:10]
        ])

        prompt = f"""
        Ты помощник по правилам оформления документов.
        Используй ТОЛЬКО следующий контекст для ответа на вопрос.

        КОНТЕКСТ:
        {context_text}

        ВОПРОС:
        {query}

        ОТВЕТ:
        """

        return self.llm.chat(prompt, save_history=False)

    def query(self, question: str) -> dict:  
        """Полный цикл RAG запроса"""
        retrieval_results = self.retrieve(question)
        answer = self.generate_answer(question, retrieval_results['context'])

        sources = []
        for item in retrieval_results['context'][:5]:  
            sources.append({
                "name": item.get('name', ''),
                "type": item.get('type', ''),
                "content": item.get('content', '')[:200] + "..." 
            })

        return {
            "answer": answer,
            "sources": sources,
            "graph_entities_count": len(retrieval_results['graph_entities'])
        }

    def get_document_structure(self) -> List[Dict]:
        sections = []
        for node_id, data in self.graph.graph.nodes(data=True):
            if data.get('type') == 'section':
                sections.append({
                    'id': node_id,
                    'name': data.get('name', ''),
                    'order': data.get('metadata', {}).get('order', 0)
                })
        return sorted(sections, key=lambda x: x.get('order', 0))