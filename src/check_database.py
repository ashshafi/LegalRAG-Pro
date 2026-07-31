from pathlib import Path
import chromadb

db_path = Path("db").resolve()
print("Database path:", db_path)

client = chromadb.PersistentClient(path=str(db_path))

collection = client.get_collection("legal_documents")

results = collection.get(include=["metadatas"])

print(f"\nCollection: {collection.name}")
print(f"Chunks: {len(results['ids'])}")

print("\nMetadata:")

for i, metadata in enumerate(results["metadatas"]):
    print(f"{i + 1}: {metadata}")