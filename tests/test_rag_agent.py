from collections import Counter
from pathlib import Path
from typing import List
import unittest

from app.agents.rag_agent.checker import analyze_document_against_standard
from app.agents.rag_agent.retriever import GraphRAGRetriever, VectorIndex
from app.llm.base import EmbeddingProvider, LLMProvider
from app.schemas.document import DocumentInput, DocumentMeta, FigureItem, Paragraph, Position, Section, TableItem
from app.standards.ingest import StandardIngestor


class FakeProvider(LLMProvider, EmbeddingProvider):
    BASIS = [
        "рисунок",
        "подпись",
        "таблица",
        "заголовок",
        "источник",
        "приложение",
        "нумерация",
        "наименование",
        "титульный",
        "реферат",
        "содержание",
        "раздел",
    ]

    def chat(self, message: str) -> str:
        return "ok"

    def embed(self, text: str) -> List[float]:
        normalized = text.lower()
        replacements = {
            "иллюстрации": "рисунок",
            "иллюстрация": "рисунок",
            "рисунка": "рисунок",
            "рисунке": "рисунок",
            "таблицы": "таблица",
            "таблице": "таблица",
            "источников": "источник",
            "источники": "источник",
            "титульного": "титульный",
            "титульном": "титульный",
            "разделов": "раздел",
            "раздела": "раздел",
        }
        for source, target in replacements.items():
            normalized = normalized.replace(source, target)
        counts = Counter(normalized.split())
        return [float(counts.get(token, 0)) for token in self.BASIS]


class GraphRAGRetrieverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.standard_id = "gost_7_32_2017"
        cls.provider = FakeProvider()
        cls.ingestor = StandardIngestor()
        cls.bundle = cls.ingestor.ingest_pdf(cls.standard_id)
        cls.cleaned_text = Path(cls.bundle.cleaned_text_path).read_text(encoding="utf-8")
        cls.artifacts = cls.ingestor.ingest_text(
            standard_id="gost_7_32_2017_test_suite",
            standard_text=cls.cleaned_text,
            embedding_provider=cls.provider,
        )
        cls.rule_by_number = {rule.number: rule.id for rule in cls.bundle.parsed.rules}
        vector_index = VectorIndex(
            cls.provider,
            collection_name="test_gost_7_32_2017_suite",
            reset_collection=True,
        )
        vector_index.add_documents(
            texts=[node.content for node in cls.artifacts.nodes],
            metadatas=[
                {
                    "entity_id": node.id,
                    "entity_type": node.type,
                    "entity_name": node.name,
                }
                for node in cls.artifacts.nodes
            ],
        )
        cls.retriever = GraphRAGRetriever(cls.artifacts.graph, vector_index, cls.provider)

    def test_graph_contains_logical_edges(self) -> None:
        edge_types = Counter(edge.type for edge in self.artifacts.relations)
        self.assertGreater(edge_types["references"], 0)
        self.assertGreater(edge_types["depends_on"], 0)
        self.assertGreater(edge_types["prerequisite"], 0)

    def test_appendix_rule_has_dependency_to_section_617(self) -> None:
        appendix_rule_id = self.rule_by_number["5.11.3"]
        appendix_format_rule_id = self.rule_by_number["6.17"]
        related_edges = self.artifacts.graph.get_related_edges(appendix_rule_id)

        self.assertTrue(
            any(edge["type"] == "depends_on" and edge["neighbor_id"] == appendix_format_rule_id for edge in related_edges)
        )
        self.assertTrue(
            any(edge["type"] == "references" and edge["neighbor_id"] == appendix_format_rule_id for edge in related_edges)
        )

    def test_figure_caption_query_returns_figure_rules(self) -> None:
        result = self.retriever.retrieve("Какая подпись должна быть у рисунка?", top_k=5)
        object_types = [item["metadata"].get("object_type") for item in result["candidate_rules"][:3]]
        constraint_types = [item["metadata"].get("constraint_type") for item in result["candidate_rules"][:3]]

        self.assertIn("figure", result["matched_signals"]["object_types"])
        self.assertIn("caption_required", result["matched_signals"]["constraint_types"])
        self.assertIn("figure", object_types)
        self.assertIn("caption_required", constraint_types)

    def test_title_page_query_returns_title_page_rules(self) -> None:
        result = self.retriever.retrieve("Что должно быть на титульном листе?", top_k=5)
        object_types = [item["metadata"].get("object_type") for item in result["candidate_rules"][:3]]

        self.assertIn("title_page", object_types)

    def test_sources_query_returns_reference_rules(self) -> None:
        result = self.retriever.retrieve("Как оформлять список использованных источников?", top_k=5)
        object_types = [item["metadata"].get("object_type") for item in result["candidate_rules"][:5]]

        self.assertIn("references", object_types)


