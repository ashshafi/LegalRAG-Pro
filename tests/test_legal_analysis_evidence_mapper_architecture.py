from __future__ import annotations

import inspect
import unittest
from pathlib import Path

import legal_analysis.evidence_mapper as evidence_mapper
from legal_analysis.definitions import INITIAL_ISSUE_DEFINITIONS
from legal_analysis.registry import DEFAULT_ISSUE_DEFINITION_REGISTRY
from legal_analysis.search_profiles import DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY


class MapperArchitectureTests(unittest.TestCase):
    def test_mapper_module_has_no_direct_retriever_import(self) -> None:
        source = inspect.getsource(evidence_mapper)
        self.assertNotIn("from retriever import retrieve", source)
        self.assertNotIn("import retriever", source)

    def test_mapper_has_no_streamlit_dependency(self) -> None:
        source = inspect.getsource(evidence_mapper)
        self.assertNotIn("import streamlit", source)
        self.assertNotIn("from streamlit", source)

    def test_mapper_has_no_openai_dependency(self) -> None:
        source = inspect.getsource(evidence_mapper)
        self.assertNotIn("import openai", source)
        self.assertNotIn("from openai", source)
        self.assertNotIn("openai_client", source)

    def test_search_profiles_do_not_mutate_issue_definitions(self) -> None:
        before = tuple(
            (d.definition_id, d.version, tuple(e.element_id for e in d.elements))
            for d in INITIAL_ISSUE_DEFINITIONS
        )
        DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY.validate()
        after = tuple(
            (d.definition_id, d.version, tuple(e.element_id for e in d.elements))
            for d in INITIAL_ISSUE_DEFINITIONS
        )
        self.assertEqual(before, after)

    def test_default_issue_registry_is_unchanged_by_profile_validation(self) -> None:
        before = DEFAULT_ISSUE_DEFINITION_REGISTRY.list_definitions()
        DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY.validate()
        self.assertEqual(before, DEFAULT_ISSUE_DEFINITION_REGISTRY.list_definitions())

    def test_m3_runtime_surface_is_additive(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "legal_analysis"
        for name in ("search_profiles.py", "evidence_mapping.py", "evidence_mapper.py"):
            self.assertTrue((root / name).is_file())


if __name__ == "__main__":
    unittest.main()
