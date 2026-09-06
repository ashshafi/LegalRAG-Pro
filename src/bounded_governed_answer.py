"""Deterministic bounded map/reduce for large governed LegalRAG answers.

This module does not reduce the governed evidence scope. It only bounds each
outbound model input. Every U8 answer-result row is assigned to exactly one
deterministic batch, each map result retains source coordinates, and the final
synthesis operates only on those mapped findings plus the governed coverage
receipt.

No persistence, authority publication, Chroma mutation, or evidence mutation
occurs here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Final

from ai_provider_policy import (
    AIDataClassification,
    AIProcessingPurpose,
    assert_ai_processing_allowed,
)

BOUNDED_ANSWER_TRIGGER_CHARS: Final[int] = 500_000
BOUNDED_BATCH_TARGET_CHARS: Final[int] = 240_000
MAP_MAX_OUTPUT_TOKENS: Final[int] = 5_000
REDUCE_MAX_OUTPUT_TOKENS: Final[int] = 8_000


@dataclass(frozen=True, slots=True)
class EvidenceBatch:
    ordinal: int
    total: int
    row_indexes: tuple[int, ...]
    text: str


def should_use_bounded_governed_answer(prompt: str) -> bool:
    return isinstance(prompt, str) and len(prompt) > BOUNDED_ANSWER_TRIGGER_CHARS


def _single_row(results: dict[str, Any], field: str) -> list[Any]:
    value = results.get(field)
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], list):
        raise ValueError(f"{field} must contain exactly one query row.")
    return value[0]


def _row_text(index: int, evidence_key: str, text: str, metadata: dict[str, Any]) -> str:
    file_name = str(metadata.get("file", "unknown"))
    page = str(metadata.get("page", "unknown"))
    role = str(metadata.get("u8_evidence_role", "unclassified"))
    document_id = str(metadata.get("source_document_instance_id", "unknown"))
    discovery_rank = metadata.get("u8_semantic_discovery_rank")
    return (
        f"EVIDENCE ROW {index + 1}\n"
        f"evidence_key: {evidence_key}\n"
        f"file: {file_name}\n"
        f"page: {page}\n"
        f"role: {role}\n"
        f"source_document_instance_id: {document_id}\n"
        f"semantic_discovery_rank: {discovery_rank}\n"
        "text:\n"
        f"{text}\n"
        "END EVIDENCE ROW\n"
    )


def build_evidence_batches(
    enriched_results: dict[str, Any],
    *,
    target_chars: int = BOUNDED_BATCH_TARGET_CHARS,
) -> tuple[EvidenceBatch, ...]:
    if target_chars < 10_000:
        raise ValueError("target_chars is too small for governed answer batching.")

    ids = _single_row(enriched_results, "ids")
    documents = _single_row(enriched_results, "documents")
    metadatas = _single_row(enriched_results, "metadatas")
    if not (len(ids) == len(documents) == len(metadatas)):
        raise ValueError("governed answer rows are misaligned.")
    if not ids:
        raise ValueError("governed answer contains no evidence rows.")
    if len(set(map(str, ids))) != len(ids):
        raise ValueError("governed answer contains duplicate evidence keys.")

    raw_batches: list[tuple[tuple[int, ...], str]] = []
    indexes: list[int] = []
    parts: list[str] = []
    size = 0

    for index, (evidence_key, document, metadata) in enumerate(
        zip(ids, documents, metadatas, strict=True)
    ):
        if not isinstance(metadata, dict):
            raise ValueError("governed answer metadata row is invalid.")
        row = _row_text(index, str(evidence_key), str(document), metadata)

        if len(row) > target_chars:
            if indexes:
                raw_batches.append((tuple(indexes), "".join(parts)))
                indexes, parts, size = [], [], 0

            header, body = row.split("text:\n", 1)
            suffix = "\nEND EVIDENCE ROW\n"
            if body.endswith(suffix):
                body = body[: -len(suffix)]
            allowance = max(10_000, target_chars - len(header) - len(suffix) - 160)
            segments = [
                body[offset : offset + allowance]
                for offset in range(0, len(body), allowance)
            ]
            for part_index, segment in enumerate(segments, start=1):
                segmented = (
                    header
                    + f"segment: {part_index}/{len(segments)}\n"
                    + "text:\n"
                    + segment
                    + suffix
                )
                raw_batches.append(((index,), segmented))
            continue

        if indexes and size + len(row) > target_chars:
            raw_batches.append((tuple(indexes), "".join(parts)))
            indexes, parts, size = [], [], 0

        indexes.append(index)
        parts.append(row)
        size += len(row)

    if indexes:
        raw_batches.append((tuple(indexes), "".join(parts)))

    total = len(raw_batches)
    return tuple(
        EvidenceBatch(ordinal=i, total=total, row_indexes=row_indexes, text=text)
        for i, (row_indexes, text) in enumerate(raw_batches, start=1)
    )


def _coverage_text(evidence: Any) -> str:
    receipt = evidence.search_result.receipt
    return "\n".join(
        (
            "GOVERNED COVERAGE RECEIPT",
            f"search_mode: {receipt.search_mode.value}",
            f"completion: {receipt.completion.value}",
            f"scope_document_count: {receipt.scope_document_count}",
            f"documents_completely_expanded: {receipt.documents_completely_expanded}",
            f"scope_page_count: {receipt.scope_page_count}",
            f"pages_inspected: {receipt.pages_inspected}",
            f"scope_chunk_count: {receipt.scope_chunk_count}",
            f"chunks_inspected: {receipt.chunks_inspected}",
            f"case_corpus_complete: {receipt.case_corpus_complete}",
            f"negative_finding_permitted: {receipt.negative_finding_permitted}",
            f"negative_finding_scope: {receipt.negative_finding_scope.value}",
        )
    )


def _negative_rule(evidence: Any) -> str:
    receipt = evidence.search_result.receipt
    if not receipt.negative_finding_permitted:
        return (
            "Do not state or imply that evidence is absent. The governed receipt "
            "does not permit a negative finding."
        )
    scope = receipt.negative_finding_scope.value
    if scope == "case_corpus":
        return (
            'A negative finding may be made only in the formulation: '
            '"No supporting evidence was identified in the searched case corpus."'
        )
    if scope == "searched_scope":
        return (
            'A negative finding may be made only in the formulation: '
            '"No supporting evidence was identified in the completely searched '
            'candidate documents." Do not generalise it to the entire case corpus.'
        )
    return "Do not make a negative finding."


def _apply_constraint(
    prompt: str,
    *,
    analytical_context: Any,
    constrain_prompt: Callable[..., str] | None,
) -> str:
    if analytical_context is None:
        return prompt
    if constrain_prompt is None:
        raise ValueError("analytical context exists without its governed prompt constrainer.")
    return constrain_prompt(base_prompt=prompt, context=analytical_context)


def _apply_prompt_wrapper(
    prompt: str,
    *,
    question: str,
    prompt_wrapper: Callable[..., str] | None,
) -> str:
    if prompt_wrapper is None:
        return prompt
    return prompt_wrapper(base_prompt=prompt, question=question)


def _authorise(model: str) -> None:
    assert_ai_processing_allowed(
        provider="openai",
        purpose=AIProcessingPurpose.LEGAL_ANSWER,
        data_classification=AIDataClassification.PRIVILEGED,
        model=model,
    )


BOUNDED_PROVIDER_TIMEOUT_SECONDS = 90.0


def _provider_call(
    client: Any,
    *,
    model: str,
    prompt: str,
    max_output_tokens: int,
    reasoning_effort: str | None = None,
    timeout_seconds: float | None = BOUNDED_PROVIDER_TIMEOUT_SECONDS,
    output_schema: dict[str, Any] | None = None,
) -> str:
    _authorise(model)
    kwargs = {
        "model": model,
        "input": prompt,
        "store": False,
        "max_output_tokens": max_output_tokens,
    }
    if reasoning_effort is not None:
        kwargs["reasoning"] = {"effort": reasoning_effort}

    provider_client = (
        client.with_options(timeout=timeout_seconds)
        if timeout_seconds is not None and hasattr(client, "with_options")
        else client
    )
    if output_schema is not None:
        kwargs["text"] = {
            "format": {
                "type": "json_schema",
                "name": "governed_analytical_answer",
                "strict": True,
                "schema": output_schema,
            }
        }
    response = provider_client.responses.create(**kwargs)
    text = getattr(response, "output_text", None)
    if not isinstance(text, str) or not text.strip():
        status = getattr(response, "status", None)
        incomplete = getattr(response, "incomplete_details", None)
        reason = getattr(incomplete, "reason", None)
        if reason is None and isinstance(incomplete, dict):
            reason = incomplete.get("reason")
        raise RuntimeError(
            "bounded governed provider call returned no answer text "
            f"(status={status or 'unknown'}, incomplete_reason={reason or 'unknown'})."
        )
    return text.strip()


def _map_prompt(*, question: str, batch: EvidenceBatch, coverage: str) -> str:
    return f"""
