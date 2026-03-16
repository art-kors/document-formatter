from pathlib import Path
from tempfile import NamedTemporaryFile


def extract_docx_text(file_bytes: bytes) -> str:
    tmp_path = None
    try:
        import docx2txt

        with NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        return docx2txt.process(tmp_path).strip()
    except Exception as exc:
        raise ValueError(f"DOCX parsing failed: {exc}") from exc
    finally:
        if tmp_path and Path(tmp_path).exists():
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass
