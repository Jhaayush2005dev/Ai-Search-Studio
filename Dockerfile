FROM python:3.11-slim

# Set environment flags
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=7860

# Install essential system packages and OCR dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with UID 1000 (Hugging Face / Render / standard secure containers)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Install Python dependencies using clean web-only requirements
COPY --chown=user:user requirements-web.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-web.txt

# Copy application source code
COPY --chown=user:user . .

# Ensure storage directories exist with write access
RUN mkdir -p chroma_db "documents loaders" chat_sessions static && \
    chmod -R 777 chroma_db "documents loaders" chat_sessions static

EXPOSE 7860

# Run FastAPI app with dynamic port support
CMD ["sh", "-c", "uvicorn web_app:app --host 0.0.0.0 --port ${PORT:-7860}"]
