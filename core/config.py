import os
import sys
import socket
from pathlib import Path
from dotenv import load_dotenv

# Base Paths
# Use the executable directory for PyInstaller builds so user configuration and
# runtime data live beside the app instead of inside its bundled internals.
if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT_DIR / "documents loaders"
CHROMA_DIR = ROOT_DIR / "chroma_db"
SESSIONS_DIR = ROOT_DIR / "chat_sessions"
DOCS_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# Load Environment
load_dotenv(ROOT_DIR / ".env", override=True)
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

# Tesseract Windows OCR Configuration
if os.name == 'nt':
    import pytesseract
    tesseract_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        os.path.expanduser(r'~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe')
    ]
    for p in tesseract_paths:
        if os.path.exists(p):
            pytesseract.pytesseract.tesseract_cmd = p
            break

# Available Models
AVAILABLE_MODELS = [
    "open-mistral-7b",
    "mistral-small-latest",
    "mistral-medium-latest",
    "mistral-large-latest",
    "codestral-latest"
]
DEFAULT_MODEL = "open-mistral-7b"
EMBEDDING_MODEL = "mistral-embed"

# Supported File Extensions
SUPPORTED_EXTENSIONS = {
    "pdf": "📄 PDF Document",
    "txt": "📝 Text File",
    "md": "📑 Markdown File",
    "docx": "📘 Word Document",
    "csv": "📊 CSV Spreadsheet",
    "xlsx": "📈 Excel Spreadsheet",
    "xls": "📈 Excel Spreadsheet",
    "py": "🐍 Python Code",
    "js": "📜 JavaScript Code",
    "ts": "📜 TypeScript Code",
    "html": "🌐 HTML File",
    "css": "🎨 CSS File",
    "json": "🗂️ JSON Data",
    "java": "☕ Java Code",
    "cpp": "⚙️ C++ Code",
    "c": "⚙️ C Code",
    "sql": "🗄️ SQL Script",
    "png": "🖼️ PNG Image (OCR)",
    "jpg": "🖼️ JPG Image (OCR)",
    "jpeg": "🖼️ JPEG Image (OCR)"
}

# Clean Developer-Grade Themes (Low Eye Strain, Matte Finishes, Balanced Contrast)
THEMES = {
    "Developer Dark": {
        "bg_base": "#131316",         # Soft matte charcoal base
        "bg_sidebar": "#18181c",      # Subtle dark slate sidebar
        "bg_card_ai": "#1c1c22",      # Clean matte AI response card
        "bg_card_user": "#23232b",    # Soft elevated user prompt card (no harsh blue)
        "bg_input": "#19191e",        # Sleek integrated input bar
        "bg_code": "#101014",         # Deep code editor frame
        "accent_primary": "#6366f1",  # Modern developer indigo (Cursor / Linear style)
        "accent_hover": "#4f46e5",
        "accent_success": "#10b981",  # Soft emerald
        "accent_warning": "#f59e0b",  # Soft amber
        "accent_danger": "#ef4444",   # Soft coral
        "text_primary": "#e4e4e7",    # Soft zinc white (zero eye fatigue)
        "text_secondary": "#a1a1aa",  # Muted neutral zinc
        "text_muted": "#71717a",      # Subtle metadata
        "border_color": "#272732",    # Ultra-clean 1px border
        "chip_bg": "#1e1e26",         # Low-contrast prompt pill
        "chip_hover": "#292934"
    },
    "Obsidian Slate": {
        "bg_base": "#0f1115",
        "bg_sidebar": "#14171d",
        "bg_card_ai": "#181c23",
        "bg_card_user": "#202630",
        "bg_input": "#14171d",
        "bg_code": "#0b0d10",
        "accent_primary": "#38bdf8",  # Soft sky blue
        "accent_hover": "#0ea5e9",
        "accent_success": "#34d399",
        "accent_warning": "#fbbf24",
        "accent_danger": "#f87171",
        "text_primary": "#e2e8f0",
        "text_secondary": "#94a3b8",
        "text_muted": "#64748b",
        "border_color": "#232934",
        "chip_bg": "#1c212a",
        "chip_hover": "#262c38"
    },
    "Nordic Dark": {
        "bg_base": "#1a1c23",
        "bg_sidebar": "#20232c",
        "bg_card_ai": "#252834",
        "bg_card_user": "#2d3140",
        "bg_input": "#20232c",
        "bg_code": "#16171d",
        "accent_primary": "#818cf8",
        "accent_hover": "#6366f1",
        "accent_success": "#86efac",
        "accent_warning": "#fde047",
        "accent_danger": "#fca5a5",
        "text_primary": "#f1f5f9",
        "text_secondary": "#94a3b8",
        "text_muted": "#64748b",
        "border_color": "#2f3444",
        "chip_bg": "#282c3b",
        "chip_hover": "#34394c"
    },
    "Developer Light": {
        "bg_base": "#f4f4f5",
        "bg_sidebar": "#fafafa",
        "bg_card_ai": "#ffffff",
        "bg_card_user": "#ececee",
        "bg_input": "#ffffff",
        "bg_code": "#e4e4e7",
        "accent_primary": "#4f46e5",
        "accent_hover": "#4338ca",
        "accent_success": "#059669",
        "accent_warning": "#d97706",
        "accent_danger": "#dc2626",
        "text_primary": "#18181b",
        "text_secondary": "#52525b",
        "text_muted": "#71717a",
        "border_color": "#e4e4e7",
        "chip_bg": "#e4e4e7",
        "chip_hover": "#d4d4d8"
    }
}

CURRENT_THEME = "Developer Dark"

def set_current_theme(theme_name):
    global CURRENT_THEME
    if theme_name in THEMES:
        CURRENT_THEME = theme_name
    return get_theme_colors(CURRENT_THEME)

def get_theme_colors(theme_name=None):
    if not theme_name or theme_name not in THEMES:
        theme_name = CURRENT_THEME
    return THEMES.get(theme_name, THEMES["Developer Dark"])

def is_internet_available(timeout=2):
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=timeout)
        return True
    except OSError:
        return False
