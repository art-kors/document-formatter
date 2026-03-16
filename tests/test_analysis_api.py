from collections import Counter
import unittest

from fastapi.testclient import TestClient

from app.api import dependencies
from app.llm.base import EmbeddingProvider, LLMProvider
from app.main import app
from app.orchestration.pipeline import DocumentPipeline
from app.standards.ingest import StandardIngestor
from app.standards.registry import StandardRegistry


class FakeProvider(LLMProvider, EmbeddingProvider):
    BASIS = [
        "рисунок",
        "подпись",
        "таблица",
        "заголовок",
        "источник",
        "приложение",
        "нумерация",
        "наименование",
    ]

    def chat(self, message: str) -> str:
        return "ok"

    def embed(self, text: str):
        normalized = text.lower().replace("рисунка", "рисунок")
        counts = Counter(normalized.split())
        return [float(counts.get(token, 0)) for token in self.BASIS]


class AnalyzeFileApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        StandardIngestor().ingest_pdf("gost_7_32_2017")

    def setUp(self) -> None:
        dependencies._pipeline = DocumentPipeline(llm_provider=FakeProvider(), registry=StandardRegistry())
        self.client = TestClient(app)

    def tearDown(self) -> None:
        dependencies._pipeline = None

    def test_analyze_file_endpoint_returns_report(self) -> None:
        text = """1 Основная часть.

На рисунке 1 показана архитектура решения.

6 Список использованных источников

"""
        response = self.client.post(
            "/analyze-file",
            files={"document": ("report.txt", text.encode("utf-8"), "text/plain")},
            data={"standard_id": "gost_7_32_2017", "document_id": "api_doc_1"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["document_id"], "api_doc_1")
        self.assertEqual(payload["standard_id"], "gost_7_32_2017")
        self.assertIn("rag_agent", payload["agents_run"])
        self.assertGreaterEqual(payload["summary"]["total_issues"], 1)
        subtypes = [issue["subtype"] for issue in payload["issues"]]
        self.assertIn("heading_trailing_period", subtypes)

    def test_analyze_file_endpoint_can_return_parsed_document(self) -> None:
        text = """1 Введение

Рисунок 1 - Архитектура системы

6 Список использованных источников

[1] ГОСТ 7.32-2017"""
        response = self.client.post(
            "/analyze-file",
            files={"document": ("report.txt", text.encode("utf-8"), "text/plain")},
            data={
                "standard_id": "gost_7_32_2017",
                "document_id": "api_doc_2",
                "include_parsed_document": "true",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("parsed_document", payload)
        self.assertEqual(payload["parsed_document"]["document_id"], "api_doc_2")
        self.assertEqual(len(payload["parsed_document"]["figures"]), 1)
        self.assertEqual(payload["parsed_document"]["sections"][0]["number"], "1")

    def test_analyze_file_endpoint_rejects_unknown_standard(self) -> None:
        response = self.client.post(
            "/analyze-file",
            files={"document": ("report.txt", "1 Введение".encode("utf-8"), "text/plain")},
            data={"standard_id": "unknown_standard"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown standard_id", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
