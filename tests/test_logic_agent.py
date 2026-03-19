import unittest

from app.agents.logic_agent.checks import _build_claim_extraction_prompt, run_logic_checks
from app.agents.logic_agent.service import LogicAgentService
from app.llm.local_chat_provider import LocalChatProvider
from app.schemas.document import DocumentInput, DocumentMeta, Paragraph, Position, Section
from tests.support.fake_provider import FakeProvider


class ClaimComparisonProvider(FakeProvider):
    def chat(self, message: str) -> str:
        if 'Extract only atomic factual claims' in message:
            return """{
  "claims": [
    {
      "paragraph_id": "p_1",
      "subject": "verification system",
      "property": "operating mode",
      "value": "fully local operation",
      "polarity": "positive",
      "claim_text": "The system works locally.",
      "confidence": "high"
    },
    {
      "paragraph_id": "p_2",
      "subject": "verification system",
      "property": "operating mode",
      "value": "external api usage",
      "polarity": "positive",
      "claim_text": "The system uses an external API.",
      "confidence": "high"
    }
  ]
}"""
        if 'Compare two claims from the same document' in message:
            return """{
  "has_conflict": true,
  "subtype": "semantic_contradiction",
  "severity": "warning",
  "confidence": "high",
  "message": "There is a contradiction in the system operating mode",
  "evidence": "One fragment states fully local operation, another states external API usage.",
  "suggestion": "Keep only one consistent architecture description."
}"""
        return '{"issues": []}'


class DirectScanProvider(FakeProvider):
    def chat(self, message: str) -> str:
        if 'Extract only atomic factual claims' in message:
            return '{"claims": []}'
        if 'Find only clear logical contradictions' in message:
            return """{
  "issues": [
    {
      "paragraph_id": "p_1",
      "related_paragraph_id": "p_2",
      "subtype": "goal_result_mismatch",
      "severity": "warning",
      "confidence": "high",
      "message": "Goal and result are inconsistent",
      "evidence": "The introduction states one goal, while the conclusion describes another result.",
      "suggestion": "Align the goal and final conclusions."
    }
  ]
}"""
        return '{"issues": []}'


class LocalClaimComparisonProvider(LocalChatProvider):
    def __init__(self) -> None:
        pass

    def chat(self, message: str) -> str:
        if 'Extract only atomic factual claims' in message:
            return """{
  "claims": [
    {
      "paragraph_id": "p_1",
      "subject": "verification system",
      "property": "operating mode",
      "value": "local mode",
      "polarity": "positive",
      "claim_text": "The system works locally.",
      "confidence": "high"
    },
    {
      "paragraph_id": "p_2",
      "subject": "verification system",
      "property": "operating mode",
      "value": "external api",
      "polarity": "positive",
      "claim_text": "The system uses an external API.",
      "confidence": "high"
    }
  ]
}"""
        if 'Compare two claims from the same document' in message:
            return """{
  "has_conflict": true,
  "subtype": "semantic_contradiction",
  "severity": "warning",
  "confidence": "high",
  "message": "There is a contradiction in the system operating mode",
  "evidence": "One fragment states local mode, another states external API usage.",
  "suggestion": "Keep only one consistent architecture description."
}"""
        return '{"issues": []}'


class EmptyLogicProvider(FakeProvider):
    def chat(self, message: str) -> str:
        if 'Extract only atomic factual claims' in message:
            return '{"claims": []}'
        if 'Find only clear logical contradictions' in message:
            return '{"issues": []}'
        return '{"has_conflict": false}'


