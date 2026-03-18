import os
from pathlib import Path
import unittest

from app.api import dependencies
from app.api.dependencies import get_chat_provider, get_embedding_provider, get_llm_provider
from app.llm.local_provider import LocalProvider
from app.orchestration.pipeline import DocumentPipeline
from app.schemas.document import DocumentInput
from app.standards.ingest import StandardIngestor
from app.standards.registry import StandardRegistry


class FakeSentenceTransformer:
    def __init__(self, dimension: int = 8):
        self.dimension = dimension

    def encode(self, text: str, normalize_embeddings: bool = True):
        base = [0.0] * self.dimension
        for index, char in enumerate(text.lower()):
            base[index % self.dimension] += (ord(char) % 17) + 1
        if normalize_embeddings:
            norm = sum(value * value for value in base) ** 0.5
            if norm:
                base = [value / norm for value in base]
        return base


class LocalProviderTests(unittest.TestCase):
    def test_embed_is_non_empty_and_stable(self) -> None:
        provider = LocalProvider(encoder=FakeSentenceTransformer())
        left = provider.embed("??????? ??????? ?????? ???? ??? ????????????")
        right = provider.embed("??????? ??????? ?????? ???? ??? ????????????")
        other = provider.embed("?????? ?????????????? ?????????? ?????? ???? ? ????? ?????????")

        self.assertTrue(left)
        self.assertEqual(len(left), 8)
        self.assertEqual(left, right)
        self.assertNotEqual(left, other)

    def test_dependencies_can_select_local_mode_via_legacy_model_mode(self) -> None:
        old_mode = os.environ.get("MODEL_MODE")
        try:
            os.environ["MODEL_MODE"] = "local"
            dependencies._chat_provider = None
            provider = get_llm_provider()
            self.assertIsInstance(provider, LocalProvider)
        finally:
            dependencies._chat_provider = None
            if old_mode is None:
                os.environ.pop("MODEL_MODE", None)
            else:
                os.environ["MODEL_MODE"] = old_mode

    def test_dependencies_can_split_chat_and_embedding_modes(self) -> None:
        old_chat = os.environ.get("CHAT_MODE")
        old_embed = os.environ.get("EMBED_MODE")
        old_key = os.environ.get("MISTRAL_API_KEY")
        try:
            os.environ["CHAT_MODE"] = "local"
            os.environ["EMBED_MODE"] = "local"
            dependencies._chat_provider = None
            dependencies._embedding_provider = None
            self.assertIsInstance(get_chat_provider(), LocalProvider)
            self.assertIsInstance(get_embedding_provider(), LocalProvider)
        finally:
            dependencies._chat_provider = None
            dependencies._embedding_provider = None
            if old_chat is None:
                os.environ.pop("CHAT_MODE", None)
            else:
                os.environ["CHAT_MODE"] = old_chat
            if old_embed is None:
                os.environ.pop("EMBED_MODE", None)
            else:
                os.environ["EMBED_MODE"] = old_embed
            if old_key is None:
                os.environ.pop("MISTRAL_API_KEY", None)
            else:
                os.environ["MISTRAL_API_KEY"] = old_key

    def test_local_pipeline_analyzes_document(self) -> None:
        StandardIngestor().ingest_pdf("gost_7_32_2017")
        pipeline = DocumentPipeline(
            llm_provider=LocalProvider(encoder=FakeSentenceTransformer()),
            embedding_provider=LocalProvider(encoder=FakeSentenceTransformer()),
            registry=StandardRegistry(),
        )
        document = DocumentInput.model_validate_json(
            Path("tests/fixtures/documents/demo_figure_caption.json").read_text(encoding="utf-8-sig")
        )

        result = pipeline.analyze_document(document)

        self.assertGreaterEqual(result.summary.total_issues, 2)
        self.assertIn("missing_figure_caption", [issue.subtype for issue in result.issues])


if __name__ == "__main__":
    unittest.main()
