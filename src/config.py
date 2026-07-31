from dotenv import load_dotenv
from openai import OpenAI
import chromadb

# Load environment variables
load_dotenv()

# OpenAI client
openai_client = OpenAI()

# Chroma client
chroma_client = chromadb.PersistentClient(path="db")

# Collection
collection = chroma_client.get_or_create_collection(
    name="legal_documents"
)