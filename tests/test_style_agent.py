import unittest

from app.agents.style_agent.checks import _build_style_prompt, build_style_summary, run_style_checks
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
      "subtype": "spelling_error",
      "severity": "warning",
      "confidence": "high",
      "message": "\u041e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d\u0430 \u043e\u0440\u0444\u043e\u0433\u0440\u0430\u0444\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u043e\u0448\u0438\u0431\u043a\u0430",
      "evidence": "\u0421\u043b\u043e\u0432\u043e '???????????' \u043d\u0430\u043f\u0438\u0441\u0430\u043d\u043e \u0441 \u043e\u043f\u0435\u0447\u0430\u0442\u043a\u043e\u0439.",
      "before": "???????????",
      "after": "????????????"
    },
    {
      "paragraph_id": "p_1",
      "subtype": "long_sentence",
      "severity": "info",
      "confidence": "high",
      "message": "\u041f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u0441\u043b\u0438\u0448\u043a\u043e\u043c \u0434\u043b\u0438\u043d\u043d\u043e\u0435 \u0438 \u0435\u0433\u043e \u0441\u0442\u043e\u0438\u0442 \u0440\u0430\u0437\u0431\u0438\u0442\u044c",
      "evidence": "\u041f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u043f\u0435\u0440\u0435\u0433\u0440\u0443\u0436\u0435\u043d\u043e \u0438 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u0441\u043b\u0438\u0448\u043a\u043e\u043c \u043c\u043d\u043e\u0433\u043e \u0441\u043b\u043e\u0432.",
      "before": "????? ??????? ???????????.",
      "after": "?????? ???????? ???????????. ?????? ???????? ???????????."
    }
  ]
}"""


class LowConfidenceStyleProvider(FakeProvider):
    def chat(self, message: str) -> str:
        return """{
  "issues": [
    {
      "paragraph_id": "p_1",
      "subtype": "spelling_error",
      "severity": "warning",
      "confidence": "low",
      "message": "\u0421\u043e\u043c\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u0430\u044f \u043e\u043f\u0435\u0447\u0430\u0442\u043a\u0430",
      "evidence": "LLM \u043d\u0435 \u0443\u0432\u0435\u0440\u0435\u043d\u0430 \u0432 \u043e\u0448\u0438\u0431\u043a\u0435.",
      "before": "?????",
      "after": "??????"
    }
  ]
}"""


class SoftStyleProvider(FakeProvider):
    def chat(self, message: str) -> str:
        return """{
  "issues": [
    {
      "paragraph_id": "p_1",
      "subtype": "informal_wording",
      "severity": "warning",
      "confidence": "high",
      "message": "РЎР»РѕРІРѕ РЅРµ Р·РІСѓС‡РёС‚ РЅР°СѓС‡РЅРѕ",
      "evidence": "РњРѕРґРµР»Рё РЅРµ РЅСЂР°РІРёС‚СЃСЏ РЅРµР№С‚СЂР°Р»СЊРЅРѕРµ СЃР»РѕРІРѕ.",
      "before": "СЃРїСЂР°РІРѕС‡РЅС‹Рµ РґР°РЅРЅС‹Рµ",
      "after": "РЅРѕСЂРјР°С‚РёРІРЅР°СЏ РёРЅС„РѕСЂРјР°С†РёСЏ"
    }
  ]
}"""


class StyleAgentTests(unittest.TestCase):

    def test_run_style_checks_uses_llm_structured_response(self) -> None:
        document = DocumentInput(
            document_id="doc_style_llm",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="\u0412\u0432\u0435\u0434\u0435\u043d\u0438\u0435", level=1)],
            paragraphs=[
                Paragraph(
                    id="p_1",
                    section_id="sec_1",
                    text=(
                        "\u0422\u0435\u043a\u0441\u0442 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 ??????????? \u0441\u0438\u0441\u0442\u0435\u043c\u044b \u0438 \u043f\u0440\u0438 \u044d\u0442\u043e\u043c \u043e\u0441\u0442\u0430\u0435\u0442\u0441\u044f \u043e\u0447\u0435\u043d\u044c \u0434\u043b\u0438\u043d\u043d\u044b\u043c, "
                        "\u043d\u0430\u0441\u0442\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u0438\u043d\u043d\u044b\u043c, \u0447\u0442\u043e \u043c\u043e\u0434\u0435\u043b\u044c \u0434\u043e\u043b\u0436\u043d\u0430 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0438\u0442\u044c \u0440\u0430\u0437\u0431\u0438\u0442\u044c \u0435\u0433\u043e \u043d\u0430 \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e "
                        "\u043a\u043e\u0440\u043e\u0442\u043a\u0438\u0445 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0439 \u0434\u043b\u044f \u0443\u0434\u043e\u0431\u0441\u0442\u0432\u0430 \u0447\u0442\u0435\u043d\u0438\u044f \u0438 \u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u043e\u0433\u043e \u0432\u043e\u0441\u043f\u0440\u0438\u044f\u0442\u0438\u044f \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u0430."
                    ),
                    position=Position(page=1, paragraph_index=1),
                )
            ],
        )

        issues = run_style_checks(document, llm_provider=StructuredStyleProvider())

        self.assertEqual({issue.subtype for issue in issues}, {"spelling_error", "long_sentence"})
        spelling_issue = next(issue for issue in issues if issue.subtype == "spelling_error")
        self.assertEqual(spelling_issue.location.paragraph_id, "p_1")
        self.assertEqual(spelling_issue.suggestion.before, "???????????")
        self.assertEqual(spelling_issue.suggestion.after, "????????????")

    def test_run_style_checks_ignores_low_confidence_llm_flags(self) -> None:
        document = DocumentInput(
            document_id="doc_style_low_confidence",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="\u0412\u0432\u0435\u0434\u0435\u043d\u0438\u0435", level=1)],
            paragraphs=[
                Paragraph(
                    id="p_1",
                    section_id="sec_1",
                    text="\u0412 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0435 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u044e\u0442\u0441\u044f \u0441\u043f\u0440\u0430\u0432\u043e\u0447\u043d\u044b\u0435 \u0434\u0430\u043d\u043d\u044b\u0435 \u0438 \u0442\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u043e\u0431\u043e\u0437\u043d\u0430\u0447\u0435\u043d\u0438\u044f.",
                    position=Position(page=1, paragraph_index=1),
                )
            ],
        )

        issues = run_style_checks(document, llm_provider=LowConfidenceStyleProvider())

        self.assertEqual(issues, [])

    def test_run_style_checks_ignores_llm_scientific_rewrites(self) -> None:
        document = DocumentInput(
            document_id="doc_style_soft_llm",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="РћСЃРЅРѕРІРЅР°СЏ С‡Р°СЃС‚СЊ", level=1)],
            paragraphs=[
                Paragraph(
                    id="p_1",
                    section_id="sec_1",
                    text="РЎРёСЃС‚РµРјР° РёСЃРїРѕР»СЊР·СѓРµС‚ СЃРїСЂР°РІРѕС‡РЅС‹Рµ РґР°РЅРЅС‹Рµ Рё СЂР°СЃС‡РµС‚РЅС‹Рµ РїР°СЂР°РјРµС‚СЂС‹.",
                    position=Position(page=1, paragraph_index=1),
                )
            ],
        )

        issues = run_style_checks(document, llm_provider=SoftStyleProvider())

        self.assertEqual(issues, [])

    def test_run_style_checks_detects_only_hard_colloquial_and_informal_phrases(self) -> None:
        document = DocumentInput(
            document_id="doc_style_colloquial",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="\u0412\u0432\u0435\u0434\u0435\u043d\u0438\u0435", level=1)],
            paragraphs=[
                Paragraph(
                    id="p_1",
                    section_id="sec_1",
                    text="\u041a\u043e\u0440\u043e\u0447\u0435 \u0433\u043e\u0432\u043e\u0440\u044f, \u044d\u0442\u0430 \u0445\u0440\u0435\u043d\u044c \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u043e\u0447\u0435\u043d\u044c \u0431\u044b\u0441\u0442\u0440\u043e.",
                    position=Position(page=1, paragraph_index=1),
                )
            ],
        )

        issues = run_style_checks(document)
        subtypes = [issue.subtype for issue in issues]

        self.assertIn("colloquial_phrase", subtypes)
        self.assertIn("informal_wording", subtypes)
        self.assertEqual(len(subtypes), 2)

    def test_run_style_checks_does_not_rewrite_neutral_technical_text(self) -> None:
        document = DocumentInput(
            document_id="doc_style_neutral",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="\u041e\u0441\u043d\u043e\u0432\u043d\u0430\u044f \u0447\u0430\u0441\u0442\u044c", level=1)],
            paragraphs=[
                Paragraph(
                    id="p_1",
                    section_id="sec_1",
                    text="\u0421\u0438\u0441\u0442\u0435\u043c\u0430 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0435\u0442 \u0441\u043f\u0440\u0430\u0432\u043e\u0447\u043d\u044b\u0435 \u0434\u0430\u043d\u043d\u044b\u0435 \u0438 \u0440\u0430\u0441\u0447\u0435\u0442\u043d\u044b\u0435 \u043f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u044b \u0434\u043b\u044f \u0430\u043d\u0430\u043b\u0438\u0437\u0430.",
                    position=Position(page=1, paragraph_index=1),
                )
            ],
        )

        issues = run_style_checks(document)

        self.assertEqual(issues, [])

    def test_run_style_checks_detects_only_extremely_long_sentence(self) -> None:
        long_sentence = (
            "\u0412 \u0440\u0430\u0431\u043e\u0442\u0435 \u0440\u0430\u0441\u0441\u043c\u0430\u0442\u0440\u0438\u0432\u0430\u0435\u0442\u0441\u044f \u0441\u0438\u0441\u0442\u0435\u043c\u0430, \u043a\u043e\u0442\u043e\u0440\u0430\u044f \u0434\u043e\u043b\u0436\u043d\u0430 \u043e\u0431\u0435\u0441\u043f\u0435\u0447\u0438\u0432\u0430\u0442\u044c \u0441\u0431\u043e\u0440 \u0434\u0430\u043d\u043d\u044b\u0445, "
            "\u043a\u043e\u0442\u043e\u0440\u044b\u0435 \u043f\u043e\u0441\u0442\u0443\u043f\u0430\u044e\u0442 \u0438\u0437 \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u0438\u0445 \u043d\u0435\u0437\u0430\u0432\u0438\u0441\u0438\u043c\u044b\u0445 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432, \u043a\u043e\u0442\u043e\u0440\u044b\u0435 \u043e\u0431\u043d\u043e\u0432\u043b\u044f\u044e\u0442\u0441\u044f \u0441 \u0440\u0430\u0437\u043d\u043e\u0439 \u0447\u0430\u0441\u0442\u043e\u0442\u043e\u0439, "
            "\u0438 \u043a\u043e\u0442\u043e\u0440\u0430\u044f \u043f\u0440\u0438 \u044d\u0442\u043e\u043c \u0434\u043e\u043b\u0436\u043d\u0430 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0442\u044c \u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u0430\u043d\u043d\u043e\u0441\u0442\u044c \u0441\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u044f, \u043f\u043e\u0441\u043a\u043e\u043b\u044c\u043a\u0443 \u043e\u0442 \u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u043e\u0441\u0442\u0438 \u044d\u0442\u043e\u0433\u043e "
            "\u043c\u0435\u0445\u0430\u043d\u0438\u0437\u043c\u0430 \u0437\u0430\u0432\u0438\u0441\u0438\u0442 \u0434\u0430\u043b\u044c\u043d\u0435\u0439\u0448\u0430\u044f \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0430, \u0432\u0438\u0437\u0443\u0430\u043b\u0438\u0437\u0430\u0446\u0438\u044f, \u0445\u0440\u0430\u043d\u0435\u043d\u0438\u0435 \u0438 \u043f\u043e\u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0430\u044f \u0430\u043d\u0430\u043b\u0438\u0442\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u0438\u043d\u0442\u0435\u0440\u043f\u0440\u0435\u0442\u0430\u0446\u0438\u044f \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u043e\u0432, "
            "\u0430 \u0442\u0430\u043a\u0436\u0435 \u043f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u043a\u0430 \u0438\u0442\u043e\u0433\u043e\u0432\u044b\u0445 \u0441\u0432\u043e\u0434\u043e\u043a \u0434\u043b\u044f \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u0438\u0445 \u0440\u0430\u0437\u043d\u044b\u0445 \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u0439 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439, \u043a\u0430\u0436\u0434\u0430\u044f \u0438\u0437 \u043a\u043e\u0442\u043e\u0440\u044b\u0445 \u043e\u0436\u0438\u0434\u0430\u0435\u0442 \u043e\u0442\u0434\u0435\u043b\u044c\u043d\u044b\u0439 "
            "\u0444\u043e\u0440\u043c\u0430\u0442 \u043f\u0440\u0435\u0434\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u0438\u044f \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u0438 \u0438 \u043e\u0442\u0434\u0435\u043b\u044c\u043d\u044b\u0435 \u043a\u0440\u0438\u0442\u0435\u0440\u0438\u0438 \u043e\u0446\u0435\u043d\u043a\u0438 \u043a\u0430\u0447\u0435\u0441\u0442\u0432\u0430 \u0434\u0430\u043d\u043d\u044b\u0445."
        )
        document = DocumentInput(
            document_id="doc_style_long",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="\u041c\u0435\u0442\u043e\u0434\u0438\u043a\u0430", level=1)],
            paragraphs=[Paragraph(id="p_1", section_id="sec_1", text=long_sentence, position=Position(page=2, paragraph_index=3))],
        )

        issues = run_style_checks(document)
        subtypes = [issue.subtype for issue in issues]

        self.assertIn("long_sentence", subtypes)


    def test_local_style_prompt_is_shorter_for_cpu_mode(self) -> None:
        paragraphs = [
            Paragraph(
                id=f"p_{index}",
                section_id="sec_1",
                text=("Очень длинный абзац для проверки локального prompt " * 20) + str(index),
                position=Position(page=1, paragraph_index=index),
            )
            for index in range(1, 21)
        ]
        document = DocumentInput(
            document_id="doc_style_local_prompt",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="Введение", level=1)],
            paragraphs=paragraphs,
        )

        remote_prompt = _build_style_prompt(document, local_mode=False)
        local_prompt = _build_style_prompt(document, local_mode=True)

        self.assertLess(len(local_prompt), len(remote_prompt))
        self.assertLessEqual(local_prompt.count('"paragraph_id"'), 13)
        self.assertIn('Верни не более 6 замечаний.', local_prompt)
    def test_style_service_returns_summary_details(self) -> None:
        document = DocumentInput(
            document_id="doc_style_summary",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="\u0412\u0432\u0435\u0434\u0435\u043d\u0438\u0435", level=1)],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="\u041a\u043e\u0440\u043e\u0447\u0435 \u0433\u043e\u0432\u043e\u0440\u044f, \u044d\u0442\u0430 \u0445\u0440\u0435\u043d\u044c \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442.", position=Position(page=1, paragraph_index=1))
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
            sections=[Section(id="sec_1", number="1", title="\u0412\u0432\u0435\u0434\u0435\u043d\u0438\u0435", level=1)],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="\u041a\u043e\u0440\u043e\u0447\u0435 \u0433\u043e\u0432\u043e\u0440\u044f, \u044d\u0442\u0430 \u0445\u0440\u0435\u043d\u044c \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u0438 \u0434\u0430\u0435\u0442 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442.", position=Position(page=1, paragraph_index=1))
            ],
        )

        pipeline = DocumentPipeline(llm_provider=FakeProvider(), registry=StandardRegistry())
        result = pipeline.analyze_document(document)

        self.assertIn("style", result.summary.by_type)
        self.assertIn("style_agent", result.agents_run)
        self.assertIn("colloquial_phrase", [issue.subtype for issue in result.issues])


if __name__ == "__main__":
    unittest.main()


