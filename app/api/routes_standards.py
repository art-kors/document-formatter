from fastapi import APIRouter

from app.api.dependencies import get_standard_registry


router = APIRouter(prefix="/standards", tags=["standards"])


@router.get("")
async def list_standards():
    registry = get_standard_registry()
    return {"standards": [item.model_dump() for item in registry.list_standards()]}
