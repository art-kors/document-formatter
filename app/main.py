from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.routes_analysis import router as analysis_router
from app.api.routes_standards import router as standards_router
from app.api.dependencies import get_standard_registry, resolve_runtime_modes


app = FastAPI(
    title="Document Processing API",
    description="API with UI for document and instruction processing",
    version="1.0.0",
)

templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def get_ui(request: Request):
    standards = [item.model_dump() for item in get_standard_registry().list_standards()]
    chat_mode, embed_mode = resolve_runtime_modes()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "standards": standards,
            "chat_mode_default": chat_mode or "default",
            "embed_mode_default": embed_mode or "default",
        },
    )


app.include_router(analysis_router)
app.include_router(standards_router)
