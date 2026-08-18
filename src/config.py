from functools import lru_cache

from dotenv import load_dotenv
from openai import OpenAI
import chromadb

# Load environment variables
load_dotenv()

# OpenAI client
@lru_cache(maxsize=1)
def get_openai_client():
    return OpenAI()


class _LazyOpenAIClient:
    def __getattr__(self, name):
        return getattr(get_openai_client(), name)


openai_client = _LazyOpenAIClient()


@lru_cache(maxsize=1)
def get_chroma_client():
    return chromadb.PersistentClient(path="db")


@lru_cache(maxsize=1)
def get_collection():
    return get_chroma_client().get_or_create_collection(
        name="legal_documents"
    )
