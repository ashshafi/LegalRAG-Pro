from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_import_sync_workspace_is_leap_first_and_safe_by_default():
    source = (ROOT / "src/ui/matter_source_import.py").read_text(encoding="utf-8")
    assert 'with st.sidebar.expander("Import / Sync"' in source
    assert 'st.markdown("**LEAP**")' in source
    assert "LEAP developer access is pending." in source
    assert "LEGALRAG_LEAP_FAKE_PILOT" in source
    assert "No LEAP network connection is being used." in source
    assert "Current Assessment" in source


def test_sidebar_activates_import_sync_without_extending_return_contract():
    source = (ROOT / "src/ui/sidebar.py").read_text(encoding="utf-8-sig")
    assert "from ui.matter_source_import import show_matter_source_import" in source
    assert "show_matter_source_import(active_case_id)" in source


def test_import_workspace_uses_existing_access_and_governed_sync_boundaries():
    source = (ROOT / "src/ui/matter_source_import.py").read_text(encoding="utf-8")
    assert "CaseRepository().require_access" in source
    assert "apply_pdf_sync_plan(" in source
    assert "registry.record_successful_sync(" in source
    assert "current_assessment" not in source.lower()
    assert "approved_work_product" not in source.lower()
