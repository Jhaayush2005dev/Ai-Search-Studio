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

# Create user with UID 1000 (standard requirement for Hugging Face Spaces non-root containers)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Install Python dependencies
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY --chown=user:user . .

# Expose default Hugging Face Spaces port
EXPOSE 7860

# Run FastAPI app
CMD ["uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "7860"]
