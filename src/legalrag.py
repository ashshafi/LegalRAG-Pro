from config import openai_client, collection
from models import EMBEDDING_MODEL, CHAT_MODEL


def ask(question, selected_documents=None):
    """
    Ask a legal question using the indexed documents.

    Returns:
        {
            "answer": str,
            "sources": [
                {
                    "file": str,
                    "page": int,
                    "text": str
                }
            ]
        }
    """

    # ------------------------------------------
    # Create embedding for the user's question
    # ------------------------------------------

    embedding = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=question
    )

    question_vector = embedding.data[0].embedding

    # ------------------------------------------
    # Search ChromaDB
    # ------------------------------------------

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

    # ------------------------------------------
    # Build context for GPT
    # ------------------------------------------

    context = ""

    for i in range(len(results["documents"][0])):

        metadata = results["metadatas"][0][i]
        document = results["documents"][0][i]

        context += f"""
Document: {metadata['file']}
Page: {metadata['page']}

{document}

--------------------------------------------------
"""

    # ------------------------------------------
    # Build GPT prompt
    # ------------------------------------------

    prompt = f"""
You are an expert legal assistant.

Answer ONLY using the supplied documents.

If the answer cannot be found in the supplied documents,
say that you cannot find the information.

Always base your answer on the evidence provided.

Documents

{context}

Question

{question}
"""

    # ------------------------------------------
    # Ask GPT
    # ------------------------------------------

    response = openai_client.responses.create(
        model=CHAT_MODEL,
        input=prompt
    )

    # ------------------------------------------
    # Build evidence list
    # ------------------------------------------

    sources = []

    for i in range(len(results["documents"][0])):

        metadata = results["metadatas"][0][i]
        document = results["documents"][0][i]

        sources.append(
            {
                "file": metadata["file"],
                "page": metadata["page"],
                "text": document
            }
        )

    # ------------------------------------------
    # Return answer
    # ------------------------------------------

    return {
        "answer": response.output_text,
        "sources": sources
    }