"""Evidence-grounded answer generation for LegalRAG Pro."""

from __future__ import annotations

from governed_answer_output_schema import (
    build_governed_answer_output_schema,
    canonicalize_exact_duplicate_source_proposition_refs,
)
from new_ai_finding import (
    NEW_AI_FINDING_NOTICE,
    is_source_comparison_new_ai_finding,
    wrap_source_comparison_new_ai_finding_prompt,
)

import logging
import os
import time
from collections.abc import Sequence

from config import openai_client
from evidence_answer import (
    EVIDENCE_ROLE_BASIS_KEY,
    EVIDENCE_ROLE_KEY,
    EVIDENCE_ROLE_RULE_KEY,
    GOVERNED_DISCOVERY_RANK_KEY,
    GOVERNED_SEARCH_MODE_KEY,
    GovernedAnswerEvidenceError,
    build_governed_answer_prompt,
    prepare_governed_answer_evidence,
)
from evidence_classification import (
    EVIDENCE_CLASSIFICATION_METHOD_KEY,
    EVIDENCE_SOURCE_LABEL_KEY,
    EVIDENCE_SOURCE_TYPE_KEY,
)
from chunk_provenance import (
    CHUNK_PROVENANCE_METHOD_KEY,
    CHUNK_SOURCE_LABEL_KEY,
    CHUNK_SOURCE_TYPE_KEY,
    PRIMARY_SOURCE_LABEL_KEY,
    PRIMARY_SOURCE_TIER_KEY,
)
from evidence_reranking import (
    RETRIEVAL_ORIGINAL_RANK_KEY,
    RETRIEVAL_PROMOTION_KEY,
    RETRIEVAL_RERANK_RANK_KEY,
)
from evidence_semantics import (
    KNOWLEDGE_SIGNAL_KEY,
    KNOWLEDGE_SIGNAL_LABEL_KEY,
    PROVENANCE_BASIS_KEY,
    PROVENANCE_CONFIDENCE_KEY,
    PROVENANCE_WARNING_KEY,
    SEMANTIC_SOURCE_LABEL_KEY,
    SEMANTIC_SOURCE_TYPE_KEY,
    enrich_evidence_semantics,
)
from ai_provider_policy import (
    AIDataClassification,
    AIProcessingPurpose,
    assert_ai_processing_allowed,
)
from semantic_reasoning import (
    build_semantic_context,
    build_semantic_legal_prompt,
)
from bounded_governed_answer import (
    create_bounded_governed_response,
    should_use_bounded_governed_answer,
)
from interactive_governed_answer import build_interactive_governed_answer_prompt
from models import CHAT_MODEL

INTERACTIVE_CHAT_MODEL = os.getenv("LEGALRAG_INTERACTIVE_CHAT_MODEL", "gpt-5.6-terra").strip() or "gpt-5.6-terra"
INTERACTIVE_REASONING_EFFORT = os.getenv("LEGALRAG_INTERACTIVE_REASONING_EFFORT", "none").strip().lower() or "none"
if INTERACTIVE_REASONING_EFFORT not in {"none", "low", "medium", "high", "xhigh", "max"}:
    raise RuntimeError("Invalid LEGALRAG_INTERACTIVE_REASONING_EFFORT.")
from retriever import retrieve


LOGGER = logging.getLogger(__name__)
_GOVERNED_FAILURE_ANSWER = (
    "I could not establish a complete governed evidence set for this question. "
    "No corpus-level negative finding has been made."
)
_GOVERNED_ANALYTICAL_FAILURE_ANSWER = (
    "I could not validate the governed analytical constraint for this answer. "
    "No analytically governed answer has been presented."
)


_LEGAL_ANSWER_PROVIDER_TIMEOUT_SECONDS = 60.0
_LEGAL_ANSWER_PROVIDER_MAX_RETRIES = 0


def _legal_answer_provider_client():
    """Return the OpenAI client with a finite interactive legal-answer policy."""
    return openai_client.with_options(
        timeout=_LEGAL_ANSWER_PROVIDER_TIMEOUT_SECONDS,
        max_retries=_LEGAL_ANSWER_PROVIDER_MAX_RETRIES,
    )

