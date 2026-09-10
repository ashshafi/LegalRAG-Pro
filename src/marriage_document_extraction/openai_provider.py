from __future__ import annotations

import json
from typing import Any, Mapping

from ai_provider_policy import (
    AIDataClassification,
    AIProcessingPurpose,
    assert_ai_processing_allowed,
)

from .service import (
    MarriageFactExtractionError,
    build_marriage_fact_extraction_output_schema,
    build_marriage_fact_extraction_prompt,
)


class OpenAIMarriageFactExtractionProvider:
    """Strict structured-output adapter with a caller-injected OpenAI client."""

    def __init__(self, *, client: Any) -> None:
        if client is None:
            raise MarriageFactExtractionError(
                "OpenAI client must be supplied."
            )
        self._client = client

    def extract(
        self,
        *,
        model: str,
        transcription_text: str,
    ) -> Mapping[str, Any]:
        prompt = build_marriage_fact_extraction_prompt(
            transcription_text
        )
        schema = build_marriage_fact_extraction_output_schema()

        try:
            assert_ai_processing_allowed(
                provider="openai",
                purpose=AIProcessingPurpose.CONTROLLED_ANALYSIS,
                data_classification=AIDataClassification.PRIVILEGED,
                model=model,
            )

            response = self._client.responses.create(
                model=model,
                input=prompt,
                store=False,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "marriage_document_fact_extraction",
                        "strict": True,
                        "schema": schema,
                    }
                },
            )
        except MarriageFactExtractionError:
            raise
        except Exception as exc:
            raise MarriageFactExtractionError(
                "Marriage-fact extraction provider call failed."
            ) from exc

        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise MarriageFactExtractionError(
                "Marriage-fact extraction returned no structured output."
            )

        try:
            payload = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise MarriageFactExtractionError(
                "Marriage-fact extraction returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise MarriageFactExtractionError(
                "Marriage-fact extraction JSON must be an object."
            )

        return payload
