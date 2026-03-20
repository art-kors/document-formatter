"""GraphRAG agent package."""
"""
GraphRAG agent package with IndexRAG enhancements.

This package implements:
- Standard GraphRAG retrieval
- IndexRAG: Bridging Facts for Cross-Document Reasoning at Index Time
  Paper: https://arxiv.org/pdf/2603.16415

Main components:
- GraphRAGService: Main service for RAG operations
- GraphRAGRetriever: Retriever with graph-based and IndexRAG support
- VectorIndex: Vector storage with AKU and bridging fact support

IndexRAG components:
- AKUExtractor: Stage 1 - Extract Atomic Knowledge Units
- BridgingFactGenerator: Stage 2 - Generate cross-document bridging facts
- BalancedContextSelector: Control AKU/bridging fact proportion

Configuration:
- IndexRAGConfig: Configuration for IndexRAG components
- GraphRAGConfig: Configuration for graph retrieval

Document loading:
- DocumentLoader: Abstract base class for document loaders
- TextLoader, MarkdownLoader, PDFLoader, JSONLoader: Format-specific loaders
- DirectoryLoader: Load from directories
- DocumentLoaderRegistry: Automatic format detection

Usage:
    # Basic usage (unchanged)
    from rag_agent import GraphRAGService
    service = GraphRAGService(llm, embeddings, registry)
    service.process_instruction(standard_text, "GOST 7.32-2017")
    result = service.query("Как оформить рисунок?")

    # With IndexRAG
    service.process_instruction_with_indexrag(standard_text, "GOST 7.32-2017")
    result = service.query_with_indexrag("Как оформить рисунок?")

    # Universal document loading
    from rag_agent import DocumentLoaderRegistry
    registry = DocumentLoaderRegistry()
    docs = registry.load("path/to/standards/")

    # Or use service method
    docs = service.load_documents("path/to/standard.pdf")
    service.load_and_index("path/to/standard.pdf")
"""

# Import from retriever module
from .retriever import (
    # Original classes (names preserved)
    GraphRAGRetriever,
    VectorIndex,

    # IndexRAG data classes
    AtomicKnowledgeUnit,
    BridgingFact,
    EntityInfo,

    # IndexRAG components
    AKUExtractor,
    BridgingFactGenerator,
    BalancedContextSelector,

    # Configuration
    IndexRAGConfig,
    GraphRAGConfig,
    DEFAULT_INDEXRAG_CONFIG,
    DEFAULT_GRAPH_CONFIG,

    # Query hints (customizable, no hardcoding)
    DEFAULT_OBJECT_QUERY_HINTS,
    DEFAULT_CONSTRAINT_QUERY_HINTS,
)

# Import from service module
from .service import (
    # Main service
    GraphRAGService,

    # Document loaders
    DocumentLoader,
    TextLoader,
    MarkdownLoader,
    PDFLoader,
    JSONLoader,
    DirectoryLoader,
    DocumentLoaderRegistry,
)

# Import prompts
from .prompts import (
    # Original prompt
    ANSWER_PROMPT,

    # IndexRAG prompts
    AKU_EXTRACTION_PROMPT,
    AKU_EXTRACTION_PROMPT_RU,
    BRIDGING_FACT_PROMPT,
    BRIDGING_FACT_PROMPT_RU,
    IRCOT_REASONING_PROMPT,

    # Document loading prompts
    DOCUMENT_SUMMARY_PROMPT,
    DOCUMENT_SECTION_SPLIT_PROMPT,
    ENTITY_EXTRACTION_PROMPT,
)

__all__ = [
    # Main classes (original names preserved)
    "GraphRAGService",
    "GraphRAGRetriever",
    "VectorIndex",

    # IndexRAG data classes
    "AtomicKnowledgeUnit",
    "BridgingFact",
    "EntityInfo",

    # IndexRAG components
    "AKUExtractor",
    "BridgingFactGenerator",
    "BalancedContextSelector",

    # Configuration
    "IndexRAGConfig",
    "GraphRAGConfig",
    "DEFAULT_INDEXRAG_CONFIG",
    "DEFAULT_GRAPH_CONFIG",

    # Query hints (customizable)
    "DEFAULT_OBJECT_QUERY_HINTS",
    "DEFAULT_CONSTRAINT_QUERY_HINTS",

    # Document loaders
    "DocumentLoader",
    "TextLoader",
    "MarkdownLoader",
    "PDFLoader",
    "JSONLoader",
    "DirectoryLoader",
    "DocumentLoaderRegistry",

    # Prompts
    "ANSWER_PROMPT",
    "AKU_EXTRACTION_PROMPT",
    "AKU_EXTRACTION_PROMPT_RU",
    "BRIDGING_FACT_PROMPT",
    "BRIDGING_FACT_PROMPT_RU",
    "IRCOT_REASONING_PROMPT",
    "DOCUMENT_SUMMARY_PROMPT",
    "DOCUMENT_SECTION_SPLIT_PROMPT",
    "ENTITY_EXTRACTION_PROMPT",
]

