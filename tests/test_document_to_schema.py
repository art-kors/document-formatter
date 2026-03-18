from io import BytesIO
import unittest

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm

from app.parsing.document_to_schema import parse_docx_to_document, parse_text_to_document


class DocumentToSchemaTests(unittest.TestCase):
    def test_parse_text_to_document_extracts_sections_paragraphs_and_captions(self) -> None:
        text = (
            "1 \u0412\u0432\u0435\u0434\u0435\u043d\u0438\u0435\n\n"
            "\u0412\u043e \u0432\u0432\u0435\u0434\u0435\u043d\u0438\u0438 \u043e\u043f\u0438\u0441\u044b\u0432\u0430\u0435\u0442\u0441\u044f \u0446\u0435\u043b\u044c \u0440\u0430\u0431\u043e\u0442\u044b.\n\n"
            "\u0420\u0438\u0441\u0443\u043d\u043e\u043a 1 - \u0410\u0440\u0445\u0438\u0442\u0435\u043a\u0442\u0443\u0440\u0430 \u0441\u0438\u0441\u0442\u0435\u043c\u044b\n\n"
            "\u0422\u0430\u0431\u043b\u0438\u0446\u0430 1 - \u0421\u0440\u0430\u0432\u043d\u0435\u043d\u0438\u0435 \u043c\u0435\u0442\u043e\u0434\u043e\u0432\n\n"
            "6 \u0421\u043f\u0438\u0441\u043e\u043a \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432\n\n"
            "[1] \u0413\u041e\u0421\u0422 7.32-2017"
        )

        document = parse_text_to_document(
            text,
            filename="report.docx",
            standard_id="gost_7_32_2017",
            document_id="doc_test",
        )

        self.assertEqual(document.document_id, "doc_test")
        self.assertEqual(document.standard_id, "gost_7_32_2017")
        self.assertEqual(len(document.sections), 2)
        self.assertEqual(document.sections[0].number, "1")
        self.assertEqual(document.sections[1].title, "\u0421\u043f\u0438\u0441\u043e\u043a \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432")
        self.assertEqual(len(document.figures), 1)
        self.assertEqual(len(document.tables), 1)
        self.assertGreaterEqual(len(document.paragraphs), 2)
        self.assertEqual(document.figures[0].caption, "\u0420\u0438\u0441\u0443\u043d\u043e\u043a 1 - \u0410\u0440\u0445\u0438\u0442\u0435\u043a\u0442\u0443\u0440\u0430 \u0441\u0438\u0441\u0442\u0435\u043c\u044b")
        self.assertEqual(document.tables[0].caption, "\u0422\u0430\u0431\u043b\u0438\u0446\u0430 1 - \u0421\u0440\u0430\u0432\u043d\u0435\u043d\u0438\u0435 \u043c\u0435\u0442\u043e\u0434\u043e\u0432")

    def test_parse_text_to_document_extracts_abbreviated_figure_caption(self) -> None:
        text = (
            "1 \u0412\u0432\u0435\u0434\u0435\u043d\u0438\u0435\n\n"
            "\u0420\u0438\u0441. 1 \u0410\u0440\u0445\u0438\u0442\u0435\u043a\u0442\u0443\u0440\u0430 \u0441\u0438\u0441\u0442\u0435\u043c\u044b\n\n"
            "\u0420\u0438\u0441 2 - \u0421\u0445\u0435\u043c\u0430 \u043c\u043e\u0434\u0443\u043b\u044f"
        )

        document = parse_text_to_document(
            text,
            filename="report.txt",
            standard_id="gost_7_32_2017",
            document_id="doc_abbrev_figures",
        )

        self.assertEqual(len(document.figures), 2)
        self.assertEqual(document.figures[0].caption, "\u0420\u0438\u0441. 1 \u0410\u0440\u0445\u0438\u0442\u0435\u043a\u0442\u0443\u0440\u0430 \u0441\u0438\u0441\u0442\u0435\u043c\u044b")
        self.assertEqual(document.figures[1].caption, "\u0420\u0438\u0441 2 - \u0421\u0445\u0435\u043c\u0430 \u043c\u043e\u0434\u0443\u043b\u044f")


    def test_parse_text_to_document_does_not_create_fake_untitled_section(self) -> None:
        text = (
            "\u0422\u0435\u043a\u0441\u0442 \u0442\u0438\u0442\u0443\u043b\u044c\u043d\u043e\u0433\u043e \u0431\u043b\u043e\u043a\u0430\n\n"
            "2 \u041e\u0441\u043d\u043e\u0432\u043d\u0430\u044f \u0447\u0430\u0441\u0442\u044c\n\n"
            "\u0422\u0435\u043a\u0441\u0442 \u0440\u0430\u0437\u0434\u0435\u043b\u0430"
        )

        document = parse_text_to_document(
            text,
            filename="report.txt",
            standard_id="gost_7_32_2017",
            document_id="doc_without_fake_section",
        )

        self.assertEqual(len(document.sections), 1)
        self.assertEqual(document.sections[0].number, "2")
        self.assertIsNone(document.paragraphs[0].section_id)
        self.assertNotIn("\u0411\u0435\u0437 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u044f", [section.title for section in document.sections])

    def test_parse_docx_to_document_collects_alignment_metadata(self) -> None:
        source = Document()
        title = source.add_paragraph("\u041e\u0442\u0447\u0435\u0442")
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        performer = source.add_paragraph("\u0412\u044b\u043f\u043e\u043b\u043d\u0438\u043b: \u0441\u0442\u0443\u0434\u0435\u043d\u0442")
        performer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        source.add_paragraph("1 \u0412\u0432\u0435\u0434\u0435\u043d\u0438\u0435")
        source.add_paragraph("\u041e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u0442\u0435\u043a\u0441\u0442 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430")

        buffer = BytesIO()
        source.save(buffer)

        document = parse_docx_to_document(
            buffer.getvalue(),
            filename="report.docx",
            standard_id="gost_7_32_2017",
            document_id="doc_docx_meta",
        )

        self.assertEqual(document.meta.extras["source_format"], "docx")
        self.assertGreaterEqual(len(document.meta.extras["docx_paragraphs"]), 3)
        self.assertEqual(document.meta.extras["docx_paragraphs"][0]["alignment"], "center")
        self.assertEqual(document.meta.extras["docx_paragraphs"][1]["alignment"], "right")

    def test_parse_docx_to_document_does_not_turn_regular_paragraphs_into_sections(self) -> None:
        source = Document()
        source.add_paragraph("1 ????????")
        source.add_paragraph("??? ??????? ????? ??????, ??????? ?? ?????? ??????????? ????????? ????????.")
        source.add_paragraph("??? ???? ??????? ????? ?????? ??? ????????????? ?????.")

        buffer = BytesIO()
        source.save(buffer)

        document = parse_docx_to_document(
            buffer.getvalue(),
            filename="report.docx",
            standard_id="gost_7_32_2017",
            document_id="doc_docx_no_fake_sections",
        )

        self.assertEqual(len(document.sections), 1)
        self.assertEqual(document.sections[0].number, "1")
        self.assertEqual(len(document.paragraphs), 2)

    def test_parse_docx_to_document_extracts_page_size_metadata(self) -> None:
        source = Document()
        source.sections[0].page_width = Mm(148)
        source.sections[0].page_height = Mm(210)
        source.add_paragraph("1 ????????")

        buffer = BytesIO()
        source.save(buffer)

        document = parse_docx_to_document(
            buffer.getvalue(),
            filename="report.docx",
            standard_id="gost_7_32_2017",
            document_id="doc_docx_page_size",
        )

        self.assertEqual(document.meta.extras['source_format'], 'docx')
        self.assertGreaterEqual(len(document.meta.extras['docx_sections']), 1)
        self.assertAlmostEqual(document.meta.extras['docx_sections'][0]['page_width_mm'], 148.0, places=1)
        self.assertAlmostEqual(document.meta.extras['docx_sections'][0]['page_height_mm'], 210.0, places=1)
        self.assertIsNotNone(document.meta.extras['docx_sections'][0]['left_margin_mm'])


if __name__ == "__main__":
    unittest.main()
