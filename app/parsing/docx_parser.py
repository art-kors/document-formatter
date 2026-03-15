from pathlib import Path
from tempfile import NamedTemporaryFile


def extract_docx_text(file_bytes: bytes) -> str:
    try:
        from llama_index.readers.file import DocxReader

        with NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        reader = DocxReader()
        documents = reader.load_data(file=Path(tmp_path))
        Path(tmp_path).unlink()
        return "\n\n".join(doc.text for doc in documents).strip()
    except Exception as exc:
        raise ValueError(f"DOCX parsing failed: {exc}") from exc
