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


    def test_detected_title_page_does_not_create_alignment_issues(self) -> None:
        document = DocumentInput(
            document_id="doc_title_page_only_presence",
            standard_id=self.standard_id,
            meta=DocumentMeta(
                filename="report.docx",
                title="Report",
                extras={
                    "source_format": "docx",
                    "docx_paragraphs": [
                        {"paragraph_index": 1, "text": "???????????? ????? ? ??????? ??????????? ?????????? ?????????", "alignment": "left", "style": "Normal"},
                        {"paragraph_index": 2, "text": "???????????", "alignment": "left", "style": "Normal"},
                        {"paragraph_index": 3, "text": "?????", "alignment": "left", "style": "Normal"},
                        {"paragraph_index": 4, "text": "???? ??????", "alignment": "left", "style": "Normal"},
                        {"paragraph_index": 5, "text": "?????? 2026", "alignment": "left", "style": "Normal"},
                    ],
                },
            ),
            sections=[Section(id="sec_1", number="1", title="????????")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="?????", position=Position(page=2, paragraph_index=6))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        subtypes = [issue.subtype for issue in result.issues]
        self.assertNotIn("title_page_right_alignment", subtypes)
        self.assertNotIn("title_page_center_alignment", subtypes)

    def test_truncated_figure_prefix_is_detected_as_caption_format_issue(self) -> None:
        document = DocumentInput(
            document_id="doc_truncated_figure_prefix",
            standard_id=self.standard_id,
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="???????? ?????")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="??. ?????? 1 ????.", position=Position(page=1, paragraph_index=1))],
            figures=[FigureItem(id="fig_1", caption="?????? 1 - ??????????? ???????", position=Position(page=1, paragraph_index=2))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        self.assertNotIn("missing_figure_caption", [issue.subtype for issue in result.issues])
        self.assertIn("invalid_figure_caption_format", [issue.subtype for issue in result.issues])

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

    def test_table_position_headers_and_appendix_create_issues(self) -> None:
        document = DocumentInput(
            document_id="doc_table_meta",
            standard_id=self.standard_id,
            meta=DocumentMeta(
                filename="report.docx",
                title="Report",
                extras={
                    "source_format": "docx",
                    "docx_tables_meta": [
                        {
                            "table_index": 1,
                            "caption_paragraph_index": 5,
                            "caption_position": "below",
                            "header_cells": ["??????????.", "????????."],
                            "appendix_letter": "?",
                            "section_title": "Приложение А - Материалы",
                        }
                    ],
                },
            ),
            sections=[Section(id="sec_app", number="?", title="Приложение А - Материалы")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_app", text="? ?????????? ? ????????? ?????????????? ??????.", position=Position(page=5, paragraph_index=1))],
            tables=[TableItem(id="tbl_1", caption="Таблица 1 - Данные", position=Position(page=5, paragraph_index=5))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        subtypes = [issue.subtype for issue in result.issues]

        self.assertIn("table_caption_below_table", subtypes)
        self.assertIn("invalid_table_header_punctuation", subtypes)
        self.assertIn("appendix_table_caption_format", subtypes)


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

    def test_appendix_heading_without_letter_is_not_flagged_as_invalid(self) -> None:
        document = DocumentInput(
            document_id="doc_appendix",
            standard_id=self.standard_id,
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_app", number="", title="Приложение Материалы")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="Дополнительные материалы приведены далее.", position=Position(page=5, paragraph_index=1))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        self.assertNotIn("invalid_appendix_heading", [issue.subtype for issue in result.issues])

    def test_docx_title_page_is_recognized_with_generic_official_layout(self) -> None:
        document = DocumentInput(
            document_id="doc_title_page_present",
            standard_id=self.standard_id,
            meta=DocumentMeta(
                filename="report.docx",
                title="Report",
                extras={
                    "source_format": "docx",
                    "docx_paragraphs": [
                        {"paragraph_index": 1, "text": "???????????? ????? ? ??????? ??????????? ?????????? ?????????", "alignment": "center", "style": "Normal"},
                        {"paragraph_index": 2, "text": "???????????? ????????????????? ???????????", "alignment": "center", "style": "Normal"},
                        {"paragraph_index": 3, "text": "??????? ?????????????? ??????????", "alignment": "center", "style": "Normal"},
                        {"paragraph_index": 4, "text": "?????", "alignment": "center", "style": "Normal"},
                        {"paragraph_index": 5, "text": "?? ?????????????????? ???????", "alignment": "center", "style": "Normal"},
                        {"paragraph_index": 6, "text": "????????: ??????? ?????? ??8-11", "alignment": "right", "style": "Normal"},
                        {"paragraph_index": 7, "text": "????????????: ?????? ?.?.", "alignment": "right", "style": "Normal"},
                        {"paragraph_index": 8, "text": "?????? 2026", "alignment": "center", "style": "Normal"},
                        {"paragraph_index": 9, "text": "Показатель", "alignment": "center", "style": "Heading 1"},
                    ],
                },
            ),
            sections=[
                Section(id="sec_contents", number="", title="Содержание", text="1 Введение"),
                Section(id="sec_1", number="1", title="Введение", text="Текст раздела"),
            ],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="Текст раздела", position=Position(page=2, paragraph_index=10))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        self.assertNotIn("missing_title_page", [issue.subtype for issue in result.issues])

    def test_docx_detects_oglavlenie_and_reference_heading_from_paragraphs(self) -> None:
        document = DocumentInput(
            document_id="doc_front_blocks_present",
            standard_id=self.standard_id,
            meta=DocumentMeta(
                filename="report.docx",
                title="Report",
                extras={
                    "source_format": "docx",
                    "docx_paragraphs": [
                        {"paragraph_index": 1, "text": "Оглавление", "alignment": "center", "style": "Heading 1"},
                        {"paragraph_index": 2, "text": "1 Введение", "alignment": "left", "style": "Normal"},
                        {"paragraph_index": 3, "text": "Список использованных источников", "alignment": "center", "style": "Heading 1"},
                        {"paragraph_index": 4, "text": "[1] ГОСТ 7.32-2017", "alignment": "left", "style": "Normal"},
                    ],
                },
            ),
            sections=[Section(id="sec_1", number="1", title="Введение", text="Текст раздела")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="Текст раздела", position=Position(page=2, paragraph_index=5))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        subtypes = [issue.subtype for issue in result.issues]
        self.assertNotIn("missing_contents_section", subtypes)
        self.assertNotIn("missing_references_section", subtypes)

    def test_docx_front_matter_checks_create_title_and_contents_issues(self) -> None:
        document = DocumentInput(
            document_id="doc_front_matter",
            standard_id=self.standard_id,
            meta=DocumentMeta(
                filename="report.docx",
                title="Report",
                extras={
                    "source_format": "docx",
                    "docx_paragraphs": [
                        {"paragraph_index": 1, "text": "1 ????????", "alignment": "left", "style": "Normal"},
                        {"paragraph_index": 2, "text": "????? ???????", "alignment": "left", "style": "Normal"},
                        {"paragraph_index": 3, "text": "2 ???????? ?????", "alignment": "left", "style": "Normal"},
                    ],
                },
            ),
            sections=[
                Section(id="sec_1", number="1", title="Значение", text="?????"),
                Section(id="sec_2", number="2", title="Основная часть", text="?????"),
            ],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="?????", position=Position(page=1, paragraph_index=1))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        subtypes = [issue.subtype for issue in result.issues]
        self.assertIn("missing_title_page", subtypes)
        self.assertIn("missing_contents_section", subtypes)


    def test_docx_page_numbering_checks_create_issues(self) -> None:
        document = DocumentInput(
            document_id="doc_page_numbering",
            standard_id=self.standard_id,
            meta=DocumentMeta(
                filename="report.docx",
                title="Report",
                extras={
                    "source_format": "docx",
                    "docx_page_numbering": [
                        {
                            "section_index": 1,
                            "different_first_page": False,
                            "default_footer_has_page_field": True,
                            "default_footer_alignment": "left",
                            "first_footer_has_page_field": False,
                            "first_footer_alignment": None,
                            "default_header_has_page_field": True,
                            "default_header_alignment": "center",
                            "first_header_has_page_field": False,
                            "first_header_alignment": None,
                            "even_header_has_page_field": False,
                            "even_header_alignment": None,
                            "page_number_start": None,
                        },
                        {
                            "section_index": 2,
                            "different_first_page": False,
                            "default_footer_has_page_field": True,
                            "default_footer_alignment": "center",
                            "first_footer_has_page_field": False,
                            "first_footer_alignment": None,
                            "default_header_has_page_field": False,
                            "default_header_alignment": None,
                            "first_header_has_page_field": False,
                            "first_header_alignment": None,
                            "even_header_has_page_field": False,
                            "even_header_alignment": None,
                            "page_number_start": 1,
                        },
                    ],
                },
            ),
            sections=[Section(id="sec_1", number="1", title="????????")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="????? ???????", position=Position(page=2, paragraph_index=1))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        subtypes = [issue.subtype for issue in result.issues]
        self.assertIn("page_number_not_centered", subtypes)
        self.assertIn("page_number_in_header", subtypes)
        self.assertIn("title_page_number_visible", subtypes)
        self.assertIn("page_numbering_restart", subtypes)



    def test_numbered_heading_is_not_flagged_as_invalid_enumeration(self) -> None:
        document = DocumentInput(
            document_id="doc_numbered_heading",
            standard_id=self.standard_id,
            meta=DocumentMeta(
                filename="report.docx",
                title="Report",
                extras={
                    "source_format": "docx",
                    "docx_paragraphs": [
                        {"paragraph_index": 1, "text": "2. ?????????? ? ??????? ?????? ?????????? ???? ???????", "alignment": "left", "style": "Heading 1", "first_line_indent_mm": 0.0},
                    ],
                    "section_headings": {
                        "sec_2": {"paragraph_index": 1, "text": "2. ?????????? ? ??????? ?????? ?????????? ???? ???????", "alignment": "left", "style_name": "Heading 1"}
                    },
                },
            ),
            sections=[Section(id="sec_2", number="2", title="?????????? ? ??????? ?????? ?????????? ???? ???????")],
            paragraphs=[],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        self.assertNotIn("invalid_enumeration_marker", [issue.subtype for issue in result.issues])

    def test_docx_enumeration_checks_create_issues(self) -> None:
        document = DocumentInput(
            document_id="doc_enumeration",
            standard_id=self.standard_id,
            meta=DocumentMeta(
                filename="report.docx",
                title="Report",
                extras={
                    "source_format": "docx",
                    "docx_paragraphs": [
                        {"paragraph_index": 1, "text": "? ?????? ?????", "alignment": "left", "style": "Normal", "first_line_indent_mm": 0.0},
                        {"paragraph_index": 2, "text": "?) ?????? ?????", "alignment": "left", "style": "Normal", "first_line_indent_mm": 0.0},
                    ],
                },
            ),
            sections=[Section(id="sec_1", number="1", title="???????? ?????")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="? ?????? ?????", position=Position(page=1, paragraph_index=1))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        subtypes = [issue.subtype for issue in result.issues]
        self.assertIn("invalid_enumeration_marker", subtypes)
        self.assertIn("enumeration_indent_invalid", subtypes)

    def test_docx_invalid_page_size_creates_issue(self) -> None:
        document = DocumentInput(
            document_id="doc_invalid_page_size",
            standard_id=self.standard_id,
            meta=DocumentMeta(
                filename="report.docx",
                title="Report",
                extras={
                    "source_format": "docx",
                    "docx_sections": [
                        {"section_index": 1, "page_width_mm": 148.0, "page_height_mm": 210.0, "orientation": "portrait"},
                    ],
                },
            ),
            sections=[Section(id="sec_1", number="1", title="Основная часть")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="????? ???????", position=Position(page=1, paragraph_index=1))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        self.assertIn("invalid_page_size", [issue.subtype for issue in result.issues])

    def test_docx_a4_page_size_does_not_create_issue(self) -> None:
        document = DocumentInput(
            document_id="doc_a4_page_size",
            standard_id=self.standard_id,
            meta=DocumentMeta(
                filename="report.docx",
                title="Report",
                extras={
                    "source_format": "docx",
                    "docx_sections": [
                        {"section_index": 1, "page_width_mm": 210.0, "page_height_mm": 297.0, "orientation": "portrait"},
                    ],
                },
            ),
            sections=[Section(id="sec_1", number="1", title="Основная часть")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="????? ???????", position=Position(page=1, paragraph_index=1))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        self.assertNotIn("invalid_page_size", [issue.subtype for issue in result.issues])

    def test_docx_typography_and_layout_issues_are_detected(self) -> None:
        document = DocumentInput(
            document_id="doc_typography_issues",
            standard_id=self.standard_id,
            meta=DocumentMeta(
                filename="report.docx",
                title="Report",
                extras={
                    "source_format": "docx",
                    "docx_sections": [
                        {
                            "section_index": 1,
                            "page_width_mm": 210.0,
                            "page_height_mm": 297.0,
                            "left_margin_mm": 25.0,
                            "right_margin_mm": 10.0,
                            "top_margin_mm": 15.0,
                            "bottom_margin_mm": 15.0,
                            "orientation": "portrait",
                        },
                    ],
                    "docx_paragraphs": [
                        {
                            "paragraph_index": 1,
                            "text": "??? ???????? ????? ? ????????? ???????????? ??????????? ??? ????????.",
                            "alignment": "justify",
                            "style": "Normal",
                            "first_line_indent_mm": 0.0,
                            "line_spacing": 1.0,
                            "font_size_pt_min": 11.0,
                            "font_family": "Arial",
                            "has_bold_text": True,
                            "has_non_black_text": True,
                        },
                    ],
                },
            ),
            sections=[Section(id="sec_1", number="1", title="Основная часть")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="??? ???????? ????? ? ????????? ???????????? ??????????? ??? ????????.", position=Position(page=1, paragraph_index=1))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        subtypes = [issue.subtype for issue in result.issues]
        self.assertIn("invalid_page_margins", subtypes)
        self.assertIn("invalid_first_line_indent", subtypes)
        self.assertIn("invalid_line_spacing", subtypes)
        self.assertIn("invalid_font_size", subtypes)
        self.assertIn("invalid_font_family", subtypes)
        self.assertIn("invalid_font_color", subtypes)
        self.assertIn("unexpected_bold_text", subtypes)

    def test_figure_caption_trailing_period_creates_issue(self) -> None:
        document = DocumentInput(
            document_id="doc_figure_period",
            standard_id=self.standard_id,
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="Основная часть")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="??? ???????? ?? ??????? 1, ????? ????????.", position=Position(page=1, paragraph_index=1))],
            figures=[FigureItem(id="fig_1", caption="??????? 1 - ??????????? ???????.", position=Position(page=2, paragraph_index=2))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        self.assertIn("figure_caption_trailing_period", [issue.subtype for issue in result.issues])

    def test_figure_caption_alignment_creates_issue_for_non_centered_docx_caption(self) -> None:
        document = DocumentInput(
            document_id="doc_figure_alignment",
            standard_id=self.standard_id,
            meta=DocumentMeta(
                filename="report.docx",
                title="Report",
                extras={
                    "source_format": "docx",
                    "docx_paragraphs": [
                        {"paragraph_index": 1, "text": "? ?????? ???????? ??????? 1.", "alignment": "justify", "style": "Normal"},
                        {"paragraph_index": 2, "text": "??????? 1 - ??????????? ???????", "alignment": "left", "style": "Normal"},
                    ],
                },
            ),
            sections=[Section(id="sec_1", number="1", title="Основная часть")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="? ?????? ???????? ??????? 1.", position=Position(page=1, paragraph_index=1))],
            figures=[FigureItem(id="fig_1", caption="??????? 1 - ??????????? ???????", position=Position(page=1, paragraph_index=2))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        self.assertIn("figure_caption_not_centered", [issue.subtype for issue in result.issues])

    def test_missing_figure_reference_before_caption_creates_issue(self) -> None:
        document = DocumentInput(
            document_id="doc_figure_reference_order",
            standard_id=self.standard_id,
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="Основная часть")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="???????? ??????????? ??? ?????? ?? ???????.", position=Position(page=1, paragraph_index=1))],
            figures=[FigureItem(id="fig_1", caption="??????? 1 - ??????????? ???????", position=Position(page=1, paragraph_index=2))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        self.assertIn("missing_figure_reference", [issue.subtype for issue in result.issues])

    def test_figure_numbering_sequence_creates_issue(self) -> None:
        document = DocumentInput(
            document_id="doc_figure_numbering",
            standard_id=self.standard_id,
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="Основная часть")],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="??? ???????? ?? ??????? 1.", position=Position(page=1, paragraph_index=1)),
                Paragraph(id="p_2", section_id="sec_1", text="??? ???????? ?? ??????? 3.", position=Position(page=2, paragraph_index=3)),
            ],
            figures=[
                FigureItem(id="fig_1", caption="??????? 1 - ????? ???????", position=Position(page=1, paragraph_index=2)),
                FigureItem(id="fig_2", caption="??????? 3 - ????????? ??????", position=Position(page=2, paragraph_index=4)),
            ],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        self.assertIn("figure_numbering_error", [issue.subtype for issue in result.issues])


    def test_figure_caption_with_em_dash_is_not_flagged_as_invalid(self) -> None:
        document = DocumentInput(
            document_id="doc_figure_em_dash",
            standard_id=self.standard_id,
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="\u041e\u0441\u043d\u043e\u0432\u043d\u0430\u044f \u0447\u0430\u0441\u0442\u044c")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="\u0421\u043c. \u0440\u0438\u0441\u0443\u043d\u043e\u043a 9.", position=Position(page=1, paragraph_index=1))],
            figures=[FigureItem(id="fig_9", caption="\u0420\u0438\u0441\u0443\u043d\u043e\u043a 9 \u2014 \u0417\u0430\u0432\u0438\u0441\u0438\u043c\u043e\u0441\u0442\u044c \u0431\u0430\u0437\u043e\u0432\u043e\u0439 \u0438\u043d\u0442\u0435\u043d\u0441\u0438\u0432\u043d\u043e\u0441\u0442\u0438 \u043e\u0442\u043a\u0430\u0437\u043e\u0432 \u043e\u0442 \u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0439 \u043c\u0430\u043a\u0441\u0438\u043c\u0430\u043b\u044c\u043d\u043e\u0433\u043e \u0442\u043e\u043a\u0430 \u0444\u043e\u0440\u043c\u0443\u043b\u0435 (8)", position=Position(page=1, paragraph_index=2))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        self.assertNotIn("invalid_figure_caption_format", [issue.subtype for issue in result.issues])


    def test_heading_appendix_and_table_header_alignment_issues_are_detected(self) -> None:
        document = DocumentInput(
            document_id="doc_heading_layout",
            standard_id=self.standard_id,
            meta=DocumentMeta(
                filename="report.docx",
                title="Report",
                extras={
                    "source_format": "docx",
                    "docx_paragraphs": [
                        {"paragraph_index": 1, "text": "1 ???????? ?????", "alignment": "center", "style": "Heading 1", "first_line_indent_mm": 0.0, "has_non_black_text": True},
                        {"paragraph_index": 2, "text": "3 ?????? ?????????????? ??????????", "alignment": "left", "style": "Heading 1", "first_line_indent_mm": 12.5, "has_non_black_text": True},
                        {"paragraph_index": 3, "text": "Приложение А - Материалы", "alignment": "left", "style": "Heading 1", "first_line_indent_mm": 0.0, "has_non_black_text": False},
                    ],
                    "section_headings": {
                        "sec_main": {"paragraph_index": 1, "text": "1 ???????? ?????", "alignment": "center", "style_name": "Heading 1"},
                        "sec_refs": {"paragraph_index": 2, "text": "3 ?????? ?????????????? ??????????", "alignment": "left", "style_name": "Heading 1"},
                        "sec_app": {"paragraph_index": 3, "text": "Приложение А - Материалы", "alignment": "left", "style_name": "Heading 1"},
                    },
                    "docx_tables_meta": [
                        {"table_index": 1, "caption_paragraph_index": 4, "caption_position": "above", "header_cells": ["Показатель", "Значение"], "appendix_letter": None},
                    ],
                    "docx_table_paragraphs": [
                        {"paragraph_index": 10000, "text": "Показатель", "alignment": "left", "style": "Normal", "table_index": 1, "row_index": 1, "cell_index": 1},
                        {"paragraph_index": 10001, "text": "Значение", "alignment": "left", "style": "Normal", "table_index": 1, "row_index": 1, "cell_index": 2},
                    ],
                },
            ),
            sections=[
                Section(id="sec_main", number="1", title="Основная часть", level=1),
                Section(id="sec_refs", number="3", title="Список использованных источников", level=1),
                Section(id="sec_app", number="", title="Приложение А - Материалы", level=1),
            ],
            tables=[TableItem(id="tbl_1", caption="Таблица 1 - Данные", position=Position(page=1, paragraph_index=4))],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        subtypes = [issue.subtype for issue in result.issues]
        self.assertIn("main_heading_centered", subtypes)
        self.assertIn("heading_invalid_font_color", subtypes)
        self.assertIn("structural_heading_numbered", subtypes)
        self.assertIn("structural_heading_not_uppercase", subtypes)
        self.assertIn("structural_heading_not_centered", subtypes)
        self.assertIn("structural_heading_invalid_font_color", subtypes)
        self.assertIn("appendix_heading_not_centered", subtypes)
        self.assertIn("appendix_heading_single_line", subtypes)
        self.assertIn("table_header_alignment", subtypes)

    def test_formula_issues_are_detected_from_docx_formula_meta(self) -> None:
        document = DocumentInput(
            document_id='doc_formula_issues',
            standard_id=self.standard_id,
            meta=DocumentMeta(
                filename='report.docx',
                title='Report',
                extras={
                    'source_format': 'docx',
                    'docx_formulas': [
                        {
                            'paragraph_index': 3,
                            'text': 'E = mc2 (2)',
                            'alignment': 'left',
                            'has_math_xml': False,
                            'is_standalone': True,
                            'equation_number': '2',
                            'raw_equation_number': '',
                            'prev_blank': False,
                            'next_blank': False,
                            'prev_text': 'Предыдущий абзац',
                            'next_text': 'где: E - энергия',
                            'section_id': 'sec_1',
                            'appendix_letter': '',
                        }
                    ],
                },
            ),
            sections=[Section(id='sec_1', number='1', title='Основная часть')],
            paragraphs=[
                Paragraph(id='p_1', section_id='sec_1', text='Расчет выполняют по формуле 2.', position=Position(page=1, paragraph_index=1)),
                Paragraph(id='p_2', section_id='sec_1', text='Предыдущий абзац', position=Position(page=1, paragraph_index=2)),
            ],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        subtypes = [issue.subtype for issue in result.issues]
        self.assertIn('formula_not_centered', subtypes)
        self.assertIn('formula_missing_blank_lines', subtypes)
        self.assertIn('invalid_formula_reference_format', subtypes)
        self.assertIn('formula_where_colon', subtypes)

    def test_valid_formula_does_not_create_formula_issues(self) -> None:
        document = DocumentInput(
            document_id='doc_formula_valid',
            standard_id=self.standard_id,
            meta=DocumentMeta(
                filename='report.docx',
                title='Report',
                extras={
                    'source_format': 'docx',
                    'docx_formulas': [
                        {
                            'paragraph_index': 3,
                            'text': 'E = mc2 (1)',
                            'alignment': 'center',
                            'has_math_xml': False,
                            'is_standalone': True,
                            'equation_number': '1',
                            'raw_equation_number': '',
                            'prev_blank': True,
                            'next_blank': True,
                            'prev_text': '',
                            'next_text': 'где E - энергия',
                            'section_id': 'sec_1',
                            'appendix_letter': '',
                        }
                    ],
                },
            ),
            sections=[Section(id='sec_1', number='1', title='Основная часть')],
            paragraphs=[
                Paragraph(id='p_1', section_id='sec_1', text='Расчет выполняют по формуле (1).', position=Position(page=1, paragraph_index=1)),
            ],
        )

        result = analyze_document_against_standard(document, self.standard_id)
        formula_subtypes = {
            'formula_not_standalone',
            'formula_not_centered',
            'formula_missing_blank_lines',
            'missing_formula_number',
            'formula_number_format_error',
            'formula_numbering_error',
            'appendix_formula_numbering_error',
            'missing_formula_reference',
            'invalid_formula_reference_format',
            'formula_where_colon',
            'formula_explanation_format_error',
            'formula_break_invalid',
        }
        self.assertTrue(formula_subtypes.isdisjoint({issue.subtype for issue in result.issues}))


if __name__ == "__main__":
    unittest.main()
