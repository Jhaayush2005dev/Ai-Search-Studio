"""HTTP entry point for hosting AI Search Studio on Render."""

from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from core.rag_engine import RAGEngine


app = FastAPI(title="AI Search Studio", version="1.0.0")
_engine = RAGEngine()
_engine_lock = Lock()


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    answer: str
    citations: list[str]


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return HTML_PAGE


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    answer_parts: list[str] = []
    citations: list[str] = []

    try:
        with _engine_lock:
            answer = _engine.stream_query(
                request.query.strip(),
                token_callback=answer_parts.append,
                source_callback=lambda values: citations.extend(values),
            )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="The AI service could not answer this request.") from exc

    return ChatResponse(answer=answer or "".join(answer_parts), citations=citations)


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Search Studio</title>
  <style>
    :root { color-scheme: dark; font-family: ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; min-height: 100vh; background: #10151c; color: #edf2f7; }
    main { width: min(900px, calc(100% - 32px)); margin: 0 auto; padding: 56px 0; }
    h1 { margin: 0 0 8px; font-size: clamp(2rem, 6vw, 4rem); letter-spacing: -.04em; }
    .intro { color: #9aa7b5; margin: 0 0 32px; }
    form { display: grid; gap: 12px; }
    textarea { min-height: 120px; resize: vertical; border: 1px solid #344353; border-radius: 10px; padding: 16px; color: inherit; background: #17202a; font: inherit; }
    button { justify-self: start; border: 0; border-radius: 8px; padding: 12px 18px; color: #10151c; background: #85d0b7; font: inherit; font-weight: 700; cursor: pointer; }
    button:disabled { opacity: .6; cursor: wait; }
    article { white-space: pre-wrap; margin-top: 28px; padding: 20px; border-left: 3px solid #85d0b7; background: #17202a; line-height: 1.6; }
    small { display: block; color: #9aa7b5; margin-top: 14px; }
  </style>
</head>
<body>
  <main>
    <h1>AI Search Studio</h1>
    <p class="intro">Ask questions across your connected knowledge base.</p>
    <form id="chat-form">
      <textarea id="query" placeholder="What would you like to find?" required></textarea>
      <button id="submit" type="submit">Search</button>
    </form>
    <article id="answer" hidden></article>
    <small id="sources"></small>
  </main>
  <script>
    const form = document.querySelector('#chat-form');
    const query = document.querySelector('#query');
    const submit = document.querySelector('#submit');
    const answer = document.querySelector('#answer');
    const sources = document.querySelector('#sources');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      submit.disabled = true;
      submit.textContent = 'Searching...';
      answer.hidden = false;
      answer.textContent = '';
      sources.textContent = '';
      try {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({query: query.value})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Request failed');
        answer.textContent = data.answer;
        if (data.citations.length) sources.textContent = 'Sources: ' + data.citations.join(', ');
      } catch (error) {
        answer.textContent = error.message;
      } finally {
        submit.disabled = false;
        submit.textContent = 'Search';
      }
    });
  </script>
</body>
</html>"""
