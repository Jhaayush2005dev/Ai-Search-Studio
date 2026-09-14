import os
import shutil
import logging
from pathlib import Path
from threading import Lock
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.config import (
    DOCS_DIR, CHROMA_DIR, MISTRAL_API_KEY, AVAILABLE_MODELS, DEFAULT_MODEL,
    SUPPORTED_EXTENSIONS
)
from core.doc_loader import UniversalDocumentLoader
from core.rag_engine import RAGEngine

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="AI Search Studio", version="2.0.0")

# Mount static folder
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Shared singletons
_doc_loader = UniversalDocumentLoader()
_engine = RAGEngine(api_key=MISTRAL_API_KEY)
_engine_lock = Lock()


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=5000)
    mode: Optional[str] = "Auto (Hybrid)"
    model: Optional[str] = DEFAULT_MODEL
    temperature: Optional[float] = 0.3


class ChatResponse(BaseModel):
    answer: str
    citations: list[str]
    status: str = "ok"


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
    return {"status": "ok", "app": "AI Search Studio"}


# ==========================================
# CONFIG & STATS ENDPOINTS
# ==========================================
@app.get("/api/config")
def get_config():
    has_key = bool(_engine.api_key or os.getenv("MISTRAL_API_KEY"))
    stats = _engine.get_knowledge_stats()
    return {
        "has_api_key": has_key,
        "current_model": _engine.model_name,
        "available_models": AVAILABLE_MODELS,
        "current_mode": _engine.search_mode,
        "available_modes": ["Auto (Hybrid)", "Docs Only", "Web Only"],
        "knowledge_stats": stats,
        "supported_extensions": list(SUPPORTED_EXTENSIONS.keys())
    }


# ==========================================
# DOCUMENT UPLOAD & MANAGEMENT ENDPOINTS
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
        # Also remove physical file if present
        target_file = DOCS_DIR / filename
        if target_file.exists():
            try:
                target_file.unlink()
            except Exception:
                pass
        return {"status": "success" if success else "failed", "filename": filename}


@app.delete("/api/documents")
def clear_all_documents():
    with _engine_lock:
        success = _engine.clear_knowledge_base()
        # Clean folder
        for item in DOCS_DIR.iterdir():
            if item.is_file():
                try:
                    item.unlink()
                except Exception:
                    pass
        return {"status": "success" if success else "failed"}


# ==========================================
# CHAT ENDPOINT
# ==========================================
@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    current_key = _engine.api_key or os.getenv("MISTRAL_API_KEY", "")
    if not current_key:
        raise HTTPException(
            status_code=500,
            detail="MISTRAL_API_KEY environment variable is not configured on server."
        )

    with _engine_lock:
        if not _engine.api_key:
            _engine.api_key = current_key
            _engine._init_models()

        if request.model and request.model != _engine.model_name:
            _engine.set_model(request.model)

        if request.mode:
            _engine.set_search_mode(request.mode)

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


