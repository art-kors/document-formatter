from io import BytesIO
from pathlib import Path
import unittest
import zipfile

from app.fixing.document_fixer import apply_fixes, build_corrected_docx
from app.orchestration.pipeline import DocumentPipeline
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
        self.assertIn('\u0420\u0438\u0441\u0443\u043d\u043e\u043a 1 -', xml)
        self.assertIn('\u0421\u043f\u0438\u0441\u043e\u043a \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432', xml)


if __name__ == '__main__':
    unittest.main()
