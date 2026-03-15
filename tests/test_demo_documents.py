from pathlib import Path
import unittest

from app.orchestration.pipeline import DocumentPipeline
from app.schemas.document import DocumentInput
from app.standards.ingest import StandardIngestor
from app.standards.registry import StandardRegistry
from tests.support.fake_provider import FakeProvider


FIXTURES_DIR = Path('tests/fixtures/documents')


class DemoDocumentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        StandardIngestor().ingest_pdf('gost_7_32_2017')
        cls.pipeline = DocumentPipeline(llm_provider=FakeProvider(), registry=StandardRegistry())

    def test_demo_figure_caption_document(self) -> None:
        result = self.pipeline.analyze_document(self._load('demo_figure_caption.json'))
        subtypes = [issue.subtype for issue in result.issues]
        self.assertIn('missing_figure_caption', subtypes)
        self.assertIn('heading_trailing_period', subtypes)

    def test_demo_table_and_refs_document(self) -> None:
        result = self.pipeline.analyze_document(self._load('demo_table_and_refs.json'))
        subtypes = [issue.subtype for issue in result.issues]
        self.assertIn('invalid_table_caption_format', subtypes)
        self.assertIn('missing_references_section', subtypes)
        self.assertIn('missing_section_number', subtypes)

    def test_demo_appendix_heading_document(self) -> None:
        result = self.pipeline.analyze_document(self._load('demo_appendix_heading.json'))
        subtypes = [issue.subtype for issue in result.issues]
        self.assertIn('invalid_appendix_heading', subtypes)
        self.assertIn('heading_trailing_period', subtypes)

    def _load(self, filename: str) -> DocumentInput:
        return DocumentInput.model_validate_json((FIXTURES_DIR / filename).read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    unittest.main()
