"""
Cấu hình tập trung cho Legal Agent Assistant.
Khi đóng gói .exe, chỉ cần sửa file này cho phù hợp máy đích.
"""
import os

# ── Đường dẫn gốc của project ──────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── LLM Provider: "ollama" (offline, local) ──────────────────────
LLM_PROVIDER = "ollama"

# ── Ollama (local) ────────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"

# ── Pandoc (đóng gói cùng .exe) ────────────────────────────────
PANDOC_DIR = os.path.join(BASE_DIR, "pandoc")
if os.path.isdir(PANDOC_DIR):
    os.environ["PYPANDOC_PANDOC"] = os.path.join(PANDOC_DIR, "pandoc.exe")

# ── Embedding model (sentence-transformers) ─────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ── ChromaDB ────────────────────────────────────────────────────
VECTOR_DB_PATH = os.path.join(BASE_DIR, "Data", "vector_db")

# ── Data directories ────────────────────────────────────────────
DATA_DIR = os.path.join(BASE_DIR, "Data")
LAW_DIR = os.path.join(DATA_DIR, "law")
USER_DOCS_DIR = os.path.join(DATA_DIR, "user_docs")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback.json")

# ── Splitter defaults ───────────────────────────────────────────
MAX_CHUNK_SIZE = 4000

# ── Duplicate detection ────────────────────────────────────────
DUPLICATE_SIMILARITY_THRESHOLD = 0.80