LEGALRAG GOVERNED LARGE-MATTER MAP PASS

You are analysing deterministic evidence batch {batch.ordinal} of {batch.total}.
The complete governed search was performed before batching. Batching changes
only provider-input size; it does not change evidence scope.

QUESTION
{question}

{coverage}

MAP-PASS RULES
- Analyse every supplied evidence row in this batch.
- Do not make any negative finding about evidence being absent; other batches exist.
- Give primary-source material priority over commentary or summaries.
- Identify supporting, adverse, contradictory and qualifying material.
- Preserve the exact evidence_key, file and page for every material finding.
- Do not invent evidence or source coordinates.
- Be concise enough for a later deterministic synthesis pass.

For each material point use:
FINDING | evidence_key=<key> | file=<file> | page=<page> |
classification=<supporting/adverse/contradictory/qualifying/context> | finding=<text>

If this batch contains no material point, output exactly:
NO MATERIAL FINDING IN BATCH {batch.ordinal}

BATCH EVIDENCE
{batch.text}
""".strip()


def _reduce_prompt(*, question: str, evidence: Any, mapped: tuple[str, ...]) -> str:
    mapped_text = "\n\n".join(
        f"BEGIN MAP RESULT {index}\n{text}\nEND MAP RESULT {index}"
        for index, text in enumerate(mapped, start=1)
    )
    return f"""
