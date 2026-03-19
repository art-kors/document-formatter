import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Dict, List

from app.schemas.standard import StandardDescriptor
from app.standards.storage import DEFAULT_STANDARDS_DIR


class StandardRegistry:
    def __init__(self):
        self._standards: Dict[str, StandardDescriptor] = {
            "gost_7_32_2017": StandardDescriptor(
                standard_id="gost_7_32_2017",
                title="ГОСТ 7.32-2017",
                source_path=self._detect_source_path("gost_7_32_2017"),
            )
        }
        self._discover_storage_standards()

    def list_standards(self) -> List[StandardDescriptor]:
        return list(self._standards.values())

    def get(self, standard_id: str) -> StandardDescriptor | None:
        return self._standards.get(standard_id)

    def register_uploaded_standard(self, standard_name: str) -> str:
        standard_id = self._build_standard_id(standard_name)
        self._standards[standard_id] = StandardDescriptor(
            standard_id=standard_id,
            title=standard_name,
            source_path=self._detect_source_path(standard_id),
        )
        return standard_id

    def _discover_storage_standards(self) -> None:
        standards_root = Path(DEFAULT_STANDARDS_DIR)
        if not standards_root.exists():
            return

        for standard_dir in sorted(path for path in standards_root.iterdir() if path.is_dir()):
            standard_id = standard_dir.name
            if standard_id in self._standards:
                descriptor = self._standards[standard_id]
                descriptor.source_path = descriptor.source_path or self._detect_source_path(standard_id)
                continue
            self._standards[standard_id] = StandardDescriptor(
                standard_id=standard_id,
                title=self._title_from_standard_id(standard_id),
                source_path=self._detect_source_path(standard_id),
            )

    def _detect_source_path(self, standard_id: str) -> str:
        standard_dir = Path(DEFAULT_STANDARDS_DIR) / standard_id
        if not standard_dir.exists():
            return ""
        preferred = standard_dir / "source.pdf"
        if preferred.exists():
            return str(preferred)
        candidates = sorted(standard_dir.glob("*.pdf"))
        return str(candidates[0]) if candidates else ""

    def _title_from_standard_id(self, standard_id: str) -> str:
        match = re.fullmatch(r"gost_(\d+)_(\d+)_(\d{4})", standard_id)
        if match:
            return f"ГОСТ {match.group(1)}.{match.group(2)}-{match.group(3)}"
        pretty = standard_id.replace("_", " ").strip()
        return pretty.upper() if pretty else standard_id

    def _build_standard_id(self, standard_name: str) -> str:
        normalized = unicodedata.normalize("NFKD", standard_name)
        ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
        slug = re.sub(r"[^a-z0-9]+", "_", ascii_only).strip("_")
        if not slug:
            digest = hashlib.md5(standard_name.encode("utf-8")).hexdigest()[:10]
            slug = f"standard_{digest}"
        return slug
