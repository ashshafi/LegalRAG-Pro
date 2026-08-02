"""Registry for versioned controlled legal issue definitions."""

from __future__ import annotations

from collections.abc import Iterable

from .definitions import INITIAL_ISSUE_DEFINITIONS
from .enums import IssueDefinitionStatus
from .models import IssueDefinition
from .validation import validate_issue_definition


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


class IssueDefinitionRegistry:
    """Store and retrieve immutable issue-definition versions by stable key."""

    def __init__(self, definitions: Iterable[IssueDefinition] = ()) -> None:
        self._definitions: dict[tuple[str, str], IssueDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: IssueDefinition) -> None:
        """Register one exact definition version, rejecting duplicates."""

        validate_issue_definition(definition)
        if definition.key in self._definitions:
            raise ValueError(
                f"Issue definition {definition.definition_id} version {definition.version} is already registered."
            )
        active_for_id = [
            item
            for item in self._definitions.values()
            if item.definition_id == definition.definition_id
            and item.status is IssueDefinitionStatus.ACTIVE
        ]
        if definition.status is IssueDefinitionStatus.ACTIVE and active_for_id:
            versions = ", ".join(sorted(item.version for item in active_for_id))
            raise ValueError(
                f"Issue definition {definition.definition_id} already has an active version ({versions}). Deprecate it before registering another active version."
            )
        self._definitions[definition.key] = definition

    def get_definition(
        self,
        definition_id: str,
        version: str | None = None,
    ) -> IssueDefinition:
        """Return a specific version or the sole active version for an issue ID."""

        normalized_id = definition_id.strip().upper()
        if version is not None:
            key = (normalized_id, version.strip())
            try:
                return self._definitions[key]
            except KeyError as exc:
                raise KeyError(
                    f"Unknown issue definition {normalized_id} version {version}."
                ) from exc

        active = [
            definition
            for definition in self._definitions.values()
            if definition.definition_id == normalized_id
            and definition.status is IssueDefinitionStatus.ACTIVE
        ]
        if not active:
            raise KeyError(f"No active issue definition registered for {normalized_id}.")
        if len(active) != 1:
            raise RuntimeError(
                f"Registry invariant violated: {normalized_id} has {len(active)} active versions."
            )
        return active[0]

    def list_definitions(self, *, active_only: bool = False) -> tuple[IssueDefinition, ...]:
        """Return definitions in deterministic ID/version order."""

        definitions = self._definitions.values()
        if active_only:
            definitions = (
                item for item in definitions if item.status is IssueDefinitionStatus.ACTIVE
            )
        return tuple(
            sorted(
                definitions,
                key=lambda item: (item.definition_id, _version_key(item.version)),
            )
        )

    def versions(self, definition_id: str) -> tuple[str, ...]:
        """Return all registered versions for one definition ID."""

        normalized_id = definition_id.strip().upper()
        versions = [
            definition.version
            for definition in self._definitions.values()
            if definition.definition_id == normalized_id
        ]
        return tuple(sorted(versions, key=_version_key))

    def validate(self) -> None:
        """Validate every registered definition and active-version invariant."""

        active_counts: dict[str, int] = {}
        for definition in self._definitions.values():
            validate_issue_definition(definition)
            if definition.status is IssueDefinitionStatus.ACTIVE:
                active_counts[definition.definition_id] = (
                    active_counts.get(definition.definition_id, 0) + 1
                )
        invalid = [key for key, count in active_counts.items() if count > 1]
        if invalid:
            raise ValueError(
                "Multiple active versions registered for: " + ", ".join(sorted(invalid))
            )


def build_default_registry() -> IssueDefinitionRegistry:
    """Return the registry containing the four Sprint 2.3 v1 definitions."""

    return IssueDefinitionRegistry(INITIAL_ISSUE_DEFINITIONS)


DEFAULT_ISSUE_DEFINITION_REGISTRY = build_default_registry()
