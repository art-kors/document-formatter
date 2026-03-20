import hashlib
import re
import unicodedata
from typing import Dict, List

from app.schemas.standard import StandardDescriptor


class StandardRegistry:
    def __init__(self):
        self._standards: Dict[str, StandardDescriptor] = {
            "gost_7_32_2017": StandardDescriptor(
                standard_id="gost_7_32_2017",
                title="ГОСТ 7.32-2017",
            )
        }

    def list_standards(self) -> List[StandardDescriptor]:
        return list(self._standards.values())

    def get(self, standard_id: str) -> StandardDescriptor | None:
        return self._standards.get(standard_id)

    def register_uploaded_standard(self, standard_name: str) -> str:
        standard_id = self._build_standard_id(standard_name)
        self._standards[standard_id] = StandardDescriptor(
            standard_id=standard_id,
            title=standard_name,
        )
        return standard_id

    def _build_standard_id(self, standard_name: str) -> str:
        normalized = unicodedata.normalize("NFKD", standard_name)
        ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
        slug = re.sub(r"[^a-z0-9]+", "_", ascii_only).strip("_")
        if not slug:
            digest = hashlib.md5(standard_name.encode("utf-8")).hexdigest()[:10]
            slug = f"standard_{digest}"
        return slug
