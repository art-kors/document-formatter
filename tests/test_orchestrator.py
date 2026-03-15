from collections import Counter
from typing import List
import unittest

from app.llm.base import EmbeddingProvider, LLMProvider
from app.orchestration.pipeline import DocumentPipeline
from app.schemas.document import DocumentInput, DocumentMeta, FigureItem, Paragraph, Position, Section
from app.standards.ingest import StandardIngestor
from app.standards.registry import StandardRegistry


class FakeProvider(LLMProvider, EmbeddingProvider):
    BASIS = ["рисунок", "подпись", "таблица", "заголовок", "источник", "приложение", "нумерация", "наименование"]

    def chat(self, message: str) -> str:
        return "ok"

    def embed(self, text: str) -> List[float]:
        normalized = text.lower().replace("рисунка", "рисунок")
        counts = Counter(normalized.split())
        return [float(counts.get(token, 0)) for token in self.BASIS]


class DocumentPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        StandardIngestor().ingest_pdf("gost_7_32_2017")

    def test_pipeline_collects_rag_issues(self) -> None:
        pipeline = DocumentPipeline(llm_provider=FakeProvider(), registry=StandardRegistry())
        document = DocumentInput(
            document_id="doc_pipeline",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="Основная часть.")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="См. рисунок ниже.", position=Position(page=1, paragraph_index=1))],
            figures=[FigureItem(id="fig_1", caption="", position=Position(page=2))],
        )

        result = pipeline.analyze_document(document)

        self.assertEqual(result.status, "done")
        self.assertGreaterEqual(result.summary.total_issues, 2)
        self.assertIn("formatting", result.summary.by_type)
        self.assertIn("missing_figure_caption", [issue.subtype for issue in result.issues])
        self.assertIn("heading_trailing_period", [issue.subtype for issue in result.issues])


if __name__ == "__main__":
    unittest.main()
