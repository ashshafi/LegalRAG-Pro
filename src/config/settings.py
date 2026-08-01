from pathlib import Path
import os
from dotenv import load_dotenv

# Project root
BASE_DIR = Path(__file__).resolve().parents[2]

# Load environment variables
load_dotenv(BASE_DIR / ".env")


class Settings:
    """Application configuration."""

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    CHAT_MODEL = "gpt-5.5"

    EMBEDDING_MODEL = "text-embedding-3-small"

    CHROMA_PATH = BASE_DIR / "db"

    DOCS_PATH = BASE_DIR / "docs"

    CHUNK_SIZE = 1000

    CHUNK_OVERLAP = 200


settings = Settings()