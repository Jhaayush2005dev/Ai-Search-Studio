import os
import json
import shutil
import logging
import base64
import time
from pathlib import Path
from threading import Lock
from typing import Optional, List, Dict, Any, Generator

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.config import (
    DOCS_DIR, CHROMA_DIR, MISTRAL_API_KEY, AVAILABLE_MODELS, DEFAULT_MODEL,
    SUPPORTED_EXTENSIONS, THEMES, is_internet_available
)
from core.doc_loader import UniversalDocumentLoader
from core.rag_engine import RAGEngine
from core.session_manager import SessionManager
from core.vision_service import VisionService
from core.web_service import WebService

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Search Studio", version="2.0.0")

# Mount static folder
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Shared singletons
_doc_loader = UniversalDocumentLoader()
_engine = RAGEngine(api_key=MISTRAL_API_KEY)
_session_manager = SessionManager()
_vision_service = VisionService(api_key=MISTRAL_API_KEY)
_web_service = WebService(max_results=4)
_engine_lock = Lock()


@app.on_event("startup")
def startup_init_documents():
    """Ingests any existing files in documents loaders/ folder into Chroma vector store."""
    try:
        doc_files = [str(f) for f in DOCS_DIR.iterdir() if f.is_file()]
        if doc_files:
            with _engine_lock:
                chunks, meta, errors = _doc_loader.process_and_chunk(doc_files)
                if chunks:
                    _engine.add_documents(chunks, meta)
                    logger.info(f"Startup: Indexed {len(meta)} files with {len(chunks)} chunks.")
        else:
            with _engine_lock:
                _engine.init_vector_store()
    except Exception as exc:
        logger.warning(f"Startup doc loading notice: {exc}")


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=5000)
    mode: Optional[str] = "Auto (Hybrid)"
    model: Optional[str] = DEFAULT_MODEL
    temperature: Optional[float] = 0.3
    depth: Optional[int] = 4
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[str]
    status: str = "ok"


class SettingsRequest(BaseModel):
    mode: Optional[str] = None
    model: Optional[str] = None
    depth: Optional[int] = None
    temperature: Optional[float] = None


class ImageSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


# ==========================================
# PWA & ASSET ROUTES
# ==========================================
@app.get("/manifest.json")
def get_manifest():
    manifest_file = STATIC_DIR / "manifest.json"
    if manifest_file.exists():
        return FileResponse(str(manifest_file), media_type="application/manifest+json")
    raise HTTPException(status_code=404, detail="Manifest not found")


@app.get("/sw.js")
def get_sw():
    sw_file = STATIC_DIR / "sw.js"
    if sw_file.exists():
        return FileResponse(str(sw_file), media_type="application/javascript")
    raise HTTPException(status_code=404, detail="Service Worker not found")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": "Search Studio", "version": "2.0.0"}


# ==========================================
# CONFIG & SETTINGS ENDPOINTS
# ==========================================
@app.get("/api/config")
def get_config():
    with _engine_lock:
        has_key = bool(_engine.api_key or os.getenv("MISTRAL_API_KEY"))
        stats = _engine.get_knowledge_stats()
        return {
            "has_api_key": has_key,
            "current_model": _engine.model_name,
            "available_models": AVAILABLE_MODELS,
            "current_mode": _engine.search_mode,
            "available_modes": ["Auto (Hybrid)", "Docs Only", "Web Only"],
            "current_depth": _engine.context_depth,
            "knowledge_stats": stats,
            "supported_extensions": list(SUPPORTED_EXTENSIONS.keys()),
            "themes": list(THEMES.keys())
        }


@app.post("/api/settings")
def update_settings(req: SettingsRequest):
    with _engine_lock:
        if req.model:
            _engine.set_model(req.model)
        if req.mode:
            _engine.set_search_mode(req.mode)
        if req.depth is not None:
            _engine.set_context_depth(req.depth)
        if req.temperature is not None:
            _engine.set_temperature(req.temperature)
        return {
            "status": "ok",
            "model": _engine.model_name,
            "mode": _engine.search_mode,
            "depth": _engine.context_depth,
            "temperature": _engine.temperature
        }


# ==========================================
# DOCUMENT MANAGEMENT ENDPOINTS
# ==========================================
@app.get("/api/documents")
def list_documents():
    with _engine_lock:
        return _engine.get_knowledge_stats()


