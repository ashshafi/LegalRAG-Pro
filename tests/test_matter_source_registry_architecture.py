from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_registry_lives_under_legalrag_data_root_and_not_case_analysis_state():
    source = (ROOT / "src/matter_sources/registry.py").read_text(encoding="utf-8")
    assert "from persistence_paths import data_root" in source
    assert 'data_root() / "integrations" / "matter_sources.sqlite3"' in source
    for token in (
        "current_assessment",
        "solicitor_tasks",
        "working_draft",
        "professional_release",
        "approved_work_product",
        "report_projection",
        "chromadb",
        "openai",
    ):
        assert token not in source.lower()


def test_registry_has_no_leap_network_or_credential_contract():
    source = (ROOT / "src/matter_sources/registry.py").read_text(encoding="utf-8").lower()
    for token in (
        "requests.",
        "httpx.",
        "aiohttp",
        "client_secret",
        "refresh_token",
        "oauth/token",
        "api.leap",
    ):
        assert token not in source