LEGALRAG GOVERNED LARGE-MATTER FINAL SYNTHESIS

QUESTION
{question}

{_coverage_text(evidence)}

SYNTHESIS RULES
- The mapped results below collectively cover every evidence row supplied by the
  already-completed governed U8 answer scope.
- Answer the legal question using only mapped findings below.
- Preserve evidence_key, file and page citations for material propositions.
- Include adverse, contradictory and qualifying evidence; do not present only
  evidence favourable to one side.
- Distinguish contemporaneous primary evidence from later commentary.
- Do not invent missing facts, dates, sources or conclusions.
- {_negative_rule(evidence)}
- Where evidence conflicts, identify the conflict rather than choosing a version
  without evidential justification.
- Give a solicitor-facing answer, not an engineering explanation of batching.

MAPPED FINDINGS
{mapped_text}
""".strip()


def create_bounded_governed_response(
    *,
    client: Any,
    model: str,
    question: str,
    evidence: Any,
    enriched_results: dict[str, Any],
    analytical_context: Any = None,
    constrain_prompt: Callable[..., str] | None = None,
    prompt_wrapper: Callable[..., str] | None = None,
    reasoning_effort: str | None = None,
    output_schema: dict[str, Any] | None = None,
) -> Any:
    batches = build_evidence_batches(
        enriched_results,
        target_chars=BOUNDED_BATCH_TARGET_CHARS,
    )
    coverage = _coverage_text(evidence)

    import os as _os
    import time as _time

    _timing_enabled = _os.getenv("LEGALRAG_ASSISTANT_TIMING") == "1"
    _bounded_started = _time.perf_counter() if _timing_enabled else 0.0
    if _timing_enabled:
        print(
            "LEGALRAG_TIMING BOUNDED_BATCH_COUNT="
            f"{len(batches)}"
        )
        print(
            "LEGALRAG_TIMING BOUNDED_PROVIDER_TIMEOUT_SECONDS="
            f"{BOUNDED_PROVIDER_TIMEOUT_SECONDS:.1f}"
        )

    mapped: list[str] = []
    for batch_index, batch in enumerate(batches, start=1):
        prompt = _map_prompt(question=question, batch=batch, coverage=coverage)
        prompt = _apply_prompt_wrapper(
            prompt,
            question=question,
            prompt_wrapper=prompt_wrapper,
        )
        # Intermediate bounded map passes perform source-bound evidence extraction.
        # The full final-answer analytical constraint is deferred to the reduce pass,
        # avoiding duplication of the same large authority projection in every batch.
        _map_started = _time.perf_counter() if _timing_enabled else 0.0
        if _timing_enabled:
            print(
                "LEGALRAG_TIMING BOUNDED_MAP_START "
                f"INDEX={batch_index}/{len(batches)} "
                f"PROMPT_CHARS={len(prompt)}"
            )
        try:
            mapped_answer = _provider_call(
                client,
                model=model,
                prompt=prompt,
                max_output_tokens=MAP_MAX_OUTPUT_TOKENS,
                reasoning_effort=reasoning_effort,
            )
        except Exception as exc:
            if _timing_enabled:
                print(
                    "LEGALRAG_TIMING BOUNDED_MAP_FAILED "
                    f"INDEX={batch_index}/{len(batches)} "
                    f"ELAPSED_MS={(_time.perf_counter() - _map_started) * 1000:.1f} "
                    f"ERROR_TYPE={type(exc).__name__}"
                )
            raise
        mapped.append(mapped_answer)
        if _timing_enabled:
            print(
                "LEGALRAG_TIMING BOUNDED_MAP_MS "
                f"INDEX={batch_index}/{len(batches)} "
                f"VALUE={(_time.perf_counter() - _map_started) * 1000:.1f}"
            )

    final_prompt = _reduce_prompt(
        question=question,
        evidence=evidence,
        mapped=tuple(mapped),
    )
    final_prompt = _apply_prompt_wrapper(
        final_prompt,
        question=question,
        prompt_wrapper=prompt_wrapper,
    )
    final_prompt = _apply_constraint(
        final_prompt,
        analytical_context=analytical_context,
        constrain_prompt=constrain_prompt,
    )
    _reduce_started = _time.perf_counter() if _timing_enabled else 0.0
    if _timing_enabled:
        print(
            "LEGALRAG_TIMING BOUNDED_REDUCE_START "
            f"PROMPT_CHARS={len(final_prompt)} "
            f"MAP_RESULTS={len(mapped)}"
        )
    try:
        answer = _provider_call(
            client,
            model=model,
            prompt=final_prompt,
            max_output_tokens=REDUCE_MAX_OUTPUT_TOKENS,
            reasoning_effort=reasoning_effort,
            output_schema=output_schema,
        )
    except Exception as exc:
        if _timing_enabled:
            print(
                "LEGALRAG_TIMING BOUNDED_REDUCE_FAILED "
                f"ELAPSED_MS={(_time.perf_counter() - _reduce_started) * 1000:.1f} "
                f"ERROR_TYPE={type(exc).__name__}"
            )
        raise
    if _timing_enabled:
        print(
            "LEGALRAG_TIMING BOUNDED_REDUCE_MS="
            f"{(_time.perf_counter() - _reduce_started) * 1000:.1f}"
        )
        print(
            "LEGALRAG_TIMING BOUNDED_TOTAL_MS="
            f"{(_time.perf_counter() - _bounded_started) * 1000:.1f}"
        )
    return SimpleNamespace(output_text=answer)


__all__ = [
    "BOUNDED_ANSWER_TRIGGER_CHARS",
    "BOUNDED_BATCH_TARGET_CHARS",
    "EvidenceBatch",
    "build_evidence_batches",
    "create_bounded_governed_response",
    "should_use_bounded_governed_answer",
]
