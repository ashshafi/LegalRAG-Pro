from pathlib import Path
import chromadb

DB_PATH = Path("db").resolve()

client = chromadb.PersistentClient(path=str(DB_PATH))

collection = client.get_collection("legal_documents")


def get_documents():

    results = collection.get(include=["metadatas"])

    documents = sorted(
        {
            metadata["file"]
            for metadata in results["metadatas"]
        }
    )

    return documents