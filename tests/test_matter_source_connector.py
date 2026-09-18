from matter_sources.fake import FakeMatterSourceConnector
from matter_sources.models import ExternalDocument, ExternalMatter, ExternalParty, ProviderIdentity


def _provider():
    identity = ProviderIdentity(provider="leap", firm_id="firm-001")
    matter = ExternalMatter(source_matter_id="matter-1", matter_reference="A1234",
                            title="Smith v Hospital Trust", practice_area="Clinical negligence")
    party = ExternalParty(source_party_id="party-1", source_matter_id="matter-1",
                          display_name="Jane Smith", party_role="Client")
    document = ExternalDocument(source_document_id="doc-1", source_matter_id="matter-1",
                                display_name="Letter.pdf", media_type="application/pdf",
                                source_version_id="v1", source_size=12)
    connector = FakeMatterSourceConnector(
        provider=identity, matters=(matter,), parties=(party,), documents=(document,),
        content={"doc-1": b"%PDF-1.4\nx\n"},
    )
    return identity, matter, party, document, connector


def test_fake_connector_exposes_provider_neutral_read_contract():
    identity, matter, party, document, connector = _provider()
    assert connector.provider_identity() == identity
    assert connector.capabilities().writeback is False
    assert connector.list_matters() == (matter,)
    assert connector.list_matters("hospital") == (matter,)
    assert connector.get_matter("matter-1") == matter
    assert connector.list_parties("matter-1") == (party,)
    assert connector.list_documents("matter-1") == (document,)
    assert connector.fetch_document_bytes("doc-1") == b"%PDF-1.4\nx\n"


def test_fake_provider_can_model_change_and_external_deletion():
    _, _, _, _, connector = _provider()
    connector.replace_document_bytes("doc-1", b"%PDF-1.4\nchanged\n", source_version_id="v2")
    changed = connector.list_documents("matter-1")[0]
    assert changed.source_version_id == "v2"
    connector.remove_document("doc-1")
    assert connector.list_documents("matter-1") == ()
