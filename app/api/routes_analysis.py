import os

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.api.dependencies import get_pipeline
from app.parsing.document_parser import extract_text
from app.schemas.document import DocumentInput


router = APIRouter(tags=["analysis"])


@router.post("/generate")
async def generate(
    document: UploadFile = File(...),
    instruction: UploadFile = File(...),
):
    pipeline = get_pipeline()

    try:
        doc_text = extract_text(document)
        instr_text = extract_text(instruction)
        processing_result = pipeline.process_instruction(
            standard_text=instr_text,
            standard_name=instruction.filename or "uploaded_instruction",
        )

        return JSONResponse(
            content={
                "status": "success",
                "message": "Instruction processed and knowledge base is ready",
                "document": {
                    "name": document.filename,
                    "char_count": len(doc_text),
                },
                "instruction": {
                    "name": instruction.filename,
                    "char_count": len(instr_text),
                    "entities_count": processing_result.get("entities_count", 0),
                },
                "processing_details": processing_result,
                "extracted_structure": pipeline.get_structure(),
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/ask")
async def ask_question(question: str = Body(..., embed=True)):
    pipeline = get_pipeline()
    try:
        return pipeline.query(question)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/analyze")
async def analyze_document(document: DocumentInput):
    pipeline = get_pipeline()
    try:
        return pipeline.analyze_document(document)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/download-graph")
async def download_graph():
    pipeline = get_pipeline()
    file_path = pipeline.get_graph_path()
    if file_path and os.path.exists(file_path):
        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type="application/json",
        )
    raise HTTPException(status_code=404, detail="Graph file not found")
