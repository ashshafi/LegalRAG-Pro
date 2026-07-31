from dotenv import load_dotenv
from openai import OpenAI
import chromadb

load_dotenv()

client = OpenAI()

# Connect to ChromaDB
chroma_client = chromadb.PersistentClient(path="db")
collection = chroma_client.get_collection("legal_documents")

question = input("Ask a question: ")

# Create embedding for the question
embedding = client.embeddings.create(
    model="text-embedding-3-small",
    input=question
)

question_vector = embedding.data[0].embedding

# Search the database
results = collection.query(
    query_embeddings=[question_vector],
    n_results=3
)

# Build the context for GPT
context = ""

for i in range(len(results["documents"][0])):

    metadata = results["metadatas"][0][i]

    context += f"""
Document: {metadata['file']}
Page: {metadata['page']}

{results["documents"][0][i]}

----------------------------

"""

prompt = f"""
You are an AI legal assistant.

Answer ONLY using the information below.

If the answer is not contained in the documents,
say you cannot find it.

Documents:

{context}

Question:

{question}
"""

response = client.responses.create(
    model="gpt-5",
    input=prompt
)

print("\n=========================\n")

print(response.output_text)