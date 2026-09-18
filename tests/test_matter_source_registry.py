from pathlib import Path

import pytest

from matter_sources.fake import FakeMatterSourceConnector
from matter_sources.models import ExternalDocument, ExternalMatter, ProviderIdentity, SyncDisposition
from matter_sources.registry import MatterSourceRegistry, MatterSourceRegistryError
from matter_sources.sync import build_sync_plan, observations_after_plan


def _connector(content=b"%PDF-1.4\none\n", version="v1"):
    matter = ExternalMatter(source_matter_id="m1", matter_reference="A1", title="Matter")
    doc = ExternalDocument(
        source_document_id="d1",
        source_matter_id="m1",
        display_name="One.pdf",
        media_type="application/pdf",
        source_version_id=version,
    )
    return FakeMatterSourceConnector(
        provider=ProviderIdentity(provider="leap", firm_id="firm-1"),
        matters=(matter,),
        documents=(doc,),
        content={"d1": content},
    )


def test_registry_round_trip_supports_restart_safe_unchanged_sync(tmp_path):
    connector = _connector()
    provider = connector.provider_identity()
    registry = MatterSourceRegistry(tmp_path / "registry.sqlite3")

    first = build_sync_plan(connector, source_matter_id="m1")
    registry.record_successful_sync(
        provider=provider,
        source_matter_id="m1",
        case_id="case-1",
        matter_reference="A1",
        title="Matter",
        plan=first,
    )

    reloaded = MatterSourceRegistry(tmp_path / "registry.sqlite3")
    previous = reloaded.load_observations(provider, "m1")
    second = build_sync_plan(connector, source_matter_id="m1", previous=previous)

    assert [entry.disposition for entry in second.entries] == [SyncDisposition.UNCHANGED]
    binding = reloaded.load_binding(provider, "m1")
    assert binding is not None
    assert binding.case_id == "case-1"


def test_registry_retains_last_captured_hash_when_external_document_disappears(tmp_path):
    connector = _connector()
    provider = connector.provider_identity()
    registry = MatterSourceRegistry(tmp_path / "registry.sqlite3")

    first = build_sync_plan(connector, source_matter_id="m1")
    first_observation = first.entries[0].current
    registry.record_successful_sync(
        provider=provider,
        source_matter_id="m1",
        case_id="case-1",
        matter_reference="A1",
        title="Matter",
        plan=first,
    )

    connector.remove_document("d1")
    second = build_sync_plan(
        connector,
        source_matter_id="m1",
        previous=registry.load_observations(provider, "m1"),
    )
    assert second.entries[0].disposition is SyncDisposition.UNAVAILABLE

    registry.record_successful_sync(
        provider=provider,
        source_matter_id="m1",
        case_id="case-1",
        matter_reference="A1",
        title="Matter",
        plan=second,
    )

    state = registry.list_document_states(provider, "m1")[0]
    assert state.availability == "unavailable"
    assert state.content_sha256 == first_observation.content_sha256


def test_registry_fails_closed_on_cross_matter_rebinding(tmp_path):
    connector = _connector()
    provider = connector.provider_identity()
    registry = MatterSourceRegistry(tmp_path / "registry.sqlite3")
    plan = build_sync_plan(connector, source_matter_id="m1")

    registry.record_successful_sync(
        provider=provider,
        source_matter_id="m1",
        case_id="case-1",
        matter_reference="A1",
        title="Matter",
        plan=plan,
    )

    with pytest.raises(MatterSourceRegistryError, match="different LegalRAG matter"):
        registry.record_successful_sync(
            provider=provider,
            source_matter_id="m1",
            case_id="case-2",
            matter_reference="A1",
            title="Matter",
            plan=plan,
        )
