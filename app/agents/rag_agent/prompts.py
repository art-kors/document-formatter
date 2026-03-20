"""
Prompts for RAG agent including IndexRAG-specific templates.

This module contains all prompt templates used by the RAG system.
Prompts are separated into categories:
- Original prompts (unchanged)
- IndexRAG prompts (from paper)
- Language-specific variants
- Document loading prompts
"""

# =============================================================================
# Original Prompts (unchanged)
# =============================================================================

ANSWER_PROMPT = """
You are an assistant for document formatting rules.
Use only the provided context to answer the question.

CONTEXT:
{context}

QUESTION:
{question}

ANSWER:
"""

# =============================================================================
# IndexRAG Prompts (from paper: IndexRAG: Bridging Facts for Cross-Document Reasoning)
# =============================================================================

# Stage 1: AKU (Atomic Knowledge Unit) Extraction
# Paper reference: "we prompt an LLM to extract a set of atomic facts, structured as
# question-answer pairs, and associated entities from each document"
AKU_EXTRACTION_PROMPT = """You are an expert information extractor specializing in converting unstructured documents into clear, atomic question-answer pairs.

Extract ALL factual information from the following document as question-answer pairs. Each pair must answer exactly one question, be self-contained, and be verifiable from the source content. Extract questions for facts, descriptions, properties, relationships, and events. For each entity mentioned, also extract questions about its relationships to other entities.

Document: {text}

Return only a valid JSON object without any other text. The JSON should have the following structure:
{{
    "akus": [
        {{"question": "...", "answer": "..."}}
    ],
    "entities": ["entity1", "entity2", ...]
}}
"""

# Stage 2: Bridging Fact Generation
# Paper reference: "We then prompt the LLM to generate bridging facts that capture
# cross-document reasoning by linking related evidence from different sources."
BRIDGING_FACT_PROMPT = """Given the following information about "{entity}" from multiple source documents, generate bridging facts that connect information across these documents.

{doc_sections}

Requirements:
- Each bridging fact must combine information from 2+ documents
- Be factually accurate — only connect information that is logically related
- Each fact should be self-contained and understandable without context
- Do not generate speculative connections
- If documents share the entity name but are about unrelated topics, return empty

Return a JSON array of strings. If no meaningful connections exist, return [].
"""

# IRCoT-style reasoning prompt (for iterative retrieval mode)
# Paper reference: "IRCoT interleaves chain-of-thought reasoning with retrieval,
# using intermediate reasoning steps to formulate new queries"
IRCOT_REASONING_PROMPT = """You are a reasoning assistant that helps answer multi-hop questions step by step.

Question: {question}

Retrieved Information: {context}

Reasoning so far: {cot_so_far}

Write ONE brief reasoning sentence that makes progress toward answering the question. If more information is needed, suggest a specific search query.

Format your response as:
Reasoning: <one sentence of reasoning>
Search: <next search query, or DONE if ready to answer>
"""

# =============================================================================
# Language-specific variants (Russian for GOST standards)
# =============================================================================

BRIDGING_FACT_PROMPT_RU = """На основе следующей информации об объекте "{entity}" из нескольких документов, создайте связывающие факты, которые объединяют информацию из разных источников.

{doc_sections}

Требования:
- Каждый связывающий факт должен объединять информацию из 2+ документов
- Факты должны быть точными — связывайте только логически связанную информацию
- Каждый факт должен быть самодостаточным и понятным без контекста
- Не создавайте спекулятивные связи
- Если документы упоминают одинаковые сущности, но речь идёт о разных темах, верните пустой массив

Верните JSON-массив строк. Если осмысленных связей нет, верните [].
"""

AKU_EXTRACTION_PROMPT_RU = """Вы эксперт по извлечению информации, специализирующийся на преобразовании неструктурированных документов в чёткие атомарные пары вопрос-ответ.

Извлеките ВСЮ фактическую информацию из следующего документа в виде пар вопрос-ответ. Каждая пара должна отвечать ровно на один вопрос, быть самодостаточной и проверяемой по исходному содержимому. Извлекайте вопросы о фактах, описаниях, свойствах, отношениях и событиях. Для каждой упомянутой сущности также извлекайте вопросы о её связях с другими сущностями.

Документ: {text}

Верните только валидный JSON-объект без другого текста. JSON должен иметь следующую структуру:
{{
    "akus": [
        {{"question": "...", "answer": "..."}}
    ],
    "entities": ["сущность1", "сущность2", ...]
}}
"""

# =============================================================================
# Document Loading Prompts (for universal document ingestion)
# =============================================================================

DOCUMENT_SUMMARY_PROMPT = """Summarize the following document section, capturing all key facts, entities, and relationships.

Document: {text}

Provide a concise summary that preserves all important information for later retrieval.
"""

DOCUMENT_SECTION_SPLIT_PROMPT = """Analyze the following document and identify logical sections for indexing.

Document: {text}

Return a JSON array of sections, each with:
- "title": section title or heading
- "content": the section content
- "entities": list of named entities mentioned
"""

ENTITY_EXTRACTION_PROMPT = """Extract all named entities from the following text.

Text: {text}

Return a JSON array of entities, each with:
- "name": entity name
- "type": entity type (person, organization, location, concept, etc.)
- "context": brief context where the entity appears
"""
