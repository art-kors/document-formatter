from chromadb import PersistentClient
from typing import List
import hashlib


class VectorStore:
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.client = PersistentClient(path=persist_directory)
        self.collection = None

    def create_collection(self, name: str = "document_rules"):
        """Создание коллекции"""
        self.collection = self.client.get_or_create_collection(name=name)

    def add_documents(self, texts: List[str], metadatas: List[dict] = None):
        """Добавление документов в векторное хранилище"""
        if not self.collection:
            self.create_collection()

        ids = [hashlib.md5(text.encode()).hexdigest() for text in texts]

        self.collection.add(
            documents=texts,
            metadatas=metadatas,
            ids=ids
        )

    def query(self, query_text: str, n_results: int = 5) -> List:
        """Поиск похожих документов"""
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results
        )
        return results

    def add_entity(self, entity):
        """Добавление сущности из графа"""
        metadata = {
            'entity_id': entity.id,
            'entity_type': entity.type,
            'entity_name': entity.name
        }
        self.add_documents([entity.content], [metadata])