def _log_analytical_binding_failure_diagnostics(
    *,
    raw_output: str,
    context: Any,
) -> None:
    """Emit structural-only binding diagnostics when interactive timing is enabled."""

    import json as _json
    import os as _os

    if _os.getenv("LEGALRAG_ASSISTANT_TIMING") != "1":
        return

    try:
        data = _json.loads(raw_output)
        rows = data.get("statements") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            print(
                "LEGALRAG_TIMING ANALYTICAL_BINDING_DIAGNOSTIC "
                "PARSE_STATE=NO_STATEMENT_ARRAY"
            )
            return

        proposition_status_by_coordinate: dict[tuple[str, str, int], str] = {}
        issue_analysis_id = str(getattr(context, "issue_analysis_id", ""))

        for element in getattr(context, "elements", ()):
            element_id = str(getattr(element, "element_id", ""))
            for proposition in getattr(element, "propositions", ()):
                reference = getattr(proposition, "reference", None)
                ref_element_id = str(
                    getattr(reference, "element_id", "") or element_id
                )
                source_index = getattr(
                    reference, "source_proposition_index", None
                )
                if not isinstance(source_index, int):
                    continue

                status = getattr(proposition, "status", "")
                status = getattr(status, "value", status)
                proposition_status_by_coordinate[
                    (issue_analysis_id, ref_element_id, source_index)
                ] = str(status)

        offending: list[tuple[int, str, int, tuple[str, ...], int, str]] = []

        for statement_index, row in enumerate(rows):
            if not isinstance(row, dict):
                offending.append(
                    (statement_index, "<non-object>", 0, (), 0, "<missing>")
                )
                continue

            statement_id = str(row.get("statement_id", "<missing>"))
            declared_status = str(row.get("source_status", "<missing>"))
            refs = row.get("source_proposition_refs")
            if not isinstance(refs, list):
                offending.append(
                    (statement_index, statement_id, 0, (), 0, declared_status)
                )
                continue

            resolved_statuses: list[str] = []
            unknown_refs = 0

            for ref in refs:
                if not isinstance(ref, dict):
                    unknown_refs += 1
                    continue

                source_index = ref.get("source_proposition_index")
                if not isinstance(source_index, int):
                    unknown_refs += 1
                    continue

                coordinate = (
                    str(ref.get("issue_analysis_id", "")),
                    str(ref.get("element_id", "")),
                    source_index,
                )
                status = proposition_status_by_coordinate.get(coordinate)
                if status is None:
                    unknown_refs += 1
                else:
                    resolved_statuses.append(status)

            distinct_statuses = tuple(sorted(set(resolved_statuses)))
            if len(distinct_statuses) != 1 or unknown_refs:
                offending.append(
                    (
                        statement_index,
                        statement_id,
                        len(refs),
                        distinct_statuses,
                        unknown_refs,
                        declared_status,
                    )
                )

        print(
            "LEGALRAG_TIMING ANALYTICAL_BINDING_DIAGNOSTIC "
            f"STATEMENTS={len(rows)} OFFENDING={len(offending)}"
        )

        for (
            statement_index,
            statement_id,
            ref_count,
            statuses,
            unknown_refs,
            declared_status,
        ) in offending[:20]:
            status_csv = ",".join(statuses) if statuses else "<none>"
            print(
                "LEGALRAG_TIMING ANALYTICAL_BINDING_OFFENDER "
                f"INDEX={statement_index} "
                f"STATEMENT_ID={statement_id} "
                f"REF_COUNT={ref_count} "
                f"RESOLVED_STATUSES={status_csv} "
                f"UNKNOWN_REFS={unknown_refs} "
                f"DECLARED_SOURCE_STATUS={declared_status}"
            )

    except Exception as diagnostic_error:
        print(
            "LEGALRAG_TIMING ANALYTICAL_BINDING_DIAGNOSTIC "
            f"ERROR_TYPE={type(diagnostic_error).__name__}"
        )


