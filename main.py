from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from utilities import *
app = FastAPI(
    title="Document Processing API",
    description="API with UI for document and instruction processing",
    version="1.0.0"
)

# Подключаем шаблоны
templates = Jinja2Templates(directory="templates")


# Serve the HTML UI at root path
@app.get("/", response_class=HTMLResponse)
async def get_ui(request: Request):

    return templates.TemplateResponse("index.html", {"request": request})


# Handle file processing
@app.post("/generate")
async def generate(
        document: UploadFile = File(...),
        instruction: UploadFile = File(...)
):
    try:
        # Используем функцию extract_text с LlamaIndex, которую мы обсуждали
        doc_text = extract_text(document)
        instr_text = extract_text(instruction)

        return JSONResponse(content={
            "status": "success",
            "message": "Файлы успешно обработаны",
            "document": {
                "name": document.filename,
                "char_count": len(doc_text),  # Важно для фронтенда
                "preview": doc_text[:100] + "..."
            },
            "instruction": {
                "name": instruction.filename,
                "char_count": len(instr_text),  # Важно для фронтенда
                "preview": instr_text[:100] + "..."
            },
        })
    except Exception as e:
        # Возвращаем ошибку в формате, который поймает JS
        raise HTTPException(status_code=500, detail=str(e))


# Keep your existing error handler
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Ресурс не найден", "path": request.url.path}
    )