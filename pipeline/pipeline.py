from entity_extractor import EntityExtractor
from graph import KnowledgeGraph
from vector_store import VectorStore
from engine import GraphRAGEngine

#1. extract rules

#2. applying agents

#3. new doc as a result


def pipeline(doc):
    # 1. Парсинг документа
    parsed_doc = ...

    # 2. Извлечение сущностей
    extractor = EntityExtractor()
    entities, relations = extractor.extract_from_parsed(parsed_doc)

    # 3. Построение графа
    kg = KnowledgeGraph()
    kg.build_from_entities(entities, relations)
    kg.save("knowledge_graph.json")

    # 4. Векторное индексирование
    vs = VectorStore()
    vs.create_collection("document_rules")
    for entity in entities:
        vs.add_entity(entity)

    # 5. Инициализация RAG движка
    rag = GraphRAGEngine(kg, vs)

    # 6. Примеры запросов
    questions = [
        "Как оформлять заголовки?",
        "Какая структура документа требуется?",
        "Что должно быть во введении?",
        "Есть ли требования к списку литературы?"
    ]

    for question in questions:
        print(f"\n❓ Вопрос: {question}")
        answer = rag.query(question)
        print(f"💡 Ответ: {answer}")

    # 7. Получение структуры документа
    structure = rag.get_document_structure()
    print("\n📋 Структура документа:")
    for section in structure:
        print(f"  {section['order']}. {section['name']}")