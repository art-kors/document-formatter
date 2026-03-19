from collections import Counter
import os
from io import BytesIO
import json
import unittest
import zipfile
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import dependencies
from app.llm.base import EmbeddingProvider, LLMProvider
from app.main import app
from app.orchestration.pipeline import DocumentPipeline
from app.schemas.document import DocumentInput
from app.standards.ingest import StandardIngestor
from app.standards.registry import StandardRegistry


class FakeProvider(LLMProvider, EmbeddingProvider):
    BASIS = [
        'рисунок',
        'подпись',
        'таблица',
        'заголовок',
        'источник',
        'приложение',
        'нумерация',
        'наименование',
    ]

    def chat(self, message: str) -> str:
        return 'ok'

    def embed(self, text: str):
        normalized = text.lower().replace('рисунка', 'рисунок')
        counts = Counter(normalized.split())
        return [float(counts.get(token, 0)) for token in self.BASIS]


def _build_minimal_docx(paragraphs: list[str]) -> bytes:
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
'''
    doc_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships" />
'''
    body = ''.join(
        f'<w:p><w:r><w:t xml:space="preserve">{paragraph}</w:t></w:r></w:p>'
        for paragraph in paragraphs
    )
    document_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{body}<w:sectPr/></w:body>
</w:document>'''
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types)
        archive.writestr('_rels/.rels', root_rels)
        archive.writestr('word/document.xml', document_xml)
        archive.writestr('word/_rels/document.xml.rels', doc_rels)
    return buffer.getvalue()


class AnalyzeFileApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        StandardIngestor().ingest_pdf('gost_7_32_2017')

    def setUp(self) -> None:
        self._old_log_dir = os.environ.get('ANALYSIS_LOG_DIR')
        os.environ['ANALYSIS_LOG_DIR'] = 'logs_test_runtime'
        dependencies._pipeline = DocumentPipeline(llm_provider=FakeProvider(), registry=StandardRegistry())
        self.client = TestClient(app)

    def tearDown(self) -> None:
        dependencies._pipeline = None
        if self._old_log_dir is None:
            os.environ.pop('ANALYSIS_LOG_DIR', None)
        else:
            os.environ['ANALYSIS_LOG_DIR'] = self._old_log_dir

    def test_analyze_file_endpoint_returns_report(self) -> None:
        text = '1 Основная часть.\n\nНа рисунке 1 показана архитектура решения.\n\n6 Список использованных источников\n\n'
        response = self.client.post(
            '/analyze-file',
            files={'document': ('report.txt', text.encode('utf-8'), 'text/plain')},
            data={'standard_id': 'gost_7_32_2017', 'document_id': 'api_doc_1'},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['document_id'], 'api_doc_1')
        self.assertEqual(payload['standard_id'], 'gost_7_32_2017')
        self.assertIn('rag_agent', payload['agents_run'])
        self.assertGreaterEqual(payload['summary']['total_issues'], 1)
        subtypes = [issue['subtype'] for issue in payload['issues']]
        self.assertIn('heading_trailing_period', subtypes)

    def test_analyze_file_endpoint_can_return_parsed_document(self) -> None:
        text = '1 Введение\n\nРисунок 1 - Архитектура системы\n\n6 Список использованных источников\n\n[1] ГОСТ 7.32-2017'
        response = self.client.post(
            '/analyze-file',
            files={'document': ('report.txt', text.encode('utf-8'), 'text/plain')},
            data={
                'standard_id': 'gost_7_32_2017',
                'document_id': 'api_doc_2',
                'include_parsed_document': 'true',
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('parsed_document', payload)
        self.assertEqual(payload['parsed_document']['document_id'], 'api_doc_2')
        self.assertGreaterEqual(len(payload['parsed_document']['sections']), 1)
        self.assertEqual(payload['parsed_document']['sections'][0]['number'], '1')

    def test_analyze_file_endpoint_rejects_unknown_standard(self) -> None:
        response = self.client.post(
            '/analyze-file',
            files={'document': ('report.txt', '1 Введение'.encode('utf-8'), 'text/plain')},
            data={'standard_id': 'unknown_standard'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Unknown standard_id', response.json()['detail'])

    def test_apply_fixes_file_endpoint_returns_preserved_docx(self) -> None:
        source_bytes = _build_minimal_docx([
            '1 Введение.',
            'Короче говоря, эта штука работает.',
            '2 Основная часть',
            'На рисунке 1 показана архитектура решения.',
            'Рисунок 1 Архитектура системы',
            '2.2 Результаты',
            'Приложение Материалы',
        ])

        analysis_response = self.client.post(
            '/analyze-file',
            files={'document': ('apply_fix.docx', source_bytes, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')},
            data={
                'standard_id': 'gost_7_32_2017',
                'document_id': 'apply_docx_1',
                'include_parsed_document': 'true',
            },
        )
        self.assertEqual(analysis_response.status_code, 200)
        payload = analysis_response.json()

        fix_response = self.client.post(
            '/apply-fixes-file',
            files={'document': ('apply_fix.docx', source_bytes, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')},
            data={
                'parsed_document_json': json.dumps(payload['parsed_document'], ensure_ascii=False),
                'issues_json': json.dumps(payload['issues'], ensure_ascii=False),
                'output_filename': '\u041f\u0440\u0438\u043c\u0435\u043d\u0435\u043d\u043d\u044b\u0439_\u043e\u0442\u0447\u0435\u0442.docx',
            },
        )

        self.assertEqual(fix_response.status_code, 200)
        self.assertIn("filename*=UTF-8''", fix_response.headers['content-disposition'])
        self.assertIn('filename="', fix_response.headers['content-disposition'])
        self.assertTrue(fix_response.content.startswith(b'PK'))

    def test_fix_document_endpoint_returns_docx(self) -> None:
        document = DocumentInput.model_validate_json(
            '{"document_id":"doc_fix_json","standard_id":"gost_7_32_2017","meta":{"filename":"demo.docx","title":"Demo","language":"ru"},"sections":[{"id":"sec_1","number":"1","title":"Выводы.","level":1,"text":"Дополнительные материалы вынесены в конец документа."},{"id":"sec_app","number":"","title":"Приложение Материалы","level":1,"text":"В приложении размещены дополнительные диаграммы."}],"paragraphs":[{"id":"p_1","section_id":"sec_1","text":"Дополнительные материалы вынесены в конец документа.","position":{"page":1,"paragraph_index":1}}],"tables":[],"figures":[]}'
        )
        result = dependencies._pipeline.analyze_document(document)

        response = self.client.post(
            '/fix-document',
            json={
                'document': document.model_dump(),
                'issues': [issue.model_dump(mode='json') for issue in result.issues],
                'output_filename': '\u0418\u0441\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043d\u044b\u0439_\u043e\u0442\u0447\u0435\u0442.docx',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers['content-type'],
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        self.assertIn("filename*=UTF-8''", response.headers['content-disposition'])
        self.assertIn('filename="', response.headers['content-disposition'])
        self.assertTrue(response.content.startswith(b'PK'))


    def test_analyze_file_endpoint_falls_back_when_python_docx_cannot_parse_file(self) -> None:
        source_bytes = _build_minimal_docx([
            '1 Введение',
            'На рисунке 1 показана архитектура.',
        ])

        with patch('app.api.routes_analysis.parse_docx_to_document', side_effect=ValueError("file '<_io.BytesIO object>' is not a Word file, content type is 'application/vnd.openxmlformats-officedocument.themeManager+xml'")):
            response = self.client.post(
                '/analyze-file',
                files={'document': ('broken.docx', source_bytes, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')},
                data={
                    'standard_id': 'gost_7_32_2017',
                    'document_id': 'api_doc_docx_fallback',
                    'include_parsed_document': 'true',
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['parsed_document']['meta']['extras']['source_format'], 'docx_fallback')
        self.assertIn('themeManager', payload['parsed_document']['meta']['extras']['docx_parser_error'])


if __name__ == '__main__':
    unittest.main()