class LogicAgentTests(unittest.TestCase):
    def test_logic_agent_uses_llm_claims_and_comparison(self) -> None:
        document = DocumentInput(
            document_id="doc_logic_llm",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="????????", level=1)],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="??????? ???????? ????????? ????????.", position=Position(page=1, paragraph_index=1)),
                Paragraph(id="p_2", section_id="sec_1", text="??? ??????? ??????? ?????????? ??????? API.", position=Position(page=1, paragraph_index=2)),
            ],
        )

        issues = run_logic_checks(document, llm_provider=ClaimComparisonProvider())

        self.assertIn("semantic_contradiction", [issue.subtype for issue in issues])
        issue = next(issue for issue in issues if issue.subtype == "semantic_contradiction")
        self.assertEqual(issue.location.paragraph_id, "p_1")
        self.assertIn("external API", issue.evidence)

    def test_logic_agent_uses_direct_scan_when_claims_are_empty(self) -> None:
        document = DocumentInput(
            document_id="doc_logic_direct",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="????????", level=1)],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="?? ???????? ??????? ???? ???? ????????????.", position=Position(page=1, paragraph_index=1)),
                Paragraph(id="p_2", section_id="sec_1", text="? ?????????? ?????? ?????????, ?? ????????? ? ?????????? ?????.", position=Position(page=1, paragraph_index=2)),
            ],
        )

        issues = run_logic_checks(document, llm_provider=DirectScanProvider())

        self.assertIn("goal_result_mismatch", [issue.subtype for issue in issues])

    def test_logic_agent_returns_empty_without_llm_signal(self) -> None:
        document = DocumentInput(
            document_id="doc_logic_empty",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="????????", level=1)],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="??????? ???????? ????????.", position=Position(page=1, paragraph_index=1)),
                Paragraph(id="p_2", section_id="sec_1", text="???????? ??????????? ?????????????.", position=Position(page=1, paragraph_index=2)),
            ],
        )

        issues = run_logic_checks(document, llm_provider=EmptyLogicProvider())

        self.assertEqual(issues, [])

    def test_logic_service_returns_details(self) -> None:
        document = DocumentInput(
            document_id="doc_logic_service",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="????????", level=1)],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="??????? ???????? ????????? ????????.", position=Position(page=1, paragraph_index=1)),
                Paragraph(id="p_2", section_id="sec_1", text="??? ??????? ??????? ?????????? ??????? API.", position=Position(page=1, paragraph_index=2)),
            ],
        )

        result = LogicAgentService(llm_provider=ClaimComparisonProvider()).analyze(document, document.standard_id)

        self.assertEqual(result.agent, "logic_agent")
        self.assertIn("issues_by_subtype", result.details)
        self.assertGreaterEqual(result.details["logic_conflicts"], 1)

    def test_local_claim_extraction_prompt_is_shorter(self) -> None:
        document = DocumentInput(
            document_id="doc_logic_prompt",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="????????", level=1)],
            paragraphs=[
                Paragraph(id=f"p_{i}", section_id="sec_1", text=("??????? ????? ??? ??????????? ? ????? ?????? ???????. " * 20) + str(i), position=Position(page=1, paragraph_index=i))
                for i in range(1, 20)
            ],
        )

        units = [
            type("Unit", (), {"id": paragraph.id, "section_id": paragraph.section_id, "text": paragraph.text, "position": paragraph.position})
            for paragraph in document.paragraphs[:6]
        ]
        remote_prompt = _build_claim_extraction_prompt(units, local_mode=False)
        local_prompt = _build_claim_extraction_prompt(units, local_mode=True)

        self.assertLess(len(local_prompt), len(remote_prompt))
        self.assertIn("Return at most 6 claims.", local_prompt)

    def test_local_logic_provider_finds_contradiction(self) -> None:
        document = DocumentInput(
            document_id="doc_logic_local",
            standard_id="gost_7_32_2017",
            meta=DocumentMeta(filename="report.docx", title="Report"),
            sections=[Section(id="sec_1", number="1", title="????????", level=1)],
            paragraphs=[
                Paragraph(id="p_1", section_id="sec_1", text="??????? ???????? ????????? ????????.", position=Position(page=1, paragraph_index=1)),
                Paragraph(id="p_2", section_id="sec_1", text="??? ??????? ??????? ?????????? ??????? API.", position=Position(page=1, paragraph_index=2)),
            ],
        )

        issues = run_logic_checks(document, llm_provider=LocalClaimComparisonProvider())

        self.assertIn("semantic_contradiction", [issue.subtype for issue in issues])


if __name__ == "__main__":
    unittest.main()
