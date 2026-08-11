from __future__ import annotations

import ast
from dataclasses import fields
import inspect
import os
from pathlib import Path

import governed_issue_evidence.binding as binding_module

from case_analysis.m2.matrices import (
    CaseEvidenceRecord,
    CaseMatrices,
    EvidencePropositionLink,
    EvidenceUse,
)
from evidence_retrieval.models import (
    DocumentEvidenceChunk,
    DocumentEvidenceInspection,
)
from evidence_roles.models import (
    DocumentEvidenceRoleInspection,
    EvidenceRoleClassification,
)
from evidence_search.models import (
    CaseEvidenceSearchResult,
    EvidenceSearchReceipt,
)


FORBIDDEN_IMPORT_ROOTS = {
    "chromadb",
    "document_manager",
    "legalrag",
    "openai",
    "query_expander",
    "retriever",
    "source_evidence",
    "streamlit",
}


def _field_names(cls) -> set[str]:
    return {item.name for item in fields(cls)}


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_frozen_u8_and_m2_dataclass_contracts_still_expose_required_fields():
    required = {
        CaseMatrices: {
            "schema_version",
            "case_id",
            "synthesis_id",
            "source_analysis_ids",
            "issue_matrix",
            "evidence_matrix",
            "matrix_builder_version",
        },
        CaseEvidenceRecord: {
            "evidence_key",
            "document_id",
            "document_name",
            "page",
            "chunk_id",
            "citation",
            "uses",
        },
        EvidenceUse: {
            "issue_analysis_id",
            "issue_definition_id",
            "issue_definition_version",
            "element_id",
            "element_ordinal",
            "evidence_key",
            "analytical_role",
            "mapping_relevance",
            "mapping_confidence",
            "mapping_rationale",
            "assessment_confidence",
            "assessment_rationale",
            "citation",
            "proposition_links",
        },
        EvidencePropositionLink: {
            "source_proposition_index",
            "text",
            "status",
            "confidence",
            "rationale",
            "evidence_keys",
        },
        DocumentEvidenceChunk: {
            "page_number",
            "chunk_ordinal",
            "chunk_id",
            "evidence_key",
            "evidence_binding_id",
            "binding_class",
            "bound_text_role",
            "chunk_text_sha256",
            "chunk_text_byte_length",
            "text",
        },
        DocumentEvidenceInspection: {
            "case_id",
            "source_document_instance_id",
            "source_snapshot_id",
            "original_filename",
            "original_blob_sha256",
            "original_byte_length",
            "extraction_profile_id",
            "chunking_profile_id",
            "page_count",
            "evidence_chunk_count",
            "pages",
        },
        EvidenceRoleClassification: {
            "role",
            "rule_id",
            "basis",
            "source_type",
            "source_label",
            "provenance_method",
            "primary_tier",
            "primary_label",
        },
        DocumentEvidenceRoleInspection: {
            "document",
            "document_source_type",
            "document_source_label",
            "document_source_method",
            "pages",
            "role_counts",
        },
        EvidenceSearchReceipt: {
            "schema_version",
            "case_id",
            "search_mode",
            "query_sha256",
            "case_document_count",
            "case_page_count",
            "case_chunk_count",
            "scope_document_count",
            "scope_page_count",
            "scope_chunk_count",
            "documents_completely_expanded",
            "pages_inspected",
            "chunks_inspected",
            "candidate_document_ids",
            "searched_document_ids",
            "filters_applied",
            "matched_evidence_keys",
            "completion",
            "case_corpus_complete",
            "negative_finding_scope",
            "negative_finding_permitted",
        },
        CaseEvidenceSearchResult: {
            "case_id",
            "query",
            "search_mode",
            "documents",
            "matches",
            "receipt",
        },
    }

    for cls, names in required.items():
        assert names <= _field_names(cls), (cls.__name__, sorted(names - _field_names(cls)))


def test_u9b_package_is_exactly_additive_and_contains_no_retrieval_runtime():
    package = Path(inspect.getfile(binding_module)).resolve().parent

    observed = {
        path.name
        for path in package.glob("*.py")
        if path.is_file()
    }
    assert observed == {
        "__init__.py",
        "binding.py",
        "models.py",
        "serialization.py",
        "validation.py",
    }

    for path in package.glob("*.py"):
        assert not (_import_roots(path) & FORBIDDEN_IMPORT_ROOTS)

    source = (package / "binding.py").read_text(encoding="utf-8")
    assert "search_case_evidence(" not in source
    assert "inspect_document_complete(" not in source
    assert "classify_document_evidence_roles(" not in source
    assert "CaseEvidenceSearchResult" in source
    assert "EvidenceUse" in source


def test_frozen_analytical_packages_do_not_reverse_depend_on_u9b():
    repo = Path(os.environ["LEGALRAG_U9B_C1_REPO_ROOT"]).resolve()

    for package_name in ("legal_analysis", "case_analysis"):
        package = repo / "src" / package_name
        assert package.is_dir()
        for path in package.rglob("*.py"):
            assert "governed_issue_evidence" not in path.read_text(encoding="utf-8")
