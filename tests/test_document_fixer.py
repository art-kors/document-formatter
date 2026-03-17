from io import BytesIO
from docx import Document as WordDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from pathlib import Path
import unittest
import zipfile

from app.fixing.docx_editor import apply_fixes_to_source_docx
from app.fixing.document_fixer import apply_fixes, build_corrected_docx
from app.orchestration.pipeline import DocumentPipeline
from app.parsing.document_to_schema import parse_docx_to_document
from app.schemas.document import DocumentInput
from app.standards.ingest import StandardIngestor
from app.standards.registry import StandardRegistry
from tests.support.fake_provider import FakeProvider


class DocumentFixerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        StandardIngestor().ingest_pdf('gost_7_32_2017')
        cls.pipeline = DocumentPipeline(llm_provider=FakeProvider(), registry=StandardRegistry())

    def test_apply_fixes_corrects_common_issues(self) -> None:
        document = DocumentInput.model_validate_json(
            Path('tests/fixtures/documents/demo_appendix_heading.json').read_text(encoding='utf-8-sig')
        )
        result = self.pipeline.analyze_document(document)

        fixed = apply_fixes(document, result.issues)

        self.assertTrue(any(section.title == '\u0412\u044b\u0432\u043e\u0434\u044b' for section in fixed.sections))
        self.assertTrue(any('\u041f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435' in section.title for section in fixed.sections))
        self.assertTrue(any('\u0421\u043f\u0438\u0441\u043e\u043a \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432' in section.title for section in fixed.sections))
        first_section = fixed.sections[0]
        self.assertIn('\u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0438', first_section.text.lower())

    def test_build_corrected_docx_returns_valid_docx_bytes(self) -> None:
        document = DocumentInput.model_validate_json(
            Path('tests/fixtures/documents/demo_figure_caption.json').read_text(encoding='utf-8-sig')
        )
        result = self.pipeline.analyze_document(document)
        fixed = apply_fixes(document, result.issues)

        content = build_corrected_docx(fixed)

        self.assertTrue(content.startswith(b'PK'))
        with zipfile.ZipFile(BytesIO(content)) as archive:
            xml = archive.read('word/document.xml').decode('utf-8')
        self.assertNotIn('\u0420\u0438\u0441\u0443\u043d\u043e\u043a 1 -', xml)
        self.assertIn('\u0421\u043f\u0438\u0441\u043e\u043a \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432', xml)


    def test_apply_fixes_normalizes_abbreviated_figure_caption(self) -> None:
        document = DocumentInput(
            document_id='doc_abbrev_fix',
            standard_id='gost_7_32_2017',
            meta={'filename': 'demo.docx', 'title': 'Demo', 'language': 'ru'},
            sections=[{'id': 'sec_1', 'number': '1', 'title': '\u0412\u0432\u0435\u0434\u0435\u043d\u0438\u0435', 'level': 1, 'text': ''}],
            paragraphs=[{'id': 'p_1', 'section_id': 'sec_1', 'text': '\u0421\u043c. \u0440\u0438\u0441. 1.', 'position': {'page': 1, 'paragraph_index': 1}}],
            figures=[{'id': 'fig_1', 'caption': '\u0420\u0438\u0441. 1 \u0410\u0440\u0445\u0438\u0442\u0435\u043a\u0442\u0443\u0440\u0430 \u0441\u0438\u0441\u0442\u0435\u043c\u044b', 'position': {'page': 1, 'paragraph_index': 2}}],
        )
        result = self.pipeline.analyze_document(document)

        fixed = apply_fixes(document, result.issues)

        self.assertEqual(fixed.figures[0].caption, '\u0420\u0438\u0441\u0443\u043d\u043e\u043a 1 - \u0410\u0440\u0445\u0438\u0442\u0435\u043a\u0442\u0443\u0440\u0430 \u0441\u0438\u0441\u0442\u0435\u043c\u044b')


    def test_apply_fixes_does_not_synthesize_missing_figure_caption(self) -> None:
        document = DocumentInput.model_validate_json(
            Path('tests/fixtures/documents/demo_figure_caption.json').read_text(encoding='utf-8-sig')
        )
        result = self.pipeline.analyze_document(document)

        fixed = apply_fixes(document, result.issues)

        self.assertEqual(fixed.figures[0].caption, '')


    def test_apply_fixes_to_source_docx_centers_figure_caption(self) -> None:
        source = WordDocument()
        source.add_paragraph('\u0412 \u0442\u0435\u043a\u0441\u0442\u0435 \u0434\u0430\u043d\u0430 \u0441\u0441\u044b\u043b\u043a\u0430 \u043d\u0430 \u0440\u0438\u0441\u0443\u043d\u043e\u043a 1.')
        caption = source.add_paragraph('\u0420\u0438\u0441\u0443\u043d\u043e\u043a 1 - \u0410\u0440\u0445\u0438\u0442\u0435\u043a\u0442\u0443\u0440\u0430 \u0441\u0438\u0441\u0442\u0435\u043c\u044b')
        caption.alignment = WD_ALIGN_PARAGRAPH.LEFT

        buffer = BytesIO()
        source.save(buffer)
        source_bytes = buffer.getvalue()

        parsed = parse_docx_to_document(
            source_bytes,
            filename='figure_alignment.docx',
            standard_id='gost_7_32_2017',
            document_id='figure_alignment',
        )
        result = self.pipeline.analyze_document(parsed)

        self.assertIn('figure_caption_not_centered', [issue.subtype for issue in result.issues])

        fixed_bytes = apply_fixes_to_source_docx(source_bytes, parsed, result.issues)
        fixed_doc = WordDocument(BytesIO(fixed_bytes))
        fixed_caption = next(paragraph for paragraph in fixed_doc.paragraphs if '\u0420\u0438\u0441\u0443\u043d\u043e\u043a 1 - \u0410\u0440\u0445\u0438\u0442\u0435\u043a\u0442\u0443\u0440\u0430 \u0441\u0438\u0441\u0442\u0435\u043c\u044b' in paragraph.text)

        self.assertEqual(fixed_caption.alignment, WD_ALIGN_PARAGRAPH.CENTER)


    def test_apply_fixes_to_source_docx_keeps_centering_when_caption_text_changes(self) -> None:
        source = WordDocument()
        source.add_paragraph('1 \u0412\u0432\u0435\u0434\u0435\u043d\u0438\u0435')
        source.add_paragraph('\u0412 \u0442\u0435\u043a\u0441\u0442\u0435 \u0434\u0430\u043d\u0430 \u0441\u0441\u044b\u043b\u043a\u0430 \u043d\u0430 \u0440\u0438\u0441\u0443\u043d\u043e\u043a 1.')
        caption = source.add_paragraph('\u0420\u0438\u0441\u0443\u043d\u043e\u043a 1 \u0410\u0440\u0445\u0438\u0442\u0435\u043a\u0442\u0443\u0440\u0430 \u0441\u0438\u0441\u0442\u0435\u043c\u044b.')
        caption.alignment = WD_ALIGN_PARAGRAPH.LEFT

        buffer = BytesIO()
        source.save(buffer)
        source_bytes = buffer.getvalue()

        parsed = parse_docx_to_document(
            source_bytes,
            filename='figure_alignment_and_format.docx',
            standard_id='gost_7_32_2017',
            document_id='figure_alignment_and_format',
        )
        result = self.pipeline.analyze_document(parsed)

        self.assertIn('figure_caption_not_centered', [issue.subtype for issue in result.issues])
        self.assertIn('invalid_figure_caption_format', [issue.subtype for issue in result.issues])

        fixed_bytes = apply_fixes_to_source_docx(source_bytes, parsed, result.issues)
        fixed_doc = WordDocument(BytesIO(fixed_bytes))
        fixed_caption = next(paragraph for paragraph in fixed_doc.paragraphs if '\u0420\u0438\u0441\u0443\u043d\u043e\u043a 1' in paragraph.text)

        self.assertEqual(fixed_caption.alignment, WD_ALIGN_PARAGRAPH.CENTER)


    def test_apply_fixes_to_source_docx_updates_multiple_figure_captions(self) -> None:
        source = WordDocument()
        source.add_paragraph('1 \u0412\u0432\u0435\u0434\u0435\u043d\u0438\u0435')
        source.add_paragraph('\u0412 \u0442\u0435\u043a\u0441\u0442\u0435 \u0434\u0430\u043d\u0430 \u0441\u0441\u044b\u043b\u043a\u0430 \u043d\u0430 \u0440\u0438\u0441\u0443\u043d\u043e\u043a 1.')
        first = source.add_paragraph('\u0420\u0438\u0441. 1 \u0410\u0440\u0445\u0438\u0442\u0435\u043a\u0442\u0443\u0440\u0430 \u0441\u0438\u0441\u0442\u0435\u043c\u044b.')
        first.alignment = WD_ALIGN_PARAGRAPH.LEFT
        source.add_paragraph('\u0412 \u0442\u0435\u043a\u0441\u0442\u0435 \u0434\u0430\u043d\u0430 \u0441\u0441\u044b\u043b\u043a\u0430 \u043d\u0430 \u0440\u0438\u0441\u0443\u043d\u043e\u043a 2.')
        second = source.add_paragraph('\u0440\u0438\u0441 2 - \u0421\u0445\u0435\u043c\u0430 \u043c\u043e\u0434\u0443\u043b\u044f.')
        second.alignment = WD_ALIGN_PARAGRAPH.LEFT

        buffer = BytesIO()
        source.save(buffer)
        source_bytes = buffer.getvalue()

        parsed = parse_docx_to_document(
            source_bytes,
            filename='multiple_figures.docx',
            standard_id='gost_7_32_2017',
            document_id='multiple_figures',
        )
        result = self.pipeline.analyze_document(parsed)

        fixed_bytes = apply_fixes_to_source_docx(source_bytes, parsed, result.issues)
        fixed_doc = WordDocument(BytesIO(fixed_bytes))
        captions = [paragraph for paragraph in fixed_doc.paragraphs if '\u0420\u0438\u0441\u0443\u043d\u043e\u043a 1' in paragraph.text or '\u0420\u0438\u0441\u0443\u043d\u043e\u043a 2' in paragraph.text]

        self.assertEqual(len(captions), 2)
        self.assertIn('\u0420\u0438\u0441\u0443\u043d\u043e\u043a 1 - \u0410\u0440\u0445\u0438\u0442\u0435\u043a\u0442\u0443\u0440\u0430 \u0441\u0438\u0441\u0442\u0435\u043c\u044b', captions[0].text)
        self.assertIn('\u0420\u0438\u0441\u0443\u043d\u043e\u043a 2 - \u0421\u0445\u0435\u043c\u0430 \u043c\u043e\u0434\u0443\u043b\u044f', captions[1].text)
        self.assertFalse(captions[0].text.endswith('.'))
        self.assertFalse(captions[1].text.endswith('.'))
        self.assertEqual(captions[0].alignment, WD_ALIGN_PARAGRAPH.CENTER)
        self.assertEqual(captions[1].alignment, WD_ALIGN_PARAGRAPH.CENTER)


    def test_apply_fixes_to_source_docx_renumbers_section_headings(self) -> None:
        source = WordDocument()
        source.add_paragraph('2 Введение')
        source.add_paragraph('Текст введения')
        source.add_paragraph('2.2 Основная часть')
        source.add_paragraph('Текст основной части')
        source.add_paragraph('4 Заключение')
        source.add_paragraph('Текст заключения')
        source.add_paragraph('5 Список использованных источников')
        source.add_paragraph('[1] Источник')

        buffer = BytesIO()
        source.save(buffer)
        source_bytes = buffer.getvalue()

        parsed = parse_docx_to_document(
            source_bytes,
            filename='section_renumbering.docx',
            standard_id='gost_7_32_2017',
            document_id='section_renumbering',
        )
        result = self.pipeline.analyze_document(parsed)

        self.assertIn('numbering_error', [issue.subtype for issue in result.issues])

        fixed_bytes = apply_fixes_to_source_docx(source_bytes, parsed, result.issues)
        fixed_doc = WordDocument(BytesIO(fixed_bytes))
        headings = [paragraph.text for paragraph in fixed_doc.paragraphs if paragraph.text and paragraph.text[0].isdigit()]

        self.assertIn('1 Введение', headings)
        self.assertIn('1.1 Основная часть', headings)
        self.assertIn('2 Заключение', headings)
        self.assertIn('3 Список использованных источников', headings)


if __name__ == '__main__':
    unittest.main()
