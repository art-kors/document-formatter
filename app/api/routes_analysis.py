from time import perf_counter, process_time
import json
import os
from urllib.parse import quote

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from app.analytics.analysis_logger import write_analysis_log
from app.api.dependencies import build_pipeline, get_pipeline, resolve_runtime_modes
from app.fixing.docx_editor import apply_fixes_to_source_docx
from app.fixing.document_fixer import apply_fixes, build_corrected_docx
from app.parsing.document_parser import extract_text, extract_text_from_docx, extract_text_from_pdf, extract_text_from_txt
from app.parsing.document_to_schema import parse_docx_to_document, parse_text_to_document
from app.schemas.document import DocumentInput
from app.schemas.fix_document import FixDocumentRequest
from app.schemas.issue import Issue


router = APIRouter(tags=["analysis"])


@router.post("/generate")
async def generate(
    document: UploadFile = File(...),
    instruction: UploadFile = File(...),
):
    try:
        pipeline = get_pipeline()
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
    try:
        pipeline = get_pipeline()
        return pipeline.query(question)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/analyze")
async def analyze_document(document: DocumentInput):
    try:
        pipeline = get_pipeline()
        return pipeline.analyze_document(document)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/analyze-file")
async def analyze_uploaded_file(
    document: UploadFile = File(...),
    standard_id: str = Form(...),
    document_id: str | None = Form(default=None),
    include_parsed_document: bool = Form(default=False),
    chat_mode: str | None = Form(default=None),
    embed_mode: str | None = Form(default=None),
):
    request_started = perf_counter()
    cpu_started = process_time()
    try:
        resolved_chat_mode, resolved_embed_mode = resolve_runtime_modes(chat_mode, embed_mode)
        pipeline = build_pipeline(chat_mode=chat_mode, embed_mode=embed_mode)
        filename = document.filename or 'uploaded_document'
        content = await document.read()
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        content_type = document.content_type or ''

        parse_started = perf_counter()
        if ext in {'docx', 'doc'} or 'wordprocessingml' in content_type:
            try:
                parsed_document = parse_docx_to_document(
                    content,
                    filename=filename,
                    standard_id=standard_id,
                    document_id=document_id,
                )
            except Exception as exc:
                parsed_document = parse_text_to_document(
                    extract_text_from_docx(content),
                    filename=filename,
                    standard_id=standard_id,
                    document_id=document_id,
                )
                parsed_document.meta.extras['source_format'] = 'docx_fallback'
                parsed_document.meta.extras['docx_parser_error'] = str(exc)
        elif ext == 'pdf' or content_type == 'application/pdf':
            parsed_document = parse_text_to_document(
                extract_text_from_pdf(content),
                filename=filename,
                standard_id=standard_id,
                document_id=document_id,
            )
        elif ext == 'txt' or content_type == 'text/plain':
            parsed_document = parse_text_to_document(
                extract_text_from_txt(content, content_type),
                filename=filename,
                standard_id=standard_id,
                document_id=document_id,
            )
        elif ext == 'md' or content_type in {'text/markdown', 'text/x-markdown'}:
            parsed_document = parse_text_to_document(
                content.decode('utf-8'),
                filename=filename,
                standard_id=standard_id,
                document_id=document_id,
            )
        else:
            document.file.seek(0)
            parsed_document = parse_text_to_document(
                extract_text(document),
                filename=filename,
                standard_id=standard_id,
                document_id=document_id,
            )

        parsing_time_ms = int((perf_counter() - parse_started) * 1000)
        result = pipeline.analyze_document(parsed_document)
        runtime_modes = {
            'chat_mode': resolved_chat_mode or 'default',
            'embed_mode': resolved_embed_mode or 'default',
        }
        request_wall_time_ms = int((perf_counter() - request_started) * 1000)
        request_cpu_time_ms = int((process_time() - cpu_started) * 1000)
        analytics_log_path = write_analysis_log(
            document=parsed_document,
            result=result,
            runtime_modes=runtime_modes,
            source_format=parsed_document.meta.extras.get('source_format', ext or 'unknown'),
            file_size_bytes=len(content),
            parsing_time_ms=parsing_time_ms,
            request_wall_time_ms=request_wall_time_ms,
            request_cpu_time_ms=request_cpu_time_ms,
        )
        if include_parsed_document:
            payload = result.model_dump()
            payload["parsed_document"] = parsed_document.model_dump()
            payload["runtime_modes"] = runtime_modes
            payload["analytics_log_path"] = analytics_log_path
            return JSONResponse(content=payload)
        payload = result.model_dump()
        payload["runtime_modes"] = runtime_modes
        payload["analytics_log_path"] = analytics_log_path
        return JSONResponse(content=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/apply-fixes-file")
async def apply_fixes_file(
    document: UploadFile = File(...),
    parsed_document_json: str = Form(...),
    issues_json: str = Form(...),
    output_filename: str | None = Form(default=None),
):
    try:
        file_bytes = await document.read()
        parsed_document = DocumentInput.model_validate_json(parsed_document_json)
        issues_payload = json.loads(issues_json)
        issues = [Issue.model_validate(item) for item in issues_payload]
        content = apply_fixes_to_source_docx(file_bytes, parsed_document, issues)
        filename = output_filename or f"{parsed_document.document_id}_fixed.docx"
        if not filename.lower().endswith('.docx'):
            filename = f"{filename}.docx"
        headers = _attachment_headers(filename)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/fix-document")
async def fix_document(request: FixDocumentRequest):
    try:
        corrected_document = apply_fixes(request.document, request.issues)
        content = build_corrected_docx(corrected_document)
        filename = request.output_filename or "corrected_document.docx"
        if not filename.lower().endswith(".docx"):
            filename = f"{filename}.docx"
        headers = _attachment_headers(filename)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _attachment_headers(filename: str) -> dict[str, str]:
    safe_ascii = ''.join(ch if ord(ch) < 128 else '_' for ch in filename)
    quoted = quote(filename.encode('utf-8'))
    return {
        'Content-Disposition': f"attachment; filename=\"{safe_ascii}\"; filename*=UTF-8''{quoted}",
    }


@router.get("/download-graph")
async def download_graph():
    try:
        pipeline = get_pipeline()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    file_path = pipeline.get_graph_path()
    if file_path and os.path.exists(file_path):
        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type="application/json",
        )
    raise HTTPException(status_code=404, detail="Graph file not found")