# ==========================================
# MAIN RESPONSIVE WEB & MOBILE UI
# ==========================================
@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return HTML_PAGE


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>AI Search Studio</title>
  <meta name="description" content="Intelligent Universal Document & Hybrid Web Search Studio">

  <!-- PWA & Mobile Meta -->
  <link rel="manifest" href="/manifest.json">
  <meta name="theme-color" content="#0d1117">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="AI Search">
  <link rel="icon" type="image/png" href="/static/icon-192.png">
  <link rel="apple-touch-icon" href="/static/icon-192.png">

  <!-- Markdown & Code Highlight -->
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>

  <style>
    :root {
      --bg-base: #0d1117;
      --bg-surface: #161b22;
      --bg-card: #21262d;
      --bg-input: #1e242c;
      --border-subtle: #30363d;
      --border-focus: #58a6ff;
      --accent-primary: #38bdf8;
      --accent-hover: #0284c7;
      --accent-success: #3fb950;
      --accent-warning: #d29922;
      --accent-danger: #f85149;
      --text-main: #f0f6fc;
      --text-muted: #8b949e;
      --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
    body {
      background-color: var(--bg-base);
      color: var(--text-main);
      font-family: var(--font-family);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      overflow-x: hidden;
    }

    /* App Shell Container */
    #app-container {
      display: flex;
      flex: 1;
      height: 100vh;
      overflow: hidden;
      position: relative;
    }

    /* Sidebar (Desktop Persistent, Mobile Drawer) */
    #sidebar {
      width: 320px;
      background: var(--bg-surface);
      border-right: 1px solid var(--border-subtle);
      display: flex;
      flex-direction: column;
      transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      z-index: 100;
    }

    /* Mobile Sidebar overlay */
    @media (max-width: 768px) {
      #sidebar {
        position: fixed;
        top: 0;
        bottom: 0;
        left: 0;
        width: 86vw;
        max-width: 340px;
        transform: translateX(-100%);
        box-shadow: 4px 0 24px rgba(0,0,0,0.6);
      }
      #sidebar.open {
        transform: translateX(0);
      }
    }

    #drawer-backdrop {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.6);
      z-index: 99;
      backdrop-filter: blur(2px);
    }
    #drawer-backdrop.active { display: block; }

    .sidebar-header {
      padding: 16px;
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .logo-area { display: flex; align-items: center; gap: 10px; }
    .logo-badge {
      width: 34px;
      height: 34px;
      border-radius: 8px;
      background: linear-gradient(135deg, #0284c7, #38bdf8);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
    }
    .logo-title { font-size: 16px; font-weight: 700; letter-spacing: -0.02em; }
    .logo-subtitle { font-size: 11px; color: var(--text-muted); }

    .sidebar-scroll {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    .section-title {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-muted);
      font-weight: 700;
      margin-bottom: 8px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    /* Upload Box */
    .upload-dropzone {
      border: 2px dashed var(--border-subtle);
      border-radius: 10px;
      padding: 16px;
      text-align: center;
      cursor: pointer;
      background: var(--bg-base);
      transition: all 0.2s ease;
    }
    .upload-dropzone:hover, .upload-dropzone.dragover {
      border-color: var(--accent-primary);
      background: rgba(56, 189, 248, 0.05);
    }
    .upload-icon { font-size: 24px; margin-bottom: 6px; }
    .upload-text { font-size: 13px; font-weight: 600; }
    .upload-sub { font-size: 11px; color: var(--text-muted); margin-top: 2px; }

    /* Sources List */
    .sources-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-height: 220px;
      overflow-y: auto;
    }
    .source-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 12px;
      background: var(--bg-card);
      border-radius: 8px;
      border: 1px solid var(--border-subtle);
      font-size: 12px;
    }
    .source-info { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; padding-right: 8px; }
    .source-meta { font-size: 10px; color: var(--text-muted); margin-top: 2px; }
    .delete-source-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      padding: 4px;
      border-radius: 4px;
      font-size: 14px;
    }
    .delete-source-btn:hover { color: var(--accent-danger); }

    /* Select & Input Controls */
    .select-control {
      width: 100%;
      background: var(--bg-card);
      color: var(--text-main);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 13px;
      font-family: inherit;
      outline: none;
    }
    .select-control:focus { border-color: var(--border-focus); }

    /* Main Chat Feed Area */
    #main-panel {
      flex: 1;
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
      position: relative;
    }

    /* Top Navigation Bar */
    .top-navbar {
      height: 54px;
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
      z-index: 10;
    }
    .nav-left { display: flex; align-items: center; gap: 12px; }
    .icon-btn {
      background: transparent;
      border: 1px solid var(--border-subtle);
      color: var(--text-main);
      width: 36px;
      height: 36px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      font-size: 16px;
      transition: background 0.2s;
    }
    .icon-btn:hover { background: var(--bg-card); }
    .status-pill {
      font-size: 12px;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 20px;
      background: rgba(63, 185, 80, 0.15);
      color: var(--accent-success);
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .status-pill.warning {
      background: rgba(210, 153, 34, 0.15);
      color: var(--accent-warning);
    }
    .status-pill::before {
      content: "";
      display: inline-block;
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: currentColor;
    }

    /* Chat Messages Viewport */
    #messages-container {
      flex: 1;
      overflow-y: auto;
      padding: 16px 20px 24px;
      display: flex;
      flex-direction: column;
      gap: 18px;
      scroll-behavior: smooth;
    }

    .message-card {
      display: flex;
      gap: 12px;
      max-width: 880px;
      width: 100%;
      margin: 0 auto;
      animation: fadeIn 0.25s ease;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .msg-avatar {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 15px;
      flex-shrink: 0;
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
    }
    .msg-avatar.ai {
      background: linear-gradient(135deg, #0284c7, #38bdf8);
      color: #fff;
    }

    .msg-content-wrapper {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 6px;
      min-width: 0;
    }
    .msg-author {
      font-size: 12px;
      font-weight: 700;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .msg-bubble {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 14px 16px;
      font-size: 14px;
      line-height: 1.6;
      word-wrap: break-word;
    }
    .message-card.user .msg-bubble {
      background: #1f3044;
      border-color: #2b4562;
    }

    /* Citations List */
    .citations-box {
      margin-top: 8px;
      padding: 8px 12px;
      border-radius: 8px;
      background: rgba(0,0,0,0.25);
      border-left: 3px solid var(--accent-primary);
      font-size: 12px;
    }
    .citations-title { font-weight: 700; color: var(--accent-primary); margin-bottom: 4px; font-size: 11px; }
    .citations-tags { display: flex; flex-wrap: wrap; gap: 6px; }
    .citation-tag {
      padding: 2px 8px;
      border-radius: 4px;
      background: var(--bg-surface);
      color: var(--text-muted);
      font-size: 11px;
      border: 1px solid var(--border-subtle);
    }

    /* Message Action Buttons */
    .msg-actions {
      display: flex;
      gap: 8px;
      margin-top: 4px;
    }
    .msg-action-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      font-size: 12px;
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 2px 6px;
      border-radius: 4px;
    }
    .msg-action-btn:hover {
      background: var(--bg-card);
      color: var(--text-main);
    }

    /* Markdown Elements Styling */
    .msg-bubble p { margin-bottom: 8px; }
    .msg-bubble p:last-child { margin-bottom: 0; }
    .msg-bubble code {
      background: #11161d;
      padding: 2px 5px;
      border-radius: 4px;
      font-family: monospace;
      font-size: 12px;
      color: #79c0ff;
    }
    .msg-bubble pre {
      background: #11161d;
      padding: 12px;
      border-radius: 8px;
      overflow-x: auto;
      margin: 8px 0;
      border: 1px solid var(--border-subtle);
    }
    .msg-bubble pre code { background: transparent; padding: 0; }

    /* Quick Chips Carousel */
    .chips-bar {
      max-width: 880px;
      width: 100%;
      margin: 0 auto;
      padding: 0 16px;
      display: flex;
      gap: 8px;
      overflow-x: auto;
      scrollbar-width: none;
      -ms-overflow-style: none;
      padding-bottom: 6px;
    }
    .chips-bar::-webkit-scrollbar { display: none; }
    .chip-btn {
      white-space: nowrap;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      color: var(--text-main);
      padding: 6px 12px;
      border-radius: 18px;
      font-size: 12px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
      flex-shrink: 0;
    }
    .chip-btn:hover {
      background: var(--bg-card);
      border-color: var(--accent-primary);
    }

    /* Bottom Sticky Input Container */
    .input-wrapper {
      background: var(--bg-surface);
      border-top: 1px solid var(--border-subtle);
      padding: 12px 16px 16px;
    }
    .input-box {
      max-width: 880px;
      width: 100%;
      margin: 0 auto;
      background: var(--bg-input);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      padding: 6px 12px;
      display: flex;
      align-items: flex-end;
      gap: 8px;
      transition: border-color 0.2s;
    }
    .input-box:focus-within { border-color: var(--border-focus); }

    .input-textarea {
      flex: 1;
      background: transparent;
      border: none;
      color: var(--text-main);
      font-family: inherit;
      font-size: 14px;
      resize: none;
      max-height: 120px;
      min-height: 24px;
      padding: 6px 0;
      outline: none;
      line-height: 1.4;
    }

    .mic-btn {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
      transition: all 0.2s;
      flex-shrink: 0;
    }
    .mic-btn:hover { color: var(--text-main); background: var(--bg-card); }
    .mic-btn.listening {
      background: var(--accent-danger);
      color: white;
      animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(1); opacity: 1; }
      50% { transform: scale(1.15); opacity: 0.85; }
      100% { transform: scale(1); opacity: 1; }
    }

    .send-btn {
      width: 36px;
      height: 36px;
      border-radius: 10px;
      background: var(--accent-primary);
      color: #0d1117;
      border: none;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      font-weight: 700;
      font-size: 16px;
      transition: background 0.2s;
      flex-shrink: 0;
    }
    .send-btn:hover { background: var(--accent-hover); }
    .send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

    /* Install Banner */
    #install-banner {
      display: none;
      background: linear-gradient(90deg, #1f2937, #111827);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 10px 14px;
      margin-bottom: 12px;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }
    .install-text { font-size: 12px; font-weight: 600; }
    .install-action {
      background: var(--accent-primary);
      color: #0d1117;
      border: none;
      border-radius: 6px;
      padding: 5px 10px;
      font-size: 11px;
      font-weight: 700;
      cursor: pointer;
    }

    /* Modal */
    .modal-backdrop {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.7);
      z-index: 200;
      backdrop-filter: blur(4px);
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .modal-backdrop.open { display: flex; }
    .modal-box {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 14px;
      width: 100%;
      max-width: 480px;
      max-height: 85vh;
      overflow-y: auto;
      padding: 20px;
      box-shadow: 0 12px 32px rgba(0,0,0,0.6);
    }
    .modal-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
    }
  </style>
