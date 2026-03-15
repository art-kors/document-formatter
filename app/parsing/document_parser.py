from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import UploadFile

from app.parsing.docx_parser import extract_docx_text
from app.parsing.md_parser import extract_md_text

try:
    import fitz
except ImportError:
    fitz = None

try:
    from llama_index.readers.file import FlatReader, PDFReader
except ImportError:
    FlatReader = None
    PDFReader = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


def extract_text_from_pdf(file_bytes: bytes) -> str:
    tmp_path = None
    try:
        with NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        if fitz is not None:
            with fitz.open(tmp_path) as pdf:
                text = "\n\n".join(page.get_text() for page in pdf).strip()
        elif PDFReader is not None:
            reader = PDFReader()
            documents = reader.load_data(file=Path(tmp_path))
            text = "\n\n".join(doc.text for doc in documents).strip()
        elif PdfReader is not None:
            reader = PdfReader(tmp_path)
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
        else:
            raise ValueError("No PDF parser is installed")

        return text
    except Exception as exc:
        raise ValueError(f"PDF parsing failed: {exc}") from exc
    finally:
        if tmp_path and Path(tmp_path).exists():
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass


def extract_text_from_docx(file_bytes: bytes) -> str:
    return extract_docx_text(file_bytes)


def extract_text_from_txt(file_bytes: bytes, content_type: str | None = None) -> str:
    tmp_path = None
    try:
        if FlatReader is not None:
            with NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            reader = FlatReader()
            documents = reader.load_data(file=Path(tmp_path))
            return "\n\n".join(doc.text for doc in documents).strip()

        return file_bytes.decode("utf-8").strip()
    except Exception as exc:
        raise ValueError(f"TXT parsing failed: {exc}") from exc
    finally:
        if tmp_path and Path(tmp_path).exists():
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass


def extract_text(file: UploadFile) -> str:
    filename = file.filename or ""
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    content = file.file.read()

    if ext == "pdf" or file.content_type == "application/pdf":
        return extract_text_from_pdf(content)
    if ext in ("docx", "doc") or "wordprocessingml" in (file.content_type or ""):
        return extract_text_from_docx(content)
    if ext == "txt" or file.content_type == "text/plain":
        return extract_text_from_txt(content, file.content_type)
    if ext == "md" or file.content_type in {"text/markdown", "text/x-markdown"}:
        return extract_md_text(content)
    raise ValueError(f"Unsupported file type: {ext or file.content_type}")
