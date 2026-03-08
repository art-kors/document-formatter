from pathlib import Path

from fastapi import UploadFile
from llama_index.readers.file import PDFReader, DocxReader, FlatReader

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF using LlamaIndex PDFReader."""
    try:
        # PDFReader expects a file path, so we use a temporary BytesIO approach
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        reader = PDFReader()
        documents = reader.load_data(file=Path(tmp_path))

        # Cleanup temp file
        Path(tmp_path).unlink()

        # Combine all pages
        text = "\n\n".join(doc.text for doc in documents)
        return text.strip()
    except Exception as e:
        raise ValueError(f"PDF parsing failed: {str(e)}")


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from DOCX using LlamaIndex DocxReader."""
    try:
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        reader = DocxReader()
        documents = reader.load_data(file=Path(tmp_path))

        Path(tmp_path).unlink()

        text = "\n\n".join(doc.text for doc in documents)
        return text.strip()
    except Exception as e:
        raise ValueError(f"DOCX parsing failed: {str(e)}")


def extract_text_from_txt(file_bytes: bytes, content_type: str = None) -> str:
    """Extract text from TXT using LlamaIndex FlatReader."""
    try:
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        reader = FlatReader()
        documents = reader.load_data(file=Path(tmp_path))

        Path(tmp_path).unlink()

        text = "\n\n".join(doc.text for doc in documents)
        return text.strip()
    except Exception as e:
        raise ValueError(f"TXT parsing failed: {str(e)}")


def extract_text(file: UploadFile) -> str:
    """Unified extractor: route by file extension or MIME type."""
    filename = file.filename or ""
    ext = filename.lower().split(".")[-1] if "." in filename else ""

    # Read entire content into memory
    content = file.file.read()

    if ext == "pdf" or file.content_type == "application/pdf":
        return extract_text_from_pdf(content)
    elif ext in ("docx", "doc") or "wordprocessingml" in (file.content_type or ""):
        return extract_text_from_docx(content)
    elif ext == "txt" or file.content_type == "text/plain":
        return extract_text_from_txt(content, file.content_type)
    else:
        raise ValueError(f"Unsupported file type: {ext or file.content_type}")


def extract_text(file: UploadFile) -> str:
    """Unified extractor: route by file extension or MIME type."""
    filename = file.filename or ""
    ext = filename.lower().split(".")[-1] if "." in filename else ""

    # Read entire content into memory (OK for docs < 50MB)
    content = file.file.read()

    if ext == "pdf" or file.content_type == "application/pdf":
        return extract_text_from_pdf(content)
    elif ext in ("docx", "doc") or "wordprocessingml" in (file.content_type or ""):
        return extract_text_from_docx(content)
    elif ext == "txt" or file.content_type == "text/plain":
        return extract_text_from_txt(content, file.content_type)
    else:
        raise ValueError(f"Unsupported file type: {ext or file.content_type}")