"""Deterministic analytical-text chunking for immutable source evidence."""

from __future__ import annotations

from importlib import metadata
from typing import Any, Final

from .models import (
    CHUNKING_PROFILE_ID,
    CHUNKING_PROFILE_SCHEMA_VERSION,
    ChunkingProfile,
)
from .validation import validate_chunking_profile

_LIBRARY_NAME: Final[str] = "langchain-text-splitters"
_SEPARATORS: Final[tuple[str, ...]] = ("\n\n", "\n", " ", "")
_CHUNK_SIZE: Final[int] = 1000
_CHUNK_OVERLAP: Final[int] = 200


class SourceEvidenceChunkingError(RuntimeError):
    """Raised when governed source-evidence chunking cannot be performed."""


def _library_version() -> str:
    try:
        value = metadata.version(_LIBRARY_NAME)
    except metadata.PackageNotFoundError as exc:
        raise SourceEvidenceChunkingError(
            "The governed langchain-text-splitters runtime is unavailable."
        ) from exc
    if not value:
        raise SourceEvidenceChunkingError(
            "The governed langchain-text-splitters runtime version is unavailable."
        )
    return value


def build_chunking_profile() -> ChunkingProfile:
    """Return the frozen v1 chunking profile for the current runtime."""

    profile = ChunkingProfile(
        profile_id=CHUNKING_PROFILE_ID,
        profile_schema_version=CHUNKING_PROFILE_SCHEMA_VERSION,
        library=_LIBRARY_NAME,
        library_version=_library_version(),
        chunk_size=_CHUNK_SIZE,
        chunk_overlap=_CHUNK_OVERLAP,
        separators=_SEPARATORS,
        length_function="len",
        is_separator_regex=False,
    )
    validate_chunking_profile(profile)
    return profile


def _splitter_type() -> type[Any]:
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as exc:
        raise SourceEvidenceChunkingError(
            "The governed langchain-text-splitters runtime is unavailable."
        ) from exc
    return RecursiveCharacterTextSplitter


def split_page_text(text: str) -> tuple[str, ...]:
    """Split exact extracted page text under the frozen v1 policy."""

    if not isinstance(text, str):
        raise TypeError("text must be a string.")

    # Validate the runtime/profile before deriving authoritative chunk text.
    build_chunking_profile()
    splitter = _splitter_type()(
        chunk_size=_CHUNK_SIZE,
        chunk_overlap=_CHUNK_OVERLAP,
        separators=list(_SEPARATORS),
        length_function=len,
        keep_separator=True,
        add_start_index=False,
        strip_whitespace=True,
        is_separator_regex=False,
    )
    chunks = splitter.split_text(text)
    if not isinstance(chunks, list) or any(not isinstance(chunk, str) for chunk in chunks):
        raise SourceEvidenceChunkingError(
            "The governed text splitter returned an invalid chunk sequence."
        )
    return tuple(chunks)


__all__ = [
    "SourceEvidenceChunkingError",
    "build_chunking_profile",
    "split_page_text",
]