# Version info
__version__ = "2.0.0"
__indexrag_paper__ = "https://arxiv.org/pdf/2603.16415"
"""
GraphRAG agent package with IndexRAG enhancements.

This package implements:
- Standard GraphRAG retrieval
- IndexRAG: Bridging Facts for Cross-Document Reasoning at Index Time
  Paper: https://arxiv.org/pdf/2603.16415

Main components:
- GraphRAGService: Main service for RAG operations
- GraphRAGRetriever: Retriever with graph-based and IndexRAG support
- VectorIndex: Vector storage with AKU and bridging fact support

IndexRAG components:
- AKUExtractor: Stage 1 - Extract Atomic Knowledge Units
- BridgingFactGenerator: Stage 2 - Generate cross-document bridging facts
- BalancedContextSelector: Control AKU/bridging fact proportion

Configuration:
- IndexRAGConfig: Configuration for IndexRAG components
- GraphRAGConfig: Configuration for graph retrieval

Document loading:
- DocumentLoader: Abstract base class for document loaders
- TextLoader, MarkdownLoader, PDFLoader, JSONLoader: Format-specific loaders
- DirectoryLoader: Load from directories
- DocumentLoaderRegistry: Automatic format detection

Usage:
    # Basic usage (unchanged)
    from rag_agent import GraphRAGService
    service = GraphRAGService(llm, embeddings, registry)
    service.process_instruction(standard_text, "GOST 7.32-2017")
    result = service.query("Как оформить рисунок?")

    # With IndexRAG
    service.process_instruction_with_indexrag(standard_text, "GOST 7.32-2017")
    result = service.query_with_indexrag("Как оформить рисунок?")

    # Universal document loading
    from rag_agent import DocumentLoaderRegistry
    registry = DocumentLoaderRegistry()
    docs = registry.load("path/to/standards/")

    # Or use service method
    docs = service.load_documents("path/to/standard.pdf")
    service.load_and_index("path/to/standard.pdf")
"""

# Import from retriever module
from .retriever import (
    # Original classes (names preserved)
    GraphRAGRetriever,
    VectorIndex,

    # IndexRAG data classes
    AtomicKnowledgeUnit,
    BridgingFact,
    EntityInfo,

    # IndexRAG components
    AKUExtractor,
    BridgingFactGenerator,
    BalancedContextSelector,

    # Configuration
    IndexRAGConfig,
    GraphRAGConfig,
    DEFAULT_INDEXRAG_CONFIG,
    DEFAULT_GRAPH_CONFIG,

    # Query hints (customizable, no hardcoding)
    DEFAULT_OBJECT_QUERY_HINTS,
    DEFAULT_CONSTRAINT_QUERY_HINTS,
)

# Import from service module
from .service import (
    # Main service
    GraphRAGService,

    # Document loaders
    DocumentLoader,
    TextLoader,
    MarkdownLoader,
    PDFLoader,
    JSONLoader,
    DirectoryLoader,
    DocumentLoaderRegistry,
)

# Import prompts
from .prompts import (
    # Original prompt
    ANSWER_PROMPT,

    # IndexRAG prompts
    AKU_EXTRACTION_PROMPT,
    AKU_EXTRACTION_PROMPT_RU,
    BRIDGING_FACT_PROMPT,
    BRIDGING_FACT_PROMPT_RU,
    IRCOT_REASONING_PROMPT,

    # Document loading prompts
    DOCUMENT_SUMMARY_PROMPT,
    DOCUMENT_SECTION_SPLIT_PROMPT,
    ENTITY_EXTRACTION_PROMPT,
)

__all__ = [
    # Main classes (original names preserved)
    "GraphRAGService",
    "GraphRAGRetriever",
    "VectorIndex",

    # IndexRAG data classes
    "AtomicKnowledgeUnit",
    "BridgingFact",
    "EntityInfo",

    # IndexRAG components
    "AKUExtractor",
    "BridgingFactGenerator",
    "BalancedContextSelector",

    # Configuration
    "IndexRAGConfig",
    "GraphRAGConfig",
    "DEFAULT_INDEXRAG_CONFIG",
    "DEFAULT_GRAPH_CONFIG",

    # Query hints (customizable)
    "DEFAULT_OBJECT_QUERY_HINTS",
    "DEFAULT_CONSTRAINT_QUERY_HINTS",

    # Document loaders
    "DocumentLoader",
    "TextLoader",
    "MarkdownLoader",
    "PDFLoader",
    "JSONLoader",
    "DirectoryLoader",
    "DocumentLoaderRegistry",

    # Prompts
    "ANSWER_PROMPT",
    "AKU_EXTRACTION_PROMPT",
    "AKU_EXTRACTION_PROMPT_RU",
    "BRIDGING_FACT_PROMPT",
    "BRIDGING_FACT_PROMPT_RU",
    "IRCOT_REASONING_PROMPT",
    "DOCUMENT_SUMMARY_PROMPT",
    "DOCUMENT_SECTION_SPLIT_PROMPT",
    "ENTITY_EXTRACTION_PROMPT",
]

# Version info
__version__ = "2.0.0"
__indexrag_paper__ = "https://arxiv.org/pdf/2603.16415"