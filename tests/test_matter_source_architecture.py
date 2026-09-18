from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "matter_sources"


def test_connector_layer_contains_no_real_leap_endpoint_or_network_client():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in PKG.glob("*.py")).lower()
    for token in ("api.leap", "console.leap", "requests.", "httpx.", "aiohttp",
                  "oauth/token", "client_secret", "refresh_token"):
        assert token not in combined


def test_sync_layer_does_not_mutate_professional_or_analysis_state():
    text = (PKG / "sync.py").read_text(encoding="utf-8").lower()
    for token in ("current_assessment", "solicitor_tasks", "working_draft",
                  "professional_release", "approved_work_product", "report_projection",
                  "openai", "chromadb"):
        assert token not in text


def test_sync_layer_reuses_existing_governed_document_upload_boundary():
    text = (PKG / "sync.py").read_text(encoding="utf-8")
    assert "from document_upload import upload_case_pdf" in text
    assert "access=access" in text
    assert "case_id=case_id" in text


def test_connector_contract_is_read_only():
    text = (PKG / "base.py").read_text(encoding="utf-8")
    for method in ("create_matter", "update_matter", "delete_matter",
                   "write_document", "create_task", "writeback"):
        assert f"def {method}(" not in text