def ask(
    question: str,
    selected_documents: Sequence[str] | None = None,
    *,
    case_id: str | None = None,
) -> dict:
    """Ask a legal question using evidence from the requested case.

    Case-scoped questions use U8 governed retrieval: semantic search discovers
    source-bound documents, then every governed page/chunk in those documents is
    completely expanded and classified before the answer prompt is built.
    Legacy/global questions with no case ID retain the pre-U8 retrieval path.
    """

    governed_evidence = None
    analytical_mode = None
    analytical_reason = None
    analytical_authority_id = None
    analytical_activation_id = None
    analytical_context = None
    new_ai_prompt_wrapper = None
    validated_analytical_answer = None
    new_ai_finding_mode = False

    _timing_enabled = os.getenv("LEGALRAG_ASSISTANT_TIMING") == "1"
    _total_started = time.perf_counter() if _timing_enabled else 0.0

    if case_id is not None:
        try:
            _governed_started = time.perf_counter() if _timing_enabled else 0.0
            governed_evidence = prepare_governed_answer_evidence(
                question=question,
                selected_documents=selected_documents,
                case_id=case_id,
                interactive_semantic_only=True,
            )
            if _timing_enabled:
                print(
                    "LEGALRAG_TIMING GOVERNED_PREPARATION_MS="
                    f"{(time.perf_counter() - _governed_started) * 1000:.1f}"
                )
        except GovernedAnswerEvidenceError:
            LOGGER.exception(
                "Governed U8 answer retrieval failed for case %s.",
                case_id,
            )
            return {
                "answer": _GOVERNED_FAILURE_ANSWER,
                "sources": [],
                "search_results": {
                    "ids": [[]],
                    "documents": [[]],
                    "metadatas": [[]],
                },
                "retrieval_mode": "governed_failed_closed",
                "semantic_discovery_receipt": None,
                "evidence_search_receipt": None,
            }

        new_ai_finding_mode = is_source_comparison_new_ai_finding(
            question=question,
            evidence=governed_evidence,
        )

        _prompt_started = time.perf_counter() if _timing_enabled else 0.0
        if new_ai_finding_mode:
            new_ai_prompt_wrapper = lambda *, base_prompt, question: (
                wrap_source_comparison_new_ai_finding_prompt(
                    base_prompt=base_prompt,
                    question=question,
                    explicit_location=governed_evidence.explicit_location,
                )
            )
            # A resolved explicit source/location comparison is a NEW finding, not
            # a rerender of the frozen Current Assessment. Use the already-complete
            # U8 document surface so the exact requested location is provider-visible.
            results = enrich_evidence_semantics(governed_evidence.answer_results)
            base_prompt = build_governed_answer_prompt(
                question=question,
                evidence=governed_evidence,
                enriched_results=results,
            )
            base_prompt = new_ai_prompt_wrapper(
                base_prompt=base_prompt,
                question=question,
            )
        elif governed_evidence.semantic_results is not None:
            # Ordinary solicitor questions use the governed semantic discovery rows
            # for the provider-facing answer context. U8 has already verified each
            # row against its completely expanded governed source document.
            _semantic_enrichment_started = time.perf_counter() if _timing_enabled else 0.0
            results = enrich_evidence_semantics(governed_evidence.semantic_results)
            if _timing_enabled:
                print(
                    "LEGALRAG_TIMING SEMANTIC_ENRICHMENT_MS="
                    f"{(time.perf_counter() - _semantic_enrichment_started) * 1000:.1f}"
                )

            _interactive_prompt_started = time.perf_counter() if _timing_enabled else 0.0
            base_prompt = build_interactive_governed_answer_prompt(
                question=question,
                enriched_results=results,
            )
            if _timing_enabled:
                print(
                    "LEGALRAG_TIMING INTERACTIVE_PROMPT_BUILD_MS="
                    f"{(time.perf_counter() - _interactive_prompt_started) * 1000:.1f}"
                )
        else:
            # Explicit exhaustive questions preserve the existing document/corpus-
            # complete provider path. Large exhaustive prompts remain bounded by the
            # map/reduce provider boundary below.
            results = enrich_evidence_semantics(governed_evidence.answer_results)
            base_prompt = build_governed_answer_prompt(
                question=question,
                evidence=governed_evidence,
                enriched_results=results,
            )

        # Supplementary derived-transcription candidates remain
        # candidate_discovery_only and never become FULL_CHAIN evidence.
        _derived_started = time.perf_counter() if _timing_enabled else 0.0
        try:
            from derived_transcription_answer_context import (
                augment_governed_answer_prompt_with_derived_candidates,
            )

            base_prompt = (
                augment_governed_answer_prompt_with_derived_candidates(
                    base_prompt=base_prompt,
                    question=question,
                    case_id=case_id,
                )
            )
        except Exception:
            LOGGER.exception(
                "Derived transcription candidate discovery failed for case %s.",
                case_id,
            )
        finally:
            if _timing_enabled:
                print(
                    "LEGALRAG_TIMING DERIVED_TRANSCRIPTION_AUGMENT_MS="
                    f"{(time.perf_counter() - _derived_started) * 1000:.1f}"
                )

        if new_ai_finding_mode:
            prompt = base_prompt
            analytical_reason = NEW_AI_FINDING_NOTICE
        else:
            # B15 is deliberately lazy-imported inside the case-scoped branch so the
            # legacy/no-case path does not acquire new analytical runtime dependencies.
            _authority_import_started = time.perf_counter() if _timing_enabled else 0.0
            from governed_analytical_authority.provider import (
                GovernedAnalyticalAuthorityProviderError,
                load_active_governed_analytical_authority,
            )
            from governed_answer_authority import (
                AnalyticalAuthorityMode,
                GovernedAnswerAuthorityError,
                GovernedAnswerBindingError,
                answer_statement_bindings_payload,
                build_constrained_governed_answer_prompt,
                build_runtime_authority_context,
                route_question_to_active_authority,
                validate_answer_statement_bindings,
            )
            if _timing_enabled:
                print(
                    "LEGALRAG_TIMING AUTHORITY_IMPORT_MS="
                    f"{(time.perf_counter() - _authority_import_started) * 1000:.1f}"
                )

            try:
                _authority_load_started = time.perf_counter() if _timing_enabled else 0.0
                active_authority = load_active_governed_analytical_authority(
                    case_id,
                    reuse_validated_runtime_authority=True,
                )
                if _timing_enabled:
                    print(
                        "LEGALRAG_TIMING AUTHORITY_LOAD_MS="
                        f"{(time.perf_counter() - _authority_load_started) * 1000:.1f}"
                    )
                if active_authority is None:
                    analytical_mode = AnalyticalAuthorityMode.ABSENT
                    analytical_reason = (
                        "No active governed analytical authority is available for this case."
                    )
                    prompt = base_prompt
                else:
                    analytical_authority_id = active_authority.manifest.authority_id
                    analytical_activation_id = active_authority.active_pointer.activation_id
                    _authority_routing_started = time.perf_counter() if _timing_enabled else 0.0
                    routing = route_question_to_active_authority(
                        question=question,
                        case_id=case_id,
                        authority=active_authority,
                    )
                    if _timing_enabled:
                        print(
                            "LEGALRAG_TIMING AUTHORITY_ROUTING_MS="
                            f"{(time.perf_counter() - _authority_routing_started) * 1000:.1f}"
                        )
                    analytical_reason = routing.reason
                    if routing.mode is AnalyticalAuthorityMode.UNAVAILABLE:
                        analytical_mode = AnalyticalAuthorityMode.UNAVAILABLE
                        prompt = base_prompt
                    else:
                        analytical_mode = AnalyticalAuthorityMode.APPLIED
                        inspected_evidence_keys = tuple(
                            _first_query_row(results.get("ids"))
                        )
                        _authority_context_started = time.perf_counter() if _timing_enabled else 0.0
                        analytical_context = build_runtime_authority_context(
                            authority=active_authority,
                            routing=routing,
                            inspected_evidence_keys=inspected_evidence_keys,
                        )
                        if _timing_enabled:
                            print(
                                "LEGALRAG_TIMING AUTHORITY_CONTEXT_BUILD_MS="
                                f"{(time.perf_counter() - _authority_context_started) * 1000:.1f}"
                            )

                        _authority_constraint_started = time.perf_counter() if _timing_enabled else 0.0
                        prompt = build_constrained_governed_answer_prompt(
                            base_prompt=base_prompt,
                            context=analytical_context,
                        )
                        if _timing_enabled:
                            print(
                                "LEGALRAG_TIMING AUTHORITY_CONSTRAINT_PROMPT_MS="
                                f"{(time.perf_counter() - _authority_constraint_started) * 1000:.1f}"
                            )
            except (
                GovernedAnalyticalAuthorityProviderError,
                GovernedAnswerAuthorityError,
                ValueError,
            ):
                LOGGER.exception(
                    "Governed analytical authority validation failed for case %s.",
                    case_id,
                )
                return _analytical_failure_payload(
                    results=results,
                    governed_evidence=governed_evidence,
                    authority_id=analytical_authority_id,
                    activation_id=analytical_activation_id,
                    mode="invalid_authority",
                )
    else:
        results = retrieve(
            question,
            selected_documents,
            n_results=10,
            case_id=case_id,
        )

        # Milestone 4 runs strictly after the frozen retrieval/reranking pipeline.
        # It enriches the already-selected evidence without changing order or scope.
        results = enrich_evidence_semantics(results)
        context = build_semantic_context(results)
        prompt = build_semantic_legal_prompt(question=question, context=context)

    if _timing_enabled:
        print(
            "LEGALRAG_TIMING PROMPT_PREPARATION_MS="
            f"{(time.perf_counter() - _prompt_started) * 1000:.1f}"
        )

    assert_ai_processing_allowed(
        provider="openai",
        purpose=AIProcessingPurpose.LEGAL_ANSWER,
        data_classification=AIDataClassification.PRIVILEGED,
        model=(INTERACTIVE_CHAT_MODEL if new_ai_finding_mode else CHAT_MODEL),
    )
    _answer_started = time.perf_counter() if _timing_enabled else 0.0
    legal_answer_client = _legal_answer_provider_client()
    if _timing_enabled:
        print(
            "LEGALRAG_TIMING PROVIDER_TIMEOUT_SECONDS="
            f"{_LEGAL_ANSWER_PROVIDER_TIMEOUT_SECONDS:.1f}"
        )
        print(
            "LEGALRAG_TIMING PROVIDER_MAX_RETRIES="
            f"{_LEGAL_ANSWER_PROVIDER_MAX_RETRIES}"
        )
    if (
        case_id is not None
        and governed_evidence is not None
        and should_use_bounded_governed_answer(prompt)
    ):
        response = create_bounded_governed_response(
            client=legal_answer_client,
            model=(
                INTERACTIVE_CHAT_MODEL
                if (new_ai_finding_mode or analytical_context is not None)
                else CHAT_MODEL
            ),
            question=question,
            evidence=governed_evidence,
            enriched_results=results,
            analytical_context=analytical_context,
            constrain_prompt=(
                build_constrained_governed_answer_prompt
                if analytical_context is not None
                else None
            ),
            prompt_wrapper=(
                new_ai_prompt_wrapper
                if new_ai_finding_mode
                else None
            ),
            reasoning_effort=(
                INTERACTIVE_REASONING_EFFORT
                if (new_ai_finding_mode or analytical_context is not None)
                else None
            ),
            output_schema=(
                build_governed_answer_output_schema(analytical_context)
                if analytical_context is not None
                else None
            ),
        )
    else:
        assert_ai_processing_allowed(
            provider="openai",
            purpose=AIProcessingPurpose.LEGAL_ANSWER,
            data_classification=AIDataClassification.PRIVILEGED,
            model=INTERACTIVE_CHAT_MODEL,
        )
        if (
            case_id is not None
            and analytical_mode is not None
            and analytical_mode.value == "applied"
        ):
            response = legal_answer_client.responses.create(
                model=INTERACTIVE_CHAT_MODEL,
                input=prompt,
                reasoning={"effort": INTERACTIVE_REASONING_EFFORT},
                store=False,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "governed_analytical_answer",
                        "strict": True,
                        "schema": build_governed_answer_output_schema(analytical_context),
                    }
                },
            )
        else:
            response = legal_answer_client.responses.create(
                model=INTERACTIVE_CHAT_MODEL,
                input=prompt,
                reasoning={"effort": INTERACTIVE_REASONING_EFFORT},
                store=False,
            )

    if _timing_enabled:
        print(
            "LEGALRAG_TIMING OPENAI_LEGAL_ANSWER_MS="
            f"{(time.perf_counter() - _answer_started) * 1000:.1f}"
        )
        print(
            "LEGALRAG_TIMING TOTAL_TO_PROVIDER_RESPONSE_MS="
            f"{(time.perf_counter() - _total_started) * 1000:.1f}"
        )

    if case_id is not None and analytical_mode is not None:
        if analytical_mode.value == "applied":
            try:
                normalized_analytical_output, duplicate_ref_count = (
                    canonicalize_exact_duplicate_source_proposition_refs(
                        response.output_text
                    )
                )
                if duplicate_ref_count:
                    LOGGER.warning(
                        "Canonicalized %d exact duplicate governed proposition reference(s) "
                        "before fail-closed validation for case %s.",
                        duplicate_ref_count,
                        case_id,
                    )
                validated_analytical_answer = validate_answer_statement_bindings(
                    raw_output=normalized_analytical_output,
                    context=analytical_context,
                )
            except GovernedAnswerAuthorityError as exc:
                LOGGER.exception(
                    "Generated analytical answer bindings failed validation for case %s.",
                    case_id,
                )
                _log_analytical_binding_failure_diagnostics(
                    raw_output=normalized_analytical_output,
                    context=analytical_context,
                )
                validation_error = type(exc).__name__
                if isinstance(exc, GovernedAnswerBindingError):
                    validation_message = " ".join(str(exc).split())[:240]
                    if validation_message:
                        validation_error = (
                            f"{validation_error}: {validation_message}"
                        )
                return _analytical_failure_payload(
                    results=results,
                    governed_evidence=governed_evidence,
                    authority_id=analytical_authority_id,
                    activation_id=analytical_activation_id,
                    mode="invalid_analytical_output",
                    validation_error=validation_error,
                )

    sources = _build_sources(results)

    payload = {
        "answer": (
            validated_analytical_answer.answer
            if validated_analytical_answer is not None
            else response.output_text
        ),
        "sources": sources,
        "search_results": results,
    }
    if new_ai_finding_mode:
        payload["answer"] = (
            NEW_AI_FINDING_NOTICE
            + "\n\n"
            + str(payload["answer"]).lstrip()
        )
        payload.update(
            {
                "new_ai_finding": True,
                "new_ai_finding_kind": "source_comparison",
                "new_ai_finding_status": "professional_review_required",
                "current_assessment_changed": False,
                "new_ai_finding_notice": NEW_AI_FINDING_NOTICE,
            }
        )

    if governed_evidence is not None:
        payload.update(
            {
                "retrieval_mode": governed_evidence.search_mode.value,
                "semantic_discovery_receipt": governed_evidence.semantic_receipt,
                "evidence_search_receipt": (
                    governed_evidence.search_result.receipt
                    if governed_evidence.search_result is not None
                    else governed_evidence.semantic_receipt
                ),
                "analytical_authority_mode": (
                    analytical_mode.value if analytical_mode is not None else None
                ),
                "analytical_authority_reason": analytical_reason,
                "analytical_authority_id": analytical_authority_id,
                "analytical_activation_id": analytical_activation_id,
            }
        )
        if validated_analytical_answer is not None:
            payload.update(
                {
                    "answer_statement_bindings": answer_statement_bindings_payload(
                        validated_analytical_answer.bindings
                    ),
                    "relied_evidence_keys": list(
                        validated_analytical_answer.relied_evidence_keys
                    ),
                }
            )
    return payload


