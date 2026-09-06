from ai_provider_policy import (
    AIDataClassification,
    AIProcessingPurpose,
    assert_ai_processing_allowed,
)
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

    assert_ai_processing_allowed(
        provider="openai",
        purpose=AIProcessingPurpose.QUERY_EXPANSION,
        data_classification=AIDataClassification.PRIVILEGED,
        model=CHAT_MODEL,
    )

    response = openai_client.responses.create(
        model=CHAT_MODEL,
        input=prompt,
        store=False,
    )

    return response.output_text.strip()