</head>
<body>

  <!-- App Shell -->
  <div id="app-container">
    <!-- Dim Backdrop for Mobile Drawer -->
    <div id="drawer-backdrop" onclick="toggleSidebar(false)"></div>

    <!-- Sidebar -->
    <aside id="sidebar">
      <div class="sidebar-header">
        <div class="logo-area">
          <div class="logo-badge">🔍</div>
          <div>
            <div class="logo-title">AI Search Studio</div>
            <div class="logo-subtitle">Universal Hybrid Assistant</div>
          </div>
        </div>
        <button class="icon-btn" onclick="toggleSidebar(false)" style="display: none;" id="sidebar-close-btn">✕</button>
      </div>

      <div class="sidebar-scroll">
        <!-- PWA Install Card if available -->
        <div id="install-banner">
          <div>
            <div class="install-text">📲 Install App</div>
            <div style="font-size: 10px; color: var(--text-muted);">Use full screen without browser bars</div>
          </div>
          <button class="install-action" id="pwa-install-btn">Install</button>
        </div>

        <!-- Mode Selector -->
        <div>
          <div class="section-title">Search Mode</div>
          <select id="mode-select" class="select-control" onchange="onModeChange()">
            <option value="Auto (Hybrid)">🔄 Auto (Hybrid Search)</option>
            <option value="Docs Only">📄 Knowledge Docs Only</option>
            <option value="Web Only">🌐 Live Web Search Only</option>
          </select>
        </div>

        <!-- Model Selector -->
        <div>
          <div class="section-title">AI Model</div>
          <select id="model-select" class="select-control" onchange="onModelChange()">
            <option value="open-mistral-7b">Mistral 7B (Fast)</option>
            <option value="mistral-small-latest">Mistral Small</option>
            <option value="mistral-medium-latest">Mistral Medium</option>
            <option value="mistral-large-latest">Mistral Large (Smartest)</option>
            <option value="codestral-latest">Codestral (Code)</option>
          </select>
        </div>

        <!-- Upload Zone -->
        <div>
          <div class="section-title">Knowledge Base</div>
          <input type="file" id="file-input" multiple style="display: none;" onchange="handleFileSelect(event)" accept=".pdf,.docx,.csv,.xlsx,.txt,.md,.py,.js,.json,.png,.jpg">
          <div class="upload-dropzone" onclick="document.getElementById('file-input').click()" id="dropzone">
            <div class="upload-icon">📥</div>
            <div class="upload-text">Upload Documents</div>
            <div class="upload-sub">PDF, Word, CSV, TXT, Code, Images</div>
          </div>
        </div>

        <!-- Indexed Documents -->
        <div>
          <div class="section-title">
            <span>Indexed Files</span>
            <button class="delete-source-btn" onclick="clearAllDocs()" title="Clear All Files">🧹 Clear</button>
          </div>
          <div id="sources-list" class="sources-list">
            <div style="font-size: 12px; color: var(--text-muted); text-align: center; padding: 12px 0;">No documents uploaded yet.</div>
          </div>
        </div>
      </div>
    </aside>

    <!-- Main Chat Workspace -->
    <main id="main-panel">
      <!-- Top Navbar -->
      <header class="top-navbar">
        <div class="nav-left">
          <button class="icon-btn" id="mobile-menu-btn" onclick="toggleSidebar(true)" title="Menu">☰</button>
          <div class="status-pill" id="status-pill">Ready</div>
        </div>
        <div style="display: flex; gap: 8px;">
          <button class="icon-btn" onclick="clearChat()" title="Clear Chat">🧹</button>
          <button class="icon-btn" onclick="toggleSidebar(true)" title="Knowledge Base & Settings">⚙️</button>
        </div>
      </header>

      <!-- Messages View -->
      <section id="messages-container">
        <div class="message-card ai">
          <div class="msg-avatar ai">⚡</div>
          <div class="msg-content-wrapper">
            <div class="msg-author">AI Search Studio</div>
            <div class="msg-bubble">
              👋 Welcome! I am your <strong>Universal Search & Knowledge Assistant</strong>.<br><br>
              • 📂 <strong>Upload documents</strong> (PDF, Word, Code, Data) in the menu to search private knowledge.<br>
              • 🌐 <strong>Live DuckDuckGo search</strong> automatically kicks in for up-to-date web queries.<br>
              • 🎙️ Tap the <strong>Microphone</strong> to ask by voice on both laptop and mobile phone.<br>
              • 📲 Tap <strong>Install App</strong> in settings to install this on your home screen!
            </div>
          </div>
        </div>
      </section>

      <!-- Quick Chips Bar -->
      <div class="chips-bar">
        <button class="chip-btn" onclick="sendQuickPrompt('Summarize the uploaded documents with key takeaways and bullet points.')">📝 Summarize Docs</button>
        <button class="chip-btn" onclick="sendQuickPrompt('Create 5 practice quiz questions based on the uploaded knowledge base.')">🎯 Practice Quiz</button>
        <button class="chip-btn" onclick="sendQuickPrompt('What are the key insights and actionable highlights in these documents?')">💡 Key Insights</button>
        <button class="chip-btn" onclick="setModeAndNotify('Web Only')">🌐 Web Mode</button>
        <button class="chip-btn" onclick="setModeAndNotify('Docs Only')">📄 Docs Mode</button>
        <button class="chip-btn" onclick="setModeAndNotify('Auto (Hybrid)')">🔄 Auto Mode</button>
      </div>

      <!-- Bottom Chat Input -->
      <div class="input-wrapper">
        <div class="input-box">
          <button class="icon-btn" style="border:none; width:32px; height:32px; margin-bottom: 2px;" onclick="document.getElementById('file-input').click()" title="Attach Document">📎</button>
          <textarea id="user-input" class="input-textarea" placeholder="Ask anything about your documents or search the web..." rows="1" onkeydown="handleKeyDown(event)" oninput="autoGrow(this)"></textarea>
          <button id="mic-btn" class="mic-btn" onclick="toggleSpeechRecognition()" title="Voice Input">🎙️</button>
          <button id="send-btn" class="send-btn" onclick="sendMessage()" title="Send">➤</button>
        </div>
      </div>
    </main>
  </div>

  <script>
    // State
    let isGenerating = false;
    let deferredInstallPrompt = null;
    let recognition = null;
    let isListening = false;

    // Elements
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('drawer-backdrop');
    const messagesContainer = document.getElementById('messages-container');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const micBtn = document.getElementById('mic-btn');
    const statusPill = document.getElementById('status-pill');
    const modeSelect = document.getElementById('mode-select');
    const modelSelect = document.getElementById('model-select');
    const sourcesList = document.getElementById('sources-list');
    const installBanner = document.getElementById('install-banner');
    const pwaInstallBtn = document.getElementById('pwa-install-btn');

    // Register Service Worker for PWA
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
          .then(reg => console.log('PWA Service Worker registered:', reg.scope))
          .catch(err => console.log('PWA registration failed:', err));
      });
    }

    // Capture PWA Install Prompt
    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      deferredInstallPrompt = e;
      installBanner.style.display = 'flex';
    });

    pwaInstallBtn.addEventListener('click', async () => {
      if (deferredInstallPrompt) {
        deferredInstallPrompt.prompt();
        const { outcome } = await deferredInstallPrompt.userChoice;
        if (outcome === 'accepted') {
          installBanner.style.display = 'none';
        }
        deferredInstallPrompt = null;
      } else {
        alert('To install on iOS: Tap the Share button (square with arrow) and select "Add to Home Screen".');
      }
    });

    // Mobile Sidebar Drawer
    function toggleSidebar(open) {
      if (open) {
        sidebar.classList.add('open');
        backdrop.classList.add('active');
        document.getElementById('sidebar-close-btn').style.display = 'block';
      } else {
        sidebar.classList.remove('open');
        backdrop.classList.remove('active');
        document.getElementById('sidebar-close-btn').style.display = 'none';
      }
    }

    // Auto-grow textarea
    function autoGrow(el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    }

    function handleKeyDown(event) {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
      }
    }

    // Update Status Pill
    function setStatus(text, type = 'success') {
      statusPill.textContent = text;
      statusPill.className = 'status-pill' + (type === 'warning' ? ' warning' : '');
    }

    // Load initial config and documents
    async function loadAppConfig() {
      try {
        const res = await fetch('/api/config');
        const data = await res.json();
        if (data.knowledge_stats) {
          renderSources(data.knowledge_stats);
        }
        if (!data.has_api_key) {
          setStatus('API Key Required', 'warning');
        }
      } catch (err) {
        console.error('Failed to load initial config:', err);
      }
    }
    loadAppConfig();

    // Render Sources List
    function renderSources(stats) {
      const sources = stats.sources || [];
      if (sources.length === 0) {
        sourcesList.innerHTML = '<div style="font-size: 12px; color: var(--text-muted); text-align: center; padding: 12px 0;">No documents uploaded yet.</div>';
        return;
      }
      sourcesList.innerHTML = sources.map(s => `
        <div class="source-item">
          <div class="source-info">
            <div style="font-weight:600;">${escapeHtml(s.filename)}</div>
            <div class="source-meta">${s.chunks} chunks • ${s.size_kb} KB</div>
          </div>
          <button class="delete-source-btn" onclick="deleteSource('${escapeHtml(s.filename)}')">✕</button>
        </div>
      `).join('');
    }

    async function deleteSource(filename) {
      if (!confirm(`Delete ${filename}?`)) return;
      try {
        const res = await fetch(`/api/documents/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        if (res.ok) {
          loadAppConfig();
        }
      } catch (err) {
        alert('Delete failed: ' + err.message);
      }
    }

    async function clearAllDocs() {
      if (!confirm('Clear all indexed documents?')) return;
      try {
        await fetch('/api/documents', { method: 'DELETE' });
        loadAppConfig();
      } catch (err) {
        alert('Clear failed: ' + err.message);
      }
    }

    // File Upload Handler
    async function handleFileSelect(event) {
      const files = event.target.files;
      if (!files.length) return;

      const formData = new FormData();
      for (const f of files) {
        formData.append('files', f);
      }

      setStatus('Indexing Documents...', 'warning');
      try {
        const res = await fetch('/api/upload', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Upload failed');
        renderSources(data.knowledge_stats);
        setStatus(`Ready (${data.knowledge_stats.total_chunks} chunks)`, 'success');
        addMessage('system', `✅ Successfully indexed ${data.files_indexed} file(s) with ${data.chunks_created} chunks into your knowledge base.`);
      } catch (err) {
        setStatus('Upload Failed', 'warning');
        alert('Upload failed: ' + err.message);
      } finally {
        event.target.value = '';
      }
    }

    // Drag and Drop Upload Support
    const dropzone = document.getElementById('dropzone');
    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      if (e.dataTransfer.files.length) {
        handleFileSelect({ target: { files: e.dataTransfer.files, value: '' } });
      }
    });

    // Chat Message Handlers
    function addMessage(role, text, citations = []) {
      const card = document.createElement('div');
      card.className = `message-card ${role}`;

      const avatar = role === 'ai' ? '⚡' : '👤';
      const author = role === 'ai' ? 'AI Search Studio' : 'You';

      let citationsHtml = '';
      if (citations && citations.length > 0) {
        citationsHtml = `
          <div class="citations-box">
            <div class="citations-title">Sources & Citations:</div>
            <div class="citations-tags">
              ${citations.map(c => `<span class="citation-tag">🔗 ${escapeHtml(c)}</span>`).join('')}
            </div>
          </div>
        `;
      }

      let actionsHtml = '';
      if (role === 'ai') {
        actionsHtml = `
          <div class="msg-actions">
            <button class="msg-action-btn" onclick="copyMessageText(this)">📋 Copy</button>
            <button class="msg-action-btn" onclick="speakMessageText(this)">🔊 Read Aloud</button>
          </div>
        `;
      }

      // Render Markdown for AI, escape text for user
      const renderedContent = role === 'ai' ? marked.parse(text) : escapeHtml(text).replace(/\n/g, '<br>');

      card.innerHTML = `
        <div class="msg-avatar ${role}">${avatar}</div>
        <div class="msg-content-wrapper">
          <div class="msg-author">${author}</div>
          <div class="msg-bubble">${renderedContent}${citationsHtml}</div>
          ${actionsHtml}
        </div>
      `;

      messagesContainer.appendChild(card);
      // Highlight code blocks
      card.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
      return card;
    }

    async function sendMessage() {
      const text = userInput.value.trim();
      if (!text || isGenerating) return;

      isGenerating = true;
      sendBtn.disabled = true;
      userInput.value = '';
      userInput.style.height = 'auto';

      addMessage('user', text);
      setStatus('Searching & Reasoning...', 'warning');

      // Create AI placeholder card
      const aiCard = addMessage('ai', '⏳ *Thinking...*');
      const bubble = aiCard.querySelector('.msg-bubble');

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: text,
            mode: modeSelect.value,
            model: modelSelect.value
          })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Request failed');

        let citationsHtml = '';
        if (data.citations && data.citations.length > 0) {
          citationsHtml = `
            <div class="citations-box">
              <div class="citations-title">Sources & Citations:</div>
              <div class="citations-tags">
                ${data.citations.map(c => `<span class="citation-tag">🔗 ${escapeHtml(c)}</span>`).join('')}
              </div>
            </div>
          `;
        }

        bubble.innerHTML = marked.parse(data.answer) + citationsHtml;
        aiCard.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
        setStatus('Ready', 'success');
      } catch (err) {
        bubble.innerHTML = `<span style="color:var(--accent-danger);">❌ Error: ${escapeHtml(err.message)}</span>`;
        setStatus('Error', 'warning');
      } finally {
        isGenerating = false;
        sendBtn.disabled = false;
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
      }
    }

    function sendQuickPrompt(prompt) {
      userInput.value = prompt;
      autoGrow(userInput);
      sendMessage();
    }

    function setModeAndNotify(mode) {
      modeSelect.value = mode;
      setStatus(`Mode: ${mode}`, 'success');
    }

    function clearChat() {
      messagesContainer.innerHTML = '';
      addMessage('ai', '🧹 Chat cleared. What would you like to search or ask next?');
    }

    // Voice Speech-to-Text (STT) via Web Speech API
    function toggleSpeechRecognition() {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) {
        alert('Voice input is not supported by this browser. Please try Chrome, Edge, or Safari.');
        return;
      }

      if (isListening) {
        recognition.stop();
        return;
      }

      recognition = new SpeechRecognition();
      recognition.lang = 'en-US';
      recognition.interimResults = false;
      recognition.continuous = false;

      recognition.onstart = () => {
        isListening = true;
        micBtn.classList.add('listening');
        setStatus('🎙️ Listening...', 'warning');
      };

      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        userInput.value = transcript;
        autoGrow(userInput);
        sendMessage();
      };

      recognition.onerror = (event) => {
        console.warn('Speech recognition error:', event.error);
        setStatus('Voice error', 'warning');
      };

      recognition.onend = () => {
        isListening = false;
        micBtn.classList.remove('listening');
        setStatus('Ready', 'success');
      };

      recognition.start();
    }

    // Voice Text-to-Speech (TTS) via Web Speech API
    function speakMessageText(btn) {
      if (!('speechSynthesis' in window)) {
        alert('Text-to-speech is not supported in this browser.');
        return;
      }

      if (window.speechSynthesis.speaking) {
        window.speechSynthesis.cancel();
        btn.textContent = '🔊 Read Aloud';
        return;
      }

      const bubble = btn.closest('.msg-content-wrapper').querySelector('.msg-bubble');
      const text = bubble.innerText;
      if (!text) return;

      const utterance = new SpeechSynthesisUtterance(text);
      btn.textContent = '⏹️ Stop';
      utterance.onend = () => { btn.textContent = '🔊 Read Aloud'; };
      utterance.onerror = () => { btn.textContent = '🔊 Read Aloud'; };
      window.speechSynthesis.speak(utterance);
    }

    function copyMessageText(btn) {
      const bubble = btn.closest('.msg-content-wrapper').querySelector('.msg-bubble');
      navigator.clipboard.writeText(bubble.innerText).then(() => {
        const orig = btn.textContent;
        btn.textContent = '✅ Copied!';
        setTimeout(() => { btn.textContent = orig; }, 1800);
      });
    }

    function escapeHtml(str) {
      if (!str) return '';
      return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
  </script>
</body>
</html>
"""
