from config import openai_client, collection
from models import EMBEDDING_MODEL
# Ask the user a question
question = input("Ask a question: ")

response = openai_client.embeddings.create(
    model=EMBEDDING_MODEL,
    input=question
)
question_embedding = response.data[0].embedding

# Search the database
results = collection.query(
    query_embeddings=[question_embedding],
    n_results=3
)

print("\nTop Matches\n")

for i in range(len(results["documents"][0])):

    print("=" * 60)

    metadata = results["metadatas"][0][i]

    print(f"File : {metadata['file']}")
    print(f"Page : {metadata['page']}")
    print()

    print(results["documents"][0][i][:600])
    print()