def _analytical_failure_payload(
    *,
    results: dict,
    governed_evidence,
    authority_id: str | None,
    activation_id: str | None,
    mode: str,
    validation_error: str | None = None,
) -> dict:
    """Return an analytical fail-closed result without replacing U8 retrieval state."""

    payload = {
        "answer": _GOVERNED_ANALYTICAL_FAILURE_ANSWER,
        "sources": _build_sources(results),
        "search_results": results,
        "retrieval_mode": governed_evidence.search_mode.value,
        "semantic_discovery_receipt": governed_evidence.semantic_receipt,
        "evidence_search_receipt": (
                    governed_evidence.search_result.receipt
                    if governed_evidence.search_result is not None
                    else governed_evidence.semantic_receipt
                ),
        "analytical_authority_mode": mode,
        "analytical_authority_reason": "Governed analytical validation failed closed.",
        "analytical_authority_id": authority_id,
        "analytical_activation_id": activation_id,
        "answer_statement_bindings": [],
        "relied_evidence_keys": [],
    }
    if validation_error:
        payload["analytical_validation_error"] = validation_error
    return payload


def _build_sources(results: dict) -> list[dict]:
    sources = []
    documents = _first_query_row(results.get("documents"))
    metadatas = _first_query_row(results.get("metadatas"))

    for index, text in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}

        sources.append(
            {
                "file": metadata.get("file", "Unknown document"),
                "page": metadata.get("page", "?"),
                "text": text,
                "source_type": metadata.get(
                    EVIDENCE_SOURCE_TYPE_KEY,
                    "other",
                ),
                "source_label": metadata.get(
                    EVIDENCE_SOURCE_LABEL_KEY,
                    "Unclassified evidence",
                ),
                "classification_method": metadata.get(
                    EVIDENCE_CLASSIFICATION_METHOD_KEY,
                    "unknown",
                ),
                "chunk_source_type": metadata.get(
                    CHUNK_SOURCE_TYPE_KEY,
                    "other",
                ),
                "chunk_source_label": metadata.get(
                    CHUNK_SOURCE_LABEL_KEY,
                    "Unclassified evidence",
                ),
                "chunk_provenance_method": metadata.get(
                    CHUNK_PROVENANCE_METHOD_KEY,
                    "unknown",
                ),
                "primary_source_tier": metadata.get(
                    PRIMARY_SOURCE_TIER_KEY,
                    0,
                ),
                "primary_source_label": metadata.get(
                    PRIMARY_SOURCE_LABEL_KEY,
                    "Unclassified source",
                ),
                "original_rank": metadata.get(
                    RETRIEVAL_ORIGINAL_RANK_KEY,
                ),
                "rerank_rank": metadata.get(
                    RETRIEVAL_RERANK_RANK_KEY,
                ),
                "primary_source_promotion": metadata.get(
                    RETRIEVAL_PROMOTION_KEY,
                    0,
                ),
                "semantic_source_type": metadata.get(
                    SEMANTIC_SOURCE_TYPE_KEY,
                    "other",
                ),
                "semantic_source_label": metadata.get(
                    SEMANTIC_SOURCE_LABEL_KEY,
                    "Unclassified evidence",
                ),
                "provenance_basis": metadata.get(
                    PROVENANCE_BASIS_KEY,
                    "unknown",
                ),
                "provenance_confidence": metadata.get(
                    PROVENANCE_CONFIDENCE_KEY,
                    "low",
                ),
                "provenance_warning": metadata.get(
                    PROVENANCE_WARNING_KEY,
                    "",
                ),
                "knowledge_signal": metadata.get(
                    KNOWLEDGE_SIGNAL_KEY,
                    "none",
                ),
                "knowledge_signal_label": metadata.get(
                    KNOWLEDGE_SIGNAL_LABEL_KEY,
                    "No explicit knowledge indicator detected",
                ),
                "evidence_role": metadata.get(
                    EVIDENCE_ROLE_KEY,
                    "",
                ),
                "evidence_role_rule": metadata.get(
                    EVIDENCE_ROLE_RULE_KEY,
                    "",
                ),
                "evidence_role_basis": metadata.get(
                    EVIDENCE_ROLE_BASIS_KEY,
                    "",
                ),
                "semantic_discovery_rank": metadata.get(
                    GOVERNED_DISCOVERY_RANK_KEY,
                ),
                "governed_search_mode": metadata.get(
                    GOVERNED_SEARCH_MODE_KEY,
                    "",
                ),
                "source_document_instance_id": metadata.get(
                    "source_document_instance_id",
                    "",
                ),
                "evidence_key": (
                    _first_query_row(results.get("ids"))[index]
                    if index < len(_first_query_row(results.get("ids")))
                    else ""
                ),
            }
        )

    return sources


def _first_query_row(value) -> list:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else []
