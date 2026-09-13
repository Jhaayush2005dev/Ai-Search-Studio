---
title: AI Search Studio
emoji: 🔍
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# 🔍 AI Search Studio

AI Search Studio is an intelligent hybrid AI search engine and knowledge assistant powered by Mistral AI, LangChain, ChromaDB, and live DuckDuckGo web search.

## ✨ Features
- 🌐 **Hybrid Knowledge & Web Search**: Seamlessly answers queries using indexed local documents and live web search results.
- ⚡ **Mistral AI Integration**: Powered by Mistral LLM with streaming responses and automatic rate-limit retry handling.
- 🎨 **Modern Dark Web UI**: Responsive, developer-grade matte interface.
- 🔒 **Zero Key Leakage**: API secrets are managed server-side.

## ⚙️ Configuration & Secrets

Before running or deploying to Hugging Face Spaces, configure your environment secrets:

1. Navigate to your Space **Settings** $\rightarrow$ **Variables and secrets**.
2. Click **New secret**.
3. Set:
   - **Name**: `MISTRAL_API_KEY`
   - **Value**: `your_mistral_api_key_here` (from [console.mistral.ai](https://console.mistral.ai/))

## 🚀 Local Development

```bash
# Clone the repository
git clone https://github.com/Jhaayush2005dev/Ai-Search-Studio.git
cd Ai-Search-Studio

# Set up virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run Web App
uvicorn web_app:app --host 0.0.0.0 --port 7860
```
