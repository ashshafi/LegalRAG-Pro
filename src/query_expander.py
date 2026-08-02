from config import openai_client
from models import CHAT_MODEL


def expand_query(question):
    """
    Expand a question into a natural-language search query
    suitable for semantic vector search.
    """

    prompt = f"""
Rewrite this question as a short semantic search query.

Rules:

- Keep it under 20 words.
- Do NOT use Boolean operators.
- Do NOT use OR, AND, quotation marks or brackets.
- Do NOT invent legal terms.
- Preserve dates, names and organisations exactly.
- Add only a few natural synonyms.

Question:

{question}
"""

    response = openai_client.responses.create(
        model=CHAT_MODEL,
        input=prompt
    )

    return response.output_text.strip()