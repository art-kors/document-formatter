from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi import Body
from utilities import extract_text
from pipeline.pipeline import DocumentPipeline
from core.llm import MistralLLM
import os


app = FastAPI(
    title="Document Processing API",
    description="API with UI for document and instruction processing",
    version="1.0.0"
)

# Подключаем шаблоны
templates = Jinja2Templates(directory="templates")

# Глобальные переменные для хранения состояния пайплайна
# (В продакшене лучше использовать Database или Redis)
current_llm = None
current_pipeline = None


def get_llm():
    """Получение LLM клиента (Singleton)."""
    global current_llm
    if current_llm is None:
        # Убедитесь, что переменная окружения MISTRAL_API_KEY установлена
        current_llm = MistralLLM()
    return current_llm


@app.get("/", response_class=HTMLResponse)
async def get_ui(request: Request):
    """Отдает HTML интерфейс."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/generate")
async def generate(
        document: UploadFile = File(...),
        instruction: UploadFile = File(...)
):
    """
    Принимает документ и инструкцию, обрабатывает их,
    строит граф знаний и векторное хранилище.
    """
    global current_pipeline

    try:
        # 1. Извлечение текста из загруженных файлов
        doc_text = extract_text(document)
        instr_text = extract_text(instruction)

        # 2. Инициализация LLM и Пайплайна
        llm = get_llm()
        current_pipeline = DocumentPipeline(llm)

        # 3. Обработка инструкции (построение графа и индексация)
        # Этот шаг может занять время (зависит от длины текста и API Mistral)
        processing_result = current_pipeline.process_instruction(instr_text)

        # 4. Формирование ответа для фронтенда
        # Важно: структура JSON должна совпадать с ожиданиями в index.html

        # Если processing_result содержит статус и счетчики
        entities_count = processing_result.get('entities_count', 0) if processing_result else 0

        return JSONResponse(content={
            "status": "success",
            "message": "Инструкция обработана, база знаний построена",
            "document": {
                "name": document.filename,
                "char_count": len(doc_text),
                # Можно добавить preview, если нужно для других целей
            },
            "instruction": {
                "name": instruction.filename,
                "char_count": len(instr_text),
                "entities_count": entities_count  # Добавлено для отображения в UI
            },
            # Можно вернуть структуру, если фронтенд захочет её отрисовать
            "extracted_structure": current_pipeline.get_structure()
        })

    except ValueError as ve:
        # Ошибки валидации (например, неправильный API ключ или формат файла)
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        # Непредвиденные ошибки
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@app.post("/ask")
async def ask_question(question: str = Body(..., embed=True)):
    """
    Принимает JSON вида: { "question": "текст вопроса" }
    """
    global current_pipeline

    if not current_pipeline:
        raise HTTPException(status_code=400, detail="Сначала загрузите инструкцию через /generate")

    try:
        answer = current_pipeline.query(question)
        return answer
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download-graph")
async def download_graph():
    """Скачивание файла графа знаний"""
    file_path = "storage/knowledge_graph.json"
    if os.path.exists(file_path):
        return FileResponse(
            path=file_path,
            filename="knowledge_graph.json",
            media_type="application/json"
        )
    raise HTTPException(status_code=404, detail="Graph file not found. Process instruction first.")

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Ресурс не найден", "path": request.url.path}
    )