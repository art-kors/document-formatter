from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(
    title="Simple API",
    description="Minimal FastAPI server example",
    version="1.0.0"
)

@app.get("/")
async def root():
    return {"message": "Hello from FastAPI!", "status": "healthy"}

@app.get("/items/{item_id}")
async def get_item(item_id: int):
    return {"item_id": item_id, "name": f"Item {item_id}"}

# Error handler example (optional but recommended)
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Resource not found", "path": request.url.path}
    )