@app.post("/api/upload")
async def upload_documents(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    saved_paths: List[str] = []
    try:
        for file in files:
            safe_name = Path(file.filename).name
            target_path = DOCS_DIR / safe_name
            with open(target_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_paths.append(str(target_path))

        with _engine_lock:
            chunks, meta, errors = _doc_loader.process_and_chunk(saved_paths)
            if chunks:
                _engine.add_documents(chunks, meta)
            stats = _engine.get_knowledge_stats()

        return {
            "status": "success",
            "files_indexed": len(meta),
            "chunks_created": len(chunks),
            "errors": errors,
            "knowledge_stats": stats
        }
    except Exception as exc:
        logger.error(f"File upload error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload processing failed: {str(exc)}") from exc


@app.delete("/api/documents/{filename}")
def delete_document(filename: str):
    with _engine_lock:
        success = _engine.delete_source(filename)
        target_file = DOCS_DIR / filename
        if target_file.exists():
            try:
                target_file.unlink()
            except Exception:
                pass
        stats = _engine.get_knowledge_stats()
        return {"status": "success" if success else "failed", "filename": filename, "knowledge_stats": stats}


@app.delete("/api/documents")
def clear_all_documents():
    with _engine_lock:
        success = _engine.clear_knowledge_base()
        for item in DOCS_DIR.iterdir():
            if item.is_file():
                try:
                    item.unlink()
                except Exception:
                    pass
        stats = _engine.get_knowledge_stats()
        return {"status": "success" if success else "failed", "knowledge_stats": stats}


# ==========================================
# CHAT & STREAMING ENDPOINTS
# ==========================================
@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    current_key = _engine.api_key or os.getenv("MISTRAL_API_KEY", "")
    if not current_key:
        raise HTTPException(status_code=500, detail="MISTRAL_API_KEY environment variable is not configured.")

    with _engine_lock:
        if not _engine.api_key:
            _engine.api_key = current_key
            _engine._init_models()

        if request.model and request.model != _engine.model_name:
            _engine.set_model(request.model)
        if request.mode:
            _engine.set_search_mode(request.mode)
        if request.depth is not None:
            _engine.set_context_depth(request.depth)
        if request.temperature is not None:
            _engine.set_temperature(request.temperature)

        answer_parts: list[str] = []
        citations: list[str] = []

        try:
            answer = _engine.stream_query(
                request.query.strip(),
                token_callback=answer_parts.append,
                source_callback=lambda values: citations.extend(values),
            )
        except Exception as exc:
            logger.error(f"Chat generation error: {exc}", exc_info=True)
            raise HTTPException(status_code=502, detail=f"AI service error: {str(exc)}") from exc

    return ChatResponse(
        answer=answer or "".join(answer_parts),
        citations=list(dict.fromkeys(citations))
    )


@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest):
    current_key = _engine.api_key or os.getenv("MISTRAL_API_KEY", "")
    if not current_key:
        raise HTTPException(status_code=500, detail="MISTRAL_API_KEY environment variable is not configured.")

    def event_stream():
        citations: list[str] = []
        status_updates: list[str] = []

        def on_token(t: str):
            yield f"data: {json.dumps({'token': t})}\n\n"

        def on_status(s: str):
            yield f"data: {json.dumps({'status': s})}\n\n"

        # Apply settings
        with _engine_lock:
            if not _engine.api_key:
                _engine.api_key = current_key
                _engine._init_models()
            if request.model:
                _engine.set_model(request.model)
            if request.mode:
                _engine.set_search_mode(request.mode)
            if request.depth is not None:
                _engine.set_context_depth(request.depth)
            if request.temperature is not None:
                _engine.set_temperature(request.temperature)

            token_queue: list[str] = []

            def sync_token(tok):
                token_queue.append(tok)

            def sync_source(srcs):
                citations.extend(srcs)

            try:
                full_text = _engine.stream_query(
                    request.query.strip(),
                    token_callback=sync_token,
                    source_callback=sync_source,
                )
                for tok in token_queue:
                    yield f"data: {json.dumps({'token': tok})}\n\n"

                clean_citations = list(dict.fromkeys(citations))
                yield f"data: {json.dumps({'citations': clean_citations})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ==========================================
# MULTIMODAL IMAGE ANALYSIS ENDPOINT
# ==========================================
@app.post("/api/analyze-image")
async def analyze_image(
    file: UploadFile = File(...),
    prompt: Optional[str] = Form("Please analyze this image, solve any question contained within it, and explain key takeaways.")
):
    try:
        import asyncio
        contents = await file.read()
        filename = file.filename or "image.jpg"

        current_key = _vision_service.api_key or os.getenv("MISTRAL_API_KEY", "")
        if not current_key:
            raise HTTPException(status_code=500, detail="MISTRAL_API_KEY is not configured for image analysis.")

        _vision_service.api_key = current_key

        # Optional RAG context if user supplied a specific query alongside the image
        search_context = ""
        clean_p = (prompt or "").strip()
        default_prompts = [
            "analyze and describe this photo in detail.",
            "answer and explain this photo in detail.",
            "analyze this photo",
            "describe this photo",
            "describe this image",
            "please analyze this image, solve any question contained within it, and explain key takeaways.",
            "analyze this image in detail."
        ]
        if clean_p and clean_p.lower() not in [p.lower() for p in default_prompts]:
            try:
                retrieved_text, _ = _engine.retrieve_context_for_query(clean_p)
                if retrieved_text:
                    search_context = retrieved_text
            except Exception as e:
                logger.warning(f"RAG context retrieval for image query skipped: {e}")

        answer_parts = []
        await asyncio.to_thread(
            _vision_service.analyze_image_stream,
            image_input=contents,
            prompt=prompt or "Analyze this image in detail.",
            token_callback=answer_parts.append,
            search_context=search_context
        )
        return {"answer": "".join(answer_parts), "filename": filename}
    except Exception as exc:
        logger.error(f"Image analysis error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ==========================================
# WEB IMAGE SEARCH ENDPOINT
# ==========================================
@app.post("/api/search-image")
def search_image_endpoint(req: ImageSearchRequest):
    try:
        clean_q = req.query.strip()
        img, url, err = _web_service.fetch_web_image(clean_q)
        if url:
            return {"image_url": url, "query": clean_q, "error": None}
        elif img:
            from io import BytesIO
            buf = BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            return {"image_url": f"data:image/png;base64,{b64}", "query": clean_q, "error": None}
        else:
            return {"image_url": None, "query": clean_q, "error": err or "No suitable image found."}
    except Exception as exc:
        logger.error(f"Image search endpoint error: {exc}", exc_info=True)
        return {"image_url": None, "query": req.query, "error": str(exc)}


# ==========================================
# SESSION MANAGEMENT ENDPOINTS
# ==========================================
@app.get("/api/sessions")
def get_sessions(q: Optional[str] = None):
    return _session_manager.list_sessions(search_query=q)


@app.get("/api/sessions/{session_id}")
def get_single_session(session_id: str):
    sess = _session_manager.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess


@app.post("/api/sessions")
def save_chat_session(data: Dict[str, Any]):
    sess_id = data.get("id") or _session_manager.create_session()["id"]
    saved = _session_manager.save_session(
        session_id=sess_id,
        messages=data.get("messages", []),
        title=data.get("title")
    )
    return saved or {"id": sess_id}


@app.delete("/api/sessions/{session_id}")
def delete_single_session(session_id: str):
    success = _session_manager.delete_session(session_id)
    return {"status": "success" if success else "failed"}


@app.delete("/api/sessions")
def clear_all_sessions_endpoint():
    success = _session_manager.clear_all_sessions()
    return {"status": "success" if success else "failed"}


# ==========================================
# MAIN RESPONSIVE WEB APPLICATION UI
# ==========================================
@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return HTML_PAGE


HTML_PAGE = r"""<!doctype html>
<html lang="en" data-theme="Developer Dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Search Studio v2.0</title>
  <meta name="description" content="Search Studio - Multi-Modal RAG Knowledge Engine & Web Intelligence">

  <!-- PWA & Mobile Meta -->
  <link rel="manifest" href="/manifest.json">
  <meta name="theme-color" content="#131316">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="Search Studio">
  <link rel="icon" type="image/png" href="/static/icon-192.png">
  <link rel="apple-touch-icon" href="/static/icon-192.png">

  <!-- Markdown & Code Highlight -->
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>

  <style>
    /* ========================================================
       THEMES DEFINITION (Developer Dark, Obsidian, Nordic, Light)
       ======================================================== */
    :root, [data-theme="Developer Dark"] {
      --bg-base: #131316;
      --bg-sidebar: #18181c;
      --bg-card-ai: #1c1c22;
      --bg-card-user: #23232b;
      --bg-input: #19191e;
      --bg-code: #101014;
      --accent-primary: #6366f1;
      --accent-hover: #4f46e5;
      --accent-success: #10b981;
      --accent-warning: #f59e0b;
      --accent-danger: #ef4444;
      --text-primary: #e4e4e7;
      --text-secondary: #a1a1aa;
      --text-muted: #71717a;
      --border-color: #272732;
      --chip-bg: #1e1e26;
      --chip-hover: #292934;
      --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    [data-theme="Obsidian Slate"] {
      --bg-base: #0f1115;
      --bg-sidebar: #14171d;
      --bg-card-ai: #181c23;
      --bg-card-user: #202630;
      --bg-input: #14171d;
      --bg-code: #0b0d10;
      --accent-primary: #38bdf8;
      --accent-hover: #0ea5e9;
      --accent-success: #34d399;
      --accent-warning: #fbbf24;
      --accent-danger: #f87171;
      --text-primary: #e2e8f0;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      --border-color: #232934;
      --chip-bg: #1c212a;
      --chip-hover: #262c38;
    }

    [data-theme="Nordic Dark"] {
      --bg-base: #1a1c23;
      --bg-sidebar: #20232c;
      --bg-card-ai: #252834;
      --bg-card-user: #2d3140;
      --bg-input: #20232c;
      --bg-code: #16171d;
      --accent-primary: #818cf8;
      --accent-hover: #6366f1;
      --accent-success: #86efac;
      --accent-warning: #fde047;
      --accent-danger: #fca5a5;
      --text-primary: #f1f5f9;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      --border-color: #2f3444;
      --chip-bg: #282c3b;
      --chip-hover: #34394c;
    }

    [data-theme="Developer Light"] {
      --bg-base: #f4f4f5;
      --bg-sidebar: #fafafa;
      --bg-card-ai: #ffffff;
      --bg-card-user: #ececee;
      --bg-input: #ffffff;
      --bg-code: #e4e4e7;
      --accent-primary: #4f46e5;
      --accent-hover: #4338ca;
      --accent-success: #059669;
      --accent-warning: #d97706;
      --accent-danger: #dc2626;
      --text-primary: #18181b;
      --text-secondary: #52525b;
      --text-muted: #71717a;
      --border-color: #e4e4e7;
      --chip-bg: #e4e4e7;
      --chip-hover: #d4d4d8;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }

    body {
      background-color: var(--bg-base);
      color: var(--text-primary);
      font-family: var(--font-family);
      min-height: 100vh;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    /* Scrollbars */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

    /* App Layout */
    #app-container {
      display: flex;
      flex: 1;
      height: 100vh;
      overflow: hidden;
      position: relative;
    }

    /* ========================================================
       SIDEBAR STYLING
       ======================================================== */
    #sidebar {
      width: 280px;
      min-width: 280px;
      background: var(--bg-sidebar);
      border-right: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      transition: transform 0.25s ease;
      z-index: 100;
      overflow-y: auto;
    }

    .sidebar-inner {
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      height: 100%;
    }

    /* Upload & Stats Row */
    .sidebar-btn-row {
      display: flex;
      gap: 8px;
      align-items: center;
    }

    .btn-upload {
      flex: 1;
      height: 34px;
      background: var(--accent-primary);
      color: #ffffff;
      border: none;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 700;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      cursor: pointer;
      transition: background 0.15s;
    }
    .btn-upload:hover { background: var(--accent-hover); }

    .btn-stats {
      width: 34px;
      height: 34px;
      background: var(--chip-bg);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      color: var(--text-secondary);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      font-size: 14px;
      transition: background 0.15s, color 0.15s;
    }
    .btn-stats:hover { background: var(--chip-hover); color: var(--text-primary); }

    /* Uploaded Files Section Header */
    .section-header-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 4px;
    }
    .section-title {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: var(--text-muted);
    }
    .section-count-badge {
      font-size: 10px;
      color: var(--text-muted);
    }

    /* Uploaded Files List */
    .sources-scroll-box {
      background: var(--bg-base);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 6px;
      min-height: 140px;
      max-height: 180px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .source-card {
      background: var(--bg-card-ai);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 6px 10px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11px;
      transition: border-color 0.15s;
    }
    .source-card:hover { border-color: var(--accent-primary); }

    .source-left {
      display: flex;
      align-items: center;
      gap: 8px;
      overflow: hidden;
      min-width: 0;
    }
    .source-icon { font-size: 14px; flex-shrink: 0; }
    .source-name {
      font-weight: 600;
      color: var(--text-primary);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 11px;
    }
    .source-meta {
      font-size: 10px;
      color: var(--text-muted);
      margin-top: 1px;
    }

    .source-del-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      padding: 2px 6px;
      font-size: 12px;
      border-radius: 4px;
      transition: color 0.15s;
    }
    .source-del-btn:hover { color: var(--accent-danger); }

    .sources-empty {
      font-size: 11px;
      color: var(--text-muted);
      font-style: italic;
      text-align: center;
      padding: 35px 10px;
    }

    /* Sidebar Dropdowns and Sliders */
    .control-group {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .control-label {
      font-size: 10px;
      font-weight: 700;
      color: var(--text-muted);
    }
    .control-header-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .depth-val-indicator {
      font-size: 10px;
      font-weight: 700;
      color: var(--accent-primary);
    }

    .select-menu {
      width: 100%;
      height: 30px;
      background: var(--chip-bg);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      color: var(--text-primary);
      font-size: 11px;
      padding: 0 8px;
      outline: none;
      cursor: pointer;
    }
    .select-menu:focus { border-color: var(--accent-primary); }

    .range-slider {
      width: 100%;
      accent-color: var(--accent-primary);
      cursor: pointer;
      height: 5px;
      background: var(--chip-bg);
      border-radius: 4px;
      outline: none;
      margin: 4px 0;
    }

    /* Switch Style */
    .switch-container {
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      user-select: none;
      margin-top: 2px;
    }
    .switch-track {
      width: 32px;
      height: 18px;
      background: var(--chip-bg);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      position: relative;
      transition: background 0.2s, border-color 0.2s;
    }
    .switch-track.active {
      background: var(--accent-primary);
      border-color: var(--accent-primary);
    }
    .switch-thumb {
      width: 12px;
      height: 12px;
      background: #ffffff;
      border-radius: 50%;
      position: absolute;
      top: 2px;
      left: 2px;
      transition: transform 0.2s;
    }
    .switch-track.active .switch-thumb {
      transform: translateX(14px);
    }
    .switch-label {
      font-size: 11px;
      color: var(--text-secondary);
    }

    /* Mobile Backdrop & Drawer */
    #drawer-backdrop {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.65);
      z-index: 99;
      backdrop-filter: blur(3px);
    }
    #drawer-backdrop.active { display: block; }

    @media (max-width: 768px) {
      #sidebar {
        position: fixed;
        top: 0;
        bottom: 0;
        left: 0;
        width: 84vw;
        max-width: 320px;
        transform: translateX(-100%);
        box-shadow: 6px 0 24px rgba(0,0,0,0.7);
      }
      #sidebar.open { transform: translateX(0); }
    }

    /* ========================================================
       MAIN PANEL STYLING
       ======================================================== */
    #main-panel {
      flex: 1;
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
      position: relative;
      background: var(--bg-base);
    }

    /* Top Action Bar */
    .top-header-bar {
      height: 50px;
      min-height: 50px;
      background: var(--bg-sidebar);
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
      z-index: 10;
    }

    .top-header-left {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .sidebar-brand-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 4px 0 6px 0;
      margin-bottom: 4px;
    }
    .sidebar-brand-title {
      font-size: 16px;
      font-weight: 700;
      letter-spacing: -0.01em;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .sidebar-brand-right {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .sidebar-close-btn {
      display: none;
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      font-size: 14px;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 4px;
    }
    .sidebar-close-btn:hover {
      background: var(--chip-hover);
      color: var(--text-primary);
    }
    @media (max-width: 768px) {
      .sidebar-close-btn { display: block; }
    }

    /* Status Pill */
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      background: var(--chip-bg);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 3px 12px;
      height: 26px;
      font-size: 11px;
      font-weight: 500;
      color: var(--text-secondary);
      box-sizing: border-box;
    }
    .status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--accent-success);
      box-shadow: 0 0 8px rgba(16, 185, 129, 0.7);
    }
    .status-dot.warning {
      background: var(--accent-warning);
      box-shadow: 0 0 8px rgba(245, 158, 11, 0.7);
    }
    .status-dot.danger {
      background: var(--accent-danger);
      box-shadow: 0 0 8px rgba(239, 68, 68, 0.7);
    }

    /* Header Action Buttons */
    .header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .btn-nav-action {
      background: var(--chip-bg);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      color: var(--text-primary);
      font-size: 11px;
      font-weight: 700;
      padding: 5px 12px;
      height: 30px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: background 0.15s, border-color 0.15s;
    }
    .btn-nav-action:hover {
      background: var(--chip-hover);
      border-color: var(--accent-primary);
    }
    .btn-clear-chat {
      background: transparent;
      border: none;
      font-weight: 500;
      color: var(--text-muted);
    }
    .btn-clear-chat:hover {
      background: var(--chip-bg);
      color: var(--text-primary);
    }

    .hamburger-btn {
      display: none;
      background: var(--chip-bg);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      color: var(--text-primary);
      width: 32px;
      height: 32px;
      cursor: pointer;
      font-size: 15px;
      align-items: center;
      justify-content: center;
    }
    @media (max-width: 768px) {
      .hamburger-btn { display: flex; }
    }

    /* ========================================================
       CHAT VIEWPORT & WELCOME HERO
       ======================================================== */
    #chat-viewport {
      flex: 1;
      overflow-y: auto;
      padding: 16px 20px 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      scroll-behavior: smooth;
    }

    /* Welcome Hero Banner (Exact 2x2 Feature Highlights Grid) */
    .hero-container {
      background: var(--bg-sidebar);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 24px 28px;
      max-width: 900px;
      width: 100%;
      margin: 20px auto;
      box-shadow: 0 4px 20px rgba(0,0,0,0.35);
      animation: fadeIn 0.3s ease;
    }

    .hero-title {
      font-size: 20px;
      font-weight: 700;
      color: #818cf8;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .hero-subtitle {
      font-size: 13px;
      color: var(--text-secondary);
      margin-top: 6px;
      line-height: 1.5;
    }

    .hero-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 20px;
    }
    @media (max-width: 680px) {
      .hero-grid { grid-template-columns: 1fr; }
      .hero-container { padding: 18px; margin: 10px auto; }
    }

    .feature-card {
      background: var(--bg-card-ai);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 14px 16px;
      transition: border-color 0.15s;
    }
    .feature-card:hover { border-color: var(--accent-primary); }

    .feature-card-header {
      font-size: 12px;
      font-weight: 700;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .feature-card-desc {
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 4px;
      line-height: 1.4;
    }

    /* Chat Message Cards - Matching Local Desktop App (ChatMessageCard) */
    .chat-message-card {
      border-radius: 10px;
      border: 1px solid var(--border-color);
      animation: fadeIn 0.2s ease;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(4px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .chat-message-card.user {
      align-self: flex-end;
      margin-left: auto;
      width: fit-content;
      max-width: 80%;
      min-width: 140px;
      background: var(--bg-card-user);
      padding: 6px 12px 8px 12px;
    }

    .chat-message-card.ai {
      align-self: flex-start;
      width: 100%;
      max-width: 100%;
      background: var(--bg-card-ai);
      padding: 8px 14px 10px 14px;
    }

    .chat-message-card.system {
      align-self: flex-start;
      width: 100%;
      background: var(--chip-bg);
      padding: 6px 12px 8px 12px;
    }

    .card-top-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 4px;
      user-select: none;
    }

    .card-top-left {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .card-avatar {
      font-size: 11px;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .chat-message-card.user .card-avatar {
      color: var(--text-secondary);
    }
    .chat-message-card.ai .card-avatar {
      color: var(--accent-primary);
    }
    .chat-message-card.system .card-avatar {
      color: var(--text-muted);
    }

    .card-timestamp {
      font-size: 10px;
      color: var(--text-muted);
    }

    .card-top-right {
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .card-action-btn {
      background: transparent;
      border: none;
      font-size: 10px;
      font-weight: 600;
      font-family: inherit;
      color: var(--text-muted);
      padding: 2px 6px;
      border-radius: 4px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      transition: background 0.15s, color 0.15s;
    }
    .card-action-btn:hover {
      background: var(--chip-hover);
      color: var(--text-primary);
    }

    .card-content {
      font-size: 13px;
      line-height: 1.6;
      color: var(--text-primary);
      word-break: break-word;
      font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    }
    .card-content p {
      margin-top: 0;
      margin-bottom: 8px;
    }
    .card-content p:last-child {
      margin-bottom: 0;
    }
    .card-content strong, .card-content b {
      font-weight: 700;
      color: var(--text-primary);
    }
    .card-content a {
      color: var(--accent-primary);
      text-decoration: underline;
      font-weight: 500;
    }
    .card-content a:hover {
      text-decoration: underline;
      color: var(--accent-hover);
    }
    .card-content ul, .card-content ol {
      margin: 4px 0 8px 20px;
      padding: 0;
    }
    .card-content li {
      margin-bottom: 3px;
    }
    .card-content code {
      background: var(--bg-code);
      padding: 2px 5px;
      border-radius: 4px;
      font-family: Consolas, ui-monospace, Menlo, Monaco, monospace;
      font-size: 11.5px;
      color: #93c5fd;
    }
    .card-content pre {
      background: var(--bg-code);
      padding: 10px 12px;
      border-radius: 8px;
      overflow-x: auto;
      margin: 8px 0;
      border: 1px solid var(--border-color);
    }
    .card-content pre code {
      background: transparent;
      padding: 0;
      color: #93c5fd;
      font-size: 12px;
    }

    /* Code block card top header */
    .code-header-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 2px 4px 6px;
      border-bottom: 1px solid var(--border-color);
      margin-bottom: 8px;
    }
    .code-lang-label {
      font-family: Consolas, monospace;
      font-size: 10px;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: lowercase;
    }
    .code-copy-btn {
      background: transparent;
      border: none;
      font-size: 10px;
      font-weight: 600;
      color: var(--text-muted);
      cursor: pointer;
      padding: 1px 6px;
      border-radius: 4px;
    }
    .code-copy-btn:hover {
      background: var(--chip-hover);
      color: var(--text-primary);
    }

    /* ========================================================
       PROMPT CHIPS & BOTTOM INPUT SECTION
       ======================================================== */
    .bottom-interactive-section {
      padding: 0 20px 16px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      max-width: 940px;
      width: 100%;
      margin: 0 auto;
    }
    @media (max-width: 768px) {
      .bottom-interactive-section { padding: 0 10px 10px; }
    }

    /* Chips Bar */
    .chips-carousel {
      display: flex;
      gap: 8px;
      overflow-x: auto;
      scrollbar-width: none;
      padding-bottom: 4px;
    }
    .chips-carousel::-webkit-scrollbar { display: none; }

    .prompt-chip-btn {
      white-space: nowrap;
      background: var(--chip-bg);
      border: 1px solid var(--border-color);
      color: var(--text-primary);
      padding: 6px 14px;
      border-radius: 18px;
      font-size: 11.5px;
      font-weight: 500;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: background 0.15s, border-color 0.15s;
      flex-shrink: 0;
    }
    .prompt-chip-btn:hover {
      background: var(--chip-hover);
      border-color: var(--accent-primary);
    }

    /* Progress Bar */
    .generation-progress-bar {
      height: 3px;
      width: 100%;
      background: transparent;
      border-radius: 2px;
      overflow: hidden;
      position: relative;
    }
    .generation-progress-bar.active::after {
      content: "";
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 40%;
      background: var(--accent-primary);
      border-radius: 2px;
      animation: indeterminate 1.4s infinite ease-in-out;
    }
    @keyframes indeterminate {
      0% { left: -40%; width: 40%; }
      50% { left: 40%; width: 60%; }
      100% { left: 100%; width: 40%; }
    }

    /* Attached Image Preview Bar */
    .image-preview-banner {
      display: none;
      align-items: center;
      justify-content: space-between;
      background: var(--chip-bg);
      border: 1px solid var(--accent-primary);
      border-radius: 8px;
      padding: 6px 12px;
    }
    .preview-info {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      font-weight: 600;
      color: var(--text-primary);
    }
    .btn-remove-photo {
      background: transparent;
      border: none;
      color: var(--accent-danger);
      font-size: 11px;
      cursor: pointer;
      font-weight: 600;
    }

    /* Elevated Input Card */
    .input-card-box {
      position: relative;
      background: var(--bg-input);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 6px 10px;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: border-color 0.2s;
    }
    .input-card-box:focus-within { border-color: var(--accent-primary); }

    /* Floating Attachment Menu (Gemini / ChatGPT Style) */
    .attachment-popup-menu {
      position: absolute;
      bottom: calc(100% + 12px);
      left: 6px;
      width: 244px;
      background: var(--bg-sidebar);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 6px;
      box-shadow: 0 16px 36px rgba(0, 0, 0, 0.55);
      display: none;
      flex-direction: column;
      gap: 3px;
      z-index: 1000;
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      animation: popupSlideFade 0.16s ease-out;
    }
    .attachment-popup-menu.open {
      display: flex;
    }
    @keyframes popupSlideFade {
      from { opacity: 0; transform: translateY(8px) scale(0.98); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }

    .attachment-menu-item {
      display: flex;
      align-items: center;
      gap: 10px;
      width: 100%;
      height: 38px;
      padding: 0 12px;
      border: none;
      background: transparent;
      color: var(--text-primary);
      font-family: inherit;
      font-size: 12px;
      font-weight: 700;
      border-radius: 8px;
      cursor: pointer;
      text-align: left;
      transition: background 0.15s, color 0.15s, transform 0.1s;
    }
    .attachment-menu-item:hover {
      background: var(--chip-hover);
      color: var(--text-primary);
    }
    .attachment-menu-item:active {
      transform: scale(0.98);
    }
    .attachment-menu-icon {
      font-size: 15px;
      width: 22px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }
    .attachment-menu-label {
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .btn-input-attach {
      background: transparent;
      border: none;
      color: var(--text-secondary);
      font-size: 20px;
      font-weight: 700;
      width: 36px;
      height: 36px;
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.15s, color 0.15s, transform 0.15s;
      flex-shrink: 0;
    }
    .btn-input-attach:hover { background: var(--chip-hover); color: var(--text-primary); }
    .btn-input-attach.open {
      color: var(--text-primary);
      background: var(--chip-hover);
      font-size: 15px;
    }

    /* Embedded Chat Image Cards */
    .chat-embedded-image-container {
      margin-top: 10px;
      border-radius: 10px;
      overflow: hidden;
      border: 1px solid var(--border-color);
      display: inline-block;
      max-width: 100%;
      cursor: pointer;
      background: rgba(0, 0, 0, 0.25);
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    .chat-embedded-image-container:hover {
      border-color: var(--accent-primary);
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
    }
    .chat-embedded-image {
      max-width: 100%;
      max-height: 380px;
      display: block;
      object-fit: cover;
    }
    .chat-image-caption {
      padding: 6px 12px;
      font-size: 11px;
      color: var(--text-muted);
      background: var(--bg-card);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      border-top: 1px solid var(--border-color);
    }

    .query-textarea {
      flex: 1;
      background: transparent;
      border: none;
      color: var(--text-primary);
      font-family: inherit;
      font-size: 13.5px;
      resize: none;
      max-height: 120px;
      min-height: 24px;
      padding: 6px 0;
      outline: none;
      line-height: 1.4;
    }
    .query-textarea::placeholder { color: var(--text-muted); }

    .btn-mic-stt {
      width: 36px;
      height: 36px;
      border-radius: 8px;
      background: transparent;
      border: none;
      color: var(--text-secondary);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
      transition: background 0.15s, color 0.15s;
      flex-shrink: 0;
    }
    .btn-mic-stt:hover { background: var(--chip-hover); color: var(--text-primary); }
    .btn-mic-stt.recording {
      background: var(--accent-danger);
      color: #ffffff;
      animation: pulseMic 1.4s infinite;
    }
    @keyframes pulseMic {
      0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
      70% { transform: scale(1.08); box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
      100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    }

    .btn-search-primary {
      height: 38px;
      padding: 0 18px;
      border-radius: 8px;
      background: var(--accent-primary);
      color: #ffffff;
      border: none;
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      font-weight: 700;
      font-size: 13px;
      transition: background 0.15s;
      flex-shrink: 0;
    }
    .btn-search-primary:hover { background: var(--accent-hover); }
    .btn-search-primary.btn-stop {
      background: var(--accent-danger);
    }

    /* ========================================================
       MODAL STYLING (Stats, History, Export, Image Viewer)
       ======================================================== */
    .modal-overlay {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.75);
      z-index: 300;
      backdrop-filter: blur(4px);
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .modal-overlay.open { display: flex; }

    .modal-window {
      background: var(--bg-sidebar);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      width: 100%;
      max-width: 520px;
      max-height: 85vh;
      overflow-y: auto;
      padding: 20px;
      box-shadow: 0 16px 40px rgba(0,0,0,0.7);
      animation: fadeIn 0.2s ease;
    }

    .modal-header-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 10px;
    }
    .modal-title {
      font-size: 15px;
      font-weight: 700;
      color: var(--text-primary);
    }
    .modal-close-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      font-size: 16px;
      padding: 4px;
    }
    .modal-close-btn:hover { color: var(--text-primary); }

    .stats-metric-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-bottom: 16px;
    }
    .stat-metric-card {
      background: var(--bg-base);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 12px;
      text-align: center;
    }
    .stat-number {
      font-size: 22px;
      font-weight: 700;
      color: var(--accent-primary);
    }
    .stat-title {
      font-size: 10px;
      text-transform: uppercase;
      color: var(--text-muted);
      margin-top: 2px;
    }

    .session-list-box {
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-height: 300px;
      overflow-y: auto;
    }
    .session-item-card {
      background: var(--bg-base);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 10px 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      cursor: pointer;
      transition: border-color 0.15s;
    }
    .session-item-card:hover { border-color: var(--accent-primary); }
    .session-title-text { font-size: 12px; font-weight: 600; color: var(--text-primary); }
    .session-date-sub { font-size: 10px; color: var(--text-muted); margin-top: 2px; }
  </style>
</head>
<body>

  <!-- App Main Shell -->
  <div id="app-container">
    <!-- Mobile Drawer Backdrop -->
    <div id="drawer-backdrop" onclick="toggleSidebarDrawer(false)"></div>

    <!-- 1. LEFT SIDEBAR -->
    <aside id="sidebar">
      <div class="sidebar-inner">
        <!-- Sidebar Brand Header (Exact Desktop Styling) -->
        <div class="sidebar-brand-header">
          <div class="sidebar-brand-title">🧠 Search Studio</div>
          <div class="sidebar-brand-right">
            <span class="badge-ver">v2.0</span>
            <button class="sidebar-close-btn" onclick="toggleSidebarDrawer(false)" title="Close Sidebar">✕</button>
          </div>
        </div>

        <!-- Upload Files & Analytics Stats Buttons -->
        <div class="sidebar-btn-row">
          <button class="btn-upload" onclick="triggerFileInput()" title="Upload PDF, Word, CSV, Code, Images">
            <span>📂</span> Upload Files
          </button>
          <button class="btn-stats" onclick="openStatsModal()" title="Knowledge Base Analytics">
            📊
          </button>
        </div>

        <!-- Uploaded Files Section Header -->
        <div class="section-header-row">
          <span class="section-title">UPLOADED FILES & DOCS</span>
          <span class="section-count-badge" id="sidebar-file-count">0 files</span>
        </div>

        <!-- Scrollable Active Sources List -->
        <div class="sources-scroll-box" id="sources-container">
          <div class="sources-empty">No documents loaded.<br>Click 'Upload Files' to add PDF, Word, CSV, Images...</div>
        </div>

        <!-- Search Mode Selector -->
        <div class="control-group">
          <label class="control-label" for="select-search-mode">Search Mode</label>
          <select id="select-search-mode" class="select-menu" onchange="onModeChanged()">
            <option value="Auto (Hybrid)">Auto (Hybrid)</option>
            <option value="Docs Only">Docs Only</option>
            <option value="Web Only">Web Only</option>
          </select>
        </div>

        <!-- AI Model Selector -->
        <div class="control-group">
          <label class="control-label" for="select-ai-model">AI Model</label>
          <select id="select-ai-model" class="select-menu" onchange="onModelChanged()">
            <option value="open-mistral-7b">open-mistral-7b</option>
            <option value="mistral-small-latest">mistral-small-latest</option>
            <option value="mistral-medium-latest">mistral-medium-latest</option>
            <option value="mistral-large-latest">mistral-large-latest</option>
            <option value="codestral-latest">codestral-latest</option>
          </select>
        </div>

        <!-- Retrieval Depth Slider -->
        <div class="control-group">
          <div class="control-header-row">
            <span class="control-label">Retrieval Depth</span>
            <span class="depth-val-indicator" id="depth-val-text">4</span>
          </div>
          <input type="range" id="slider-depth" class="range-slider" min="1" max="10" value="4" oninput="onDepthChanged(this.value)">
        </div>

        <!-- Auto-Read Aloud (TTS) Switch -->
        <div class="switch-container" onclick="toggleAutoTts()">
          <div class="switch-track" id="auto-tts-track">
            <div class="switch-thumb"></div>
          </div>
          <span class="switch-label">Auto-Read Aloud (TTS)</span>
        </div>

        <!-- Interface Theme Selector -->
        <div class="control-group">
          <label class="control-label" for="select-theme">Interface Theme</label>
          <select id="select-theme" class="select-menu" onchange="onThemeChanged(this.value)">
            <option value="Developer Dark">Developer Dark</option>
            <option value="Obsidian Slate">Obsidian Slate</option>
            <option value="Nordic Dark">Nordic Dark</option>
            <option value="Developer Light">Developer Light</option>
          </select>
        </div>
      </div>
    </aside>

    <!-- 2. MAIN WORKSPACE PANEL -->
    <main id="main-panel">
      <!-- Top Action Bar -->
      <header class="top-header-bar">
        <div class="top-header-left">
          <button class="hamburger-btn" onclick="toggleSidebarDrawer(true)" title="Menu">☰</button>
          <div class="status-pill" id="header-status-pill">
            <div class="status-dot" id="status-dot"></div>
            <span id="status-pill-text">Ready</span>
          </div>
        </div>

        <!-- Right Quick Action Buttons -->
        <div class="header-actions">
          <button class="btn-nav-action btn-clear-chat" onclick="clearCurrentChat()" title="Clear Chat">
            🧹 Clear Chat
          </button>
          <button class="btn-nav-action" onclick="openHistoryModal()" title="View Chat History">
            🕒 History
          </button>
          <button class="btn-nav-action" onclick="openExportModal()" title="Export Chat">
            💾 Export Chat
          </button>
        </div>
      </header>

      <!-- Scrollable Message Feed -->
      <section id="chat-viewport">
        <!-- Welcome Hero View (Rendered when no chat messages) -->
        <div class="hero-container" id="hero-welcome-card">
          <div class="hero-title">✨ Welcome to Search Studio</div>
          <div class="hero-subtitle">
            Your multi-modal RAG knowledge engine. Ask questions from your PDFs, Word documents,<br>code, spreadsheets, or query live web intelligence with voice & image support.
          </div>

          <!-- 2x2 Feature Highlights Grid -->
          <div class="hero-grid">
            <div class="feature-card">
              <div class="feature-card-header">📄 Multi-Format Uploads</div>
              <div class="feature-card-desc">PDF, Word (DOCX), CSV, Excel, TXT, Code & OCR</div>
            </div>
            <div class="feature-card">
              <div class="feature-card-header">⚡ Real-Time Streaming</div>
              <div class="feature-card-desc">Instant token generation powered by Mistral AI</div>
            </div>
            <div class="feature-card">
              <div class="feature-card-header">🎙️ Two-Way Voice</div>
              <div class="feature-card-desc">Speech-to-text input and natural voice read-aloud</div>
            </div>
            <div class="feature-card">
              <div class="feature-card-header">🌐 Live Web & Images</div>
              <div class="feature-card-desc">Automatic search fallbacks and inline image discovery</div>
            </div>
          </div>
        </div>
      </section>

      <!-- Bottom Interactive Section -->
      <footer class="bottom-interactive-section">
        <!-- Prompt Suggestion Chips -->
        <div class="chips-carousel">
          <button class="prompt-chip-btn" onclick="sendQuickPrompt('Summarize the uploaded documents with key takeaways and bullet points.')">📝 Summarize Docs</button>
          <button class="prompt-chip-btn" onclick="sendQuickPrompt('Create 5 practice quiz questions based on the uploaded knowledge base.')">🎯 Practice Quiz</button>
          <button class="prompt-chip-btn" onclick="sendQuickPrompt('What are the key insights and actionable highlights in these documents?')">💡 Key Insights</button>
          <button class="prompt-chip-btn" onclick="setQuickMode('Web Only')">🌐 Web Mode</button>
          <button class="prompt-chip-btn" onclick="setQuickMode('Docs Only')">📄 Docs Mode</button>
          <button class="prompt-chip-btn" onclick="setQuickMode('Auto (Hybrid)')">🔄 Auto Mode</button>
        </div>

        <!-- Generation Progress Bar -->
        <div class="generation-progress-bar" id="progress-indicator"></div>

        <!-- Attached Image Preview Bar -->
        <div class="image-preview-banner" id="photo-preview-bar">
          <div class="preview-info">
            <span>🖼️</span>
            <span id="photo-preview-name">image.png</span>
          </div>
          <button class="btn-remove-photo" onclick="removeAttachedPhoto()">✕ Remove Photo</button>
        </div>

        <!-- Elevated Input Box -->
        <div class="input-card-box">
          <!-- Floating Attachment Menu Card (Gemini / ChatGPT Style) -->
          <div class="attachment-popup-menu" id="attachment-popup-menu">
            <button class="attachment-menu-item" type="button" onclick="triggerAttachmentAction('photo')">
              <span class="attachment-menu-icon">📷</span>
              <span class="attachment-menu-label">Photos (Image Analysis)</span>
            </button>
            <button class="attachment-menu-item" type="button" onclick="triggerAttachmentAction('files')">
              <span class="attachment-menu-icon">📄</span>
              <span class="attachment-menu-label">Upload Files & Docs</span>
            </button>
            <button class="attachment-menu-item" type="button" onclick="triggerAttachmentAction('web_image')">
              <span class="attachment-menu-icon">🌐</span>
              <span class="attachment-menu-label">Search Web Images</span>
            </button>
            <button class="attachment-menu-item" type="button" onclick="triggerAttachmentAction('summarize')">
              <span class="attachment-menu-icon">📝</span>
              <span class="attachment-menu-label">Summarize Knowledge</span>
            </button>
            <button class="attachment-menu-item" type="button" onclick="triggerAttachmentAction('quiz')">
              <span class="attachment-menu-icon">🎯</span>
              <span class="attachment-menu-label">Practice Quiz</span>
            </button>
          </div>

          <button class="btn-input-attach" id="btn-attach-menu" onclick="toggleAttachmentMenu(event)" title="Attach or Quick Tools">+</button>
          <textarea id="main-query-input" class="query-textarea" rows="1" placeholder="Ask any question about your documents, code, or search the web..." onkeydown="handleInputKeyDown(event)" oninput="autoGrowInput(this)"></textarea>
          <button class="btn-mic-stt" id="mic-toggle-btn" onclick="toggleVoiceSTT()" title="Voice Dictation">🎙️</button>
          <button class="btn-search-primary" id="btn-submit-search" onclick="handleSubmitOrStop()">
            <span id="search-icon-symbol">🔍</span> <span id="search-btn-label">Search</span>
          </button>
        </div>
      </footer>
    </main>
  </div>

  <!-- Hidden File Pickers -->
  <input type="file" id="general-file-input" multiple style="display: none;" onchange="handleFileUpload(event)">
  <input type="file" id="image-file-input" accept="image/*" style="display: none;" onchange="handleImageAttachment(event)">

  <!-- MODALS -->
  <!-- 1. Knowledge Base Analytics Modal -->
  <div class="modal-overlay" id="stats-modal" onclick="closeModalOnBackdrop(event, 'stats-modal')">
    <div class="modal-window">
      <div class="modal-header-row">
        <div class="modal-title">📊 Knowledge Base Analytics</div>
        <button class="modal-close-btn" onclick="closeModal('stats-modal')">✕</button>
      </div>
      <div class="stats-metric-grid">
        <div class="stat-metric-card">
          <div class="stat-number" id="stats-total-files">0</div>
          <div class="stat-title">Indexed Documents</div>
        </div>
        <div class="stat-metric-card">
          <div class="stat-number" id="stats-total-chunks">0</div>
          <div class="stat-title">Vector Chunks</div>
        </div>
        <div class="stat-metric-card">
          <div class="stat-number" id="stats-total-size">0 KB</div>
          <div class="stat-title">Storage Footprint</div>
        </div>
        <div class="stat-metric-card">
          <div class="stat-number" style="font-size: 16px; margin-top: 5px;" id="stats-db-status">Active</div>
          <div class="stat-title">ChromaDB Engine</div>
        </div>
      </div>
      <button class="btn-upload" style="background: var(--accent-danger); width: 100%;" onclick="clearAllDocuments()">
        🧹 Clear Entire Knowledge Base
      </button>
    </div>
  </div>

  <!-- 2. Chat History Modal -->
  <div class="modal-overlay" id="history-modal" onclick="closeModalOnBackdrop(event, 'history-modal')">
    <div class="modal-window">
      <div class="modal-header-row">
        <div class="modal-title">🕒 Conversation History</div>
        <button class="modal-close-btn" onclick="closeModal('history-modal')">✕</button>
      </div>
      <button class="btn-upload" style="width: 100%; margin-bottom: 12px;" onclick="createNewSession()">
        ➕ New Conversation
      </button>
      <div class="session-list-box" id="session-items-list">
        <div style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 20px 0;">Loading history...</div>
      </div>
    </div>
  </div>

  <!-- 3. Export Chat Modal -->
  <div class="modal-overlay" id="export-modal" onclick="closeModalOnBackdrop(event, 'export-modal')">
    <div class="modal-window">
      <div class="modal-header-row">
        <div class="modal-title">💾 Export Conversation</div>
        <button class="modal-close-btn" onclick="closeModal('export-modal')">✕</button>
      </div>
      <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 16px;">
        Download the active conversation with full citations and formatting:
      </p>
      <div style="display: flex; flex-direction: column; gap: 8px;">
        <button class="btn-nav-action" style="height: 38px; justify-content: center;" onclick="downloadExport('markdown')">
          📄 Download as Markdown (.md)
        </button>
        <button class="btn-nav-action" style="height: 38px; justify-content: center;" onclick="downloadExport('json')">
          🗂️ Download as JSON (.json)
        </button>
        <button class="btn-nav-action" style="height: 38px; justify-content: center;" onclick="downloadExport('txt')">
          📝 Download as Plain Text (.txt)
        </button>
      </div>
    </div>
  </div>

  <!-- 4. Image Viewer Modal -->
  <div class="modal-overlay" id="image-modal" onclick="closeModalOnBackdrop(event, 'image-modal')">
    <div class="modal-window" style="max-width: 680px; text-align: center;">
      <div class="modal-header-row">
        <div class="modal-title">🖼️ Image Preview</div>
        <button class="modal-close-btn" onclick="closeModal('image-modal')">✕</button>
      </div>
      <img id="modal-preview-img" src="" style="max-width: 100%; max-height: 55vh; border-radius: 8px; border: 1px solid var(--border-color); object-fit: contain;">
      <div style="margin-top: 12px; display: flex; justify-content: flex-end; gap: 8px;">
        <button class="btn-nav-action" id="modal-img-save-btn" onclick="saveActiveImage()">💾 Save Image</button>
      </div>
    </div>
  </div>

  <!-- ========================================================
       CORE CLIENT CONTROLLER JAVASCRIPT
       ======================================================== -->
  <script>
    // State
    let currentSessionId = 'session_' + Date.now();
    let currentMessages = [];
    let isProcessing = false;
    let autoTtsEnabled = false;
    let attachedImageFile = null;
    let recognitionInstance = null;
    let isRecordingVoice = false;
    let activeEventSource = null;
    let activeSourcesList = [];

    // Elements
    const sidebar = document.getElementById('sidebar');
    const drawerBackdrop = document.getElementById('drawer-backdrop');
    const chatViewport = document.getElementById('chat-viewport');
    const queryInput = document.getElementById('main-query-input');
    const searchBtn = document.getElementById('btn-submit-search');
    const searchIconSymbol = document.getElementById('search-icon-symbol');
    const searchBtnLabel = document.getElementById('search-btn-label');
    const statusDot = document.getElementById('status-dot');
    const statusPillText = document.getElementById('status-pill-text');
    const sourcesContainer = document.getElementById('sources-container');
    const fileCountBadge = document.getElementById('sidebar-file-count');
    const progressBar = document.getElementById('progress-indicator');
    const photoBanner = document.getElementById('photo-preview-bar');
    const photoNameText = document.getElementById('photo-preview-name');
    const depthValText = document.getElementById('depth-val-text');
    const depthSlider = document.getElementById('slider-depth');
    const modeSelect = document.getElementById('select-search-mode');
    const modelSelect = document.getElementById('select-ai-model');
    const themeSelect = document.getElementById('select-theme');
    const heroCard = document.getElementById('hero-welcome-card');

    // Restore saved theme from local storage
    const savedTheme = localStorage.getItem('search_studio_theme') || 'Developer Dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    if (themeSelect) themeSelect.value = savedTheme;

    // Configure Marked for GitHub Flavored Markdown and secure new-tab links
    try {
      if (typeof marked !== 'undefined') {
        marked.setOptions({ breaks: true, gfm: true });
        const renderer = {
          link(item) {
            const href = item.href || (typeof item === 'string' ? item : '#');
            const text = item.text || item.href || href;
            const title = item.title ? ` title="${item.title}"` : '';
            return `<a href="${href}"${title} target="_blank" rel="noopener noreferrer">${text}</a>`;
          }
        };
        marked.use({ renderer });
      }
    } catch (e) {
      console.log('Marked configuration notice:', e);
    }

    // Service Worker Registration for PWA
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(err => console.log('SW notice:', err));
      });
    }

    // 1. INITIAL APP CONFIG & DOCUMENTS LOAD
    async function initApp() {
      try {
        const res = await fetch('/api/config');
        const data = await res.json();

        if (data.current_mode) modeSelect.value = data.current_mode;
        if (data.current_model) modelSelect.value = data.current_model;
        if (data.current_depth) {
          depthSlider.value = data.current_depth;
          depthValText.textContent = data.current_depth;
        }

        if (data.knowledge_stats) {
          renderKnowledgeSources(data.knowledge_stats);
        }
      } catch (e) {
        console.error('Config load failed:', e);
        setStatus("Ready (Offline)", "warning");
      }
    }
    initApp();

    // 2. STATUS HELPER
    function setStatus(text, type = "success") {
      statusPillText.textContent = text;
      statusDot.className = "status-dot" + (type === "warning" ? " warning" : type === "danger" ? " danger" : "");
    }

    // 3. KNOWLEDGE SOURCES RENDERING
    function getFileIcon(filename) {
      const ext = filename.split('.').pop().toLowerCase();
      if (ext === 'pdf') return '📄';
      if (ext === 'docx') return '📘';
      if (ext === 'txt' || ext === 'md') return '📝';
      if (['csv', 'xlsx', 'xls'].includes(ext)) return '📊';
      if (['java'].includes(ext)) return '☕';
      if (['py'].includes(ext)) return '🐍';
      if (['js', 'ts', 'html', 'css', 'json'].includes(ext)) return '📜';
      if (['png', 'jpg', 'jpeg', 'webp'].includes(ext)) return '🖼️';
      return '📄';
    }

    function renderKnowledgeSources(stats) {
      const sources = stats.sources || [];
      activeSourcesList = sources;
      fileCountBadge.textContent = `${sources.length} files`;

      // Update Top Status Pill
      if (stats.total_chunks > 0) {
        setStatus(`Ready (${stats.total_chunks} Chunks)`, "success");
      } else {
        setStatus("Ready (0 Chunks)", "warning");
      }

      // Update Stats Modal Metrics
      document.getElementById('stats-total-files').textContent = sources.length;
      document.getElementById('stats-total-chunks').textContent = stats.total_chunks || 0;
      document.getElementById('stats-total-size').textContent = (stats.total_size_kb || 0) + ' KB';

      if (!sources.length) {
        sourcesContainer.innerHTML = `<div class="sources-empty">No documents loaded.<br>Click 'Upload Files' to add PDF, Word, CSV, Images...</div>`;
        return;
      }

      sourcesContainer.innerHTML = sources.map(s => `
        <div class="source-card">
          <div class="source-left">
            <span class="source-icon">${getFileIcon(s.filename)}</span>
            <div style="min-width: 0;">
              <div class="source-name" title="${escapeHtml(s.filename)}">${escapeHtml(s.filename)}</div>
              <div class="source-meta">${s.chunks} chunks • ${s.size_kb} KB</div>
            </div>
          </div>
          <button class="source-del-btn" onclick="deleteSource('${escapeHtml(s.filename)}')" title="Delete Source">✕</button>
        </div>
      `).join('');
    }

    // 4. FILE UPLOADS
    function triggerFileInput() {
      document.getElementById('general-file-input').click();
    }

    async function handleFileUpload(event) {
      const files = event.target.files;
      if (!files || !files.length) return;

      const formData = new FormData();
      for (const f of files) {
        formData.append('files', f);
      }

      setStatus("Indexing Documents...", "warning");
      progressBar.classList.add('active');

      try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Upload error");

        renderKnowledgeSources(data.knowledge_stats);
        addSystemCard(`✅ Indexed **${data.files_indexed} file(s)** (${data.chunks_created} chunks) into knowledge base.`);
      } catch (err) {
        alert("Upload error: " + err.message);
        setStatus("Upload Failed", "danger");
      } finally {
        progressBar.classList.remove('active');
        event.target.value = '';
      }
    }

    async function deleteSource(filename) {
      if (!confirm(`Remove ${filename} from knowledge base?`)) return;
      try {
        const res = await fetch(`/api/documents/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.knowledge_stats) renderKnowledgeSources(data.knowledge_stats);
      } catch (err) {
        alert("Delete failed: " + err.message);
      }
    }

    async function clearAllDocuments() {
      if (!confirm("Are you sure you want to clear the entire knowledge base?")) return;
      try {
        const res = await fetch('/api/documents', { method: 'DELETE' });
        const data = await res.json();
        if (data.knowledge_stats) renderKnowledgeSources(data.knowledge_stats);
        closeModal('stats-modal');
        addSystemCard("🧹 Entire knowledge base and vectors cleared.");
      } catch (err) {
        alert("Failed clearing knowledge base: " + err.message);
      }
    }

    // 5. SIDEBAR SETTINGS HANDLERS
    async function onModeChanged() {
      const mode = modeSelect.value;
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode })
      });
      addSystemCard(`Search mode switched to: **${mode}**`);
    }

    async function onModelChanged() {
      const model = modelSelect.value;
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model })
      });
    }

    async function onDepthChanged(val) {
      depthValText.textContent = val;
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ depth: parseInt(val) })
      });
    }

    function toggleAutoTts() {
      autoTtsEnabled = !autoTtsEnabled;
      const track = document.getElementById('auto-tts-track');
      if (autoTtsEnabled) track.classList.add('active');
      else track.classList.remove('active');
    }

    function onThemeChanged(themeName) {
      document.documentElement.setAttribute('data-theme', themeName);
      localStorage.setItem('search_studio_theme', themeName);
    }

    function toggleSidebarDrawer(open) {
      if (open) {
        sidebar.classList.add('open');
        drawerBackdrop.classList.add('active');
      } else {
        sidebar.classList.remove('open');
        drawerBackdrop.classList.remove('active');
      }
    }

    // 6. FLOATING ATTACHMENT (+) MENU & PHOTO ANALYSIS
    function toggleAttachmentMenu(event) {
      if (event) {
        event.stopPropagation();
        event.preventDefault();
      }
      const menu = document.getElementById('attachment-popup-menu');
      const btn = document.getElementById('btn-attach-menu');
      if (!menu || !btn) return;

      const isOpen = menu.classList.contains('open');
      if (isOpen) {
        closeAttachmentMenu();
      } else {
        menu.classList.add('open');
        btn.classList.add('open');
        btn.textContent = '✕';
      }
    }

    function closeAttachmentMenu() {
      const menu = document.getElementById('attachment-popup-menu');
      const btn = document.getElementById('btn-attach-menu');
      if (menu) menu.classList.remove('open');
      if (btn) {
        btn.classList.remove('open');
        btn.textContent = '+';
      }
    }

    function triggerAttachmentAction(action) {
      closeAttachmentMenu();

      if (action === 'photo') {
        const input = document.getElementById('image-file-input');
        if (input) input.click();
      } else if (action === 'files') {
        triggerFileInput();
      } else if (action === 'web_image') {
        queryInput.value = "Show me a picture of ";
        autoGrowInput(queryInput);
        queryInput.focus();
        const len = queryInput.value.length;
        try { queryInput.setSelectionRange(len, len); } catch (e) {}
      } else if (action === 'summarize') {
        if (!activeSourcesList || activeSourcesList.length === 0) {
          alert("Please upload files (PDF, Word, TXT, etc.) to use this AI tool.");
          return;
        }
        sendQuickPrompt("Generate a comprehensive executive summary of all uploaded documents.");
      } else if (action === 'quiz') {
        if (!activeSourcesList || activeSourcesList.length === 0) {
          alert("Please upload files (PDF, Word, TXT, etc.) to use this AI tool.");
          return;
        }
        sendQuickPrompt("Generate an interactive 5-question practice quiz with an Answer Key and Explanations based on the loaded documents.");
      }
    }

    // Dismiss attachment popup when clicking anywhere outside or pressing Escape
    document.addEventListener('click', (event) => {
      const menu = document.getElementById('attachment-popup-menu');
      const btn = document.getElementById('btn-attach-menu');
      if (menu && menu.classList.contains('open')) {
        if (!menu.contains(event.target) && !btn.contains(event.target)) {
          closeAttachmentMenu();
        }
      }
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        closeAttachmentMenu();
      }
    });

    function handleImageAttachment(event) {
      const file = event.target.files[0];
      if (!file) return;
      attachedImageFile = file;
      const sizeKb = Math.round(file.size / 1024);
      photoNameText.textContent = `${file.name} (${sizeKb} KB)`;
      photoBanner.style.display = 'flex';
      queryInput.placeholder = "Ask a question about this image (or click Search to analyze)...";
      queryInput.focus();
      event.target.value = '';
    }

    function removeAttachedPhoto() {
      attachedImageFile = null;
      photoBanner.style.display = 'none';
      queryInput.placeholder = "Ask any question about your documents, code, or search the web...";
    }

    // 7. INPUT RESIZE & SUBMISSION
    function autoGrowInput(el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    }

    function handleInputKeyDown(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmitOrStop();
      }
    }

    function sendQuickPrompt(promptText) {
      queryInput.value = promptText;
      autoGrowInput(queryInput);
      handleSubmitOrStop();
    }

    function setQuickMode(modeName) {
      modeSelect.value = modeName;
      onModeChanged();
    }

    function handleSubmitOrStop() {
      if (isProcessing) {
        // Trigger Stop
        if (activeEventSource) {
          activeEventSource.close();
          activeEventSource = null;
        }
        finishProcessingState();
        return;
      }

      const query = queryInput.value.trim();
      if (!query && !attachedImageFile) return;

      if (attachedImageFile) {
        sendImageAnalysis(query || "Please analyze this image, solve any question contained within it, and explain key takeaways.");
      } else {
        sendTextQuery(query);
      }
    }

    function setProcessingState(running) {
      isProcessing = running;
      if (running) {
        progressBar.classList.add('active');
        searchBtn.classList.add('btn-stop');
        searchIconSymbol.textContent = '⏹';
        searchBtnLabel.textContent = 'Stop';
      } else {
        progressBar.classList.remove('active');
        searchBtn.classList.remove('btn-stop');
        searchIconSymbol.textContent = '🔍';
        searchBtnLabel.textContent = 'Search';
      }
    }

    function finishProcessingState() {
      setProcessingState(false);
      saveCurrentSession();
    }

    // 8. CHAT RENDERING
    function formatCurrentTime() {
      const now = new Date();
      return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
    }

    function enhanceCodeBlocks(container) {
      container.querySelectorAll('pre code').forEach(block => {
        try { hljs.highlightElement(block); } catch (e) {}
        const pre = block.parentElement;
        if (pre && !pre.querySelector('.code-header-bar')) {
          const langMatch = block.className.match(/language-(\w+)/);
          const lang = langMatch ? langMatch[1] : 'code';
          const header = document.createElement('div');
          header.className = 'code-header-bar';
          header.innerHTML = `
            <span class="code-lang-label">${lang.toLowerCase()}</span>
            <button class="code-copy-btn" onclick="copySnippet(this)">📋 Copy</button>
          `;
          pre.insertBefore(header, block);
        }
      });
    }

    function copySnippet(btn) {
      const code = btn.closest('pre').querySelector('code').innerText;
      navigator.clipboard.writeText(code);
      btn.textContent = '✅ Copied!';
      setTimeout(() => { btn.textContent = '📋 Copy'; }, 1500);
    }

    // 8. CHAT RENDERING - Matching Local Desktop App Cards
    function hideHeroIfVisible() {
      if (heroCard && heroCard.style.display !== 'none') {
        heroCard.style.display = 'none';
      }
    }

    function addMessageRow(role, content, citations = [], timestamp = null) {
      hideHeroIfVisible();

      const timeStr = timestamp || formatCurrentTime();
      const card = document.createElement('div');
      card.className = `chat-message-card ${role}`;

      if (role === 'user') {
        card.innerHTML = `
          <div class="card-top-bar">
            <div class="card-top-left">
              <span class="card-avatar">👤 You</span>
              <span class="card-timestamp">${escapeHtml(timeStr)}</span>
            </div>
          </div>
          <div class="card-content">${escapeHtml(content).replace(/\n/g, '<br>')}</div>
        `;
      } else if (role === 'ai') {
        const parsedHtml = marked.parse(content);
        card.innerHTML = `
          <div class="card-top-bar">
            <div class="card-top-left">
              <span class="card-avatar">⚡ Assistant</span>
              <span class="card-timestamp">${escapeHtml(timeStr)}</span>
            </div>
            <div class="card-top-right">
              <button class="card-action-btn" onclick="copyMessage(this)">📋 Copy All</button>
              <button class="card-action-btn" onclick="speakMessage(this)">🔊 Speak</button>
            </div>
          </div>
          <div class="card-content">${parsedHtml}</div>
        `;
      } else {
        const parsedHtml = marked.parse(content);
        card.innerHTML = `
          <div class="card-top-bar">
            <div class="card-top-left">
              <span class="card-avatar">ℹ️ System</span>
              <span class="card-timestamp">${escapeHtml(timeStr)}</span>
            </div>
          </div>
          <div class="card-content">${parsedHtml}</div>
        `;
      }

      chatViewport.appendChild(card);
      enhanceCodeBlocks(card);
      chatViewport.scrollTop = chatViewport.scrollHeight;

      currentMessages.push({ role, content, timestamp: timeStr, citations });
      return card;
    }

    function addSystemCard(text) {
      hideHeroIfVisible();
      const timeStr = formatCurrentTime();
      const card = document.createElement('div');
      card.className = 'chat-message-card system';
      card.innerHTML = `
        <div class="card-top-bar">
          <div class="card-top-left">
            <span class="card-avatar">ℹ️ System</span>
            <span class="card-timestamp">${escapeHtml(timeStr)}</span>
          </div>
        </div>
        <div class="card-content">${marked.parse(text)}</div>
      `;
      chatViewport.appendChild(card);
      chatViewport.scrollTop = chatViewport.scrollHeight;
    }

    // 9. QUERY DISPATCH & STREAMING
    async function sendTextQuery(query) {
      // Check if user is searching for web images
      const lowerQ = query.toLowerCase().trim();
      const imgTriggers = ["show me a picture of", "show me a photo of", "show me an image of", "show me picture of", "picture of ", "photo of ", "image of ", "diagram of ", "draw ", "generate image"];
      if (imgTriggers.some(t => lowerQ.startsWith(t))) {
        executeImageSearch(query);
        return;
      }

      setProcessingState(true);
      queryInput.value = '';
      queryInput.style.height = 'auto';

      addMessageRow('user', query);

      // Create streaming placeholder card matching Assistant design
      hideHeroIfVisible();
      const timeStr = formatCurrentTime();
      const streamCard = document.createElement('div');
      streamCard.className = 'chat-message-card ai';
      streamCard.innerHTML = `
        <div class="card-top-bar">
          <div class="card-top-left">
            <span class="card-avatar">⚡ Assistant</span>
            <span class="card-timestamp">${escapeHtml(timeStr)}</span>
          </div>
          <div class="card-top-right" id="active-stream-actions" style="display: none;">
            <button class="card-action-btn" onclick="copyMessage(this)">📋 Copy All</button>
            <button class="card-action-btn" onclick="speakMessage(this)">🔊 Speak</button>
          </div>
        </div>
        <div class="card-content" id="active-stream-content">Thinking...</div>
      `;
      chatViewport.appendChild(streamCard);
      chatViewport.scrollTop = chatViewport.scrollHeight;

      const streamContent = document.getElementById('active-stream-content');
      let streamedTokens = "";
      let collectedCitations = [];

      try {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: query,
            mode: modeSelect.value,
            model: modelSelect.value,
            depth: parseInt(depthSlider.value)
          })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Generation error");

        streamedTokens = data.answer || "No response generated.";
        collectedCitations = data.citations || [];

        streamContent.innerHTML = marked.parse(streamedTokens);
        enhanceCodeBlocks(streamCard);
        document.getElementById('active-stream-actions').style.display = 'flex';

        currentMessages.push({ role: 'ai', content: streamedTokens, timestamp: timeStr, citations: collectedCitations });

        if (autoTtsEnabled) {
          speakCleanText(streamedTokens);
        }
      } catch (err) {
        streamContent.innerHTML = `<span style="color: var(--accent-danger);">⚠️ Error: ${escapeHtml(err.message)}</span>`;
      } finally {
        streamContent.removeAttribute('id');
        const act = document.getElementById('active-stream-actions');
        if (act) act.removeAttribute('id');
        finishProcessingState();
      }
    }

    // 10. WEB IMAGE SEARCH DISPATCHER
    async function executeImageSearch(query) {
      setProcessingState(true);
      queryInput.value = '';
      queryInput.style.height = 'auto';

      addMessageRow('user', query);

      hideHeroIfVisible();
      const timeStr = formatCurrentTime();
      const imgCard = document.createElement('div');
      imgCard.className = 'chat-message-card ai';
      imgCard.innerHTML = `
        <div class="card-top-bar">
          <div class="card-top-left">
            <span class="card-avatar">⚡ Assistant</span>
            <span class="card-timestamp">${escapeHtml(timeStr)}</span>
          </div>
          <div class="card-top-right" id="active-image-actions" style="display: none;">
            <button class="card-action-btn" onclick="copyMessage(this)">📋 Copy</button>
          </div>
        </div>
        <div class="card-content" id="active-image-search-content">
          <span style="display: flex; align-items: center; gap: 8px; color: var(--text-secondary);">
            <span>🔍</span> Searching web & knowledge sources for image...
          </span>
        </div>
      `;
      chatViewport.appendChild(imgCard);
      chatViewport.scrollTop = chatViewport.scrollHeight;

      try {
        const res = await fetch('/api/search-image', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: query })
        });
        const data = await res.json();
        const contentEl = document.getElementById('active-image-search-content');
        if (!contentEl) return;

        if (data && data.image_url) {
          contentEl.innerHTML = `
            <p>Here is the image found for <strong>${escapeHtml(query)}</strong>:</p>
            <div class="chat-embedded-image-container" onclick="openImagePreviewModal('${escapeHtml(data.image_url)}', '${escapeHtml(query)}')">
              <img src="${data.image_url}" alt="${escapeHtml(query)}" class="chat-embedded-image" loading="lazy">
              <div class="chat-image-caption">
                <span>🖼️ ${escapeHtml(query)}</span>
                <span>🔍 Click to expand</span>
              </div>
            </div>
          `;
          const act = document.getElementById('active-image-actions');
          if (act) act.style.display = 'flex';

          currentMessages.push({
            role: 'ai',
            content: `Here is the image found for **${query}**:\n\n![${query}](${data.image_url})`,
            timestamp: timeStr,
            citations: []
          });
        } else {
          contentEl.innerHTML = `<span style="color: var(--text-secondary);">⚠️ ${escapeHtml(data.error || "No suitable image found for this query.")}</span>`;
          currentMessages.push({
            role: 'ai',
            content: `⚠️ ${data.error || "No suitable image found."}`,
            timestamp: timeStr,
            citations: []
          });
        }
      } catch (err) {
        const contentEl = document.getElementById('active-image-search-content');
        if (contentEl) {
          contentEl.innerHTML = `<span style="color: var(--accent-danger);">❌ Image search error: ${escapeHtml(err.message)}</span>`;
        }
      } finally {
        const contentEl = document.getElementById('active-image-search-content');
        if (contentEl) contentEl.removeAttribute('id');
        const act = document.getElementById('active-image-actions');
        if (act) act.removeAttribute('id');
        finishProcessingState();
      }
    }

    function openImagePreviewModal(url, title) {
      const modal = document.getElementById('image-modal');
      const img = document.getElementById('modal-preview-img');
      if (!modal || !img) return;
      img.src = url;
      const titleEl = modal.querySelector('.modal-title');
      if (titleEl) titleEl.textContent = title ? `🖼️ ${title}` : '🖼️ Image Preview';
      modal.classList.add('active');
    }

    function saveActiveImage() {
      const img = document.getElementById('modal-preview-img');
      if (!img || !img.src) return;
      const a = document.createElement('a');
      a.href = img.src;
      a.download = 'search-studio-image.jpg';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }

    // 11. MULTIMODAL PIXTRAL IMAGE ANALYSIS
    async function sendImageAnalysis(promptText) {
      if (!attachedImageFile) return;

      setProcessingState(true);
      const photoFile = attachedImageFile;
      removeAttachedPhoto();

      let photoThumbnailHtml = '';
      try {
        const tempUrl = URL.createObjectURL(photoFile);
        photoThumbnailHtml = `<br><img src="${tempUrl}" style="max-height: 200px; max-width: 100%; border-radius: 8px; margin-top: 8px; border: 1px solid var(--border-color); display: block;" />`;
      } catch (e) {}

      addMessageRow('user', `🖼️ **[Attached Photo: ${escapeHtml(photoFile.name)}]**${photoThumbnailHtml}\n\n${escapeHtml(promptText)}`);

      const formData = new FormData();
      formData.append('file', photoFile);
      formData.append('prompt', promptText);

      try {
        const res = await fetch('/api/analyze-image', { method: 'POST', body: formData });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Image analysis failed");

        addMessageRow('ai', data.answer);
        if (autoTtsEnabled) speakCleanText(data.answer);
      } catch (err) {
        addMessageRow('ai', `⚠️ Image reasoning notice: ${err.message}`);
      } finally {
        finishProcessingState();
      }
    }

    // 11. VOICE SPEECH-TO-TEXT (STT) & TEXT-TO-SPEECH (TTS)
    function toggleVoiceSTT() {
      const micBtn = document.getElementById('mic-toggle-btn');
      const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;

      if (!SpeechRec) {
        alert("Speech Recognition is not supported by your current browser. Please use Chrome, Edge, or Safari.");
        return;
      }

      if (isRecordingVoice) {
        if (recognitionInstance) recognitionInstance.stop();
        return;
      }

      recognitionInstance = new SpeechRec();
      recognitionInstance.lang = 'en-US';
      recognitionInstance.interimResults = false;

      recognitionInstance.onstart = () => {
        isRecordingVoice = true;
        micBtn.classList.add('recording');
        setStatus("🎙️ Listening... Speak now", "warning");
      };

      recognitionInstance.onresult = (e) => {
        const transcript = e.results[0][0].transcript;
        queryInput.value = (queryInput.value ? queryInput.value + " " : "") + transcript;
        autoGrowInput(queryInput);
      };

      recognitionInstance.onerror = (e) => {
        console.warn("Speech recognition error:", e.error);
        setStatus("Voice timeout", "warning");
      };

      recognitionInstance.onend = () => {
        isRecordingVoice = false;
        micBtn.classList.remove('recording');
        setStatus("Ready", "success");
      };

      recognitionInstance.start();
    }

    function speakCleanText(rawText) {
      if (!('speechSynthesis' in window)) return;
      window.speechSynthesis.cancel();

      // Clean code blocks, URLs, markdown
      let clean = rawText.replace(/```[\s\S]*?```/g, 'code block omitted.');
      clean = clean.replace(/[*#_`~>•\-]/g, ' ');
      clean = clean.replace(/http\S+/g, '');
      clean = clean.trim();
      if (!clean) return;

      const utterance = new SpeechSynthesisUtterance(clean.slice(0, 1200));
      utterance.rate = 1.0;
      utterance.pitch = 1.0;

      const voices = window.speechSynthesis.getVoices();
      const naturalVoice = voices.find(v => v.lang.startsWith('en') && (v.name.includes('Natural') || v.name.includes('Neural') || v.name.includes('Female')));
      if (naturalVoice) utterance.voice = naturalVoice;

      window.speechSynthesis.speak(utterance);
    }

    function speakMessage(btn) {
      const card = btn.closest('.chat-message-card') || btn.closest('.msg-body-wrapper');
      const content = card ? (card.querySelector('.card-content') || card.querySelector('.msg-bubble')) : null;
      if (content) speakCleanText(content.innerText);
    }

    function copyMessage(btn) {
      const card = btn.closest('.chat-message-card') || btn.closest('.msg-body-wrapper');
      const content = card ? (card.querySelector('.card-content') || card.querySelector('.msg-bubble')) : null;
      if (content) {
        navigator.clipboard.writeText(content.innerText);
        const prev = btn.textContent;
        btn.textContent = '✅ Copied!';
        setTimeout(() => { btn.textContent = prev; }, 1500);
      }
    }

    // 12. SESSIONS & HISTORY MODAL
    async function openHistoryModal() {
      document.getElementById('history-modal').classList.add('open');
      const container = document.getElementById('session-items-list');
      try {
        const res = await fetch('/api/sessions');
        const sessions = await res.json();
        if (!sessions.length) {
          container.innerHTML = `<div style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 20px 0;">No conversation history yet.</div>`;
          return;
        }
        container.innerHTML = sessions.map(s => `
          <div class="session-item-card" onclick="loadSession('${escapeHtml(s.id)}')">
            <div>
              <div class="session-title-text">${escapeHtml(s.title || 'Untitled Session')}</div>
              <div class="session-date-sub">${s.updated_at ? new Date(s.updated_at).toLocaleString() : ''} • ${s.messages ? s.messages.length : 0} msgs</div>
            </div>
            <button class="source-del-btn" onclick="deleteSession(event, '${escapeHtml(s.id)}')">🗑️</button>
          </div>
        `).join('');
      } catch (err) {
        container.innerHTML = `<div style="color: var(--accent-danger); font-size: 11px;">Failed loading history: ${err.message}</div>`;
      }
    }

    async function loadSession(id) {
      try {
        const res = await fetch(`/api/sessions/${id}`);
        const data = await res.json();
        currentSessionId = data.id;
        currentMessages = [];
        chatViewport.innerHTML = '';

        if (data.messages && data.messages.length) {
          data.messages.forEach(m => addMessageRow(m.role, m.content, m.citations || [], m.timestamp));
        } else {
          showHeroCard();
        }
        closeModal('history-modal');
      } catch (err) {
        alert("Could not load session: " + err.message);
      }
    }

    async function deleteSession(event, id) {
      event.stopPropagation();
      if (!confirm("Delete this conversation?")) return;
      try {
        await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
        openHistoryModal();
      } catch (err) {
        alert("Failed deleting session: " + err.message);
      }
    }

    function createNewSession() {
      currentSessionId = 'session_' + Date.now();
      currentMessages = [];
      chatViewport.innerHTML = '';
      showHeroCard();
      closeModal('history-modal');
    }

    async function saveCurrentSession() {
      if (!currentMessages.length) return;
      try {
        await fetch('/api/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: currentSessionId,
            messages: currentMessages
          })
        });
      } catch (e) {
        console.warn('Session save notice:', e);
      }
    }

    function clearCurrentChat() {
      currentMessages = [];
      chatViewport.innerHTML = '';
      showHeroCard();
      if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    }

    function showHeroCard() {
      chatViewport.innerHTML = `
        <div class="hero-container" id="hero-welcome-card">
          <div class="hero-title">✨ Welcome to Search Studio</div>
          <div class="hero-subtitle">
            Your multi-modal RAG knowledge engine. Ask questions from your PDFs, Word documents,<br>code, spreadsheets, or query live web intelligence with voice & image support.
          </div>
          <div class="hero-grid">
            <div class="feature-card">
              <div class="feature-card-header">📄 Multi-Format Uploads</div>
              <div class="feature-card-desc">PDF, Word (DOCX), CSV, Excel, TXT, Code & OCR</div>
            </div>
            <div class="feature-card">
              <div class="feature-card-header">⚡ Real-Time Streaming</div>
              <div class="feature-card-desc">Instant token generation powered by Mistral AI</div>
            </div>
            <div class="feature-card">
              <div class="feature-card-header">🎙️ Two-Way Voice</div>
              <div class="feature-card-desc">Speech-to-text input and natural voice read-aloud</div>
            </div>
            <div class="feature-card">
              <div class="feature-card-header">🌐 Live Web & Images</div>
              <div class="feature-card-desc">Automatic search fallbacks and inline image discovery</div>
            </div>
          </div>
        </div>
      `;
    }

    // 13. EXPORT MODAL
    function openExportModal() {
      document.getElementById('export-modal').classList.add('open');
    }

    function downloadExport(format) {
      if (!currentMessages.length) {
        alert("No chat messages to export yet.");
        return;
      }

      let content = "";
      let filename = `search_studio_${Date.now()}`;
      let mime = "text/plain";

      if (format === 'markdown') {
        filename += ".md";
        mime = "text/markdown";
        content = `# Search Studio Conversation\nExported: ${new Date().toLocaleString()}\n\n---\n\n`;
        currentMessages.forEach(m => {
          content += `### ${m.role === 'ai' ? '🧠 AI Search Studio' : '👤 User'}\n\n${m.content}\n\n`;
          if (m.citations && m.citations.length) {
            content += `**Citations:** ${m.citations.join(', ')}\n\n`;
          }
          content += `---\n\n`;
        });
      } else if (format === 'json') {
        filename += ".json";
        mime = "application/json";
        content = JSON.stringify({ session_id: currentSessionId, messages: currentMessages }, null, 2);
      } else {
        filename += ".txt";
        currentMessages.forEach(m => {
          content += `[${m.role.toUpperCase()}]: ${m.content}\n\n`;
        });
      }

      const blob = new Blob([content], { type: mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      closeModal('export-modal');
    }

    // 14. MODAL UTILITIES
    function openStatsModal() {
      document.getElementById('stats-modal').classList.add('open');
    }

    function closeModal(id) {
      document.getElementById(id).classList.remove('open');
    }

    function closeModalOnBackdrop(e, id) {
      if (e.target.id === id) closeModal(id);
    }

    function escapeHtml(text) {
      return String(text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }
  </script>
</body>
</html>
"""
