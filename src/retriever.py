from config import openai_client, collection
from models import EMBEDDING_MODEL


def retrieve(question, n_results=3):
    embedding = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=question
    )

    question_vector = embedding.data[0].embedding

    return collection.query(
        query_embeddings=[question_vector],
        n_results=n_results
    )