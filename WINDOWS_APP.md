# Windows app deployment

The current desktop application is packaged with PyInstaller as a one-folder Windows app.

## Setup & Build

```powershell
# Install desktop dependencies (includes GUI and voice playback)
pip install -r requirements-desktop.txt

# Package application with PyInstaller
.\venv\Scripts\python.exe -m PyInstaller --clean --noconfirm ai_search_studio.spec
```

The output is `dist\AI-Search-Studio\AI-Search-Studio.exe`.

## Run on another Windows machine

1. Copy the complete `dist\AI-Search-Studio` folder.
2. Copy `.env.example` into that folder and rename it to `.env`.
3. Set `MISTRAL_API_KEY` in `.env`.
4. Start `AI-Search-Studio.exe`.

Keep `.env` private. The application stores its local knowledge database and chat sessions beside the executable.
