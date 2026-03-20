import os


DEFAULT_STORAGE_ROOT = os.path.join("app", "storage")
DEFAULT_GRAPHS_DIR = os.path.join(DEFAULT_STORAGE_ROOT, "graphs")
DEFAULT_STANDARDS_DIR = os.path.join(DEFAULT_STORAGE_ROOT, "standards")


def ensure_storage_dirs() -> None:
    os.makedirs(DEFAULT_STORAGE_ROOT, exist_ok=True)
    os.makedirs(DEFAULT_GRAPHS_DIR, exist_ok=True)
    os.makedirs(DEFAULT_STANDARDS_DIR, exist_ok=True)


def graph_path_for(standard_id: str) -> str:
    ensure_storage_dirs()
    return os.path.join(DEFAULT_GRAPHS_DIR, f"{standard_id}.json")


def standard_dir_for(standard_id: str) -> str:
    ensure_storage_dirs()
    path = os.path.join(DEFAULT_STANDARDS_DIR, standard_id)
    os.makedirs(path, exist_ok=True)
    return path


def standard_source_pdf_path_for(standard_id: str) -> str:
    return os.path.join(standard_dir_for(standard_id), "source.pdf")


def standard_raw_text_path_for(standard_id: str) -> str:
    return os.path.join(standard_dir_for(standard_id), "raw.txt")


def standard_cleaned_text_path_for(standard_id: str) -> str:
    return os.path.join(standard_dir_for(standard_id), "cleaned.txt")


def standard_parsed_path_for(standard_id: str) -> str:
    return os.path.join(standard_dir_for(standard_id), "parsed.json")
