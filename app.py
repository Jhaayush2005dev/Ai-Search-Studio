"""Entry point for Hugging Face Spaces and ASGI runners."""

import os
import uvicorn
from web_app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("web_app:app", host="0.0.0.0", port=port, reload=False)
