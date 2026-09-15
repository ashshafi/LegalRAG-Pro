from functools import lru_cache
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from openai import OpenAI


_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOTENV_PATH = _REPO_ROOT / ".env"
load_dotenv(dotenv_path=_DOTENV_PATH, override=True)


@lru_cache(maxsize=1)
def get_openai_client():
    """Construct the OpenAI client only when an AI operation actually needs it."""
    return OpenAI()


class _LazyOpenAIClient:
    """Compatibility proxy for modules that import ``openai_client`` directly."""

    def __getattr__(self, name):
        return getattr(get_openai_client(), name)


openai_client = _LazyOpenAIClient()


@lru_cache(maxsize=1)
def get_chroma_client():
    return chromadb.PersistentClient(path="db")


@lru_cache(maxsize=1)
def get_collection():
    return get_chroma_client().get_or_create_collection(name="legal_documents")
