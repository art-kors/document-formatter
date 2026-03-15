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
        standard_id = standard_name.lower().replace(" ", "_").replace(".", "_")
        self._standards[standard_id] = StandardDescriptor(
            standard_id=standard_id,
            title=standard_name,
        )
        return standard_id
