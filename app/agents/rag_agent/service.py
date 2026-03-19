"""
GraphRAG Service with IndexRAG enhancements.

This module provides:
- Standard GraphRAG functionality (unchanged)
- IndexRAG pipeline for cross-document reasoning
- Universal document loading for various formats

Usage:
    # Basic usage (unchanged)
    service = GraphRAGService(llm, embeddings, registry)
    service.process_instruction(standard_text, "GOST 7.32-2017")
    result = service.query("Как оформить рисунок?")

    # With IndexRAG
    service = GraphRAGService(llm, embeddings, registry)
    service.process_instruction_with_indexrag(standard_text, "GOST 7.32-2017")
    result = service.query_with_indexrag("Как оформить рисунок?")

    # Universal document loading
    docs = service.load_documents("path/to/standards/")
    service.load_and_index("path/to/standard.pdf")
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union, TYPE_CHECKING

from .retriever import (
    DEFAULT_GRAPH_CONFIG,
    DEFAULT_INDEXRAG_CONFIG,
    GraphRAGConfig,
    GraphRAGRetriever,
    IndexRAGConfig,
    VectorIndex,
)

# =============================================================================
# Type hints for external dependencies (avoiding hard imports)
# =============================================================================

if TYPE_CHECKING:
    from app.llm.base import EmbeddingProvider, LLMProvider
    from app.schemas.agent_result import AgentResult
    from app.schemas.document import DocumentInput
    from app.standards.graph_builder import KnowledgeGraph
    from app.standards.ingest import StandardArtifacts, StandardIngestor
    from app.standards.registry import StandardRegistry


# =============================================================================
# Document Loaders (Universal document ingestion)
# =============================================================================

class DocumentLoader(ABC):
    """Abstract base class for document loaders."""

    @abstractmethod
    def load(self, source: Union[str, Path], **kwargs) -> List[Dict[str, Any]]:
        """
        Load documents from a source.

        Returns:
            List of documents, each with 'id', 'text', 'metadata'
        """
        pass

    @abstractmethod
    def supports(self, source: Union[str, Path]) -> bool:
        """Check if this loader supports the given source."""
        pass


class TextLoader(DocumentLoader):
    """Loader for plain text files."""

    def load(self, source: Union[str, Path], **kwargs) -> List[Dict[str, Any]]:
        path = Path(source)
        with open(path, 'r', encoding=kwargs.get('encoding', 'utf-8')) as f:
            text = f.read()

        return [{
            'id': path.stem,
            'text': text,
            'metadata': {
                'source': str(path),
                'filename': path.name,
                'extension': path.suffix,
            }
        }]

    def supports(self, source: Union[str, Path]) -> bool:
        return Path(source).suffix.lower() == '.txt'


class MarkdownLoader(DocumentLoader):
    """Loader for Markdown files with section splitting."""

    def load(self, source: Union[str, Path], **kwargs) -> List[Dict[str, Any]]:
        import re
        path = Path(source)
        with open(path, 'r', encoding=kwargs.get('encoding', 'utf-8')) as f:
            text = f.read()

        # Split by headers
        sections = self._split_by_headers(text)

        documents = []
        for idx, section in enumerate(sections):
            documents.append({
                'id': f"{path.stem}_section_{idx}",
                'text': section['content'],
                'metadata': {
                    'source': str(path),
                    'filename': path.name,
                    'section_title': section.get('title', ''),
                    'section_idx': idx,
                }
            })

        return documents if documents else [{
            'id': path.stem,
            'text': text,
            'metadata': {'source': str(path), 'filename': path.name}
        }]

    def _split_by_headers(self, text: str) -> List[Dict]:
        import re
        sections = []
        current = {'title': '', 'content': ''}

        for line in text.split('\n'):
            header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if header_match:
                if current['content'].strip():
                    sections.append(current)
                current = {'title': header_match.group(2), 'content': ''}
            else:
                current['content'] += line + '\n'

        if current['content'].strip():
            sections.append(current)

        return sections

    def supports(self, source: Union[str, Path]) -> bool:
        return Path(source).suffix.lower() in ('.md', '.markdown')


class PDFLoader(DocumentLoader):
    """Loader for PDF files (requires pdfplumber or PyMuPDF)."""

    def load(self, source: Union[str, Path], **kwargs) -> List[Dict[str, Any]]:
        path = Path(source)
        text = self._extract_text(path, **kwargs)

        return [{
            'id': path.stem,
            'text': text,
            'metadata': {
                'source': str(path),
                'filename': path.name,
                'extension': '.pdf',
            }
        }]

    def _extract_text(self, path: Path, **kwargs) -> str:
        # Try pdfplumber first
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                return '\n\n'.join(page.extract_text() or '' for page in pdf.pages)
        except ImportError:
            pass

        # Try PyMuPDF as fallback
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            return '\n\n'.join(page.get_text() for page in doc)
        except ImportError:
            pass

        raise ImportError("PDF loading requires pdfplumber or PyMuPDF")

    def supports(self, source: Union[str, Path]) -> bool:
        return Path(source).suffix.lower() == '.pdf'


class JSONLoader(DocumentLoader):
    """Loader for JSON files with configurable text extraction."""

    def __init__(
            self,
            text_key: str = 'text',
            id_key: str = 'id',
            metadata_keys: Optional[List[str]] = None,
    ):
        self.text_key = text_key
        self.id_key = id_key
        self.metadata_keys = metadata_keys or []

    def load(self, source: Union[str, Path], **kwargs) -> List[Dict[str, Any]]:
        import json
        path = Path(source)
        with open(path, 'r', encoding=kwargs.get('encoding', 'utf-8')) as f:
            data = json.load(f)

        # Handle list or single document
        items = data if isinstance(data, list) else [data]

        documents = []
        for idx, item in enumerate(items):
            text = item.get(self.text_key, '')
            if not text:
                continue

            doc_id = item.get(self.id_key, f"{path.stem}_{idx}")
            metadata = {'source': str(path), 'filename': path.name}

            for key in self.metadata_keys:
                if key in item:
                    metadata[key] = item[key]

            documents.append({
                'id': doc_id,
                'text': text,
                'metadata': metadata,
            })

        return documents

    def supports(self, source: Union[str, Path]) -> bool:
        return Path(source).suffix.lower() == '.json'


class DirectoryLoader(DocumentLoader):
    """Loader for directories with multiple files."""

    def __init__(
            self,
            loaders: Optional[List[DocumentLoader]] = None,
            recursive: bool = True,
            extensions: Optional[List[str]] = None,
    ):
        self.loaders = loaders or []
        self.recursive = recursive
        self.extensions = extensions or ['.txt', '.md', '.json', '.pdf']

    def load(self, source: Union[str, Path], **kwargs) -> List[Dict[str, Any]]:
        path = Path(source)
        documents = []

        pattern = '**/*' if self.recursive else '*'
        for file_path in path.glob(pattern):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in self.extensions:
                continue

            for loader in self.loaders:
                if loader.supports(file_path):
                    documents.extend(loader.load(file_path, **kwargs))
                    break

        return documents

    def supports(self, source: Union[str, Path]) -> bool:
        return Path(source).is_dir()


class DocumentLoaderRegistry:
    """
    Registry for document loaders with automatic format detection.

    Supports:
    - Plain text (.txt)
    - Markdown (.md, .markdown)
    - PDF (.pdf) - requires pdfplumber or PyMuPDF
    - JSON (.json) - configurable key extraction
    - Directories (recursive loading)
    """

    def __init__(self):
        self._loaders: List[DocumentLoader] = []
        self._register_defaults()

    def _register_defaults(self):
        """Register default loaders."""
        self._loaders = [
            TextLoader(),
            MarkdownLoader(),
            PDFLoader(),
            JSONLoader(),
        ]

    def register(self, loader: DocumentLoader) -> None:
        """Register a custom loader."""
        self._loaders.append(loader)

    def load(self, source: Union[str, Path], **kwargs) -> List[Dict[str, Any]]:
        """Load documents from a source using the appropriate loader."""
        path = Path(source)

        # Handle directory
        if path.is_dir():
            return DirectoryLoader(loaders=self._loaders).load(source, **kwargs)

        # Find appropriate loader
        for loader in self._loaders:
            if loader.supports(source):
                return loader.load(source, **kwargs)

        # Fallback to text loader
        return TextLoader().load(source, **kwargs)


# =============================================================================
# GraphRAG Service (Extended with IndexRAG)
# =============================================================================

class GraphRAGService:
    """
    GraphRAG Service with IndexRAG enhancements.

    Original functionality preserved, extended with:
    - Universal document loading
    - IndexRAG pipeline for cross-document reasoning
    - Configurable parameters (no hardcoded values)

    Original methods (unchanged):
    - process_instruction()
    - query()
    - get_structure()
    - get_graph_path()
    - analyze()

    New methods:
    - process_instruction_with_indexrag()
    - add_document()
    - add_documents_batch()
    - query_with_indexrag()
    - retrieve_with_indexrag()
    - load_documents()
    - load_and_index()
    """

    def __init__(
            self,
            llm_provider: 'LLMProvider',
            embedding_provider: 'EmbeddingProvider',
            registry: 'StandardRegistry',
            graph_config: Optional[GraphRAGConfig] = None,
            indexrag_config: Optional[IndexRAGConfig] = None,
            persist_directory: Optional[str] = None,
    ):
        self.llm_provider = llm_provider
        self.embedding_provider = embedding_provider
        self.registry = registry

        # Configurations (removing hardcoded values)
        self._graph_config = graph_config or DEFAULT_GRAPH_CONFIG
        self._indexrag_config = indexrag_config or DEFAULT_INDEXRAG_CONFIG
        self._persist_directory = persist_directory or "./app/storage/chroma"

        # Standard components (imported lazily to avoid hard dependencies)
        self.ingestor: Optional['StandardIngestor'] = None
        self.artifacts: Optional['StandardArtifacts'] = None
        self.retriever: Optional[GraphRAGRetriever] = None

        # Document loader registry
        self._loader_registry = DocumentLoaderRegistry()

        # IndexRAG state
        self._indexed_documents: Dict[str, Dict] = {}
        self._indexrag_enabled = False

    @property
    def is_ready(self) -> bool:
        return self.retriever is not None and self.artifacts is not None

    @property
    def indexrag_ready(self) -> bool:
        """Check if IndexRAG indexing is complete."""
        return (
                self._indexrag_enabled
                and self.retriever is not None
                and self.retriever._indexrag_ready
        )

    def _get_ingestor(self) -> 'StandardIngestor':
        """Lazily initialize StandardIngestor."""
        if self.ingestor is None:
            from app.standards.ingest import StandardIngestor
            self.ingestor = StandardIngestor()
        return self.ingestor

    # =========================================================================
    # Document Loading Methods
    # =========================================================================

    def register_loader(self, loader: DocumentLoader) -> None:
        """Register a custom document loader."""
        self._loader_registry.register(loader)

    def load_documents(
            self,
            source: Union[str, Path, List[Union[str, Path]]],
            **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Universal document loading from various sources.

        Args:
            source: File path, directory, or list of paths
            **kwargs: Additional arguments passed to loaders
                - encoding: text encoding (default: utf-8)
                - text_key: JSON text field name (default: text)
                - id_key: JSON id field name (default: id)

        Returns:
            List of documents with 'id', 'text', 'metadata'

        Examples:
            # Single file
            docs = service.load_documents("standard.txt")

            # Directory (recursive)
            docs = service.load_documents("standards/")

            # Multiple files
            docs = service.load_documents(["a.txt", "b.md", "c.pdf"])

            # JSON with custom keys
            docs = service.load_documents("data.json", text_key="content", id_key="doc_id")
        """
        if isinstance(source, list):
            documents = []
            for src in source:
                documents.extend(self._loader_registry.load(src, **kwargs))
            return documents

        return self._loader_registry.load(source, **kwargs)

    def load_and_index(
            self,
            source: Union[str, Path, List[Union[str, Path]]],
            standard_name: Optional[str] = None,
            **kwargs,
    ) -> Dict:
        """
        Load documents and index them for RAG.

        Combines loading and indexing in one step.

        Args:
            source: File path, directory, or list of paths
            standard_name: Name for the standard (default: derived from source)
            **kwargs: Additional arguments for loaders
        """
        documents = self.load_documents(source, **kwargs)

        if not documents:
            return {
                "status": "error",
                "message": "No documents loaded",
                "documents_count": 0,
            }

        # Combine all documents for standard ingestion
        combined_text = "\n\n".join(doc['text'] for doc in documents)

        if standard_name is None:
            if isinstance(source, (str, Path)):
                standard_name = Path(source).stem
            else:
                standard_name = "loaded_standard"

        result = self.process_instruction(combined_text, standard_name)
        result["loaded_documents"] = len(documents)

        return result

    # =========================================================================
    # Standard Processing Methods (Original, unchanged)
    # =========================================================================

    def process_instruction(self, standard_text: str, standard_name: str) -> Dict:
        """Process and index a standard document (original method, unchanged)."""
        standard_id = self.registry.register_uploaded_standard(standard_name)

        ingestor = self._get_ingestor()
        self.artifacts = ingestor.ingest_text(
            standard_id=standard_id,
            standard_text=standard_text,
            embedding_provider=self.embedding_provider,
        )

        vector_index = VectorIndex(
            self.embedding_provider,
            persist_directory=self._persist_directory,
            collection_name=f"standard_{standard_id}",
            reset_collection=True,
        )
        vector_index.add_documents(
            texts=[node.content for node in self.artifacts.nodes],
            metadatas=[
                {
                    "entity_id": node.id,
                    "entity_type": node.type,
                    "entity_name": node.name,
                }
                for node in self.artifacts.nodes
            ],
        )

        self.retriever = GraphRAGRetriever(
            graph=self.artifacts.graph,
            vector_index=vector_index,
            llm_provider=self.llm_provider,
            graph_config=self._graph_config,
            indexrag_config=self._indexrag_config,
        )

        return {
            "status": "indexed",
            "standard_id": standard_id,
            "entities_count": len(self.artifacts.nodes),
            "relations_count": len(self.artifacts.relations),
        }

    # =========================================================================
    # IndexRAG Pipeline Methods
    # =========================================================================

    def process_instruction_with_indexrag(
            self,
            standard_text: str,
            standard_name: str,
            enable_bridging: bool = True,
            extract_from_sections: bool = True,
    ) -> Dict:
        """
        Process instruction using IndexRAG's two-stage pipeline.

        Stage 1: Extract AKUs and entities from each document
        Stage 2: Generate bridging facts for cross-document reasoning

        Paper: "IndexRAG identifies bridge entities shared across documents and
        generates bridging facts as independently retrievable units, requiring no
        additional training or fine-tuning."
        """
        standard_id = self.registry.register_uploaded_standard(standard_name)

        ingestor = self._get_ingestor()
        self.artifacts = ingestor.ingest_text(
            standard_id=standard_id,
            standard_text=standard_text,
            embedding_provider=self.embedding_provider,
        )

        vector_index = VectorIndex(
            self.embedding_provider,
            persist_directory=self._persist_directory,
            collection_name=f"standard_{standard_id}_indexrag",
            reset_collection=True,
        )

        # Add standard nodes to vector index
        vector_index.add_documents(
            texts=[node.content for node in self.artifacts.nodes],
            metadatas=[
                {
                    "entity_id": node.id,
                    "entity_type": node.type,
                    "entity_name": node.name,
                }
                for node in self.artifacts.nodes
            ],
        )

        self.retriever = GraphRAGRetriever(
            graph=self.artifacts.graph,
            vector_index=vector_index,
            llm_provider=self.llm_provider,
            graph_config=self._graph_config,
            indexrag_config=self._indexrag_config,
        )

        # IndexRAG Stage 1: Extract AKUs from each document section
        aku_total = 0
        entity_total = 0

        if extract_from_sections:
            for node in self.artifacts.nodes:
                if node.type in ["section", "rule"] and node.content:
                    result = self.retriever.index_document(
                        node.id,
                        node.content,
                        metadata={"node_type": node.type, "node_name": node.name}
                    )
                    aku_total += result["akus_extracted"]
                    entity_total += result["entities_found"]
                    self._indexed_documents[node.id] = result

        # IndexRAG Stage 2: Generate bridging facts
        bridging_result = {"bridge_entities_identified": 0, "bridging_facts_generated": 0}
        if enable_bridging:
            bridging_result = self.retriever.generate_bridging_facts()
            self._indexrag_enabled = True

        return {
            "status": "indexed_with_indexrag",
            "standard_id": standard_id,
            "entities_count": len(self.artifacts.nodes),
            "relations_count": len(self.artifacts.relations),
            "akus_extracted": aku_total,
            "entities_found": entity_total,
            "bridge_entities_identified": bridging_result["bridge_entities_identified"],
            "bridging_facts_generated": bridging_result["bridging_facts_generated"],
        }

    def add_document(
            self,
            document_id: str,
            text: str,
            metadata: Optional[Dict[str, Any]] = None,
            regenerate_bridging: bool = True,
    ) -> Dict:
        """
        Add a new document to the IndexRAG index.

        Performs Stage 1 (AKU extraction) and optionally updates bridging facts.

        Paper: "When a new document d_new is added, only Stage 1 for d_new and
        Stage 2 for affected bridge entities need to be re-executed."
        """
        if not self.retriever:
            raise RuntimeError("Knowledge base is not initialized yet")

        result = self.retriever.index_document(document_id, text, metadata)
        self._indexed_documents[document_id] = result

        # Re-generate bridging facts for affected entities
        bridging_result = {"bridging_facts_generated": 0}
        if regenerate_bridging:
            bridging_result = self.retriever.generate_bridging_facts()

        return {
            "document_id": document_id,
            "akus_extracted": result["akus_extracted"],
            "entities_found": result["entities_found"],
            "bridging_facts_updated": bridging_result["bridging_facts_generated"],
        }

    def add_documents_batch(
            self,
            documents: List[Dict[str, Any]],
            regenerate_bridging: bool = True,
    ) -> Dict:
        """
        Add multiple documents in batch.

        Args:
            documents: List of documents with 'id', 'text', optional 'metadata'
            regenerate_bridging: Whether to regenerate bridging facts after
        """
        if not self.retriever:
            raise RuntimeError("Knowledge base is not initialized yet")

        total_akus = 0
        total_entities = 0

        for doc in documents:
            doc_id = doc.get('id')
            text = doc.get('text', '')
            metadata = doc.get('metadata')

            if not doc_id or not text:
                continue

            result = self.retriever.index_document(doc_id, text, metadata)
            total_akus += result["akus_extracted"]
            total_entities += result["entities_found"]
            self._indexed_documents[doc_id] = result

        bridging_result = {"bridging_facts_generated": 0}
        if regenerate_bridging:
            bridging_result = self.retriever.generate_bridging_facts()

        return {
            "documents_added": len(documents),
            "total_akus_extracted": total_akus,
            "total_entities_found": total_entities,
            "bridging_facts_updated": bridging_result["bridging_facts_generated"],
        }

    def finalize_indexrag(self) -> Dict:
        """Generate bridging facts after all documents are indexed."""
        if not self.retriever:
            raise RuntimeError("Knowledge base is not initialized yet")

        result = self.retriever.generate_bridging_facts()
        self._indexrag_enabled = True

        return result

    # =========================================================================
    # Query Methods
    # =========================================================================

    def query(self, question: str) -> Dict:
        """Original query method (unchanged)."""
        if not self.retriever:
            raise RuntimeError("Knowledge base is not initialized yet")
        return self.retriever.answer(question)

    def query_with_indexrag(
            self,
            question: str,
            max_bridging_facts: Optional[int] = None,
    ) -> Dict:
        """
        Query using IndexRAG's enhanced retrieval with bridging facts.

        Paper: "Single-pass retrieval with pre-computed bridging facts enables
        cross-document reasoning without additional inference-time processing."

        Returns:
            Dict with:
            - answer: The generated answer
            - sources: List of source rules/sections
            - bridging_facts: List of bridging facts used
            - graph_entities_count: Number of graph entities involved
            - matched_signals: Query signal matches
        """
        if not self.retriever:
            raise RuntimeError("Knowledge base is not initialized yet")
        return self.retriever.answer_with_bridging(question, max_bridging_facts=max_bridging_facts)

    def retrieve_with_indexrag(
            self,
            question: str,
            top_k: Optional[int] = None,
            max_bridging_facts: Optional[int] = None,
    ) -> Dict:
        """
        Retrieve context using IndexRAG's enhanced retrieval.

        Returns both AKUs and bridging facts for cross-document reasoning.
        """
        if not self.retriever:
            raise RuntimeError("Knowledge base is not initialized yet")

        top_k = top_k or self._indexrag_config.default_top_k
        return self.retriever.retrieve_with_bridging(
            question,
            top_k=top_k,
            max_bridging_facts=max_bridging_facts,
        )

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_structure(self) -> List[Dict]:
        """Get document structure (original method, unchanged)."""
        if not self.artifacts:
            return []
        sections = []
        for node in self.artifacts.nodes:
            if node.type == "section":
                sections.append({
                    "id": node.id,
                    "name": node.name,
                    "order": node.metadata.get("order", 0),
                })
        return sorted(sections, key=lambda item: item["order"])

    def get_graph_path(self) -> Optional[str]:
        """Get graph storage path (original method, unchanged)."""
        if not self.artifacts:
            return None
        return self.artifacts.graph_path

    def get_indexrag_stats(self) -> Dict:
        """Get statistics about the IndexRAG index."""
        if not self.retriever or not self.retriever.vector_index:
            return {
                "akus_count": 0,
                "bridging_facts_count": 0,
                "entities_count": 0,
                "indexed_documents_count": 0,
                "indexrag_enabled": self._indexrag_enabled,
            }

        return {
            "akus_count": self.retriever.vector_index.aku_count,
            "bridging_facts_count": self.retriever.vector_index.bridging_fact_count,
            "entities_count": self.retriever.vector_index.entity_count,
            "indexed_documents_count": len(self._indexed_documents),
            "indexrag_enabled": self._indexrag_enabled,
        }

    def get_config(self) -> Dict:
        """Get current configuration."""
        return {
            "graph_config": {
                "edge_types": self._graph_config.edge_types,
                "edge_weights": self._graph_config.edge_weights,
                "support_context_edge_types": self._graph_config.support_context_edge_types,
            },
            "indexrag_config": {
                "entity_min_document_frequency": self._indexrag_config.entity_min_document_frequency,
                "entity_max_document_frequency": self._indexrag_config.entity_max_document_frequency,
                "max_source_documents": self._indexrag_config.max_source_documents,
                "max_facts_per_document": self._indexrag_config.max_facts_per_document,
                "default_max_bridging_facts": self._indexrag_config.default_max_bridging_facts,
                "language": self._indexrag_config.language,
            },
        }

    def update_config(
            self,
            graph_config: Optional[GraphRAGConfig] = None,
            indexrag_config: Optional[IndexRAGConfig] = None,
    ) -> None:
        """Update configuration (applied to new retrievers)."""
        if graph_config:
            self._graph_config = graph_config
        if indexrag_config:
            self._indexrag_config = indexrag_config

    def analyze(self, document: 'DocumentInput', standard_id: str) -> 'AgentResult':
        """Analyze a document against a standard (original method, unchanged)."""
        from app.agents.rag_agent.checker import analyze_document_against_standard
        return analyze_document_against_standard(document, standard_id)
