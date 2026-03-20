def extract_md_text(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError(f"MD parsing failed: {exc}") from exc
