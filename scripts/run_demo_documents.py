import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.orchestration.pipeline import DocumentPipeline
from app.schemas.document import DocumentInput
from app.standards.ingest import StandardIngestor
from app.standards.registry import StandardRegistry
from tests.support.fake_provider import FakeProvider


FIXTURES_DIR = PROJECT_ROOT / 'tests' / 'fixtures' / 'documents'


def load_document(path: Path) -> DocumentInput:
    return DocumentInput.model_validate_json(path.read_text(encoding='utf-8-sig'))


def main() -> None:
    StandardIngestor().ingest_pdf('gost_7_32_2017')
    pipeline = DocumentPipeline(llm_provider=FakeProvider(), registry=StandardRegistry())

    fixture_paths = sorted(FIXTURES_DIR.glob('*.json'))
    if not fixture_paths:
        print('No demo documents found.')
        return

    for path in fixture_paths:
        document = load_document(path)
        result = pipeline.analyze_document(document)
        print('=' * 80)
        print(f'Document: {path.name}')
        print(f'Total issues: {result.summary.total_issues}')
        print(f'By type: {result.summary.by_type}')
        print(f'By severity: critical={result.summary.critical}, warning={result.summary.warning}, info={result.summary.info}')
        print('Issues:')
        for issue in result.issues:
            ref = issue.standard_reference
            location = issue.location
            print(
                '- '
                f'{issue.subtype} | {issue.severity} | page={location.page} | '
                f'section={location.section_id} | rule={ref.rule_id} | {issue.message}'
            )
            if issue.evidence:
                print(f'  evidence: {issue.evidence}')
            if ref.quote:
                print(f'  quote: {ref.quote}')
            if issue.suggestion:
                print(f'  suggestion: {issue.suggestion}')


if __name__ == '__main__':
    main()
