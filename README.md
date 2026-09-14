---
title: AI Search Studio
emoji: 🔍
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# 🔍 AI Search Studio (Web, Mobile & Desktop PWA)

AI Search Studio is an intelligent hybrid AI search engine and knowledge assistant powered by **Mistral AI**, **LangChain**, **ChromaDB**, and live **DuckDuckGo web search**.

Designed to run seamlessly on **laptops, desktops, and mobile phones** (iOS & Android) with installable **Progressive Web App (PWA)** support.

---

## ✨ Features

- 📱 **Mobile & Laptop App**: Responsive touch-friendly layout with slide-out menu on phones and side-by-side view on laptops.
- 📲 **Installable PWA**: Tap "Add to Home Screen" on iPhone or "Install App" on Android/Chrome to use it as a standalone app with its own icon.
- 🌐 **Hybrid Knowledge & Web Search**: Queries local uploaded documents (PDF, Word, TXT, CSV, Code, Images) and falls back to live web search automatically.
- 🎙️ **Voice Search & Speech Playback**: Built-in voice dictation (STT) and read-aloud (TTS) using browser Web Speech APIs—no heavy server audio dependencies required.
- ⚡ **Mistral AI Integration**: Compatible with `open-mistral-7b`, `mistral-small`, `mistral-medium`, `mistral-large`, and `codestral`.
- 🎨 **Modern Matte UI**: Syntax-highlighted code blocks, expandable citations, and dark mode interface.

---

## 🚀 Running on Laptop & Mobile Phone

### 1. Instant Local Network / Wi-Fi Access (No Cloud Needed)

Run the mobile launcher on your laptop:

```bash
# Activate virtual environment
.\venv\Scripts\activate

# Launch local app server
python run_mobile.py
```

The terminal will display:
- **Laptop URL**: `http://localhost:8000`
- **Mobile Phone URL**: `http://<your-laptop-ip>:8000` (e.g. `http://192.168.1.15:8000`)

Open the mobile URL on your phone connected to the same Wi-Fi.

### 2. How to Install as an App on Your Phone

- **Android (Chrome)**: Open the URL $\rightarrow$ Tap the **"Install App"** banner or Chrome menu (⋮) $\rightarrow$ **"Add to Home screen"**.
- **iPhone / iPad (Safari)**: Open the URL $\rightarrow$ Tap the **Share** button (square with arrow) $\rightarrow$ **"Add to Home Screen ➕"**.

---

## ☁️ Cloud Deployment Options

### Option A: Render (Recommended Free Web Service)
1. Push this repository to GitHub.
2. Sign in to [Render.com](https://render.com) and click **New Web Service**.
3. Connect your GitHub repository.
4. Set:
   - **Environment**: `Python`
   - **Build Command**: `pip install -r requirements-web.txt`
   - **Start Command**: `uvicorn web_app:app --host 0.0.0.0 --port $PORT`
5. Under **Environment Variables**, add:
   - `MISTRAL_API_KEY`: `your_mistral_api_key_here`
6. Click **Deploy**. You'll get an `https://...onrender.com` link accessible from anywhere!

### Option B: Hugging Face Spaces (Docker)
1. Create a new Space on Hugging Face and choose **Docker** SDK.
2. Push this repo. The updated [Dockerfile](Dockerfile) uses `requirements-web.txt` and properly configures permissions.
3. In Space **Settings** $\rightarrow$ **Variables and secrets**, add `MISTRAL_API_KEY`.

---

## ⚙️ Environment Variables

Create a `.env` file in the root directory:

```env
MISTRAL_API_KEY=your_mistral_api_key_here
```
