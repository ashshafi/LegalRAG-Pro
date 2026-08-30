"""Governed supplementary derived-transcription answer context."""

from __future__ import annotations

from pathlib import Path
import hashlib
import math


_INDEX_ROOT = (
    Path(__file__).resolve().parents[1]
    / "derived_transcription_search_index"
    / "v1"
)


class DerivedTranscriptionAnswerContextError(RuntimeError):
    pass


class OpenAIQueryEmbeddingProvider:
    """Query-only provider; document re-embedding is prohibited."""

    def __init__(self):
        self._client = None

    def _client_instance(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                max_retries=0,
                timeout=60.0,
            )

        return self._client

    def embed_query(
        self,
        *,
        model,
        text,
    ):
        response = (
            self._client_instance()
            .embeddings.create(
                model=model,
                input=text,
            )
        )

        if len(response.data) != 1:
            raise DerivedTranscriptionAnswerContextError(
                "Query embedding response cardinality is invalid."
            )

        vector = [
            float(value)
            for value
            in response.data[0].embedding
        ]

        if not vector or any(
            not math.isfinite(value)
            for value
            in vector
        ):
            raise DerivedTranscriptionAnswerContextError(
                "Query embedding is invalid."
            )

        return vector

    def embed_document(
        self,
        *,
        model,
        text,
    ):
        raise DerivedTranscriptionAnswerContextError(
            "Document re-embedding is prohibited."
        )


def _load_retained_row(
    *,
    case_id,
):
    if not _INDEX_ROOT.is_dir():
        return None

    import chromadb

    from models import EMBEDDING_MODEL

    from derived_transcription_search_activation import (
        ActivationAuthority,
        ActivationRow,
        DERIVED_SEARCH_COLLECTION_NAME,
    )

    client = chromadb.PersistentClient(
        path=str(_INDEX_ROOT)
    )

    names = [
        value
        if isinstance(value, str)
        else value.name
        for value
        in client.list_collections()
    ]

    if names != [
        DERIVED_SEARCH_COLLECTION_NAME
    ]:
        raise DerivedTranscriptionAnswerContextError(
            "Derived-search collection authority differs."
        )

    collection = client.get_collection(
        name=DERIVED_SEARCH_COLLECTION_NAME,
        embedding_function=None,
    )

    stored = collection.get(
        include=[
            "documents",
            "metadatas",
        ],
    )

    ids = stored.get("ids") or []
    documents = stored.get("documents") or []
    metadatas = stored.get("metadatas") or []

    if not (
        len(ids)
        == len(documents)
        == len(metadatas)
        == 1
    ):
        raise DerivedTranscriptionAnswerContextError(
            "Derived-search retained row is not singular."
        )

    metadata = dict(
        metadatas[0]
    )

    if metadata.get("case_id") != case_id:
        return None

    document = documents[0]

    raw = document.encode(
        "utf-8",
        errors="strict",
    )

    if (
        hashlib.sha256(raw).hexdigest()
        != metadata.get(
            "transcription_sha256"
        )
    ):
        raise DerivedTranscriptionAnswerContextError(
            "Derived transcription authority differs."
        )

    row = ActivationRow(
        candidate_id=ids[0],
        document=document,
        case_id=metadata["case_id"],
        source_document_instance_id=
            metadata[
                "source_document_instance_id"
            ],
        source_snapshot_id=
            metadata[
                "source_snapshot_id"
            ],
        page=int(
            metadata["page"]
        ),
        source_original_blob_sha256=
            metadata[
                "source_original_blob_sha256"
            ],
        derived_record_id=
            metadata[
                "derived_record_id"
            ],
        transcription_sha256=
            metadata[
                "transcription_sha256"
            ],
        embedded_image_sha256=
            metadata[
                "embedded_image_sha256"
            ],
        profile_id=
            metadata[
                "profile_id"
            ],
    )

    authority = ActivationAuthority(
        case_id=case_id,
        candidate_id=row.candidate_id,
        transcription_sha256=
            row.transcription_sha256,
        transcription_bytes=len(raw),
        embedding_model=EMBEDDING_MODEL,
        collection_name=
            DERIVED_SEARCH_COLLECTION_NAME,
    )

    return (
        authority,
        row,
        collection,
    )


def format_candidate_context(
    result,
):
    if (
        result.discovery_scope
        != "candidate_discovery_only"
    ):
        raise DerivedTranscriptionAnswerContextError(
            "Derived-search discovery scope differs."
        )

    if (
        result.negative_finding_authoritative
        is not False
    ):
        raise DerivedTranscriptionAnswerContextError(
            "Derived search acquired negative-finding authority."
        )

    if not result.hits:
        return ""

    parts = [
        "DERIVED TRANSCRIPTION CANDIDATE CONTEXT",
        "Governance: candidate_discovery_only.",
        "negative_finding_authoritative=false.",
        "This is NOT FULL_CHAIN source evidence.",
        (
            "It is supplementary derived transcription bound "
            "to its source document/page."
        ),
        (
            "Do not represent this derived text as captured "
            "source text."
        ),
        (
            "Absence of a derived-search hit is NOT an "
            "authoritative negative finding."
        ),
    ]

    for hit in result.hits:
        metadata = dict(
            hit.metadata
        )

        parts.extend([
            "",
            "BEGIN DERIVED TRANSCRIPTION CANDIDATE",
            "candidate_id=" + hit.candidate_id,
            (
                "source_document_instance_id="
                + str(
                    metadata.get(
                        "source_document_instance_id",
                        "",
                    )
                )
            ),
            (
                "source_snapshot_id="
                + str(
                    metadata.get(
                        "source_snapshot_id",
                        "",
                    )
                )
            ),
            "page=" + str(
                metadata.get(
                    "page",
                    "",
                )
            ),
            (
                "derived_record_id="
                + str(
                    metadata.get(
                        "derived_record_id",
                        "",
                    )
                )
            ),
            (
                "transcription_sha256="
                + str(
                    metadata.get(
                        "transcription_sha256",
                        "",
                    )
                )
            ),
            "<<<DERIVED_TRANSCRIPTION_DATA",
            hit.document,
            "DERIVED_TRANSCRIPTION_DATA",
            "END DERIVED TRANSCRIPTION CANDIDATE",
        ])

    return "\n".join(
        parts
    )


def augment_governed_answer_prompt_with_derived_candidates(
    *,
    base_prompt,
    question,
    case_id,
    embedding_provider=None,
):
    if not case_id:
        return base_prompt

    loaded = _load_retained_row(
        case_id=case_id
    )

    if loaded is None:
        return base_prompt

    authority, row, collection = loaded

    from derived_transcription_search_activation import (
        query_retained_candidate,
    )

    provider = (
        embedding_provider
        if embedding_provider is not None
        else OpenAIQueryEmbeddingProvider()
    )

    result = query_retained_candidate(
        authority=authority,
        row=row,
        collection=collection,
        embedding_provider=provider,
        active_case_id=case_id,
        query_text=question,
        n_results=5,
    )

    context = format_candidate_context(
        result
    )

    if not context:
        return base_prompt

    return (
        base_prompt
        + "\n\n"
        + context
    )
