import unittest

from app.agents.style_agent.checks import build_style_summary, run_style_checks
from app.agents.style_agent.service import StyleAgentService
from app.orchestration.pipeline import DocumentPipeline
from app.schemas.document import DocumentInput, DocumentMeta, Paragraph, Position, Section
from app.standards.registry import StandardRegistry
from tests.support.fake_provider import FakeProvider




class StructuredStyleProvider(FakeProvider):
    def chat(self, message: str) -> str:
        return """{
  "issues": [
    {
      "paragraph_id": "p_1",
      "subtype": "informal_wording",
      "severity": "warning",
      "confidence": "high",
      "message": "???????????? ??????? ???????????",
      "evidence": "?????? '??? ?????' ?? ???????? ??? ???????? ??????.",
      "before": "??? ????? ????????",
      "after": "?????? ???????? ????????"
    },
    {
      "paragraph_id": "p_1",
      "subtype": "long_sentence",
      "severity": "info",
      "confidence": "high",
      "message": "??????????? ????? ?????????",
      "evidence": "? ????? ??????????? ??????? ????????? ??????????????? ???????.",
      "before": "?????? ??????, ??? ????? ???????? ????? ?????? ?, ? ?????, ???? ?????????.",
      "after": "??????? ???????? ??????. ?????????? ????????? ????????????? ?????????."
    }
  ]
}"""




class LowConfidenceStyleProvider(FakeProvider):
    def chat(self, message: str) -> str:
        return """{
  "issues": [
    {
      "paragraph_id": "p_1",
      "subtype": "informal_wording",
      "severity": "warning",
      "confidence": "low",
      "message": "???????????? ?????????",
      "evidence": "??????????? ??????????? ?????? ???????? ??????? ??? ???????????.",
      "before": "?????????? ??????",
      "after": "???????? ??????"
    }
  ]
}"""


class StyleAgentTests(unittest.TestCase):

    def test_run_style_checks_uses_llm_structured_response(self) -> None:
        document = DocumentInput(
            document_id="doc_style_llm",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="????????", level=1)],
            paragraphs=[
                Paragraph(
                    id="p_1",
                    section_id="sec_1",
                    text="?????? ??????, ??? ????? ???????? ????? ?????? ?, ? ?????, ???? ?????????.",
                    position=Position(page=1, paragraph_index=1),
                )
            ],
        )

        issues = run_style_checks(document, llm_provider=StructuredStyleProvider())

        self.assertEqual({issue.subtype for issue in issues}, {"informal_wording", "long_sentence"})
        informal_issue = next(issue for issue in issues if issue.subtype == "informal_wording")
        self.assertEqual(informal_issue.location.paragraph_id, "p_1")
        self.assertEqual(informal_issue.suggestion.before, "??? ????? ????????")
        self.assertEqual(informal_issue.suggestion.after, "?????? ???????? ????????")


    def test_run_style_checks_ignores_low_confidence_llm_flags(self) -> None:
        document = DocumentInput(
            document_id="doc_style_low_confidence",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="????????", level=1)],
            paragraphs=[
                Paragraph(
                    id="p_1",
                    section_id="sec_1",
                    text="?????????? ?????? ????????? ? ??????????.",
                    position=Position(page=1, paragraph_index=1),
                )
            ],
        )

        issues = run_style_checks(document, llm_provider=LowConfidenceStyleProvider())

        self.assertEqual(issues, [])

    def test_run_style_checks_detects_colloquial_and_informal_phrases(self) -> None:
        document = DocumentInput(
            document_id="doc_style_colloquial",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="Введение", level=1)],
            paragraphs=[
                Paragraph(
                    id="p_1",
                    section_id="sec_1",
                    text="Короче говоря, эта штука работает очень быстро и, в общем, дает результат.",
                    position=Position(page=1, paragraph_index=1),
                )
            ],
        )

        issues = run_style_checks(document)
        subtypes = [issue.subtype for issue in issues]

        self.assertIn("colloquial_phrase", subtypes)
        self.assertIn("informal_wording", subtypes)
        self.assertIn("style_mismatch", subtypes)
        colloquial_issue = next(issue for issue in issues if issue.subtype == "colloquial_phrase")
        self.assertEqual(colloquial_issue.location.paragraph_id, "p_1")
        self.assertTrue(hasattr(colloquial_issue.suggestion, "before"))
        self.assertTrue(hasattr(colloquial_issue.suggestion, "after"))

    def test_run_style_checks_detects_term_inconsistency(self) -> None:
        document = DocumentInput(
            document_id="doc_style_terms",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="Основная часть", level=1)],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="Система использует внешний API для синхронизации.", position=Position(page=1, paragraph_index=1)),
                Paragraph(id="p_2", section_id="sec_1", text="Далее апи вызывается повторно для получения статуса.", position=Position(page=1, paragraph_index=2)),
            ],
        )

        issues = run_style_checks(document)
        term_issue = next(issue for issue in issues if issue.subtype == "term_inconsistency")

        self.assertIn("API", term_issue.suggestion.after)
        self.assertIn("api", term_issue.evidence.lower())
        self.assertIn("апи", term_issue.evidence.lower())

    def test_run_style_checks_detects_long_and_overloaded_sentence(self) -> None:
        long_sentence = (
            "В работе рассматривается система, которая должна обеспечивать сбор данных, "
            "которые поступают из нескольких независимых источников, которые обновляются с разной частотой, "
            "и которая при этом должна поддерживать согласованность состояния, поскольку от корректности этого "
            "механизма зависит дальнейшая обработка, визуализация, хранение и последующая аналитическая интерпретация результатов."
        )
        document = DocumentInput(
            document_id="doc_style_long",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="Методика", level=1)],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text=long_sentence, position=Position(page=2, paragraph_index=3))],
        )

        issues = run_style_checks(document)
        subtypes = [issue.subtype for issue in issues]

        self.assertIn("long_sentence", subtypes)
        self.assertIn("overloaded_sentence", subtypes)

    def test_style_service_returns_summary_details(self) -> None:
        document = DocumentInput(
            document_id="doc_style_summary",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="Введение", level=1)],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="Короче говоря, эта штука работает.", position=Position(page=1, paragraph_index=1))
            ],
        )

        result = StyleAgentService().analyze(document, document.standard_id)

        self.assertEqual(result.agent, "style_agent")
        self.assertIn("issues_by_subtype", result.details)
        self.assertGreater(result.details["fixable_issues"], 0)

    def test_pipeline_collects_style_issues(self) -> None:
        document = DocumentInput(
            document_id="doc_style_pipeline",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="Введение", level=1)],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="Короче говоря, эта штука работает и дает результат.", position=Position(page=1, paragraph_index=1))
            ],
        )

        pipeline = DocumentPipeline(llm_provider=FakeProvider(), registry=StandardRegistry())
        result = pipeline.analyze_document(document)

        self.assertIn("style", result.summary.by_type)
        self.assertIn("style_agent", result.agents_run)
        self.assertIn("colloquial_phrase", [issue.subtype for issue in result.issues])


if __name__ == "__main__":
    unittest.main()
