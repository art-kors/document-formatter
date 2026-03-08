import os
import hashlib
from typing import List, Optional
from mistralai import Mistral
import chromadb


class Agent:
    def __init__(
            self,
            api_key: Optional[str] = None,
            model: str = "mistral-small-latest",
            embedding_model: str = "mistral-embed",
            persist_directory: str = "./db_storage"
    ):
        """
        Initialize the RAG Agent.
        """
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY not found.")

        self.client = Mistral(api_key=self.api_key)
        self.model = model
        self.embedding_model = embedding_model

        # Initialize ChromaDB (Persistent)
        self.chroma_client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.chroma_client.get_or_create_collection(name="rag_collection")

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """Simple text chunker to split documents into manageable pieces."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            # Try to break at a space to avoid cutting words in half
            if end < len(text):
                last_space = chunk.rfind(' ')
                if last_space != -1:
                    end = start + last_space
                    chunk = text[start:end]

            chunks.append(chunk.strip())
            start = end - overlap
        return chunks

    def _get_embedding(self, text: str) -> List[float]:
        """Generate embedding vector using Mistral API."""
        response = self.client.embeddings.create(
            model=self.embedding_model,
            inputs=[text]
        )
        return response.data[0].embedding

    def ingest_documents(self, documents: List[dict]):
        """
        Ingest documents into the Vector Store.

        Args:
            documents: List of dicts like [{"content": "text...", "id": "unique_id"}, ...]
        """
        print(f"Ingesting {len(documents)} documents...")

        ids = []
        embeddings = []
        metadatas = []
        documents_content = []

        for doc in documents:
            # Create a unique ID if not provided
            doc_id = doc.get("id") or hashlib.md5(doc["content"].encode()).hexdigest()

            # Chunk the content
            chunks = self._chunk_text(doc["content"])

            for i, chunk in enumerate(chunks):
                # Create unique ID for chunk
                chunk_id = f"{doc_id}_chunk_{i}"

                # Skip if already exists (optional optimization)
                existing = self.collection.get(ids=[chunk_id])
                if existing['ids']:
                    continue

                ids.append(chunk_id)
                documents_content.append(chunk)
                metadatas.append({"source": doc.get("source", "unknown"), "chunk_index": i})
                embeddings.append(self._get_embedding(chunk))

        if ids:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents_content
            )
            print(f"Successfully added {len(ids)} chunks to vector store.")
        else:
            print("No new chunks to add.")

    def query(self, question: str, top_k: int = 3) -> str:
        """
        Query the agent. It retrieves context and generates an answer.
        """
        # 1. Embed the query
        query_embedding = self._get_embedding(question)

        # 2. Retrieve relevant chunks
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas"]
        )

        # 3. Format Context
        context_text = ""
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                context_text += f"[Source {i + 1}]: {doc}\n\n"
        else:
            context_text = "No relevant information found."

        # 4. Construct Prompt
        system_prompt = (
            "You are a helpful assistant. Answer the user's question ONLY based on the provided context below. "
            "If the answer is not in the context, say 'I don't have enough information to answer that.' "
            "Do not make things up."
        )

        user_prompt = f"Context:\n{context_text}\n\nQuestion: {question}"

        # 5. Generate Answer using Mistral Chat
        response = self.client.chat.complete(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )

        return response.choices[0].message.content