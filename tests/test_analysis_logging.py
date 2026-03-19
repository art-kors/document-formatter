import json
import os
from pathlib import Path
import shutil
import unittest

from fastapi.testclient import TestClient

from app.api import dependencies
from app.main import app
from app.orchestration.pipeline import DocumentPipeline
from app.standards.ingest import StandardIngestor
from app.standards.registry import StandardRegistry
from tests.test_analysis_api import FakeProvider


class AnalysisLoggingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        StandardIngestor().ingest_pdf('gost_7_32_2017')

    def setUp(self) -> None:
        dependencies._pipeline = DocumentPipeline(llm_provider=FakeProvider(), registry=StandardRegistry())
        self.client = TestClient(app)

    def tearDown(self) -> None:
        dependencies._pipeline = None

    def test_analyze_file_writes_analytics_log(self) -> None:
        log_dir = Path('logs_test_runtime')
        if log_dir.exists():
            shutil.rmtree(log_dir)
        old = os.environ.get('ANALYSIS_LOG_DIR')
        try:
            os.environ['ANALYSIS_LOG_DIR'] = str(log_dir)
            text = '1 Введение\n\n2 Основная часть\n\n6 Список использованных источников'
            response = self.client.post(
                '/analyze-file',
                files={'document': ('report.txt', text.encode('utf-8'), 'text/plain')},
                data={'standard_id': 'gost_7_32_2017', 'document_id': 'api_doc_log_1'},
            )
        finally:
            if old is None:
                os.environ.pop('ANALYSIS_LOG_DIR', None)
            else:
                os.environ['ANALYSIS_LOG_DIR'] = old

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        log_path = Path(payload['analytics_log_path'])
        self.assertTrue(log_path.exists())

        analytics = json.loads(log_path.read_text(encoding='utf-8'))
        self.assertEqual(analytics['document_id'], 'api_doc_log_1')
        self.assertIn('request_wall_time_ms', analytics)
        self.assertIn('request_cpu_time_ms', analytics)
        self.assertIn('system_memory_total_mb', analytics)
        self.assertIn('human_summary', analytics)
        self.assertIn('Статистика запуска проверки документа', analytics['human_summary'])
        self.assertEqual(analytics['chat_mode'], 'default')
        self.assertEqual(analytics['total_issues'], payload['summary']['total_issues'])
        self.assertNotIn('estimated_min_ram_mb', analytics)
        self.assertNotIn('estimated_recommended_ram_mb', analytics)
        self.assertNotIn('estimated_cpu_threads', analytics)
        self.assertNotIn('expected_latency', analytics)
        self.assertNotIn('document_complexity', analytics)
        self.assertNotIn('complexity_score', analytics)


if __name__ == '__main__':
    unittest.main()
