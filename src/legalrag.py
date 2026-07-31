from config import openai_client, collection
from models import EMBEDDING_MODEL, CHAT_MODEL


def ask(question, selected_documents=None):

    # Create embedding
    embedding = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=question
    )

    question_vector = embedding.data[0].embedding

    # Search Chroma
    if selected_documents:

        results = collection.query(
            query_embeddings=[question_vector],
            n_results=3,
            where={
                "file": {
                    "$in": selected_documents
                }
            }
        )

    else:

        results = collection.query(
            query_embeddings=[question_vector],
            n_results=3
        )

    # Build context
    context = ""

    for i in range(len(results["documents"][0])):

        metadata = results["metadatas"][0][i]

        context += f"""
Document: {metadata['file']}
Page: {metadata['page']}

{results["documents"][0][i]}

-------------------------

"""

    prompt = f"""
You are a legal assistant.

Answer ONLY using the supplied documents.

If the answer is not in the supplied documents,
say so.

Documents:

{context}

Question:

{question}
"""

    # Ask GPT
    response = openai_client.responses.create(
        model=CHAT_MODEL,
        input=prompt
    )

    # Build source list
    sources = []

    for i in range(len(results["documents"][0])):

        metadata = results["metadatas"][0][i]

        sources.append({
            "file": metadata["file"],
            "page": metadata["page"]
        })

    return {
        "answer": response.output_text,
        "sources": sources
    }