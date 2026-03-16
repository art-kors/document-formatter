from collections import Counter
from typing import List
import unittest
from unittest.mock import patch

from app.llm.base import EmbeddingProvider, LLMProvider
from app.orchestration.aggregator import collect_issues
from app.orchestration.pipeline import DocumentPipeline
from app.schemas.agent_result import AgentResult
from app.schemas.document import DocumentInput, DocumentMeta, FigureItem, Paragraph, Position, Section
from app.schemas.issue import Issue, IssueLocation, StandardReference
from app.standards.ingest import StandardIngestor
from app.standards.registry import StandardRegistry


class FakeProvider(LLMProvider, EmbeddingProvider):
    BASIS = ["???????", "???????", "???????", "?????????", "????????", "??????????", "?????????", "????????????"]

    def chat(self, message: str) -> str:
        return "ok"

    def embed(self, text: str) -> List[float]:
        normalized = text.lower().replace("???????", "???????")
        counts = Counter(normalized.split())
        return [float(counts.get(token, 0)) for token in self.BASIS]


def _build_issue(issue_id: str) -> Issue:
    return Issue(
        id=issue_id,
        type="formatting",
        subtype="missing_figure_caption",
        severity="warning",
        message="? ??????? ??????????? ???????",
        location=IssueLocation(page=2),
        standard_reference=StandardReference(source="???? 7.32-2017", rule_id="gost_rule_31", quote="..."),
        suggestion="???????? ???????",
        agent="rag_agent",
    )


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
            sections=[Section(id="sec_1", number="1", title="???????? ?????.")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="??. ??????? ????.", position=Position(page=1, paragraph_index=1))],
            figures=[FigureItem(id="fig_1", caption="", position=Position(page=2))],
        )

        result = pipeline.analyze_document(document)

        self.assertEqual(result.status, "done")
        self.assertEqual(result.standard_id, "gost_7_32_2017")
        self.assertIn("rag_agent", result.agents_run)
        self.assertEqual(result.agents_failed, {})
        self.assertGreaterEqual(result.summary.total_issues, 2)
        self.assertIn("formatting", result.summary.by_type)
        self.assertIn("missing_figure_caption", [issue.subtype for issue in result.issues])
        self.assertIn("heading_trailing_period", [issue.subtype for issue in result.issues])

    def test_pipeline_survives_agent_failure(self) -> None:
        pipeline = DocumentPipeline(llm_provider=FakeProvider(), registry=StandardRegistry())
        document = DocumentInput(
            document_id="doc_pipeline_partial",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="???????? ?????.")],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text="??. ??????? ????.", position=Position(page=1, paragraph_index=1))],
            figures=[FigureItem(id="fig_1", caption="", position=Position(page=2))],
        )

        with patch.object(pipeline.style_agent, "analyze", side_effect=RuntimeError("style failed")):
            result = pipeline.analyze_document(document)

        self.assertEqual(result.status, "partial_success")
        self.assertIn("style_agent", result.agents_failed)
        self.assertIn("rag_agent", result.agents_run)
        self.assertGreater(result.summary.total_issues, 0)

    def test_pipeline_validates_standard_id(self) -> None:
        pipeline = DocumentPipeline(llm_provider=FakeProvider(), registry=StandardRegistry())
        document = DocumentInput(
            document_id="doc_missing_standard",
            standard_id="unknown_standard",
            meta=DocumentMeta(filename="report.docx", title="Report"),
        )

        with self.assertRaises(FileNotFoundError):
            pipeline.analyze_document(document)

    def test_collect_issues_removes_exact_duplicates(self) -> None:
        issue = _build_issue("issue_rag_001")
        results = [
            AgentResult(agent="rag_agent", issues=[issue]),
            AgentResult(agent="rag_agent", issues=[issue.model_copy(deep=True)]),
        ]

        issues = collect_issues(results)

        self.assertEqual(len(issues), 1)


if __name__ == "__main__":
    unittest.main()
