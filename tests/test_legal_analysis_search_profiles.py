from __future__ import annotations

import unittest

from legal_analysis.definitions import INITIAL_ISSUE_DEFINITIONS
from legal_analysis.search_profiles import (
    DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY,
    ELEMENT_CANDIDATE_LIMIT,
    ELEMENT_MAPPER_VERSION,
    ELEMENT_RETAIN_LIMIT,
    ElementSearchProfile,
    ElementSearchProfileRegistry,
)


class SearchProfileTests(unittest.TestCase):
    def test_mapper_version_is_stable(self) -> None:
        self.assertEqual(ELEMENT_MAPPER_VERSION, "element-mapper/1.0")

    def test_limits_are_bounded(self) -> None:
        self.assertGreater(ELEMENT_CANDIDATE_LIMIT, 0)
        self.assertGreater(ELEMENT_RETAIN_LIMIT, 0)
        self.assertLessEqual(ELEMENT_RETAIN_LIMIT, ELEMENT_CANDIDATE_LIMIT)

    def test_all_four_definitions_have_complete_profile_coverage_in_order(self) -> None:
        for definition in INITIAL_ISSUE_DEFINITIONS:
            profiles = DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY.profiles_for_definition(definition)
            self.assertEqual(
                tuple(profile.element_id for profile in profiles),
                tuple(element.element_id for element in definition.elements),
            )

    def test_total_profile_count_matches_total_element_count(self) -> None:
        expected = sum(len(definition.elements) for definition in INITIAL_ISSUE_DEFINITIONS)
        actual = sum(
            len(DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY.profiles_for_definition(definition))
            for definition in INITIAL_ISSUE_DEFINITIONS
        )
        self.assertEqual(actual, expected)
        self.assertEqual(actual, 34)

    def test_profile_lookup_is_exact_versioned_domain_data(self) -> None:
        profile = DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY.get_profile(
            "EK-001", "1.0", "EK-DIRECT-KNOWLEDGE"
        )
        self.assertIn("receipt", profile.search_objective)
        self.assertEqual(profile.issue_definition_version, "1.0")

    def test_duplicate_profile_is_rejected(self) -> None:
        registry = ElementSearchProfileRegistry()
        profile = DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY.get_profile(
            "RA-001", "1.0", "RA-DISABILITY"
        )
        registry.register(profile)
        with self.assertRaises(ValueError):
            registry.register(profile)

    def test_unknown_element_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ElementSearchProfileRegistry(
                (
                    ElementSearchProfile(
                        issue_definition_id="RA-001",
                        issue_definition_version="1.0",
                        element_id="RA-INVENTED",
                        search_objective="Find invented evidence.",
                        search_terms=("invented",),
                    ),
                )
            )

    def test_profile_requires_search_signal(self) -> None:
        with self.assertRaises(ValueError):
            ElementSearchProfile(
                issue_definition_id="RA-001",
                issue_definition_version="1.0",
                element_id="RA-DISABILITY",
                search_objective="Find evidence.",
                search_terms=(),
            )


if __name__ == "__main__":
    unittest.main()
