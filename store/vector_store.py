# vector_store.py
from chromadb import PersistentClient
from typing import List, TYPE_CHECKING
import hashlib

if TYPE_CHECKING:
    from llm import MistralLLM


class VectorStore:
    def __init__(self, llm_client: "MistralLLM", persist_directory: str = "./chroma_db"):
        self.client = PersistentClient(path=persist_directory)
        self.collection = None
        self.llm = llm_client

    def create_collection(self, name: str = "document_rules"):
        self.collection = self.client.get_or_create_collection(name=name)

    def add_documents(self, texts: List[str], metadatas: List[dict] = None):
        if not self.collection:
            self.create_collection()

        # Генерируем эмбеддинги через LLM клиент
        embeddings = [self.llm.get_embedding(text) for text in texts]

        ids = [hashlib.md5(text.encode()).hexdigest() for text in texts]

        # Фильтруем пустые эмбеддинги, если были ошибки
        valid_ids, valid_texts, valid_embeddings, valid_metadatas = [], [], [], []
        for i, emb in enumerate(embeddings):
            if emb:
                valid_ids.append(ids[i])
                valid_texts.append(texts[i])
                valid_embeddings.append(emb)
                if metadatas:
                    valid_metadatas.append(metadatas[i])

        if valid_ids:
            self.collection.add(
                documents=valid_texts,
                embeddings=valid_embeddings,
                metadatas=valid_metadatas if metadatas else None,
                ids=valid_ids
            )

    def query(self, query_text: str, n_results: int = 5) -> List:
        query_embedding = self.llm.get_embedding(query_text)
        if not query_embedding:
            return None

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )
        return results

    def add_entity(self, entity):
        metadata = {
            'entity_id': entity.id,
            'entity_type': entity.type,
            'entity_name': entity.name
        }
        self.add_documents([entity.content], [metadata])