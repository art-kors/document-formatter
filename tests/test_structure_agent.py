import unittest

from app.agents.structure_agent.checks import build_structure_map, build_structure_summary, run_structure_checks
from app.agents.structure_agent.service import StructureAgentService
from app.schemas.document import DocumentInput, DocumentMeta, Paragraph, Position, Section


class StructureAgentTests(unittest.TestCase):
    def test_build_structure_map_normalizes_numbering(self) -> None:
        document = DocumentInput(
            document_id="doc_structure_map",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[
                Section(id="sec_1", number="1", title="Введение", level=1),
                Section(id="sec_2", number="2", title="Основная часть", level=1),
                Section(id="sec_2_1", number="2.1", title="Описание метода", level=2),
            ],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="Текст", position=Position(page=1, paragraph_index=1)),
                Paragraph(id="p_2", section_id="sec_2", text="Текст", position=Position(page=2, paragraph_index=2)),
                Paragraph(id="p_3", section_id="sec_2_1", text="Текст", position=Position(page=3, paragraph_index=3)),
            ],
        )

        structure_map = build_structure_map(document)

        self.assertEqual(len(structure_map), 3)
        self.assertEqual(structure_map[0]["number_parts"], (1,))
        self.assertEqual(structure_map[1]["number_parts"], (2,))
        self.assertEqual(structure_map[2]["number_parts"], (2, 1))
        self.assertEqual(structure_map[2]["parent_number"], "2")
        self.assertEqual(structure_map[2]["page"], 3)
        self.assertEqual(structure_map[2]["paragraph_id"], "p_3")

    def test_run_structure_checks_detects_numbering_and_missing_sections(self) -> None:
        document = DocumentInput(
            document_id="doc_structure_broken",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[
                Section(id="sec_1", number="1", title="Введение", level=1),
                Section(id="sec_2", number="2", title="Основная часть", level=1),
                Section(id="sec_2_1", number="2.1", title="Метод", level=2),
                Section(id="sec_2_3", number="2.3", title="Результаты", level=2),
                Section(id="sec_4", number="4", title="Обсуждение", level=1),
            ],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="Текст", position=Position(page=1, paragraph_index=1)),
                Paragraph(id="p_2", section_id="sec_2", text="Текст", position=Position(page=2, paragraph_index=2)),
                Paragraph(id="p_3", section_id="sec_2_1", text="Текст", position=Position(page=3, paragraph_index=3)),
                Paragraph(id="p_4", section_id="sec_2_3", text="Текст", position=Position(page=4, paragraph_index=4)),
                Paragraph(id="p_5", section_id="sec_4", text="Текст", position=Position(page=5, paragraph_index=5)),
            ],
        )

        issues = run_structure_checks(document, document.standard_id)
        subtypes = [issue.subtype for issue in issues]

        self.assertIn("numbering_error", subtypes)
        self.assertIn("missing_required_section", subtypes)
        self.assertTrue(any(issue.location.section_id == "sec_2_3" for issue in issues if issue.subtype == "numbering_error"))
        self.assertTrue(any(issue.location.paragraph_id == "p_4" for issue in issues if issue.subtype == "numbering_error"))

    def test_run_structure_checks_detects_missing_parent_section(self) -> None:
        document = DocumentInput(
            document_id="doc_structure_hierarchy",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[
                Section(id="sec_1", number="1", title="Введение", level=1),
                Section(id="sec_3_1", number="3.1", title="Детали", level=2),
                Section(id="sec_4", number="4", title="Заключение", level=1),
                Section(id="sec_refs", number="5", title="Список использованных источников", level=1),
            ],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="Текст", position=Position(page=1, paragraph_index=1)),
                Paragraph(id="p_2", section_id="sec_3_1", text="Текст", position=Position(page=2, paragraph_index=2)),
            ],
        )

        issues = run_structure_checks(document, document.standard_id)
        subtypes = [issue.subtype for issue in issues]

        self.assertIn("hierarchy_error", subtypes)
        self.assertTrue(any(issue.location.section_id == "sec_3_1" for issue in issues if issue.subtype == "hierarchy_error"))

    def test_run_structure_checks_detects_missing_number_and_order(self) -> None:
        document = DocumentInput(
            document_id="doc_structure_order",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[
                Section(id="sec_1", number="1", title="Заключение", level=1),
                Section(id="sec_2", number="2", title="Введение", level=1),
                Section(id="sec_3", number="", title="Результаты", level=1),
                Section(id="sec_4", number="3", title="Список использованных источников", level=1),
            ],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="Текст", position=Position(page=1, paragraph_index=1)),
                Paragraph(id="p_2", section_id="sec_2", text="Текст", position=Position(page=2, paragraph_index=2)),
                Paragraph(id="p_3", section_id="sec_3", text="Текст", position=Position(page=3, paragraph_index=3)),
                Paragraph(id="p_4", section_id="sec_4", text="Текст", position=Position(page=4, paragraph_index=4)),
            ],
        )

        issues = run_structure_checks(document, document.standard_id)
        subtypes = [issue.subtype for issue in issues]

        self.assertIn("numbering_error", subtypes)
        self.assertIn("order_error", subtypes)
        self.assertTrue(any(issue.location.section_id == "sec_3" for issue in issues if issue.subtype == "numbering_error"))

    def test_run_structure_checks_detects_missing_first_section_number(self) -> None:
        document = DocumentInput(
            document_id="doc_structure_starts_from_two",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[
                Section(id="sec_2", number="2", title="???????? ?????", level=1),
                Section(id="sec_3", number="3", title="??????????", level=1),
                Section(id="sec_refs", number="4", title="?????? ?????????????? ??????????", level=1),
            ],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_2", text="?????", position=Position(page=1, paragraph_index=1)),
                Paragraph(id="p_2", section_id="sec_3", text="?????", position=Position(page=2, paragraph_index=2)),
                Paragraph(id="p_3", section_id="sec_refs", text="[1] ????????", position=Position(page=3, paragraph_index=3)),
            ],
        )

        issues = run_structure_checks(document, document.standard_id)
        self.assertTrue(any(issue.subtype == "numbering_error" and issue.location.section_id == "sec_2" for issue in issues))

    def test_required_sections_can_be_detected_from_docx_paragraphs(self) -> None:
        document = DocumentInput(
            document_id="doc_structure_docx_required",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(
                filename="report.docx",
                title="Report",
                extras={
                    "docx_paragraphs": [
                        {"paragraph_index": 1, "text": "?????? ?????????????? ??????????", "alignment": "center", "style": "Heading 1"},
                        {"paragraph_index": 2, "text": "[1] ???? 7.32-2017", "alignment": "left", "style": "Normal"},
                    ],
                },
            ),
            sections=[
                Section(id="sec_1", number="1", title="????????", level=1),
                Section(id="sec_2", number="2", title="??????????", level=1),
            ],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="?????", position=Position(page=1, paragraph_index=1)),
                Paragraph(id="p_2", section_id="sec_2", text="?????", position=Position(page=2, paragraph_index=2)),
            ],
        )

        issues = run_structure_checks(document, document.standard_id)
        self.assertFalse(any(issue.subtype == "missing_required_section" and "?????? ?????????????? ??????????" in issue.evidence for issue in issues))

    def test_structure_service_returns_summary_details(self) -> None:
        document = DocumentInput(
            document_id="doc_structure_summary",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[
                Section(id="sec_1", number="1", title="Введение", level=1),
                Section(id="sec_2", number="2", title="Основная часть", level=1),
            ],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="Текст", position=Position(page=1, paragraph_index=1)),
                Paragraph(id="p_2", section_id="sec_2", text="Текст", position=Position(page=2, paragraph_index=2)),
            ],
        )

        service = StructureAgentService()
        result = service.analyze(document, document.standard_id)

        self.assertEqual(result.agent, "structure_agent")
        self.assertIn("sections_found", result.details)
        self.assertIn("missing_sections", result.details)
        self.assertIn("structure_map", result.details)
        self.assertTrue(result.details["missing_sections"])


if __name__ == "__main__":
    unittest.main()
