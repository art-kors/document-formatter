import unittest

from app.parsing.document_to_schema import parse_text_to_document


class DocumentToSchemaTests(unittest.TestCase):
    def test_parse_text_to_document_extracts_sections_paragraphs_and_captions(self) -> None:
        text = """1 Введение

Во введении описывается цель работы.

Рисунок 1 - Архитектура системы

Таблица 1 - Сравнение методов

6 Список использованных источников

[1] ГОСТ 7.32-2017"""

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
        self.assertEqual(document.sections[1].title, "Список использованных источников")
        self.assertEqual(len(document.figures), 1)
        self.assertEqual(len(document.tables), 1)
        self.assertGreaterEqual(len(document.paragraphs), 2)
        self.assertEqual(document.figures[0].caption, "Рисунок 1 - Архитектура системы")
        self.assertEqual(document.tables[0].caption, "Таблица 1 - Сравнение методов")


if __name__ == "__main__":
    unittest.main()
