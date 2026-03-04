from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(
    title="Document Processing API",
    description="API with UI for document and instruction processing",
    version="1.0.0"
)


# Serve the HTML UI at root path
@app.get("/", response_class=HTMLResponse)
async def get_ui():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Document Processor</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #e0f7e0;
                margin: 0;
                padding: 20px;
                display: flex;
                flex-direction: column;
                align-items: center;
                min-height: 100vh;
            }
            .container {
                max-width: 800px;
                width: 100%;
                background: white;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                padding: 30px;
                margin-top: 20px;
            }
            h1 {
                text-align: center;
                color: #2e7d32;
                margin-bottom: 30px;
            }
            .upload-section {
                display: flex;
                gap: 20px;
                margin-bottom: 30px;
                flex-wrap: wrap;
            }
            .upload-area {
                flex: 1;
                min-width: 250px;
                border: 2px dashed #b0bec5;
                border-radius: 8px;
                padding: 30px 20px;
                text-align: center;
                background-color: #f8f9fa;
                transition: all 0.3s;
            }
            .upload-area:hover {
                border-color: #4caf50;
                background-color: #e8f5e9;
            }
            .upload-area input {
                display: none;
            }
            .upload-area label {
                cursor: pointer;
                display: inline-block;
                padding: 10px 20px;
                background-color: #e0f7e0;
                border-radius: 5px;
                color: #2e7d32;
                font-weight: 500;
            }
            .upload-area label:hover {
                background-color: #c8e6c9;
            }
            .upload-icon {
                font-size: 48px;
                color: #66bb6a;
                margin-bottom: 15px;
            }
            .btn-generate {
                background-color: #616161;
                color: white;
                border: none;
                padding: 15px 40px;
                font-size: 18px;
                border-radius: 8px;
                cursor: pointer;
                width: 100%;
                max-width: 300px;
                margin: 0 auto;
                display: block;
                transition: background-color 0.3s;
            }
            .btn-generate:hover {
                background-color: #424242;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Обработка документов</h1>

            <form id="upload-form" action="/generate" method="post" enctype="multipart/form-data">
                <div class="upload-section">
                    <div class="upload-area">
                        <div class="upload-icon">📄</div>
                        <p>Загрузите документ</p>
                        <input type="file" id="document" name="document" accept=".pdf,.docx,.txt">
                        <label for="document">Выбрать файл</label>
                    </div>

                    <div class="upload-area">
                        <div class="upload-icon">📘</div>
                        <p>Загрузите инструкцию</p>
                        <input type="file" id="instruction" name="instruction" accept=".pdf,.docx,.txt">
                        <label for="instruction">Выбрать файл</label>
                    </div>
                </div>

                <button type="submit" class="btn-generate">Генерировать</button>
            </form>
        </div>

        <script>
            // Optional: Add client-side validation
            document.getElementById('upload-form').onsubmit = function() {
                const docFile = document.getElementById('document').files[0];
                const instrFile = document.getElementById('instruction').files[0];

                if (!docFile || !instrFile) {
                    alert('Пожалуйста, загрузите оба файла');
                    return false;
                }
                return true;
            };
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# Handle file processing
@app.post("/generate")
async def generate(
        document: UploadFile = File(...),
        instruction: UploadFile = File(...)
):
    # Here you would implement your actual processing logic
    try:
        # Example processing (in real app you'd do actual work here):
        doc_content = await document.read()
        instr_content = await instruction.read()

        # Just for demonstration - return file sizes
        return JSONResponse(
            content={
                "status": "success",
                "message": "Файлы успешно обработаны",
                "document": {
                    "name": document.filename,
                    "size": len(doc_content),
                    "type": document.content_type
                },
                "instruction": {
                    "name": instruction.filename,
                    "size": len(instr_content),
                    "type": instruction.content_type
                }
            },
            status_code=200
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки файлов: {str(e)}"
        )


# Keep your existing error handler
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Ресурс не найден", "path": request.url.path}
    )