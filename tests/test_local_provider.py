import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from app.api import dependencies
from app.api.dependencies import get_chat_provider, get_embedding_provider, get_llm_provider
from app.llm.local_chat_provider import LocalChatProvider
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


class _FakeHttpResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class LocalProviderTests(unittest.TestCase):
    def tearDown(self) -> None:
        dependencies._chat_provider = None
        dependencies._embedding_provider = None

    def test_embed_is_non_empty_and_stable(self) -> None:
        provider = LocalProvider(encoder=FakeSentenceTransformer())
        left = provider.embed("????????? ?????? ?????? ?????????? ?????????? ??????????")
        right = provider.embed("????????? ?????? ?????? ?????????? ?????????? ??????????")
        other = provider.embed("?????? ????? ?????? ???????? ?????? ??????")

        self.assertTrue(left)
        self.assertEqual(len(left), 8)
        self.assertEqual(left, right)
        self.assertNotEqual(left, other)

    def test_local_chat_provider_calls_ollama_endpoint(self) -> None:
        provider = LocalChatProvider(base_url="http://127.0.0.1:11434", model="qwen2.5:7b", temperature=0.1)

        with patch("app.llm.local_chat_provider.request.urlopen", return_value=_FakeHttpResponse({"response": "??????"})) as mocked:
            result = provider.chat("??????? ?????")

        self.assertEqual(result, "??????")
        request_obj = mocked.call_args.args[0]
        self.assertEqual(request_obj.full_url, "http://127.0.0.1:11434/api/generate")
        self.assertEqual(request_obj.get_method(), "POST")
        body = json.loads(request_obj.data.decode("utf-8"))
        self.assertEqual(body["model"], "qwen2.5:7b")
        self.assertEqual(body["prompt"], "??????? ?????")
        self.assertFalse(body["stream"])

    def test_dependencies_can_select_local_mode_via_legacy_model_mode(self) -> None:
        old_mode = os.environ.get("MODEL_MODE")
        old_chat = os.environ.get("CHAT_MODE")
        try:
            os.environ["MODEL_MODE"] = "local"
            os.environ.pop("CHAT_MODE", None)
            dependencies._chat_provider = None
            provider = get_llm_provider()
            self.assertIsInstance(provider, LocalChatProvider)
        finally:
            dependencies._chat_provider = None
            if old_mode is None:
                os.environ.pop("MODEL_MODE", None)
            else:
                os.environ["MODEL_MODE"] = old_mode
            if old_chat is None:
                os.environ.pop("CHAT_MODE", None)
            else:
                os.environ["CHAT_MODE"] = old_chat

    def test_dependencies_can_split_chat_and_embedding_modes(self) -> None:
        old_chat = os.environ.get("CHAT_MODE")
        old_embed = os.environ.get("EMBED_MODE")
        old_key = os.environ.get("MISTRAL_API_KEY")
        try:
            os.environ["CHAT_MODE"] = "local"
            os.environ["EMBED_MODE"] = "local"
            dependencies._chat_provider = None
            dependencies._embedding_provider = None
            self.assertIsInstance(get_chat_provider(), LocalChatProvider)
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