class GraphRAGCheckerTests(unittest.TestCase):
    standard_id = "gost_7_32_2017"

    @classmethod
    def setUpClass(cls) -> None:
        StandardIngestor().ingest_pdf(cls.standard_id)

    def test_missing_figure_caption_creates_issue(self) -> None:
        document = DocumentInput(
            document_id="doc_fig",
            standard_id=self.standard_id,
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="Основная часть")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="См. рисунок ниже.", position=Position(page=1, paragraph_index=1))],
            figures=[FigureItem(id="fig_1", caption="", position=Position(page=2))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        subtypes = [issue.subtype for issue in result.issues]

        self.assertIn("missing_figure_caption", subtypes)
        issue = next(issue for issue in result.issues if issue.subtype == "missing_figure_caption")
        self.assertEqual(issue.agent, "rag_agent")
        self.assertEqual(issue.type, "formatting")
        self.assertTrue(issue.standard_reference.rule_id)

    def test_invalid_table_caption_creates_issue(self) -> None:
        document = DocumentInput(
            document_id="doc_tbl",
            standard_id=self.standard_id,
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="Основная часть")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="Данные сведены в таблицу.", position=Position(page=1, paragraph_index=1))],
            tables=[TableItem(id="tbl_1", caption="Таблица сравнения методов", position=Position(page=3))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        subtypes = [issue.subtype for issue in result.issues]

        self.assertIn("invalid_table_caption_format", subtypes)

    def test_missing_references_section_creates_issue(self) -> None:
        document = DocumentInput(
            document_id="doc_refs",
            standard_id=self.standard_id,
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="Введение", text="Текст раздела")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="Во введении описывается работа.", position=Position(page=1, paragraph_index=1))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        subtypes = [issue.subtype for issue in result.issues]

        self.assertIn("missing_references_section", subtypes)

    def test_heading_trailing_period_creates_issue(self) -> None:
        document = DocumentInput(
            document_id="doc_heading",
            standard_id=self.standard_id,
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="Основная часть.")],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        self.assertIn("heading_trailing_period", [issue.subtype for issue in result.issues])

    def test_missing_section_number_creates_issue(self) -> None:
        document = DocumentInput(
            document_id="doc_numbering",
            standard_id=self.standard_id,
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[
                Section(id="sec_1", number="1", title="Введение"),
                Section(id="sec_2", number="2", title="Основная часть"),
                Section(id="sec_3", number="", title="Результаты"),
            ],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        self.assertIn("missing_section_number", [issue.subtype for issue in result.issues])

    def test_invalid_appendix_heading_creates_issue(self) -> None:
        document = DocumentInput(
            document_id="doc_appendix",
            standard_id=self.standard_id,
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_app", number="", title="Приложение Материалы")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="Дополнительные материалы приведены далее.", position=Position(page=5, paragraph_index=1))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        self.assertIn("invalid_appendix_heading", [issue.subtype for issue in result.issues])


if __name__ == "__main__":
    unittest.main()
